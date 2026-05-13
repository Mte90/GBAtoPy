# Implementation Status

Honest assessment of what works and what doesn't.

## Pipeline

| Stage | Status | Notes |
|-------|--------|-------|
| Disassembler | **Working** | Decodes ~99.4% of ARM opcodes. ~14 unimplemented (SMLAL, UMLAL, BLX reg, RSB). |
| Codegen | **Working** | Generates valid Python for all 41 test ROMs. 40/41 produce syntactically correct output. |
| Multi-function support | **Blocked** | Single function per ROM. Branch targets not analyzed. T2 blocked. |
| Asset extraction | **Not implemented** | Palette, tiles, sprites not extracted yet. |

## Python Runtime

| Module | Status | Notes |
|--------|--------|-------|
| Memory / MMIO | **Working** | 8/16/32-bit read/write implemented. All memory regions mapped. |
| PPU Backgrounds | **Partial** | Mode 3/4 rendering works. Mode 0 (4BPP tiles) working. Default gradient shown when VRAM empty. |
| PPU Sprites | **Missing** | OAM processing unimplemented. No sprites render. |
| APU | **Missing** | Audio synthesis not implemented. DMA FIFO infrastructure exists. |
| DMA | **Stub** | Pending flag logic exists. No actual transfers implemented. |
| BIOS SWI | **Stub** | `bios_swi()` returns 0 for all calls. Specific handlers not implemented. |
| Input | **Working** | Keyboard maps to KEYINPUT register. |
| VBlank | **Stub** | VBlank flag set after render. HBlank/timer interrupts not implemented. |

## End-to-End

| Capability | Works? |
|------------|--------|
| ROM loads and disassembles | **Yes** - 41/41 ROMs |
| Python file generates | **Yes** - 40/41 ROMs (song.gba fails due to size) |
| Python file runs without crash | **Partial** - Executes single function, hits "Unknown PC" on branches |
| Game renders graphics | **No** - Default gradient (VRAM empty) |
| Keyboard input affects game | **Unverified** |

## What Was Fixed (Recent)

1. **r15 initialization** - PC now starts at 0x08000000 instead of 0
2. **Multiply variable names** - Fixed `rr3` → `r3` bug in MUL/MLA/UMULL/SMULL/SWP
3. **16-bit memory access** - Added `read_16`/`write_16` to GBA class
4. **BIOS SWI stub** - Added `bios_swi()` handler (returns 0 for all calls)
5. **Codegen coverage** - Verified ~99.4% ARM opcode coverage

## What Needs Fixing (Priority Order)

1. **Multi-function support (T2)** - Analyze branch targets, split instructions into multiple `func_*` functions
2. **VBlank interrupt** - Games hang waiting for VBlank (stub exists but not triggered)
3. **BIOS SWI handlers** - Implement specific handlers (SoftReset, RegisterRamReset, Sqrt, Div, etc.)
4. **PPU sprites** - OAM parsing and sprite rendering
5. **APU audio** - Implement 4-channel audio synthesis
6. **DMA transfers** - Complete DMA implementation with actual memory copies
7. **Asset extraction** - Extract palette, tiles, sprites from ROM

## Test ROMs

41 ROMs across 18 suites. All disassemble. 40/41 produce valid Python.

| Suite | ROMs | Status |
|-------|------|--------|
| jsmolka/gba-tests | 16 | Valid Python, no graphics |
| armwrestler-gba | 1 | Valid Python, no graphics |
| FuzzARM | 1 | Valid Python, no graphics |
| libbet | 1 | Valid Python, no graphics |
| GBA-Test-Collection | 1 | Valid Python, no graphics |
| destoer/gba_tests | 4 | Valid Python, no graphics |
| enhancedcontrolcheckerGBA | 1 | Valid Python, no graphics |
| gba-sound-demo | 1 | Valid Python, no graphics |
| hw-test | 3 | Valid Python, no graphics |
| FalseDiagonalTest | 1 | Valid Python, no graphics |
| gba-playground | 2 | Valid Python, no graphics |
| tonc | 1 | Valid Python, no graphics |
| blargg | 3 | Valid Python, no graphics |
| misc/custom | 4 | Valid Python, no graphics |
| **song.gba** | 1 | **FAILS** - Python syntax error (too large) |
