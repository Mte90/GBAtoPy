#!/bin/bash
# Capture golden screenshot from GBA ROM using mGBA headless

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MGBA="${SCRIPT_DIR}/../../mgba/build/mgba-headless"
DUMP_VRAM="${SCRIPT_DIR}/dump_to_png.py"

usage() {
    echo "Usage: $0 <rom.gba> [output.png] [frames]"
    echo "  rom.gba    - Path to GBA ROM"
    echo "  output.png - Output PNG (default: screenshot.png)"
    echo "  frames     - Frames to run (default: 60)"
    exit 1
}

ROM="$1"
OUTPUT="${2:-screenshot.png}"
FRAMES="${3:-60}"

if [ -z "$ROM" ] || [ ! -f "$ROM" ]; then
    usage
fi

if [ ! -x "$MGBA" ]; then
    echo "Error: mgba-headless not found at $MGBA" >&2
    exit 1
fi

WORKDIR=$(mktemp -d)
cd "$WORKDIR"

echo "Running mGBA for $FRAMES frames..."
timeout 30 "$MGBA" --script "$SCRIPT_DIR/capture_screen.lua" "$ROM" 2>&1 | grep -v "^Scripting:"

if [ ! -f vram_dump.bin ]; then
    echo "Error: Failed to capture VRAM" >&2
    exit 1
fi

echo "Converting to PNG..."
python3 "$DUMP_VRAM" vram_dump.bin palette_dump.bin "$OUTPUT"

echo "Saved: $OUTPUT ($FRAMES frames)"
rm -rf "$WORKDIR"