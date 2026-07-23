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
│  Codegen     │  Generate Python functions with runtime calls
└──────┬───────┘
       │
       ▼
output.py (standalone Python + pygame)
```

## Crate Structure

The pipeline is implemented as a single Rust crate:

| Crate | Purpose |
|-------|---------|
| `gbatopy-cli` | CLI driver with embedded disassembler and codegen |

The workspace is defined in `Cargo.toml` at the project root.

## ARM/Thumb Processing

The GBA CPU is an ARM7TDMI running the ARMv4T instruction set. It has two instruction encodings:

- **ARM mode** (32-bit instructions) — ~160 unique opcodes
- **Thumb mode** (16-bit instructions) — ~60 unique opcodes

The CPU switches between modes via `BX` instructions. The disassembler decodes both encodings, and the codegen tracks the `CPSR.T` flag for mode switching.

ARM instructions support **conditional execution** — a 4-bit condition code in the upper bits determines whether the instruction executes based on CPSR flags (EQ, NE, GT, LT, CS, CC, MI, PL, VS, VC, HI, LS, GE, GT, AL).

## Function Reconstruction

The codegen recognizes ARM calling conventions to reconstruct functions:

- **Prologue**: `PUSH {lr}`, `SUB sp, sp, #N`
- **Epilogue**: `POP {pc}`, `ADD sp, sp, #N`, `BX lr`
- **Calling convention**: r0-r3 arguments, r0 return value, r4-r11 callee-saved

The codegen produces a `func_map` dictionary mapping entry addresses to Python functions.

## Python Runtime

Generated Python includes an inlined runtime that emulates GBA hardware. The runtime source code is derived from [PyBoyAdvance](https://github.com/williamckha/PyBoyAdvance) (MIT licensed).

| Module | Hardware | Role | Status |
|--------|----------|------|--------|
| `ppu.py` | Picture Processing Unit | Background tiles, sprites, scanline rendering | ⚠️ Mode 0 verified on shades.gba, Mode 3 verified on stripes.gba; Mode 4 partial; Mode 1/2 affine, windows, blend, mosaic = stubs |
| `memory.py` | Bus | Memory-mapped I/O with HAL side effects | ✅ Working |
| `bios.py` | BIOS ROM | Software interrupt handlers (SWI) | ✅ 54 handlers implemented |
| `dma.py` | DMA Controller | Background memory transfers | ✅ All 4 channels operational |
| `timers.py` | Timer | Timer 0-3 with prescaler | ✅ Working |
| `interrupts.py` | IRQ | VBlank/HBlank/VCount interrupt dispatch | ✅ Working |
| `input.py` | Keypad | KEYINPUT register, pygame keyboard mapping | ✅ Working |

MMIO writes trigger hardware behavior through the HAL interface — writing to `DISPCNT` configures the PPU, writing to sound registers triggers APU output, DMA register writes initiate transfers.

## Asset Extraction

ROM data (tiles, palettes, tilemaps, audio samples) is embedded directly in the generated Python as `ROM_DATA = bytearray([...])`. No separate asset files are needed.

## mGBA Verification

The verification pipeline uses a modified mGBA build with extended Lua scripting (branch `extend-lua`). Lua scripts in `scripts/screenshot/` control mGBA programmatically:

- `screenshot.lua` — Captures frames for visual verification
- `compare_screenshots.py` — Compares golden vs transpiled screenshots

The mGBA binary builds at `mgba/build/sdl/mgba`.

## Test ROMs

Test ROMs are organized in `test_roms/`:

- `test_roms/roms/` — 66 `.gba` files across 18 test suites
- `test_roms/sources/` — Source code and documentation for each suite

Download script: `bash scripts/setup/download_roms.sh`

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
| Rust pipeline | ✅ Builds | Zero compiler warnings |
| Disassembler | ✅ Working | ~100% ARM/Thumb coverage |
| Python generation | ✅ Working | All 68 ROMs produce valid Python |
| Memory map | ✅ Working | Full GBA memory layout with mirrors |
| CPU core | ⚠️ Partial | Code-gen generates Python functions; runtime uses PyBoyAdvance modules; STMFD/LDMFD register order bug corrupts stack |
| PPU Mode 3 | ✅ Verified | stripes.gba 100% golden match |
| PPU Mode 0 | ✅ Verified | shades.gba 100% golden match (after 5 bug fixes) |
| PPU Mode 4 | ⚠️ Partial | 8BPP bitmap, palette fallback fixed on hello.gba, not all ROMs verified |
| PPU Mode 1/2 | ⚠️ Stubs | Affine backgrounds, code exists, MMIO broken |
| Sprite rendering | ⚠️ Unverified | OAM parsing + tile fetch implemented, no golden comparison |
| BIOS handlers | ✅ Working | 54 SWI handlers implemented |
| DMA controller | ✅ Working | All 4 channels operational |
| Timers | ✅ Working | 4 timers with cascade mode |
| IRQ system | ✅ Working | ISR dispatch, VBlank/HBlank |
| Input handling | ✅ Working | KEYINPUT/KEYCNT registers |

### What Doesn't Work Yet

| Component | Status | Notes |
|-----------|--------|-------|
| APU audio | ❌ Stub | DMA FIFO infrastructure exists, no synthesis |
| Mode 0 text rendering | ⚠️ Partial | render_text_mode() needs implementation |
| Affine backgrounds | ❌ Out of scope | Mode 1/2 transforms not implemented |
| Windows/Blend/Mosaic | ❌ Out of scope | Advanced PPU features |
| 8BPP tile modes | ❌ Not implemented | Only 4BPP for tiled backgrounds |

## PyBoyAdvance Attribution

The Python runtime modules in `crates/gbatopy-cli/assets/gba_runtime/` are derived from [PyBoyAdvance](https://github.com/williamckha/PyBoyAdvance) by williamckha, licensed under the MIT License.

## License

MIT License — See LICENSE file
