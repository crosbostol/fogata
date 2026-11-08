[CmdletBinding()]
param(
    [Parameter(Mandatory)][guid]$SubscriptionId,
    [ValidateSet('centralus','eastus','brazilsouth')][string]$Location = 'centralus',
    [ValidatePattern('^Standard_[A-Za-z0-9_]+$')][string]$VmSize = 'Standard_D2as_v7',
    [ValidatePattern('^[a-z][a-z0-9-]{2,15}$')][string]$Name = 'fogata',
    [Parameter(Mandatory)][ValidatePattern('^(\d{1,3}\.){3}\d{1,3}/32$')][string]$AdminCidr,
    [Parameter(Mandatory)][string]$SshPublicKeyPath,
    [ValidateRange(1,425)][int]$MonthlyHours = 180,
    [ValidateRange(1,24)][int]$SessionHours = 8,
    [ValidateRange(5,60)][int]$IdleMinutes = 15,
    [string]$ServerCatalogPath,
    [switch]$Apply,
    [switch]$GeneratePortalPassword,
    [switch]$AcceptMinecraftEula,
    [switch]$AllowOtherSubscription
)
. "$PSScriptRoot/Common.ps1"
$null = Initialize-AzureContext -SubscriptionId $SubscriptionId -AllowOtherSubscription:$AllowOtherSubscription
if ($Apply) {
    & "$PSScriptRoot/Preflight.ps1" -SubscriptionId $SubscriptionId -Location $Location -VmSize $VmSize -AllowOtherSubscription:$AllowOtherSubscription
}
$root = Split-Path $PSScriptRoot -Parent
$resourceGroup = "rg-$Name"
$vmName = "$Name-vm"
$deploymentAttempted = $false
$groupExists = Invoke-Azure -Arguments @('group','exists','--name',$resourceGroup,'--output','tsv')
if ("$groupExists".Trim() -eq 'true') {
    $existingGroup = Invoke-Azure -Arguments @('group','show','--name',$resourceGroup,'--output','json') | ConvertFrom-Json
    if ($existingGroup.tags.application -ne 'fogata' -or $existingGroup.tags.managedBy -ne 'minecraft-azure') {
        throw 'El RG ya existe y no pertenece a este proyecto. Elige otro Name; no se modifica infraestructura ajena.'
    }
    if ($Apply) {
        $existingVms = @(Invoke-Azure -Arguments @('vm','list','--resource-group',$resourceGroup,'--query',"[?name=='$vmName'].name",'--output','json') | ConvertFrom-Json)
        if ($existingVms.Count -gt 0) {
            $power = Invoke-Azure -Arguments @('vm','get-instance-view','--resource-group',$resourceGroup,'--name',$vmName,'--query',"instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]",'--output','tsv')
            if ("$power".Trim() -ne 'PowerState/deallocated') {
                throw 'Para reaplicar, la VM debe estar desasignada. Cierra Minecraft guardando el mundo y deja que el controlador desasigne la VM antes de desplegar. No se interrumpe una sesión activa.'
            }
        }
    }
}
$publicKey = (Get-Content -LiteralPath (Resolve-Path $SshPublicKeyPath) -Raw).Trim()
if ($publicKey -notmatch '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp\d+) [A-Za-z0-9+/=]+') { throw 'Proporciona una clave SSH pública, nunca la clave privada.' }
if ($VmSize -eq 'Standard_D2as_v7') {
    if ($Location -eq 'brazilsouth' -and $MonthlyHours -gt 220) { throw 'Para D2as_v7 en Brazil South el límite inicial permitido es 220 h/mes para conservar margen de costos.' }
    if ($Location -eq 'centralus' -and $MonthlyHours -gt 390) { throw 'Para D2as_v7 en Central US el límite inicial permitido es 390 h/mes para conservar margen de costos.' }
    if ($Location -eq 'eastus') { Write-Warning 'La tarifa vigente de D2as_v7 en East US no está cotizada en esta revisión. Recotiza antes de aplicar; no asumas que el límite de horas equivale a 50 USD.' }
} else {
    Write-Warning 'VmSize distinto de D2as_v7: las tablas de precios y límites de horas calculados no aplican. Recotiza memoria, cómputo y presupuesto antes de aplicar.'
}

$temporaryDirectory = Join-Path ([IO.Path]::GetTempPath()) ('fogata-' + [guid]::NewGuid().ToString('N'))
$local = Join-Path $root '.local'
$null = New-Item -ItemType Directory -Path $local -Force
$heartbeatSecret = New-SecretToken
$passwordHash = ('0' * 64) # Non-secret placeholder is enough to compute a what-if.
if ($Apply) {
    if ($GeneratePortalPassword) {
        $privateDirectory = Join-Path $local 'private'
        $null = New-Item -ItemType Directory -Path $privateDirectory -Force
        if ([Environment]::OSVersion.Platform -eq 'Win32NT') {
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            & icacls $privateDirectory /inheritance:r /grant:r "*${sid}:(OI)(CI)F" | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo proteger el directorio de contraseñas.' }
        } else {
            & chmod 700 $privateDirectory
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo proteger el directorio de contraseñas.' }
        }
        $plain = New-SecretToken
        $passwordPath = Join-Path $privateDirectory 'portal-password.txt'
        Write-Utf8File $passwordPath $plain
        if ([Environment]::OSVersion.Platform -ne 'Win32NT') { & chmod 600 $passwordPath }
        Write-Host 'Contraseña aleatoria guardada en .local/private/portal-password.txt; no se imprime ni se sube a Git.'
    } else {
        $securePassword = Read-Host 'Contraseña compartida del portal (mínimo 16 caracteres)' -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
        try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    }
    if ($plain.Length -lt 16) { throw 'Usa una contraseña de al menos 16 caracteres.' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $passwordHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($plain)))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose(); $plain = $null; $securePassword = $null }
}
$null = New-Item -ItemType Directory -Path $temporaryDirectory
$catalogFile = if ($ServerCatalogPath) { $ServerCatalogPath } else { Join-Path $local 'server-catalog.json' }
$catalogJson = if (Test-Path -LiteralPath $catalogFile) { (Get-Content -Raw -LiteralPath $catalogFile | ConvertFrom-Json | ConvertTo-Json -Compress -Depth 6) } else { '[]' }
$parameters = @{
    '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
    contentVersion = '1.0.0.0'
    parameters = @{
        serverCatalogJson = @{value=$catalogJson}
        name = @{value=$Name}; location = @{value=$Location}; adminCidr = @{value=$AdminCidr}
        sshPublicKey = @{value=$publicKey}; portalPasswordHash = @{value=$passwordHash}
        heartbeatSecret = @{value=$heartbeatSecret}; monthlyHours = @{value=$MonthlyHours}
        sessionHours = @{value=$SessionHours}; idleMinutes = @{value=$IdleMinutes}; vmSize = @{value=$VmSize}
    }
}
$parameterFile = Join-Path $temporaryDirectory 'parameters.json'
Write-Utf8File $parameterFile ($parameters | ConvertTo-Json -Depth 10)
$deploymentName = "$Name-infrastructure"
$baseArguments = @('deployment','sub','what-if','--name',$deploymentName,'--location',$Location,'--template-file',(Join-Path $root 'infra/main.bicep'),'--parameters',"@$parameterFile")
try {
    Write-Host 'Revisión de recursos (what-if). Revisa región, RG dedicado y tamaño antes de aplicar.'
    Invoke-Azure -Arguments $baseArguments | Write-Host
    if (-not $Apply) { Write-Host 'Plan terminado. No se crearon recursos. Repite con -Apply para desplegar.'; return }
    $baseArguments[2] = 'create'
    $deploymentAttempted = $true
    $outputs = Invoke-Azure -Arguments ($baseArguments + @('--query','properties.outputs','--output','json')) | ConvertFrom-Json
    $resourceGroup = $outputs.resourceGroup.value
    $storage = $outputs.storageName.value
    $functionName = $outputs.functionName.value
    $vmName = $outputs.vmName.value
    $apiBase = $outputs.apiBaseUrl.value
    $portalUrl = $outputs.portalUrl.value
    $deployment = [ordered]@{
        subscriptionId=$SubscriptionId.ToString(); resourceGroup=$resourceGroup; location=$Location; vmSize=$VmSize
        vmName=$vmName; storageName=$storage; functionName=$functionName
        publicIp=$outputs.publicIp.value; portalUrl=$portalUrl; apiBaseUrl=$apiBase
        panelUrl=$outputs.panelUrl.value; panelHostname=$outputs.panelHostname.value; adminUsername='azureuser'; monthlyHours=$MonthlyHours
    }
    Write-Utf8File (Join-Path $local 'deployment.json') ($deployment | ConvertTo-Json)

    $apiZip = Join-Path $temporaryDirectory 'api.zip'
    $apiStage = Join-Path $temporaryDirectory 'api'
    $null = New-Item -ItemType Directory -Path $apiStage
    $apiSource = Join-Path $root 'api'
    Get-ChildItem -LiteralPath $apiSource -File -Recurse | ForEach-Object {
        $relative = $_.FullName.Substring($apiSource.Length + 1)
        if ($relative -notmatch '(^|[\\/])(\.venv|venv|__pycache__|\.git)([\\/]|$)' -and $_.Name -ne 'local.settings.json' -and ($_.Extension -eq '.py' -or $_.Name -in @('host.json', 'requirements.txt'))) {
            $target = Join-Path $apiStage $relative
            $null = New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force
            Copy-Item -LiteralPath $_.FullName -Destination $target
        }
    }
    Compress-Archive -Path (Join-Path $apiStage '*') -DestinationPath $apiZip -Force
    Invoke-Azure -Arguments @('functionapp','deployment','source','config-zip','--resource-group',$resourceGroup,'--name',$functionName,'--src',$apiZip,'--build-remote','true','--output','none') | Out-Null

    # Storage keys remain in this process environment, never in native command arguments.
    $previousStorageKey = $env:AZURE_STORAGE_KEY
    try {
        $env:AZURE_STORAGE_KEY = Invoke-Azure -Arguments @('storage','account','keys','list','--resource-group',$resourceGroup,'--account-name',$storage,'--query','[0].value','--output','tsv')
        Invoke-Azure -Arguments @('storage','blob','service-properties','update','--account-name',$storage,'--static-website','--index-document','index.html','--404-document','index.html','--output','none') | Out-Null
        $site = Join-Path $temporaryDirectory 'site'
        $null = New-Item -ItemType Directory -Path $site
        Copy-Item -Path (Join-Path $root 'web/*') -Destination $site -Recurse
        $config = @{apiBaseUrl=$apiBase;demo=$false} | ConvertTo-Json -Compress
        Write-Utf8File (Join-Path $site 'config.js') "window.PORTAL_CONFIG = $config;"
        Invoke-Azure -Arguments @('storage','blob','upload-batch','--account-name',$storage,'--destination','$web','--source',$site,'--overwrite','true','--output','none') | Out-Null
    } finally { $env:AZURE_STORAGE_KEY = $previousStorageKey }

    # Azure encrypts protectedSettings. Secrets are not placed in customData, stdout or Git.
    $environmentText = "API_BASE_URL=$apiBase`nHEARTBEAT_SECRET=$heartbeatSecret`nCONTAINER_NAME=`nSERVER_DIR=`nMC_HOST=127.0.0.1`nMC_PORT=25565`nPANEL_HOSTNAME=$($outputs.panelHostname.value)`nPANEL_HEALTH_URL=$($outputs.panelUrl.value)/`nADMIN_CIDR=$AdminCidr`n"
    $bootstrap = (Get-Content -LiteralPath (Join-Path $root 'vm/bootstrap.sh') -Raw).Replace("`r`n","`n")
    $agent = (Get-Content -LiteralPath (Join-Path $root 'vm/agent.py') -Raw).Replace("`r`n","`n")
    $wings = (Get-Content -LiteralPath (Join-Path $root 'vm/wings.py') -Raw).Replace("`r`n","`n")
    $accept = if ($AcceptMinecraftEula) { 'true' } else { 'false' }
    $mergeEnvironment = @'
import base64, pathlib
p = pathlib.Path('/etc/fogata/agent.env')
def parse(text):
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line and not line.startswith('#'))
existing = parse(p.read_text()) if p.exists() else {}
values = parse(base64.b64decode('__ENV__').decode())
for key in ('CONTAINER_NAME', 'SERVER_DIR', 'MC_HOST', 'MC_PORT', 'PANEL_HEALTH_URL'):
    if existing.get(key):
        values[key] = existing[key]
p.write_text(''.join(key + '=' + value + '\n' for key, value in values.items()))
p.chmod(0o600)
'@
    $mergeEnvironment = $mergeEnvironment.Replace('__ENV__', (ConvertTo-Base64Utf8 $environmentText))
    $shell = "#!/bin/bash`nset -eu`ninstall -d -m 700 /etc/fogata`ninstall -d -m 755 /opt/fogata`nprintf '%s' '$(ConvertTo-Base64Utf8 $mergeEnvironment)' | base64 -d | python3`nprintf '%s' '$(ConvertTo-Base64Utf8 $bootstrap)' | base64 -d > /opt/fogata/bootstrap.sh`nprintf '%s' '$(ConvertTo-Base64Utf8 $agent)' | base64 -d > /opt/fogata/agent.py`nprintf '%s' '$(ConvertTo-Base64Utf8 $wings)' | base64 -d > /opt/fogata/wings.py`nchmod 755 /opt/fogata/bootstrap.sh`nACCEPT_MINECRAFT_EULA=$accept bash /opt/fogata/bootstrap.sh`n"
    $protectedFile = Join-Path $temporaryDirectory 'extension-protected.json'
    Write-Utf8File $protectedFile (@{script=(ConvertTo-Base64Utf8 $shell)} | ConvertTo-Json -Compress)
    Invoke-Azure -Arguments @('vm','start','--resource-group',$resourceGroup,'--name',$vmName,'--output','none') | Out-Null
    Invoke-Azure -Arguments @('vm','extension','set','--resource-group',$resourceGroup,'--vm-name',$vmName,'--publisher','Microsoft.Azure.Extensions','--name','CustomScript','--version','2.1','--protected-settings',"@$protectedFile",'--output','none') | Out-Null
    Invoke-Azure -Arguments @('vm','deallocate','--resource-group',$resourceGroup,'--name',$vmName,'--output','none') | Out-Null
    Write-Host "Portal: $portalUrl"
    Write-Host 'VM desasignada para evitar cómputo mientras no se usa. Configuración manual de Pelican/node/servidor pendiente; consulta README.'
    Write-Host 'Panel HTTPS con hostname gratuito de Azure; verifica certificado y configura la cuenta administradora antes de compartir.'
} catch {
    # If provisioning was partial, avoid leaving a billable VM running without its controller.
    if ($deploymentAttempted) {
        Write-Warning 'Falló una etapa. Se intentará desasignar la VM para frenar cómputo; los discos/IP permanecen.'
        try {
            $ownedGroup = Invoke-Azure -Arguments @('group','show','--name',$resourceGroup,'--output','json') | ConvertFrom-Json
            if ($ownedGroup.tags.application -ne 'fogata' -or $ownedGroup.tags.managedBy -ne 'minecraft-azure') { throw 'No se confirma propiedad del RG.' }
            Invoke-Azure -Arguments @('vm','deallocate','--resource-group',$resourceGroup,'--name',$vmName,'--output','none') | Out-Null
        }
        catch { Write-Warning 'No se pudo confirmar la desasignación. Revisa el estado de la VM en el RG indicado en .local/deployment.json.' }
    }
    throw
} finally {
    $heartbeatSecret = $null
    $parameters = $null
    # The exact random directory was created above under the system temporary directory.
    $resolvedTemporary = [IO.Path]::GetFullPath($temporaryDirectory)
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTemporary.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolvedTemporary -Leaf) -like 'fogata-*') {
        Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
    }
}
