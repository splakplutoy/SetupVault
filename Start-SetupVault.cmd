@echo off
pushd "%~dp0"
python -B app.py --open
if errorlevel 1 pause
popd
