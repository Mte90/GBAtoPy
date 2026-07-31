# GBAtoPy

[![License](https://img.shields.io/badge/License-MIT%20v1-blue.svg)](https://spdx.org/licenses/MIT.html#licenseText)
[![Tests](https://img.shields.io/badge/tests-66%2F68%20smoke%20pass-yellow.svg)](docs/testing-framework.md)
[![Status](https://img.shields.io/badge/status-In%20Development-yellow.svg)](docs/roadmap.md)

GBAtoPy is a **transpiler** (a Rust CLI) that converts Game Boy Advance ROMs (`.gba`) into standalone Python files that run with [pygame](https://www.pygame.org/). The output is human-readable, modifiable Python source code that, when executed, reproduces the game's behavior. It is **NOT an emulator** — the goal is a `.py` file you can open, read, and edit.

**Tech stack:** Rust (transpiler), Python (generated runtime), pygame (display).

---

## Implementation Status

Project is in active development. The transpilation pipeline works end-to-end; per-ROM visual verification is tracked in [`docs/reference/test-roms.md`](docs/reference/test-roms.md). See [`docs/roadmap.md`](docs/roadmap.md) for strategy and remaining work.

### Test coverage (68 test ROMs)

| Check | Result |
|-------|--------|
| Transpile to Python (0 instruction decode failures) | 68/68 |
| Smoke test (transpile + syntax check) | 66/68 — `helloAudio.gba`, `rates.gba` fail |
| Visually verified vs mGBA golden (<30% pixel difference) | 24/68 |
| Known failures (smoke or visual) | 4/68 |
| Hang at runtime (IRQ/DMA/timer paths) | 9/68 |
| Transpile + smoke pass, visual not yet verified | 31/68 |

The 24 visually verified ROMs (all pass the <30% threshold vs mGBA golden): `arm`, `bgx`, `bios`, `cond_invalid`, `flash64`, `flash128`, `hello`, `helloWorld`, `hello_world`, `if_ack`, `irq_delay`, `joypad`, `memory`, `mode2`, `mode3`, `mode4`, `none`, `redline`, `retAddr`, `shades`, `sram`, `stripes`, `thumb`, `unsafe`.

Known failures: `helloAudio.gba` and `rates.gba` (smoke failure), `greenswap.gba` (85% diff), `window_midframe.gba` (55% diff).
Runtime hangs: `bgpd`, `dma_priority`, `isr`, `line_timing`, `lyc_midline`, `nes`, `pcmxx`, `sprite-hmosaic`, `timer_change`.

### What works

- **CPU core** — ARM7TDMI: ARM mode (~160 unique opcodes) and Thumb mode (~60 unique opcodes), CPSR flag tracking, all 16 condition codes, global register propagation.
- **BIOS SWI handlers** — 54 handlers (Halt, Div, Sqrt, CpuSet/CpuFastSet, LZ77/Huffman/RLE decompression, ArcTan, ObjAffineSet, BgAffineSet, and more).
- **PPU rendering** — Mode 0 (4BPP text tiles) verified on `shades`, `hello`, `helloWorld`, `hello_world`; Mode 2 (affine) verified on `mode2`; Mode 3 (16-bit bitmap) verified on `stripes`, `mode3`, `bgx`; Mode 4 (8BPP bitmap) verified on `mode4`.
- **Interrupt system** — VBlank/HBlank/VCount dispatch, timer IRQs (0-3), DMA IRQs, keypad IRQ, IE/IF/IME handling with ARM/Thumb mode switching.
- **DMA** — 4 channels with all trigger modes; HBlank DMA verified via `bgx`.
- **Timers** — 0-3 with prescaler (1/64/256/1024) and cascade mode.
- **Input** — KEYINPUT / KEYCNT registers.
- **Save types** — SRAM, Flash64, Flash128, none.
- **Memory map** — ROM, EWRAM, IWRAM, MMIO, VRAM, Palette RAM, OAM with mirrors.

### What does NOT work (or is not verified)

- **PPU Mode 1 affine** — code exists, not verified.
- **Window layers (WIN0/WIN1/OBJWIN), blend, mosaic** — register stubs only, not functional.
- **Sprite rendering** — code exists, not verified against golden.
- **Audio synthesis** — APU infrastructure (4 channels, FIFO A/B) exists, not verified end-to-end; no sound output confirmed.
- **DMA audio (FIFO A/B)** — not implemented (`song.gba`, `rates.gba` fail).
- **RTC** — not implemented.
- **Automated screenshot-golden comparison** — 32 golden screenshots exist in `scripts/screenshot/golden/`, but comparison is not wired into CI; verification is currently manual.

---

## Quick Start

### Prerequisites

- **Rust toolchain** (1.70+): `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **Python 3.10+**
- **pygame**: `pip install pygame`
- **SDL2** (optional, for display): `sudo apt install libsdl2-dev`

### Build

```bash
cargo build --release
```

### Transpile a ROM

```bash
cargo run -p gbatopy-cli -- pipeline --rom <rom.gba> --output /tmp/<name>.py
```

Example:

```bash
cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py
```

### Run the generated Python

Headless mode (for testing / screenshots):

```bash
python3 /tmp/<name>.py --headless --frame=60 --screenshot /tmp/<name>.png
```

Interactive mode (with display):

```bash
python3 /tmp/<name>.py --scale=2
```

### CLI arguments (generated runtime)

- `--headless`: run without display (for testing/screenshot)
- `--frame=N`: run exactly N frames then exit
- `--screenshot=FILE`: save a screenshot at end
- `--scale=N`: scale the display by N (e.g., 3 = 720x480 pixels)
- `--pc-trace=FILE`, `--trace-n=N`, `--max-instrs=N`: built-in execution tracing (see `docs/how-debug.md`)

---

## Test ROMs

Test ROMs are **not included** in the repository (see `.gitignore`). Download and organize the 68 test ROMs with:

```bash
bash scripts/setup/download_roms.sh
```

This populates `test_roms/roms/`. The ROM catalog with per-ROM hardware analysis is in [`docs/reference/test-roms.md`](docs/reference/test-roms.md).

---

## Verification

mGBA is the reference implementation: if mGBA renders a ROM correctly, the transpiled Python must produce pixel-matching output. Verify with screenshots, not just "does it run".

### One-shot verification

Transpile, run, and compare against a golden screenshot in one step:

```bash
./scripts/verify/verify_rom.sh <rom> --no-golden
```

### Manual verification

```bash
# Transpile
cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py

# Run transpiled output
python3 /tmp/stripes.py --headless --frame=60 --screenshot /tmp/stripes_transpiled.png

# Compare against mGBA golden (PASS if <30% difference)
python3 scripts/verify/compare_screenshots.py -s /tmp/stripes.png /tmp/stripes_transpiled.png --threshold 30
```

### Smoke test (syntax only)

```bash
# All ROMs — transpile + syntax check only (does NOT verify graphics/audio)
./scripts/run-all-tests.sh
```

> **Note:** `run-all-tests.sh` only checks that the generated Python compiles. It does NOT verify graphics or audio. For full verification use the screenshot comparison above.

---

## mGBA Integration

For golden screenshots and debugging, GBAtoPy uses **mGBA** with custom patches that add a `--script` flag and Lua scripting hooks. mGBA source is **not** included in this repository.

The custom patches live in [`mgba-custom-patches.diff`](mgba-custom-patches.diff). The upstream Lua scripting extension is tracked in [mGBA PR #3752](https://github.com/mgba-emu/mgba/pull/3752).

### Build mGBA with scripting

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

### Take a golden screenshot

```bash
./mgba/build/sdl/mgba --script scripts/screenshot/screenshot.lua test_roms/roms/stripes.gba
```

Lua API exposed by the patched mGBA:

- `emu:currentFrame()` — get current frame number
- `emu:runFrame()` — advance one frame
- `emu:screenshot(filename)` — save a screenshot to PNG
- `callbacks:add("frame", fn)` — register a per-frame callback

---

## Architecture

```
ROM bytes -> Disassembly -> Python code gen -> Executable Python
```

- **Disassembler** (`crates/gbatopy-disasm/`) — decodes ARM/Thumb instructions (~100% coverage).
- **Code generator** (`crates/gbatopy-cli/src/codegen/`) — ARM/Thumb to Python translation.
- **Python runtime** (`crates/gbatopy-cli/assets/gba_runtime/`) — CPU, PPU, memory, DMA, timers, APU modules embedded into the generated Python.
- **Test framework** (`crates/gbatopy-test/`) — Rust-based test runner with parallel execution and configurable per-ROM testing via `test-roms-config.toml`.

The generated `.py` file is standalone (depends only on `pygame`, plus `numpy` if needed), readable, and modifiable.

---

## References

- [GBA Hardware Manual (GBATEK)](https://github.com/mgba-emu/gbatek/blob/gh-pages/gba.md)
- [Roadmap & Status](docs/roadmap.md)
- [Test ROM Catalog](docs/reference/test-roms.md)
- [Runtime Architecture](docs/runtime-architecture.md)
- [Debugging Guide](docs/how-debug.md)
- [mGBA Scripting PR #3752](https://github.com/mgba-emu/mgba/pull/3752)

---
