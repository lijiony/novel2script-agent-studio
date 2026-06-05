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

& (Join-Path $PSScriptRoot "stop-demo.ps1")

Push-Location (Join-Path $RepoRoot "backend")
try {
    if (-not (Test-Path ".venv")) {
        Invoke-Checked "uv" @("venv")
        Invoke-Checked "uv" @("pip", "install", "-e", ".[dev]")
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
    Invoke-Checked "npx" @("playwright", "install", "chromium")
    Invoke-Checked "npx" @("playwright", "test")
}
finally {
    Pop-Location
}

Write-Host "All local checks passed."
