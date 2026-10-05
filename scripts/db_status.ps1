param([switch]$AllowUnmigrated)
$arguments = @('status')
if ($AllowUnmigrated) { $arguments += '--allow-unmigrated' }
& (Join-Path $PSScriptRoot 'invoke_dev.ps1') -Arguments $arguments
exit $LASTEXITCODE
