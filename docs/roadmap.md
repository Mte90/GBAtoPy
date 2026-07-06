# GBAtoPy Roadmap — Project Status

> **Role:** Strategy, sequencing, and remaining work.
> For the current capability matrix (what works/what's stubbed), see [`status.md`](status.md).

> **Last updated**: 2026-07-06
> **Current state**: 68 ROMs transpile; 66/68 pass smoke test (helloAudio, rates fail). Build: 0 errors, 0 warnings. 2/68 ROMs verified pixel-perfect against mGBA golden via manual comparison (stripes.gba, shades.gba). 32 golden screenshots exist; automated comparison not yet wired into CI. Known blocking bug: STMFD/LDMFD register order corrupts stack on real-game ROMs (hello.gba).
> **Status**: IN ACTIVE DEVELOPMENT — Core transpiler works for instruction-coverage ROMs; real-game ROMs blocked by CPU-core bugs

---

## 1. Project Overview

GBAtoPy is a **transpiler** that converts GBA ROMs into standalone Python files playable with pygame. NOT an emulator — the output is human-readable Python source code that can be read, modified, and extended.

---

## 2. Detailed Progress

### ✅ Wave 1: Core Infrastructure - COMPLETE
- Rust pipeline builds with zero warnings
- Disassembler decodes ARM/Thumb instructions (~100% coverage)
- Python generation produces syntactically valid output for all 68 ROMs
- Memory map implemented (ROM, EWRAM, IWRAM, MMIO, VRAM, Palette, OAM)
- Basic block merging (52-80% code size reduction)

### ✅ Wave 2: CPU Core - COMPLETE
- ARM7TDMI core implemented (849 lines in arm7tdmi.py + 706 lines in cpu.py)
- All ARM data processing instructions (MOV, ADD, SUB, ORR, AND, EOR, BIC, MVN, SBC, ADC)
- Load/store instructions (LDR, STR, LDRH, STRH, LDRB, STRB) with PC-relative addressing
- Branch instructions (B, BL, BLX, BX, CBZ, CBNZ) with condition code support
- Multiply instructions (MUL, MLA)
- MRS/MSR, SWP/SWPB, LDM/STM (all variants: IA/IB/DA/DB + writeback) - **fixed 2026-06-18**
- Thumb mode codegen (~100% coverage)
- CPSR flag tracking (N/Z/C/V) with all 16 condition codes
- Global register propagation across function boundaries
- **Performance**: Registers optimized as list instead of dict (+20% speedup)

### ✅ Wave 3: BIOS Handlers - COMPLETE
- 54 BIOS SWI handlers implemented in arm7tdmi.py
- Core handlers: Halt, IntrWait, VBlankIntrWait, Div, Sqrt, DivArm
- CPU operations: CPUSet, CPUFastSet, RegisterRamReset
- Decompression: LZ77, Huffman, RLE (LZ77UnComp, HuffmanUnComp, RLUnComp)
- Arithmetic: ArcTan, ArcTan2, BitCount, Sin, Cos, Sqrt
- Geometry: ObjAffineSet, BgAffineSet
- MIDI operations, Time functions, Sound control

### ⚠️ Wave 4: PPU Rendering — PARTIAL
- **Mode 0 (4BPP text)**: Verified on shades.gba (100% golden match). Multiple bugs fixed: char-block base mapping, 4BPP nibble order, double-scale. See `docs/codegen-pitfalls.md`.
- **Mode 3 (15-bit bitmap)**: Verified on stripes.gba (100% golden match).
- **Mode 4 (8BPP bitmap)**: Partial — palette fallback bug fixed on hello.gba; not all ROMs verified.
- **Mode 1/2 (affine)**: Code exists, MMIO wiring broken — NOT verified.
- **Mode 5**: Implemented, not verified.
- **Window layers (WIN0/WIN1/OBJWIN)**: Register stubs only — NOT functional.
- **Blend effects**: Register stubs only — NOT functional.
- **Mosaic effect**: Register stubs only — NOT functional.
- **Sprite rendering**: Code exists, not verified against golden.
- **8BPP tile decoding**: Code exists, not verified.
- **Affine backgrounds**: Code exists, not verified.

### ⚠️ Wave 5: Audio System — INFRASTRUCTURE ONLY
- APU infrastructure with 4 audio channels (CH1-CH4)
- SquareWaveChannel (CH1/2), WaveChannel (CH3), NoiseChannel (CH4) implemented
- FIFO A/B buffers, DMA-triggered playback
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
- Repeat mode with FIFO A/B for audio
- Timers 0-3 with prescaler (1/64/256/1024) and cascade mode
- Timer overflow detection and reload

### ✅ Wave 8: Input System - COMPLETE
- KEYINPUT register (0x04000130) - 10-bit keypad state
- KEYCNT register (0x04000132) - interrupt conditions
- 8-bit and 16-bit read support

### ✅ Wave 9: Test Framework — PARTIAL
- Rust-based automated testing with 68 ROMs configured
- **Smoke tests**: 66/68 passing (helloAudio, rates fail)
- **ScreenshotGolden tests**: ❌ NOT YET WIRED — 32 golden screenshots exist in `scripts/screenshot/golden/` but automated comparison is not in the test runner
- **Manual golden matches**: 2/68 verified (stripes.gba, shades.gba — 100% pixel match via `compare_screenshots.py`)
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

### ScreenshotGolden Tests (Pixel-Perfect)
```
Status: NOT AUTOMATED
Golden screenshots available: 32 (in scripts/screenshot/golden/)
Manually verified: 2/68
  - stripes.gba: 100% pixel match (Mode 3)
  - shades.gba: 100% pixel match (Mode 0, after 5 bug fixes — see docs/codegen-pitfalls.md)
Remaining: 30 goldens exist but comparison not run; 36 ROMs have no golden yet
```

---

## 4. Known Limitations

### Blocking Bugs
- **STMFD/LDMFD register order** (UNRESOLVED): STMFD writes registers in reverse address order, corrupting saved LR/PC. Causes PC to jump to `0x04040404` on real-game ROMs (hello.gba). See `docs/codegen-pitfalls.md`.
- **helloAudio, rates smoke failures**: Cause not yet diagnosed.

### Not Implemented / Not Verified
- **PPU Mode 1/2 (affine)**: Code exists, MMIO wiring broken — not verified
- **Window/Blend/Mosaic**: Register stubs only — not functional
- **Audio synthesis**: Infrastructure exists, no verified sound output
- **Sprite rendering**: Code exists, not verified against golden
- **Automated ScreenshotGolden**: 32 goldens exist, comparison not wired into CI
- **EWRAM dump verification**: Infrastructure exists, needs test ROMs

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
python3 -c "from PIL import Image; img=Image.open('/tmp/stripes.png'); nb=sum(1 for p in img.getdata() if sum(p)>30); print(f'Non-black: {nb}')"

# Run all tests
cargo run -p gbatopy-test -- --config test-roms-config.toml --format console

# Run specific test type
cargo run -p gbatopy-test -- --config test-roms-config.toml --filter "bgx" --format json
```

---

## 6. Next Steps (Priority Order)

1. **Wire ScreenshotGolden into CI** — 32 goldens exist, comparison not automated. Highest-leverage: converts "works/doesn't work" from assertion to fact.
2. **Fix STMFD/LDMFD register order** — blocks all real-game ROMs (hello.gba et al.)
3. **Diagnose helloAudio, rates smoke failures**
4. **Generate goldens for remaining 36 ROMs** — then run full ScreenshotGolden suite
5. **Verify sprite rendering** — code exists, no golden comparison
6. **Verify audio synthesis** — infrastructure exists, no output check
7. **EWRAM dump tests** with memory comparison
8. **Code size optimization** (reduce per-block boilerplate)

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
| Test pass rate | 66/68 smoke (97%); 2/68 manual golden |
| Build time | ~30s (release) |
| Transpile time | ~1-5s per ROM |

---

**Status**: ⚠️ IN ACTIVE DEVELOPMENT — core transpiler works for instruction-coverage ROMs; real-game ROMs blocked by STMFD/LDMFD bug; visual verification not yet automated
