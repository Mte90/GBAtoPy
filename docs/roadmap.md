# GBAtoPy Roadmap — Project Status

> **Role:** Strategy, sequencing, and remaining work.
> For the current verification status, see [reference/test-roms.md](reference/test-roms.md).

> **Last updated**: 2026-07-30
> **Current state**: 68/68 ROMs transpile to Python (0 instruction decode failures). 66/68 pass smoke test (helloAudio.gba, rates.gba fail). 24/68 visually verified vs mGBA golden (<30% pixel difference). Build: 0 errors, 0 warnings.
> **Status**: IN ACTIVE DEVELOPMENT — Core transpiler works end-to-end; remaining work focuses on PPU edge cases, audio synthesis, and runtime hang diagnosis.

---

## 1. Project Overview

GBAtoPy is a **transpiler** that converts GBA ROMs into standalone Python files playable with pygame. NOT an emulator — the output is human-readable Python source code that can be read, modified, and extended.

---

## 2. Detailed Progress

### ✅ Wave 1: Core Infrastructure - COMPLETE
- Rust pipeline builds with zero warnings
- Disassembler decodes ARM/Thumb instructions (~100% coverage)
- Python generation produces syntactically valid output for all 68 ROMs
- Memory map implemented (ROM, EWRAM, IWRAM, MMIO, VRAM, Palette, OAM) with mirrors
- Basic block merging (52-80% code size reduction)

### ✅ Wave 2: CPU Core - COMPLETE
- ARM7TDMI core implemented (849 lines in arm7tdmi.py + 706 lines in cpu.py)
- All ARM data processing instructions (MOV, ADD, SUB, ORR, AND, EOR, BIC, MVN, SBC, ADC)
- Load/store instructions (LDR, STR, LDRH, STRH, LDRB, STRB) with PC-relative addressing
- Branch instructions (B, BL, BLX, BX, CBZ, CBNZ) with all 16 condition codes
- Multiply instructions (MUL, MLA)
- MRS/MSR, SWP/SWPB, LDM/STM (all variants: IA/IB/DA/DB + writeback)
- Thumb mode codegen (~100% coverage)
- CPSR flag tracking (N/Z/C/V) with all 16 condition codes
- Global register propagation across function boundaries
- **Recent fix (2026-07-27)**: Fallback interpreter refactored to pure CPU executor — no PPU stepping

### ✅ Wave 3: BIOS Handlers - COMPLETE
- 54 BIOS SWI handlers implemented in arm7tdmi.py
- Core handlers: Halt, IntrWait, VBlankIntrWait, Div, Sqrt, DivArm
- CPU operations: CPUSet, CPUFastSet, RegisterRamReset
- Decompression: LZ77, Huffman, RLE (LZ77UnComp, HuffmanUnComp, RLUnComp)
- Arithmetic: ArcTan, ArcTan2, BitCount, Sin, Cos, Sqrt
- Geometry: ObjAffineSet, BgAffineSet
- MIDI operations, Time functions, Sound control

### ✅ Wave 4: PPU Rendering — PARTIAL
- **Mode 0 (4BPP text)**: Verified on shades, hello, helloWorld, hello_world (all <30% diff vs mGBA)
- **Mode 2 (affine)**: Verified on mode2.gba (20.0% diff)
- **Mode 3 (16-bit bitmap)**: Verified on stripes, mode3, bgx (all 0.0% diff)
- **Mode 4 (8BPP bitmap)**: Verified on mode4 (0.0% diff)
- **Mode 1 (affine)**: Code exists, not verified
- **Mode 5**: Implemented, not verified
- **Per-scanline affine parameter snapshots**: Implemented for Mode 3/4/5 (2026-07-27)
- **Window layers (WIN0/WIN1/OBJWIN)**: Register stubs only — NOT functional
- **Blend effects**: Register stubs only — NOT functional
- **Mosaic effect**: Register stubs only — NOT functional
- **Sprite rendering**: Code exists, not verified against golden
- **8BPP tile decoding**: Code exists, not verified

### ⚠️ Wave 5: Audio System — INFRASTRUCTURE ONLY
- APU infrastructure with 4 audio channels (CH1-CH4)
- SquareWaveChannel (CH1/2), WaveChannel (CH3), NoiseChannel (CH4) implemented
- FIFO A/B buffers exist
- ⚠️ DMA audio (FIFO A/B) NOT implemented — song.gba, rates.gba fail
- ⚠️ NOT verified end-to-end — no sound output confirmed against golden

### ✅ Wave 6: Interrupt System - COMPLETE
- VBlank/HBlank/VCount interrupt dispatch
- Timer interrupts (0-3)
- DMA interrupts (all 4 channels)
- Keypad interrupt
- IRQ handler with ARM/Thumb mode switching
- IE/IF/IME register handling

### ✅ Wave 7: DMA & Timers - COMPLETE
- 4 DMA channels (0-3) with all trigger modes (immediate/VBlank/HBlank/special)
- 16/32-bit transfers with inc/dec/fixed address modes
- **Recent fix (2026-07-27)**: HBlank/VBlank DMA fixed to transfer one unit per trigger (bgx verified)
- Repeat mode with FIFO A/B for audio (infrastructure exists, not integrated)
- Timers 0-3 with prescaler (1/64/256/1024) and cascade mode
- Timer overflow detection and reload

### ✅ Wave 8: Input System - COMPLETE
- KEYINPUT register (0x04000130) — 10-bit keypad state
- KEYCNT register (0x04000132) — interrupt conditions
- 8-bit and 16-bit read support

### ✅ Wave 9: Test Framework — PARTIAL
- Rust-based automated testing with 68 ROMs configured
- **Smoke tests**: 66/68 passing (helloAudio, rates fail)
- **ScreenshotGolden tests**: NOT YET WIRED — 32 goldens exist in `scripts/screenshot/golden/` but automated comparison is not in the test runner
- **Manual golden matches**: 24/68 verified (<30% pixel diff via `compare_screenshots.py`)
- Verifier types in config: Smoke, ScreenshotGolden, EWRAM, Assertion, Performance, Coverage
- Only Smoke verifier currently exercised
- Parallel execution (4 workers)
- JSON/JUnit report generation

---

## 3. Test Results

### Smoke Tests (Transpile + Syntax)
```
Total: 68 ROMs
Passed: 66 (97%)
Failed: 2 (helloAudio, rates)
```

### Visual Verification (ScreenshotGolden vs mGBA)
```
Total: 68 ROMs
Verified (<30% diff): 24 (35%)
Known failures: 4 (helloAudio, rates, greenswap 85% diff, window_midframe 55% diff)
Runtime hangs: 9 (bgpd, dma_priority, isr, line_timing, lyc_midline, nes, pcmxx, sprite-hmosaic, timer_change)
Unverified: 31 (transpile+smoke pass, visual not checked)
```

---

## 4. Known Limitations

### Smoke Test Failures
- **helloAudio.gba**: Cause undiagnosed — smoke test failure
- **rates.gba**: Cause undiagnosed — smoke test failure (DMA audio not implemented)

### Runtime Hangs (9 ROMs)
- bgpd, dma_priority, isr, line_timing, lyc_midline, nes, pcmxx, sprite-hmosaic, timer_change
- Likely causes: IRQ/DMA/timer path bugs, infinite loops in wait handlers

### Not Implemented / Not Verified
- **PPU Mode 1 (affine)**: Code exists, not verified
- **PPU Mode 5**: Implemented, not verified
- **Window/Blend/Mosaic**: Register stubs only — not functional
- **Sprite rendering**: Code exists, not verified against golden
- **Audio synthesis**: Infrastructure exists, no verified sound output
- **DMA audio (FIFO A/B)**: Not implemented (song.gba, rates.gba fail)
- **RTC**: Not implemented
- **Automated ScreenshotGolden**: 32 goldens exist, comparison not wired into CI

### Resolved Issues (2026-07-27 to 2026-07-30)
- **STMFD/LDMFD bug**: RESOLVED — hello.gba now passes (0.0% diff)
- **Per-scanline affine snapshots**: Implemented for Mode 3/4/5
- **HBlank/VBlank DMA**: Fixed to transfer one unit per trigger
- **Main loop**: Made instruction-counted — PPU advances one scanline per `instr_per_scanline` CPU instructions
- **Removed fast-forward DISPPCNT reads**: Was causing DMA exhaustion

---

## 5. Build & Test Commands

```bash
# Build transpiler
cargo build --release

# Transpile a ROM
cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py

# Run generated Python
python3 /tmp/stripes.py --headless --frame=60 --screenshot=/tmp/stripes.png

# Verify screenshot
python3 scripts/verify/compare_screenshots.py -s /tmp/stripes.png /tmp/stripes_transpiled.png --threshold 30

# Run all smoke tests
./scripts/run-all-tests.sh

# Run specific ROM test
python3 scripts/run_tests.py --level 3 --rom stripes
```

---

## 6. Next Steps (Priority Order)

1. **Diagnose bgpd runtime hang** — First priority among hanging ROMs; likely DMA/PPU timing issue
2. **Wire ScreenshotGolden into CI** — 32 goldens exist, comparison not automated. Highest-leverage: converts "works/doesn't work" from assertion to fact.
3. **Diagnose helloAudio, rates smoke failures** — Root cause unknown
4. **Implement DMA audio (FIFO A/B)** — Required for song.gba, rates.gba
5. **Debug remaining hang ROMs** — isr, line_timing, lyc_midline, nes, pcmxx, sprite-hmosaic, timer_change, dma_priority
6. **Verify sprite rendering** — Code exists, no golden comparison
7. **Verify audio synthesis** — Infrastructure exists, no output check
8. **Generate goldens for remaining 36 ROMs** — Then run full ScreenshotGolden suite
9. **Implement Window/Blend/Mosaic** — Register stubs only, not functional

---

## 7. Project Statistics

| Metric | Value |
|--------|-------|
| Rust source lines | ~15,000 (across 3 crates) |
| Python runtime lines | ~4,500 (ppu.py + apu.py + cpu.py + helpers.py) |
| Test ROMs | 68 |
| BIOS handlers | 54 |
| ARM instructions | ~160 unique opcodes |
| Thumb instructions | ~60 unique opcodes |
| Test pass rate | 66/68 smoke (97%); 24/68 visual verified (35%) |
| Build time | ~30s (release) |
| Transpile time | ~1-5s per ROM |

---

**Status**: IN ACTIVE DEVELOPMENT — core transpiler works end-to-end; remaining work focuses on PPU edge cases, audio synthesis, and runtime hang diagnosis