@echo off
chcp 65001 >nul
title 這哪家小貓偵探 Discord Bot
cd /d "%~dp0"

echo ========================================================
echo   🐾 [找餐廳] 這哪家小貓偵探 Discord Bot 獨立視窗
echo   💡 說明：此視窗獨立於 Antigravity 運行，重啟 agy 不受影響
echo   💡 提示：按 Ctrl + C 或直接關閉此視窗即可停止機器人
echo ========================================================
echo.

python -u discord_bot/bot.py

echo.
echo [ℹ️] 機器人進程已結束。按任意鍵關閉此視窗...
pause >nul
