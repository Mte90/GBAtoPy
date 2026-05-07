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

- **Disassembler** (`crates/gbatopy-disasm/`) - Decodes 56,000+ ARM/Thumb instructions
- **Code Generator** (`crates/gbatopy-cli/src/cmds/pipeline_cmd.rs`) - ARM/Thumb → Python translation
- **Memory Model** - GBA memory map (0x08000000 ROM, 0x06000000 VRAM, 0x04000000 MMIO)
- **Game Loop** - pygame-based display and input
- **PyBoyAdvance Runtime** - Core emulation modules embedded in generated Python (see `assets/gba_runtime/`). **MIT-licensed, attribution required**.

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

Test ROMs are downloaded automatically via `scripts/setup/download_test_roms.sh` (**39 ROMs**):

```bash
# First time setup
bash scripts/setup/download_test_roms.sh
```

---

## Current Status (May 2026)

### ✅ What Works

- **Rust pipeline**: Compiles without warnings
- **Disassembler**: Decodes 56,000+ ARM instructions from test ROMs
- **Code generation**: Produces valid Python (75,000+ lines output)
- **Syntax validation**: Generated Python passes `python3 -m py_compile`
- **Memory model**: `memory.read_32()`/`memory.write_32()` operations work
- **Asset extraction**: Loads VRAM, palette, and sprite data at runtime

### ❌ What Doesn't Work

- **No instruction codegen**: Pipeline does NOT translate instructions. Output is template + ROM data.
- **603+ stubs**: Generated Python has `pass # TODO: {opcode} not implemented` for all opcodes.
- **No execution**: Codegen match uses exact strings; disassembler emits suffixed forms (e.g., `ORRVS`, `ADDGT`, `STRBEQ`). 603+ stubs from mismatch.
- **No PPU rendering**: Screenshots are blank (PPU not implemented)
- **No Thumb codegen**: Thumb coverage ~0%
- **No multiply instructions**: MUL, MLA not handled
- **No interrupts**: VBlank/HBlank IRQ handling incomplete
- **No audio**: APU stubs return 0

### Root Cause

The pipeline was simplified — `run_pipeline()` does not call disassembly or codegen. The output is a template with ROM data embedded. The actual codegen path (strip condition codes, full opcode map, branch handling) exists as **unexecuted plan tasks T8-T12** in `.sisyphus/plans/roadmap-rewrite.md`.

---

## Known Limitations

1. **Blank Screenshots**: All generated Python produces black/blank screens - PPU rendering not implemented
2. **603+ Stubs**: Most instructions generate `pass` statements instead of code
3. **No Execution**: Generated Python cannot execute real game logic
4. **No Audio**: APU emulation not integrated
5. **No Interrupts**: VBlank wait loops may hang

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

# Transpile smoke test
bash scripts/setup/download_test_roms.sh  # First time only
for rom in test_roms/roms/*.gba; do
  cargo run --release -p gbatopy-cli -- pipeline --rom "$rom" --output /tmp/test.py && \
  python3 -m py_compile /tmp/test.py && \
  echo "✓ $(basename "$rom")"
done
```

### Verify Generated Python

```bash
# Generate ROM
cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/arm.gba --output /tmp/test.py

# Check syntax
python3 -m py_compile /tmp/test.py

# Count stubs (expect 603+)
grep -c "pass.*not implemented" /tmp/test.py

# Verify not black
python3 -c "from PIL import Image; img=Image.open('/tmp/test.png'); px=list(img.getdata()); nb=sum(1 for p in px if sum(p)>30); print(f'Non-black: {nb}/38400'); assert nb >= 100"
```

### mGBA Integration

For golden screenshots and debugging, GBAtoPy integrates with **mGBA** emulator.

mGBA source is NOT included in this repository (see `.gitignore`). To use:

```bash
# Clone mGBA with Lua scripting extension
git clone --branch extend-lua https://github.com/Mte90/mgba.git

# Build mGBA
cd mgba
cmake -B build . && cmake --build build -j$(nproc)

# Run with Lua scripting
./build/sdl/mgba --lua-script your_script.lua game.gba
```

The `extend-lua` branch adds APIs for memory/instruction tracing:
- `emu:traceMemory(enabled, callback)` - Memory access monitoring
- `emu:traceInstructions(enabled, callback)` - Instruction execution tracing
- `emu:watchRegister("r0", callback)` - Register change detection

See [PR #3752](https://github.com/mgba-emu/mgba/pull/3752) for details.

---

## References

- [GBA Hardware Manual](https://gbdev.io/gbafaq/)
- [GBA Memory Map](docs/ARCHITECTURE_INTERRUPTS.md)
- [Test ROM Catalog](docs/v3/reference/test-roms.md)
- [mGBA Scripting PR #3752](https://github.com/mgba-emu/mgba/pull/3752)
