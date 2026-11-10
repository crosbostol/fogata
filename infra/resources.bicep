param name string
param location string
param adminCidr string
param sshPublicKey string
param adminUsername string = 'azureuser'
@secure()
param portalPasswordHash string
@secure()
param heartbeatSecret string
param monthlyHours int
param sessionHours int
param idleMinutes int
param serverCatalogJson string = '[]'
param vmSize string

var suffix = uniqueString(resourceGroup().id)
var storageName = 'st${take(replace(name, '-', ''), 9)}${suffix}'
var functionName = 'func-${name}-${suffix}'
var tags = { application: 'fogata', managedBy: 'minecraft-azure' }

resource publicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: '${name}-ip'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
    dnsSettings: { domainNameLabel: '${name}-${suffix}' }
  }
}
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: '${name}-nsg'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'MinecraftJava'
        properties: {
          priority: 100
          access: 'Allow'
          direction: 'Inbound'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRanges: ['25565', '25566', '25567']
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AdminOnly'
        properties: {
          priority: 110
          access: 'Allow'
          direction: 'Inbound'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRanges: ['22', '2022']
          sourceAddressPrefix: adminCidr
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'PanelAndWingsHttps'
        properties: {
          priority: 120
          access: 'Allow'
          direction: 'Inbound'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRanges: ['80', '443', '8443']
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${name}-vnet'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.42.0.0/16'] }
    subnets: [
      {
        name: 'game'
        properties: {
          addressPrefix: '10.42.0.0/24'
          defaultOutboundAccess: false
          networkSecurityGroup: { id: nsg.id }
        }
      }
    ]
  }
}
resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: '${name}-nic'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'primary'
        properties: {
          privateIPAllocationMethod: 'Static'
          privateIPAddress: '10.42.0.4'
          subnet: { id: '${vnet.id}/subnets/game' }
          publicIPAddress: { id: publicIp.id }
        }
      }
    ]
  }
}
resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: '${name}-vm'
  location: location
  tags: tags
  properties: {
    hardwareProfile: { vmSize: vmSize }
    osProfile: {
      computerName: name
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        provisionVMAgent: true
        ssh: { publicKeys: [{ path: '/home/azureuser/.ssh/authorized_keys', keyData: sshPublicKey }] }
      }
    }
    storageProfile: {
      // Dasv7 (the default) is NVMe-only. Keep legacy D-series callers on SCSI.
      diskControllerType: startsWith(vmSize, 'Standard_D') && (endsWith(vmSize, '_v7') || endsWith(vmSize, '_v6')) ? 'NVMe' : 'SCSI'
      imageReference: { publisher: 'Canonical', offer: 'ubuntu-24_04-lts', sku: 'server', version: 'latest' }
      osDisk: {
        name: '${name}-os'
        createOption: 'FromImage'
        diskSizeGB: 64
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
        deleteOption: 'Delete'
      }
    }
    networkProfile: { networkInterfaces: [{ id: nic.id, properties: { primary: true, deleteOption: 'Delete' } }] }
    diagnosticsProfile: { bootDiagnostics: { enabled: true } }
    securityProfile: {
      securityType: 'TrustedLaunch'
      uefiSettings: { secureBootEnabled: true, vTpmEnabled: true }
    }
  }
}
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true // Host/state SDK and deployment use a protected storage connection.
    publicNetworkAccess: 'Enabled'
  }
}
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {}
}
resource stateContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'control'
  properties: { publicAccess: 'None' }
}
resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'app-package'
  properties: { publicAccess: 'None' }
}
var storageConnection = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
var portalOrigin = substring(storage.properties.primaryEndpoints.web, 0, max(0, length(storage.properties.primaryEndpoints.web) - 1))

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${name}-consumption'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: { name: 'FC1', tier: 'FlexConsumption' }
  properties: { reserved: true }
}
resource api 'Microsoft.Web/sites@2024-04-01' = {
  name: functionName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    functionAppConfig: {
      runtime: { name: 'python', version: '3.11' }
      scaleAndConcurrency: { instanceMemoryMB: 512, maximumInstanceCount: 40 }
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainer.name}'
          authentication: {
            type: 'StorageAccountConnectionString'
            storageAccountConnectionStringName: 'AzureWebJobsStorage'
          }
        }
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      http20Enabled: true
      cors: { allowedOrigins: [portalOrigin], supportCredentials: false }
      appSettings: [
        { name: 'AzureWebJobsStorage', value: storageConnection }
        { name: 'SUBSCRIPTION_ID', value: subscription().subscriptionId }
        { name: 'VM_RESOURCE_GROUP', value: resourceGroup().name }
        { name: 'VM_NAME', value: vm.name }
        { name: 'PORTAL_PASSWORD_SHA256', value: portalPasswordHash }
        { name: 'HEARTBEAT_SECRET', value: heartbeatSecret }
        { name: 'STATE_CONTAINER', value: stateContainer.name }
        { name: 'STATE_BLOB', value: 'state.json' }
        { name: 'SERVERS_JSON', value: serverCatalogJson }
        { name: 'MAX_MONTHLY_HOURS', value: string(monthlyHours) }
        { name: 'MAX_SESSION_HOURS', value: string(sessionHours) }
        { name: 'IDLE_MINUTES', value: string(idleMinutes) }
        { name: 'BOOT_TIMEOUT_MINUTES', value: '15' }
        { name: 'HEARTBEAT_TIMEOUT_SECONDS', value: '180' }
        { name: 'MINECRAFT_ADDRESS', value: '${publicIp.properties.ipAddress}:25565' }
        { name: 'PANEL_URL', value: 'https://${publicIp.properties.dnsSettings.fqdn}' }
        { name: 'PORTAL_ORIGIN', value: portalOrigin }
      ]
    }
  }
}
resource controllerRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'fogata-vm-controller')
  properties: {
    roleName: 'Fogata VM controller ${suffix}'
    description: 'Read state, start and deallocate one assigned VM; no RBAC or VM modification.'
    type: 'CustomRole'
    assignableScopes: [resourceGroup().id]
    permissions: [
      {
        actions: [
          'Microsoft.Compute/virtualMachines/read'
          'Microsoft.Compute/virtualMachines/instanceView/read'
          'Microsoft.Compute/virtualMachines/start/action'
          'Microsoft.Compute/virtualMachines/deallocate/action'
        ]
        notActions: []
        dataActions: []
        notDataActions: []
      }
    ]
  }
}
resource controllerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vm.id, api.id, controllerRole.id)
  scope: vm
  properties: {
    roleDefinitionId: controllerRole.id
    principalId: api.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output vmName string = vm.name
output publicIp string = publicIp.properties.ipAddress
output functionName string = api.name
output storageName string = storage.name
output portalUrl string = storage.properties.primaryEndpoints.web
output apiBaseUrl string = 'https://${api.properties.defaultHostName}'
output panelUrl string = 'https://${publicIp.properties.dnsSettings.fqdn}'
output panelHostname string = publicIp.properties.dnsSettings.fqdn
