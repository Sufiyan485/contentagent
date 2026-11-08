$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $taskRoot '.cache/tmp'
$env:TMP=$env:TEMP
$env:PLAYWRIGHT_BROWSERS_PATH=Join-Path $taskRoot '.cache/ms-playwright'
$env:LANGSMITH_TRACING='false'
$env:LANGCHAIN_TRACING_V2='false'
$env:XDG_CACHE_HOME=Join-Path $taskRoot '.cache'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
& '.\.venv\Scripts\python.exe' -B -m pytest backend/tests --basetemp='.cache/pytest-tmp' -o cache_dir='.cache/pytest' @args
exit $LASTEXITCODE
