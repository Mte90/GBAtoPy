#!/bin/bash
# GBAtoPy Parallel Test Runner - Run all 68 ROM smoke tests in parallel
# Usage: ./scripts/run-parallel-tests.sh [--rom <name>] [--workers <n>]
#        ./scripts/run-parallel-tests.sh [workers]  (backward compat)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ROMS_DIR="$PROJECT_ROOT/test_roms/roms"
OUTPUT_DIR="$PROJECT_ROOT/test-reports/artifacts"
REPORT_DIR="$PROJECT_ROOT/test-reports"

# Number of parallel workers (default: 4)
WORKERS=4

# Parse arguments for --rom and --workers
ROM_SPEC=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --rom)
            ROM_SPEC="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        -*)
            echo "Unknown option: $1"
            exit 1
            ;;
        *)
            # Backward compat: bare numeric positional arg = worker count
            if [[ "$1" =~ ^[0-9]+$ ]]; then
                WORKERS="$1"
            fi
            shift
            ;;
    esac
done

# Create output directories
mkdir -p "$OUTPUT_DIR"
mkdir -p "$REPORT_DIR"

# Build the transpiler once before running tests
GBATOPY_BIN="$PROJECT_ROOT/target/release/gbatopy-cli"
echo "Building gbatopy-cli..."
if ! cargo build --release -p gbatopy-cli; then
    echo "Error: Failed to build gbatopy-cli"
    exit 1
fi
echo "Build complete: $GBATOPY_BIN"
echo ""

# Function to test a single ROM
test_rom() {
    local rom="$1"
    local rom_name=$(basename "$rom" .gba)
    local output_dir="$OUTPUT_DIR/$rom_name"
    local output_py="$output_dir/output.py"
    
    mkdir -p "$output_dir"
    
    # Run transpiler and syntax check
    if "$GBATOPY_BIN" pipeline --rom "$rom" --output "$output_py" 2>/dev/null && \
       python3 -m py_compile "$output_py" 2>/dev/null; then
        echo "PASS:$rom_name"
    else
        echo "FAIL:$rom_name"
    fi
}

export -f test_rom
export OUTPUT_DIR
export GBATOPY_BIN

# Handle --rom parameter (run single ROM)
if [ -n "$ROM_SPEC" ]; then
    # Remove .gba extension if present for matching
    ROM_BASE="${ROM_SPEC%.gba}"
    ROM_FILE="$ROMS_DIR/${ROM_BASE}.gba"
    
    if [ ! -f "$ROM_FILE" ]; then
        echo "Error: ROM not found: $ROM_FILE"
        echo ""
        echo "Available ROMs matching prefix '$ROM_BASE':"
        ls "$ROMS_DIR/${ROM_BASE}*" 2>/dev/null | while read f; do
            echo "  - $(basename "$f")"
        done
        if [ -z "$(ls "$ROMS_DIR/${ROM_BASE}*" 2>/dev/null)" ]; then
            echo "  (none found)"
        fi
        exit 1
    fi
    
    echo "=== GBAtoPy Single ROM Test ==="
    echo "ROM: $ROM_BASE"
    echo "File: $ROM_FILE"
    echo ""
    
    # Run single ROM test
    ROM_NAME="$ROM_BASE"
    TOTAL=1
    PASS=0
    FAIL=0
    START_TIME=$(date +%s)
    
    # Create artifact directory
    ROM_OUTPUT_DIR="$OUTPUT_DIR/$ROM_NAME"
    mkdir -p "$ROM_OUTPUT_DIR"
    OUTPUT_PY="$ROM_OUTPUT_DIR/output.py"
    
    # Run transpiler and syntax check
    echo -n "Testing $ROM_NAME... "
    if "$GBATOPY_BIN" pipeline --rom "$ROM_FILE" --output "$OUTPUT_PY" 2>/dev/null && \
       python3 -m py_compile "$OUTPUT_PY" 2>/dev/null; then
        echo "✓ PASS"
        PASS=1
    else
        echo "✗ FAIL"
        FAIL=1
    fi
    
    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    
    # Summary
    echo ""
    echo "========================================"
    echo "Test Summary"
    echo "========================================"
    echo "Total:   $TOTAL"
    echo "Passed:  $PASS"
    echo "Failed:  $FAIL"
    echo "Time:    ${ELAPSED}s"
    echo "Pass rate: $([ $TOTAL -gt 0 ] && echo $((PASS * 100 / TOTAL)) || echo 0)%"
    echo ""
    
    if [ $FAIL -eq 0 ]; then
        echo "✓ Test passed!"
        exit 0
    else
        echo "✗ Test failed"
        exit 1
    fi
fi

echo "=== GBAtoPy Parallel Smoke Test Runner ==="
echo "ROMs directory: $ROMS_DIR"
echo "Parallel workers: $WORKERS"
echo ""

# Get list of ROMs
ROMS=("$ROMS_DIR"/*.gba)
TOTAL=${#ROMS[@]}

echo "Total ROMs: $TOTAL"
echo ""

# Process ROMs in parallel using xargs
PASS=0
FAIL=0

START_TIME=$(date +%s)

# Run tests in parallel and collect results
results=$(printf '%s\n' "${ROMS[@]}" | xargs -P "$WORKERS" -I {} bash -c 'test_rom "{}"' 2>&1)

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

# Parse results
while IFS= read -r line; do
    if [[ "$line" == PASS:* ]]; then
        rom_name="${line#PASS:}"
        echo "✓ $rom_name"
        PASS=$((PASS + 1))
    elif [[ "$line" == FAIL:* ]]; then
        rom_name="${line#FAIL:}"
        echo "✗ $rom_name"
        FAIL=$((FAIL + 1))
    fi
done <<< "$results"

# Calculate pass rate
if [ $TOTAL -gt 0 ]; then
    PASS_RATE=$((PASS * 100 / TOTAL))
else
    PASS_RATE=0
fi

# Generate reports
echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo "Total:   $TOTAL"
echo "Passed:  $PASS"
echo "Failed:  $FAIL"
echo "Time:    ${ELAPSED}s"
echo "Pass rate: ${PASS_RATE}%"
echo ""

# Text report
TEXT_REPORT="$REPORT_DIR/test-results-parallel.txt"
{
    echo "GBAtoPy Parallel Smoke Test Results"
    echo "Generated: $(date)"
    echo "Workers: $WORKERS"
    echo "========================================"
    echo ""
    echo "Summary:"
    echo "  Total:  $TOTAL"
    echo "  Passed: $PASS"
    echo "  Failed: $FAIL"
    echo "  Time:   ${ELAPSED}s"
    echo "  Rate:   ${PASS_RATE}%"
} > "$TEXT_REPORT"

# JUnit report
JUNIT_FILE="$REPORT_DIR/results-junit-parallel.xml"
{
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo "<testsuites timestamp=\"$(date -Iseconds)\" name=\"gbatopy-smoke-tests\">"
    echo "  <testsuite name=\"gbatopy-smoke\" tests=\"$TOTAL\" failures=\"$FAIL\" errors=\"0\" skipped=\"0\">"
    
    while IFS= read -r line; do
        if [[ "$line" == PASS:* ]]; then
            rom_name="${line#PASS:}"
            echo "    <testcase name=\"$rom_name\" classname=\"smoke\" time=\"0\"/>"
        elif [[ "$line" == FAIL:* ]]; then
            rom_name="${line#FAIL:}"
            echo "    <testcase name=\"$rom_name\" classname=\"smoke\" time=\"0\">"
            echo "      <failure message=\"Test failed\"/>"
            echo "    </testcase>"
        fi
    done <<< "$results"
    
    echo "  </testsuite>"
    echo "</testsuites>"
} > "$JUNIT_FILE"

echo "Reports:"
echo "  Text:  $TEXT_REPORT"
echo "  JUnit: $JUNIT_FILE"
echo ""

if [ $FAIL -eq 0 ]; then
    echo "✓ All tests passed!"
    exit 0
else
    echo "✗ $FAIL test(s) failed"
    exit 1
fi
