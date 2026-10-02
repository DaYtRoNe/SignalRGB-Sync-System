@echo off
title SignalRGB Sync System - start
schtasks /Run /TN SignalRGBController >nul 2>&1
if errorlevel 1 (
    echo The startup task is missing - running Install.bat instead...
    call "%~dp0Install.bat"
) else (
    echo Controller started. Look for the coloured dot next to the clock.
    timeout /t 3 >nul
)
