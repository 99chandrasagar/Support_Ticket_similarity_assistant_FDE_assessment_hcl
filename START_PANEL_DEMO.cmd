@echo off
setlocal
cd /d "%~dp0"
set "FDE_PRESENT_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%FDE_PRESENT_PY%" (
  "%FDE_PRESENT_PY%" "%~dp0present_to_panel.py" %*
  goto finish
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0present_to_panel.py" %*
  goto finish
)
where python >nul 2>nul
if not errorlevel 1 (
  python "%~dp0present_to_panel.py" %*
  goto finish
)
echo Python 3.11 or newer is required.
:finish
if /i "%~1"=="--check" exit /b
echo.
pause
