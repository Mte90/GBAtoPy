# Automated Testing Framework

This document describes the testing strategy for GBAtoPy, based on analysis of the 68 test ROMs and their expected output formats.

---

## Testing Strategies

The GBA emulation community uses four verification methods. GBAtoPy should support all four.

### 1. Screenshot Comparison (PPU Rendering)

Compare transpiled Python output against known-correct reference images.

**Golden reference ROMs** (hw-test provides `expected.png`):

| ROM | Tests | Reference |
|-----|-------|-----------|
| greenswap.gba | Green swap register | `test_roms/sources/hw-test/ppu/greenswap/expected.png` |
| bgx.gba | BG2/BG3 affine transform latching | `test_roms/sources/hw-test/ppu/bgx/expected.png` |
| bgpd.gba | BG2PD/BG3PD latching timing | `test_roms/sources/hw-test/ppu/bgpd/expected.png` |
| sprite-hmosaic.gba | Sprite horizontal mosaic | `test_roms/sources/hw-test/ppu/sprite-hmosaic/expected.png` |
| dispcnt-latch.gba | DISPCNT latching mid-frame | `test_roms/sources/hw-test/ppu/dispcnt-latch/expected.png` |

**mGBA oracle ROMs** (capture golden from mGBA, then compare):

| ROM | Tests |
|-----|-------|
| stripes.gba | Mode 0 tile rendering with diagonal stripes |
| shades.gba | Mode 0 palette gradient |
| hello.gba | Mode 0 text rendering |
| helloWorld.gba | Mode 0 text rendering |
| hello_world.gba | Mode 0 text rendering |

**How it works**: Transpile ROM → run with `--headless --frame=N --screenshot` → compare pixel-by-pixel against reference. Tolerance of ±10 per channel handles minor rendering differences.

**Existing tool**: `scripts/verify/visual_test.py`

---

### 2. eWRAM Dump Parsing (CPU Correctness)

FuzzARM ROMs dump structured test results to eWRAM at `0x02000000`.

**ROMs**: `ARM_Any.gba`, `ARM_DataProcessing.gba`, `THUMB_Any.gba`, `THUMB_DataProcessing.gba`, `FuzzARM.gba`

Each ROM contains 10,000 randomized instruction tests. When a test fails, it writes a 16-word record to eWRAM:

```
Offset  Size   Content
0x00    1 word ['AAAA' or 'TTTT'] — ARM or THUMB mode
0x04    2 words [opcode + shift] — e.g. "tst lsl     " (12 chars padded)
0x0C    1 word [reserved]

0x10    1 word [initial r0]
0x14    1 word [initial r1]
0x18    1 word [initial r2]
0x1C    1 word [initial CPSR]

0x20    1 word [actual r3]
0x24    1 word [actual r4]
0x28    1 word [0x00000000]
0x2C    1 word [actual CPSR]

0x30    1 word [expected r3]
0x34    1 word [expected r4]
0x38    1 word [0x00000000]
0x3C    1 word [expected CPSR]
```

When all tests pass, the ROM displays a green screen (Mode 4) and stops.

**Verification approach**: 
1. Transpile → run with `--headless --frame=N`
2. Dump eWRAM from runtime memory
3. Parse records at `0x02000000`
4. No failure records = PASS
5. Failure records present = report opcode, got vs expected

**Total coverage**: 50,000 instruction tests (5 ROMs × 10,000 each).

**Requires**: Adding `--dump-memory` flag to the Python runtime to expose eWRAM after execution.

---

### 3. Pass/Fail Screen Detection (Test ROM Display)

Most gba-tests-master ROMs display results on screen in BG Mode 4.

**How it works** (from gba-tests-master README):
> "Each ROM contains multiple tests. Either all of them pass or the number of the first failed one is displayed on the screen."

- Screen is blank/green → all tests passed
- Screen shows a number → that test number failed

**ROMs using this pattern**:

| ROM | Category | Tests |
|-----|----------|-------|
| arm.gba | CPU | ARM instruction set (flags, conditions, shifts, branches, PSR transfer) |
| thumb.gba | CPU | Thumb instruction set (arithmetic, logical, shifts, branches, memory) |
| bios.gba | BIOS | SWI handlers (Div, Sqrt, CpuSet, LZ77, Huffman, RLE) |
| memory.gba | Memory | RAM read/write, mirroring, wait states |
| unsafe.gba | CPU | Edge case instructions |
| armwrestler.gba | CPU | ARM7DI load-store, multiply, SWP |
| armwrestler-gba-fixed.gba | CPU | Fixed load-store tests |
| cond_invalid.gba | CPU | Conditional flag behavior |
| retAddr.gba | CPU | Return address handling (BL, BX, POP pc) |
| dma_priority.gba | DMA | DMA priority handling |
| isr.gba | IRQ | Interrupt service routines |
| if_ack.gba | IRQ | Interrupt flag acknowledgment |
| irq_delay.gba | IRQ | IRQ delay timing |
| joypad.gba | Keypad | Key interrupt handling |
| line_timing.gba | PPU | Scanline timing |
| lyc_midline.gba | PPU | LY=LYC coincidence mid-frame |
| window_midframe.gba | PPU | Window rendering mid-frame |

**Verification approach**: Screenshot at frame 60 → check if screen is blank (PASS) or contains a number (FAIL). Simple pixel analysis can detect non-blank screens.

---

### 4. Assertion Output Parsing (hw-test C Tests)

hw-test ROMs written in C use explicit assertion functions:

```c
test_expect("HBLANK=0", 144, hblank_0);       // Exact match
test_expect_hex("M0 10000h", 0xABAD1DEA, val); // Hex match
test_expect_range("name", lo, hi, actual);       // Range match
```

They print "PASS" or "FAIL" text on screen.

**ROMs**: `status-irq-dma.gba`, `vram-mirror.gba`, `burst-into-tears.gba`, `force-nseq-access.gba`, `latch.gba`, `start-stop.gba`, `reload.gba`, `128kb-boundary.gba`, `haltcnt.gba`, `timer_change.gba`

**Verification approach**: Screenshot → pixel pattern matching for "PASS"/"FAIL" text.

---

## ROM Classification by Test Strategy

| Strategy | ROMs | Count |
|----------|------|-------|
| Screenshot (golden) | greenswap, bgx, bgpd, sprite-hmosaic, dispcnt-latch | 5 |
| Screenshot (mGBA oracle) | stripes, shades, hello, helloWorld, hello_world | 5 |
| Pass/fail screen | arm, thumb, bios, memory, unsafe, armwrestler, armwrestler-gba-fixed, cond_invalid, retAddr, dma_priority, isr, if_ack, irq_delay, joypad, line_timing, lyc_midline, window_midframe | 17 |
| eWRAM dump | ARM_Any, ARM_DataProcessing, THUMB_Any, THUMB_DataProcessing, FuzzARM | 5 |
| Assertion text | status-irq-dma, vram-mirror, burst-into-tears, force-nseq-access, latch, start-stop, reload, 128kb-boundary, haltcnt, timer_change | 10 |
| Smoke only | nes, enhancedcontrolchecker, redline, rtc-demo, helloAudio, test, song, rates, pcmxx, basic-timing, exact-timing, start-delay, sram, flash64, flash128, none, mode2, mode3, mode4, ram-access-timing, cancel-irq-ie, cancel-irq-if, cancel-irq-ime | 23 |

**Note**: Some ROMs fit multiple strategies. FuzzARM ROMs also display results in Mode 4 (visual) in addition to eWRAM dumps.

---

## Existing Test Infrastructure

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/verify/visual_test.py` | Automated screenshot comparison (8 ROMs, 4 frames each) |
| `scripts/verify_all_roms.py` | Batch transpile + syntax check for all 68 ROMs |
| `scripts/verify/coverage_tracker.py` | Feature coverage analysis of transpiled Python |
| `scripts/screenshot/compare_screenshots.py` | Single ROM mGBA golden vs transpiled comparison |
| `scripts/screenshot/screenshot.lua` | mGBA Lua script for golden screenshot capture |

### Pytest Suite

`crates/gbatopy-cli/tests/python/` — 12 test files:

- `test_cpu.py` — CPU registers, CPSR flags, all 16 condition codes, thumb mode
- `test_ppu.py` — PPU creation, register writes, framebuffer, render_frame
- `test_dma.py` — DMA controller
- `test_apu.py` — Audio processing unit
- `test_timers.py` — Timer hardware
- `test_interrupts.py` — IRQ system
- `test_memory.py` — Memory mapping
- `test_mmio.py` — MMIO register handlers
- `test_input.py` — Keypad input
- `test_exceptions.py` — Exception handling
- `test_rom.py` — ROM loading

### Rust Tests

- `crates/gbatopy-disasm/tests/test_halfword_load_store.rs` — ARM LDRH/STRH/LDRSB/LDRSH
- `crates/gbatopy-disasm/tests/test_mul_mla.rs` — ARM MUL/MLA
- `crates/gbatopy-cli/src/codegen/patterns.rs` — 5 codegen unit tests

---

## Proposed Test Levels

### Level 1: Transpile Smoke Test

For every ROM: transpile → syntax check → runs without crash.

```bash
cargo run -p gbatopy-cli -- pipeline --rom $ROM --output /tmp/test.py
python3 -m py_compile /tmp/test.py
SDL_VIDEODRIVER=dummy python3 /tmp/test.py --headless --frame=1
```

Extension: detect stubs (`pass`, `return 0`, `NotImplementedError`) in generated code.

### Level 2: Visual Regression Test

Two sub-suites:

**Suite A** (no mGBA needed — uses hw-test golden images):
- greenswap, bgx, bgpd, sprite-hmosaic, dispcnt-latch
- Compare transpiled output against `expected.png`

**Suite B** (mGBA oracle):
- stripes, shades, hello, helloWorld, hello_world
- Capture golden from mGBA → transpile → compare

### Level 3: CPU Correctness Test

FuzzARM eWRAM dump verification:

```bash
# Transpile FuzzARM ROM
cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/ARM_Any.gba --output /tmp/arm_any.py

# Run with memory dump
python3 /tmp/arm_any.py --headless --frame=600 --dump-memory /tmp/ewram.bin

# Parse eWRAM dump for failure records
python3 scripts/verify/fuzzarm_parser.py /tmp/ewram.bin
```

Requires adding `--dump-memory` to the Python runtime.

### Level 4: Pass/Fail Screen Detection

For gba-tests-master ROMs: screenshot at frame 60 → detect blank screen (PASS) or test number (FAIL).

```bash
cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/arm.gba --output /tmp/arm.py
SDL_VIDEODRIVER=dummy python3 /tmp/arm.py --headless --frame=60 --screenshot /tmp/arm_result.png
python3 scripts/verify/screen_check.py /tmp/arm_result.png
# Output: PASS (blank screen) or FAIL: test #42 (number detected)
```

---

## Implementation Priority

1. **Extend `visual_test.py`** with hw-test golden images (Suite A)
2. **Add `--dump-memory` flag** to Python runtime
3. **Build FuzzARM eWRAM parser** (`scripts/verify/fuzzarm_parser.py`)
4. **Build screen pass/fail detector** (`scripts/verify/screen_check.py`)
5. **Create unified test runner** that orchestrates all levels
6. **Add GitHub Actions CI** with the unified runner
