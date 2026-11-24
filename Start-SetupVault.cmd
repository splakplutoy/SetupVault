@echo off
setlocal
pushd "%~dp0" || exit /b 1
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -B app.py --open
) else (
    python -B app.py --open
)
set "result=%errorlevel%"
if not "%result%"=="0" pause
popd
exit /b %result%
