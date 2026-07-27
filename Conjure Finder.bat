@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Conjure Finder

REM Double-click "Conjure Finder.vbs" (preferred) or this .bat file.
REM Optional: Conjure Finder.bat --setup-only

set "SETUP_ONLY=0"
if /I "%~1"=="--setup-only" set "SETUP_ONLY=1"

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
  echo Enable "Add python.exe to PATH" and "tcl/tk", then try again.
  pause
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo [1/2] Creating virtualenv...
  %PY% -m venv venv
  if errorlevel 1 (
    echo Failed to create venv.
    pause
    exit /b 1
  )
)

set "VPY=%CD%\venv\Scripts\python.exe"
set "VPIP=%CD%\venv\Scripts\pip.exe"
set "VPYW=%CD%\venv\Scripts\pythonw.exe"

if not exist "venv\.conjure_finder_deps_ok" (
  echo [2/2] Installing dependencies ^(first run^)...
  "%VPIP%" install -r requirements.txt
  if errorlevel 1 (
    echo pip install failed.
    pause
    exit /b 1
  )
  echo ok>"venv\.conjure_finder_deps_ok"
)

if "%SETUP_ONLY%"=="1" exit /b 0

echo Starting Conjure Finder...
if exist "%VPYW%" (
  start "" "%VPYW%" -m conjure_finder
) else (
  start "" "%VPY%" -m conjure_finder
)
exit /b 0
