#!/bin/bash
# GBAtoPy CI Visual Test Script
# Runs Level 3 visual comparison for ci-fixtures ROMs
#
# Usage: bash scripts/ci/visual_tests.sh
#
# This script:
# 1. Builds the transpiler
# 2. For each ROM in ci-fixtures/roms/:
#    - Transpiles to /tmp/<romname>.py
#    - Runs headless with screenshot capture
#    - Compares against ci-fixtures/goldens/<romname>_f60.png
# 3. Reports PASS/FAIL for each ROM
# 4. Exits non-zero on any failure

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

# Environment setup for headless mGBA
export SDL_VIDEODRIVER=offscreen
export SDL_AUDIODRIVER=dummy
export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:${LD_LIBRARY_PATH:-}"

ROMS_DIR="$PROJECT_ROOT/ci-fixtures/roms"
GOLDENS_DIR="$PROJECT_ROOT/ci-fixtures/goldens"
COMPARE_SCRIPT="$PROJECT_ROOT/scripts/verify/compare_screenshots.py"

echo "=== GBAtoPy CI Visual Tests ==="
echo "ROMs directory: $ROMS_DIR"
echo "Goldens directory: $GOLDENS_DIR"
echo ""

# Build transpiler
echo "Building transpiler..."
cargo build --release --quiet
echo "Build complete."
echo ""

# Count ROMs
ROM_COUNT=$(ls "$ROMS_DIR"/*.gba 2>/dev/null | wc -l)
if [ "$ROM_COUNT" -eq 0 ]; then
    echo "ERROR: No ROMs found in $ROMS_DIR"
    exit 1
fi
echo "Found $ROM_COUNT ROMs to test"
echo ""

# Track results
PASS_COUNT=0
FAIL_COUNT=0

# Process each ROM
for ROM_PATH in "$ROMS_DIR"/*.gba; do
    ROM_BASENAME=$(basename "$ROM_PATH" .gba)
    GOLDEN_PATH="$GOLDENS_DIR/${ROM_BASENAME}_f60.png"
    OUTPUT_PY="/tmp/${ROM_BASENAME}.py"
    SCREENSHOT_OUT="/tmp/${ROM_BASENAME}_test.png"

    echo "--- Testing $ROM_BASENAME ---"

    # Check if golden exists
    if [ ! -f "$GOLDEN_PATH" ]; then
        echo "  SKIP: No golden screenshot at $GOLDEN_PATH"
        continue
    fi

    # Transpile
    echo "  Transpiling..."
    if ! "$PROJECT_ROOT/target/release/gbatopy-cli" pipeline --rom "$ROM_PATH" --output "$OUTPUT_PY" 2>&1; then
        echo "  FAIL: Transpilation failed"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    # Run with screenshot
    echo "  Running (frame 60)..."
    if ! python3 "$OUTPUT_PY" --headless --frame=60 --screenshot="$SCREENSHOT_OUT" 2>&1; then
        echo "  FAIL: Execution failed"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi

    # Compare screenshots
    echo "  Comparing screenshots..."
    COMPARE_OUTPUT=$(python3 "$COMPARE_SCRIPT" -s "$GOLDEN_PATH" "$SCREENSHOT_OUT" 2>&1)
    COMPARE_STATUS=$(echo "$COMPARE_OUTPUT" | grep -E "^Status:" | head -1 | awk '{print $2}' || echo "UNKNOWN")

    if [ "$COMPARE_STATUS" = "PASS" ]; then
        echo "  PASS: $COMPARE_STATUS"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "  FAIL: $COMPARE_STATUS"
        echo "  Details: $COMPARE_OUTPUT"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi

    echo ""
done

# Summary
echo "=== Visual Test Summary ==="
echo "PASS: $PASS_COUNT"
echo "FAIL: $FAIL_COUNT"
echo "Total: $((PASS_COUNT + FAIL_COUNT))"
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "CI VISUAL TESTS FAILED"
    exit 1
else
    echo "CI VISUAL TESTS PASSED"
    exit 0
fi