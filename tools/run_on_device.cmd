@echo off
rem Wrapper for run_on_device.ps1. Windows PowerShell rejects unsigned .ps1
rem scripts under the harness execution policy, so run with Bypass here.
rem
rem Usage:
rem   tools\run_on_device.cmd -SetupOnly
rem   tools\run_on_device.cmd
rem   tools\run_on_device.cmd -DeviceId RF8M123ABCD -Release
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_on_device.ps1" %*
exit /b %ERRORLEVEL%
