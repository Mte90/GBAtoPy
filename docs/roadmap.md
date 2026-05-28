# GBAtoPy Roadmap — Project Status

> **Last updated**: 2026-05-22
> **Current state**: 66 ROMs transpile successfully. PPU Mode 3/4 verified working with 100% golden screenshot match. 54 BIOS handlers implemented. DMA/Timer/IRQ infrastructure exists.
> **Blockers**: 
> - APU audio synthesis not implemented
> - Mode 0 (4BPP tiles) rendering needs completion
> - Affine backgrounds (Mode 1/2) out of scope

---

## 1. Project Overview

GBAtoPy is a **transpiler** that converts GBA ROMs into standalone Python files playable with pygame. NOT an emulator — the output is human-readable Python source code.

## 2. Detailed Progress

### Wave 1: Core Infrastructure ✅ Complete
- Rust pipeline builds with zero warnings
- Disassembler decodes ARM/Thumb instructions (~100% coverage)
- Python generation produces syntactically valid output for all 66 ROMs
- Memory map implemented (ROM, EWRAM, IWRAM, MMIO, VRAM, Palette, OAM)

### Wave 2: CPU Core ✅ Complete
- ARM7TDMI core implemented (22K lines)
- All ARM data processing instructions (MOV, ADD, SUB, ORR, AND, EOR, BIC, MVN, SBC, ADC)
- Load/store instructions (LDR, STR, LDRH, STRH, LDRB, STRB)
- Branch instructions (B, BL, BLX, BX, CBZ, CBNZ) with PC-relative offset handling
- Multiply instructions (MUL, MLA)
- MRS/MSR, SWP/SWPB, LDM/STM (all variants)
- Thumb mode codegen (~100% coverage)
- Global register propagation across function boundaries
- PC auto-advance fix (registers update correctly)

### Wave 3: BIOS Handlers ✅ Complete
- 54 BIOS SWI handlers implemented in bios.py
- Core handlers: Halt, IntrWait, VBlankIntrWait, Div, Sqrt
- CPU operations: CPUSet, CPUFastSet
- Decompression: LZ77, Huffman, RLE
- Arithmetic: ArcTan, ArcTan2, BitCount, Sin, Cos
- Geometry: ObjAffineSet, BgAffineSet
- MIDI operations, Time functions, Sound control

### Wave 4: PPU Rendering ✅ Partial
- **Mode 3 (15-bit bitmap)**: Working — stripes.gba achieves 100% golden screenshot match
- **Mode 4 (8BPP bitmap)**: Working with palette lookup
- **Mode 0 (4BPP tiles)**: Partial — tile rendering exists but needs text mode completion
- **Mode 1/2 (Affine)**: Registers stored but rendering not implemented (out of scope)
- Sprite rendering: OAM parsing + tile fetch + palette lookup implemented
- BGR555 to RGB888 color conversion working

### Wave 5: DMA Controller ✅ Partial
- All 4 DMA channels implemented
- Immediate, VBlank, HBlank, and special trigger modes
- 16/32-bit transfer modes
- Increment/Decrement/Fixed addressing modes
- Repeat mode support
- FIFO A/B modes for audio (infrastructure exists, no audio synthesis)

### Wave 6: Timer & IRQ ✅ Partial
- Timers 0-3 with prescaler (1/64/256/1024)
- Cascade mode support
- Overflow interrupt handling
- IRQ system: IE/IF/IME registers, ISR dispatch at 0x03007FFC
- VBlank/HBlank/VCount timer interrupts
- DISPSTAT/LYC interrupt support
- ISR handler with ARM/Thumb mode switching

### Wave 7: Input Handling ✅ Complete
- KEYINPUT register (0x04000130) implemented
- KEYCNT register (0x04000132) for combo keys
- pygame keyboard mapping integration

### Wave 8: Verification ✅ Complete
- Golden screenshot comparison pipeline working
- compare_screenshots.py handles resolution differences
- 100% match achieved for stripes.gba (Mode 3)
- All 66 ROMs produce syntactically valid Python
- Zero parsing failures across test ROMs

## 3. What Works (May 2026)

| Component | Status | Notes |
|-----------|--------|-------|
| Rust pipeline | ✅ Builds | Zero compiler warnings |
| Disassembler | ✅ Working | ~100% ARM/Thumb coverage |
| Python generation | ✅ Working | All 66 ROMs produce valid Python |
| Memory map | ✅ Working | Full GBA memory layout with mirrors |
| CPU core | ✅ Working | ARM7TDMI with global registers |
| PPU Mode 3 | ✅ Working | 100% golden screenshot match |
| PPU Mode 4 | ✅ Working | 8BPP bitmap with palette |
| PPU Mode 0 | ⚠️ Partial | 4BPP tiles working, text mode needs completion |
| Sprite rendering | ✅ Working | OAM parsing + tile fetch |
| BIOS handlers | ✅ Working | 54 SWI handlers implemented |
| DMA controller | ✅ Working | All 4 channels operational |
| Timers | ✅ Working | 4 timers with cascade mode |
| IRQ system | ✅ Working | ISR dispatch, VBlank/HBlank |
| Input handling | ✅ Working | KEYINPUT/KEYCNT registers |

## 4. What Doesn't Work Yet

| Component | Status | Notes |
|-----------|--------|-------|
| APU audio | ❌ Stub | DMA FIFO infrastructure exists, no synthesis |
| Mode 0 text rendering | ⚠️ Partial | render_text_mode() needs implementation |
| Affine backgrounds | ❌ Out of scope | Mode 1/2 transforms not implemented |
| Windows/Blend/Mosaic | ❌ Out of scope | Advanced PPU features |
| 8BPP tile modes | ❌ Not implemented | Only 4BPP for tiled backgrounds |

## 5. Test ROMs

66 ROMs across multiple suites. All transpile without errors.

| Suite | ROMs | Status |
|-------|------|--------|
| jsmolka/gba-tests | 16 | Valid Python, verified rendering |
| armwrestler-gba | 1 | Valid Python |
| FuzzARM | 1 | Valid Python |
| libbet | 1 | Valid Python |
| GBA-Test-Collection | 1 | Valid Python |
| destoer/gba_tests | 4 | Valid Python |
| enhancedcontrolcheckerGBA | 1 | Valid Python |
| gba-sound-demo | 1 | Valid Python |
| hw-test | 3 | Valid Python |
| FalseDiagonalTest | 1 | Valid Python |
| gba-playground | 2 | Valid Python |
| tonc | 1 | Valid Python |
| blargg | 3 | Valid Python |
| misc/custom | 4 | Valid Python |

## 6. Recent Fixes

1. **r15 initialization** - PC starts at 0x08000000 (header.py)
2. **Register-reset ordering** - Removed duplicate instantiation in header.py
3. **run_with_pygame execution** - Now calls transpiled game logic
4. **PC auto-advance** - 81 functions have r15 auto-advance
5. **DISPCNT defaults** - Test ROMs now render with sensible defaults
6. **Italian comments** - All runtime comments translated to English
7. **Golden screenshot pipeline** - stripes.gba achieves 100% match

## 7. Priority Roadmap

### Phase 1: Complete Mode 0 (1-2 days)
- Implement render_text_mode()
- Tile data reading from VRAM
- Tilemap parsing
- Palette lookup for 4BPP tiles
- Scroll register support

### Phase 2: Audio (3-5 days, optional)
- pygame mixer initialization
- Square wave channels 1-2
- Wave channel 3
- Noise channel 4
- Direct Sound A/B (FIFO → PCM)
- Mixing and volume control

### Phase 3: Automated Testing (2-3 days)
- Extend `visual_test.py` with hw-test golden images (5 PPU ROMs)
- Add `--dump-memory` flag to Python runtime for eWRAM access
- Build FuzzARM eWRAM parser (50,000 CPU instruction tests)
- Build screen pass/fail detector for gba-tests-master ROMs
- Create unified test runner
- See [testing-framework.md](testing-framework.md) for full plan

### Phase 4: Polish (1-2 days)
- Window layers (optional)
- Alpha blending (optional)
- Documentation updates
- README improvements

## 8. File Structure

```
crates/gbatopy-disasm/src/     — ARM/Thumb disassembler
crates/gbatopy-cli/src/
  cmds/pipeline.rs             — Main transpilation pipeline (<800 lines)
  codegen/                     — Instruction codegen modules
    arm_ops.rs                 — ARM instruction codegen
    thumb_ops.rs               — Thumb instruction codegen
    instruction_codegen.rs     — Unified codegen dispatcher
    helpers.rs                 — Code generation helpers
crates/gbatopy-cli/assets/
  gba_runtime/                 — Python runtime (embedded at compile-time)
    arm7tdmi.py                — CPU core (22K lines)
    ppu.py                     — PPU renderer (Mode 0/3/4 + sprites)
    memory.py                  — Memory-mapped I/O
    bios.py                    — 54 SWI handlers
    dma.py                     — DMA controller
    timers.py                  — Timer 0-3
    interrupts.py              — IRQ system
    input.py                   — KEYINPUT handler
    text_lib.py                — Text utilities
  templates/
    header.py                  — Runtime setup, register init
    game_loop.py               — Execution loop
```

## 9. Attribution

The Python runtime modules are derived from [PyBoyAdvance](https://github.com/williamckha/PyBoyAdvance) by williamckha, licensed under the MIT License.

## 10. License

MIT License — See LICENSE file
