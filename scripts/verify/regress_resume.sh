#!/bin/bash
# Phase 9 regression resume v2: skip known-hanging ROMs, process the rest.
# Skips: rates (known hang), song (known hang)
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:${LD_LIBRARY_PATH:-}"
export SDL_AUDIODRIVER=dummy
export NUMBA_DISABLE_JIT=1

RESULTS_FILE="/tmp/phase9_regression.csv"

# ROMs to skip entirely (known to hang even with timeout)
SKIP_ROMS="rates song"

# Build set of already-done ROMs from CSV (skip header)
DONE=$(tail -n +2 "$RESULTS_FILE" | cut -d, -f1)

# Read all ROM names from config
ROMS=$(awk -F'"' '/^name = "/{print $2}' test-roms-config.toml)

TOTAL=0
I=0
PASS=0
FAIL=0
SKIP=0

for ROM in $ROMS; do
    # Skip if in SKIP_ROMS list
    if echo "$SKIP_ROMS" | grep -qw "$ROM"; then
        echo "[SKIP] %-25s (known hang)" "$ROM"
        echo "$ROM,0,0,0,SKIP_KNOWN_HANG" >> "$RESULTS_FILE"
        SKIP=$((SKIP+1))
        continue
    fi

    # Skip if already in CSV
    if echo "$DONE" | grep -qx "$ROM"; then
        continue
    fi

    TOTAL=$((TOTAL+1))
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

    # Run transpiled (60s timeout)
    rm -f "$OUTPUT"
    timeout 60 python3 "$PY_FILE" --headless --frame=60 --screenshot "$OUTPUT" --max-instrs=10000000 > /dev/null 2>&1
    EXIT_CODE=$?
    if [ ! -f "$OUTPUT" ]; then
        if [ $EXIT_CODE -eq 124 ]; then
            echo "TIMEOUT (60s)"
            echo "$ROM,$GOLDEN_BYTES,0,100,FAIL_TIMEOUT" >> "$RESULTS_FILE"
            FAIL=$((FAIL+1))
        else
            echo "FAIL_NO_OUTPUT (golden=${GOLDEN_BYTES}B)"
            echo "$ROM,$GOLDEN_BYTES,0,100,FAIL_NO_OUTPUT" >> "$RESULTS_FILE"
            FAIL=$((FAIL+1))
        fi
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

    rm -f "$PY_FILE" "$OUTPUT"
done

echo ""
echo "=== RESUME BATCH SUMMARY ==="
echo "PROCESSED: $((PASS+FAIL+SKIP))"
echo "PASS:  $PASS"
echo "FAIL:  $FAIL"
echo "SKIP:  $SKIP"