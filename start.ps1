# Start the Airline Twin dashboard: FastAPI backend (port 8000) + Next.js web app (port 3000).
#   .\start.bat          (or: powershell -ExecutionPolicy Bypass -File start.ps1)
# Needs: MongoDB running, the pipeline run once (python run_pipeline.py --data data/1m),
# .venv with requirements.txt installed, Node.js 20+.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

function Fail($msg) { Write-Host "  x $msg" -ForegroundColor Red; Read-Host "Press Enter to close"; exit 1 }
Write-Host "Airline Twin - simulation and analytics (not a real flight-control system)" -ForegroundColor Cyan

# 1. MongoDB
if (-not (Test-NetConnection localhost -Port 27017 -WarningAction SilentlyContinue).TcpTestSucceeded) {
    $svc = Get-Service MongoDB -ErrorAction SilentlyContinue
    if ($svc) { Write-Host "  starting MongoDB service..."; Start-Service MongoDB } else { Fail "MongoDB is not running on localhost:27017" }
}
Write-Host "  ok MongoDB"

# 2. Python environment + simulator parameters
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Fail "no .venv - run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt" }
& $py -c "import fastapi, uvicorn, pymongo" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "  installing Python requirements..."; & $py -m pip install -q -r requirements.txt }
$n = & $py -c "from pymongo import MongoClient; print(MongoClient().airline_twin.sim_params.count_documents({}))"
if ([int]$n -eq 0) { Fail "sim_params is empty - run first: .venv\Scripts\python run_pipeline.py --data data/1m" }
Write-Host "  ok Python, sim_params ($n documents)"

# 3. Node / web dependencies
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "Node.js not found - install Node.js LTS" }
if (-not (Test-Path (Join-Path $root "web\node_modules"))) { Write-Host "  installing web dependencies (npm install)..."; Push-Location web; npm install; Pop-Location }
Write-Host "  ok Node $(node -v)"

# 4. Already running? Just open it.
$api = (Test-NetConnection localhost -Port 8000 -WarningAction SilentlyContinue).TcpTestSucceeded
$web = (Test-NetConnection localhost -Port 3000 -WarningAction SilentlyContinue).TcpTestSucceeded
if ($api -and $web) {
    Write-Host "  API and web app are already running." -ForegroundColor Green
    Start-Process "http://localhost:3000"
    exit 0
}
if ($api -or $web) { Fail "port $(if ($api) {'8000'} else {'3000'}) is busy but the other server is not running - close the old window and retry" }

# 5. Launch both servers in their own windows
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='Airline Twin API :8000'; Set-Location '$root'; & '$py' -m uvicorn backend.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='Airline Twin web :3000'; Set-Location '$root\web'; npm run dev"

Write-Host "  waiting for the web app (first compile takes ~30 s)..."
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep 2
    try { if ((Invoke-WebRequest "http://localhost:3000" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) { break } } catch {}
}
Start-Process "http://localhost:3000"
Write-Host "Dashboard: http://localhost:3000    API docs: http://127.0.0.1:8000/docs" -ForegroundColor Green
