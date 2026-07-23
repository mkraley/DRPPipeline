@echo off
setlocal
REM DRPID 42 — large USFS publication downloads

echo Downloading big.zip ...
aria2c -c -x 8 -s 8 -j 1 --file-allocation=none --max-tries=0 --retry-wait=10 --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" -d "C:\Documents\Code\DRPPipeline\collectors\tests\_tmp_aria2_write" -o "big.zip" "https://example.com/big.zip"
if errorlevel 1 exit /b 1

echo Done.
