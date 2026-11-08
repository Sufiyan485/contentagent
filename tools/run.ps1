$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $taskRoot '.cache/tmp'
$env:TMP=$env:TEMP
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $taskRoot '.cache/ms-playwright'
$env:LANGSMITH_TRACING='false'
$env:LANGCHAIN_TRACING_V2='false'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
& '.\.venv\Scripts\python.exe' -B -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --workers 1
exit $LASTEXITCODE
