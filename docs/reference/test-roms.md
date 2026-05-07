song.gba# GBA Test ROMs Reference

This document catalogs all test ROMs used by GBAtoPy for verification and testing.

## Overview

| Metric | Value |
|--------|-------|
| Total ROMs | 60+ |
| Test Suites | 18 |
| Sources | jsmolka, hw-test, gba-playground, armwrestler, gba_tests, FuzzARM, libbet, GBA-Test-Collection, velipso, destoer, nataliethenerd, cadfan, gba-sound-test, NanoBoyAdvance, commercial |

---

## Test Suite 1: gba-tests-master

**Source**: https://github.com/jsmolka/gba-tests  
**Description**: Comprehensive GBA hardware tests covering ARM/Thumb CPU, BIOS, memory, PPU, and save types.

### 1.1 arm.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/arm/arm.gba` |
| Size | ~2KB |
| Tests | ARM instruction set (32-bit) |
| Coverage | Data processing, load/store, branch, multiply |
| Usefulness | **CRITICAL** - Validates ARM instruction decoding and execution |

**Tested Opcodes**: ADD, SUB, MOV, CMP, AND, ORR, EOR, BIC, LDR, STR, B, BL, MUL, MLA

### 1.2 thumb.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/thumb/thumb.gba` |
| Size | ~2KB |
| Tests | Thumb instruction set (16-bit) |
| Coverage | Thumb arithmetic, load/store, branch |
| Usefulness | **CRITICAL** - Validates Thumb mode execution |

**Tested Opcodes**: MOV, ADD, SUB, LDR, STR, B, BL, CMP

### 1.3 bios.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/bios/bios.gba` |
| Size | ~2KB |
| Tests | BIOS SWI handlers |
| Coverage | Div, Sqrt, CpuSet, LZ77, Huffman, RLE decompression |
| Usefulness | **HIGH** - Tests BIOS function calls |

**Tested SWI**: 0x06 (Div), 0x07 (Sqrt), 0x09 (CpuSet), 0x10-0x14 (decompression)

### 1.4 memory.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/memory/memory.gba` |
| Size | ~2KB |
| Tests | Memory access patterns, timing |
| Coverage | ROM, RAM, I/O read/write |
| Usefulness | **HIGH** - Validates memory subsystem |

### 1.5 nes.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/nes/nes.gba` |
| Size | ~4KB |
| Tests | NES emulator on GBA |
| Coverage | ARM performance under heavy load |
| Usefulness | **MEDIUM** - Stress test for ARM execution |

### 1.6 unsafe.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/unsafe/unsafe.gba` |
| Size | ~2KB |
| Tests | UNF-safe operations |
| Coverage | Edge cases |
| Usefulness | **MEDIUM** - Tests boundary conditions |

### 1.7 save/*.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/save/` |
| ROMs | sram.gba, flash64.gba, flash128.gba, none.gba |
| Tests | Save type detection |
| Coverage | SRAM, Flash ROM detection |
| Usefulness | **MEDIUM** - Save type handling |

### 1.8 ppu/hello.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/ppu/hello.gba` |
| Size | ~1KB |
| Tests | Basic PPU rendering |
| Coverage | Text display on background |
| Usefulness | **HIGH** - Basic graphics output |

### 1.9 ppu/shades.gba ⚠️ CRITICAL
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/ppu/shades.gba` |
| Size | 352 bytes |
| Tests | **DISPCNT, BG0CNT, palette, VRAM, tilemap** |
| Source Code | `test_roms/gba-tests-master/ppu/shades.asm` |
| Usefulness | **CRITICAL** - Validates PPU register writes and rendering |

This ROM writes to:
- `0x04000000` (DISPCNT) - Display control
- `0x04000008` (BG0CNT) - Background control
- `0x05000000` (PALETTE) - Color palette
- `0x06000000` (VRAM) - Video RAM tiles
- `0x06000800` (VRAM tilemap) - Background map

**Why Critical**: This is THE test ROM for verifying PPU functionality.

### 1.10 ppu/stripes.gba ⚠️ CRITICAL
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-tests-master/ppu/stripes.gba` |
| Size | 324 bytes |
| Tests | **PPU rendering with diagonal stripes** |
| Source Code | `test_roms/gba-tests-master/ppu/stripes.asm` |
| Usefulness | **CRITICAL** - Visual rendering verification |

This ROM produces diagonal red/white stripes - perfect for visual verification.

---

## Test Suite 2: hw-test

**Source**: https://github.com/AntonioND/hw-test  
**Description**: Low-level hardware tests for GBA internals.

### 2.1 DMA Tests
| ROM | Path | Tests |
|-----|------|-------|
| burst-into-tears.gba | `test_roms/hw-test/dma/burst-into-tears/` | DMA burst behavior |
| force-nseq-access.gba | `test_roms/hw-test/dma/force-nseq-access/` | Non-sequential access |
| latch.gba | `test_roms/hw-test/dma/latch/` | DMA latch timing |
| start-delay.gba | `test_roms/hw-test/dma/start-delay/` | DMA start delay |

### 2.2 IRQ Tests
| ROM | Path | Tests |
|-----|------|-------|
| cancel-irq-ie.gba | `test_roms/hw-test/archive/irq/cancel-irq-ie/` | IRQ cancel via IE |
| cancel-irq-if.gba | `test_roms/hw-test/archive/irq/cancel-irq-if/` | IRQ cancel via IF |
| cancel-irq-ime.gba | `test_roms/hw-test/archive/irq/cancel-irq-ime/` | IRQ cancel via IME |
| irq-delay.gba | `test_roms/hw-test/irq/irq-delay/` | IRQ delay timing |

### 2.3 PPU Tests
| ROM | Path | Tests |
|-----|------|-------|
| basic-timing.gba | `test_roms/hw-test/archive/ppu/basic-timing/` | PPU basic timing |
| exact-timing.gba | `test_roms/hw-test/archive/ppu/exact-timing/` | PPU exact timing |
| mode2.gba | `test_roms/hw-test/archive/ppu/mode2/` | Mode 2 rotation |
| mode3.gba | `test_roms/hw-test/archive/ppu/mode3/` | Mode 3 bitmap |
| mode4.gba | `test_roms/hw-test/archive/ppu/mode4/` | Mode 4 bitmap double-buffer |
| bgpd.gba | `test_roms/hw-test/ppu/bgpd/` | BG palette direct |
| bgx.gba | `test_roms/hw-test/ppu/bgx/` | BG rotation/scaling |
| dispcnt-latch.gba | `test_roms/hw-test/ppu/dispcnt-latch/` | DISPCNT timing |
| greenswap.gba | `test_roms/hw-test/ppu/greenswap/` | Green swap effect |
| ram-access-timing.gba | `test_roms/hw-test/ppu/ram-access-timing/` | VRAM timing |
| sprite-hmosaic.gba | `test_roms/hw-test/ppu/sprite-hmosaic/` | Sprite H mosaic |
| status-irq-dma.gba | `test_roms/hw-test/ppu/status-irq-dma/` | PPU status IRQ/DMA |
| vram-mirror.gba | `test_roms/hw-test/ppu/vram-mirror/` | VRAM mirroring |

### 2.4 Timer Tests
| ROM | Path | Tests |
|-----|------|-------|
| reload.gba | `test_roms/hw-test/timer/reload/` | Timer reload |
| start-stop.gba | `test_roms/hw-test/timer/start-stop/` | Timer start/stop |

### 2.5 Bus Tests
| ROM | Path | Tests |
|-----|------|-------|
| 128kb-boundary.gba | `test_roms/hw-test/bus/128kb-boundary/` | 128KB boundary crossing |

### 2.6 Other
| ROM | Path | Tests |
|-----|------|-------|
| haltcnt.gba | `test_roms/hw-test/haltcnt/` | Halt counter |

---

## Test Suite 3: gba-playground

**Source**: https://github.com/AntonioND/gba-playground  
**Description**: Homebrew demos and tests.

### 3.1 redline.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-playground-master/redline/redline.gba` |
| Tests | Full game demo |
| Usefulness | **HIGH** - Complex real-world code execution |

### 3.2 rtc-demo.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/gba-playground-master/rtc-demo/rtc-demo.gba` |
| Tests | Real-time clock |
| Usefulness | **LOW** - RTC not essential for core functionality |

---

## Test Suite 4: FalseDiagonalTest

**Source**: https://github.com/FalseDiagonal/FalseDiagonalTest  
**Description**: Additional test suite.

### false_diagonal_test.gba
| Property | Value |
|----------|-------|
| Path | `test_roms/FalseDiagonalTest-main/false_diagonal_test.gba` |
| Tests | General GBA functionality |
| Usefulness | **MEDIUM** - Additional test coverage |

---

## Commercial ROMs

### Tetris Worlds (Europe)
| Property | Value |
|----------|-------|
| Path | User-provided |
| Size | 4MB |
| Tests | Real commercial game |
| Usefulness | **CRITICAL** - Full game test with graphics/audio/input |

---

---

## Test Suite 5: armwrestler-gba-fixed

**Source**: https://github.com/destoer/armwrestler-gba-fixed  
**Stars**: 26  
**Description**: ARM7DI CPU instruction tests with multiple load-store tests working. Fork of Arisotura's arm7wrestler.

### armwrestler.gba
| Property | Value |
|----------|-------|
| Tests | ARM instruction set, load-store operations |
| Coverage | Data processing, multiply, load/store, branch |
| Usefulness | **HIGH** - Comprehensive ARM7DI CPU tests |

---

## Test Suite 6: gba_tests (destoer)

**Source**: https://github.com/destoer/gba_tests  
**Stars**: 13  
**Description**: Focused test ROMs for specific GBA hardware behaviors.

| ROM | Tests |
|-----|-------|
| cond_invalid | Conditional flag behavior |
| dma_priority | DMA priority handling |
| hello_world | Basic output |
| if_ack | Interrupt flag acknowledgment |
| isr | Interrupt service routines |
| line_timing | Scanline timing |
| lyc_midline | LY=LYC coincidence mid-frame |
| window_midframe | Window rendering mid-frame |

**Usefulness**: **HIGH** - Tests edge cases not covered by jsmolka suite

---

## Test Suite 7: FuzzARM

**Source**: https://github.com/DenSinH/FuzzARM  
**Stars**: 49  
**Description**: Random test ROM generator for ARM/Thumb instruction fuzzing. Generates thousands of test cases.

### Pre-built ROMs
| ROM | Tests | Description |
|-----|-------|-------------|
| ARM_DataProcessing.gba | 10,000 | ARM mode data processing |
| ARM_Any.gba | 10,000 | ARM mode all types |
| THUMB_DataProcessing.gba | 10,000 | THUMB mode data processing |
| THUMB_Any.gba | 10,000 | THUMB mode all types |
| FuzzARM.gba | 10,000 | Mixed ARM+THUMB all types |

**Usefulness**: **CRITICAL** - Massively parallel instruction testing with eWRAM result dump

---

## Test Suite 8: GBA-Test-Collection

**Source**: https://github.com/ladystarbreeze/GBA-Test-Collection  
**Stars**: 9  
**Description**: Collection of GBA test ROMs in assembly. Early development stage.

**Usefulness**: **MEDIUM** - Growing collection, worth monitoring

---

## Test Suite 9: enhancedcontrolcheckerGBA

**Source**: https://github.com/nataliethenerd/enhancedcontrolcheckerGBA  
**Stars**: 8  
**Description**: Button test ROM - counts presses, plays tones.

| Property | Value |
|----------|-------|
| Tests | All GBA buttons (A, B, L, R, Start, Select, D-pad) |
| Coverage | Input polling, button state |
| Usefulness | **MEDIUM** - Input subsystem validation |

---

## Test Suite 10: gba-accuracy-tests

**Source**: https://github.com/cadfan/gba-accuracy-tests  
**Description**: Cross-emulator accuracy benchmark framework. Test ROM manifests, reference hashes, diff images.

### Integrated Suites
| Suite | Tests | Source |
|-------|-------|--------|
| jsmolka | 13 | jsmolka/gba-tests |
| armwrestler | 6 | destoer/armwrestler-gba-fixed |
| fuzzarm | 3 | DenSinH/FuzzARM |
| mgba-suite | 14 | mgba-emu/suite |
| ags-aging | 1 | TCRF AGS Aging Cartridge |

**Total**: 37 test cases  
**Usefulness**: **CRITICAL** - Multi-emulator comparison, gold reference hashes

---

## Additional Test Sources Researched

This section documents additional GBA test ROM sources that were researched but are not available for download.

### 1. mGBA Test Suite (mgba-emu/mgba)

| Property | Value |
|----------|-------|
| Source | https://github.com/mgba-emu/mgba |
| Status | ⚠️ Limited - GB/GBC only |
| Tests | Located in `cinema/gb/` folder |

**Finding**: The mGBA repository does not contain standalone GBA test ROMs. It has GB/GBC test ROMs in `cinema/gb/` including:
- Blargg CPU instruction tests
- Blargg sound tests (DMG/CGB)
- Mooneye-GB compatibility tests
- ACID tests (CGB/DMG)

These are Game Boy tests, not GBA tests.

**Download individual ROMs**:
```bash
# Example: blargg cpu_instrs
curl -L -o cpu_instrs.gb "https://raw.githubusercontent.com/mgba-emu/mgba/master/cinema/gb/blargg/cpu_instrs/01-special/test.gb"
```

---

### 2. TONC GBA Demos (gbadev-org/tonc)

| Property | Value |
|----------|-------|
| Source | https://github.com/gbadev-org/tonc |
| Status | ⚠️ Source code only |
| Requires | devkitARM to compile |

**Finding**: TONC is a comprehensive GBA programming tutorial. Contains demo code embedded in markdown files:
- `content/sndsqr.md` - Sound square wave demo with SOS tune
- `content/timers.md` - Digital clock using cascaded timers

No pre-built .gba ROMs - code must be compiled with devkitARM.

---

### 3. Jeff Frohwein GBA Sound Demo

| Property | Value |
|----------|-------|
| Source | pdroms.de, gbadev.org |
| Status | ❌ Unavailable |
| Original Author | Jeff Frohwein (FASound creator) |

**Finding**: Jeff Frohwein was a prominent GBA developer known for the FASound audio library. However:
- pdroms.de is currently down (404 errors)
- gbadev.org archives don't have his specific demos
- No direct download URLs found

---

### 4. SkyEmu Test ROMs (skylersaleh/SkyEmu)

| Property | Value |
|----------|-------|
| Source | https://github.com/skylersaleh/SkyEmu |
| Status | ❌ No bundled ROMs |

**Finding**: SkyEmu does not include test ROMs in its repository. It uses external test suites for validation:
- jsmolka/gba-tests (arm.gba, thumb.gba)
- ARMWrestler
- FuzzARM

The emulator validates against these external suites but doesn't bundle them.

---

### 5. NanoBoyAdvance Test Matrix (nba-emu/NanoBoyAdvance)

| Property | Value |
|----------|-------|
| Source | https://github.com/nba-emu/NanoBoyAdvance |
| Status | ❌ No bundled ROMs |

**Finding**: Similar to SkyEmu, NanoBoyAdvance is a clean-room emulator with no bundled test ROMs. It references external test suites for validation:
- mGBA suite
- ARMWrestler
- gba-suite
- FuzzARM

---

## Test Priority Matrix

| Priority | ROMs | Purpose |
|----------|------|---------|
| 🔴 CRITICAL | arm.gba, thumb.gba, shades.gba, stripes.gba, FuzzARM.gba | Core CPU + PPU validation |
| 🟠 HIGH | bios.gba, memory.gba, hello.gba, redline.gba, armwrestler.gba, gba_tests | Extended functionality |
| 🟡 MEDIUM | save/*.gba, nes.gba, false_diagonal_test.gba, GBA-Test-Collection, enhancedcontrolcheckerGBA | Additional coverage |
| 🟢 LOW | rtc-demo.gba | Optional features |

---

## Test Categories

### CPU Tests (9 ROMs)
- arm.gba, thumb.gba, memory.gba, nes.gba, unsafe.gba
- hw-test DMA (4 ROMs), hw-test timer (2 ROMs)

### Graphics Tests (14 ROMs)
- gba-tests-master ppu (3 ROMs): hello, shades, stripes
- hw-test ppu (13 ROMs): mode2/3/4, bgx, sprite, timing

### Memory/Storage Tests (5 ROMs)
- gba-tests-master memory, save (4 ROMs)
- hw-test bus (1 ROMs)

### Interrupt/BIOS Tests (8 ROMs)
- gba-tests-master bios
- hw-test irq (4 ROMs), haltcnt

---

## Usage in GBAtoPy Pipeline

```
Pipeline Stage → Test ROMs Used
─────────────────────────────────
Disassembly    → ALL ROMs (verify JSON output)
IR Generation  → arm.gba, thumb.gba (verify IR)
Type Inference → (optional)
Code Generation → ALL ROMs (verify Python output)
Runtime Test    → arm.gba, thumb.gba (headless)
Visual Test     → shades.gba, stripes.gba (screenshot)
Audio Test      → redline.gba (audio playback)
Input Test      → redline.gba (keyboard)
```

---

## Verification Commands

```bash
# Test all ROMs headless
cargo run -p pygba-cli -- test all

# Visual test - shades
python3 output_python/gba-tests-master_ppu_shades/shades.py --screenshot /tmp/shades.png

# Visual test - stripes  
python3 output_python/gba-tests-master_ppu_stripes/stripes.py --screenshot /tmp/stripes.png
```

---

## Notes

1. **shades.gba** and **stripes.gba** are THE most important ROMs for PPU verification
2. hw-test suite has 27 ROMs but only some are actively tested
3. Commercial ROMs (Tetris) provide real-world gameplay testing
4. All test ROMs should produce executable Python without errors# New GBA Test Suites Analysis

This document provides detailed analysis of the 6 newly discovered test ROM repositories and their unique coverage compared to existing suites (jsmolka/gba-tests and hw-test).

---

## Summary Table

| Suite | Stars | Unique Coverage | Priority |
|-------|-------|-----------------|----------|
| armwrestler-gba-fixed | 26 | ARM7DI load-store tests | HIGH |
| gba_tests (destoer) | 13 | Edge cases: IRQ, DMA priority, windowing | HIGH |
| FuzzARM | 49 | 10K+ randomized fuzz tests | CRITICAL |
| GBA-Test-Collection | 9 | TBD (early stage) | MEDIUM |
| enhancedcontrolcheckerGBA | 8 | Input polling (L/R buttons) | MEDIUM |
| gba-accuracy-tests | 0 | Multi-emulator benchmark framework | CRITICAL |

---

## 1. armwrestler-gba-fixed

**Repository**: https://github.com/destoer/armwrestler-gba-fixed  
**Stars**: 26  
**License**: Not specified

### Overview
Fork of Arisotura's arm7wrestler with multiple load-store tests working. Focused on ARM7DI CPU instruction validation.

### ROMs Available
- `armwrestler.gba` - Main test ROM
- `armwrestler-gba-fixed.gba` - Fixed version

### What It Tests
- ARM instruction set (32-bit)
- Load-store operations
- Data processing
- Multiply instructions
- Branch instructions

### Unique Coverage
| Feature | jsmolka | hw-test | armwrestler |
|---------|---------|---------|-------------|
| Load-store edge cases | Partial | No | **YES** |
| ARM7DI specific | No | No | **YES** |

### Integration
Already integrated into `gba-accuracy-tests` framework (suite: armwrestler, 6 tests).

---

## 2. gba_tests (destoer)

**Repository**: https://github.com/destoer/gba_tests  
**Stars**: 13  
**License**: MIT

### Overview
Focused test ROMs for specific GBA hardware behaviors. Tests edge cases not covered by jsmolka.

### ROMs Available

| ROM | Category | What It Tests |
|-----|----------|---------------|
| `cond_invalid` | CPU | Conditional flag behavior |
| `dma_priority` | DMA | DMA priority handling |
| `hello_world` | Basic | Basic output |
| `if_ack` | IRQ | Interrupt flag acknowledgment |
| `isr` | IRQ | Interrupt service routines |
| `line_timing` | PPU | Scanline timing |
| `lyc_midline` | PPU | LY=LYC coincidence mid-frame |
| `window_midframe` | PPU | Window rendering mid-frame |

### Unique Coverage

| Feature | jsmolka | hw-test | gba_tests |
|---------|---------|---------|-----------|
| DMA priority | No | Partial | **YES** |
| IRQ acknowledgment | No | No | **YES** |
| LYC mid-line IRQ | No | No | **YES** |
| Window mid-frame | No | No | **YES** |
| Conditional invalid | No | No | **YES** |

### Why Important
Tests timing-sensitive hardware behaviors that cause issues in many emulators:
- DMA priority conflicts
- IRQ flag clearing timing
- LY=LYC coincidence mid-scanline
- Window rendering in different modes

---

## 3. FuzzARM

**Repository**: https://github.com/DenSinH/FuzzARM  
**Stars**: 49  
**License**: GPL-3.0

### Overview
Random test ROM generator for ARM/Thumb instruction fuzzing. Generates thousands of test cases with configurable options.

### ROMs Available (Pre-built)

| ROM | Tests | Mode | Type |
|-----|-------|------|------|
| ARM_DataProcessing.gba | 10,000 | ARM | Data Processing |
| ARM_Any.gba | 10,000 | ARM | All types |
| THUMB_DataProcessing.gba | 10,000 | THUMB | Data Processing |
| THUMB_Any.gba | 10,000 | THUMB | All types |
| FuzzARM.gba | 10,000 | Mixed | All types |

### Generation Options
```bash
# Generate custom ROM
python main.py -h
usage: main.py [-h] [-T {some,all,none}] [-nM] [-nD] [-nLS] [--S SEED] N

Options:
  -T {some,all,none}  THUMB mode tests
  -nM                 Disable multiply tests
  -nD                 Disable data processing tests
  -nLS                Disable load/store tests
  --S SEED            Seed for reproducibility
```

### What It Tests

**Data Processing**:
- Arithmetic: ADD, SUB, ADC, SBC, RSC
- Logical: AND, ORR, EOR, BIC, MVN
- Comparisons: CMP, CMN, TST, TEQ
- Shifts: LSL, LSR, ASR, ROR, RRX

**Multiply**:
- MUL, MLA, UMULL, UMLAL, SMULL, SMLAL

**Load/Store**:
- LDR, STR, LDRH, STRH, LDRB, STRB
- LDM, STM, SWP

**PSR Transfers**:
- MRS, MSR

### Unique Coverage
| Feature | jsmolka | hw-test | FuzzARM |
|---------|---------|---------|---------|
| Random fuzz testing | No | No | **YES** |
| 10K+ test cases | No | No | **YES** |
| eWRAM result dump | No | No | **YES** |
| Reproducible (seed) | No | No | **YES** |

### eWRAM Result Format
```
1 word:  ['AAAA' OR 'TTTT'] for ARM or THUMB state
2 words: [opcode + shift] OR [multiplication opcode] OR [store opcode/load opcode]
1 word:  [????]

1 word:  [initial r0]
1 word:  [initial r1]
1 word:  [initial r2]
1 word:  [initial CPSR]

1 word:  [gotten  r3]
1 word:  [gotten  r4]
1 word:  [0000 0000]
1 word:  [gotten  CPSR]

1 word:  [expected r3]
1 word:  [expected r4]
1 word:  [0000 0000]
1 word:  [expected CPSR]
```

### Integration
Already integrated into `gba-accuracy-tests` framework (suite: fuzzarm, 3 tests).

---

## 4. GBA-Test-Collection

**Repository**: https://github.com/ladystarbreeze/GBA-Test-Collection  
**Stars**: 9  
**License**: MIT

### Overview
Collection of GBA test ROMs written in assembly. Currently in early development stage (TODO in README).

### ROMs Available
Not yet available (pre-compiled ROMs not in repo)

### Unique Coverage
Unknown - collection is in early stages. Worth monitoring for future tests.

---

## 5. enhancedcontrolcheckerGBA

**Repository**: https://github.com/nataliethenerd/enhancedcontrolcheckerGBA  
**Stars**: 8  
**License**: Not specified

### Overview
Button test ROM that counts button presses and plays tones. Heavily inspired by Orangeglo's Better Button Test for GB.

### ROMs Available
- `enhancedcontrolchecker.gba`

### What It Tests
- All GBA buttons: A, B, L, R, Start, Select, D-pad
- Input polling
- Button state detection
- Audio output (tone generation)

### Unique Coverage

| Feature | jsmolka | hw-test | enhancedcontrolcheckerGBA |
|---------|---------|---------|---------------------------|
| L/R button test | No | No | **YES** |
| Button press counting | No | No | **YES** |
| Audio feedback | No | No | **YES** |

### Why Important
Most test ROMs don't test L and R shoulder buttons. This ROM specifically validates:
- KEYINPUT register (0x4000130)
- Input polling timing
- All button states

---

## 6. gba-accuracy-tests

**Repository**: https://github.com/cadfan/gba-accuracy-tests  
**Stars**: 0  
**License**: MIT

### Overview
Cross-emulator accuracy benchmark framework. Not a test ROM suite itself, but coordinates running multiple suites and comparing results.

### What It Does
1. Runs test ROMs against multiple emulators
2. Captures framebuffers as raw BGR555 bytes
3. SHA256 hashes each capture
4. Compares across runners + BIOS modes
5. Promotes consensus hashes to "gold"
6. Generates static HTML dashboard

### Integrated Suites

| Suite | Tests | Source |
|-------|-------|--------|
| jsmolka | 13 | jsmolka/gba-tests |
| armwrestler | 6 | destoer/armwrestler-gba-fixed |
| fuzzarm | 3 | DenSinH/FuzzARM |
| mgba-suite | 14 | mgba-emu/suite |
| ags-aging | 1 | TCRF AGS Aging Cartridge |

**Total**: 37 test cases

### Supported Runners

| Runner | Emulator | BIOS Modes |
|--------|----------|------------|
| cable_club | Cable Club | All 3 |
| mgba | mGBA | All 3 |
| nanoboyadvance | NanoBoyAdvance | All 3 |
| skyemu | SkyEmu | All 3 |

### BIOS Modes
- **official** - Real Nintendo BIOS (user-provided)
- **hle** - Emulator's HLE implementation
- **cleanroom** - Cult-of-GBA MIT-licensed replacement

### Key Features

**Reference Hash System**:
- Gold: ≥2 runners agree
- Contested: 2+ distinct hashes with ≥2 votes each
- Unverified: No hash has ≥2 votes

**eWRAM Dump for FuzzARM**:
- Automated test failure detection
- Detailed opcode/operand logging

### Why Critical for GBAtoPy
- Provides gold reference hashes for validation
- Multi-emulator comparison matrix
- Identifies accuracy gaps in our implementation

---

## Coverage Comparison Matrix

| Category | jsmolka | hw-test | armwrestler | gba_tests | FuzzARM | eccGBA |
|----------|---------|---------|-------------|-----------|---------|--------|
| ARM instructions | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ |
| Thumb instructions | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ |
| BIOS functions | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Memory access | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ |
| PPU rendering | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ |
| PPU timing | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ |
| DMA | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ |
| IRQ | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ |
| Timer | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Save types | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| **Load-store edge** | ✗ | ✗ | **✓** | ✗ | **✓** | ✗ |
| **Fuzz testing** | ✗ | ✗ | ✗ | ✗ | **✓** | ✗ |
| **Input (L/R)** | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| **Multi-emulator** | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |

---

## Recommendations for GBAtoPy

### High Priority (Add to pipeline)
1. **FuzzARM** - Massively parallel CPU testing
2. **gba-accuracy-tests** - Golden reference hashes
3. **gba_tests** - Edge cases (IRQ, DMA, windowing)
4. **armwrestler** - Load-store specific

### Medium Priority
1. **enhancedcontrolcheckerGBA** - Input validation
2. **GBA-Test-Collection** - Monitor for new tests

### Integration Strategy
1. Download FuzzARM pre-built ROMs
2. Add gba_tests edge case ROMs
3. Use gba-accuracy-tests for reference comparison
4. Add enhancedcontrolcheckerGBA for input testing

---

## References

- armwrestler: https://github.com/destoer/armwrestler-gba-fixed
- gba_tests: https://github.com/destoer/gba_tests
- FuzzARM: https://github.com/DenSinH/FuzzARM
- GBA-Test-Collection: https://github.com/ladystarbreeze/GBA-Test-Collection
- enhancedcontrolcheckerGBA: https://github.com/nataliethenerd/enhancedcontrolcheckerGBA
- gba-accuracy-tests: https://github.com/cadfan/gba-accuracy-tests