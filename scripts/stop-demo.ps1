$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$CurrentPid = $PID

$processes = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $CurrentPid -and
    $_.Name -in @("python.exe", "node.exe", "powershell.exe") -and
    $_.CommandLine -like "*$RepoRoot*"
}

foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Stopped $($processes.Count) demo process(es)."
