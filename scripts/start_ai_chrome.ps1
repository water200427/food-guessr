param (
    [int]$Port = 9222,
    [switch]$Headless = $false
)

$ErrorActionPreference = "Stop"

# 尋找 Chrome 執行檔路徑
$ChromePaths = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

$ChromeExe = $null
foreach ($path in $ChromePaths) {
    if (Test-Path $path) {
        $ChromeExe = $path
        break
    }
}

if (-not $ChromeExe) {
    Write-Error "找不到 Google Chrome 執行檔，請確認系統已安裝 Chrome。"
    exit 1
}

# 專案專屬的獨立 Profile 資料夾（完全不干擾使用者的日常 Chrome）
$ProfileDir = Join-Path $PSScriptRoot "..\.ai_chrome_profile"
if (-not (Test-Path $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
}

$FullProfileDir = (Resolve-Path $ProfileDir).Path

# 檢查該端口是否已經在執行
$Existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Existing) {
    Write-Host "AI 專用 Chrome 已經在連接埠 $Port 上運行中。" -ForegroundColor Yellow
    exit 0
}

# Chrome 啟動參數
$Arguments = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$FullProfileDir",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled",
    "--password-store=basic"
)

if ($Headless) {
    $Arguments += "--headless=new"
    $Arguments += "--disable-gpu"
}

Write-Host "正在啟動 AI 專用 Chrome..." -ForegroundColor Cyan
Write-Host "執行路徑: $ChromeExe"
Write-Host "除錯連接埠: $Port"
Write-Host "獨立資料目錄: $FullProfileDir"
if ($Headless) {
    Write-Host "模式: 背景無頭模式 (Headless)" -ForegroundColor Green
} else {
    Write-Host "模式: 獨立視窗模式" -ForegroundColor Green
}

# 背景啟動
Start-Process -FilePath $ChromeExe -ArgumentList $Arguments

# 等待連線就緒
$Ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 2 -ErrorAction Stop
        if ($response) {
            $Ready = $true
            break
        }
    } catch {}
}

if ($Ready) {
    Write-Host "AI 專用 Chrome 已成功啟動並就緒！(Port: $Port)" -ForegroundColor Green
} else {
    Write-Warning "Chrome 已啟動，但連線埠尚未響應，請稍候再確認。"
}
