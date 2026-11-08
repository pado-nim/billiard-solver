@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 install.py
    goto done
)
where python >nul 2>nul
if %errorlevel%==0 (
    python install.py
    goto done
)
echo.
echo [!] Python is not installed.
echo     1. Download from https://www.python.org/downloads/
echo     2. Check "Add python.exe to PATH" during install
echo     3. Run install.bat again
start https://www.python.org/downloads/

:done
echo.
pause
