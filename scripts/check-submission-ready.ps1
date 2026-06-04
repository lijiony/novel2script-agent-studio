param(
    [switch]$AllowMissingDemo
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ReadmePath = Join-Path $RepoRoot "README.md"
$BatchStart = [DateTimeOffset]::Parse("2026-06-05T00:00:00+08:00")
$BatchEnd = [DateTimeOffset]::Parse("2026-06-07T23:59:59+08:00")

function Assert-Ok($Condition, $Message) {
    if (-not $Condition) {
        throw $Message
    }
    Write-Host "[OK] $Message"
}

Push-Location $RepoRoot
try {
    $insideWorkTree = git rev-parse --is-inside-work-tree
    Assert-Ok ($insideWorkTree -eq "true") "Repository is a Git work tree."

    $status = git status --porcelain
    Assert-Ok (-not $status) "Working tree is clean."

    $remote = git remote get-url origin
    Assert-Ok ($remote -match "lijiony/novel2script-agent-studio") "Origin points to the submission repository."

    $branch = git branch --show-current
    Assert-Ok ($branch -eq "main") "Current branch is main."

    $commitTimes = git log --format=%cI
    foreach ($commitTime in $commitTimes) {
        $parsed = [DateTimeOffset]::Parse($commitTime)
        if ($parsed -lt $BatchStart -or $parsed -gt $BatchEnd) {
            throw "Commit timestamp outside third-batch window: $commitTime"
        }
    }
    Write-Host "[OK] All commit timestamps are inside the third-batch window."

    $readme = Get-Content -Path $ReadmePath -Raw -Encoding UTF8
    Assert-Ok ($readme -match "Demo video") "README has a demo video section."
    if ($readme -match "Demo video:\s*TODO") {
        if ($AllowMissingDemo) {
            Write-Host "[WARN] README demo video link is still TODO."
        }
        else {
            throw "README demo video link is still TODO. Replace it before final submission."
        }
    }
    else {
        Write-Host "[OK] README demo video link is not TODO."
    }

    Assert-Ok ($readme -match "Original Work") "README documents original work."
    Assert-Ok (Test-Path (Join-Path $RepoRoot "docs/schema.md")) "Schema documentation exists."
    Assert-Ok (Test-Path (Join-Path $RepoRoot "samples/sample_script.yaml")) "Generated sample YAML exists."
    Assert-Ok (Test-Path (Join-Path $RepoRoot "docs/submission_summary.md")) "Submission summary exists."

    Write-Host "Submission readiness checks completed."
}
finally {
    Pop-Location
}
