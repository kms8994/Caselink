$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$frontend = Join-Path $root "frontend"

if (-not (Test-Path $python)) {
  throw "Python virtual environment not found: $python"
}

$backendJob = Start-Job -Name "caselink-backend" -ArgumentList $root, $python -ScriptBlock {
  param($root, $python)
  Set-Location $root
  & $python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
}

$frontendJob = Start-Job -Name "caselink-frontend" -ArgumentList $frontend -ScriptBlock {
  param($frontend)
  Set-Location $frontend
  & node server.mjs
}

Write-Host "Caselink backend:  http://127.0.0.1:8001/api/health"
Write-Host "Caselink frontend: http://127.0.0.1:4173"
Write-Host "Press Ctrl+C to stop both servers."

try {
  while ($true) {
    Receive-Job $backendJob, $frontendJob
    Start-Sleep -Seconds 1
  }
} finally {
  Stop-Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
  Remove-Job $backendJob, $frontendJob -Force -ErrorAction SilentlyContinue
}
