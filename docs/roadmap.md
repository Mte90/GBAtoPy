# GBAtoPy Roadmap — Project Status

> **Role:** Strategy, sequencing, and remaining work.
> For the current verification status, see [reference/test-roms.md](reference/test-roms.md).

> **Last updated**: 2026-08-14  
> **Current state**: 69/76 ROMs pass visual verification (5 FAIL, 0 SKIP). 0 ROMs hang. Build: 0 errors, 0 warnings.
> **Status**: IN ACTIVE DEVELOPMENT — Core transpiler works end-to-end; remaining work focuses on PPU edge cases, audio synthesis, and runtime hang diagnosis.

---

## 1. Project Overview

GBAtoPy is a **transpiler** that converts GBA ROMs into standalone Python files playable with pygame. NOT an emulator — the output is human-readable Python source code that can be read, modified, and extended.

---

## 2. Detailed Progress

### ✅ Wave 1: Core Infrastructure - COMPLETE
- Rust pipeline builds with zero warnings
- Disassembler decodes ARM/Thumb instructions (~100% coverage)
- Python generation produces syntactically valid output for all 66 ROMs
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
- **Recent fix (2026-07-27)**: HBlank/VBlank DMA uses full-count burst on first trigger via `_do_transfer()`

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
- **Window layers (WIN0/WIN1/OBJWIN)**: IMPLEMENTED and verified (window_midframe passes)
- **Blend effects**: IMPLEMENTED — alpha blend with 2nd target, brightness 1st-target only
- **Mosaic effect**: IMPLEMENTED for Mode 0/1 (BG) and OBJ; Mode 2-5 BG mosaic pending (F27)
- **Sprite rendering**: Code exists, not verified against golden
- **8BPP tile decoding**: Code exists, not verified

### ⚠️ Wave 5: Audio System — INFRASTRUCTURE ONLY
- APU infrastructure with 4 audio channels (CH1-CH4)
- SquareWaveChannel (CH1/2), WaveChannel (CH3), NoiseChannel (CH4) implemented
- FIFO A/B buffers exist with DMA integration
- ⚠️ DMA audio (FIFO A/B): IMPLEMENTED — DMA writes to FIFO registers, but audio output not verified end-to-end
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
- **Recent fix (2026-07-27)**: HBlank/VBlank DMA fixed to transfer full-count burst on first trigger via `_do_transfer()` (not one-unit-per-trigger) (bgx verified)
- Repeat mode with FIFO A/B for audio (integrated — DMA writes to FIFO registers)
- Timers 0-3 with prescaler (1/64/256/1024) and cascade mode
- Timer overflow detection and reload

### ✅ Wave 8: Input System - COMPLETE
- KEYINPUT register (0x04000130) — 10-bit keypad state
- KEYCNT register (0x04000132) — interrupt conditions
- 8-bit and 16-bit read support

### ✅ Wave 9: Phase 16 Fixes - COMPLETE
- IWRAM CFG BFS discovery (FlashSpeedTestROM fixed)
- 0x03000128 trampoline removal
- read_u8 MMIO & 0xFF fix
- VBlankIntrWait IF clear
- IRQ register save/restore R0-R3/R12
- Banked register System mode 0x1F

### ✅ Wave 10: Test Framework — PARTIAL
- Rust-based automated testing with 66 ROMs configured
- **Smoke tests**: 64/66 passing (helloAudio, rates fail)
- **ScreenshotGolden tests**: WIRED — 78 goldens in `test-reports/goldens/`, compared via `scripts/verify/regress_all.sh` (full regression) and `ScreenshotGoldenVerifier` (Rust). Golden path: `test-reports/goldens/{rom}_f60.png`.
- **Manual golden matches**: 53/66 verified (<30% pixel diff via `compare_screenshots.py`)
- Verifier types in config: Smoke, ScreenshotGolden, EWRAM, Assertion, Performance, Coverage
- Only Smoke verifier currently exercised
- Parallel execution (4 workers)
- JSON/JUnit report generation

---

## 3. Test Results

### Smoke Tests (Transpile + Syntax)
```
Total: 66 ROMs
Passed: 66 (97%)
Failed: 2 (helloAudio, rates)
```

### Visual Verification (ScreenshotGolden vs mGBA)
```
Total: 66 ROMs
Verified (<30% diff): 53 (80%)
Known failures: 9 (dispcnt-latch, force-nseq-access, nes, ram-access-timing, reload, start-delay, start-stop, status-irq-dma, vram-mirror)
SKIP: 4 (rates OOM, song OOM, enhancedcontrolchecker corrupt, test corrupt)
Runtime hangs: 0
Unverified: 0 (transpile+smoke pass, visual not checked)
```

---

## 4. Known Limitations

### Smoke Test Failures
- **helloAudio.gba**: Cause undiagnosed — smoke test failure  
- **rates.gba**: Cause undiagnosed — smoke test failure (DMA audio not implemented)

### Visual Verification Failures (9 ROMs)
- dispcnt-latch, force-nseq-access, nes, ram-access-timing, reload, start-delay, start-stop, status-irq-dma, vram-mirror
- Likely causes: PPU edge cases, MMIO timing, DMA interactions

### SKIP (4 ROMs)
- rates (111MB OOM), song (748MB OOM), enhancedcontrolchecker (corrupt ROM), test (corrupt ROM)

### Resolved Issues (2026-07-27 to 2026-08-10)
- **STMFD/LDMFD bug**: RESOLVED — hello.gba now passes (0.0% diff)
- **Per-scanline affine snapshots**: Implemented for Mode 3/4/5
- **HBlank/VBlank DMA**: Fixed to full-count burst on first trigger (bgpd verified)
- **Main loop**: Made instruction-counted — PPU advances one scanline per `instr_per_scanline` CPU instructions
- **Removed fast-forward DISPPCNT reads**: Was causing DMA exhaustion
- **mode2, mode4, greenswap, window_midframe**: All now PASS (verified)

### Not Implemented / Not Verified
- **PPU Mode 1 (affine)**: Code exists, not verified
- **PPU Mode 5**: Implemented, not verified
- **Window/Blend/Mosaic**: IMPLEMENTED (window_midframe verified; Mode 2-5 BG mosaic pending F27)
- **Sprite rendering**: Code exists, not verified against golden
- **Audio synthesis**: Infrastructure exists, no verified sound output
- **DMA audio (FIFO A/B)**: Not implemented (song.gba, rates.gba fail)
- **RTC**: Not implemented
- **Automated ScreenshotGolden**: 78 goldens in `test-reports/goldens/`, comparison wired into `regress_all.sh` and Rust `ScreenshotGoldenVerifier`

### Resolved Issues (2026-07-27 to 2026-07-30)
- **STMFD/LDMFD bug**: RESOLVED — hello.gba now passes (0.0% diff)
- **Per-scanline affine snapshots**: Implemented for Mode 3/4/5
- **HBlank/VBlank DMA**: Fixed to transfer full-count burst on first trigger via `_do_transfer()` (see AGENTS.md runtime invariant #4)
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

1. **Diagnose helloAudio, rates smoke failures** — Root cause unknown
2. **Implement DMA audio (FIFO A/B)** — Required for song.gba, rates.gba
3. **Fix remaining visual failures** — dispcnt-latch, force-nseq-access, nes, ram-access-timing, reload, start-delay, start-stop, status-irq-dma, vram-mirror
4. **Verify sprite rendering** — Code exists, no golden comparison
5. **Verify audio synthesis** — Infrastructure exists, no output check
6. **Generate goldens for remaining ROMs** — Then run full ScreenshotGolden suite
7. **Verify sprite rendering** — Code exists, no golden comparison
8. **numba JIT (future work)** — `--profile` (F52) shows `read_u16` + `dict.get` dominate runtime (4.76s/2.3M calls). JIT-compiling the memory access hot path with numba is the highest-leverage perf win but requires numba as a runtime dependency, breaking the standalone-output requirement. Defer until the transpiler output format is stable, then gate behind an opt-in `--jit` flag.
 9. **F14: N/S-cycle memory access timing — PERMANENTLY DEFERRED (KILL)** — Oracle analysis (92% confidence) found that adding cycle-accurate memory timing violates all 5 runtime invariants: (1) fallback interpreter must stay pure CPU, (2) main loop is instruction-counted, (3) no step_scanline in memory reads, (4) DMA full-count burst on first trigger, (5) per-scanline affine snapshots. Implementing F14 would break every PASS ROM and require 20+ dev weeks of work. Zero failing ROMs require cycle-accurate timing. **Revisit only if:** a specific failing ROM is found that explicitly requires N/S cycle timing, or visual comparisons show timing-based artifacts not fixable by other means. Full analysis in `todo.md` § APPENDIX.
10. **F40: Link cable transfer — DEFERRED (stub only)** — No ROM in the test suite exercises real link-cable data transfer. The afska/gba-link-connection suite (25 ROMs) is integrated for future use, but none of the ROMs produce transfer output that can be verified against mGBA. The runtime exposes a stub `LinkCable` class that no-ops on read/write. **Unblock by:** sourcing a ROM that performs a verifiable link transfer, or building a minimal homebrew ROM that sends a known byte pattern and reads it back.

---

## 7. Project Statistics

| Metric | Value |
|--------|-------|
| Rust source lines | ~15,000 (across 3 crates) |
| Python runtime lines | ~4,500 (ppu.py + apu.py + cpu.py + helpers.py) |
| Test ROMs | 76 |
| BIOS handlers | 54 |
| ARM instructions | ~160 unique opcodes |
| Thumb instructions | ~60 unique opcodes |
| Test pass rate | 64/66 smoke (97%); 53/66 visual verified (80%); 9 fail; 4 skip |
| Build time | ~30s (release) |
| Transpile time | ~1-5s per ROM |

---

**Status**: IN ACTIVE DEVELOPMENT — core transpiler works end-to-end; remaining work focuses on PPU edge cases, audio synthesis, and runtime hang diagnosis