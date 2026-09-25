[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')

function Invoke-CheckedAz {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & az @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "az $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$ModuleFiles = Get-ChildItem -Path (Join-Path $RepoRoot 'infra\modules') -Filter '*.bicep' | Sort-Object FullName
$EntryPoints = @(
    Join-Path $RepoRoot 'infra\environments\dev\main.bicep'
    Join-Path $RepoRoot 'infra\environments\prod\main.bicep'
)
$ParameterFiles = @(
    Join-Path $RepoRoot 'infra\environments\dev\main.bicepparam'
    Join-Path $RepoRoot 'infra\environments\prod\main.bicepparam'
)

foreach ($File in $ModuleFiles) {
    Write-Host "Building module $($File.FullName)"
    Invoke-CheckedAz bicep build --file $File.FullName --stdout | Out-Null
}

foreach ($File in $EntryPoints) {
    Write-Host "Building entry point $File"
    Invoke-CheckedAz bicep build --file $File --stdout | Out-Null
}

foreach ($File in $ParameterFiles) {
    Write-Host "Building parameter file $File"
    Invoke-CheckedAz bicep build-params --file $File --stdout | Out-Null
}

Write-Host 'Infrastructure Bicep validation succeeded.'
