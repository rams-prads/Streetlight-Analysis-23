# Starts (or stops) the Urban ERP locally without Docker: API on :8000 (SQLite file with demo data) and the web console on :4200.
# Called by start.bat and stop.bat. Windows PowerShell 5.1 compatible.
#
# What it guarantees, so "it does not open" does not happen again:
#   - the browser opens only after the API and the web console answer;
#   - the API is always restarted, so it never runs old code left over from an earlier session;
#   - a broken Python environment or missing node modules are repaired, not just checked for existence;
#   - an out-of-date local database is rebuilt by the API itself (app/db/dev_schema.py);
#   - every failure ends with a plain message saying what to do, and the window stays open.
param([switch]$Stop, [switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Api = Join-Path $Root 'backend\services\core_service'
$Web = Join-Path $Root 'frontend\urban-console'
$Py = Join-Path $Api '.venv\Scripts\python.exe'
$ApiPort = 8000
$WebPort = 4200
$Log = Join-Path $env:TEMP 'urban-start.log'

function Say([string]$m, [string]$color = 'Gray') { Write-Host $m -ForegroundColor $color }
function Fail([string]$m) { throw $m }

function Test-Url([string]$url) {
    try { return (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { return $false }
}

function Get-Listener([int]$port) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Get-Proc([int]$id) {
    Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
}

# Stops whatever listens on the port, together with the console window and launcher that started it (so no dead window is left behind).
function Stop-Port([int]$port) {
    $l = Get-Listener $port
    if (-not $l) { return }
    $top = Get-Proc $l.OwningProcess
    while ($top -and $top.ParentProcessId) {
        $parent = Get-Proc $top.ParentProcessId
        if ($parent -and $parent.Name -match '^(cmd|python|node|npx)(\.exe)?$' -and $parent.CommandLine -match 'uvicorn|ng(\.js)?\s+serve|npx|\.venv') { $top = $parent } else { break }
    }
    if ($top) { & taskkill.exe /PID $top.ProcessId /T /F 2>&1 | Out-Null }
    for ($i = 0; $i -lt 20 -and (Get-Listener $port); $i++) { Start-Sleep -Milliseconds 500 }
    if (Get-Listener $port) { Fail "Something is still using port $port and could not be stopped. Close it (or restart the computer) and try again." }
}

function Wait-Up([string]$url, [string]$what, [int]$seconds, $proc) {
    $deadline = (Get-Date).AddSeconds($seconds)
    $n = 0
    while ((Get-Date) -lt $deadline) {
        if (Test-Url $url) { return }
        if ($proc -and $proc.HasExited) { Fail "The $what window closed on its own. Read the error in that window (or run start.bat again and watch it)." }
        if ($n % 5 -eq 4) { Say "  still starting $what ..." }
        $n++
        Start-Sleep -Seconds 2
    }
    Fail "The $what did not answer within $seconds seconds. Look at its window for the reason."
}

function Run-Python([string[]]$arguments) {
    # Native errors are checked by exit code, never by stderr text.
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Py @arguments 2>&1 | ForEach-Object { Say "  $_" }; return $LASTEXITCODE } finally { $ErrorActionPreference = $old }
}

try {
    try { Start-Transcript -Path $Log -Force | Out-Null } catch {}

    if ($Stop) {
        Stop-Port $ApiPort
        Stop-Port $WebPort
        Say 'Stopped the API and the web console.' 'Green'
        return
    }

    Say 'Urban ERP - starting locally (no Docker needed)' 'Cyan'
    Say "  API       http://localhost:$ApiPort/docs   (FastAPI on a local SQLite file with demo data)"
    Say "  Console   http://localhost:$WebPort`n"

    # 1. Python environment: present AND working, otherwise (re)built
    $probe = 'import fastapi, uvicorn, aiosqlite, sqlalchemy, pydantic'
    $ready = $false
    if (Test-Path $Py) { $ready = ((Run-Python @('-c', $probe)) -eq 0) }
    if (-not $ready) {
        Say 'Setting up the Python environment (first run, or the old one is broken) - a few minutes...' 'Yellow'
        if (-not (Test-Path $Py)) {
            $made = $false
            foreach ($cmd in @(@('py', '-3.12'), @('py', '-3'), @('python'))) {
                if (Get-Command $cmd[0] -ErrorAction SilentlyContinue) {
                    $extra = @($cmd | Select-Object -Skip 1)
                    & $cmd[0] @extra -m venv (Join-Path $Api '.venv') 2>&1 | Out-Null
                    if (Test-Path $Py) { $made = $true; break }
                }
            }
            if (-not $made) { Fail 'Python 3.12 was not found. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH") and run start.bat again.' }
        }
        if ((Run-Python @('-m', 'pip', 'install', '-r', (Join-Path $Api 'requirements.txt'), 'aiosqlite')) -ne 0) { Fail 'Installing the Python packages failed. Check the internet connection and run start.bat again.' }
        if ((Run-Python @('-c', $probe)) -ne 0) { Fail 'The Python packages are installed but still cannot be loaded. Delete the folder backend\services\core_service\.venv and run start.bat again.' }
    }

    # 2. Node packages
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail 'Node.js was not found. Install the LTS version from https://nodejs.org/ and run start.bat again.' }
    if (-not (Test-Path (Join-Path $Web 'node_modules\.bin\ng.cmd'))) {
        Say 'Installing the web packages (first run) - a few minutes...' 'Yellow'
        Push-Location $Web
        try {
            & cmd.exe /c 'npm ci --no-audit --no-fund' 2>&1 | ForEach-Object { Say "  $_" }
            if ($LASTEXITCODE -ne 0) { & cmd.exe /c 'npm install --no-audit --no-fund' 2>&1 | ForEach-Object { Say "  $_" } }
        } finally { Pop-Location }
        if (-not (Test-Path (Join-Path $Web 'node_modules\.bin\ng.cmd'))) { Fail 'Installing the web packages failed. Check the internet connection and run start.bat again.' }
    }

    # 3. API: always restarted so it runs the code on disk
    if (Get-Listener $ApiPort) { Say "Restarting the API (port $ApiPort was in use)..."; Stop-Port $ApiPort }
    $env:DATABASE_URL = 'sqlite+aiosqlite:///./local-dev.db'
    $apiProc = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $Api -PassThru `
        -ArgumentList '/k', 'title Urban API (port 8000) & .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000'
    Say 'Starting the API and loading demo data (about 30 seconds the first time)...'
    Wait-Up "http://localhost:$ApiPort/health" 'API' 180 $apiProc
    Say '  API is up.' 'Green'

    # 4. Web console: reused when it already answers, otherwise started clean
    if (Test-Url "http://localhost:$WebPort/") {
        Say '  Web console is already running - reusing it.' 'Green'
    } else {
        if (Get-Listener $WebPort) { Say "Port $WebPort is busy but not answering - stopping it."; Stop-Port $WebPort }
        # The dev server's pre-bundled-dependency cache goes stale between runs and then refuses to start; it is rebuilt in seconds.
        Get-ChildItem (Join-Path $Web '.angular\cache') -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $vite = Join-Path $_.FullName 'vite'
                if (Test-Path $vite) { Remove-Item $vite -Recurse -Force -ErrorAction SilentlyContinue }
            }
        }
        $env:NG_CLI_ANALYTICS = 'false'
        $webProc = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $Web -PassThru `
            -ArgumentList '/k', 'title Urban Console (port 4200) & npx ng serve --port 4200'
        Say 'Starting the web console (about a minute the first time)...'
        Wait-Up "http://localhost:$WebPort/" 'web console' 240 $webProc
        Say '  Web console is up.' 'Green'
    }

    Say "`nEverything is running. Open http://localhost:$WebPort" 'Green'
    Say 'To stop it later, run stop.bat (or just close the two windows named "Urban ...").'
    if (-not $NoBrowser) { Start-Process "http://localhost:$WebPort" }
    $code = 0
} catch {
    Say "`nCould not start: $($_.Exception.Message)" 'Red'
    Say "Details were saved in $Log" 'DarkGray'
    $code = 1
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}
exit $code
