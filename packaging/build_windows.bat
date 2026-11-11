@echo off
REM Build the Windows binaries for Inkstone in place (cmd).
REM packaging\build_windows.ps1 does the same from a clean copy, works from
REM WSL, and also builds the installer when Inno Setup is present.
REM
REM Run on Windows in a terminal (cmd). Requires Python 3.10+ on PATH.
REM Output: dist\Inkstone\      (one-dir bundle, fastest startup)
REM         dist\Inkstone.exe   (portable single file)

setlocal
set HERE=%~dp0
set ROOT=%HERE%..

cd /d "%ROOT%"

echo ^>^> Creating build venv...
if not exist .build_venv (
    python -m venv .build_venv
)
call .build_venv\Scripts\activate.bat

echo ^>^> Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r "%ROOT%\requirements.txt" pyinstaller

echo ^>^> Building with PyInstaller...
rmdir /s /q build 2>nul
python -m PyInstaller --noconfirm "%ROOT%\packaging\inkstone.spec"

echo.
echo ^>^> Done: dist\Inkstone\Inkstone.exe and dist\Inkstone.exe
endlocal
