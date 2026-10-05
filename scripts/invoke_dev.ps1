param([Parameter(Mandatory = $true)][string[]]$Arguments)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing repository virtual environment. Run python -m venv .venv and install -e '.[dev]'."
}
& $python (Join-Path $PSScriptRoot 'dev.py') @Arguments
exit $LASTEXITCODE
