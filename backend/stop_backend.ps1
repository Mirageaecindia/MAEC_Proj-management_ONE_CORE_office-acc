# Stop the ProManage API and free port 8000.
#
# Usage:  .\stop_backend.ps1
$Port = 8000
$held = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if (-not $held) {
    Write-Host "No process is using port ${Port}." -ForegroundColor Green
    exit 0
}
foreach ($conn in $held) {
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Stopping $($proc.ProcessName) (PID $($proc.Id)) on port ${Port}" -ForegroundColor Yellow
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "Port ${Port} is free." -ForegroundColor Green