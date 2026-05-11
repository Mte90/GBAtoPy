#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MGBA="${SCRIPT_DIR}/../../mgba/build/mgba-headless"

if [ -z "$1" ] || [ ! -f "$1" ]; then
    echo "Usage: $0 <rom.gba> [output.png] [frames]" >&2
    exit 1
fi

ROM="$1"
OUTPUT="${2:-screenshot.png}"
FRAMES="${3:-60}"
WORKDIR=$(mktemp -d)
cd "$WORKDIR"

echo "Running: $MGBA --script /dev/stdin \"$ROM\""
python3 -c "
print('local FRAMES_TO_RUN = ' + str($FRAMES))
print('print(\"Frames to run:\", FRAMES_TO_RUN)')
print('callbacks:add(\"frame\", function()')
print('  emu.frameWait()')
print('  if core and core:currentFrame and core:currentFrame() >= FRAMES_TO_RUN then')
print('    print(\"Frame target reached\")')
print('  end')
print('end)')
print('print(\"Started...\", flush=True)')
" > capture.lua

timeout 30 "$MGBA" --script capture.lua "$ROM" 2>/dev/null || true

if [ -f vram_dump.bin ] && [ -f palette_dump.bin ]; then
    python3 "${SCRIPT_DIR}/dump_to_png.py" vram_dump.bin palette_dump.bin "$OUTPUT"
    echo "Saved: $OUTPUT"
else
    echo "No dumps found" >&2
    rm -rf "$WORKDIR"
    exit 1
fi

rm -rf "$WORKDIR"
