@echo off
title SignalRGB Sync System - controller (visible window)
cd /d "%~dp0"
echo Stopping the background controller and running it here so you can watch it.
echo Close this window (or press Ctrl+C) when done - the background controller restarts by itself.
echo.
schtasks /End /TN SignalRGBController >nul 2>&1
timeout /t 2 /nobreak >nul
py -3 -u rgb_controller.py
schtasks /Run /TN SignalRGBController >nul 2>&1
