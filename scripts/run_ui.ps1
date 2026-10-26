$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = "F:\Miniforge3\envs\lingjing-ai\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}
Set-Location -LiteralPath $Root
$env:PYTHONUTF8 = "1"
& $Python -m streamlit run frontend/streamlit_app.py --server.address 127.0.0.1 --server.port 8501