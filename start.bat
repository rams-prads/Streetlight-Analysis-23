@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>nul
if %errorlevel%==0 (
    echo Docker found - starting full stack...
    docker compose up --build
    goto :eof
)

echo Docker not found - starting local development mode:
echo   API       http://localhost:8000/docs  (FastAPI on a local SQLite file with demo data)
echo   Frontend  http://localhost:4200
echo.

set "API=%~dp0backend\services\core_service"
if not exist "%API%\.venv\Scripts\python.exe" (
    echo Creating the Python environment - first run only...
    py -3.12 -m venv "%API%\.venv" 2>nul || python -m venv "%API%\.venv" || goto :fail
    "%API%\.venv\Scripts\python.exe" -m pip install -r "%API%\requirements.txt" aiosqlite || goto :fail
)

rem The API window inherits this variable; the database file is created next to the API on first start.
set "DATABASE_URL=sqlite+aiosqlite:///./local-dev.db"
start "Urban API (port 8000)" /D "%API%" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"

cd frontend\urban-console
if not exist node_modules (
    call npm ci || goto :fail
)
start "" http://localhost:4200
call npm start
goto :eof

:fail
echo Setup failed - see the messages above.
pause
