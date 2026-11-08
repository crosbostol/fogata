[CmdletBinding()]
param(
    [Parameter(Mandatory)][guid]$SubscriptionId,
    [ValidateSet('centralus','eastus','brazilsouth')][string]$Location = 'centralus',
    [ValidatePattern('^Standard_[A-Za-z0-9_]+$')][string]$VmSize = 'Standard_D2as_v7',
    [switch]$AllowOtherSubscription
)
. "$PSScriptRoot/Common.ps1"
$null = Initialize-AzureContext -SubscriptionId $SubscriptionId -AllowOtherSubscription:$AllowOtherSubscription
Write-Host "Región: $Location. Tamaño: $VmSize. Comprobaciones de lectura; no se crean recursos."
$issues = [Collections.Generic.List[string]]::new()
$skus = @(Invoke-Azure -Arguments @('vm','list-skus','--location',$Location,'--size',$VmSize,'--resource-type','virtualMachines','--all','--output','json') | ConvertFrom-Json)
$matchingSkus = @($skus | Where-Object { $_.name -eq $VmSize })
$family = $null
$requiredCores = 0
if ($matchingSkus.Count -ne 1) {
    $issues.Add("Azure no devolvió una ficha inequívoca de $VmSize en $Location. Disponibilidad desconocida; no continúes con Apply.")
} else {
    $sku = $matchingSkus[0]
    $restrictions = @($sku.restrictions)
    $blockingRestrictions = @($restrictions | Where-Object { $_.type -ne 'Zone' })
    if ($blockingRestrictions.Count -gt 0) {
        $details = $blockingRestrictions | ConvertTo-Json -Depth 8 -Compress
        $issues.Add("$VmSize tiene restricciones para esta suscripción en ${Location}: $details")
    }
    if (@($restrictions | Where-Object { $_.type -eq 'Zone' }).Count -gt 0) {
        Write-Host 'La ficha tiene restricciones de zonas específicas. Esta plantilla no solicita una zona; no se consideran bloqueo regional.'
    }
    $family = $sku.family
    $cores = @($sku.capabilities | Where-Object { $_.name -eq 'vCPUs' })
    if ($cores.Count -ne 1 -or -not [int]::TryParse([string]$cores[0].value, [ref]$requiredCores) -or $requiredCores -lt 1) {
        $issues.Add('No se pudo determinar el número de vCPU del tamaño seleccionado; no se puede validar su cuota.')
    }
    if (-not $family) { $issues.Add('La ficha de Azure no informa la familia de cuota de la VM.') }
}

# Match canonical quota names case-insensitively in PowerShell; do not silently accept
# an empty JMESPath projection or depend on localized display names.
$usage = @(Invoke-Azure -Arguments @('vm','list-usage','--location',$Location,'--output','json') | ConvertFrom-Json)
$regional = @($usage | Where-Object { $_.name.value -eq 'cores' })
$familyUsage = @($usage | Where-Object { $family -and $_.name.value -eq $family })
foreach ($quota in @(@{ Label='regional'; Rows=$regional }, @{ Label="familia $family"; Rows=$familyUsage })) {
    $rows = @($quota.Rows)
    if ($rows.Count -ne 1) {
        $issues.Add("Cuota $($quota.Label) ausente o ambigua en $Location. No se considera validada; revisa Quotas de Azure.")
        continue
    }
    $row = $rows[0]
    $limit = 0L
    $used = 0L
    if (-not [long]::TryParse([string]$row.limit, [ref]$limit) -or -not [long]::TryParse([string]$row.currentValue, [ref]$used)) {
        $issues.Add("Cuota $($quota.Label) con valores desconocidos.")
        continue
    }
    $available = $limit - $used
    Write-Host "Cuota $($quota.Label): $used/$limit vCPU utilizadas; $available disponibles; $requiredCores necesarias."
    if ($requiredCores -gt $available) {
        $issues.Add("Cuota $($quota.Label) insuficiente: $available vCPU disponibles, $requiredCores necesarias. Solicita cuota o elige otro tamaño/región.")
    }
}
foreach ($provider in @('Microsoft.Compute','Microsoft.Network','Microsoft.Storage','Microsoft.Web')) {
    $registration = Invoke-Azure -Arguments @('provider','show','--namespace',$provider,'--query','{namespace:namespace,state:registrationState}','--output','json') | ConvertFrom-Json
    Write-Host "$provider : $($registration.state)"
    if ($registration.state -ne 'Registered') {
        $issues.Add("Proveedor $provider sin registrar. Revisa permisos y ejecuta explícitamente: az provider register --namespace $provider --subscription $SubscriptionId")
    }
}
if ($issues.Count -gt 0) {
    foreach ($issue in $issues) { Write-Warning $issue }
    throw 'Preflight no aprobado: hay restricciones, cuotas desconocidas/insuficientes o proveedores pendientes. No se crearon recursos.'
}
Write-Host 'Disponibilidad de catálogo y cuotas de VM comprobadas. Esto no reserva capacidad ni garantiza que Azure acepte una asignación futura.'
Write-Host 'Pendiente de validar en what-if/deploy: Functions Linux Flex Consumption, permisos de crear recursos y crear/asignar rol personalizado en el RG dedicado.'
Write-Host 'Confirma también elegibilidad del beneficio Visual Studio para este uso y saldo en Cost Management. Esta prueba no certifica derechos de licencia ni presupuesto.'
