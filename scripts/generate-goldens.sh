#!/bin/bash
# Parallel golden screenshot generator using mGBA.
#
# Generates golden reference screenshots for the visual canary ROM set by
# running mGBA with a per-ROM Lua capture script, in parallel.
#
# Usage:
#   ./scripts/generate-goldens.sh                      # all 12 canary ROMs, 10 frames, 4 workers
#   ./scripts/generate-goldens.sh --rom stripes          # single ROM
#   ./scripts/generate-goldens.sh --rom mode3.gba        # .gba suffix optional
#   ./scripts/generate-goldens.sh --frames 60            # custom frame count
#   ./scripts/generate-goldens.sh --workers 8            # custom parallelism
#   ./scripts/generate-goldens.sh --output-dir /tmp/gold # custom output location

set -euo pipefail

FRAMES=10
WORKERS=4
ROM_NAME=""
OUTPUT_DIR="scripts/screenshot/golden"
MGBA_BIN="mgba/build/sdl/mgba"
ROMS_DIR="test_roms/roms"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rom)       ROM_NAME="${2%.gba}"; shift 2 ;;
        --frames)    FRAMES="$2"; shift 2 ;;
        --workers)   WORKERS="$2"; shift 2 ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        -h|--help)
            head -16 "$0" | tail -14
            exit 0 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

if [ ! -f "$MGBA_BIN" ]; then
    echo "ERROR: mGBA not found at $MGBA_BIN"
    echo "Build it with: cd mgba && cmake -B build -S . && cmake --build build --target mgba-sdl"
    exit 1
fi

if [ -n "$ROM_NAME" ]; then
    ROMS=("$ROMS_DIR/$ROM_NAME.gba")
else
    ROMS=(
        "$ROMS_DIR/bgpd.gba"
        "$ROMS_DIR/bgx.gba"
        "$ROMS_DIR/greenswap.gba"
        "$ROMS_DIR/hello.gba"
        "$ROMS_DIR/hello_world.gba"
        "$ROMS_DIR/helloWorld.gba"
        "$ROMS_DIR/mode3.gba"
        "$ROMS_DIR/mode4.gba"
        "$ROMS_DIR/shades.gba"
        "$ROMS_DIR/sprite-hmosaic.gba"
        "$ROMS_DIR/stripes.gba"
        "$ROMS_DIR/vram-mirror.gba"
    )
fi

for rom in "${ROMS[@]}"; do
    if [ ! -f "$rom" ]; then
        echo "ERROR: ROM not found: $rom"
        exit 1
    fi
done

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

capture_one() {
    local rom="$1"
    local rom_stem
    rom_stem=$(basename "$rom" .gba)
    local output="$OUTPUT_DIR/golden_${rom_stem}_frame_${FRAMES}.png"
    local lua_file="$TMPDIR/${rom_stem}.lua"

    cat > "$lua_file" << LUAEOF
local frame_count = 0
callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count == ${FRAMES} then
        emu:screenshot("${output}")
        os.exit(0)
    end
end)
LUAEOF

    "$MGBA_BIN" -S "$lua_file" "$rom" >/dev/null 2>&1 || true

    if [ -f "$output" ]; then
        echo "  PASS  $rom_stem"
    else
        echo "  FAIL  $rom_stem (no screenshot produced)"
    fi
}
export -f capture_one
export OUTPUT_DIR FRAMES TMPDIR MGBA_BIN

rom_count=${#ROMS[@]}
echo "Generating $rom_count golden screenshot(s) at frame $FRAMES ($WORKERS workers)..."
echo ""

printf '%s\n' "${ROMS[@]}" | xargs -P "$WORKERS" -I {} bash -c 'capture_one "{}"'

echo ""
echo "Output: $OUTPUT_DIR/"
ls -1 "$OUTPUT_DIR/" | grep "frame_${FRAMES}" || echo "  (no files matching frame_${FRAMES})"
