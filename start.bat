@echo off
setlocal
cd /d "%~dp0"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

rem Docker is used only when it is installed AND its engine is running. Otherwise the local mode needs nothing but Python and Node.
set "USE_DOCKER="
where docker >nul 2>nul && docker info >nul 2>nul && set "USE_DOCKER=1"
if defined USE_DOCKER (
    echo Docker is running - starting the full stack...
    docker compose up --build
    goto :end
)

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1"
if errorlevel 1 (
    echo.
    echo Start-up did not finish. The reason is shown above.
    echo Press any key to close this window.
    pause >nul
    exit /b 1
)
:end
endlocal
