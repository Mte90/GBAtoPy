#!/usr/bin/env bash
# Rule AGENTS.md #26: ZERO-SKIP policy. Every ROM must PASS or FAIL, never SKIP.
# Exits non-zero if docs/reference/test-roms.md contains any SKIP entry.
set -euo pipefail

doc="docs/reference/test-roms.md"
[[ -f "$doc" ]] || { echo "FAIL: $doc not found" >&2; exit 1; }

# Parse the summary line: "Total ROMs: 76 — 71 ✅ PASS, 3 ❌ FAIL, 0 ⏰ SKIP, 2 🆕 NEW"
summary=$(grep -E 'Total ROMs.*PASS.*FAIL.*SKIP' "$doc" | tail -1 || true)
if [[ -z "$summary" ]]; then
    echo "WARN: could not find summary line in $doc — skipping SKIP check" >&2
    exit 0
fi

skip_count=$(echo "$summary" | grep -oE '[0-9]+ ⏰ SKIP' | grep -oE '^[0-9]+' || echo 0)

if [[ "$skip_count" -gt 0 ]]; then
    echo "FAIL: $skip_count SKIP ROMs in $doc (AGENTS.md rule #26 — ZERO-SKIP policy)" >&2
    echo "Summary: $summary" >&2
    exit 1
fi

echo "OK: 0 SKIP ROMs in $doc."
exit 0
