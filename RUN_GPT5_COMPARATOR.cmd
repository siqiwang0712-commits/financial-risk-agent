@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_gpt5_comparator_interactive.ps1"
set "exit_code=%ERRORLEVEL%"
if not "%exit_code%"=="0" (
  echo.
  echo GPT-5 comparator did not complete. Exit code: %exit_code%
  pause
)
exit /b %exit_code%
