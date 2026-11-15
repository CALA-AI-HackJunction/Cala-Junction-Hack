#!/usr/bin/env pwsh
# ==============================================================================
# Unicorn Radar -- One-Command Launcher (Windows PowerShell)
# Usage: .\scripts\start.ps1 [-Port 8080] [-HostAddr "127.0.0.1"]
# ==============================================================================
param(
    [int]$Port = 0,
    [string]$HostAddr = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Load .env variables into process environment if .env exists
$EnvFile = Join-Path $RepoRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $idx = $line.IndexOf("=")
            $key = $line.Substring(0, $idx).Trim()
            $val = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
            if (-not [Environment]::GetEnvironmentVariable($key, "Process")) {
                [Environment]::SetEnvironmentVariable($key, $val, "Process")
            }
        }
    }
}

if ($Port -le 0) {
    $envPort = [Environment]::GetEnvironmentVariable("PORT", "Process")
    $Port = if ($envPort) { [int]$envPort } else { 8080 }
}
if (-not $HostAddr) {
    $envHost = [Environment]::GetEnvironmentVariable("HOST", "Process")
    $HostAddr = if ($envHost) { $envHost } else { "127.0.0.1" }
}
$env:PORT = "$Port"
$env:HOST = $HostAddr

$BootCode = @"
import importlib, os, sys
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
host = os.environ.get('HOST', '127.0.0.1')
port = int(os.environ.get('PORT', '8080'))

app = None
target = None
for mod_name in ('backend.main', 'backend.app', 'backend.server'):
    try:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, 'app'):
            app = getattr(mod, 'app')
            target = f'{mod_name}:app'
            break
        if hasattr(mod, 'create_app'):
            app = mod.create_app()
            target = mod_name
            break
    except ImportError:
        continue

if app is not None:
    import uvicorn
    print(f'[Unicorn Radar] Starting server ({target}) at http://{host}:{port}')
    uvicorn.run(app, host=host, port=port, log_level='info')
else:
    for mod_name in ('backend.server', 'server'):
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, 'run_server'):
                mod.run_server(host=host, port=port)
                sys.exit(0)
        except ImportError:
            continue
    raise SystemExit('Backend entrypoint not found. Expected backend.main:app, backend.app:app, or backend.server:app.')
"@

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Unicorn Radar -- Cala x Slush Connection Intelligence (2026)  " -ForegroundColor Cyan
Write-Host "  URL: http://${HostAddr}:${Port}                               " -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan

if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv run --python 3.12 python -c $BootCode
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c $BootCode
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -c $BootCode
} else {
    Write-Error "Neither 'uv' nor 'python' was found in PATH."
    exit 1
}
