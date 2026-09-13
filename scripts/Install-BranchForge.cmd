@echo off
REM Keep this file beside Install-BranchForge.ps1. Double-click to install.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-BranchForge.ps1"
if errorlevel 1 echo Setup failed. Send the displayed log to the BranchForge team.
pause
