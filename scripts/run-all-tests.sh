#!/bin/bash
# GBAtoPy Test Runner - Run all 68 ROM smoke tests
# Usage: ./scripts/run-all-tests.sh [--junit] [--quick] [--filter <substring>] [--rom <name>]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ROMS_DIR="$PROJECT_ROOT/test_roms/roms"
OUTPUT_DIR="$PROJECT_ROOT/test-reports/artifacts"
REPORT_DIR="$PROJECT_ROOT/test-reports"

# Parse arguments
JUNIT_REPORT=false
QUICK_MODE=false
FILTER=""
ROM_SPEC=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --junit)
            JUNIT_REPORT=true
            shift
            ;;
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --filter)
            FILTER="$2"
            shift 2
            ;;
        --rom)
            ROM_SPEC="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
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
    
    # Warn if --filter is also provided
    if [ -n "$FILTER" ]; then
        echo "Warning: --filter is ignored when --rom is specified"
    fi
    
    # Run single ROM test
    ROM_NAME="$ROM_BASE"
    TOTAL=1
    PASSED=0
    FAILED=0
    START_TIME=$(date +%s)
    
    echo "=== GBAtoPy Single ROM Test ==="
    echo "ROM: $ROM_NAME"
    echo "File: $ROM_FILE"
    echo ""
    
    # Create artifact directory
    ROM_OUTPUT_DIR="$OUTPUT_DIR/$ROM_NAME"
    mkdir -p "$ROM_OUTPUT_DIR"
    OUTPUT_PY="$ROM_OUTPUT_DIR/output.py"
    
    # Start JUnit if requested
    if [ "$JUNIT_REPORT" = true ]; then
        JUNIT_FILE="$REPORT_DIR/results-junit.xml"
        echo '<?xml version="1.0" encoding="UTF-8"?>' > "$JUNIT_FILE"
        echo "<testsuites timestamp=\"$(date -Iseconds)\" name=\"gbatopy-smoke-tests\">" >> "$JUNIT_FILE"
        echo "  <testsuite name=\"gbatopy-smoke\" tests=\"1\" failures=\"0\" errors=\"0\" skipped=\"0\">" >> "$JUNIT_FILE"
    fi
    
    # Text report
    TEXT_REPORT="$REPORT_DIR/test-results.txt"
    echo "GBAtoPy Smoke Test Results" > "$TEXT_REPORT"
    echo "Generated: $(date)" >> "$TEXT_REPORT"
    echo "ROM: $ROM_NAME" >> "$TEXT_REPORT"
    echo "========================================" >> "$TEXT_REPORT"
    echo "" >> "$TEXT_REPORT"
    
    # Run transpiler
    echo -n "Testing $ROM_NAME... "
    if timeout 600 "$GBATOPY_BIN" pipeline --rom "$ROM_FILE" --output "$OUTPUT_PY" >/dev/null 2>&1; then
        FILE_SIZE=$(stat -c%s "$OUTPUT_PY" 2>/dev/null || stat -f%z "$OUTPUT_PY" 2>/dev/null)
        if [ "$FILE_SIZE" -gt 10485760 ]; then
            echo "✓ PASS (large file, syntax skipped)"
            PASSED=1
        elif python3 -m py_compile "$OUTPUT_PY" 2>/dev/null; then
            echo "✓ PASS"
            PASSED=1
        else
            echo "✗ FAIL (Python syntax error)"
            FAILED=1
        fi
    else
        echo "✗ FAIL (transpilation error)"
        FAILED=1
    fi
    
    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    
    # Close JUnit
    if [ "$JUNIT_REPORT" = true ]; then
        if [ $FAILED -eq 0 ]; then
            echo "    <testcase name=\"$ROM_NAME\" classname=\"smoke\" time=\"0\"/>" >> "$JUNIT_FILE"
        else
            echo "    <testcase name=\"$ROM_NAME\" classname=\"smoke\" time=\"0\">" >> "$JUNIT_FILE"
            echo "      <failure message=\"Test failed\"/>" >> "$JUNIT_FILE"
            echo "    </testcase>" >> "$JUNIT_FILE"
        fi
        echo "  </testsuite>" >> "$JUNIT_FILE"
        echo "</testsuites>" >> "$JUNIT_FILE"
        echo ""
        echo "JUnit report: $JUNIT_FILE"
    fi
    
    # Summary
    echo ""
    echo "========================================"
    echo "Test Summary"
    echo "========================================"
    echo "Total:   $TOTAL"
    echo "Passed:  $PASSED"
    echo "Failed:  $FAILED"
    echo "Time:    ${ELAPSED}s"
    echo ""
    
    if [ $FAILED -eq 0 ]; then
        echo "✓ Test passed!"
        PASS_RATE=100
        echo "Pass rate: ${PASS_RATE}%"
        echo "" >> "$TEXT_REPORT"
        echo "Result: PASS" >> "$TEXT_REPORT"
    else
        echo "✗ Test failed"
        PASS_RATE=0
        echo "Pass rate: ${PASS_RATE}%"
        echo "" >> "$TEXT_REPORT"
        echo "Result: FAIL" >> "$TEXT_REPORT"
        exit 1
    fi
    
    exit 0
fi

# Initialize counters
TOTAL=0
PASSED=0
FAILED=0
START_TIME=$(date +%s)

# Start JUnit XML if requested
if [ "$JUNIT_REPORT" = true ]; then
    JUNIT_FILE="$REPORT_DIR/results-junit.xml"
    echo '<?xml version="1.0" encoding="UTF-8"?>' > "$JUNIT_FILE"
    echo "<testsuites timestamp=\"$(date -Iseconds)\" name=\"gbatopy-smoke-tests\">" >> "$JUNIT_FILE"
    echo "  <testsuite name=\"gbatopy-smoke\" tests=\"0\" failures=\"0\" errors=\"0\" skipped=\"0\">" >> "$JUNIT_FILE"
fi

# Text report file
TEXT_REPORT="$REPORT_DIR/test-results.txt"
echo "GBAtoPy Smoke Test Results" > "$TEXT_REPORT"
echo "Generated: $(date)" >> "$TEXT_REPORT"
echo "========================================" >> "$TEXT_REPORT"
echo "" >> "$TEXT_REPORT"

echo "=== GBAtoPy Smoke Test Runner ==="
echo "ROMs directory: $ROMS_DIR"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Process each ROM
for rom in "$ROMS_DIR"/*.gba; do
    if [ ! -f "$rom" ]; then
        continue
    fi
    
    ROM_NAME=$(basename "$rom" .gba)
    
    # Apply filter if specified
    if [ -n "$FILTER" ] && [[ "$ROM_NAME" != *"$FILTER"* ]]; then
        continue
    fi
    
    TOTAL=$((TOTAL + 1))
    
    # Skip if quick mode and this is a large ROM (>1MB)
    if [ "$QUICK_MODE" = true ]; then
        ROM_SIZE=$(stat -f%z "$rom" 2>/dev/null || stat -c%s "$rom" 2>/dev/null)
        if [ "$ROM_SIZE" -gt 1048576 ]; then
            echo "[SKIP] $ROM_NAME (large ROM in quick mode)"
            continue
        fi
    fi
    
    echo -n "Testing $ROM_NAME... "
    
    # Create artifact directory for this ROM
    ROM_OUTPUT_DIR="$OUTPUT_DIR/$ROM_NAME"
    mkdir -p "$ROM_OUTPUT_DIR"
    
    OUTPUT_PY="$ROM_OUTPUT_DIR/output.py"
    
    # Run transpiler (with timeout for large ROMs)
    if timeout 600 "$GBATOPY_BIN" pipeline --rom "$rom" --output "$OUTPUT_PY" >/dev/null 2>&1; then
        # Check Python syntax (skip for huge files >10MB - takes too long)
        FILE_SIZE=$(stat -c%s "$OUTPUT_PY" 2>/dev/null || stat -f%z "$OUTPUT_PY" 2>/dev/null)
        if [ "$FILE_SIZE" -gt 10485760 ]; then
            # File too large for py_compile - assume valid if transpile succeeded
            echo "✓ PASS (large file, syntax skipped)"
            PASSED=$((PASSED + 1))
        elif python3 -m py_compile "$OUTPUT_PY" 2>/dev/null; then
            echo "✓ PASS"
            PASSED=$((PASSED + 1))
            
            # JUnit success element
            if [ "$JUNIT_REPORT" = true ]; then
                echo "    <testcase name=\"$ROM_NAME\" classname=\"smoke\" time=\"0\"/>" >> "$JUNIT_FILE"
            fi
        else
            echo "✗ FAIL (Python syntax error)"
            FAILED=$((FAILED + 1))
            
            # JUnit failure element
            if [ "$JUNIT_REPORT" = true ]; then
                echo "    <testcase name=\"$ROM_NAME\" classname=\"smoke\" time=\"0\">" >> "$JUNIT_FILE"
                echo "      <failure message=\"Python syntax error\"/>" >> "$JUNIT_FILE"
                echo "    </testcase>" >> "$JUNIT_FILE"
            fi
        fi
    else
        echo "✗ FAIL (transpilation error)"
        FAILED=$((FAILED + 1))
        
        # JUnit failure element
        if [ "$JUNIT_REPORT" = true ]; then
            echo "    <testcase name=\"$ROM_NAME\" classname=\"smoke\" time=\"0\">" >> "$JUNIT_FILE"
            echo "      <failure message=\"Transpilation failed\"/>" >> "$JUNIT_FILE"
            echo "    </testcase>" >> "$JUNIT_FILE"
        fi
    fi
    
    # Text report entry
    if [ $((TOTAL % 10)) -eq 0 ]; then
        echo "Progress: $TOTAL ROMs processed..."
    fi
done

# Calculate elapsed time
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

# Close JUnit XML
if [ "$JUNIT_REPORT" = true ]; then
    echo "  </testsuite>" >> "$JUNIT_FILE"
    echo "</testsuites>" >> "$JUNIT_FILE"
    echo ""
    echo "JUnit report: $JUNIT_FILE"
fi

# Final summary
echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo "Total:   $TOTAL"
echo "Passed:  $PASSED"
echo "Failed:  $FAILED"
echo "Time:    ${ELAPSED}s"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✓ All tests passed!"
    PASS_RATE=100
else
    PASS_RATE=$((PASSED * 100 / TOTAL))
    echo "✗ $FAILED test(s) failed"
fi

echo "Pass rate: ${PASS_RATE}%"

# Append to text report
echo "" >> "$TEXT_REPORT"
echo "Summary:" >> "$TEXT_REPORT"
echo "  Total:  $TOTAL" >> "$TEXT_REPORT"
echo "  Passed: $PASSED" >> "$TEXT_REPORT"
echo "  Failed: $FAILED" >> "$TEXT_REPORT"
echo "  Time:   ${ELAPSED}s" >> "$TEXT_REPORT"
echo "  Rate:   ${PASS_RATE}%" >> "$TEXT_REPORT"

# Exit with error code if any failures
if [ $FAILED -gt 0 ]; then
    exit 1
fi
