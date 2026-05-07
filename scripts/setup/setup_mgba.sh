#!/usr/bin/env bash
# setup_mgba.sh – Build mGBA from local fork with extended Lua APIs
# Run from project root: bash scripts/setup/setup_mgba.sh

set -euo pipefail

MGBA_DIR="mgba"
BUILD_DIR="$MGBA_DIR/build"

echo "=== Building mGBA from local fork ==="

if [ ! -d "$MGBA_DIR" ]; then
    echo "Error: mgba/ directory not found"
    echo "The fork should be cloned in the project root"
    exit 1
fi

# Create build directory if needed
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Configure with scripting enabled
echo "Configuring mGBA..."
cmake .. \
    -DENABLE_SCRIPTING=ON \
    -DUSE_LUA=ON \
    -DCMAKE_BUILD_TYPE=Release

# Build
echo "Building mGBA (this may take a few minutes)..."
make -j$(nproc)

# Verify build
if [ -f "mgba" ]; then
    echo "✓ Build successful: $BUILD_DIR/mgba"
    echo ""
    echo "To use this build:"
    echo "  export MGBA_EXECUTABLE=$BUILD_DIR/mgba"
    echo "  mgba -l game.gba --script your_script.lua"
else
    echo "Error: Build failed, mgba executable not found"
    exit 1
fi