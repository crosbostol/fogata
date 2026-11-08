[CmdletBinding()]
param([switch]$WithBicep)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = if (Test-Path -LiteralPath (Join-Path $root '.venv/Scripts/python.exe')) { Join-Path $root '.venv/Scripts/python.exe' } else { 'python' }
Push-Location $root
try {
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Fallaron pruebas Python.' }
    & node --test web/tests/flows.test.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Fallaron pruebas del portal.' }
    $scriptErrors = @()
    Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1' | ForEach-Object {
        $tokens = $null
        $errors = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
        $scriptErrors += $errors
    }
    if ($scriptErrors.Count -gt 0) { $scriptErrors | Format-List Message,Extent; throw 'Errores de sintaxis PowerShell.' }
    & "$PSScriptRoot/Test-Preflight.ps1"
    if ($WithBicep) {
        $command = Get-Command bicep -ErrorAction SilentlyContinue
        $compiler = if ($command) { $command.Source } else { Join-Path $env:USERPROFILE '.azure/bin/bicep.exe' }
        if (-not (Test-Path -LiteralPath $compiler)) { throw 'Instala Bicep con az bicep install; este script no descarga herramientas.' }
        $previousExtract = $env:DOTNET_BUNDLE_EXTRACT_BASE_DIR
        try {
            $env:DOTNET_BUNDLE_EXTRACT_BASE_DIR = Join-Path $root '.local/dotnet'
            & $compiler build infra/main.bicep --stdout | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Falló compilación Bicep.' }
        } finally { $env:DOTNET_BUNDLE_EXTRACT_BASE_DIR = $previousExtract }
    }
    Write-Host 'Verificación local completada. No se desplegaron recursos ni se verificó Azure end-to-end.'
} finally { Pop-Location }
