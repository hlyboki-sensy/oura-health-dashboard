#!/bin/bash
# Weekly AI coach: fresh data -> rebuild -> new week plan.
# Tries a DEEP plan via headless `claude` (needs a one-time `claude login`),
# otherwise falls back to the deterministic coach_plan.py. Wire to cron/launchd weekly.
cd "$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"
CLAUDE="$(command -v claude || true)"

echo "----- $(date '+%Y-%m-%d %H:%M') -----" >> coach.log
"$PY" oura_export.py --no-heartrate >> coach.log 2>&1 || echo "  (export skipped — using existing data)" >> coach.log
"$PY" build_dashboard.py >> coach.log 2>&1

DEEP=0
if [ -n "$CLAUDE" ]; then
  B=$(stat -f %m next_week_plan.js 2>/dev/null || echo 0)
  ( "$CLAUDE" -p "$(cat coach_prompt.md)" --permission-mode bypassPermissions --add-dir "$(pwd)" >> coach.log 2>&1 ) & CPID=$!
  ( sleep 420; kill "$CPID" 2>/dev/null ) & WPID=$!
  wait "$CPID" 2>/dev/null; kill "$WPID" 2>/dev/null
  A=$(stat -f %m next_week_plan.js 2>/dev/null || echo 0)
  if [ "$A" != "$B" ] && "$PY" -c "t=open('next_week_plan.js').read();import json;s=t.find('{');e=t.rfind('}');json.loads(t[s:e+1])" 2>/dev/null; then
    DEEP=1
  fi
fi
[ "$DEEP" = "1" ] || "$PY" coach_plan.py >> coach.log 2>&1
echo "done ($([ "$DEEP" = 1 ] && echo deep || echo deterministic))" >> coach.log
