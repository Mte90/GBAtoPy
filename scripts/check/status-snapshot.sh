#!/usr/bin/env bash
# Rule AGENTS.md #0a / #26: print current PASS/FAIL/SKIP/NEW counts at session start.
# This is a read-only snapshot — does not enforce, only reports.
# Run at session start: bash scripts/check/status-snapshot.sh
set -euo pipefail

doc="docs/reference/test-roms.md"
[[ -f "$doc" ]] || { echo "FAIL: $doc not found" >&2; exit 1; }

# Parse: "Current status (2026-09-30): 78 PASS, 2 FAIL, ~5 untested"
summary=$(grep -E 'Current status.*PASS.*FAIL' "$doc" | tail -1 || true)
if [[ -z "$summary" ]]; then
    echo "WARN: could not find status line in $doc" >&2
    exit 0
fi

pass=$(echo "$summary" | grep -oE '[0-9]+ PASS' | grep -oE '^[0-9]+' || echo 0)
fail=$(echo "$summary" | grep -oE '[0-9]+ FAIL' | grep -oE '^[0-9]+' || echo 0)
skip=0  # Current format doesn't use SKIP marker
new=0   # Current format doesn't use NEW marker

total=$((pass + fail + skip + new))
cat <<EOF
=== GBAtoPy Status Snapshot ===
PASS: $pass
FAIL: $fail
SKIP: $skip   $( [[ $skip -gt 0 ]] && echo "← VIOLATION of zero-SKIP policy (rule #26)" )
NEW:  $new
Total: $total
==============================
EOF

if [[ $skip -gt 0 ]]; then
    echo "WARNING: SKIP ROMs present. Treat each as FAIL (rule #26)." >&2
fi
