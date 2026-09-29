#!/bin/bash
# Export basic block boundaries from a GBA ROM
# Usage: ghidra_blocks.sh <rom_name>
#
# Note: Requires Ghidra GUI for full functionality

# Auto-detect project root (two levels up from script location)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ROM_NAME="$1"
ROM_FILE="${PROJECT_ROOT}/test_roms/roms/${ROM_NAME}.gba"

if [ -z "$ROM_NAME" ]; then
    echo "Usage: $0 <rom_name>"
    exit 1
fi

if [ ! -f "$ROM_FILE" ]; then
    echo "Error: ROM file not found: $ROM_FILE"
    exit 1
fi

echo "Basic block analysis requires Ghidra GUI:"
echo "1. Open ROM in Ghidra"
echo "2. Navigate to a function"
echo "3. View > Basic Blocks to see control flow"
echo ""
echo "For transpiler verification, use the transpiler's own CFG output:"
echo "  gbatopy transpile $ROM_FILE --print-cfg 2>/dev/null"