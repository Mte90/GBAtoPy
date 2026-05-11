# GBA Feature Coverage Reference

## Overview

This document tracks which GBA features are implemented in GBAtoPy and which features are used by test ROMs. It is generated automatically by `coverage_tracker.py`.

## Transpiler Support Status

### ARM Instructions (42 total)

| Category | Status | Notes |
|----------|--------|-------|
| Data Processing | ✅ Implemented | MOV, ADD, ADC, SUB, SBC, RSB, RSC, AND, EOR, ORR, BIC, TST, TEQ, CMP, CMN, plus suffix variants |
| Multiply | ✅ Implemented | MUL, MLA, UMULL, UMLAL, SMULL, SMLAL |
| Load/Store | ✅ Implemented | LDR, STR, LDRB, STRB, LDRH, STRH, LDRSB, LDRSH |
| Load/Store Multiple | ✅ Implemented | LDM (all variants), STM (all variants), SWP, SWPB |
| Branch | ✅ Implemented | B, BL, BLX, BX, all conditional branches (BEQ, BNE, BCS, etc.) |
| Status | ✅ Implemented | MRS, MSR |
| Other | ✅ Implemented | SWI, NOP, and variants |

### Thumb Instructions (51 total)

| Category | Status | Notes |
|----------|--------|-------|
| Data Processing | ✅ Implemented | MOV, ADD, SUB, AND, EOR, ORR, BIC, CMP, CMN, TST, shifts (LSL, LSR, ASR, ROR) |
| Load/Store | ✅ Implemented | LDR, STR, LDRB, STRB, LDRH, STRH, LDRSP, STRSP, LDRPC |
| Load/Store Multiple | ✅ Implemented | PUSH, POP, LDMIA, STMIA |
| Branch | ✅ Implemented | All 16 conditional and unconditional branches |
| Other | ✅ Implemented | SWI, NOP, ADDSP, SUBSP |

### MMIO Registers (87 total)

| Category | Status | Notes |
|----------|--------|-------|
| Display (0x04000000-0x0400005F) | ✅ Implemented | DISPCNT, DISPSTAT, VCOUNT, BG0CNT-BG3CNT, BGxHOFS, BGxVOFS, BG2PA-PG3Y, WINxH, WINxV, WININ, WINOUT, MOSAIC, BLDx registers |
| Sound (0x04000060-0x040000A5) | ⚠️ Partial | Sound CNT registers implemented, FIFO DMA access available but no audio synthesis |
| DMA (0x040000B0-0x040000DE) | ✅ Implemented | All 4 channels with all control registers |
| Timers (0x04000100-0x0400010E) | ✅ Implemented | TM0-3 with prescaler, cascade, IRQ, enable |
| Keypad (0x04000130-0x04000132) | ✅ Implemented | KEYINPUT, KEYCNT |
| Serial (0x04000120-0x0400015A) | ⚠️ Partial | SIO, RCNT, JOY registers available but not fully implemented |
| Interrupts (0x04000200-0x04000208) | ✅ Implemented | IE, IF, IME |
| System (0x04000204, 0x04000300-0x04000301) | ✅ Implemented | WAITCNT, POSTFLG, HALTCNT |

### PPU Modes (6 total)

| Mode | Status | Description |
|------|--------|-------------|
| Mode 0 | ✅ Implemented | 4 text backgrounds (160×160 each, displayed as 240×160), tile-based with palette lookup |
| Mode 1 | ⚠️ Stub | Text + Rotation/Scaling - registers implemented but not rendered |
| Mode 2 | ⚠️ Stub | Rotation/Scaling only - registers implemented but not rendered |
| Mode 3 | ✅ Implemented | 16-bit bitmap (320×240, BGR555), scaled to 240×160 |
| Mode 4 | ✅ Implemented | 8-bit palette bitmap (240×160, 256-color), with double buffering |
| Mode 5 | ⚠️ Stub | 16-bit bitmap (240×160) - infrastructure exists, not tested |

### BIOS SWI Functions (45 total)

| Category | Status | Notes |
|----------|--------|-------|
| System Control | ✅ Implemented | SoftReset, Halt, Stop, RegisterRamReset, PostBootReset |
| Interrupts | ✅ Implemented | VBlankIntrWait, IntrWait with DISPCNT/LYC/DMASK support |
| Math | ✅ Implemented | Div, DivArm, Sqrt, ArcTan, ArcTan2 via Python math module |
| CPU Set | ✅ Implemented | CpuSet, CpuFastSet for memory copy |
| Affine | ⚠️ Partial | BgAffineSet, ObjAffineSet - registers stored but not processed |
| Decompression | ⚠️ Stub | LZ77, HuffUnComp, RLUnComp - stubs only |
| Sound | ⚠️ Stub | Sound driver functions - not implemented (no audio synthesis) |
| Music | ⚠️ Stub | Music player functions - not implemented |

## Known Limitations

### Audio
- DMA FIFO_A/FIFO_B registers can be written but no audio output
- Sound DMA (DMA1/2 FIFO triggers) infrastructure exists but no synthesis
- All sound driver SWI handlers are stubs

### Affine Rendering
- BG2/BG3 affine register arrays implemented
- 32×32 transformation matrices stored in MMIO
- Mode 1/2 display not rendered (hardcoded Mode 0/3/4)

### Windows/Mosaic
- WIN0/1, WININ, WINOUT registers implemented
- MOSAIC register implemented
- No window rendering or mosaic effect applied

## Test ROM Coverage

Run coverage analysis:

```bash
# Single ROM
python3 scripts/verify_roms/coverage_tracker.py <transpiled_rom.py>

# Multiple ROMs
python3 scripts/verify_roms/coverage_tracker.py --roms-dir <dir> --output-dir <output> --summary
```

## Coverage Thresholds

To maintain test ROM compatibility:
- ARM instruction coverage: ≥95% of used instructions supported
- Thumb instruction coverage: ≥95% of used instructions supported
- MMIO register access: 100% of accessed registers implemented
- PPU mode rendering: All modes used by ROMs must render

## Contribution Guidelines

When adding feature support:
1. Update this document with the new feature
2. Verify it passes with `cargo build --release`
3. Test with at least 3 diverse ROMs
4. Document any limitations or edge cases
