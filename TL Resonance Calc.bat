@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title TL Resonance Calc

REM Double-click "TL Resonance Calc.vbs" (preferred) or this .bat file.

set "PY="
if exist "venv\Scripts\python.exe" set "PY=%CD%\venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>&1 && for /f "delims=" %%I in ('where py') do (
    set "PY=py -3"
    goto :py_found
  )
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
:py_found
if not defined PY (
  echo Python was not found. Install Python 3 from https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo Creating virtualenv...
  %PY% -m venv venv
  if errorlevel 1 (
    echo Failed to create venv.
    pause
    exit /b 1
  )
)

set "VPY=%CD%\venv\Scripts\python.exe"
set "VPYW=%CD%\venv\Scripts\pythonw.exe"

echo Starting TL Resonance Calc...
if exist "%VPYW%" (
  start "" "%VPYW%" -m tl_resonance
) else (
  start "" "%VPY%" -m tl_resonance
)
exit /b 0
