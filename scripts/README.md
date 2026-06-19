# Scripts

## Structure

```
scripts/
├── README.md                  ← This file
├── run-all-tests.sh           ← Smoke test: transpile + syntax check for all 68 ROMs
├── run-parallel-tests.sh      ← Parallel variant of run-all-tests.sh
├── quick_test.sh              ← Quick single-ROM transpile and syntax check
├── screenshot/
│   ├── screenshot.lua         ← mGBA Lua script for golden screenshot capture
│   └── golden/                ← Golden screenshots (generated manually)
├── setup/
│   └── download_roms.sh       ← Downloads test ROMs from GitHub
└── verify/
    ├── compare_screenshots.py ← Golden screenshot comparison (mGBA vs transpiled)
    └── ewram_dump_verify.py   ← Verify EWRAM dump binary format
```

## Test Scripts

### `run-all-tests.sh` — Smoke Test Suite

**Purpose:** Verify that all 68 test ROMs transpile to syntactically valid Python.

**What it DOES:**
- ✅ Transpile each ROM using the Rust CLI
- ✅ Run `py_compile` on generated Python files
- ✅ Report PASS/FAIL for each ROM
- ✅ Generate JUnit XML report (optional: `--junit`)

**What it does NOT do:**
- ❌ Execute the generated Python scripts
- ❌ Verify graphics rendering
- ❌ Verify audio playback
- ❌ Compare with golden screenshots

**Usage:**
```bash
# Run all 68 ROMs (may take 10-15 minutes)
./scripts/run-all-tests.sh

# Quick mode (skip ROMs >1MB)
./scripts/run-all-tests.sh --quick

# Generate JUnit report
./scripts/run-all-tests.sh --junit

# Filter by ROM name
./scripts/run-all-tests.sh --filter mode3
```

**Output:** Results in `test-reports/test-results.txt` and optionally `test-reports/results-junit.xml`

---

### `run-parallel-tests.sh` — Parallel Smoke Test

**Purpose:** Same as `run-all-tests.sh` but runs transpilation in parallel for faster execution.

**Usage:**
```bash
./scripts/run-parallel-tests.sh
```

---

### `quick_test.sh` — Single ROM Quick Test

**Purpose:** Fast transpile and syntax check for a single ROM.

**Usage:**
```bash
./scripts/quick_test.sh test_roms/roms/stripes.gba
```

---

## Verification Scripts

### `compare_screenshots.py` — Golden Screenshot Comparison

**Purpose:** Compare mGBA golden screenshot with transpiled ROM screenshot pixel-by-pixel.

**What it does:**
- ✅ Load two PNG images (golden vs transpiled)
- ✅ Resize golden if needed (handles different resolutions)
- ✅ Calculate pixel-by-pixel difference
- ✅ Report difference percentage and max pixel difference
- ✅ Generate visual diff image highlighting differences in red
- ✅ Pass/fail based on configurable threshold (default: 30%)

**Usage:**
```bash
# Compare single pair
python3 scripts/verify/compare_screenshots.py \
  --golden /tmp/stripes_mgba.png \
  --transpiled /tmp/stripes_transpiled.png \
  --threshold 30

# Compare multiple ROMs
python3 scripts/verify/compare_screenshots.py \
  --golden-dir /tmp/golden/ \
  --transpiled-dir /tmp/transpiled/ \
  --output-dir /tmp/diffs/ \
  --threshold 30
```

**Note:** This script is **NOT automatically called** by `run-all-tests.sh`. You must manually:
1. Generate golden screenshot with mGBA
2. Generate transpiled screenshot by running the Python script
3. Compare with this script

---

### `ewram_dump_verify.py` — EWRAM Dump Verification

**Purpose:** Verify that EWRAM dump files are in correct FuzzARM binary format.

**Usage:**
```bash
# Generate dump from transpiled ROM
python3 stripes.py --dump-memory /tmp/ewram_dump.bin

# Verify dump format
python3 scripts/verify/ewram_dump_verify.py /tmp/ewram_dump.bin
```

---

## mGBA Scripts

### `screenshot/screenshot.lua` — Golden Screenshot Capture

**Purpose:** Lua script for mGBA to capture golden screenshots automatically.

**Usage:**
```bash
# Capture golden screenshot for a ROM
./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua test_roms/roms/stripes.gba

# Output: /tmp/stripes.png (golden screenshot)
```

**Note:** The script runs the ROM for 60 frames, then saves the screenshot.

---

## Setup

### `setup/download_roms.sh` — Download Test ROMs

**Purpose:** Download all 68 test ROMs from GitHub (first-time setup only).

**Usage:**
```bash
bash scripts/setup/download_roms.sh
```

---

## Complete Verification Workflow

For **full verification** (not just syntax check), you must manually:

1. **Transpile the ROM:**
   ```bash
   cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py
   ```

2. **Generate golden screenshot with mGBA:**
   ```bash
   ./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua test_roms/roms/stripes.gba
   # Output: /tmp/stripes.png
   ```

3. **Generate transpiled screenshot:**
   ```bash
   cd /tmp && python3 stripes.py --headless --frame=60 --screenshot /tmp/stripes_transpiled.png
   ```

4. **Compare screenshots:**
   ```bash
   python3 scripts/verify/compare_screenshots.py \
     --golden /tmp/stripes.png \
     --transpiled /tmp/stripes_transpiled.png \
     --threshold 30
   ```

5. **Verify result:**
   - If `diff_percentage < 30%`: PASS
   - If `diff_percentage >= 30%`: FAIL (visual diff saved to `/tmp/stripes_diff.png`)

---

## Notes

- **mGBA is not included in the repository** — see `../README.md` for build instructions
- The Rust test crate (`crates/gbatopy-test/`) provides automated testing infrastructure
- **No automated golden screenshot pipeline exists yet** — all visual verification is manual
- Debug logging (`DEBUG: render_frame called`) is currently enabled in generated code; this will be removed in a future update
