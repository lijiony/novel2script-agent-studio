$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $RepoRoot "backend")
if (-not (Test-Path ".venv")) {
    uv venv
    uv pip install -e ".[dev]"
}
.venv\Scripts\python -m pytest
Pop-Location

Push-Location (Join-Path $RepoRoot "frontend")
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run build
npx playwright install chromium
npx playwright test
Pop-Location

Write-Host "All local checks passed."
