#!/bin/bash
# mGBA Golden Screenshot Capture Suite
#
# Captures golden screenshots for all test ROMs using mGBA.
# Uses SDL_VIDEODRIVER=offscreen for headless rendering.
#
# Usage:
#   ./scripts/generate_mgba_goldens.sh                    # All ROMs, frame 60
#   ./scripts/generate_mgba_goldens.sh --rom hello        # Single ROM
#   ./scripts/generate_mgba_goldens.sh --frames 1,10,30   # Multiple frames
#   ./scripts/generate_mgba_goldens.sh --workers 4        # Parallel instances
#
# Environment:
#   Automatically sets LD_LIBRARY_PATH, SDL_AUDIODRIVER=dummy, SDL_VIDEODRIVER=offscreen

set -e

# --- Determine project root ---
# Use current working directory as project root (where user runs the script)
PROJECT_ROOT="$(pwd)"

# --- Paths ---
ROMS_DIR="$PROJECT_ROOT/test_roms/roms"
GOLDEN_DIR="$PROJECT_ROOT/scripts/screenshot/golden"
LUA_SCRIPT="$PROJECT_ROOT/scripts/screenshot/screenshot.lua"
MGBA_BIN="$PROJECT_ROOT/mgba/build/sdl/mgba"

# --- Defaults ---
FRAME=60
WORKERS=2
TIMEOUT=120
ROM_FILTER=""

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --rom)
            ROM_BASE="$2"
            shift 2
            ;;
        --filter)
            ROM_FILTER="$2"
            shift 2
            ;;
        --frames)
            FRAME="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Capture golden screenshots for GBA test ROMs using mGBA."
            echo ""
            echo "Options:"
            echo "  --rom NAME      Single ROM name (without .gba)"
            echo "  --filter SUBSTR Filter ROMs by name substring"
            echo "  --frames N      Frame number(s), comma-separated (default: 60)"
            echo "  --workers N     Parallel mGBA instances (default: 2)"
            echo "  --timeout N     Timeout per ROM in seconds (default: 120)"
            echo "  --help          Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# --- Validate mGBA binary ---
if [[ ! -x "$MGBA_BIN" ]]; then
    echo "ERROR: mGBA binary not found or not executable: $MGBA_BIN" >&2
    echo "Build mGBA first: cd mgba && mkdir -p build && cd build && cmake .. && make" >&2
    exit 1
fi

# --- Validate Lua script ---
if [[ ! -f "$LUA_SCRIPT" ]]; then
    echo "ERROR: Lua script not found: $LUA_SCRIPT" >&2
    exit 1
fi

# --- Create golden directory ---
mkdir -p "$GOLDEN_DIR"

# --- Set environment variables ---
export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:$LD_LIBRARY_PATH"
export SDL_AUDIODRIVER=dummy
export SDL_VIDEODRIVER=offscreen

# --- Collect ROMs ---
collect_roms() {
    if [[ -n "${ROM_BASE:-}" ]]; then
        ROM_PATH="$ROMS_DIR/${ROM_BASE}.gba"
        if [[ ! -f "$ROM_PATH" ]]; then
            echo "ERROR: ROM not found: $ROM_PATH" >&2
            exit 1
        fi
        echo "$ROM_PATH"
    else
        if [[ -n "$ROM_FILTER" ]]; then
            find "$ROMS_DIR" -name "*.gba" -type f | grep -i "$ROM_FILTER" | sort
        else
            find "$ROMS_DIR" -name "*.gba" -type f | sort
        fi
    fi
}

ROMS=($(collect_roms))
ROM_COUNT=${#ROMS[@]}

if [[ $ROM_COUNT -eq 0 ]]; then
    echo "ERROR: No ROMs to process" >&2
    exit 1
fi

# --- Parse frames ---
IFS=',' read -ra FRAMES <<< "$FRAME"

# --- Capture function ---
capture_golden() {
    local rom_path="$1"
    local frame="$2"
    local rom_base=$(basename "$rom_path" .gba)
    local output_path="$GOLDEN_DIR/golden_${rom_base}_frame_${frame}"
    
    # Set environment for this capture
    export GBATOPY_SCREENSHOT_PATH="$output_path"
    export GBATOPY_TARGET_FRAME="$frame"
    
    # Run mGBA with offscreen rendering
    "$MGBA_BIN" -S "$LUA_SCRIPT" "$rom_path" \
        2>/dev/null
    
    # Check result
    if [[ -f "${output_path}.png" ]]; then
        echo "OK:${rom_base}:${frame}"
        return 0
    else
        echo "FAIL:${rom_base}:${frame}:screenshot not created"
        return 1
    fi
}

# --- Main execution ---
echo "=== mGBA Golden Screenshot Capture ==="
echo "ROMs: $ROM_COUNT"
echo "Frames: ${FRAMES[*]}"
echo "Workers: $WORKERS"
echo "Output: $GOLDEN_DIR"
echo ""

# Build work items
WORK_ITEMS=()
for rom in "${ROMS[@]}"; do
    for frame in "${FRAMES[@]}"; do
        WORK_ITEMS+=("$rom:$frame")
    done
done

TOTAL_WORK=${#WORK_ITEMS[@]}
SUCCESS=0
FAIL=0

# Process sequentially (parallelism causes output capture issues)
export MGBA_BIN LUA_SCRIPT GOLDEN_DIR PROJECT_ROOT

RESULTS_FILE=$(mktemp)

for item in "${WORK_ITEMS[@]}"; do
    rom="${item%%:*}"
    frame="${item##*:}"
    
    # Run capture inline
    (
        # Set library path in subshell
        export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:$LD_LIBRARY_PATH"
        
        rom_base=$(basename "$rom" .gba)
        output_path="$GOLDEN_DIR/golden_${rom_base}_frame_${frame}"
        
        # Set environment for this capture
        export GBATOPY_SCREENSHOT_PATH="$output_path"
        export GBATOPY_TARGET_FRAME="$frame"
        export SDL_AUDIODRIVER=dummy
        export SDL_VIDEODRIVER=offscreen
        
        # Run mGBA with offscreen rendering
        "$MGBA_BIN" -S "$LUA_SCRIPT" "$rom" \
            2>/dev/null
        
        # Check result
        if [[ -f "${output_path}.png" ]]; then
            echo "OK:${rom_base}:${frame}"
        else
            echo "FAIL:${rom_base}:${frame}:screenshot not created"
        fi
    ) >> "$RESULTS_FILE"
    
    # Show progress
    tail -1 "$RESULTS_FILE"
done

# Count results
SUCCESS=$(grep -c "^OK:" "$RESULTS_FILE" 2>/dev/null || echo 0)
FAIL=$(grep -c "^FAIL:" "$RESULTS_FILE" 2>/dev/null || echo 0)

rm -f "$RESULTS_FILE"

# --- Summary ---
echo ""
echo "=== Summary ==="
echo "Total: $TOTAL_WORK"
echo "Success: $SUCCESS"
echo "Failed: $FAIL"

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi
exit 0