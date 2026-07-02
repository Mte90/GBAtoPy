# Scripts

## Structure

```
scripts/
├── README.md                  ← This file
├── run-all-tests.sh           ← Smoke test: transpile + syntax check for all 66 ROMs
├── run-parallel-tests.sh      ← Parallel variant of run-all-tests.sh
├── quick_test.sh              ← Quick single-ROM transpile and syntax check
├── run_tests.py               ← Python test runner (alternative to run-all-tests.sh)
├── analyze_codegen.py         ← Analyze codegen patterns and statistics
├── detect_features.py         ← Detect GBA features used by ROMs
├── extract_assets.py          ← Extract graphics/assets from ROMs
├── minify.py                  ← Minify generated Python files
├── final_benchmark.py         ← Performance benchmark for transpiled ROMs
├── generate_baseline.py       ← Generate baseline comparison data
├── screenshot/
│   ├── screenshot.lua         ← Main mGBA Lua script for golden screenshots
│   ├── stripes_golden.lua     ← Specific for stripes.gba
│   ├── sprite_mosaic_test.lua ← Sprite/mosaic testing
│   ├── test_callback.lua      ← Callback test
│   ├── test_manual.lua        ← Manual testing
│   ├── test_simple.lua        ← Simple test
│   ├── window_test.lua        ← Window rendering test
│   └── golden/                ← Golden screenshots (generated manually)
├── setup/
│   └── download_roms.sh       ← Downloads test ROMs from GitHub
└── verify/
    ├── compare_screenshots.py ← Golden screenshot comparison (mGBA vs transpiled)
    ├── coverage_tracker.py    ← Track test coverage across ROMs
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

## Analysis & Utility Scripts

### `analyze_codegen.py` — Codegen Analysis

**Purpose:** Analyze patterns in generated Python code, statistics on instruction usage, and codegen quality metrics.

**Usage:**
```bash
python3 scripts/analyze_codegen.py /tmp/stripes.py
```

---

### `detect_features.py` — ROM Feature Detection

**Purpose:** Detect which GBA hardware features are used by a ROM (modes, sprites, DMA, etc.).

**Usage:**
```bash
python3 scripts/detect_features.py test_roms/roms/stripes.gba
```

---

### `extract_assets.py` — Graphics Extraction

**Purpose:** Extract tile data, palettes, and sprite graphics from ROMs for debugging or documentation.

**Usage:**
```bash
python3 scripts/extract_assets.py test_roms/roms/stripes.gba --output /tmp/assets/
```

---

### `minify.py` — Python Minification

**Purpose:** Minify generated Python files to reduce size (removes comments, whitespace).

**Usage:**
```bash
python3 scripts/minify.py /tmp/stripes.py --output /tmp/stripes.min.py
```

---

### `final_benchmark.py` — Performance Benchmark

**Purpose:** Measure execution speed of transpiled ROMs and compare with mGBA.

**Usage:**
```bash
python3 scripts/final_benchmark.py --rom test_roms/roms/stripes.gba --frames 1000
```

---

### `generate_baseline.py` — Baseline Generation

**Purpose:** Generate baseline data for comparison tests (pixel data, timing, etc.).

**Usage:**
```bash
python3 scripts/generate_baseline.py --rom test_roms/roms/stripes.gba
```

---

### `run_tests.py` — Python Test Runner

**Purpose:** Alternative Python-based test runner for smoke tests (alternative to `run-all-tests.sh`).

**Usage:**
```bash
python3 scripts/run_tests.py --all
python3 scripts/run_tests.py --filter mode3
```

---

### `verify/coverage_tracker.py` — Test Coverage Tracker

**Purpose:** Track which ROMs have passed visual verification and maintain coverage statistics.

**Usage:**
```bash
python3 scripts/verify/coverage_tracker.py --report
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
