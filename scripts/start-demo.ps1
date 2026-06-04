param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"

function Test-Port([int]$Port) {
    try {
        return (Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
    }
    catch {
        return $false
    }
}

if (-not (Test-Path (Join-Path $BackendDir ".venv"))) {
    Push-Location $BackendDir
    uv venv
    uv pip install -e ".[dev]"
    Pop-Location
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Push-Location $FrontendDir
    npm install
    Pop-Location
}

if (-not (Test-Port $BackendPort)) {
    Start-Process -FilePath powershell -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "`$env:USE_MOCK_LLM='true'; cd '$BackendDir'; .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
    ) -WindowStyle Hidden
}

if (-not (Test-Port $FrontendPort)) {
    Start-Process -FilePath powershell -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "cd '$FrontendDir'; npx next dev --webpack --hostname 127.0.0.1 --port $FrontendPort"
    ) -WindowStyle Hidden
}

Write-Host "Demo backend:  http://127.0.0.1:$BackendPort"
Write-Host "Demo frontend: http://127.0.0.1:$FrontendPort"
Write-Host "Mock mode is enabled for stable recording."
