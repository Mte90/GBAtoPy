# GBA PPU Reference - Technical Specification

> **GBAtoPy Project Documentation**
> Extracted from official gbatek documentation for GBA hardware programming
> Purpose: Fix stripes.gba rendering issue (brown instead of blue-grey)

---

## Table of Contents

1. [Memory Map Overview](#memory-map-overview)
2. [Display Control Register (DISPCNT)](#display-control-register-dispcnt)
3. [Background Control Registers (BG0CNT-BG3CNT)](#background-control-registers-bg0cnt-bg1cnt-bg2cnt-bg3cnt)
4. [Mode 0 Text Background Rendering](#mode-0-text-background-rendering)
5. [4BPP Tile Format](#4bpp-tile-format)
6. [Palette Format (RGB555)](#palette-format-rgb555)
7. [VRAM Memory Map](#vram-memory-map)
8. [RGB555 to RGB888 Conversion](#rgb555-to-rgb888-conversion)
9. [BG0CNT=0x104 Analysis](#bg0cnt0x104-analysis)
10. [PPU Implementation Issues to Check](#ppu-implementation-issues-to-check)

---

## Memory Map Overview

### Internal Display Memory

```
05000000-050003FF   BG/OBJ Palette RAM        (1 Kbyte)  
05000400-05FFFFFF   Not used
06000000-06017FFF   VRAM - Video RAM          (96 KBytes)
06018000-06FFFFFF   Not used
07000000-070003FF   OAM - OBJ Attributes      (1 Kbyte)
07000400-07FFFFFF   Not used
```

### I/O Registers (PPU-related)

```
4000000h  2    R/W  DISPCNT   LCD Control
4000002h  2    R/W  -         Undocumented - Green Swap
4000004h  2    R/W  DISPSTAT  General LCD Status (STAT,LYC)
4000006h  2    R    VCOUNT    Vertical Counter (LY)
4000008h  2    R/W  BG0CNT    BG0 Control
400000Ah  2    R/W  BG1CNT    BG1 Control
400000Ch  2    R/W  BG2CNT    BG2 Control
400000Eh  2    R/W  BG3CNT    BG3 Control
4000010h  2    W    BG0HOFS   BG0 X-Offset
4000012h  2    W    BG0VOFS   BG0 Y-Offset
4000014h  2    W    BG1HOFS   BG1 X-Offset
4000016h  2    W    BG1VOFS   BG1 Y-Offset
4000018h  2    W    BG2HOFS   BG2 X-Offset
400001Ah  2    W    BG2VOFS   BG2 Y-Offset
400001Ch  2    W    BG3HOFS   BG3 X-Offset
400001Eh  2    W    BG3VOFS   BG3 Y-Offset
```

---

## Display Control Register (DISPCNT)

**Address:** 0x04000000  
**Size:** 16-bit (2 bytes)  
**Access:** Read/Write

### Bit Layout

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

### Display Modes Summary

| Mode | Type | Layers | Features | Notes |
|------|------|--------|----------|-------|
| 0 | Text/Map | BG0-BG3 | S,F,M,A,B,P | 4 tile layers, 16/16 or 256/1 palettes |
| 1 | Text/Map + Affine | BG0-BG1 | S,F,M,A,B,P | BG2 is affine rotation/scaling |
| 2 | Affine | BG2-BG3 | S,M,A,B,P | 2 affine backgrounds |
| 3 | Bitmap | BG2 | - | 240x160, 32768 colors (15-bit) |
| 4 | Bitmap | BG2 | - | 240x160, 256 colors (8BPP) |
| 5 | Bitmap | BG2 | - | 160x128, 32768 colors (15-bit) |

**Features:** S=Scrolling, F=Flip, M=Mosaic, A=Alpha Blending, B=Brightness, P=Priority


### Important Notes

- **Forced Blank (Bit 7):** When set, displays white lines and allows fast access to VRAM/Palette/OAM
- **H-Blank Interval Free (Bit 5):** Allows OAM access during H-Blank (reduces sprites per line)
- **Display Enable Bits (Bits 8-12):** Control which backgrounds and OBJs are displayed
- **Frame Selection (Bit 4):** In BG Modes 4-5, selects which frame buffer to display

---

## Background Control Registers (BG0CNT-BG3CNT)

**Addresses:** 0x04000008-0x0400000E  
**Size:** 16-bit (2 bytes) each  
**Access:** Read/Write

### Common Bit Layout (for all BG registers)

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

### Character Base Block Calculation

Character base blocks are 16KB (0x4000) each:

```
Block 0: 0x06000000-0x06003FFF
Block 1: 0x06004000-0x06007FFF
Block 2: 0x06008000-0x0600BFFF
Block 3: 0x0600C000-0x0600FFFF
```

**Address formula:** `0x06000000 + (char_base_block * 0x4000)`

### Screen Base Block Calculation

Screen base blocks are 2KB (0x800) each:

```
Block 0: 0x06000000-0x060007FF
Block 1: 0x06000800-0x06000FFF
Block 2: 0x06001000-0x060017FF
...
Block 31: 0x0600F800-0x0600FFFF
```

**Address formula:** `0x06000000 + (screen_base_block * 0x800)`

### Priority Rules

- **BG0 > BG1 > BG2 > BG3** (lower number = higher priority)
- If multiple BGs have same priority, BG0 wins
- OBJ priority: 0-127 (lower number = higher priority)
- OBJ/BG priority: 0-3 (lower number = higher priority)

---

## Mode 0 Text Background Rendering

### Overview

Mode 0 uses **4 tile-based background layers** (BG0-BG3). Each layer:
- Uses **4BPP or 8BPP tiles** (selected by BGxCNT Bit 7)
- Has **tile data** (character base block) and **map data** (screen base block)
- Supports **scrolling** via BGxHOFS/BGxVOFS registers
- Supports **mosaic** (if enabled in BGxCNT Bit 6)


### Rendering Algorithm (Step-by-Step)

1. **Initialize scanline buffer** (240 pixels, each with color index + priority)

2. **For each background layer (BG0-BG3):**
   - **Check if enabled** (DISPCNT Bit 8-11 AND BGxCNT priority valid)
   - **Get tile data address:** `0x06000000 + (char_base_block * 0x4000)`
   - **Get map data address:** `0x06000000 + (screen_base_block * 0x800)`
   - **Apply scrolling:** Add BGxHOFS/BGxVOFS offsets to current position
   - **For each pixel in scanline:**
     a. Calculate **tile coordinates** from screen position
     b. Fetch **tile index** from map data (2 bytes per tile in 4BPP mode)
     c. Calculate **pixel within tile** (8x8 grid)
     d. Fetch **4BPP pixel data** from tile data
     e. Lookup **palette color** from palette RAM
     f. **Blend with existing pixel** based on priority

3. **Render sprites (OBJs)** on top of backgrounds

4. **Apply special effects** (alpha blending, brightness)

5. **Output final pixel** to display

### Map Data Format (Text Mode)

Each **tile entry** is 2 bytes (16-bit):

```
Bit   Description
0-9   Tile Index (0-1023)
10-11 Palette Bank (0-3, selects which 16-color palette to use)
12    Horizontal Flip (0=normal, 1=flip)
13    Vertical Flip   (0=normal, 1=flip)
14-15 Priority (0-3, same as BG priority)
```

**Total map size:** 32x32 tiles = 2K bytes, 64x64 tiles = 8K bytes

### Tile Coordinate Calculation

Given screen position (x, y) and scroll offsets (sx, sy):

```
tile_x = (x + sx) / 8  (integer division)
tile_y = (y + sy) / 8  (integer division)
```

Map address calculation:
```
map_addr = base_map_addr + (tile_y * 32 + tile_x) * 2
```

---

## 4BPP Tile Format

### Tile Structure

Each **tile** is 8x8 pixels = 64 pixels total  
Each **pixel** is 4 bits (16 possible colors)  

**Memory required per tile:** 32 bytes (64 pixels × 4 bits / 8 bits per byte)

### Tile Data Layout

Tiles are stored in **character base blocks** in VRAM. Each block is 16KB (0x4000 bytes).

**Tile addressing:** `tile_index * 32` bytes from base address


### Pixel Data Encoding

Each **byte** contains **2 pixels** (4 bits each):

```
Byte 0: Pixel 0 (bits 0-3) + Pixel 1 (bits 4-7)
Byte 1: Pixel 2 (bits 0-3) + Pixel 3 (bits 4-7)
...
Byte 31: Pixel 62 (bits 0-3) + Pixel 63 (bits 4-7)
```

**Pixel bit order:** Left-to-right, top-to-bottom

**Example:** For a tile with pixels [A,B,C,D,...], the first byte would be:
- Bits 0-3: Pixel A
- Bits 4-7: Pixel B

### 4BPP Decoding Algorithm

```python
def decode_4bpp_tile(tile_data: bytes, palette_bank: int) -> list[int]:
    """
    Decode a 4BPP tile to palette indices.
    
    Args:
        tile_data: 32 bytes of tile data
        palette_bank: 0-3 (selects palette 0-3 from 16-color palette set)
    
    Returns:
        List of 64 palette indices (0-15)
    """
    pixels = []
    for byte in tile_data:
        # Extract two 4-bit pixels from each byte
        pixel1 = byte & 0x0F      # Lower 4 bits
        pixel2 = (byte >> 4) & 0x0F  # Upper 4 bits
        pixels.extend([pixel1, pixel2])
    
    # Apply palette bank offset
    # Each palette bank has 16 colors (indices 0-15)
    # Palette bank 0: indices 0-15
    # Palette bank 1: indices 16-31
    # etc.
    return [p + (palette_bank * 16) for p in pixels]
```

---

## Palette Format (RGB555)

### Palette RAM Structure

**Address:** 0x05000000-0x050003FF  
**Size:** 1 Kbyte (512 × 16-bit words)  
**Access:** 16-bit or 32-bit reads/writes

### Palette Organization

```
05000000-050001FF   Background Palette RAM (256 colors)
05000200-050003FF   OBJ (Sprite) Palette RAM (256 colors)
```

### RGB555 Color Format

Each **color** is stored as a 16-bit word:

```
Bit   Description
0-4   Red   (5 bits, 0-31)
5-9   Green (5 bits, 0-31)
10-14 Blue  (5 bits, 0-31)
15    Not used (always 0)
```

**Total colors:** 32,768 possible (2^15)

### RGB555 to RGB888 Conversion

```python
def rgb555_to_rgb888(color16: int) -> tuple[int, int, int]:
    """
    Convert RGB555 to RGB888 (8-bit per channel).
    
    Args:
        color16: 16-bit RGB555 value
    
    Returns:
        (r, g, b) tuple with 8-bit values (0-255)
    """
    r5 = (color16 >> 0) & 0x1F
    g5 = (color16 >> 5) & 0x1F
    b5 = (color16 >> 10) & 0x1F
    
    # Convert 5-bit to 8-bit: (value * 255) / 31
    r8 = (r5 * 255) // 31
    g8 = (g5 * 255) // 31
    b8 = (b5 * 255) // 31
    
    return (r8, g8, b8)
```

### Palette Indexing

- **4BPP mode:** Each pixel value (0-15) indexes into the palette
- **8BPP mode:** Each pixel value (0-255) indexes into the palette
- **Palette banks:** In 4BPP mode, bits 10-11 of map data select palette bank (0-3)
  - Palette bank 0: colors 0-15
  - Palette bank 1: colors 16-31
  - Palette bank 2: colors 32-47
  - Palette bank 3: colors 48-63

---

## VRAM Memory Map

### VRAM Organization by Mode

#### BG Mode 0, 1, 2 (Tile/Map based)

```
06000000-0600FFFF  64 KBytes shared for BG Map and Tiles
06010000-06017FFF  32 KBytes OBJ Tiles
```

**Shared 64KB area can be split:**
- Map area(s): Set by BGxCNT screen base block (2KB units)
- Tile area(s): Set by BGxCNT character base block (16KB units)

#### BG Mode 3 (Bitmap mode)

```
06000000-06013FFF  80 KBytes Frame 0 buffer (240x160x15-bit = 75K used)
06014000-06017FFF  16 KBytes OBJ Tiles
```

#### BG Mode 4 (Bitmap mode, 8BPP)

```
06000000-06009FFF  40 KBytes Frame 0 buffer (240x160x8-bit = 37.5K used)
0600A000-06013FFF  40 KBytes Frame 1 buffer (240x160x8-bit = 37.5K used)
06014000-06017FFF  16 KBytes OBJ Tiles
```

### VRAM Access Rules

- **VRAM can be accessed during H-Blank or V-Blank only** (unless display disabled)
- **Forced Blank (DISPCNT Bit 7)** allows unrestricted access
- **Accesses during active display** incur 1 cycle wait penalty
- **VRAM bus width:** 16-bit

---

## RGB555 to RGB888 Conversion

### Formula

The GBA uses **RGB555** format internally. When displaying, colors are converted to **RGB888** for output.

**Conversion formula:**
```
RGB888_value = (RGB555_value * 255) / 31
```

### Implementation

```python
# Direct conversion (fast)
def rgb555_to_rgb888(color16: int) -> tuple[int, int, int]:
    r5 = (color16 >> 0) & 0x1F
    g5 = (color16 >> 5) & 0x1F
    b5 = (color16 >> 10) & 0x1F
    
    return ((r5 * 255) // 31, 
            (g5 * 255) // 31, 
            (b5 * 255) // 31)
```

### Common RGB555 Colors

| Color | RGB555 | RGB888 | Description |
|-------|---------|---------|-------------|
| 0x0000 | (0,0,0) | (0,0,0) | Black |
| 0x7C00 | (31,0,0) | (255,0,0) | Red |
| 0x03E0 | (0,31,0) | (0,255,0) | Green |
| 0x001F | (0,0,31) | (0,0,255) | Blue |
| 0x7FFF | (31,31,31) | (255,255,255) | White |
| 0x03FF | (0,31,31) | (0,255,255) | Cyan |
| 0x7C1F | (31,0,31) | (255,0,255) | Magenta |
| 0x7FE0 | (31,31,0) | (255,255,0) | Yellow |
| 0x4210 | (20,10,0) | (160,80,0) | Brown |
| 0x5294 | (25,20,20) | (200,160,160) | Grey |
```

---

## BG0CNT=0x104 Analysis

### Register Value Breakdown

**BG0CNT = 0x104**

```
Binary: 0000 0001 0000 0100
Hex:    0x104
```

### Bit-by-Bit Analysis

```
Bit 15-12: 0001 = Screen Size = 1 (512x256 pixels)
Bit 11-8:  0000 = Screen Base Block = 1 (0x06000800)
Bit 7:      0 = Colors/Palettes = 4BPP mode
Bit 6:      0 = Mosaic = Disabled
Bit 5-4:    00 = Not used = Must be zero
Bit 3-2:    01 = Character Base Block = 1 (0x06004000)
Bit 1-0:    00 = Priority = 0 (Highest priority)
```

### Memory Address Calculation

#### Character Base Block (Tile Data)

- **Bit 2-3 = 01** → Character base block 1
- **Each block = 16 KBytes**
- **Address = 0x06000000 + (1 * 0x4000) = 0x06004000**

**What this means:** Tile data (character patterns) starts at VRAM 0x06004000

#### Screen Base Block (Map Data)

- **Bit 8-12 = 00001** → Screen base block 1
- **Each block = 2 KBytes**
- **Address = 0x06000000 + (1 * 0x800) = 0x06000800**

**What this means:** Background map data starts at VRAM 0x06000800

#### Screen Size

- **Bit 14-15 = 01** → Screen size = 1
- **Text mode size = 512x256 pixels**
- **Map size = 64x32 tiles** (since 512/8=64, 256/8=32)
- **Total map size = 64x32 × 2 bytes = 4096 bytes = 4K**

### Expected Behavior

With BG0CNT=0x104:
1. **Tile data** is read from VRAM 0x06004000
2. **Map data** is read from VRAM 0x06000800
3. **Mode = 4BPP** (Bit 7 = 0)
4. **Priority = 0** (highest)
5. **Screen = 512x256** (wraps around at edges)
6. **No mosaic** (Bit 6 = 0)

### Why This Should Work for stripes.gba

The stripes.gba ROM likely uses:
- **Mode 0** (text mode with 4BPP tiles)
- **BG0** for the main background
- **Character base block 1** for tile patterns
- **Screen base block 1** for map data
- **4BPP color depth** for palette-based rendering

If the colors are wrong (brown instead of blue-grey), the issue is likely:
1. **Palette RAM not initialized correctly** (wrong colors in palette)
2. **Tile data not loaded correctly** (wrong tile patterns)
3. **Map data not loaded correctly** (wrong tile indices)
4. **Color conversion wrong** (RGB555 to RGB888)
5. **Priority blending wrong** (OBJ/BG priority issues)

---

## PPU Implementation Issues to Check

### High Priority Issues (Likely Cause of stripes.gba Color Problem)

#### 1. Palette RAM Initialization

**Issue:** Palette RAM might not be initialized with correct colors

**Check:**
- Verify palette RAM writes are happening at correct addresses (0x05000000-0x050003FF)
- Check that RGB555 colors are stored correctly
- Verify palette bank selection for 4BPP mode

**Expected:** Background palette (0x05000000-0x050001FF) should contain correct colors

**GBAtoPy code to check:**
```python
# In your PPU implementation, check:
print(f"Palette RAM at 0x05000000: {memory.read_u16(0x05000000):04X}")
print(f"Palette RAM at 0x05000002: {memory.read_u16(0x05000002):04X}")
```

#### 2. VRAM Tile Data Access

**Issue:** Tile data might not be loaded from correct VRAM address

**Check:**
- Verify character base block calculation: `0x06000000 + (char_base * 0x4000)`
- Check that tile data is being read from VRAM correctly
- Verify 4BPP decoding algorithm

**Expected:** Tile data at 0x06004000 should contain valid tile patterns

**GBAtoPy code to check:**
```python
# Check VRAM tile data
tile_addr = 0x06004000 + (tile_index * 32)
tile_data = []
for i in range(32):
    tile_data.append(memory.read_u8(tile_addr + i))
print(f"Tile {tile_index} data: {tile_data[:8]}")
```

#### 3. VRAM Map Data Access

**Issue:** Map data might not be read from correct VRAM address

**Check:**
- Verify screen base block calculation: `0x06000000 + (screen_base * 0x800)`
- Check map data format (2 bytes per tile)
- Verify tile index and palette bank extraction

**Expected:** Map data at 0x06000800 should contain valid tile indices

**GBAtoPy code to check:**
```python
# Check VRAM map data
map_addr = 0x06000800 + (tile_y * 64 + tile_x) * 2  # 64 = 32 tiles * 2 bytes
map_entry = memory.read_u16(map_addr)
tile_index = map_entry & 0x3FF
palette_bank = (map_entry >> 10) & 0x03
print(f"Map entry at {map_addr:08X}: tile={tile_index}, palette={palette_bank}")
```

#### 4. RGB555 to RGB888 Conversion


**Issue:** Color conversion might be wrong

**Check:**
- Verify conversion formula: `(value * 255) // 31`
- Check that 5-bit values are extracted correctly from 16-bit words
- Verify no clamping issues

**Expected:** RGB555 0x7C1F (blue) should convert to RGB888 (0,0,255)

**GBAtoPy code to check:**
```python
# Test conversion
def test_conversion():
    color555 = 0x7C1F  # Blue
    r5 = (color555 >> 0) & 0x1F
    g5 = (color555 >> 5) & 0x1F
    b5 = (color555 >> 10) & 0x1F
    r8 = (r5 * 255) // 31
    g8 = (g5 * 255) // 31
    b8 = (b5 * 255) // 31
    print(f"RGB555 {color555:04X} -> RGB888 ({r8},{g8},{b8})")
    assert r8 == 0 and g8 == 0 and b8 == 255, "Blue conversion failed!"
```

#### 5. Background Enable Bits

**Issue:** BG0 might not be enabled in DISPCNT

**Check:**
- Verify DISPCNT Bit 8 is set (BG0 enable)
- Check BG0CNT priority is valid (0-3)
- Verify no forced blank (DISPCNT Bit 7 should be 0)

**Expected:** DISPCNT should have Bit 8 = 1, Bit 7 = 0

**GBAtoPy code to check:**
```python
# Check DISPCNT
dispcnt = memory.read_u16(0x04000000)
print(f"DISPCNT = {dispcnt:04X}")
print(f"  BG0 enabled: {bool(dispcnt & 0x100)}")
print(f"  Forced blank: {bool(dispcnt & 0x80)}")
print(f"  BG Mode: {dispcnt & 0x07}")
```

### Medium Priority Issues

#### 6. Tile Decoding Algorithm

**Issue:** 4BPP decoding might be incorrect


**Check:**
- Verify pixel extraction from bytes (lower 4 bits first, then upper 4 bits)
- Check palette bank offset application
- Verify tile coordinate calculation

**Expected:** Each byte should produce 2 pixels (pixel0 = bits 0-3, pixel1 = bits 4-7)

#### 7. Scrolling Implementation

**Issue:** BG scrolling might not be applied correctly

**Check:**
- Verify BGxHOFS/BGxVOFS registers are read correctly
- Check that offsets are applied to tile coordinates
- Verify screen wrapping behavior

**Expected:** Scrolling should shift the visible portion of the background

#### 8. Priority Blending

**Issue:** OBJ/BG priority might not be respected

**Check:**
- Verify priority comparison logic
- Check that higher priority layers overwrite lower priority ones
- Verify OBJ priority (0-127)

**Expected:** BG0 (priority 0) should overwrite BG1 (priority 1)

### Low Priority Issues

#### 9. Mosaic Implementation

**Issue:** Mosaic might not be implemented or might be wrong
**Check:**
- Verify BGxCNT Bit 6 is checked
- Check mosaic size registers (MOSAIC register)
- Verify pixel replication logic

**Expected:** Mosaic should replicate pixels in blocks

#### 10. Window/Blend Features

**Issue:** Window layers or special effects might interfere
**Check:**
- Verify WININ/WINOUT registers
- Check BLDCNT/BLDALPHA/BLDY registers
- Verify special effects are disabled if not needed

**Expected:** If not using windows/blend, these should not affect rendering

---

## Quick Diagnostic Checklist

### For stripes.gba Color Issue

1. **Check palette RAM** - Are colors correct in 0x05000000-0x050001FF?
2. **Check tile data** - Is data loaded at 0x06004000?
3. **Check map data** - Are tile indices correct at 0x06000800?
4. **Check DISPCNT** - Is BG0 enabled (Bit 8 = 1)?
5. **Check BG0CNT** - Is priority 0 and 4BPP mode (Bit 7 = 0)?
6. **Check conversion** - Is RGB555 to RGB888 working?
7. **Check scrolling** - Are BGxHOFS/BGxVOFS applied?


### Test Values

```
# Expected for correct rendering:
DISPCNT = 0x0100  # BG0 enabled, Mode 0
BG0CNT = 0x104     # Priority 0, 4BPP, char base 1, screen base 1
Palette[0] = 0x7C1F  # Blue color
Tile[0] = [0x11, 0x22, ...]  # Valid tile data
Map[0] = 0x0001    # Tile index 1, palette bank 0
```

---

## References

- [gbatek - GBA LCD Video Controller](https://github.com/mgba-emu/gbatek/blob/gh-pages/gba.md#gba-lcd-video-controller)
- [GBA Memory Map](https://github.com/mgba-emu/gbatek/blob/gh-pages/gba.md#gbamemorymap)
- [GBA I/O Map](https://github.com/mgba-emu/gbatek/blob/gh-pages/gba.md#gbaiomap)

---

## Version History

- **v1.0** (2026-06-25): Initial extraction from gbatek documentation
- **Purpose**: Fix stripes.gba rendering issue (brown → blue-grey colors)

---

**Document created for GBAtoPy project**
**Author**: GBA hardware documentation specialist
**Status**: Complete - Ready for implementation review