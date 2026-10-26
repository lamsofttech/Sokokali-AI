# Starts the Sokokali backend and dashboard in two new PowerShell windows, then opens the dashboard.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
# Close the two windows (or press Ctrl+C in them) to stop.

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

if (-not (Test-Path (Join-Path $backend ".venv\Scripts\python.exe"))) {
    Write-Error "Backend virtual environment not found. See README.md > Setup."
    exit 1
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing dashboard dependencies (first run only)..."
    Push-Location $frontend
    npm install
    Pop-Location
}

Start-Process powershell -WorkingDirectory $backend -ArgumentList @(
    "-NoExit", "-Command", ".\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
)
Start-Process powershell -WorkingDirectory $frontend -ArgumentList @("-NoExit", "-Command", "npm run dev")

Start-Sleep -Seconds 5
Start-Process "http://localhost:5173"
