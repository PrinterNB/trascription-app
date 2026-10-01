@echo off
rem One-click setup: creates the virtual environment, installs core and
rem optional dependencies, and generates the tray icon.
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo No system Python found. Install Python 3 first, then run this again.
    pause
    exit /b 1
)

echo Creating virtual environment...
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat

echo.
echo Installing core dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo Core install failed.
    pause
    exit /b 1
)

echo.
echo Installing optional engines (Canary / Parakeet)...
pip install -r requirements-optional.txt

echo.
echo Generating tray icon...
python trayicon.py

echo.
echo All done. To start the app:
echo     start /b "" .venv\Scripts\pythonw.exe app.py
echo.
pause
