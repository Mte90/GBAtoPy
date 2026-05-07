# Architecture

GBAtoPy is a transpiler that converts GBA ROMs (ARM/Thumb assembly) into standalone Python files playable with pygame.

## Pipeline Overview

```
ROM (.gba)
  │
  ▼
┌──────────────┐
│  Disassembler │  Decode ARM/Thumb instructions
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Oracle      │  Trace execution via mGBA, collect register/memory state
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  IR Lifter   │  Convert instructions to intermediate representation
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Type Recovery │  Infer types from traces (arrays, structs, pointers)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Codegen    │  Generate Python functions with runtime calls
└──────┬───────┘
       │
       ▼
output.py (standalone Python + pygame)
```

## Crate Structure

The pipeline is implemented as 6 Rust crates:

| Crate | Purpose |
|-------|---------|
| `gbatopy-disasm` | Decodes ARM and Thumb instructions from ROM binary |
| `gbatopy-mgba` | Interfaces with mGBA to trace execution paths |
| `gbatopy-ir` | Lifts decoded instructions to an intermediate representation |
| `gbatopy-types` | Shared type definitions used across all pipeline crates |
| `gbatopy-codegen` | Generates Python code from IR or disassembly |
| `gbatopy-cli` | CLI driver that orchestrates the pipeline |

The workspace is defined in `Cargo.toml` at the project root.

## ARM/Thumb Processing

The GBA CPU is an ARM7TDMI running the ARMv4T instruction set. It has two instruction encodings:

- **ARM mode** (32-bit instructions) — ~160 unique opcodes
- **Thumb mode** (16-bit instructions) — ~60 unique opcodes

The CPU switches between modes via `BX` instructions. The disassembler decodes both encodings, and the IR lifter tracks the `CPSR.T` flag for mode switching.

ARM instructions support **conditional execution** — a 4-bit condition code in the upper bits determines whether the instruction executes based on CPSR flags (EQ, NE, GT, LT, CS, CC, MI, PL, VS, VC, HI, LS, GE, GT, AL).

## Function Reconstruction

The lifter recognizes ARM calling conventions to reconstruct functions:

- **Prologue**: `PUSH {lr}`, `SUB sp, sp, #N`
- **Epilogue**: `POP {pc}`, `ADD sp, sp, #N`, `BX lr`
- **Calling convention**: r0-r3 arguments, r0 return value, r4-r11 callee-saved

The codegen produces a `func_map` dictionary mapping entry addresses to Python functions.

## Python Runtime

Generated Python includes an inlined runtime that emulates GBA hardware. The runtime source code is derived from [PyBoyAdvance](https://github.com/williamckha/PyBoyAdvance) (MIT licensed).

| Module | Hardware | Role | Status |
|--------|----------|------|--------|
| `memory.py` | Bus | Memory-mapped I/O with HAL side effects | Partial |
| `ppu.py` | Picture Processing Unit | Background tiles, sprites, scanline rendering | Partial — produces screenshots but graphics not yet correct |
| `apu.py` | Audio Processing Unit | PSG channels, FIFO, pygame mixer output | Stub — all `return 0` |
| `dma.py` | DMA Controller | Background memory transfers | Partial — pending flag bug |
| `bios.py` | BIOS ROM | Software interrupt handlers (SWI) | Partial — 9/43 implemented |
| `input.py` | Keypad | KEYINPUT register, pygame keyboard mapping | Unverified |

MMIO writes trigger hardware behavior through the HAL interface — writing to `DISPCNT` configures the PPU, writing to sound registers triggers APU output, DMA register writes initiate transfers.

## Asset Extraction

ROM data (tiles, palettes, tilemaps, audio samples) is extracted to separate `.bin` files:

- `palette.bin` — Background palette data
- `tiles.bin` — 4bpp tile graphics
- `sprites.bin` — Sprite/OAM tile data
- `tilemap.bin` — Screen block map data

The generated Python calls `load_assets()` at startup to read these files. GBA LZ77 compression uses a 24-bit (3-byte little-endian) expanded size field.

## mGBA Oracle

The oracle uses a modified mGBA build with extended Lua scripting (branch `extend-lua`). Lua scripts in `scripts/lua/` control mGBA programmatically:

- `oracle_trace.lua` — Captures register state, memory accesses, and execution path
- `screenshot.lua` — Captures frames for visual verification
- `test_api.lua` — Tests the Lua API surface

The mGBA binary builds at `mgba/build/sdl/mgba`.

## Test ROMs

Test ROMs are organized in `test_roms/`:

- `test_roms/roms/` — 39 `.gba` files across 18 test suites
- `test_roms/sources/` — Source code and documentation for each suite

Download script: `bash scripts/setup/download_and_organize_roms.sh`

## Output

The end-user interaction model:

```bash
# Transpile a ROM
cargo run -p gbatopy-cli -- pipeline --rom game.gba --output game.py

# Run the result
python3 game.py
```

The output is a single `.py` file with all runtime code inlined. The only external dependency is `pygame`.

## Current Status (May 2026)

### What Works

| Component | Status | Notes |
|-----------|--------|-------|
| Rust pipeline | ✅ Builds | All 6 crates compile with zero warnings |
| Disassembler | ✅ Partial | Decodes basic ARM/Thumb instructions |
| Python generation | ✅ Syntactically valid | All 39 test ROMs produce valid Python |
| Memory map | ✅ Partial | ROM, EWRAM, IWRAM, MMIO routing |
| Asset extraction | ✅ Partial | Reads palette, tiles, sprites from ROM |

### What Doesn't Work Yet

| Component | Status | Notes |
|-----------|--------|-------|
| Condition code stripping | ❌ | 603+ stubs from suffix mismatch |
| Branch instructions | ❌ | B/BL/BX handlers unimplemented |
| Thumb codegen | ❌ | ~0% coverage |
| PPU rendering | ❌ | Screenshots all identical (black/gradient) |
| APU audio | ❌ | All stub `return 0` |
| DMA transfers | ❌ | Pending flag bug |
| Interrupts | ❌ | Only VBlank flag set |

## PyBoyAdvance Attribution

The Python runtime modules in `crates/gbatopy-cli/assets/gba_runtime/` are derived from [PyBoyAdvance](https://github.com/williamckha/PyBoyAdvance) by williamckha, licensed under the MIT License.

## License

MIT License — See LICENSE file
