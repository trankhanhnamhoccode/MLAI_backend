param([switch]$Seed)
$arguments = @('reset')
if ($Seed) { $arguments += '--seed' }
& (Join-Path $PSScriptRoot 'invoke_dev.ps1') -Arguments $arguments
exit $LASTEXITCODE
