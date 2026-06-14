---
name: start-app
description: Start or restart both the cEDH Simulator FastAPI backend (port 8000) and Vite/React frontend (port 5173), then verify both are up.
---

Start the full app (backend + frontend) using the following steps:

## 1. Kill existing processes on both ports (best-effort, ignore errors)

Run both in parallel:
- `Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue`
- `Stop-Process -Id (Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue`

## 2. Apply database migrations

Run in the backend directory `C:\Users\ARSR\ClaudeCode\BantWalk\cEDH_Simulator\backend`:

```
.venv\Scripts\alembic.exe upgrade head
```

- If it succeeds (exit 0) → continue
- If it fails → show the error output and stop; do not start the servers

## 3. Launch both servers in the background

Run both in parallel with `run_in_background: true`:

**Backend:**
- Working dir: `C:\Users\ARSR\ClaudeCode\BantWalk\cEDH_Simulator\backend`
- Command: `.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000`

**Frontend:**
- Working dir: `C:\Users\ARSR\ClaudeCode\BantWalk\cEDH_Simulator\frontend`
- Command: `npm run dev`

## 4. Wait 4 seconds, then smoke-test both

Run both checks in parallel:
- Backend: `Invoke-RestMethod http://localhost:8000/health`
- Frontend: `Invoke-WebRequest http://localhost:5173 -UseBasicParsing -TimeoutSec 5`

## 5. Report results

- Backend `status: ok` → "Backend is up at http://localhost:8000"
- Frontend HTTP 200 → "Frontend is up at http://localhost:5173"
- Any failure → show the error and suggest checking terminal output for startup errors
