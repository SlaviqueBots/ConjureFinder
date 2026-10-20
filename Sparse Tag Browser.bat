@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Sparse Tag Browser

REM Double-click "Sparse Tag Browser.vbs" (preferred) or this .bat file.

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

if not exist "venv\.sparse_tags_deps_ok" (
  echo Installing dependencies...
  "%VPY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo pip install failed.
    pause
    exit /b 1
  )
  echo ok>"venv\.sparse_tags_deps_ok"
)

echo Starting Sparse Tag Browser...
if exist "%VPYW%" (
  start "" "%VPYW%" -m sparse_tags
) else (
  start "" "%VPY%" -m sparse_tags
)
exit /b 0
