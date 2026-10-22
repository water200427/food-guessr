@echo off
chcp 65001 >nul
title 這哪家小貓偵探 Discord Bot
cd /d "%~dp0"

echo ========================================================
echo   🐾 [找餐廳] 這哪家小貓偵探 Discord Bot 守護進程
echo   💡 說明：此視窗獨立於 Antigravity 運行，重啟 agy 不受影響
echo ========================================================
echo.

:loop
python -u discord_bot/bot.py
echo.
echo [⚠️] 機器人連線中斷或進程退出，將於 5 秒後自動重新連線...
timeout /t 5 /nobreak >nul
echo [🔄] 正在重啟機器人...
goto loop
