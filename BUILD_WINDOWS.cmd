@echo off
setlocal
cd /d "%~dp0"
echo ===============================================
echo   ELSEWHERE STUDIO - WINDOWS PORTABLE BUILDER
echo ===============================================
echo.
echo This is for DEVELOPERS. Finished portable builds do not need Python.
echo.
where py >nul 2>nul
if errorlevel 1 goto missing
py -3.11 --version >nul 2>nul
if errorlevel 1 goto missing
if not exist .venv py -3.11 -m venv .venv
if not exist .venv\Scripts\python.exe goto fail
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pytest -q tests
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name "Elsewhere Studio" --collect-all rawpy --collect-all tifffile elsewhere_studio.py
if errorlevel 1 goto fail
echo.
echo Successfully built standalone app:
echo dist\Elsewhere Studio\Elsewhere Studio.exe
echo Keep the whole dist\Elsewhere Studio folder together.
pause
exit /b 0
:missing
echo Python 3.11 is needed only when compiling LOCALLY.
echo To avoid installing it, use the GitHub Actions workflow included in this project.
pause
exit /b 1
:fail
echo Build failed. Read the error printed above.
pause
exit /b 1
