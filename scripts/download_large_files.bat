@echo off
setlocal
cd /d "%~dp0.."
python scripts\download_large_files.py %*
exit /b %ERRORLEVEL%
