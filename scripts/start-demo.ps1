param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 3000,
    [ValidateSet("production", "dev")]
    [string]$FrontendMode = "production",
    [switch]$UseRealLlm,
    [switch]$InstallDeps
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

function Assert-CommandExists {
    param([string]$Command)

    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "Required command '$Command' was not found. Install it before running this script."
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

Assert-CommandExists "python"
Assert-CommandExists "npm"
Assert-CommandExists "npx"

function Test-CommandUsable {
    param([string]$Command)

    try {
        & $Command "--version" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Test-VenvPipUsable {
    try {
        & ".venv\Scripts\python" "-m" "pip" "--version" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Ensure-VenvPip {
    if (Test-VenvPipUsable) {
        return $true
    }
    try {
        & ".venv\Scripts\python" "-m" "ensurepip" "--upgrade" *> $null
        return (Test-VenvPipUsable)
    }
    catch {
        return $false
    }
}

$BackendVenvCreated = $false
if (-not (Test-Path (Join-Path $BackendDir ".venv"))) {
    Push-Location $BackendDir
    if (Test-CommandUsable "uv") {
        Invoke-Checked "uv" @("venv")
    }
    else {
        Invoke-Checked "python" @("-m", "venv", ".venv")
    }
    $BackendVenvCreated = $true
    Pop-Location
}
Push-Location $BackendDir
if (-not $BackendVenvCreated -and -not $InstallDeps) {
    Write-Host "Using existing backend .venv; dependency install skipped."
}
elseif (Test-CommandUsable "uv") {
    Invoke-Checked "uv" @("pip", "install", "-e", ".[dev]")
}
elseif (Ensure-VenvPip) {
    Invoke-Checked ".venv\Scripts\python" @("-m", "pip", "install", "-e", ".[dev]")
}
else {
    Write-Warning "pip is unavailable in .venv; skipping dependency install and using existing environment."
}
Pop-Location

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
    $MockFlag = if ($UseRealLlm) { "false" } else { "true" }
    Start-Process -FilePath powershell -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "`$env:USE_MOCK_LLM='$MockFlag'; cd '$BackendDir'; .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
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
if ($UseRealLlm) {
    Write-Host "Real LLM mode requested. Configure backend/.env before testing."
}
else {
    Write-Host "Mock mode is enabled for stable recording."
}
Write-Host "Frontend mode: $FrontendMode"
