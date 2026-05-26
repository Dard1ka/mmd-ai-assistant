# Start semua services untuk MMD AI Assistant
# Usage: klik kanan file ini → "Run with PowerShell"
#        atau di terminal: powershell -ExecutionPolicy Bypass -File start-all.ps1

$ErrorActionPreference = "Continue"
$ProjectRoot = "$PSScriptRoot\.."
$CloudflaredExe = "$ProjectRoot\tools\cloudflared.exe"
$TunnelLogFile = "$ProjectRoot\tools\tunnel.log"
$HelperLogFile = "$ProjectRoot\host-helper\helper.log"

Write-Host "`n=== Starting MMD AI Assistant Services ===`n" -ForegroundColor Cyan

# ===== 1. Start n8n container =====
Write-Host "[1/4] Starting n8n Docker container..." -ForegroundColor Yellow
docker start n8n 2>&1 | Out-Null
Start-Sleep -Seconds 3
$n8nStatus = docker ps --filter "name=n8n" --format "{{.Status}}"
if ($n8nStatus -like "Up*") {
    Write-Host "      OK - n8n running ($n8nStatus)" -ForegroundColor Green
} else {
    Write-Host "      FAIL - n8n tidak jalan!" -ForegroundColor Red
    exit 1
}

# ===== 2. Start Cloudflare Tunnel =====
Write-Host "[2/4] Starting Cloudflare Tunnel..." -ForegroundColor Yellow
# Kill old tunnels
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Remove-Item $TunnelLogFile -ErrorAction SilentlyContinue

Start-Process -FilePath $CloudflaredExe `
  -ArgumentList "tunnel", "--url", "http://localhost:5678" `
  -RedirectStandardOutput $TunnelLogFile `
  -RedirectStandardError "$TunnelLogFile.err" `
  -WindowStyle Hidden

# Wait for tunnel URL (max 30 sec)
$tunnelUrl = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $TunnelLogFile) {
        $content = Get-Content $TunnelLogFile -Raw -ErrorAction SilentlyContinue
        if ($content -match 'https://([a-z0-9\-]+\.trycloudflare\.com)') {
            $tunnelUrl = "https://" + $matches[1]
            break
        }
    }
    # Cek juga di stderr file
    if (Test-Path "$TunnelLogFile.err") {
        $content = Get-Content "$TunnelLogFile.err" -Raw -ErrorAction SilentlyContinue
        if ($content -match 'https://([a-z0-9\-]+\.trycloudflare\.com)') {
            $tunnelUrl = "https://" + $matches[1]
            break
        }
    }
}

if ($tunnelUrl) {
    Write-Host "      OK - Tunnel: $tunnelUrl" -ForegroundColor Green
} else {
    Write-Host "      FAIL - Tunnel tidak dapat URL dalam 30 detik" -ForegroundColor Red
    Write-Host "      Cek manual: type $TunnelLogFile" -ForegroundColor Gray
    exit 1
}

# ===== 3. Update n8n WEBHOOK_URL kalau tunnel URL berubah =====
Write-Host "[3/4] Checking n8n WEBHOOK_URL..." -ForegroundColor Yellow
$currentUrl = docker inspect n8n --format "{{range .Config.Env}}{{println .}}{{end}}" | Select-String "^WEBHOOK_URL=" | ForEach-Object { ($_ -split "=", 2)[1] }
if ($currentUrl -ne $tunnelUrl) {
    Write-Host "      Tunnel URL berubah, recreating container..." -ForegroundColor Yellow
    Write-Host "      Old: $currentUrl" -ForegroundColor Gray
    Write-Host "      New: $tunnelUrl" -ForegroundColor Gray
    $tunnelHost = $tunnelUrl -replace 'https://', ''
    docker stop n8n 2>&1 | Out-Null
    docker rm n8n 2>&1 | Out-Null
    docker run -d --name n8n -p 5678:5678 `
      -v n8n_data:/home/node/.n8n `
      -e "WEBHOOK_URL=$tunnelUrl" `
      -e "N8N_HOST=$tunnelHost" `
      -e "N8N_PROTOCOL=https" `
      -e "N8N_PORT=5678" `
      -e "N8N_EDITOR_BASE_URL=$tunnelUrl" `
      n8nio/n8n 2>&1 | Out-Null
    Start-Sleep -Seconds 5
    Write-Host "      OK - n8n recreated with new URL" -ForegroundColor Green
} else {
    Write-Host "      OK - URL match, no recreate" -ForegroundColor Green
}

# ===== 4. Start Host Helper =====
Write-Host "[4/4] Starting Host Helper (FastAPI)..." -ForegroundColor Yellow
# Kill old helper
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*host-helper*app.py*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$helperDir = "$ProjectRoot\host-helper"
Start-Process -FilePath "python" `
  -ArgumentList "app.py" `
  -WorkingDirectory $helperDir `
  -RedirectStandardOutput $HelperLogFile `
  -RedirectStandardError "$HelperLogFile.err" `
  -WindowStyle Hidden

# Wait for helper to be ready (longer timeout, FastAPI startup slow)
Start-Sleep -Seconds 4
$helperReady = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest "http://localhost:8000/" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $helperReady = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if ($helperReady) {
    Write-Host "      OK - Host Helper jalan di http://localhost:8000" -ForegroundColor Green
} else {
    Write-Host "      FAIL - Host Helper tidak start. Cek $HelperLogFile" -ForegroundColor Red
}

# ===== Summary =====
Write-Host "`n=== ALL READY ===`n" -ForegroundColor Cyan
Write-Host "n8n UI    : http://localhost:5678" -ForegroundColor White
Write-Host "n8n Public: $tunnelUrl" -ForegroundColor White
Write-Host "Helper API: http://localhost:8000" -ForegroundColor White
Write-Host "Helper Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "TIP: Buka Telegram, kirim pesan ke @MMD_Dardika_bot" -ForegroundColor Gray
Write-Host "TIP: Stop semua dengan: powershell -File $ProjectRoot\stop-all.ps1" -ForegroundColor Gray
Write-Host ""
