@echo off
title SignalRGB Sync System - Uninstall
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall.ps1"
echo.
pause
