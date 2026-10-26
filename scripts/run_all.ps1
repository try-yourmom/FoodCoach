$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = "F:\Miniforge3\envs\lingjing-ai\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}
Set-Location -LiteralPath $Root
$env:PYTHONUTF8 = "1"
$api = Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $Root -WindowStyle Hidden -PassThru
try {
    Start-Sleep -Seconds 2
    & $Python -m streamlit run frontend/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
}
finally {
    if (-not $api.HasExited) {
        Stop-Process -Id $api.Id
    }
}