# Stop semua services MMD AI Assistant
Write-Host "`n=== Stopping MMD AI Assistant Services ===`n" -ForegroundColor Cyan

Write-Host "[1/3] Stopping n8n container..." -ForegroundColor Yellow
docker stop n8n 2>&1 | Out-Null
Write-Host "      OK" -ForegroundColor Green

Write-Host "[2/3] Stopping Cloudflare Tunnel..." -ForegroundColor Yellow
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "      OK" -ForegroundColor Green

Write-Host "[3/3] Stopping Host Helper..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*host-helper*" } | Stop-Process -Force
Write-Host "      OK" -ForegroundColor Green

Write-Host "`nAll stopped.`n" -ForegroundColor Cyan
