# GBAtoPy
[![License](https://img.shields.io/badge/License-MIT%20v1-blue.svg)](https://spdx.org/licenses/MIT.html#licenseText)   

Transform Game Boy Advance ROMs into standalone Python files.

> **NOT an emulator.** GBAtoPy transpiles GBA ROMs into human-readable Python code that, when executed, reproduces the game's behavior. The goal is a `.py` file you can open, read, and modify.

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
- **Python Runtime** - Core emulation modules (CPU, PPU, Memory, DMA, Timers, APU) embedded in generated Python (see `crates/gbatopy-cli/assets/gba_runtime/`). Derived from [PyBoyAdvance](https://github.com/williamckha/PyBoyAdvance) (MIT-licensed).
- **Test Framework** (`crates/gbatopy-test/`) - Rust-based automated test infrastructure with parallel execution, 6 verifier types (smoke, screenshot_golden, mgba_oracle, ewram_dump, pass_fail, assertion_text), and configurable per-ROM testing via `test-config.toml`.

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

## Current Status

| Component | Status |
|-----------|--------|
| ARM/Thumb codegen | ✅ Complete (600+ opcodes, zero stubs) |
| PPU rendering | ✅ Mode 3/4 (100% golden match on stripes.gba), Mode 0 (4BPP) partial |
| Memory subsystem | ✅ VRAM, Palette, OAM, MMIO with mirrors |
| IRQ/DMA/Timers | ✅ 4 DMA channels, Timers 0-3, VBlank/HBlank/VCount interrupts |
| BIOS SWI | ✅ 54 handlers (Sqrt, Div, Halt, CpuSet, etc.) |
| Keypad input | ✅ KEYINPUT/KEYCNT |
| Sprite rendering | ✅ OAM + tile fetch + palette lookup |
| APU audio | ❌ PSG + FIFO infrastructure exists, no sound output |
| Affine backgrounds | ❌ Mode 1/2 code exists, MMIO wiring broken |
| Window/Blend/Mosaic | ❌ Register stubs only |

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

## Coverage Statistics

| Metric | Value |
|--------|-------|
| Test ROMs | 66 |
| Transpile success | ✅ 100% (66/66) |
| Golden match | ✅ stripes.gba (100%) |
| Zero stubs | ✅ All 66 ROMs |
| ARM/Thumb codegen | ✅ 600+ opcodes |
| 54 BIOS handlers | Implemented |
| VRAM writes | Working (Mode 3/4) |
| DMA channels | ✅ 4 channels |
| IRQ handlers | ✅ VBlank/HBlank/VCount |

**Known Gaps:**
- ❌ APU audio synthesis (no sound output)
- ❌ Affine backgrounds (Mode 1/2)
- ❌ Window layers, blend modes, mosaic effects
- ❌ CPSR flags (conditional branches unreliable)

---

## Test ROMs

Test ROMs are downloaded automatically via `scripts/setup/download_roms.sh` (**66 ROMs**):

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
cargo run -p gbatopy-test -- --config test-config.toml

# Subset of tests (filter by name)
cargo run -p gbatopy-test -- --config test-config.toml --filter stripes

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
cargo run -p gbatopy-test -- --config test-config.toml

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
