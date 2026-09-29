#!/bin/bash
# Full regression suite for GBAtoPy
# Transpiles all 76 test ROMs and runs syntax checks

set -e

cd "$(dirname "$0")/../.."

echo "Running full 76-ROM regression suite..."
python3 scripts/run_tests.py --level 3

echo "Regression complete."