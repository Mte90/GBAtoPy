#!/bin/bash
# Capture golden audio from a GBA ROM using mGBA's SDL disk audio driver.
# Converts raw PCM output to WAV format using Python's wave module.

set -e

# --- Argument parsing ---
ROM_PATH=""
FRAME=60
OUTPUT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --frame)
            FRAME="$2"
            shift 2
            ;;
        --output)
            OUTPUT="$2"
            shift 2
            ;;
        *)
            if [[ -z "$ROM_PATH" ]]; then
                ROM_PATH="$1"
            fi
            shift
            ;;
    esac
done

# --- Validate arguments ---
if [[ -z "$ROM_PATH" ]]; then
    echo "Usage: $0 <rom_path> [--frame N] [--output PATH]" >&2
    exit 1
fi

if [[ ! -f "$ROM_PATH" ]]; then
    echo "Error: ROM file not found: $ROM_PATH" >&2
    exit 1
fi

# --- Set defaults ---
ROM_BASENAME=$(basename "$ROM_PATH" .gba)
DEFAULT_OUTPUT="/tmp/${ROM_BASENAME}_golden.wav"
OUTPUT="${OUTPUT:-$DEFAULT_OUTPUT}"

# --- Create temp file for raw capture ---
RAW_FILE=$(mktemp)
trap 'rm -f "$RAW_FILE"' EXIT

# --- Set environment variables ---
export LD_LIBRARY_PATH="/home/d.scasciafratte/gbatopy/mgba/build:/home/d.scasciafratte/gbatopy/mgba/build/sdl:$LD_LIBRARY_PATH"
export SDL_AUDIODRIVER=disk
export SDL_DISKAUDIOFILE="$RAW_FILE"
export SDL_VIDEODRIVER=dummy
export GBATOPY_TARGET_FRAME="$FRAME"

# --- Calculate runtime for target frames ---
# GBA runs at ~59.73 fps, approximate as 60 fps
# Runtime in seconds = frames / 60
RUNTIME_SECS=$(( (FRAME + 59) / 60 ))
if [[ $RUNTIME_SECS -lt 1 ]]; then
    RUNTIME_SECS=1
fi

# --- Run mGBA without Lua script (causes segfault) ---
# Use timeout + kill approach to capture exact frames
MGBA_PATH="/home/d.scasciafratte/gbatopy/mgba/build/sdl/mgba"

# Start mGBA in background
"$MGBA_PATH" "$ROM_PATH" &
MGBA_PID=$!

# Wait for the calculated runtime
sleep "$RUNTIME_SECS"

# Terminate mGBA gracefully
kill -TERM $MGBA_PID 2>/dev/null
wait $MGBA_PID 2>/dev/null
MGBA_EXIT=$?

# --- Check if raw file was created and has content ---
if [[ ! -f "$RAW_FILE" ]]; then
    echo "Error: No audio file generated" >&2
    exit 1
fi

if [[ ! -s "$RAW_FILE" ]]; then
    echo "Error: Audio file is empty" >&2
    exit 1
fi

# --- Convert raw PCM to WAV ---
python3 - "$RAW_FILE" "$OUTPUT" <<'PYTHON_SCRIPT'
import wave
import struct
import sys
import os

raw_path = sys.argv[1]
wav_path = sys.argv[2]

with open(raw_path, 'rb') as f:
    raw_data = f.read()

# Validate: must be even number of bytes (stereo 16-bit)
if len(raw_data) % 4 != 0:
    print(f"Error: Invalid raw data size ({len(raw_data)} bytes, not divisible by 4)", file=sys.stderr)
    sys.exit(1)

with wave.open(wav_path, 'wb') as wav:
    wav.setnchannels(2)
    wav.setsampwidth(2)
    wav.setframerate(44100)
    wav.writeframes(raw_data)

# Verify output
if os.path.getsize(wav_path) < 44:  # WAV header is 44 bytes minimum
    print("Error: Generated WAV file is too small", file=sys.stderr)
    sys.exit(1)

# Check for RIFF header
with open(wav_path, 'rb') as f:
    header = f.read(4)
    if header != b'RIFF':
        print("Error: Generated WAV file missing RIFF header", file=sys.stderr)
        sys.exit(1)

sys.exit(0)
PYTHON_SCRIPT

if [[ $? -ne 0 ]]; then
    echo "Error: WAV conversion failed" >&2
    exit 1
fi

# --- Report success ---
FILE_SIZE=$(stat -c%s "$OUTPUT")
echo "Successfully captured audio to: $OUTPUT"
echo "File size: $FILE_SIZE bytes"

exit 0