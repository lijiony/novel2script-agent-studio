param(
    [switch]$InstallDeps,
    [switch]$InstallBrowsers
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

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

Assert-CommandExists "python"
Assert-CommandExists "npm"
Assert-CommandExists "npx"

& (Join-Path $PSScriptRoot "stop-demo.ps1")

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

Push-Location (Join-Path $RepoRoot "backend")
try {
    Remove-Item -Recurse -Force "runs" -ErrorAction SilentlyContinue
    $UseUv = Test-CommandUsable "uv"
    $CreatedVenv = $false
    if (-not (Test-Path ".venv") -and $UseUv) {
        Invoke-Checked "uv" @("venv")
        $CreatedVenv = $true
    }
    elseif (-not (Test-Path ".venv")) {
        Invoke-Checked "python" @("-m", "venv", ".venv")
        $CreatedVenv = $true
    }
    if (-not $CreatedVenv -and -not $InstallDeps) {
        Write-Host "Using existing backend .venv; dependency install skipped."
    }
    elseif ($UseUv) {
        Invoke-Checked "uv" @("pip", "install", "-e", ".[dev]")
    }
    elseif (Ensure-VenvPip) {
        Invoke-Checked ".venv\Scripts\python" @("-m", "pip", "install", "-e", ".[dev]")
    }
    else {
        Write-Warning "pip is unavailable in .venv; skipping dependency install and using existing environment."
    }
    Invoke-Checked ".venv\Scripts\python" @("-m", "pytest")
}
finally {
    Pop-Location
}

Push-Location (Join-Path $RepoRoot "frontend")
try {
    if (-not (Test-Path "node_modules")) {
        Invoke-Checked "npm" @("install")
    }
    Invoke-Checked "npm" @("run", "build")
    if ($InstallBrowsers) {
        Invoke-Checked "npx" @("playwright", "install", "chromium")
    }
    else {
        Write-Host "Playwright browser install skipped; using existing browser cache."
    }
    Invoke-Checked "npx" @("playwright", "test")
}
finally {
    Pop-Location
}

Write-Host "All local checks passed."
