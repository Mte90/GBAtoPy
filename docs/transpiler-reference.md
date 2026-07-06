# GBAtoPy Transpiler Reference

> **For AI Agents Working on the Transpiler**
> 
> This document provides detailed technical specifications for AI agents contributing to GBAtoPy. It covers memory mapping, PPU registers, codegen conventions, and known limitations.

---

## Table of Contents

1. [Memory Mapping](#memory-mapping)
2. [PPU Register Reference](#ppu-register-reference)
3. [Codegen Conventions](#codegen-conventions)
4. [Known Limitations & Workarounds](#known-limitations--workarounds)
5. [GBA Hardware Reference](#gba-hardware-reference)

---

## Memory Mapping

### Complete Memory Map

| Start Address | End Address | Size | Name | Bus Width | Notes |
|---------------|-------------|------|------|-----------|-------|
| 0x00000000 | 0x00003FFF | 16 KB | BIOS ROM | 32-bit | Read-only, protected after boot |
| 0x02000000 | 0x0203FFFF | 256 KB | EWRAM | 16-bit | External work RAM |
| 0x03000000 | 0x03007FFF | 32 KB | IWRAM | 32-bit | Internal work RAM |
| 0x04000000 | 0x040003FF | 1 KB | I/O | 32-bit | Memory-mapped I/O registers |
| 0x05000000 | 0x050003FF | 1 KB | Palette RAM | 16-bit | Background + sprite palettes |
| 0x06000000 | 0x06017FFF | 96 KB | VRAM | 16-bit | Video RAM |
| 0x07000000 | 0x070003FF | 1 KB | OAM | 32-bit | Object Attribute Memory |
| 0x08000000 | 0x09FFFFFF | 32 MB | ROM WS0 | 16-bit | Game Pak ROM, wait state 0 |

### Absolute vs Relative Addresses

**Absolute addresses** are the physical GBA memory addresses (e.g., `0x06000000` for VRAM). The transpiler uses these directly in the generated Python code.

**Relative addresses** are offsets from a base address. For example:
- VRAM offset `0x0000` = absolute address `0x06000000`
- VRAM offset `0x4000` = absolute address `0x06004000`

**Important**: The transpiler converts all relative addresses to absolute addresses in the generated Python. The runtime uses absolute addresses for all memory operations.

### Address Mapping in Generated Python

```python
# Memory regions are defined as absolute addresses
VRAM_BASE = 0x06000000
PALETTE_BASE = 0x05000000
OAM_BASE = 0x07000000
MMIO_BASE = 0x04000000

# Memory access functions use absolute addresses
def read_u16(addr: int) -> int:
    if 0x06000000 <= addr < 0x06018000:
        # VRAM access
        return vram[addr - VRAM_BASE]
    elif 0x05000000 <= addr < 0x05000400:
        # Palette RAM access
        return palette[addr - PALETTE_BASE]
    # ... other regions
```

### Mirror Addresses

Most memory regions are mirrored at higher addresses. The GBA ignores upper address bits, so:

| Region | Physical Range | Mirror Pattern |
|--------|----------------|----------------|
| BIOS | 0x00000000-0x3FFF | Mirrored at 0x01-0x1FFFxxxx |
| EWRAM | 0x02000000-0x3FFFF | Mirrored at 0x024-0x02F |
| IWRAM | 0x03000000-0x7FFFF | Mirrored at 0x031-0x03F |
| I/O | 0x04000000-0x3FF | Mirrored at 0x041-0x04F |
| VRAM | 0x06000000-0x17FFF | Mirrored at 0x062-0x06F |

**Key Rule**: The transpiler normalizes all addresses to their primary range. For example, an access to `0x06200000` (VRAM mirror) is converted to `0x06000000 + offset`.

### Memory Access Sizes

| Region | 8-bit Read | 16-bit Read | 32-bit Read | 8-bit Write | 16-bit Write | 32-bit Write |
|--------|------------|-------------|-------------|-------------|--------------|--------------|
| BIOS | Yes | Yes | Yes | No | No | No |
| EWRAM | Yes | Yes | Yes | Yes | Yes | Yes |
| IWRAM | Yes | Yes | Yes | Yes | Yes | Yes |
| I/O | Yes | Yes | Yes | Yes | Yes | Yes |
| Palette | No | Yes | Yes | No | Yes | Yes |
| VRAM | No | Yes | Yes | No | Yes | Yes |
| OAM | No | Yes | Yes | No | Yes | Yes |
| ROM | Yes | Yes | Yes | No | No | No |
| SRAM | Yes | No | No | Yes | No | No |

---

## PPU Register Reference

### Display Control Registers (0x04000000-0x0400005F)

| Address | Name | R/W | Width | Description |
|---------|------|-----|-------|-------------|
| 0x04000000 | DISPCNT | R/W | 16 | LCD Control |
| 0x04000004 | DISPSTAT | R/W | 16 | General LCD status |
| 0x04000006 | VCOUNT | R | 16 | Vertical counter |
| 0x04000008 | BG0CNT | R/W | 16 | BG0 control |
| 0x0400000A | BG1CNT | R/W | 16 | BG1 control |
| 0x0400000C | BG2CNT | R/W | 16 | BG2 control |
| 0x0400000E | BG3CNT | R/W | 16 | BG3 control |

### DISPCNT Bit Fields (0x04000000)

```
Bit   Name                Description
0-2   BG Mode             0-5=Video Mode 0-5, 6-7=Prohibited
3     Reserved/CGB Mode   0=GBA, 1=CGB (BIOS only)
4     Display Frame Select 0-1=Frame 0-1 (BG Modes 4,5 only)
5     H-Blank Interval Free 1=Allow OAM access during H-Blank
6     OBJ Character VRAM Mapping 0=Two dimensional, 1=One dimensional
7     Forced Blank        1=Allow FAST access to VRAM/Palette/OAM (displays white)
8     Screen Display BG0   0=Off, 1=On
9     Screen Display BG1   0=Off, 1=On
10    Screen Display BG2   0=Off, 1=On
11    Screen Display BG3   0=Off, 1=On
12    Screen Display OBJ   0=Off, 1=On
13    Window 0 Display Flag  0=Off, 1=On
14    Window 1 Display Flag  0=Off, 1=On
15    OBJ Window Display Flag 0=Off, 1=On
```

### BGCNT Bit Fields (0x04000008-0x0400000E)

```
Bit   Name                Description
0-1   BG Priority          0-3, 0=Highest priority
2-3   Character Base Block 0-3, in units of 16 KBytes (BG Tile Data)
4-5   Not used            Must be zero (except NDS mode)
6     Mosaic               0=Disable, 1=Enable
7     Colors/Palettes      0=16/16 (4BPP), 1=256/1 (8BPP)
8-12  Screen Base Block    0-31, in units of 2 KBytes (BG Map Data)
13    Display Area Overflow 0=Transparent, 1=Wraparound (BG2/BG3 only)
14-15 Screen Size          0-3 (see table below)
```

### Screen Size Values

| Value | Text Mode Size | Rotation/Scaling Size | Map Size (bytes) |
|-------|---------------|---------------------|------------------|
| 0 | 256x256 | 128x128 | 2K |
| 1 | 512x256 | 256x256 | 4K |
| 2 | 256x512 | 512x512 | 4K |
| 3 | 512x512 | 1024x1024 | 8K |

### Background Scrolling Registers

| Address | Name | R/W | Width | Description |
|---------|------|-----|-------|-------------|
| 0x04000010 | BG0HOFS | W | 16 | BG0 horizontal offset (0-511) |
| 0x04000012 | BG0VOFS | W | 16 | BG0 vertical offset (0-511) |
| 0x04000014 | BG1HOFS | W | 16 | BG1 horizontal offset |
| 0x04000016 | BG1VOFS | W | 16 | BG1 vertical offset |
| 0x04000018 | BG2HOFS | W | 16 | BG2 horizontal offset |
| 0x0400001A | BG2VOFS | W | 16 | BG2 vertical offset |
| 0x0400001C | BG3HOFS | W | 16 | BG3 horizontal offset |
| 0x0400001E | BG3VOFS | W | 16 | BG3 vertical offset |

### Affine Background Parameters (BG2/BG3)

| Address | Name | R/W | Width | Description |
|---------|------|-----|-------|-------------|
| 0x04000020 | BG2PA | W | 16 | Rotation/scaling parameter A (dx) |
| 0x04000022 | BG2PB | W | 16 | Rotation/scaling parameter B (dmx) |
| 0x04000024 | BG2PC | W | 16 | Rotation/scaling parameter C (dy) |
| 0x04000026 | BG2PD | W | 16 | Rotation/scaling parameter D (dmy) |
| 0x04000028 | BG2X | W | 32 | BG2 reference X-coordinate |
| 0x0400002C | BG2Y | W | 32 | BG2 reference Y-coordinate |

### Window Registers

| Address | Name | R/W | Width | Description |
|---------|------|-----|-------|-------------|
| 0x04000040 | WIN0H | W | 16 | Window 0 horizontal dimensions |
| 0x04000042 | WIN1H | W | 16 | Window 1 horizontal dimensions |
| 0x04000044 | WIN0V | W | 16 | Window 0 vertical dimensions |
| 0x04000046 | WIN1V | W | 16 | Window 1 vertical dimensions |
| 0x04000048 | WININ | R/W | 16 | Inside of Window 0 and 1 |
| 0x0400004A | WINOUT | R/W | 16 | Outside of windows & OBJ window |

### Color Special Effects Registers

| Address | Name | R/W | Width | Description |
|---------|------|-----|-------|-------------|
| 0x04000050 | BLDCNT | R/W | 16 | Color special effects selection |
| 0x04000052 | BLDALPHA | R/W | 16 | Alpha blending coefficients |
| 0x04000054 | BLDY | W | 16 | Brightness coefficient |

---

## Codegen Conventions

### How Rust Converts ARM to Python

The transpiler follows a multi-stage pipeline:

```
ROM → Disassembler → IR → Codegen → Python
```

### Stage 1: Disassembler

The disassembler decodes ARM/Thumb instructions into an intermediate representation (IR).

**ARM Instruction Format:**
```
[31:28] Condition code (0xE = always)
[27:25] Opcode (data processing, branch, etc.)
[24:0]  Operand fields
```

**Thumb Instruction Format:**
```
[15:0]  Full instruction (16-bit)
```

### Stage 2: IR Lifting

The IR represents instructions in a platform-independent format:

```rust
enum Instruction {
    DataProcessing {
        opcode: u8,
        cond: u8,
        rn: u8,
        rd: u8,
        operand2: Operand,
    },
    LoadStore {
        opcode: u8,
        rn: u8,
        rd: u8,
        offset: i32,
    },
    Branch {
        target: u32,
        link: bool,
    },
    // ... more variants
}
```

### Stage 3: Codegen

The codegen converts IR to Python functions. Each instruction type has a specific codegen pattern.

#### Data Processing Instructions

```python
# ARM: ADD r0, r1, r2
# Generated:
r[0] = (r[1] + r[2]) & 0xFFFFFFFF
update_cpsr_flags(r[0])
```

#### Load/Store Instructions

```python
# ARM: LDR r0, [r1, #4]
# Generated:
r[0] = read_u32((r[1] + 4) & 0xFFFFFFFF)

# ARM: STR r0, [r1]
# Generated:
write_u32(r[1], r[0])
```

#### Branch Instructions

```python
# ARM: B label
# Generated:
pc = label_address

# ARM: BLX r0
# Generated:
lr = pc + 4
pc = r[0]
cpsr.t = r[0] & 1  # Thumb mode switch
```

### Basic Block Merging

Sequential instructions are grouped into basic blocks for efficiency:

```python
# Before (unoptimized):
def block_08000000():
    r[0] = read_u32(0x03005000)
    r[1] = r[0] + 1
    r[2] = r[1] * 2
    pc = 0x08000010

# After (merged):
def block_08000000():
    r[0] = read_u32(0x03005000)
    r[1] = (r[0] + 1) & 0xFFFFFFFF
    r[2] = (r[1] * 2) & 0xFFFFFFFF
    pc = 0x08000010
```

### Dispatch Table Mechanism

Branch targets are resolved using a dispatch table:

```python
func_map = {
    0x08000000: "func_08000000",
    0x08000010: "func_08000010",
    # ...
}

def dispatch_table(pc: int) -> str:
    return func_map.get(pc, "default_handler")
```

### Register Naming Convention

Generated Python uses `r[0]` through `r[15]` for ARM registers:

```python
r = [0] * 16  # R0-R15
sp = r[13]    # Stack pointer
lr = r[14]    # Link register
pc = r[15]    # Program counter
cpsr = CPSR() # Processor status
```

### Memory Access Functions

All memory operations use helper functions:

```python
def read_u8(addr: int) -> int: ...
def read_u16(addr: int) -> int: ...
def read_u32(addr: int) -> int: ...

def write_u8(addr: int, value: int) -> None: ...
def write_u16(addr: int, value: int) -> None: ...
def write_u32(addr: int, value: int) -> None: ...
```

These functions handle:
- Address normalization (mirrors)
- VRAM access timing (H-Blank/V-Blank)
- MMIO side effects

---

## Known Limitations & Workarounds

### Mode 1/2 Affine Backgrounds

**Status**: Partial implementation

**Issue**: Affine background rendering (Mode 1/2) uses 16.16 fixed-point transforms that are complex to implement correctly.

**Workaround**: 
- Mode 1/2 are marked as "implemented" but may not render correctly for all ROMs
- Use Mode 0, 3, or 4 for reliable rendering

**Implementation Notes**:
- PA/PB/PC/PD parameters use 7.8 signed fixed-point format
- Reference point (BG2X/BG2Y) uses 19.8 signed fixed-point format
- Screen wrapping depends on the "Display Area Overflow" bit in BGxCNT

### Window Layers

**Status**: Register support only

**Issue**: Window layers (WIN0/WIN1/OBJWIN) are mapped but not fully implemented in the PPU.

**Workaround**:
- Window registers are readable/writable
- Window effects are ignored in rendering
- Use simple backgrounds without windows for now

### Blend Modes

**Status**: Partial implementation

**Issue**: Alpha blending and brightness effects require complex per-pixel calculations.

**Workaround**:
- Basic blend mode formulas are implemented
- Advanced effects (bright/dark enhancement) not implemented
- Test ROMs using blend modes may not render correctly

### 8BPP Tile Modes

**Status**: Partial implementation

**Issue**: 8BPP tile decoding (256 colors) is implemented but not fully tested.

**Workaround**:
- 8BPP mode is enabled by setting BGxCNT Bit 7
- Palette lookup uses 256-color indices
- Test with Mode 0/3/4 first

### Address Mapping Issues

**Status**: Known bug in stripes.gba and shades.gba

**Issue 1: STRH/LDRH Immediate Offset Parsing**
The disassembler incorrectly parses half-word immediate offsets by using bits 7-3 instead of bits 3-0.

**Symptom**: `strh r0, [r1]` generates `memory.write_u16(registers[1] + 22, ...)` instead of `memory.write_u16(registers[1] + 0, ...)`

**Root Cause**: 
```rust
// WRONG (current code)
let imm5 = (word >> 3) & 0x1F;  // bits 7-3

// CORRECT (fix)
let imm4l = word & 0xF;  // bits 3-0
let imm = (imm4h << 4) | imm4l;
```

**Fix Location**: `crates/gbatopy-disasm/src/arm/mod.rs`

**Issue 2: Some ROMs use relative addresses that aren't correctly converted to absolute addresses.**

**Symptoms**:
- Incorrect graphics (wrong colors, missing tiles)
- Screen shows partial content (e.g., 160/38,400 pixels)

**Debugging**:
1. Check VRAM access addresses in generated Python
2. Verify palette RAM initialization
3. Confirm tile data is loaded from correct VRAM offset

**Fix**:
- Ensure all addresses are normalized to primary range
- Check for mirror address handling
- Verify offset calculations for tile/map data

---

## GBA Hardware Reference

### CPU Specifications

| Feature | Value |
|---------|-------|
| Architecture | ARM7TDMI (ARMv4T) |
| Clock Speed | 16.78 MHz |
| Instruction Set | ARM (32-bit) + Thumb (16-bit) |
| Registers | 16 × 32-bit (R0-R15) |
| CPSR Flags | N, Z, C, V, T, I, F |

### Display Specifications

| Feature | Value |
|---------|-------|
| Resolution | 240×160 pixels |
| Refresh Rate | 60 Hz |
| Colors | 32,768 (15-bit RGB555) |
| Background Layers | 4 (BG0-BG3) |
| Sprites | 128 (OBJ) |
| VRAM | 96 KB |
| Palette RAM | 1 KB |

### PPU Modes

| Mode | Type | Layers | Color Depth | Status |
|------|------|--------|-------------|--------|
| 0 | Text/Map | BG0-BG3 | 4BPP/8BPP | ✅ Verified (shades.gba golden match) |
| 1 | Text + Affine | BG0-BG1 | 4BPP/8BPP | ⚠️ Stubs (code exists, MMIO broken) |
| 2 | Affine | BG2-BG3 | 8BPP | ⚠️ Stubs (code exists, not verified) |
| 3 | Bitmap | BG2 | 15-bit | ✅ Verified (stripes.gba golden match) |
| 4 | Bitmap | BG2 | 8BPP | ⚠️ Partial (palette fallback fixed, not all ROMs verified) |
| 5 | Bitmap | BG2 | 15-bit | ⚠️ Unverified |

### Audio Specifications

| Feature | Value |
|---------|-------|
| Channels | 4 (CH1-CH4) + 2 FIFO |
| Sample Rate | 32.768 kHz (max) |
| Bit Depth | 16-bit |
| Memory | 32 KB wave RAM (CH3) |

### Memory Access Timing

| Region | 8-bit | 16-bit | 32-bit |
|--------|-------|--------|--------|
| BIOS | 1 cycle | 1 cycle | 1 cycle |
| IWRAM | 1 cycle | 1 cycle | 1 cycle |
| EWRAM | 3/6 cycles | 3/6 cycles | 6/12 cycles |
| VRAM | 1/2 cycles | 1/2 cycles | 2/4 cycles |
| ROM | 5/8 cycles | 5/8 cycles | 8/16 cycles |

**Note**: VRAM/OAM/Palette access is restricted to H-Blank or V-Blank unless Forced Blank is set.

---

## Quick Reference for AI Agents

### When Adding New Instructions

1. **Disassembler**: Add opcode decoding in `crates/gbatopy-disasm/src/arm/`
2. **IR**: Add IR variant in `crates/gbatopy-ir/src/ir.rs`
3. **Codegen**: Add Python codegen in `crates/gbatopy-cli/src/codegen/`

### When Fixing Memory Access

1. **Address normalization**: Check `memory.rs` for mirror handling
2. **VRAM timing**: Verify H-Blank/V-Blank checks
3. **MMIO side effects**: Update `mmio.rs` for register writes

### When Debugging Rendering Issues

1. **Check DISPCNT**: Verify BG mode and layer enables
2. **Check BGCNT**: Verify priority, tile base, map base
3. **Check scrolling**: Verify BGxHOFS/BGxVOFS values
4. **Check palette**: Verify RGB555 colors in 0x05000000-0x050003FF

### Common Pitfalls

- **Address mirrors**: Always normalize to primary range
- **VRAM access timing**: Only access during H-Blank/V-Blank
- **RGB555 conversion**: Use `(value * 255) // 31` formula
- **CPSR flags**: Update after every arithmetic operation
- **Thumb mode**: Check CPSR.T bit for mode switching

---

**Document Version**: 1.0 (2026-06-26)  
**Maintained by**: GBAtoPy Documentation Team  
**For questions**: See `docs/architecture.md` for project structure
