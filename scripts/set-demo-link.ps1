param(
    [Parameter(Mandatory = $true)]
    [string]$DemoUrl
)

$ErrorActionPreference = "Stop"

if ($DemoUrl -notmatch "^https?://") {
    throw "DemoUrl must start with http:// or https://"
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ReadmePath = Join-Path $RepoRoot "README.md"
$SummaryPath = Join-Path $RepoRoot "docs/submission_summary.md"

function Update-File($Path, [scriptblock]$Updater) {
    $content = Get-Content -Path $Path -Raw -Encoding UTF8
    $updated = & $Updater $content
    if ($updated -eq $content) {
        throw "No replacement was made in $Path"
    }
    Set-Content -Path $Path -Value $updated -Encoding UTF8 -NoNewline
}

Update-File $ReadmePath {
    param($content)
    $content -replace "> Demo video: .*", "> Demo video: $DemoUrl"
}

Update-File $SummaryPath {
    param($content)
    $content -replace "TODO: replace with the narrated demo video URL after upload\.", $DemoUrl
}

Write-Host "Demo link updated in README.md and docs/submission_summary.md"
Write-Host "Next: run .\scripts\check-submission-ready.ps1"
