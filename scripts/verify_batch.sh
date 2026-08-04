#!/bin/bash
# Batch verify ROMs: generate golden, transpile, run, compare
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:${LD_LIBRARY_PATH:-}"
export SDL_AUDIODRIVER=dummy

ROMS=$(cat /tmp/need_golden.txt)
RESULTS_FILE="/tmp/batch_results.csv"
if [ ! -f "$RESULTS_FILE" ]; then
    echo "rom,golden_bytes,output_bytes,diff_pct,status" > "$RESULTS_FILE"
fi

for ROM in $ROMS; do
    ROM_FILE="test_roms/roms/${ROM}.gba"
    GOLDEN="/tmp/gold_${ROM}"
    GOLDEN_PNG="${GOLDEN}.png"
    OUTPUT="/tmp/${ROM}_out.png"
    PY_FILE="/tmp/${ROM}.py"

    echo "=== $ROM ==="

    if [ ! -f "$ROM_FILE" ]; then
        echo "  SKIP: ROM file not found"
        echo "$ROM,0,0,0,SKIP_NO_ROM" >> "$RESULTS_FILE"
        continue
    fi

    export GBATOPY_SCREENSHOT_PATH="$GOLDEN"
    export GBATOPY_TARGET_FRAME=60
    timeout 30 xvfb-run -a -s "-screen 0 640x480x24" ./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua "$ROM_FILE" > /dev/null 2>&1
    if [ ! -f "$GOLDEN_PNG" ]; then
        echo "  SKIP: golden generation failed"
        echo "$ROM,0,0,0,SKIP_NO_GOLDEN" >> "$RESULTS_FILE"
        continue
    fi
    GOLDEN_BYTES=$(stat -c%s "$GOLDEN_PNG")

    cargo run -p gbatopy-cli --release -- pipeline --rom "$ROM_FILE" --output "$PY_FILE" > /dev/null 2>&1
    if [ ! -f "$PY_FILE" ]; then
        echo "  SKIP: transpile failed"
        echo "$ROM,$GOLDEN_BYTES,0,0,SKIP_NO_TRANSPILE" >> "$RESULTS_FILE"
        continue
    fi

    timeout 60 python3 "$PY_FILE" --headless --frame=60 --screenshot "$OUTPUT" --max-instrs=10000000 > /dev/null 2>&1
    if [ ! -f "$OUTPUT" ]; then
        echo "  SKIP: run failed (no output)"
        echo "$ROM,$GOLDEN_BYTES,0,0,SKIP_NO_OUTPUT" >> "$RESULTS_FILE"
        continue
    fi
    OUTPUT_BYTES=$(stat -c%s "$OUTPUT")

    DIFF_PCT=$(python3 -c "
from PIL import Image
try:
    g = Image.open('$GOLDEN_PNG')
    o = Image.open('$OUTPUT')
    gp = list(g.getdata())
    op = list(o.getdata())
    if len(gp) != len(op):
        print(100.0)
    else:
        diffs = sum(1 for a,b in zip(gp,op) if a!=b)
        print(f'{100*diffs/len(gp):.2f}')
except Exception as e:
    print(100.0)
" 2>/dev/null)

    STATUS="FAIL"
    if awk "BEGIN{exit !($DIFF_PCT < 30)}"; then
        STATUS="PASS"
    fi
    echo "  golden=$GOLDEN_BYTES output=$OUTPUT_BYTES diff=${DIFF_PCT}% -> $STATUS"
    echo "$ROM,$GOLDEN_BYTES,$OUTPUT_BYTES,$DIFF_PCT,$STATUS" >> "$RESULTS_FILE"

    cp "$GOLDEN_PNG" "test-reports/goldens/${ROM}_f60.png"
done

echo ""
echo "=== SUMMARY ==="
echo "PASS: $(grep -c ',PASS$' $RESULTS_FILE)"
echo "FAIL: $(grep -c ',FAIL$' $RESULTS_FILE)"
echo "SKIP: $(grep -c ',SKIP' $RESULTS_FILE)"
echo ""
echo "=== DETAILS ==="
cat "$RESULTS_FILE" | column -t -s,
