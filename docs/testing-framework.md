# Automated Testing Framework

This document describes GBAtoPy's test infrastructure. The old Python scripts have been replaced with a unified Rust-based test framework.

---

## Overview

GBAtoPy uses a Rust test framework (`crates/gbatopy-test/`) that provides:

- Parallel test execution via rayon
- Configurable per-ROM testing via `test-roms-config.toml`
- 6 verification strategies
- Multiple report formats (Console, JSON, JUnit XML)

---

## Test Framework Architecture

### Components

| Component | Location | Description |
|-----------|----------|-------------|
| **Test Runner** | `crates/gbatopy-test/src/runner.rs` | Parallel execution engine |
| **Configuration** | `test-roms-config.toml` | Per-ROM test settings |
| **Verifiers** | `crates/gbatopy-test/src/verifiers/` | 6 verification strategies |
| **Reporter** | `crates/gbatopy-test/src/report.rs` | Console/JSON/JUnit output |

### Verifier Types

| Verifier | Description |
|----------|-------------|
| `smoke` | Transpile ROM + Python syntax validation |
| `screenshot_golden` | Compare transpiled output against expected.png |
| `mgba_oracle` | Compare against mGBA reference screenshots |
| `ewram_dump` | Parse FuzzARM eWRAM dumps for CPU correctness |
| `pass_fail` | Detect blank screens vs numbered pass/fail indicators |
| `assertion_text` | Parse assertion error messages from ROM output |

---

## Configuration

Tests are configured in `test-roms-config.toml`:

```toml
# Base paths
roms_dir = "test_roms/roms"
output_dir = "test-reports"
parallel = 4

# Per-ROM configuration
[[test]]
name = "stripes"
rom_path = "stripes.gba"
test_type = "screenshot_golden"
frames = 60
tolerance = 10

[[test]]
name = "arm"
rom_path = "arm.gba"
test_type = "pass_fail"
frames = 60

[[test]]
name = "FuzzARM"
rom_path = "ARM_Any.gba"
test_type = "ewram_dump"
frames = 600
```

### Config Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique test name |
| `rom_path` | string | Relative path to ROM file |
| `test_type` | enum | Verifier type: smoke, screenshot_golden, mgba_oracle, ewram_dump, pass_fail, assertion_text |
| `frames` | integer | Number of frames to run (default: 60) |
| `tolerance` | integer | Pixel tolerance for screenshot comparison (default: 10) |

---

## Running Tests

### Full Test Suite

```bash
cargo run -p gbatopy-test -- --config test-roms-config.toml
```

### Filter by ROM Name

```bash
cargo run -p gbatopy-test -- --config test-roms-config.toml --filter stripes
```

### Custom Config

```bash
cargo run -p gbatopy-test -- --config /path/to/custom.toml
```

---

## Test Output

### Console Output

```
=== GBAtoPy Test Suite ===
Config: test-roms-config.toml
ROMs: 66
Parallel workers: 4

[1/66] stripes ........... PASS (smoke)
[2/66] hello ............. PASS (screenshot_golden) 98.5% match
[3/66] arm ............... PASS (pass_fail)
[4/66] FuzzARM ........... PASS (ewram_dump) 0 failures / 10000 tests
...

=== Summary ===
Passed:  65
Failed:  3
Errors:  0
Pass rate: 95.6%
```

### JSON Report

```bash
cat test-reports/results.json
```

```json
[
  {
    "name": "stripes",
    "test_type": "smoke",
    "status": "pass",
    "duration_ms": 5234
  },
  ...
]
```

### JUnit XML

```bash
cat test-reports/results-junit.xml
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="gbatopy-test" tests="66" failures="3" time="234.567">
  <testcase name="stripes" classname="smoke" time="5.234"/>
  ...
</testsuite>
```

---

## Verification Strategies

### 1. Smoke Test

The simplest verifier: transpile ROM and verify Python syntax is valid.

```bash
cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py
python3 -m py_compile /tmp/stripes.py
```

### 2. Screenshot Golden

Compare transpiled output against known-correct reference images.

**Requirements**: ROM must have `expected.png` in the output directory.

```python
# Compare with tolerance
def compare_screenshots(actual, expected, tolerance=10):
    diff = 0
    for a, e in zip(actual, expected):
        if any(abs(ac - ec) > tolerance for ac, ec in zip(a, e)):
            diff += 1
    return diff / len(actual) * 100
```

### 3. mGBA Oracle

Compare transpiled output against mGBA reference screenshots.

```bash
# Capture golden from mGBA
./mgba/build/sdl/mgba --script scripts/screenshot/screenshot.lua test_roms/roms/stripes.gba

# Compare
# (handled by screenshot_golden verifier)
```

### 4. eWRAM Dump

Parse FuzzARM eWRAM dumps to verify CPU correctness.

**Format**: Each failure record is 64 bytes at eWRAM address 0x02000000:

```
Offset  Size   Content
0x00    1 word ['AAAA' or 'TTTT'] — ARM or THUMB mode
0x04    2 words [opcode + shift] — e.g. "tst lsl     "
0x10    1 word [initial r0]
0x14    1 word [initial r1]
0x18    1 word [initial r2]
0x1C    1 word [initial CPSR]
0x20    1 word [actual r3]
0x24    1 word [actual r4]
0x2C    1 word [actual CPSR]
0x30    1 word [expected r3]
0x34    1 word [expected r4]
0x3C    1 word [expected CPSR]
```

### 5. Pass/Fail Screen

Detect blank/green screens (pass) vs numbered failures (fail).

```python
def detect_pass_fail(screenshot):
    # Check if screen is blank/green (PASS)
    # vs contains a number (FAIL)
    non_blank_pixels = count_non_blank(screenshot)
    if non_blank_pixels < 100:
        return "pass"
    # Otherwise, try OCR or pattern match for number
    return "fail"
```

### 6. Assertion Text

Parse assertion messages from hw-test ROMs.

```python
def parse_assertion(screenshot):
    # Pixel pattern matching for "PASS" or "FAIL" text
    # Extract assertion message if present
    pass
```

---

## ROM Classification

| Strategy | ROMs | Count |
|----------|------|-------|
| screenshot_golden | greenswap, bgx, bgpd, sprite-hmosaic, dispcnt-latch | 5 |
| mgba_oracle | stripes, shades, hello, helloWorld, hello_world | 5 |
| pass_fail | arm, thumb, bios, memory, unsafe, armwrestler, cond_invalid, retAddr, dma_priority, isr, if_ack, irq_delay, joypad, line_timing, lyc_midline, window_midframe | 16 |
| ewram_dump | ARM_Any, ARM_DataProcessing, THUMB_Any, THUMB_DataProcessing, FuzzARM | 5 |
| assertion_text | status-irq-dma, vram-mirror, burst-into-tears, force-nseq-access, latch, start-stop, reload, 128kb-boundary, haltcnt, timer_change | 10 |
| smoke | nes, enhancedcontrolchecker, redline, rtc-demo, helloAudio, test, song, rates, pcmxx, basic-timing, exact-timing, start-delay, sram, flash64, flash128, none, mode2, mode3, mode4, ram-access-timing, cancel-irq-ie, cancel-irq-if, cancel-irq-ime | 23 |

**Total**: 66 ROMs

---

## Helper Scripts

The Rust test framework (`gbatopy-test`) is the primary CI surface. The following helper scripts remain for manual workflows:

- ✅ `scripts/verify/compare_screenshots.py` — Golden-screenshot comparison against mGBA output (referenced in AGENTS.md full-verification workflow)
- ✅ `scripts/verify/coverage_tracker.py` — Feature coverage analysis (not part of CI)
- ✅ `scripts/verify/ewram_dump_verify.py` — EWRAM dump verification
- ✅ `scripts/screenshot/screenshot.lua` — mGBA Lua script for capturing golden screenshots

The following were removed as standalone tools in favor of `gbatopy-test`:

- ❌ `scripts/verify/visual_test.py` — Replaced by `gbatopy-test` smoke + screenshot verifiers
- ❌ `scripts/verify_all_roms.py` — Replaced by `gbatopy-test` with parallel execution

---

## Adding New Tests

1. Add entry to `test-roms-config.toml`:

```toml
[[test]]
name = "my-rom"
rom_path = "my-rom.gba"
test_type = "smoke"  # or screenshot_golden, pass_fail, etc.
frames = 60
```

2. For screenshot tests, add `expected.png` to `test-reports/my-rom/`

3. Run tests:

```bash
cargo run -p gbatopy-test -- --config test-roms-config.toml --filter my-rom
```

---

## CI Integration

Run tests in CI:

```bash
# Build
cargo build --release

# Run test suite
cargo run -p gbatopy-test -- --config test-roms-config.toml

# Check results
if [ -f test-reports/results.json ]; then
    echo "Tests completed"
fi
```

JUnit XML output can be consumed by GitHub Actions, Jenkins, etc.