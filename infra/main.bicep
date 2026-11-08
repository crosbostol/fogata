targetScope = 'subscription'

@minLength(3)
@maxLength(16)
param name string = 'fogata'
param location string = 'centralus'
param adminCidr string
param sshPublicKey string
@secure()
param portalPasswordHash string
@secure()
param heartbeatSecret string
param monthlyHours int = 180
param sessionHours int = 8
param idleMinutes int = 15
param serverCatalogJson string = '[]'
param vmSize string = 'Standard_D2as_v7'

resource group 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${name}'
  location: location
  tags: { application: 'fogata', managedBy: 'minecraft-azure' }
}

module resources './resources.bicep' = {
  name: '${name}-resources'
  scope: group
  params: {
    name: name
    location: location
    adminCidr: adminCidr
    sshPublicKey: sshPublicKey
    portalPasswordHash: portalPasswordHash
    heartbeatSecret: heartbeatSecret
    monthlyHours: monthlyHours
    sessionHours: sessionHours
    idleMinutes: idleMinutes
    serverCatalogJson: serverCatalogJson
    vmSize: vmSize
  }
}

output resourceGroup string = group.name
output vmName string = resources.outputs.vmName
output publicIp string = resources.outputs.publicIp
output functionName string = resources.outputs.functionName
output storageName string = resources.outputs.storageName
output portalUrl string = resources.outputs.portalUrl
output apiBaseUrl string = resources.outputs.apiBaseUrl
output panelUrl string = resources.outputs.panelUrl
output panelHostname string = resources.outputs.panelHostname
