#!/usr/bin/env bash
set -u

repo=/home/lucas/crosscoder-recatcher-steering
log="$repo/runs/BBASV_STOP_2026-08-26.log"

{
  echo "[$(date -Iseconds)] Scheduled BBASV stop started"
  for family in dstk codellama; do
    parent="$(pgrep -f "^\.venv/bin/python tools/run_bbasv_v1.py --family ${family}$" | head -n 1 || true)"
    if [[ -z "$parent" ]]; then
      echo "[$(date -Iseconds)] ${family}: runner not found"
      continue
    fi
    children="$(pgrep -P "$parent" || true)"
    if [[ -n "$children" ]]; then
      echo "[$(date -Iseconds)] ${family}: TERM child ${children}"
      kill -TERM $children 2>/dev/null || true
    fi
    echo "[$(date -Iseconds)] ${family}: TERM runner ${parent}"
    kill -TERM "$parent" 2>/dev/null || true
  done
  echo "[$(date -Iseconds)] Scheduled BBASV stop completed"
} >> "$log" 2>&1
