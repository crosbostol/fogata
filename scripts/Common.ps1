Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Find-AzureCli {
    $command = Get-Command az -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in @("$env:ProgramFiles\Microsoft SDKs\Azure\CLI2\wbin\az.cmd", "${env:ProgramFiles(x86)}\Microsoft SDKs\Azure\CLI2\wbin\az.cmd")) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw 'Azure CLI no está instalado. Instala Azure CLI y ejecuta az login primero.'
}

function Invoke-Azure {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $result = & $script:AzureCli @Arguments --subscription $script:TargetSubscription --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "Azure CLI falló: $($Arguments[0..([Math]::Min(1, $Arguments.Length - 1))] -join ' '). Revisa el mensaje anterior." }
    return $result
}

function Initialize-AzureContext {
    param([Parameter(Mandatory)][guid]$SubscriptionId, [switch]$AllowOtherSubscription)
    $script:AzureCli = Find-AzureCli
    $script:TargetSubscription = $SubscriptionId.ToString()
    $account = Invoke-Azure -Arguments @('account','show','--query','{id:id,name:name,state:state}','--output','json') | ConvertFrom-Json
    if ($account.id -ne $script:TargetSubscription -or $account.state -ne 'Enabled') { throw 'La suscripción solicitada no está habilitada o no coincide.' }
    if ($account.name -notmatch 'Visual Studio' -and -not $AllowOtherSubscription) {
        throw 'La suscripción no se identifica como Visual Studio. Verifica el ID. Para otra suscripción usa -AllowOtherSubscription conscientemente.'
    }
    Write-Host "Suscripción fijada: $($account.name) [$($account.id)]"
    Write-Host 'No se cambia la suscripción predeterminada de Azure CLI.'
    return $account
}

function Write-Utf8File {
    param([string]$Path,[string]$Content)
    [IO.File]::WriteAllText($Path, $Content, [Text.UTF8Encoding]::new($false))
}

function New-SecretToken {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes)
}

function ConvertTo-Base64Utf8 { param([string]$Text) return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text)) }
