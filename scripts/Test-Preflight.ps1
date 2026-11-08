# Offline contract checks. The mock rejects any unexpected Azure command.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$directory = Join-Path $root ('.local/preflight-test-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $directory -Force
$previousPath = $env:PATH
$previousScenario = $env:FOGATA_TEST_SCENARIO
$previousVm = $env:FOGATA_TEST_VM
$fakeSource = @'
$global:LASTEXITCODE = 0
$a = @($args)
Add-Content -LiteralPath (Join-Path $PSScriptRoot 'events.jsonl') -Value (ConvertTo-Json -InputObject $a -Compress)
$scenario = $env:FOGATA_TEST_SCENARIO
switch (($a[0..1] -join ' ')) {
    'account show' { '{"id":"11111111-1111-1111-1111-111111111111","name":"Visual Studio Local Mock","state":"Enabled"}' }
    'vm list-skus' {
        if ($scenario -eq 'missing-sku') { '[]'; break }
        $restrictions = @()
        if ($scenario -eq 'restricted') { $restrictions = @(@{type='Location';reasonCode='NotAvailableForSubscription';values=@('centralus')}) }
        if ($scenario -eq 'zone-only') { $restrictions = @(@{type='Zone';reasonCode='NotAvailableForSubscription';restrictionInfo=@{locations=@('centralus');zones=@('1')}}) }
        $cores = if ($scenario -eq 'custom-vm') { '4' } else { '2' }
        ConvertTo-Json -InputObject @(@{name=$env:FOGATA_TEST_VM;family='standardDasv7Family';restrictions=$restrictions;capabilities=@(@{name='vCPUs';value=$cores})}) -Depth 8 -Compress
    }
    'vm list-usage' {
        if ($scenario -eq 'unknown-quota') { '[]'; break }
        $used = if ($scenario -eq 'insufficient') { 19 } else { 0 }
        ConvertTo-Json -InputObject @(@{name=@{value='CORES'};currentValue=0;limit=16},@{name=@{value='StandardDasv7Family'};currentValue=$used;limit=20}) -Depth 5 -Compress
    }
    'provider show' {
        $state = if ($scenario -eq 'unregistered') { 'NotRegistered' } else { 'Registered' }
        ConvertTo-Json @{namespace=$a[([array]::IndexOf($a, '--namespace') + 1)];state=$state} -Compress
    }
    default { throw ('Unexpected Azure command in read-only Preflight: ' + ($a -join ' ')) }
}
'@
try {
    [IO.File]::WriteAllText((Join-Path $directory 'az.ps1'), $fakeSource, [Text.UTF8Encoding]::new($false))
    $env:PATH = $directory + [IO.Path]::PathSeparator + $previousPath
    $passed = 0
    foreach ($scenario in @('available','restricted','zone-only','unknown-quota','insufficient','unregistered','missing-sku','custom-vm')) {
        $env:FOGATA_TEST_SCENARIO = $scenario
        $env:FOGATA_TEST_VM = if ($scenario -eq 'custom-vm') { 'Standard_D4as_v7' } else { 'Standard_D2as_v7' }
        $caught = $false
        try {
            & "$PSScriptRoot/Preflight.ps1" -SubscriptionId 11111111-1111-1111-1111-111111111111 -VmSize $env:FOGATA_TEST_VM 6>$null 3>$null
        } catch { $caught = $true }
        $shouldFail = $scenario -notin @('available','custom-vm','zone-only')
        if ($caught -ne $shouldFail) { throw "Preflight scenario $scenario returned an unexpected result (failed=$caught)." }
        $passed++
    }
    foreach ($line in Get-Content -LiteralPath (Join-Path $directory 'events.jsonl')) {
        $event = @(ConvertFrom-Json $line)
        if ($event -notcontains '--subscription' -or $event -notcontains '11111111-1111-1111-1111-111111111111') { throw 'Command missing explicit subscription.' }
        if ($event[0] -eq 'vm') {
            $locationIndex = [array]::IndexOf($event, '--location')
            if ($locationIndex -lt 0 -or $event[$locationIndex + 1] -ne 'centralus') { throw 'Preflight did not default to Central US.' }
        }
    }
    Write-Host "$passed pruebas de Preflight aprobadas: solo mocks, sin acceso a Azure."
} finally {
    $env:PATH = $previousPath
    $env:FOGATA_TEST_SCENARIO = $previousScenario
    $env:FOGATA_TEST_VM = $previousVm
    $target = [IO.Path]::GetFullPath($directory)
    $allowedRoot = [IO.Path]::GetFullPath((Join-Path $root '.local')) + [IO.Path]::DirectorySeparatorChar
    if ($target.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $target -Leaf) -like 'preflight-test-*') { Remove-Item -LiteralPath $target -Recurse -Force }
}
