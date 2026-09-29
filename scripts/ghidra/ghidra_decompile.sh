#!/bin/bash
# Decompile a function at a specific address
# Usage: ghidra_decompile.sh <rom_name> <hex_addr>
#
# Note: Requires Ghidra GUI for decompilation

# Auto-detect project root (two levels up from script location)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ROM_NAME="$1"
ADDR="$2"
ROM_FILE="${PROJECT_ROOT}/test_roms/roms/${ROM_NAME}.gba"

if [ -z "$ROM_NAME" ] || [ -z "$ADDR" ]; then
    echo "Usage: $0 <rom_name> <hex_addr>"
    echo "Example: $0 hello 0x08000000"
    exit 1
fi

if [ ! -f "$ROM_FILE" ]; then
    echo "Error: ROM file not found: $ROM_FILE"
    exit 1
fi

echo "Decompilation at 0x$ADDR requires Ghidra GUI:"
echo "1. Open ROM in Ghidra"
echo "2. Navigate to 0x$ADDR"
echo "3. Press 'D' to disassemble if needed"
echo "4. Press 'F5' to decompile"
echo ""
echo "This is useful for understanding what code at a given address does"
echo "when debugging timeout/hang issues."