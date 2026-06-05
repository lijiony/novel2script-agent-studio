param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000,
    [ValidateSet("production", "dev")]
    [string]$FrontendMode = "production"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"

function Invoke-Checked {
    param(
        [string]$Command,
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

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
    Invoke-Checked "uv" @("venv")
    Invoke-Checked "uv" @("pip", "install", "-e", ".[dev]")
    Pop-Location
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Push-Location $FrontendDir
    Invoke-Checked "npm" @("install")
    Pop-Location
}

function Build-StandaloneFrontend {
    Push-Location $FrontendDir
    Invoke-Checked "npm" @("run", "build")

    $StaticSource = Join-Path $FrontendDir ".next\static"
    $StandaloneStatic = Join-Path $FrontendDir ".next\standalone\.next\static"
    if (Test-Path $StaticSource) {
        New-Item -ItemType Directory -Force -Path $StandaloneStatic | Out-Null
        Copy-Item -Path (Join-Path $StaticSource "*") -Destination $StandaloneStatic -Recurse -Force
    }

    $PublicSource = Join-Path $FrontendDir "public"
    $StandalonePublic = Join-Path $FrontendDir ".next\standalone\public"
    if (Test-Path $PublicSource) {
        New-Item -ItemType Directory -Force -Path $StandalonePublic | Out-Null
        Copy-Item -Path (Join-Path $PublicSource "*") -Destination $StandalonePublic -Recurse -Force
    }
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
    if ($FrontendMode -eq "production") {
        Build-StandaloneFrontend
        $ServerPath = Join-Path $FrontendDir ".next\standalone\server.js"
        Start-Process -FilePath powershell -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "`$env:PORT='$FrontendPort'; `$env:HOSTNAME='127.0.0.1'; cd '$FrontendDir'; node '$ServerPath'"
        ) -WindowStyle Hidden
    }
    else {
        Start-Process -FilePath powershell -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "cd '$FrontendDir'; npx next dev --webpack --hostname 127.0.0.1 --port $FrontendPort"
        ) -WindowStyle Hidden
    }
}

Write-Host "Demo backend:  http://127.0.0.1:$BackendPort"
Write-Host "Demo frontend: http://127.0.0.1:$FrontendPort"
Write-Host "Mock mode is enabled for stable recording."
Write-Host "Frontend mode: $FrontendMode"
