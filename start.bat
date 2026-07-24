@echo off
rem ============================================================
rem  MediFlow - start the web server and open it in the browser
rem ============================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions
title MediFlow

rem Paths are derived from THIS file's folder, so the project can be moved
rem or copied to another clinic PC without editing anything here.
set "PROJECT=%~dp0"
if "%PROJECT:~-1%"=="\" set "PROJECT=%PROJECT:~0,-1%"
set "PY=%PROJECT%\.venv-win\Scripts\python.exe"
set "URL=http://127.0.0.1:8000"

rem Must run FROM the project folder: the package is not pip-installed, so
rem "python -m mediflow.web" only resolves when it is on the current path.
cd /d "%PROJECT%" || (echo   [خطا] پوشه پروژه پیدا نشد. & pause & exit /b 1)

rem Data lives OUTSIDE %APPDATA% on purpose. The bundled Python is a Microsoft
rem Store (MSIX) build, and Windows silently redirects %APPDATA% writes from
rem such apps into a private per-package folder - which once left the app and
rem its own maintenance scripts reading two different databases.
if not defined MEDIFLOW_DATA_DIR set "MEDIFLOW_DATA_DIR=%USERPROFILE%\MediFlowData"

echo.
echo   MediFlow
echo   --------
echo   پوشه داده : %MEDIFLOW_DATA_DIR%
echo   آدرس      : %URL%
echo.

if not exist "%PY%" (
  echo   [خطا] پایتون پیدا نشد:
  echo         %PY%
  echo.
  echo   محیط مجازی ساخته نشده است.
  echo.
  pause
  exit /b 1
)

rem Already up? Then just open the browser - never start a second copy,
rem which would fail on the port and leave a confusing error window.
curl --silent --fail --max-time 2 "%URL%/healthz" >nul 2>&1
if not errorlevel 1 (
  echo   سرور از قبل در حال اجراست.
  goto :open
)

echo   در حال راه‌اندازی سرور...
start "MediFlow Server" /min /d "%PROJECT%" "%PY%" -m mediflow.web

rem Wait for it to answer before opening the browser, otherwise the first
rem page load races the server and shows "cannot connect".
set /a _tries=0
:wait
set /a _tries+=1
if %_tries% gtr 40 goto :toolong
ping -n 2 127.0.0.1 >nul
curl --silent --fail --max-time 2 "%URL%/healthz" >nul 2>&1
if errorlevel 1 goto :wait

:open
echo   باز کردن مرورگر...
start "" "%URL%"
echo.
echo   آماده است. برای توقف سرور، پنجره «MediFlow Server» را ببندید.
echo.
ping -n 4 127.0.0.1 >nul
exit /b 0

:toolong
echo.
echo   [خطا] سرور در ۴۰ ثانیه بالا نیامد.
echo   پنجره «MediFlow Server» را ببینید تا پیام خطا را بخوانید.
echo.
pause
exit /b 1
