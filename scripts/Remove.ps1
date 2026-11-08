[CmdletBinding()]
param(
    [Parameter(Mandatory)][guid]$SubscriptionId,
    [Parameter(Mandatory)][ValidatePattern('^[a-z][a-z0-9-]{2,15}$')][string]$Name,
    [Parameter(Mandatory)][string]$ConfirmName,
    [switch]$AllowOtherSubscription
)
. "$PSScriptRoot/Common.ps1"
$null = Initialize-AzureContext -SubscriptionId $SubscriptionId -AllowOtherSubscription:$AllowOtherSubscription
if ($ConfirmName -cne $Name) { throw 'ConfirmName debe coincidir exactamente con Name. La eliminación incluye el mundo y todos los backups dentro del RG.' }
$groupName = "rg-$Name"
$group = Invoke-Azure -Arguments @('group','show','--name',$groupName,'--output','json') | ConvertFrom-Json
if ($group.tags.application -ne 'fogata' -or $group.tags.managedBy -ne 'minecraft-azure') { throw 'El RG no tiene las etiquetas esperadas; no se elimina.' }
Invoke-Azure -Arguments @('group','delete','--name',$groupName,'--yes','--output','none') | Out-Null
Write-Host "Eliminado $groupName en la suscripción especificada."
