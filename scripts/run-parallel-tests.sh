#!/bin/bash
# GBAtoPy Parallel Test Runner - Run all 68 ROM smoke tests in parallel
# Usage: ./scripts/run-parallel-tests.sh [workers]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ROMS_DIR="$PROJECT_ROOT/test_roms/roms"
OUTPUT_DIR="$PROJECT_ROOT/test-reports/artifacts"
REPORT_DIR="$PROJECT_ROOT/test-reports"

# Number of parallel workers (default: 4)
WORKERS=${1:-4}

# Create output directories
mkdir -p "$OUTPUT_DIR"
mkdir -p "$REPORT_DIR"

# Initialize counters file
COUNTER_FILE=$(mktemp)
echo "0 0 0" > "$COUNTER_FILE"  # passed failed total

# Function to test a single ROM
test_rom() {
    local rom="$1"
    local rom_name=$(basename "$rom" .gba)
    local output_dir="$OUTPUT_DIR/$rom_name"
    local output_py="$output_dir/output.py"
    
    mkdir -p "$output_dir"
    
    # Run transpiler and syntax check
    if cargo run -p gbatopy-cli --quiet -- pipeline --rom "$rom" --output "$output_py" 2>/dev/null && \
       python3 -m py_compile "$output_py" 2>/dev/null; then
        echo "PASS:$rom_name"
    else
        echo "FAIL:$rom_name"
    fi
}

export -f test_rom
export OUTPUT_DIR

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
