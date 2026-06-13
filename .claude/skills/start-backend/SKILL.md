---
name: start-backend
description: Start or restart the cEDH Simulator FastAPI backend on port 8000, then verify it is up.
---

Start the FastAPI backend for this project using the following steps:

1. Kill any existing process on port 8000 (best-effort, ignore errors):
   Run: `Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue`

2. Launch uvicorn in the background using PowerShell:
   Working dir: `C:\Users\BanditCoot\Documents\ClaudeCodeProjects\cEDH_Simulator\backend`
   Command: `.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000`
   Use `run_in_background: true`.

3. Wait 3 seconds, then smoke-test with:
   `Invoke-RestMethod http://localhost:8000/health`

4. Report the result:
   - If `status: ok` is returned → "Backend is up at http://localhost:8000"
   - If the request fails → show the error and suggest checking the output file for startup errors
