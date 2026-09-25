# Start the ProManage API in its own console window.
#
# Fixes the recurring "backend failed to load" problem by:
#   1. Freeing port 8000 from any stale/dying uvicorn instance (a leftover
#      process from a previous run keeps the port bound and makes every new
#      start fail with "address already in use").
#   2. Running uvicorn with the project venv interpreter, which has the
#      pinned requirements installed. The system Python does NOT have them
#      and dies at startup with ModuleNotFoundError.
#
# Usage:  .\start_backend.ps1

$ErrorActionPreference = "Stop"

$BackendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $BackendDir "..\.venv\Scripts\python.exe"
$LogFile = Join-Path $BackendDir "backend.log"
$Port = 8000

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "ERROR: venv interpreter not found at $VenvPython" -ForegroundColor Red
    Write-Host "Run:  python -m venv ..\.venv`nThen: ..\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

# 1. Kill any process holding our port (this also catches the dead
#    "Bound" sockets left behind when a previous uvicorn crashed).
$held = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
foreach ($conn in $held) {
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Freeing port ${Port}: stopping $($proc.ProcessName) (PID $($proc.Id))" -ForegroundColor Yellow
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 1

# 2. Start the API in its own window, logging to backend.log as well.
Write-Host "Starting ProManage API on http://localhost:${Port} ..." -ForegroundColor Green
Start-Process -FilePath $VenvPython `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$Port", "--reload" `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError "$LogFile.err" `
    -WindowStyle Normal

Write-Host "Logs: $LogFile  (close the uvicorn window to stop the backend)"