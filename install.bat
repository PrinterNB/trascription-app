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
if errorlevel 1 (
    echo Could not create the virtual environment.
    pause
    exit /b 1
)
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
if errorlevel 1 (
    echo Tray icon generation failed.
    pause
    exit /b 1
)

echo.
echo Creating the one-click launcher (VoiceDictation.bat)...
python make_launcher.py
if errorlevel 1 (
    echo Launcher generation failed.
    pause
    exit /b 1
)

echo.
echo All done. A launcher file was created next to this script:
echo     VoiceDictation.bat
echo Copy that file to your desktop (or anywhere) and double-click it to start
echo the app in your system tray.
echo.
pause
