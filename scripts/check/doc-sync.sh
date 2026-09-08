#!/usr/bin/env bash
# Rule AGENTS.md #23: a codegen/runtime fix that changes a ROM's pass/fail
# status MUST update docs/reference/test-roms.md in the same change.
#
# Usage: scripts/check/doc-sync.sh [<changed-file>...]
# Reads a list of changed files from argv or stdin (one per line).
# Exits non-zero if crates/ or gba_runtime/ changed but test-roms.md did not.
set -euo pipefail

changed=("$@")
if [[ $# -eq 0 ]]; then
    mapfile -t changed
fi

code_touched=0
docs_touched=0
for f in "${changed[@]}"; do
    case "$f" in
        crates/gbatopy-cli/assets/gba_runtime/*|crates/gbatopy-cli/src/*|crates/gbatopy-disasm/src/*)
            code_touched=1 ;;
        docs/reference/test-roms.md)
            docs_touched=1 ;;
    esac
done

if [[ $code_touched -eq 1 && $docs_touched -eq 0 ]]; then
    echo "FAIL: code under crates/ changed but docs/reference/test-roms.md was not updated (AGENTS.md rule #23)" >&2
    echo "Update the status table, summary counts, and the affected ROM row." >&2
    exit 1
fi

echo "OK: doc-sync rule satisfied (or no code changed)."
exit 0
