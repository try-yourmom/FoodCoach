$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = "F:\Miniforge3\envs\lingjing-ai\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}
Set-Location -LiteralPath $Root
$env:PYTHONUTF8 = "1"
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload