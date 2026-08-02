#!/bin/bash
# Surfaces work-tracking state at session start so governance is enforced
# (it fires) rather than only documented. Profile auto-detected from layout.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 0
if [ -d "$ROOT/docs/sprints" ]; then
  echo "-- governance (multi-agent) --"
  sprint=$(ls -1 "$ROOT"/docs/sprints/SPRINT_*.md 2>/dev/null | sort -V | tail -1)
  if [ -n "$sprint" ]; then
    echo "active sprint: $(basename "$sprint")"
    grep -nE '\[[ /]\]' "$sprint" 2>/dev/null | head -10 | sed 's/^/  /'
  fi
  [ -f "$ROOT/claims.md" ] && { echo "open claims:"; grep -iE 'in progress|\[/\]' "$ROOT/claims.md" 2>/dev/null | head -8 | sed 's/^/  /'; }
  echo "start: claim in claims.md + flip checkbox to [/]. finish: [x] + handoff in docs/handoffs/log/."
elif [ -f "$ROOT/WORKLOG.md" ]; then
  echo "-- worklog (solo) --"
  echo "recent:"; grep -E '^## ' "$ROOT/WORKLOG.md" 2>/dev/null | tail -3 | sed 's/^/  /'
  [ -f "$ROOT/ROADMAP.md" ] && { echo "surfaced this session (ROADMAP):"; awk '/Surfaced this session/{f=1;next} /^## /{f=0} f' "$ROOT/ROADMAP.md" 2>/dev/null | grep -E '\S' | head -5 | sed 's/^/  /'; }
  echo "before finishing: append a dated entry to WORKLOG.md."
fi
exit 0
