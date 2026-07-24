@echo off
rem ============================================================
rem  MediFlow - stop the running web server
rem ============================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title MediFlow - توقف

echo.
echo   در حال توقف سرور مدی‌فلو...

rem Match on the command line rather than the image name: the interpreter is
rem shared with other tools, so killing every python.exe would be reckless.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='python3.13.exe'\" | Where-Object { $_.CommandLine -like '*mediflow.web*' };" ^
  "if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Write-Host ('  متوقف شد: ' + $p.Count + ' پروسه') } else { Write-Host '  سروری در حال اجرا نبود.' }"

echo.
ping -n 4 127.0.0.1 >nul
exit /b 0
