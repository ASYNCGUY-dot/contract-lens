# 계약서 돋보기 — 서버와 터널을 함께 띄운다.
#
# 지인에게 링크를 보내 후기를 받기 위한 것이다. 이 창을 닫으면 서버와 터널이
# 함께 꺼지고 **주소도 사라진다.** 창을 열어 둔 동안만 접속된다.
#
# 실행:  PowerShell 에서  .\서비스_켜기.ps1
#        (처음 한 번은  Set-ExecutionPolicy -Scope Process Bypass  가 필요할 수 있다)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$python = "C:\WORK\WORK\.venv\Scripts\python.exe"
$cloudflared = Join-Path $root "tools\cloudflared.exe"

# --- 준비물 확인 ---------------------------------------------------------
if (-not (Test-Path $python)) {
  Write-Host "  [!] 파이썬을 찾지 못했습니다: $python" -ForegroundColor Red
  Write-Host "      경로가 다르면 이 파일에서 `$python 을 고쳐 주세요."
  exit 1
}
if (-not (Test-Path $cloudflared)) {
  Write-Host "  [!] tools\cloudflared.exe 가 없습니다." -ForegroundColor Red
  Write-Host "      https://github.com/cloudflare/cloudflared/releases/latest 에서"
  Write-Host "      cloudflared-windows-amd64.exe 를 받아 tools\cloudflared.exe 로 두세요."
  exit 1
}
if (-not (Test-Path (Join-Path $root "web\dist\index.html"))) {
  Write-Host "  [!] 화면이 빌드되어 있지 않습니다. web 폴더에서 npm run build 를 먼저 하세요." -ForegroundColor Red
  exit 1
}
if (-not (Select-String -Path (Join-Path $root ".env") -Pattern "^ADMIN_KEY=.+" -Quiet -ErrorAction SilentlyContinue)) {
  Write-Host "  [주의] .env 에 ADMIN_KEY 가 비어 있습니다. 후기 운영자 보기가 막힙니다." -ForegroundColor Yellow
}

# --- 이미 쓰고 있는 8000 포트 정리 ---------------------------------------
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host "  이전 서버를 닫습니다 (PID $($_.OwningProcess))"
  Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}

# --- API 서버 ------------------------------------------------------------
Write-Host ""
Write-Host "  서버를 켜는 중입니다. 모델을 올리는 데 10초쯤 걸립니다…"
$env:HF_HUB_OFFLINE = "1"
$env:USE_ONNX = "1"          # torch 대신 ONNX. 메모리가 절반 아래로 준다.
$api = Start-Process -FilePath $python `
  -ArgumentList "-m","uvicorn","src.api:app","--host","127.0.0.1","--port","8000","--log-level","warning" `
  -PassThru -NoNewWindow

$ready = $false
foreach ($i in 1..40) {
  Start-Sleep -Seconds 1
  try {
    if ((Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 3).ok) { $ready = $true; break }
  } catch {}
}
if (-not $ready) {
  Write-Host "  [!] 서버가 뜨지 않았습니다." -ForegroundColor Red
  Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
  exit 1
}
Write-Host "  서버 준비됨 (http://127.0.0.1:8000)" -ForegroundColor Green

# --- 터널 ----------------------------------------------------------------
Write-Host "  주소를 만드는 중입니다…"
$log = Join-Path $env:TEMP "contract-lens-tunnel.log"
if (Test-Path $log) { Remove-Item $log -Force }
$tun = Start-Process -FilePath $cloudflared `
  -ArgumentList "tunnel","--url","http://127.0.0.1:8000","--no-autoupdate" `
  -PassThru -NoNewWindow -RedirectStandardError $log

$url = $null
foreach ($i in 1..40) {
  Start-Sleep -Seconds 1
  if (Test-Path $log) {
    $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue
    if ($m) { $url = $m.Matches[0].Value; break }
  }
}

Write-Host ""
if ($url) {
  Write-Host "  ============================================================"
  Write-Host "   $url" -ForegroundColor Cyan
  Write-Host "  ============================================================"
  Write-Host ""
  Write-Host "  이 주소를 지인에게 보내세요."
  Write-Host "  후기는 화면의 [후기] 탭 → [운영자] 에서 ADMIN_KEY 로 보실 수 있습니다."
} else {
  Write-Host "  [!] 주소를 얻지 못했습니다. 로그: $log" -ForegroundColor Red
}
Write-Host ""
Write-Host "  * 이 창을 닫으면 서비스가 꺼지고 주소도 사라집니다."
Write-Host "  * 다시 켜면 주소가 바뀝니다."
Write-Host "  * 끄려면 이 창에서 Ctrl+C 를 누르세요."
Write-Host ""

try {
  Wait-Process -Id $tun.Id
} finally {
  Write-Host ""
  Write-Host "  정리 중…"
  Stop-Process -Id $tun.Id -Force -ErrorAction SilentlyContinue
  Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
  Write-Host "  서비스를 껐습니다."
}
