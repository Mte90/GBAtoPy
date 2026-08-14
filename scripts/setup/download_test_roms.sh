#!/usr/bin/env bash
# Compatibility shim — delegates to download_roms.sh (the unified downloader).
# AGENTS.md references this filename; the actual implementation lives in download_roms.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/download_roms.sh" "$@"
