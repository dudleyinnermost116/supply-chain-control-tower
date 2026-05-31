@echo off
REM run_scheduler.bat
REM ================================================================
REM PURPOSE:
REM   Double-click this file to start the Supply Chain scheduler
REM   in a terminal window. The window stays open so you can see
REM   the log output as hooks fire.
REM
REM HOW TO USE:
REM   Option A: Double-click this file in Windows Explorer
REM   Option B: Run from terminal: scripts\run_scheduler.bat
REM
REM HOW TO STOP:
REM   Click on the terminal window and press Ctrl+C
REM   Or just close the terminal window.
REM
REM TO START AUTOMATICALLY WITH WINDOWS:
REM   1. Press Win+R, type: shell:startup, press Enter
REM   2. Copy a shortcut to this .bat file into that folder
REM   3. The scheduler will start every time Windows boots
REM ================================================================

REM Change to the project root directory
REM %~dp0 means "the folder containing this .bat file" (scripts\)
REM .. means "go up one level" (to the project root)
cd /d "%~dp0.."

REM Print a visible header so you know it started
echo ============================================================
echo  Supply Chain Control Tower — Scheduler
echo  Project: %cd%
echo  Time:    %date% %time%
echo ============================================================
echo.
echo Press Ctrl+C to stop the scheduler.
echo.

REM Launch the scheduler using your Python installation
REM If Python is not found, you will see an error here
"C:\Users\preet\AppData\Local\Programs\Python\Python310\python.exe" scripts\scheduler.py

REM If the script exits (error or Ctrl+C), pause so the window stays open
REM and you can read any error messages before the window closes
echo.
echo Scheduler stopped. Press any key to close this window.
pause
