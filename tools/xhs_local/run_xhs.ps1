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

$AppPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $AppPython)) {
  Write-XhsLog "Khong thay Python cua app tai $AppPython. Hay tao lai .venv va cai requirements-dev.txt."
  exit 1
}

$McPath = $env:MEDIACRAWLER_PATH
if (-not $McPath) { $McPath = "C:\tools\MediaCrawler" }
if (-not (Test-Path $McPath)) {
  Write-XhsLog "Khong thay MediaCrawler tai $McPath. Clone repo ra ngoai project roi dat MEDIACRAWLER_PATH."
  exit 1
}

Write-XhsLog "Kiem tra Python cua app: $AppPython"
& $AppPython -c "import sys; print(sys.version)"
if ($LASTEXITCODE -ne 0) {
  Write-XhsLog "Python cua app khong chay duoc."
  exit 1
}

$McPython = $env:MEDIACRAWLER_PYTHON
if (-not $McPython) { $McPython = Join-Path $McPath ".venv\Scripts\python.exe" }
if (-not (Test-Path $McPython)) {
  Write-XhsLog "Khong thay Python rieng cua MediaCrawler tai $McPython."
  exit 1
}
$env:MEDIACRAWLER_PYTHON = $McPython

Write-XhsLog "Kiem tra MediaCrawler Python va Playwright: $McPython"
& $McPython -c "import sys, playwright; print(sys.version); print('playwright-ok')"
if ($LASTEXITCODE -ne 0) {
  Write-XhsLog "Python MediaCrawler loi hoac thieu Playwright. Cai requirements.txt trong .venv cua MediaCrawler."
  exit 1
}

$env:PYTHONPATH = $ProjectRoot
Write-XhsLog "Bat dau run_week.py"
& $AppPython (Join-Path $PSScriptRoot "run_week.py")
$code = $LASTEXITCODE
if ($code -eq 2) {
  Write-XhsLog "Session Xiaohongshu het han hoac gap captcha. Mo MediaCrawler va quet QR lai. Khong tu vuot captcha."
}
exit $code
