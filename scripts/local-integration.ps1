param(
    [ValidateSet('status', 'docker', 'start', 'stop', 'restart', 'seed')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$backendRoot = Split-Path $PSScriptRoot -Parent
$frontendRoot = Join-Path (Split-Path $backendRoot -Parent) 'Shelfcash_FE_v2'
$privateRoot = Join-Path $backendRoot 'runtime/s411/private'
$pythonExe = Join-Path $backendRoot '.venv/Scripts/python.exe'
$feStatePath = Join-Path $privateRoot 'fe-server.json'

function Invoke-Integration([string]$Command) {
    Push-Location $backendRoot
    try {
        & $pythonExe -m scripts.integration $Command
        if ($LASTEXITCODE -ne 0) { throw "Integration $Command failed; inspect private logs/config." }
    } finally { Pop-Location }
}

function Get-Listeners([int]$Port) {
    @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Assert-BackendOwner {
    $owned = Get-Content -Raw (Join-Path $privateRoot 'server.json') | ConvertFrom-Json
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($owned.pid)"
    if (!$process -or $process.CommandLine -notlike "*scripts.integration_server*$($owned.run_id)*") {
        throw 'Backend ownership mismatch; no process replaced or stopped.'
    }
    foreach ($listener in (Get-Listeners 18001)) {
        $serving = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if ($listener.LocalAddress -notin @('127.0.0.1', '::1') -or
            ($serving.ProcessId -ne $owned.pid -and $serving.ParentProcessId -ne $owned.pid)) {
            throw 'Port18001 has a foreign/non-loopback process.'
        }
    }
}

function Get-OwnedFrontend {
    if (!(Test-Path -LiteralPath $feStatePath)) { return $null }
    $owned = Get-Content -Raw $feStatePath | ConvertFrom-Json
    $process = Get-Process -Id $owned.pid -ErrorAction SilentlyContinue
    if (!$process) { return $null }
    $info = Get-CimInstance Win32_Process -Filter "ProcessId=$($owned.pid)"
    $entry = Join-Path $frontendRoot 'node_modules/vite/bin/vite.js'
    if (!$owned.startedAt -or $process.StartTime.ToUniversalTime().ToString('o') -ne $owned.startedAt -or
        $info.CommandLine -notlike "*$entry*--host localhost --port 5173 --strictPort*") {
        throw 'Frontend incarnation/command mismatch; no process stopped.'
    }
    return $process
}

function Start-Local {
    Invoke-Integration 'status'
    if (@(Get-Listeners 18001).Count) {
        Assert-BackendOwner
        if ((Invoke-WebRequest -UseBasicParsing 'http://localhost:18001/health').StatusCode -ne 200) {
            throw 'Owned backend health is not ready.'
        }
        Write-Host 'Reusing owned backend http://localhost:18001'
    } else {
        $serverPath = Join-Path $privateRoot 'server.json'
        if (Test-Path -LiteralPath $serverPath) {
            $owned = Get-Content -Raw $serverPath | ConvertFrom-Json
            $exitPath = Join-Path $privateRoot 'server-exit.json'
            $matched = $false
            if (Test-Path -LiteralPath $exitPath) {
                $matched = (Get-Content -Raw $exitPath | ConvertFrom-Json).run_id -eq $owned.run_id
            }
            if (!$matched) { Invoke-Integration 'recover-stopped' }
        }
        Invoke-Integration 'start'
    }
    $frontend = Get-OwnedFrontend
    $listeners = @(Get-Listeners 5173)
    if ($listeners.Count) {
        if (!$frontend -or @($listeners | Where-Object {
            $_.OwningProcess -ne $frontend.Id -or $_.LocalAddress -notin @('127.0.0.1', '::1')
        }).Count) { throw 'Port5173 occupied by a foreign/non-loopback process; no port fallback.' }
        Write-Host 'Reusing owned frontend http://localhost:5173'
        return
    }
    if ($frontend) { throw 'Owned Vite exists without a listener; inspect private log.' }
    $entry = Join-Path $frontendRoot 'node_modules/vite/bin/vite.js'
    if (!(Test-Path -LiteralPath $entry)) { throw 'Run npm ci in the frontend repository first.' }
    $oldSource = $env:VITE_DATA_SOURCE
    $oldApi = $env:VITE_API_BASE_URL
    try {
        $env:VITE_DATA_SOURCE = 'api'
        $env:VITE_API_BASE_URL = 'http://localhost:18001'
        $frontend = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @(
            ('"' + $entry + '"'), '--host', 'localhost', '--port', '5173', '--strictPort'
        ) -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru `
          -RedirectStandardOutput (Join-Path $privateRoot 'fe-server.log') `
          -RedirectStandardError (Join-Path $privateRoot 'fe-server-error.log')
        $frontend.Refresh()
        @{ pid = $frontend.Id; startedAt = $frontend.StartTime.ToUniversalTime().ToString('o');
            url = 'http://localhost:5173'; api = 'http://localhost:18001' } |
            ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath $feStatePath
    } finally {
        $env:VITE_DATA_SOURCE = $oldSource
        $env:VITE_API_BASE_URL = $oldApi
    }
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        if ($frontend.HasExited) { throw 'Owned Vite exited; inspect private fe-server-error.log.' }
        try {
            if ((Invoke-WebRequest -UseBasicParsing 'http://localhost:5173' -TimeoutSec 1).StatusCode -eq 200) {
                Write-Host 'Frontend ready http://localhost:5173 (api mode)'
                return
            }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    throw 'Vite readiness unverified; no second frontend launched.'
}

function Stop-Local {
    $frontend = Get-OwnedFrontend
    if ($frontend) {
        Stop-Process -InputObject $frontend
        $frontend.WaitForExit(10000) | Out-Null
        Write-Host 'Owned Vite stopped.'
    } elseif (@(Get-Listeners 5173).Count) { throw 'Foreign frontend listener; stop refused.' }
    if (@(Get-Listeners 18001).Count) {
        Assert-BackendOwner
        Invoke-Integration 'stop'
    }
}

switch ($Action) {
    'status' {
        Invoke-Integration 'status'
        foreach ($port in @(5173, 18001, 5433)) {
            Get-Listeners $port | Select-Object LocalAddress, LocalPort, OwningProcess
        }
    }
    'docker' {
        Push-Location $backendRoot
        try {
            & docker compose --env-file runtime/s411/private/compose.env -f compose.integration.yaml up -d --wait
            if ($LASTEXITCODE -ne 0) { throw 'Integration Docker startup failed.' }
        } finally { Pop-Location }
    }
    'start' { Start-Local }
    'stop' { Stop-Local }
    'restart' { Stop-Local; Start-Local }
    'seed' { Invoke-Integration 'seed' }
}
