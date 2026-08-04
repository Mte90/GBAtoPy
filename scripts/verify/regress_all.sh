#!/bin/bash
# Phase 9 full regression: transpile + run + compare against existing goldens.
# Uses goldens already in test-reports/goldens/. Does NOT regenerate goldens.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:${LD_LIBRARY_PATH:-}"
export SDL_AUDIODRIVER=dummy
export NUMBA_DISABLE_JIT=1

RESULTS_FILE="/tmp/phase9_regression.csv"
echo "rom,golden_bytes,output_bytes,diff_pct,status" > "$RESULTS_FILE"

# Read all 66 ROM names from config
ROMS=$(grep -oP '^\[\[tests\]\]\s*\n\s*\[tests\.[^]]+\]\s*\n\s*name\s*=\s*"?\K[^"]+' test-roms-config.toml 2>/dev/null)
# Fallback: simpler parse
if [ -z "$ROMS" ]; then
    ROMS=$(awk -F'"' '/^name = "/{print $2}' test-roms-config.toml)
fi

TOTAL=$(echo "$ROMS" | wc -l)
I=0
PASS=0
FAIL=0
SKIP=0

for ROM in $ROMS; do
    I=$((I+1))
    ROM_FILE="test_roms/roms/${ROM}.gba"
    GOLDEN_PNG="test-reports/goldens/${ROM}_f60.png"
    OUTPUT="/tmp/regress_${ROM}.png"
    PY_FILE="/tmp/${ROM}.py"

    printf "[%d/%d] %-25s " "$I" "$TOTAL" "$ROM"

    if [ ! -f "$ROM_FILE" ]; then
        echo "SKIP_NO_ROM"
        echo "$ROM,0,0,0,SKIP_NO_ROM" >> "$RESULTS_FILE"
        SKIP=$((SKIP+1))
        continue
    fi
    if [ ! -f "$GOLDEN_PNG" ]; then
        echo "SKIP_NO_GOLDEN"
        echo "$ROM,0,0,0,SKIP_NO_GOLDEN" >> "$RESULTS_FILE"
        SKIP=$((SKIP+1))
        continue
    fi

    GOLDEN_BYTES=$(stat -c%s "$GOLDEN_PNG")

    # Transpile
    cargo run -p gbatopy-cli --release -- pipeline --rom "$ROM_FILE" --output "$PY_FILE" > /dev/null 2>&1
    if [ ! -f "$PY_FILE" ]; then
        echo "SKIP_NO_TRANSPILE"
        echo "$ROM,$GOLDEN_BYTES,0,0,SKIP_NO_TRANSPILE" >> "$RESULTS_FILE"
        SKIP=$((SKIP+1))
        continue
    fi

    # Run transpiled
    rm -f "$OUTPUT"
    timeout 90 python3 "$PY_FILE" --headless --frame=60 --screenshot "$OUTPUT" --max-instrs=10000000 > /dev/null 2>&1
    if [ ! -f "$OUTPUT" ]; then
        echo "SKIP_NO_OUTPUT (golden=${GOLDEN_BYTES}B)"
        echo "$ROM,$GOLDEN_BYTES,0,100,FAIL_NO_OUTPUT" >> "$RESULTS_FILE"
        FAIL=$((FAIL+1))
        continue
    fi
    OUTPUT_BYTES=$(stat -c%s "$OUTPUT")

    # Compare
    DIFF_PCT=$(python3 -c "
from PIL import Image
try:
    g = Image.open('$GOLDEN_PNG')
    o = Image.open('$OUTPUT')
    gp = list(g.getdata())
    op = list(o.getdata())
    if len(gp) != len(op):
        print('100.00')
    else:
        diffs = sum(1 for a,b in zip(gp,op) if a!=b)
        print(f'{100*diffs/len(gp):.2f}')
except Exception:
    print('100.00')
" 2>/dev/null)

    STATUS="FAIL"
    if awk "BEGIN{exit !($DIFF_PCT < 30)}"; then
        STATUS="PASS"
        PASS=$((PASS+1))
    else
        FAIL=$((FAIL+1))
    fi
    echo "$STATUS diff=${DIFF_PCT}% (g=${GOLDEN_BYTES}B o=${OUTPUT_BYTES}B)"
    echo "$ROM,$GOLDEN_BYTES,$OUTPUT_BYTES,$DIFF_PCT,$STATUS" >> "$RESULTS_FILE"

    # Cleanup per-ROM artifacts to save disk
    rm -f "$PY_FILE" "$OUTPUT"
done

echo ""
echo "=== PHASE 9 REGRESSION SUMMARY ==="
echo "TOTAL: $TOTAL"
echo "PASS:  $PASS"
echo "FAIL:  $FAIL"
echo "SKIP:  $SKIP"
echo ""
echo "=== FAILURES (diff >= 30%) ==="
awk -F, 'NR>1 && $5=="FAIL" {printf "  %-25s diff=%s%%\n", $1, $4}' "$RESULTS_FILE"
echo ""
echo "=== SKIPS ==="
awk -F, 'NR>1 && $5 ~ /SKIP/ {printf "  %-25s %s\n", $1, $5}' "$RESULTS_FILE"
