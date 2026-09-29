#!/bin/bash
# Disassemble at a specific address using Ghidra
# Usage: ghidra_decode.sh <rom_name> <hex_addr>
#
# Note: For interactive disassembly, use the Ghidra GUI

# Auto-detect project root (two levels up from script location)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Auto-detect Ghidra installation
GHIDRA_HOME="${GHIDRA_HOME:-/opt/ghidra}"

ROM_NAME="$1"
ADDR="$2"
ROM_FILE="${PROJECT_ROOT}/test_roms/roms/${ROM_NAME}.gba"
GHIDRA="${GHIDRA_HOME}/ghidra_12.1.4_PUBLIC/support/analyzeHeadless"
PROJECT_DIR="/tmp/ghidra-projects"

if [ -z "$ROM_NAME" ] || [ -z "$ADDR" ]; then
    echo "Usage: $0 <rom_name> <hex_addr>"
    echo "Example: $0 hello 0x08000000"
    exit 1
fi

if [ ! -f "$ROM_FILE" ]; then
    echo "Error: ROM file not found: $ROM_FILE"
    exit 1
fi

echo "Ghidra import/analysis for address 0x$ADDR:"
echo "Open the ROM in Ghidra GUI and navigate to 0x$ADDR"
echo ""
echo "Quick alternative using arm-none-eabi-as (if available):"
arm-none-eabi-as --version >/dev/null 2>&1 && {
    echo "arm-none-eabi-as is available for quick disassembly"
} || {
    echo "arm-none-eabi-as not found. Use Ghidra GUI or objdump with appropriate flags."
}