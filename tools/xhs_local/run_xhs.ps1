#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LockFile = Join-Path $ProjectRoot "data\xhs_outbox\.xhs_local.lock"
$LogHint = Join-Path $ProjectRoot "logs\xhs_local_crawl.log"

function Write-XhsLog([string]$Message) {
  $line = "{0} INFO {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Write-Host $line
  $logDir = Split-Path $LogHint
  if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
  Add-Content -Path $LogHint -Value $line -Encoding UTF8
}

if (Test-Path $LockFile) {
  Write-XhsLog "Dang co mot tien trinh Xiaohongshu chay. Dung lai."
  exit 1
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
  if (-not $Python) { $Python = "python" }
}

$McPath = $env:MEDIACRAWLER_PATH
if (-not $McPath) { $McPath = "C:\tools\MediaCrawler" }
if (-not (Test-Path $McPath)) {
  Write-XhsLog "Khong thay MediaCrawler tai $McPath. Clone repo ra ngoai project roi dat MEDIACRAWLER_PATH."
  exit 1
}

Write-XhsLog "Kiem tra Python: $Python"
& $Python -c "import sys; print(sys.version)"
if ($LASTEXITCODE -ne 0) {
  Write-XhsLog "Python khong chay duoc."
  exit 1
}

Write-XhsLog "Kiem tra Playwright..."
& $Python -c "import playwright; print('playwright-ok')"
if ($LASTEXITCODE -ne 0) {
  Write-XhsLog "Thieu Playwright. Cai trong MediaCrawler: pip install playwright && playwright install chromium"
  exit 1
}

$env:PYTHONPATH = $ProjectRoot
Write-XhsLog "Bat dau run_week.py"
& $Python (Join-Path $PSScriptRoot "run_week.py")
$code = $LASTEXITCODE
if ($code -eq 2) {
  Write-XhsLog "Session Xiaohongshu het han hoac gap captcha. Mo MediaCrawler va quet QR lai. Khong tu vuot captcha."
}
exit $code
