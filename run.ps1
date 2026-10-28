<#
  Task runner.   Usage:  .\run.ps1 <command>

  setup   create .venv, install Python + npm dependencies, seed DB, build vector store
  seed    rebuild the demo database (dates are relative to today)
  ingest  rebuild the vector store from data/docs
  api     start the backend on http://localhost:8000  (Swagger: /docs)
  web     start the frontend on http://localhost:5173
  test    run the pytest suite
  e2e     run the Playwright end-to-end tests (starts its own servers)
  eval    run the evaluation set -> ai/eval/report.md
  calibrate  print reranker scores to tune RERANK_THRESHOLD
#>
param([Parameter(Position = 0)][string]$Command = "help")

# Note: no $ErrorActionPreference = "Stop" - in Windows PowerShell 5.1 that turns harmless stderr output
# from python/uvicorn (log lines, warnings) into terminating errors.
$Root = $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_PROGRESS_BARS = "1"
$env:TRANSFORMERS_VERBOSITY = "error"
Set-Location $Root

switch ($Command) {
  "setup" {
    if (-not (Test-Path $Py)) { python -m venv .venv }
    & $Py -m pip install -r backend\requirements.txt
    if (-not (Test-Path ".env")) { Copy-Item .env.example .env; Write-Host "Created .env - add your ANTHROPIC_API_KEY (optional)." }
    & $Py -m backend.app.seed --reset
    & $Py -m ai.ingest
    Push-Location frontend; npm install; Pop-Location
  }
  "seed" { & $Py -m backend.app.seed --reset }
  "ingest" { & $Py -m ai.ingest }
  "api" { & $Py -m uvicorn backend.app.main:app --reload --port 8000 }
  "web" { Push-Location frontend; npm run dev; Pop-Location }
  "test" { & $Py -m pytest }
  "e2e" { Push-Location frontend; npm run test:e2e; Pop-Location }
  "eval" { & $Py -m ai.eval.run_eval }
  "calibrate" { & $Py -m ai.eval.calibrate }
  default { Get-Content $PSCommandPath -TotalCount 14 | Select-Object -Skip 1 }
}
