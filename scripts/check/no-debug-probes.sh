#!/usr/bin/env bash
# Rule AGENTS.md #14: use built-in debug flags (--pc-trace, --trace-n, --max-instrs).
# Do not inject print(f"PC={...}") probes into pipeline_cmd.rs or runtime templates.
# Exits non-zero if a probe pattern is left in a source file.
set -euo pipefail

patterns=(
    'print(f"PC='
    'print(f"pc='
    'print("PC='
    'print(f"DBG'
    'print(f"DEBUG'
    'print(f"R0='
    'print(f"R6='
    'print(f"VRAM'
    'print(f"DMA'
    'print(f"IRQ'
)

files=(
    crates/gbatopy-cli/src/pipeline_cmd.rs
)

# Also scan runtime templates for stray probes
shopt -s nullglob
for f in crates/gbatopy-cli/assets/gba_runtime/*.py; do
    # Skip test files — probes in tests are fine
    [[ "$f" == *test* ]] && continue
    files+=("$f")
done

violations=0
for f in "${files[@]}"; do
    [[ -f "$f" ]] || continue
    for p in "${patterns[@]}"; do
        # Match non-commented lines only
        while IFS= read -r line_num; do
            [[ -z "$line_num" ]] && continue
            content=$(sed -n "${line_num}p" "$f")
            stripped=$(echo "$content" | sed 's/^[[:space:]]*//')
            case "$stripped" in
                \#*) continue ;;  # skip commented-out probes
                *)
                    echo "FAIL: stray probe '$p' found in $f:$line_num (AGENTS.md rule #14)" >&2
                    echo "  $content" >&2
                    violations=$((violations + 1))
                    ;;
            esac
        done < <(grep -nF "$p" "$f" | cut -d: -f1 || true)
    done
done

if [[ $violations -gt 0 ]]; then
    exit 1
fi

echo "OK: no stray debug probes in source."
exit 0
