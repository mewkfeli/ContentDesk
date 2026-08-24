@echo off
setlocal
cd /d "%~dp0"
title ContentDesk Launcher

rem Keep the Windows desktop shortcut on the current ContentDesk icon.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$P=[Environment]::GetFolderPath('Desktop')+'\ContentDesk.lnk'; $W=New-Object -ComObject WScript.Shell; $S=$W.CreateShortcut($P); $S.TargetPath='%~dp0start-contentdesk.cmd'; $S.WorkingDirectory='%~dp0'; $S.Description='ContentDesk'; $S.IconLocation='%~dp0assets\contentdesk.ico,0'; $S.Save()" >nul 2>nul
ie4uinit.exe -show >nul 2>nul

if not exist "backend\.venv\Scripts\python.exe" goto :setup
if not exist "frontend\node_modules" goto :setup

start "ContentDesk Backend" /D "%~dp0backend" cmd /k "call .venv\Scripts\activate.bat && uvicorn app.main:app --reload"
timeout /t 2 /nobreak >nul
start "ContentDesk Frontend" /D "%~dp0frontend" cmd /k "npm run dev"
timeout /t 4 /nobreak >nul
start "" "http://localhost:3000"
exit /b 0

:setup
echo ContentDesk is not installed yet. Starting setup...
call "%~dp0setup-contentdesk.cmd"
if errorlevel 1 exit /b 1
call "%~dp0start-contentdesk.cmd"
