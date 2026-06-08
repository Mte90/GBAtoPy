#!/bin/bash
# Quick transpiler test - compile once, test all ROMs

set -e
cd /home/archimede/Desktop/projects/GBAtoPy

echo "Building release binary..."
cargo build --release -p gbatopy-cli 2>&1 | tail -3

BINARY="./target/release/gbatopy-cli"
ROMS_DIR="test_roms/roms"
PASSED=0
FAILED=0

echo -e "\nTesting ROMs..."
for rom in $ROMS_DIR/*.gba; do
    name=$(basename "$rom")
    output="/tmp/test_${name%.gba}.py"
    
    # Transpile
    if $BINARY pipeline --rom "$rom" --output "$output" 2>/dev/null; then
        # Verify syntax
        if python3 -m py_compile "$output" 2>/dev/null; then
            echo "✓ $name"
            ((PASSED++))
        else
            echo "✗ $name: syntax error"
            ((FAILED++))
        fi
    else
        echo "✗ $name: transpile failed"
        ((FAILED++))
    fi
    rm -f "$output"
done

echo -e "\n================================"
echo "Passed: $PASSED/$((PASSED+FAILED))"
echo "Failed: $FAILED"
exit $FAILED
