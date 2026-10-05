param([ValidateSet('unit', 'integration', 'api', 'e2e', 'all')][string]$Category = 'all')
& (Join-Path $PSScriptRoot 'invoke_dev.ps1') -Arguments @('test', $Category)
exit $LASTEXITCODE
