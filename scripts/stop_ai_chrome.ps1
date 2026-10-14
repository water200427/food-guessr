param (
    [int]$Port = 9222
)

Write-Host "正在檢查連接埠 $Port 上的 AI 專用 Chrome 處理程序..." -ForegroundColor Cyan

$Connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue

if (-not $Connections) {
    Write-Host "連接埠 $Port 上沒有執行中的 AI 專用 Chrome。" -ForegroundColor Yellow
    exit 0
}

$ProcessIds = $Connections | Select-Object -ExpandProperty OwningProcess -Unique

foreach ($pidToKill in $ProcessIds) {
    try {
        $p = Get-Process -Id $pidToKill -ErrorAction Stop
        if ($p.ProcessName -like "*chrome*") {
            Write-Host "正在關閉 AI Chrome 處理程序 (PID: $pidToKill)..." -ForegroundColor Yellow
            Stop-Process -Id $pidToKill -Force
        }
    } catch {
        Write-Warning "無法終止 PID: $pidToKill ($($_.Exception.Message))"
    }
}

Write-Host "AI 專用 Chrome 已成功關閉，您的日常 Chrome 未受任何影響。" -ForegroundColor Green
