@echo off
rem TerraTrend local launcher for Windows. Mirrors start.sh.
rem Usage: start.cmd [port]      (default port 8517)
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || goto :failed
)

".venv\Scripts\python.exe" -c "import numpy, requests, netCDF4" >nul 2>&1
if errorlevel 1 (
  echo Installing Python dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :failed
)

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8517"

echo TerraTrend running on http://127.0.0.1:%PORT%
".venv\Scripts\python.exe" backend\server.py %PORT%
goto :eof

:failed
echo.
echo Startup failed. Check that Python 3.10+ is installed and on PATH.
exit /b 1
