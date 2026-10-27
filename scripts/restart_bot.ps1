# ==============================================================================
# 貓貓偵探 (Discord Bot) 平滑重啟與健康檢查腳本
# ==============================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🐾 正在平滑重啟貓貓偵探 Discord Bot..." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. 查找並終止既有的 bot.py 進程 (避免多實例重複回覆)
$currentPid = $PID
$oldProcesses = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*bot.py*" -and $_.ProcessId -ne $currentPid
}

if ($oldProcesses) {
    Write-Host "[1/3] 發現運行中的舊實例，正在安全終止..." -ForegroundColor Yellow
    foreach ($proc in $oldProcesses) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "      [-] 已終止 PID: $($proc.ProcessId)" -ForegroundColor DarkGray
        } catch {
            Write-Host "      [!] 終止 PID $($proc.ProcessId) 失敗: $_" -ForegroundColor DarkRed
        }
    }
} else {
    Write-Host "[1/3] 無運作中的舊實例，直接啟動新進程。" -ForegroundColor DarkGray
}

Start-Sleep -Milliseconds 800

# 2. 確定 Python 直譯器路徑
$pythonCmd = "python"
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $pythonCmd = (Get-Command "python").Source
}

Write-Host "[2/3] 啟動全新守護進程 (python -u discord_bot/bot.py)..." -ForegroundColor Yellow

$logDir = Join-Path $RepoRoot "scratch"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logFile = Join-Path $logDir "bot.log"

# 記錄啟動前日誌的位元組大小或行數，以便監控新連線
$initialLength = 0
if (Test-Path $logFile) {
    $initialLength = (Get-Item $logFile).Length
}

# 啟動獨立背景進程
$procStartInfo = New-Object System.Diagnostics.ProcessStartInfo
$procStartInfo.FileName = $pythonCmd
$procStartInfo.Arguments = "-u discord_bot/bot.py"
$procStartInfo.WorkingDirectory = $RepoRoot
$procStartInfo.UseShellExecute = $false
$procStartInfo.CreateNoWindow = $true

$botProc = [System.Diagnostics.Process]::Start($procStartInfo)
if ($botProc) {
    Write-Host "      [+] 守護進程已建立，PID: $($botProc.Id)" -ForegroundColor DarkGreen
} else {
    Write-Host "      [❌] 啟動失敗，請檢查 Python 環境！" -ForegroundColor Red
    exit 1
}

# 3. 健康檢查：監聽 Gateway 連線狀態 (最多等待 15 秒)
Write-Host "[3/3] 正在進行健康檢查，等待連線至 Discord Gateway..." -ForegroundColor Yellow
$timeoutSeconds = 15
$startTime = [System.Diagnostics.Stopwatch]::StartNew()
$connected = $false

while ($startTime.Elapsed.TotalSeconds -lt $timeoutSeconds) {
    if ($botProc.HasExited) {
        Write-Host "      [❌] 警告：Bot 進程異常退出！ExitCode: $($botProc.ExitCode)" -ForegroundColor Red
        if (Test-Path $logFile) {
            Write-Host "--- 最新執行日誌 ---" -ForegroundColor DarkYellow
            Get-Content $logFile -Tail 15
        }
        exit 1
    }

    if (Test-Path $logFile) {
        $recentContent = Get-Content $logFile -Tail 20 -ErrorAction SilentlyContinue | Out-String
        if ($recentContent -match "已成功上線" -or $recentContent -match "has connected to Gateway" -or $recentContent -match "Connected to Gateway") {
            $connected = $true
            break
        }
    }
    Start-Sleep -Milliseconds 500
}

if ($connected) {
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "✅ 貓貓偵探已成功重啟並連線至 Discord Gateway！🐾" -ForegroundColor Green
    Write-Host "   - 守護進程 PID : $($botProc.Id)" -ForegroundColor Green
    Write-Host "   - 耗時         : $($startTime.Elapsed.TotalSeconds.ToString('F1')) 秒" -ForegroundColor Green
    Write-Host "   - 監控日誌     : scratch/bot.log" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
    exit 0
} else {
    Write-Host "⚠️ 健康檢查逾時（未在 $timeoutSeconds 秒內確認 Gateway 連線），請檢查日誌：" -ForegroundColor Yellow
    if (Test-Path $logFile) {
        Get-Content $logFile -Tail 15
    }
    exit 0
}
