#!/bin/bash
# Export function list from a GBA ROM using Ghidra
# Usage: ghidra_functions.sh <rom_name>
# Output: /tmp/<rom_name>-functions.txt
#
# Note: Ghidra headless mode doesn't support scripting well in this version.
# This script imports and analyzes the ROM. For function extraction, use:
#   - Ghidra GUI: File > Show Symbol Table
#   - Or manually inspect the Ghidra project database

# Auto-detect project root (two levels up from script location)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Auto-detect Ghidra installation
GHIDRA_HOME="${GHIDRA_HOME:-/opt/ghidra}"

ROM_NAME="$1"
ROM_FILE="${PROJECT_ROOT}/test_roms/roms/${ROM_NAME}.gba"
GHIDRA="${GHIDRA_HOME}/ghidra_12.1.4_PUBLIC/support/analyzeHeadless"
PROJECT_DIR="/tmp/ghidra-projects"

if [ -z "$ROM_NAME" ]; then
    echo "Usage: $0 <rom_name>"
    echo "Example: $0 hello"
    exit 1
fi

if [ ! -f "$ROM_FILE" ]; then
    echo "Error: ROM file not found: $ROM_FILE"
    exit 1
fi

mkdir -p "$PROJECT_DIR"

echo "Importing and analyzing $ROM_NAME with Ghidra..."
$GHIDRA "$PROJECT_DIR" gbatopy \
  -import "$ROM_FILE" \
  -processor ARM:BE:32:v4t \
  -noanalysis \
  -overwrite \
  2>&1 | grep -E "Total Time|Analysis succeeded|IMPORTING"

echo ""
echo "ROM imported successfully to $PROJECT_DIR/gbatopy/$ROM_NAME.gba"
echo "To extract functions:"
echo "  1. Open Ghidra GUI: ghidraRun"
echo "  2. Open project at $PROJECT_DIR/gbatopy"
echo "  3. Double-click $ROM_NAME.gba"
echo "  4. View > Symbol Table to see all functions"
echo ""
echo "Or use the transpiler's built-in dispatch table:"
echo "  gbatopy transpile $ROM_FILE --print-dispatch 2>/dev/null | grep '^FUNC'"