param([switch]$Seed, [switch]$TestDatabase)
$arguments = @('reset')
if ($TestDatabase) { $arguments += '--test-database' }
if ($Seed) { $arguments += '--seed' }
& (Join-Path $PSScriptRoot 'invoke_dev.ps1') -Arguments $arguments
exit $LASTEXITCODE
