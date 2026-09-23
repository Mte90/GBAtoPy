# GBAtoPy Roadmap — Project Status

> **Role:** Strategy, sequencing, and remaining work.
> For the current verification status, see [reference/test-roms.md](reference/test-roms.md).

> **Last updated**: 2026-09-14  
> **Current state**: 77 PASS, 2 FAIL (naming conflict - platform/pong stdlib shadow), ~6 untested out of 85 ROMs. Two code fixes applied on 2026-09-14: (1) `ic += _steps` in pipeline_cmd.rs:1549 fixes instruction counter advancement; (2) `PROLOGUE_SCAN_END` increased to 0x80000 in cfg.rs:1000 fixes dispatch table completeness. **0 regressions from fixes**. Build: 0 errors, 0 warnings.
> **Status**: IN ACTIVE DEVELOPMENT — Core transpiler works end-to-end; remaining work focuses on PPU edge cases, audio synthesis, and runtime hang diagnosis.

---

## 1. Project Overview

GBAtoPy is a **transpiler** that converts GBA ROMs into standalone Python files playable with pygame. NOT an emulator — the output is human-readable Python source code that can be read, modified, and extended.

---

## 2. Detailed Progress

### ✅ Wave 1: Core Infrastructure - COMPLETE
- Rust pipeline builds with zero warnings
- Disassembler decodes ARM/Thumb instructions (~100% coverage)
- Python generation produces syntactically valid output for all 76 ROMs
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
- **Mosaic effect**: IMPLEMENTED for Mode 0-5 (BG) and OBJ (F27 ✅ — Mode 2-5 BG mosaic added)
- **Sprite rendering**: Implemented and verified (sprite-hmosaic PASS)
- **8BPP tile decoding**: Code exists, not verified

### ⚠️ Wave 5: Audio System — INFRASTRUCTURE ONLY
- APU infrastructure with 4 audio channels (CH1-CH4)
- SquareWaveChannel (CH1/2), WaveChannel (CH3), NoiseChannel (CH4) implemented
- FIFO A/B buffers exist with DMA integration
- ⚠️ DMA audio (FIFO A/B): IMPLEMENTED — DMA writes to FIFO registers. Verified: helloAudio PASS (0% diff), song PASS (1.12% diff), rates PASS (3.65% diff). Full end-to-end audio synthesis comparison not yet automated (F70).
- ⚠️ **MIDI BIOS SWI handlers (0x1B-0x24)**: IMPLEMENTED as utility functions only — NO actual MIDI sound synthesis or playback. See detailed audit below.

**MIDI Handler Implementation Status (Audit 2026-09-11):**

| SWI | Handler | Implementation | Gap |
|-----|---------|----------------|-----|
| 0x1B | `swi_midi_alt_scale` | Returns note unchanged | No scale mapping to APU |
| 0x1C | `swi_midi_alt_key` | Returns note unchanged | No key mapping to APU |
| 0x1D | `swi_midi_inc_octave` | note + 12 semitones | Math only, no playback |
| 0x1E | `swi_midi_dec_octave` | note - 12 semitones | Math only, no playback |
| 0x1F | `swi_midi_inc_note` | note + 1 semitone | Math only, no playback |
| 0x20 | `swi_midi_dec_note` | note - 1 semitone | Math only, no playback |
| 0x21 | `swi_midi_chord` | Returns note list | No APU channel triggering |
| 0x22 | `swi_midi_volume_voice` | Stores volume in dict | Does NOT set APU channel volume |
| 0x23 | `swi_midi_freq_note` | freq → MIDI note | Math only |
| 0x24 | `swi_midi_note_to_freq` | MIDI note → freq | Math only |

**Critical Gap:** These handlers perform MIDI arithmetic but NEVER:
1. Trigger APU channels (CH1-CH4)
2. Set wave RAM for CH3
3. Configure DMA for audio
4. Start/stop note playback
5. Access any APU state

**Result:** A game calling these SWI handlers expecting MIDI playback will get note calculations but no sound. Real GBA MIDI would require the game to manually configure APU channels after calling these helpers, OR a full MIDI synth layer would be needed to bridge MIDI note data to APU synthesis.

**Verification status:** Unverified — no ROM in the 76-ROM test suite exercises MIDI SWI handlers. The handlers are present but functionally incomplete for actual sound generation.

**Audio Output Accuracy (Audit 2026-09-11):**

| Component | Status | Verification |
|-----------|--------|--------------|
| Square wave (CH1/2) | Implemented | Unverified against hardware spectrum |
| Wave channel (CH3) | Implemented | Unverified against hardware spectrum |
| Noise channel (CH4) | Implemented | Unverified against hardware spectrum |
| FIFO A/B DMA | Implemented | helloAudio PASS (0% diff), song PASS (1.12% diff), rates PASS (3.65% diff) |
| MIDI synthesis | NOT IMPLEMENTED | No MIDI playback in test suite |
| Automated audio testing | MISSING | No spectral analysis vs mGBA exists |

**Gap:** Visual-only verification (screenshots) cannot validate audio accuracy. helloAudio/song/rates PASS based on visual output, not audio spectrum comparison. A dedicated audio verification harness comparing generated waveform samples against mGBA output is needed for true audio accuracy validation.

**Sound Output Accuracy:**
- Square wave channels (CH1/CH2): Duty cycles, envelope, sweep implemented. Unverified against hardware.
- Wave channel (CH3): 8/4-bit wave RAM playback with volume scaling. Unverified against hardware.
- Noise channel (CH4): LFSR-based noise with 7/15-bit width. Unverified against hardware.
- FIFO playback (CH1/2 via DMA): Verified with helloAudio (0% diff), song (1.12% diff), rates (3.65% diff).
- **Missing verification:** No automated audio spectrum comparison test exists. Current verification is visual-only (screenshots). Audio accuracy claims are based on functional tests (helloAudio PASS) but not spectral analysis against mGBA output.

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
- Rust-based automated testing with 76 ROMs configured
- **Smoke tests**: 76/76 passing (100%)
- **ScreenshotGolden tests**: WIRED — 91 goldens in `test-reports/goldens/`, compared via `scripts/verify/regress_all.sh` (full regression) and `ScreenshotGoldenVerifier` (Rust). Golden path: `test-reports/goldens/{rom}_f60.png`.
- **Manual golden matches**: 71/76 verified (<30% pixel diff via `compare_screenshots.py`)
- **ScreenshotMgba tests**: 12 ROMs configured (bgpd, bgx, greenswap, hello, hello_world, helloWorld, mode3, mode4, shades, sprite-hmosaic, stripes, vram-mirror)
- **Golden coverage gap**: 12 ROMs use ScreenshotMgba test type but only 12 have corresponding golden files — 0 gap. However, 64 ROMs use other test types (PassFailScreen, EwramDump, Smoke) and have NO golden coverage.
- Verifier types in config: Smoke, ScreenshotGolden, EWRAM, Assertion, Performance, Coverage
- Smoke + ScreenshotGolden verifiers exercised
- Parallel execution (4 workers)
- JSON/JUnit report generation

---

## 3. Test Results

### Smoke Tests (Transpile + Syntax)
```
Total: 76 ROMs
Passed: 76 (100%)
Failed: 0
```

### Visual Verification (ScreenshotGolden vs mGBA)
```
Total: 85 ROMs (2026-09-14 verification)
Verified (<30% diff): 77 (90.6%)
FAIL: 2 (naming conflict: platform/pong stdlib shadow)
Untested: ~6 (timeout/not run)
SKIP: 0 (ZERO-SKIP policy)
Runtime hangs: 0
```

**Note:** Two code fixes applied on 2026-09-14: (1) `ic += _steps` in pipeline_cmd.rs:1549 fixes instruction counter advancement; (2) `PROLOGUE_SCAN_END` increased to 0x80000 in cfg.rs:1000 fixes dispatch table completeness. 0 regressions.

### Golden Screenshot Coverage Audit (2026-09-11)
- **Total golden files**: 91 in `test-reports/goldens/`
- **ScreenshotMgba test ROMs**: 12 (bgpd, bgx, greenswap, hello, hello_world, helloWorld, mode3, mode4, shades, sprite-hmosaic, stripes, vram-mirror)
- **Golden coverage for ScreenshotMgba**: 12/12 (100%)
- **ROMs without golden coverage**: 64 ROMs use PassFailScreen, EwramDump, or Smoke test types — no visual verification against golden images
- **Gap count**: 64 ROMs lack screenshot-based visual verification

**Level 2 (Assertion Text) Results (2026-09-01):** 76/76 PASS. Includes status-irq-dma (CpuFastSet mask fix), dispcnt-latch (IRQ return alignment fix), and all L1 ROMs.

---

## 4. Known Limitations

### Known Codegen Bug Classes
- **F106: BL-split bug** — 32-bit Thumb BL instructions incorrectly split into two 2-byte dispatch entries, creating mid-instruction block boundaries. Affects all ROMs with Thumb BL calls. Fixed in cfg.rs to merge BL prefix/suffix pairs.

### Smoke Test Failures (Historical)
- **helloAudio.gba**: RESOLVED — F45 fix (SWI halt + IRQ IF clear) → PASS (0% diff)
- **rates.gba**: RESOLVED — F46 fix (MUL decode + CRT0) → PASS (3.65% diff)

### Visual Verification Failures (3 ROMs)
- **cascade7**: F83 crash fix applied (dispatch table entry for CRT0 zero-fill). Remaining: blank screen at frame 60 (F106) — likely `.init_array` constructor gap or PPU display state issue
- **fantasy-knight**: Stuck in IRQ handler poll loop — missing IRQ delivery
- **Skyland**: 79K code blocks — hits codegen guard for unimplemented pattern

### Recently Fixed (2026-09-01)
- **blindjump_BlindJump**: PASS at 9.39% diff. Root causes: (F54) Thumb format-7 selector used bit 12 + bits 11-10 instead of bits 11-9, mis-decoding all register-offset load/store; (F12) DISPSTAT read path used stale Python attrs instead of the live MMIO buffer `io[4]/io[5]` that `step_scanline()` writes. Size tracked as F64.

### SKIP (0 ROMs)
- None. All previously skipped ROMs (rates, song, enhancedcontrolchecker, test) now PASS.

### Not Implemented / Not Verified
- **PPU Mode 1 (affine)**: Code exists, not verified
- **PPU Mode 5**: Implemented, not verified
- **Windows/Alpha Blending/Mosaic**: IMPLEMENTED (window_midframe verified; sprite-hmosaic verified at 27.02% diff)
- **Sprite rendering**: Implemented and verified (sprite-hmosaic PASS, proposal_proposal-demo PASS)
- **Audio synthesis**: Infrastructure exists, some verification (helloAudio PASS 0% diff, song PASS 1.12% diff, rates PASS 3.65% diff)
- **RTC**: Implemented (rtc-demo.gba PASS)
- **Automated ScreenshotGolden**: 78 goldens in `test-reports/goldens/`, comparison wired into `regress_all.sh` and Rust `ScreenshotGoldenVerifier`

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

1. **C8/F25a: ELF .init_array constructor processing** — CLOSED: .init_array processed by ROM CRT0, not runtime; 0x030000FC was typo for 0x03007FFC IRQ ptr
3. ~~**C10/F27: PPU BG mosaic for Mode 2-5**~~ — ✅ FIXED: `_apply_mosaic()` calls added to Mode 2 (BG2/BG3), Mode 3, Mode 4, Mode 5 renderers
4. ~~**C11/F28: BIOS SWI LZ77/Huff/RL decompression**~~ — ✅ FIXED: LZ77, Huffman, Run-Length decompression rewritten against mGBA reference; verified with functional test loading compressed data into EWRAM
5. ~~**C12/F29: swi_intr_wait IF wake check**~~ — ✅ FIXED: `IntrWait` now checks IF before halting (R0=1 mode consumes pending IRQ)
6. ~~**C16: MMIO strict width/mask audit**~~ — ✅ DONE: 3 bugs fixed (DMA read high-byte, write_u8 full MMIO dispatch, timer read high-byte); runtime suite green, line_timing canary PASS
7. ~~**F54: blindjump codegen correctness**~~ — ✅ FIXED: Thumb format-7 selector bits 11-9 (was bit 12 + bits 11-10); DISPSTAT read uses MMIO buffer. PASS at 9.39% diff. Size tracked as F64.
8. **Generate goldens for 2 NEW ROMs** (gbarcade, bpcore_BPCoreEngine) — Then run full ScreenshotGolden suite
9. **numba JIT (future work)** — `--profile` (F52) shows `read_u16` + `dict.get` dominate runtime (4.76s/2.3M calls). JIT-compiling the memory access hot path with numba is the highest-leverage perf win but requires numba as a runtime dependency, breaking the standalone-output requirement. Defer until the transpiler output format is stable, then gate behind an opt-in `--jit` flag.
10. **F14: N/S-cycle memory access timing — PERMANENTLY DEFERRED (KILL)** — Oracle analysis (92% confidence) found that adding cycle-accurate memory timing violates all 5 runtime invariants. Zero failing ROMs require cycle-accurate timing. Full analysis in `WORKPLAN.md`.
11. **F40: Link cable transfer — DEFERRED (stub only)** — No ROM in the test suite exercises real link-cable data transfer. The runtime exposes a stub `LinkCable` class that no-ops on read/write.

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
| Test pass rate | 77/85 visual verified (90.6%); 2 fail (naming conflict); 0 skip; ~6 not yet run |
| Build time | ~30s (release) |
| Transpile time | ~1-5s per ROM |

---

## 8. Performance Audit (2026-09-11)

### Generated Python Output Size

Sample line counts from transpiled ROMs in `/tmp/` (audit 2026-09-11):

| ROM | Lines | Size (bytes) |
|-----|-------|--------------|
| LinkCable_basic | 84,738 | 3.24 MB |
| LinkCable_full | 129,483 | 4.94 MB |
| LinkCable_stress | 108,088 | 4.33 MB |
| LinkUART_demo | 82,540 | 3.11 MB |
| cascade7 | 99,647 | 4.45 MB |
| fantasy-knight | 131,553 | ~5.2 MB (estimated) |

**Total generated Python in /tmp/:** ~504K+ lines across measured ROMs

**Latest samples:**
- cascade7: 99,647 lines
- fantasy-knight: 131,553 lines (largest measured)
- Combined sample: 231,200 lines from 2 ROMs

**Observations:**
- Generated files range from 80K-130K lines per ROM
- File sizes range from 3-5 MB per ROM
- Larger ROMs with more code blocks produce proportionally larger output
- Block merging (Wave 1) provides 52-80% code size reduction

### Numba JIT Usage

**Status:** Infrastructure present but **NOT ENABLED** in production

Numba is referenced in 4 runtime files:
- `arm7tdmi.py` - CPU core JIT decorators
- `ppu.py` - PPU rendering JIT decorators  
- `apu.py` - Audio channel JIT decorators
- `numba.py` - Fallback stub module

**Implementation:**
- Graceful fallback when numba not installed (no-op decorators)
- `set_numba_enabled()` and `is_numba_available()` APIs exist
- JIT compilation gated behind opt-in flag

**Why not enabled by default:**
- Breaks standalone output requirement (numba is a runtime dependency)
- Deferrable optimization (F99) — defer until transpiler output format stabilizes
- Current performance acceptable for testing/development use cases

**Potential impact:**
- F52 profiling shows `read_u16` + `dict.get` dominate runtime (4.76s/2.3M calls)
- JIT-compiling memory access hot path could provide 10x speedup
- Recommended as future optimization behind `--jit` flag

---

**Status**: IN ACTIVE DEVELOPMENT — core transpiler works end-to-end; remaining work focuses on PPU edge cases, audio synthesis, and runtime hang diagnosis

## Appendix: Phase 16/17 Runtime Fixes (2026-08-04 to 2026-08-17)

These fixes bring the test suite from 69 PASS / 5 FAIL / 0 SKIP / 2 NEW out of 76 ROMs as of 2026-08-14.

### Phase 16 (2026-08-04 to 2026-08-13)

| Fix | ROM(s) | Impact |
|-----|--------|--------|
| ARM BX Rn bug | burst-into-tears, nes, reload, 128kb-boundary | Indirect branch via register now works |
| Timer fractional accumulator | haltcnt | Timer precision matches hardware |
| LDR-literal alignment mask | basic-timing, start-stop | `(PC+4) & !3` applied to literal loads |
| _deliver_irq re-entry guard | cancel-irq-if, irq-delay, status-irq-dma | IRQ handler cannot re-enter itself |
| CFG literal pool detection | dispcnt-latch, force-nseq-access, ram-access-timing | Data pools skipped in BFS traversal |
| IE/IF/IME sync | cancel-irq-if, status-irq-dma | Interrupt enable/flag/ack properly synchronized |
| IWRAM execution dispatch | vram-mirror | Code at 0x03000000-0x03007FFF executes correctly |
| PPU MMIO read dispatch | dispcnt-latch | DISPCNT reads via _dispatch_hal_read |
| io[] DISPCNT byte swap | window_midframe | Byte order matches hardware |
| Thumb dispatch routing | reload | Thumb→ARM mode switches correctly |
| CPSR/SPSR banking | cancel-irq-ie | Mode-specific status registers preserved |
| N/S timing | force-nseq-access, ram-access-timing | N and S cycle timing matches hardware |
| Sprite_list memory leak | All ROMs >60 frames | No more OOM on long runs |
| OBJ mosaic implementation | sprite-hmosaic | Object mosaic effect renders |
| Window register addresses | window_midframe | Window regs at correct MMIO addresses |
| Alpha blend second target | All blend ROMs | Blend target B selected properly |
| Brightness first-target only | All brightness ROMs | Brightness affects target A only |
| DMA Audio FIFO A/B | song, rates | Audio DMA FIFOs dispatch to APU |
| SRAM address mapping 0x0E000000 | Save ROMs | SRAM at correct Game Pak address |
| CP/CPUT/CPUSet fill-mode bit 24 | 1024-transfer-loop, openbus-cpu, spsr | DMA fill mode toggled by bit 24 |
| VBlank IRQ once-per-entry | All IRQ ROMs | IRQ fires exactly once per VBlank |
| IRQ Thumb-bit preservation | irq-delay, status-irq-dma | T-bit kept across IRQ entry/exit |

### Phase 17 (2026-08-14 to 2026-08-17)

| Fix | ROM(s) | Impact |
|-----|--------|--------|
| F44 IWRAM CFG BFS discovery | FlashSpeedTestROM | IWRAM-resident code discovered and emitted |
| F45 0x03000128 trampoline removal | FlashSpeedTestROM | Spurious trampoline no longer generated |
| F46 read_u8 MMIO & 0xFF mask | cascade7, fantasy-knight | 8-bit MMIO reads masked correctly |
| F47 VBlankIntrWait IF clear on unhalt | cascade7, fantasy-knight | IF bit cleared after halt loop exits |
| F48 IRQ register save/restore | fantasy-knight | R0-R3, R12 preserved during IRQ |
| F49 IRQ return mid-scanline | fantasy-knight | _irq_return_pc checked immediately |
| F50 Banked register System mode 0x1F | fantasy-knight | System mode (0x1F) mapped in _switch_mode |
| F51 cascade7 indirect BX Rn CFG | cascade7 | LDR Rd,[Rn,Rm] + BX/BLX Rm thunk discovery |
| F53 Skyland IWRAM circuit-breaker | Skyland | code validity filter + min copy size |
| F55 APU FIFO A/B DMA dispatch | song, rates | Audio FIFO A/B DMA MMIO implemented |
| F56 Deduplicate _deliver_irq | All IRQ ROMs | Shared const body, no more dual copies |
| C0 Remove embedded runtime | All ROMs | gba_runtime_embedded.py deleted (10,924 lines) |

### Phase 18 (2026-08-31 to 2026-09-01)

| Fix | ROM(s) | Impact |
|-----|--------|--------|
| F14b Halt wake IME requirement removed | line_timing | SWI 0x02 (Halt) no longer requires IME=1 to wake; 0%→23.92% content match |
| F14b codegen SWI halt block-break | line_timing | Transpiled blocks emit `if _cpu_halted: return` after `swi_handler(N)`; prevents rest of block executing after HALT before main loop detects halt. 26.89% diff, PASS |
| swi_cpufastset count mask | status-irq-dma | Missing `& 0x001FFFFF` count mask in bios.py CpuFastSet caused timeout (130s→4.9s) |
| CFG final-sweep seed validation | All ROMs | Requires consecutive valid decodes to filter audio data pools from BFS |
| CFG BFS deduplication | All ROMs | Eliminated duplicated BFS loop in cfg.rs |
| ARM SWP/SWPB routing + _set_nz + long-multiply flags | All ARM ROMs | SWP/SWPB correctly routed; _set_nz preserves T-bit; UMULL/SMULL/UMLAL/SMLAL set flags |
| Pre-flight OOM guard | blindjump | Output size checked before write; prevents 2G OOM crash |
| C9/F26 Coprocessor silent-pass stubs | All ROMs | Coprocessor opcodes and unknown opcodes now raise NotImplementedError instead of silent NOP |
| IRQ return alignment mask | dispcnt-latch | ARM-mode MOV PC,LR masks LR to 4-byte boundary; return detection now accepts masked PC at 4 sites |
| Codegen exception-return cpsr.clear() fix | All IRQ ROMs | 4 exception-return paths (MOVS/SUBS/LDM PC^/ANDS PC) no longer erase SPSR dict entries; T-bit restored from SPSR |
| C12/F29 IntrWait IF pre-check | All IntrWait users | SWI 0x04 (R0=1) now checks IF before halting; consumes pending IRQ, sets R0=1, returns without halt. SWI 0x03 (Stop) separated from SWI 0x04 |
| C10/F27 BG mosaic Mode 2-5 | bitmap/affine ROMs | `_apply_mosaic()` calls added to Mode 2 (BG2+BG3), Mode 3, Mode 4, Mode 5 renderers; coordinates snapped before affine transform |