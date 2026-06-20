#!/bin/bash
# Double-click to launch the dashboard (macOS). Builds, starts the local server, opens the browser.
cd "$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"
"$PY" build_dashboard.py >/dev/null 2>&1
if ! lsof -nP -iTCP:8910 -sTCP:LISTEN >/dev/null 2>&1; then
  nohup "$PY" serve.py >/dev/null 2>&1 &
  sleep 1
fi
open "http://127.0.0.1:8910/"
echo "Dashboard: http://127.0.0.1:8910/  — this window can be closed."
