#!/usr/bin/env bash
# Rule AGENTS.md #26: ZERO-SKIP policy. Every ROM must PASS or FAIL, never SKIP.
# Exits non-zero if docs/reference/test-roms.md contains any SKIP entry.
set -euo pipefail

doc="docs/reference/test-roms.md"
[[ -f "$doc" ]] || { echo "FAIL: $doc not found" >&2; exit 1; }

# Parse the status line: "Current status (2026-09-30): 78 PASS, 2 FAIL, ~5 untested"
summary=$(grep -E 'Current status.*PASS.*FAIL' "$doc" | tail -1 || true)
if [[ -z "$summary" ]]; then
    echo "WARN: could not find status line in $doc — skipping SKIP check" >&2
    exit 0
fi

# Check for explicit SKIP mentions (⏰ SKIP or "SKIP" in text)
skip_count=$(echo "$summary" | grep -oE '[0-9]+ ⏰ SKIP' | grep -oE '^[0-9]+' | head -1 || true)
if [[ -z "$skip_count" ]]; then
    # Also check for "SKIP" in the text (case insensitive)
    skip_count=$(echo "$summary" | grep -ioE '\bSKIP\b' | wc -l || true)
    skip_count=$(echo "$skip_count" | tr -d '[:space:]')
fi
skip_count=${skip_count:-0}

if [[ "$skip_count" -gt 0 ]]; then
    echo "FAIL: $skip_count SKIP ROMs in $doc (AGENTS.md rule #26 — ZERO-SKIP policy)" >&2
    echo "Summary: $summary" >&2
    exit 1
fi

echo "OK: 0 SKIP ROMs in $doc."
exit 0
