#!/usr/bin/env bash
# verify_rom.sh - One-shot verification for GBAtoPy transpiled ROMs
# Usage: ./scripts/verify/verify_rom.sh <rom_basename> [--frame=N] [--no-golden]

set -euo pipefail

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MGBA_PATH="${PROJECT_ROOT}/mgba/build/sdl/mgba"
SCREENSHOT_LUA="${PROJECT_ROOT}/scripts/screenshot/screenshot.lua"
GOLDEN_DIR="${PROJECT_ROOT}/test-reports/goldens"
THRESHOLD_PCT=30
FRAME_COUNT=60
NO_GOLDEN=false
HELP=false

# --- Parse arguments ---
usage() {
    cat <<EOF
Usage: $(basename "$0") <rom_basename> [--frame=N] [--no-golden] [--help]

Automated verification of GBAtoPy transpiled ROMs.

Arguments:
  rom_basename      ROM name without extension (e.g., stripes, helloWorld)

Options:
  --frame=N         Frame count for screenshot (default: 60)
  --no-golden       Skip golden screenshot regeneration if it exists
  --help            Show this help message

Example:
  $(basename "$0") stripes
  $(basename "$0") helloWorld --frame=120 --no-golden

Workflow:
  1. Generates golden screenshot with mGBA (unless --no-golden and golden exists)
  2. Builds transpiler if needed
  3. Transpiles ROM to /tmp/<rom>.py
  4. Runs transpiled Python to generate screenshot
  5. Compares screenshots and reports PASS/FAIL

Exit codes:
  0 - PASS (difference <= threshold)
  1 - FAIL (difference > threshold or error)
EOF
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            HELP=true
            shift
            ;;
        --frame=*)
            FRAME_COUNT="${1#*=}"
            shift
            ;;
        --no-golden)
            NO_GOLDEN=true
            shift
            ;;
        *)
            if [[ -z "${ROM_BASENAME:-}" ]]; then
                ROM_BASENAME="$1"
            else
                echo "Error: Unknown argument: $1" >&2
                usage
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ "$HELP" == true ]]; then
    usage
    exit 0
fi

if [[ -z "${ROM_BASENAME:-}" ]]; then
    echo "Error: ROM basename is required" >&2
    usage
    exit 1
fi

# --- Validation ---

# Check mGBA binary
if [[ ! -x "${MGBA_PATH}" ]]; then
    echo "Error: mGBA binary not found or not executable: ${MGBA_PATH}" >&2
    echo "Build mGBA first: cd mgba && cmake .. && make" >&2
    exit 1
fi

# Check ROM file
ROM_PATH="${PROJECT_ROOT}/test_roms/roms/${ROM_BASENAME}.gba"
if [[ ! -f "${ROM_PATH}" ]]; then
    echo "Error: ROM file not found: ${ROM_PATH}" >&2
    exit 1
fi

# Ensure golden directory exists
mkdir -p "${GOLDEN_DIR}"

GOLDEN_PNG="${GOLDEN_DIR}/${ROM_BASENAME}.png"
TEMP_GOLDEN="/tmp/${ROM_BASENAME}.png"
TEMP_PY="/tmp/${ROM_BASENAME}.py"
TEMP_TRANSPILED_SCREENSHOT="/tmp/${ROM_BASENAME}_transpiled.png"

# --- Generate golden screenshot (if needed) ---
if [[ "$NO_GOLDEN" == true ]] && [[ -f "${GOLDEN_PNG}" ]]; then
    echo "✓ Using existing golden: ${GOLDEN_PNG}"
else
    echo "Generating golden screenshot with mGBA..."
    cd "${PROJECT_ROOT}"
    "${MGBA_PATH}" -S "${SCREENSHOT_LUA}" "${ROM_PATH}"
    
    if [[ ! -f "${TEMP_GOLDEN}" ]]; then
        echo "Error: mGBA did not generate golden screenshot at ${TEMP_GOLDEN}" >&2
        exit 1
    fi
    
    cp "${TEMP_GOLDEN}" "${GOLDEN_PNG}"
    echo "✓ Golden saved: ${GOLDEN_PNG}"
fi

# --- Build transpiler ---
echo "Checking transpiler build..."
cd "${PROJECT_ROOT}"
if ! cargo build --release -p gbatopy-cli --quiet 2>&1 | tail -1; then
    echo "Error: Failed to build transpiler" >&2
    exit 1
fi
echo "✓ Transpiler ready"

# --- Transpile ROM ---
echo "Transpiling ROM..."
cargo run --release -p gbatopy-cli --quiet -- pipeline \
    --rom "${ROM_PATH}" \
    --output "${TEMP_PY}"

if [[ ! -f "${TEMP_PY}" ]]; then
    echo "Error: Transpilation failed - ${TEMP_PY} not created" >&2
    exit 1
fi
echo "✓ Transpiled: ${TEMP_PY}"

# --- Run transpiled Python ---
echo "Running transpiled Python (frame ${FRAME_COUNT})..."
cd /tmp
if ! python3 "${ROM_BASENAME}.py" --headless --frame="${FRAME_COUNT}" --screenshot="${TEMP_TRANSPILED_SCREENSHOT}" 2>&1; then
    echo "Error: Transpiled Python execution failed" >&2
    exit 1
fi

if [[ ! -f "${TEMP_TRANSPILED_SCREENSHOT}" ]]; then
    echo "Error: Transpiled screenshot not generated: ${TEMP_TRANSPILED_SCREENSHOT}" >&2
    exit 1
fi
echo "✓ Transpiled screenshot: ${TEMP_TRANSPILED_SCREENSHOT}"

# --- Compare screenshots ---
echo "Comparing screenshots..."
cd "${PROJECT_ROOT}"
COMPARE_OUTPUT=$(python3 scripts/verify/compare_screenshots.py \
    -s "${GOLDEN_PNG}" \
    "${TEMP_TRANSPILED_SCREENSHOT}" \
    --threshold "${THRESHOLD_PCT}" 2>&1) || true

echo "${COMPARE_OUTPUT}"

# Parse diff percentage from output (assumes format like "Difference: X.X%")
DIFF_PCT=$(echo "${COMPARE_OUTPUT}" | grep -oP '\d+\.?\d*(?=%)' | head -1 || echo "0")

if [[ -z "${DIFF_PCT}" ]]; then
    DIFF_PCT="0"
fi

# Check threshold
DIFF_INT=${DIFF_PCT%.*}  # Integer part for comparison
if [[ "${DIFF_INT}" -le "${THRESHOLD_PCT}" ]]; then
    echo ""
    echo "=========================================="
    echo "PASS: ${ROM_BASENAME} (${DIFF_PCT}% difference, threshold ${THRESHOLD_PCT}%)"
    echo "=========================================="
    exit 0
else
    echo ""
    echo "=========================================="
    echo "FAIL: ${ROM_BASENAME} (${DIFF_PCT}% difference, threshold ${THRESHOLD_PCT}%)"
    echo "=========================================="
    exit 1
fi