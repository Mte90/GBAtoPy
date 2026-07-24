# GBAtoPy
[![License](https://img.shields.io/badge/License-MIT%20v1-blue.svg)](https://spdx.org/licenses/MIT.html#licenseText)   
[![Tests](https://img.shields.io/badge/tests-66%2F68%20smoke%20pass-yellow.svg)](docs/testing-framework.md)
[![Status](https://img.shields.io/badge/status-In%20Development-yellow.svg)](docs/roadmap.md)

Transform Game Boy Advance ROMs into standalone Python files.

> **NOT an emulator.** GBAtoPy transpiles GBA ROMs into human-readable Python code that, when executed, reproduces the game's behavior. The goal is a `.py` file you can open, read, and modify.

---

## In Active Development

- ✅ **68/68 ROMs** transpile to syntactically valid Python
- ✅ **23/68 ROMs** verified pixel-perfect against mGBA golden at frame 60 (stripes, shades, hello, helloWorld, hello_world, mode3, mode4, redline, arm, thumb, bios, memory, unsafe, cond_invalid, retAddr, if_ack, irq_delay, joypad, mode2, sram, flash64, flash128, none — see [`docs/reference/test-roms.md`](docs/reference/test-roms.md) for per-ROM evidence)
- ✅ **PPU Mode 0** (4BPP text tiles) verified on shades.gba, hello.gba, helloWorld.gba, hello_world.gba; **Mode 2** (affine) verified on mode2.gba; **Mode 3** (16-bit bitmap) verified on stripes.gba, mode3.gba; **Mode 4** (8BPP bitmap) verified on mode4.gba — all exact pixel matches
- ⚠️ **Mode 1/2 affine**, windows, blends, mosaic = register stubs only
- ⚠️ **Audio system** infrastructure exists, synthesis not verified end-to-end
- ⚠️ **4/68 ROMs** known failures: helloAudio.gba, rates.gba (runtime hang), window_midframe.gba (55% diff), greenswap.gba (85% diff)
- ⏰ **10/68 ROMs** hang at runtime (bgx, bgpd, nes, timer_change, pcmxx, line_timing, sprite-hmosaic, lyc_midline, dma_priority, isr) — likely codegen bugs in IRQ/DMA/timer paths
- ✅ **Test framework** includes smoke tests and screenshot-golden comparison via `scripts/verify/verify_rom.sh <rom> --no-golden`

**Last updated**: 2026-07-24

---

## Architecture

GBAtoPy converts ARM/Thumb assembly → Python code using a Rust pipeline:

```
ROM bytes → Disassembly → Python Code Gen → Executable Python
```

### Key Components

- **Disassembler** (`crates/gbatopy-disasm/`) - Decodes ARM/Thumb instructions
- **Code Generator** (`crates/gbatopy-cli/src/codegen/`) - ARM/Thumb → Python translation (600+ opcodes)
- **Memory Model** - GBA memory map (0x08000000 ROM, 0x06000000 VRAM, 0x04000000 MMIO)
- **Game Loop** - pygame-based display and input
- **Python Runtime** - Core emulation modules (CPU, PPU, Memory, DMA, Timers, APU) embedded in generated Python (see `crates/gbatopy-cli/assets/gba_runtime/`).
- **Test Framework** (`crates/gbatopy-test/`) - Rust-based automated test infrastructure with parallel execution, 6 verifier types (smoke, screenshot_golden, mgba_oracle, ewram_dump, pass_fail, assertion_text), and configurable per-ROM testing via `test-roms-config.toml`.

### Generated Output Structure

```python
# ROM data embedded
ROM_DATA = bytearray([...])

def func_08000000():
    global r0, r1, ..., r15
    r0 = r1 + r2  # Example: ADD instruction
    memory.write_32(0x08000100, value)  # Example: STR instruction

def main_entry():
    # ROM execution loop with pygame display
    while True:
        call_func(r15)
```

---

## Status

Project is in active development. Transpilation pipeline works for the test ROM set; per-ROM visual verification status is tracked in [`docs/reference/test-roms.md`](docs/reference/test-roms.md).

---

## Quick Start

### Prerequisites

- **Rust toolchain** (1.70+): `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **Python 3.10+**
- **Pygame**: `pip install pygame`
- **SDL2** (optional, for display): `sudo apt install libsdl2-dev`

### Build

```bash
cargo build --release
```

### Transpile a ROM

```bash
cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/arm.gba --output /tmp/test.py
```

### Run Generated Python

**Headless mode** (for testing):

```bash
python3 /tmp/test.py --headless --frame=60 --screenshot /tmp/test.png
```

**Interactive mode** (with display):

```bash
python3 /tmp/test.py --scale=2
```

### CLI Arguments

- `--headless`: Run without display (for testing/screenshot)
- `--frame=N`: Run exactly N frames then exit
- `--screenshot=FILE`: Save screenshot at end
- `--scale=N`: Scale display by N (e.g., 3 = 720×480 pixels)

---

## Test ROMs

Test ROMs are downloaded automatically via `scripts/setup/download_roms.sh` (**68 ROMs**):

```bash
# First time setup
bash scripts/setup/download_roms.sh
```

---

## Development

### Building

```bash
# Debug
cargo build

# Release (faster)
cargo build --release

# All crates
cargo build --workspace
```

### Testing

```bash
# Rust unit tests
cargo test --workspace

# Rust test framework (gbatopy-test) - runs all 68 ROMs
cargo run -p gbatopy-test -- --config test-roms-config.toml

# Subset of tests (filter by name)
cargo run -p gbatopy-test -- --config test-roms-config.toml --filter stripes

# Python tests (inside gba_runtime module)
python3 -m pytest crates/gbatopy-cli/assets/gba_runtime/tests/ -v

# Transpile smoke test
bash scripts/setup/download_roms.sh  # First time only
for rom in test_roms/roms/*.gba; do
  cargo run --release -p gbatopy-cli -- pipeline --rom "$rom" --output /tmp/test.py && \
  python3 -m py_compile /tmp/test.py && \
  echo "✓ $(basename "$rom")"
done
```

### Run Test Framework

The `gbatopy-test` crate provides automated testing with multiple verification strategies:

```bash
# Full test suite (all 68 ROMs)
cargo run -p gbatopy-test -- --config test-roms-config.toml

# Run specific verifier types
# smoke: Transpile + syntax check
# screenshot_golden: Compare against expected.png
# mgba_oracle: Compare against mGBA reference
# ewram_dump: Parse FuzzARM eWRAM dumps
# pass_fail: Detect blank/failed screens
# assertion_text: Parse assertion messages from ROM output
```

Reports are generated in multiple formats:
- Console: Color-coded pass/fail output
- JSON: `test-reports/results.json`
- JUnit XML: `test-reports/results-junit.xml`

### Verify Generated Python

```bash
# Generate ROM
cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/arm.gba --output /tmp/test.py

# Check syntax
python3 -m py_compile /tmp/test.py

# Verify stripes.gba golden match
python3 scripts/screenshot/compare_screenshots.py test_roms/roms/stripes.gba
# Expected: 100% pixel match
```

### mGBA Integration

For golden screenshots and debugging, GBAtoPy uses **mGBA** with custom patches for Lua scripting via `--script` flag.

mGBA source is NOT included in this repository (see `.gitignore`). To build:

```bash
# Clone mGBA
git clone https://github.com/mgba-emu/mgba.git
cd mgba

# Apply custom patches (adds --script flag + mScriptContext integration)
patch -p1 < ../mgba-custom-patches.diff

# Build with Lua scripting enabled
cmake -B build -DENABLE_SCRIPTING=ON -DBUILD_PYTHON=OFF -DUSE_QT=OFF
cmake --build build -j$(nproc)
```

#### Taking Golden Screenshots

```bash
# Single ROM
./build/sdl/mgba --script scripts/screenshot/screenshot.lua test_roms/roms/stripes.gba

# Full comparison (golden + transpile + compare)
python3 scripts/screenshot/compare_screenshots.py test_roms/roms/stripes.gba
```

The Lua API exposed by mGBA (after patching):
- `emu:currentFrame()` - Get current frame number
- `emu:runFrame()` - Advance one frame
- `emu:screenshot(filename)` - Save screenshot to PNG
- `callbacks:add("frame", fn)` - Register per-frame callback

See [mgba-custom-patches.diff](mgba-custom-patches.diff) for the full diff against upstream mGBA.
See [PR #3752](https://github.com/mgba-emu/mgba/pull/3752) for the upstream Lua scripting extension.

---

## References

- [GBA Hardware Manual](https://gbdev.io/gbafaq/)
- [GBA Memory Map](docs/reference/memory-map.md)
- [Test ROM Catalog](docs/reference/test-roms.md)
- [mGBA Scripting PR #3752](https://github.com/mgba-emu/mgba/pull/3752)
