---
name: start-frontend
description: Start or restart the cEDH Simulator Vite/React frontend on port 5173, then verify it is up.
---

Start the Vite dev server for this project using the following steps:

1. Kill any existing process on port 5173 (best-effort, ignore errors):
   Run: `Stop-Process -Id (Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue`

2. Launch Vite in the background using PowerShell:
   Working dir: `C:\Users\BanditCoot\Documents\ClaudeCodeProjects\cEDH_Simulator\frontend`
   Command: `npm run dev`
   Use `run_in_background: true`.

3. Wait 4 seconds, then smoke-test with:
   `Invoke-WebRequest http://localhost:5173 -UseBasicParsing -TimeoutSec 5`

4. Report the result:
   - If the response status is 200 → "Frontend is up at http://localhost:5173"
   - If the request fails → show the error and suggest checking the terminal output for startup errors
