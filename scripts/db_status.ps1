& (Join-Path $PSScriptRoot 'invoke_dev.ps1') -Arguments @('status')
exit $LASTEXITCODE
