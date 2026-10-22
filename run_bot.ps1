$host.UI.RawUI.WindowTitle = "這哪家小貓偵探 Discord Bot"
Set-Location $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  🐾 [找餐廳] 這哪家小貓偵探 Discord Bot 守護進程" -ForegroundColor Green
Write-Host "  💡 說明：此視窗獨立於 Antigravity 運行，重啟 agy 不受影響" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

while ($true) {
    python -u discord_bot/bot.py
    Write-Host ""
    Write-Host "[⚠️] 機器人連線中斷或進程退出，將於 5 秒後自動重新連線..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
    Write-Host "[🔄] 正在重啟機器人..." -ForegroundColor Green
}
