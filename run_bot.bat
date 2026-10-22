@echo off
title Food Guessr Discord Bot
cd /d "%~dp0"

echo ========================================================
echo   Food Guessr - Detective Cat Discord Bot
echo   Independent Process (Safe to restart / update agy)
echo   To Stop: Press Ctrl + C or close this window
echo ========================================================
echo.

python -u discord_bot/bot.py

echo.
echo [!] Bot process stopped. Press any key to close...
pause >nul
