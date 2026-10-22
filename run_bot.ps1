$host.UI.RawUI.WindowTitle = "這哪家小貓偵探 Discord Bot"
Set-Location $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  🐾 [找餐廳] 這哪家小貓偵探 Discord Bot 獨立視窗" -ForegroundColor Green
Write-Host "  💡 說明：此視窗獨立於 Antigravity 運行，重啟 agy 不受影響" -ForegroundColor Yellow
Write-Host "  💡 提示：按 Ctrl + C 或直接關閉此視窗即可停止機器人" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

python -u discord_bot/bot.py

Write-Host ""
Write-Host "[ℹ️] 機器人進程已結束。" -ForegroundColor Gray
Read-Host "按 Enter 鍵關閉此視窗..."
