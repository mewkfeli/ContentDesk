@echo off
setlocal
cd /d "%~dp0"
title ContentDesk 1.0 - Setup

echo ==========================================
echo        ContentDesk 1.0 - Setup
echo ==========================================
echo.

where python >nul 2>nul || (echo [ERROR] Python not found. Install Python 3.12+ and try again.& pause & exit /b 1)
where npm >nul 2>nul || (echo [ERROR] Node.js/npm not found. Install Node.js 20+ and try again.& pause & exit /b 1)

if not exist "backend\.venv\Scripts\python.exe" (
  echo [1/4] Creating Python environment...
  python -m venv "backend\.venv" || goto :fail
) else (
  echo [1/4] Python environment already exists.
)

echo [2/4] Installing backend packages...
call "backend\.venv\Scripts\activate.bat"
python -m pip install -r "backend\requirements.txt" || goto :fail

echo [3/4] Installing frontend packages...
pushd frontend
if not exist ".env.local" copy /Y ".env.local.example" ".env.local" >nul
call npm install || (popd & goto :fail)
popd

echo [4/4] Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$W=New-Object -ComObject WScript.Shell; $S=$W.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\ContentDesk.lnk'); $S.TargetPath='%~dp0start-contentdesk.cmd'; $S.WorkingDirectory='%~dp0'; $S.Description='ContentDesk'; $S.IconLocation='%~dp0assets\contentdesk.ico,0'; $S.Save()" >nul 2>nul

echo.
echo Setup complete. You can now double-click ContentDesk on the Desktop
echo or run start-contentdesk.cmd.
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup failed. Read the message above and try again.
pause
exit /b 1
