#!/usr/bin/env bash
# Preflight: run all deterministic AGENTS.md enforcement checks.
# Use before committing, before marking a task done, or at session start.
#
# Individual checks can be run standalone:
#   scripts/check/no-skip.sh
#   scripts/check/no-debug-probes.sh
#   scripts/check/doc-sync.sh <changed-file>...
#   scripts/check/status-snapshot.sh
#
# To wire as a pre-commit hook in a git repo:
#   cp scripts/check/preflight.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
checks=(no-skip.sh no-debug-probes.sh)
failed=0

echo "=== Preflight: AGENTS.md enforcement ==="
for c in "${checks[@]}"; do
    if bash "$dir/$c"; then
        :
    else
        failed=1
    fi
done

# Doc-sync check: pass through any changed files from argv
if [[ $# -gt 0 ]]; then
    if ! bash "$dir/doc-sync.sh" "$@"; then
        failed=1
    fi
fi

# Status snapshot (informational, non-blocking)
bash "$dir/status-snapshot.sh" || true

if [[ $failed -ne 0 ]]; then
    echo "=== Preflight: FAILED — fix violations above ===" >&2
    exit 1
fi

echo "=== Preflight: PASSED ==="
exit 0
