"""GBA PPU (Pixel Processing Unit) - Graphics rendering"""

import struct
import os
from typing import Optional, List, Tuple

# Numba JIT compilation support
try:
    import numba
    from numba import njit, prange
    _HAS_NUMBA = True
except ImportError:
    numba = None
    njit = None
    prange = None
    _HAS_NUMBA = False

_NUMBA_ENABLED = False
_NUMBA_PPU_ENABLED = True  # Separate flag for PPU JIT


def _try_enable_numba_jit() -> bool:
    """Attempt to enable Numba JIT for PPU functions.

    Returns the enabled state. Falls back gracefully if numba is not installed."""
    global _NUMBA_PPU_ENABLED, _HAS_NUMBA
    try:
        import numba  # noqa: F401
        if numba is not None:
            _HAS_NUMBA = True
            _NUMBA_PPU_ENABLED = True
            return True
    except ImportError:
        pass

    _HAS_NUMBA = False
    _NUMBA_PPU_ENABLED = False
    print("  Warning: numba not installed, PPU JIT disabled")
    return False


def jit_compile(func):
    """Decorator to JIT-compile a function with numba when available."""
    if not _HAS_NUMBA or not _NUMBA_ENABLED:
        return func
    try:
        return njit(func)
    except Exception as e:
        print(f"  Warning: JIT compilation failed for {func.__name__}: {e}")
        return func


def jit_compile_ppu(func):
    """Decorator to JIT-compile PPU functions with numba when enabled."""
    if not _HAS_NUMBA or not _NUMBA_PPU_ENABLED:
        return func
    try:
        return njit(func, parallel=True)
    except Exception as e:
        print(f"  Warning: PPU JIT compilation failed for {func.__name__}: {e}")
        return func


def set_numba_enabled(enabled: bool):
    """Enable or disable all numba JIT compilation."""
    global _NUMBA_ENABLED
    if not _HAS_NUMBA and enabled:
        print("  Warning: numba not installed, JIT compilation unavailable")
    _NUMBA_ENABLED = enabled and _HAS_NUMBA


def set_numba_ppu_enabled(enabled: bool):
    """Enable or disable PPU-specific numba JIT compilation."""
    global _NUMBA_PPU_ENABLED
    if not _HAS_NUMBA and enabled:
        print("  Warning: numba not installed, PPU JIT compilation unavailable")
    _NUMBA_PPU_ENABLED = enabled and _HAS_NUMBA


def is_numba_available() -> bool:
    """Check if numba is available."""
    return _HAS_NUMBA


def is_numba_ppu_enabled() -> bool:
    """Check if PPU JIT is enabled."""
    return _NUMBA_PPU_ENABLED and _HAS_NUMBA


@jit_compile
def _c5to8_jit(c):
    if not isinstance(c, int):
        c = int(c)
    val = c & 0x1F
    return ((val << 3) | (val >> 2)) & 0xFF


@jit_compile
def _read_color_jit(vram_data, addr):
    if addr >= 0 and addr + 1 < len(vram_data):
        return int(vram_data[addr] | (vram_data[addr + 1] << 8))
    return 0


@jit_compile
def _read_palette_jit(palette_data, addr):
    if addr >= 0 and addr + 1 < len(palette_data):
        return int(palette_data[addr] | (palette_data[addr + 1] << 8))
    return 0


@jit_compile
def _convert_color_jit(color_val):
    r = int((color_val >> 0) & 0x1F)
    g = int((color_val >> 5) & 0x1F)
    b = int((color_val >> 10) & 0x1F)
    r8 = int((r << 3) | (r >> 2))
    g8 = int((g << 3) | (g >> 2))
    b8 = int((b << 3) | (b >> 2))
    return int(0xFF000000 | (b8 << 16) | (g8 << 8) | r8)


@jit_compile
def _decode_tile_4bpp_jit(vram_data, tile_offset):
    result = [0] * 64
    for row in range(8):
        for col in range(8):
            byte_offset = row * 4 + (col // 2)
            addr = tile_offset + byte_offset
            if addr >= 0 and addr < len(vram_data):
                byte_val = vram_data[addr]
                if col % 2 == 0:
                    color_idx = int(byte_val & 0x0F)
                else:
                    color_idx = int((byte_val >> 4) & 0x0F)
                result[row * 8 + col] = color_idx
            else:
                result[row * 8 + col] = 0
    return result


@jit_compile
def _decode_tile_8bpp_jit(vram_data, tile_offset):
    result = [0] * 64
    for row in range(8):
        for col in range(8):
            addr = tile_offset + (row * 8) + col
            if addr >= 0 and addr < len(vram_data):
                result[row * 8 + col] = int(vram_data[addr])
            else:
                result[row * 8 + col] = 0
    return result


# ========================================================================
# Numba JIT-compiled rendering helpers (cache=True for performance)
# ========================================================================

@jit_compile
def _get_palette_color_jit(palette_data, palette_idx):
    addr = palette_idx * 2
    if addr + 1 >= len(palette_data):
        return (0, 0, 0)

    color_val = palette_data[addr] | (palette_data[addr + 1] << 8)

    r = int((color_val >> 0) & 0x1F)
    g = int((color_val >> 5) & 0x1F)
    b = int((color_val >> 10) & 0x1F)
    r8 = int((r << 3) | (r >> 2))
    g8 = int((g << 3) | (g >> 2))
    b8 = int((b << 3) | (b >> 2))
    return (r8, g8, b8)


@jit_compile
def _get_palette_color_256_jit(palette_data, color_idx):
    addr = color_idx * 2
    if addr + 1 >= len(palette_data):
        return (0, 0, 0)

    color_val = palette_data[addr] | (palette_data[addr + 1] << 8)

    r = int((color_val >> 0) & 0x1F)
    g = int((color_val >> 5) & 0x1F)
    b = int((color_val >> 10) & 0x1F)
    r8 = int((r << 3) | (r >> 2))
    g8 = int((g << 3) | (g >> 2))
    b8 = int((b << 3) | (b >> 2))
    return (r8, g8, b8)


def _get_vram_bytes(memory, start: int, size: int) -> bytes:
    """Extract VRAM bytes for JIT functions."""
    data = bytearray(size)
    for i in range(size):
        try:
            data[i] = memory.read_u8(start + i)
        except:
            data[i] = 0
    return bytes(data)


def _get_palette_bytes(memory, start: int = 0x05000000, size: int = 512) -> bytes:
    """Extract palette RAM bytes for JIT functions."""
    data = bytearray(size)
    for i in range(size):
        try:
            data[i] = memory.read_u8(start + i)
        except:
            data[i] = 0
    return bytes(data)


def compute_flags(result: int, width: int) -> int:
    """Compute ARM7TDMI CPSR flags from arithmetic result.
    
    Args:
        result: 32-bit arithmetic result
        width: Bit width (32 for ARM, 16 for Thumb)
    
    Returns:
        CPSR flags: N (bit 31), Z (bit 30), C (bit 29), V (bit 28)
    """
    # N (Negative): bit 31
    n = 1 if result < 0 else 0
    
    # Z (Zero): bit 30
    z = 1 if result == 0 else 0
    
    # C (Carry): bit 29
    # For add/sub, C=1 if result < operand (unsigned overflow)
    c = 0
    
    # V (Overflow): bit 28 - for signed overflow
    # This is complex to compute generically, default to 0
    v = 0
    
    return (n << 31) | (z << 30) | (c << 29) | (v << 28)


def _c5to8(c: int) -> int:
    """Convert 5-bit GBA color to 8-bit. Formula: (c << 3) | (c >> 2)"""
    return (c << 3) | (c >> 2)


class PPU:
    """Game Boy Advance Pixel Processing Unit"""


# ========================================================================
    # OAM (Object Attribute Memory) - Sprite rendering
    # ========================================================================
# OAM at 0x07000000-0x070003FF (1KB, 128 sprites × 8 bytes)
    #
    # Each sprite has 3 attributes (8 bytes total per sprite):
    #   Attribute 0 (offset 0): Y position (bits 0-7), various flags
    #   Attribute 1 (offset 2): X position (bits 8-0 of word), size, affine
    #   Attribute 2 (offset 4): Tile number (bits 0-9), priority, palette
    #
    # GBATEK Reference:
    #   Attr0 bits: 0-7=Y, 8-9=mode, 10=mosaic, 11=color mode(0=4bpp,1=8bpp), 12-13=shape
    #   Attr1 bits: 0-8=X, 9=affine/flip, 10=double-size, 11=rotate/scale, 12=color mode, 13=mosaic, 14-15=size
    #   Attr2 bits: 0-9=tile#, 10-11=priority, 12-15=palette (4bpp only)
    # ========================================================================

    # Sprite size lookup table: [shape][size] = (width, height)
    SPRITE_SIZES = {
        # Square shapes (shape 0)
        0: {0: (8, 8), 1: (16, 16), 2: (32, 32), 3: (64, 64)},
        # Rectangular shapes (shape 1: 8x16, 16x8, etc)
        1: {0: (8, 16), 1: (16, 8), 2: (32, 16), 3: (16, 32)},
        # Rectangular shapes (shape 2)
        2: {0: (8, 32), 1: (16, 16), 2: (32, 8), 3: (8, 8)},
        # Reserved shape 3 - treat as 8x8
        3: {0: (8, 8), 1: (8, 8), 2: (8, 8), 3: (8, 8)},
    }

    # OAM affine matrix parameter addresses (32 bytes per matrix)
    # Matrix 0: 0x07000000 + 0x20 = 0x07000020
    # Matrix 1: 0x07000000 + 0x28 = 0x07000028
    # etc. Each matrix is 32 bytes (8 u16 values)
    OAM_AFFINE_BASE = 0x07000000
    OAM_AFFINE_STRIDE = 32  # 32 bytes between matrices

    def parse_oam(self):
        """Parse OAM to build sprite display list.
        
        Reads all 128 sprite entries from OAM at 0x07000000-0x070003FF.
        Filters out sprites with Y=224+ (off-screen vertically).
        Returns list of sprite dictionaries with parsed attributes.
        """
        self.sprite_list = []
        
        for i in range(128):
            oam_addr = 0x07000000 + (i * 8)
            attr0 = self.memory.read_u16(oam_addr)
            attr1 = self.memory.read_u16(oam_addr + 2)
            attr2 = self.memory.read_u16(oam_addr + 4)
            
            # Extract Attribute 0 fields (GBATEK reference)
            y = attr0 & 0xFF  # Y position (0-255, 224+ = offscreen)
            mode = (attr0 >> 8) & 0x3  # 0=normal, 1=affine, 2=hidden, 3=affine+alt
            mosaic = (attr0 >> 10) & 0x1
            color_mode = (attr0 >> 11) & 0x1  # 0=4BPP, 1=8BPP
            shape = (attr0 >> 12) & 0x3  # 0=square, 1=wide, 2=tall, 3=reserved
            
            # Extract Attribute 1 fields
            x = (attr1 >> 8) & 0x1FF  # X position (0-511, wraps at 256 for display)
            flip_h = (attr1 >> 9) & 0x1  # Horizontal flip (when not affine)
            flip_v = (attr1 >> 10) & 0x1  # Vertical flip (when not affine)
            double_size = (attr1 >> 10) & 0x1  # Double size (when affine)
            rotate_scale = (attr1 >> 11) & 0x1  # Enable rotation/scaling
            size = (attr1 >> 14) & 0x3  # Size index
            
            # Extract Attribute 2 fields
            tile_num = attr2 & 0x3FF  # Tile number (0-1023)
            priority = (attr2 >> 10) & 0x3  # Priority (0-3, 0=highest)
            palette_num = (attr2 >> 12) & 0xF  # Palette number (0-15, 4BPP only)
            
            # Filter: Y >= 224 means sprite is off-screen vertically
            # X is 9-bit (0-511) but displayable range is 0-239
            if y >= 224:
                continue
            
            # Get sprite dimensions based on shape and size
            if shape in self.SPRITE_SIZES and size in self.SPRITE_SIZES[shape]:
                width, height = self.SPRITE_SIZES[shape][size]
            else:
                width, height = 8, 8  # Default fallback
            
            # Calculate affine matrix index (0-31, 4 groups of 8)
            matrix_idx = (i // 4) % 32
            
            self.sprite_list.append({
                "y": y,
                "x": x,
                "width": width,
                "height": height,
                "attr0": attr0,
                "attr1": attr1,
                "attr2": attr2,
                "mode": mode,
                "shape": shape,
                "size": size,
                "color_mode": color_mode,
                "rotate_scale": rotate_scale,
                "double_size": double_size,
                "flip_h": flip_h,
                "flip_v": flip_v,
                "tile_num": tile_num,
                "priority": priority,
                "palette_num": palette_num,
                "matrix_idx": matrix_idx,
            })

    def _render_sprites(self):
        """Render all sprites from OAM after background layers.
        
        Called from render_frame() after backgrounds are rendered.
        Handles:
        - 4BPP color mode (index 0 = transparent)
        - Sprite priority (higher priority sprites draw on top)
        - Basic rotation/scaling if affine mode enabled
        
        Note: 8BPP sprites use 256-color palette at 0x05000200 with direct color index lookup.
        """
        # Parse OAM to build sprite list
        self.parse_oam()
        
        # Sort sprites by priority (0=highest, 3=lowest)
        # Lower priority value = draw on top of higher priority
        self.sprite_list.sort(key=lambda s: s["priority"])
        
        for sprite in self.sprite_list:
            self._render_single_sprite(sprite)

    def _render_single_sprite(self, sprite: dict):
        """Render a single sprite to the framebuffer.
        
        Args:
            sprite: Sprite dictionary from parse_oam()
        """
        # Skip hidden sprites (mode 2)
        if sprite["mode"] == 2:
            return
        
        y = sprite["y"]
        x = sprite["x"]
        width = sprite["width"]
        height = sprite["height"]
        tile_num = sprite["tile_num"]
        palette_num = sprite["palette_num"]
        color_mode = sprite["color_mode"]

        # Apply rotation/scaling if enabled
        if sprite["rotate_scale"]:
            self._render_affine_sprite(sprite)
            return
        
        # Render normal (non-rotated) sprite
        # Calculate base tile address in VRAM
        # 4BPP tiles: 32 bytes each (8x8 pixels × 4 bits)
        # 8BPP tiles: 64 bytes each (8x8 pixels × 8 bits)
        vram_base = 0x06000000
        tile_size = 32 if color_mode == 0 else 64
        
        # VRAM tile addressing - DISPCNT bit 6 controls OBJ character VRAM mapping
        #   1D mapping (bit 6 == 1): stride 32, no VRAM offset
        #   2D mapping (bit 6 == 0): stride 32, BG2 VRAM offset (4K = 128 tiles for 32B, 64 for 64B)
        tiles_per_row = 32
        vram_offset = 0
        if not self.obj_character_vram_mapping:
            # 2D mode: OBJ characters use BG2 character VRAM region (4K offset)
            vram_offset = 128 if color_mode == 0 else 64
        
        for py in range(height):
            for px in range(width):
                # Calculate tile coordinates within sprite
                tile_x = px // 8
                tile_y = py // 8
                
                # Calculate local pixel within tile
                local_x = px % 8
                local_y = py % 8
                
                # Handle horizontal flip
                if sprite["flip_h"]:
                    local_x = 7 - local_x
                
                # Handle vertical flip
                if sprite["flip_v"]:
                    local_y = 7 - local_y
                
                # Calculate global tile number (with 2D mode offset if applicable)
                global_tile = tile_num + vram_offset + tile_y * tiles_per_row + tile_x
                
                # Calculate address in VRAM
                tile_addr = vram_base + global_tile * tile_size
                
                # Read pixel from tile
                if color_mode == 0:
                    # 4BPP: 2 pixels packed in 1 byte
                    byte_offset = local_y * 4 + (local_x // 2)
                    byte_val = self.memory.read_u8(tile_addr + byte_offset)
                    if local_x % 2 == 0:
                        color_idx = (byte_val >> 4) & 0x0F
                    else:
                        color_idx = byte_val & 0x0F
                else:
                    # 8BPP: 1 byte per pixel
                    byte_offset = local_y * 8 + local_x
                    color_idx = self.memory.read_u8(tile_addr + byte_offset)

                # Skip transparent pixels
                if color_idx == 0:
                    continue
                
                # Calculate screen position
                screen_x = x + px
                screen_y = y + py
                
                # Check bounds
                if not (0 <= screen_x < self.screen_width and 
                        0 <= screen_y < self.screen_height):
                    continue
                
                # Get color from sprite palette
                if color_mode == 0:
                    # 4BPP: 16-color sprite palette
                    sprite_palette_base = 0x05000200
                    palette_addr = sprite_palette_base + (sprite["palette_num"] * 32) + (color_idx * 2)
                else:
                    # 8BPP: 256-color sprite palette at 0x05000200
                    palette_addr = 0x05000200 + (color_idx * 2)
                
                try:
                    color_val = self.memory.read_u16(palette_addr)
                    r = _c5to8((color_val >> 0) & 0x1F)
                    g = _c5to8((color_val >> 5) & 0x1F)
                    b = _c5to8((color_val >> 10) & 0x1F)
                    
                    # Draw pixel directly to framebuffer
                    self.framebuffer[screen_y][screen_x] = (r, g, b)
                except Exception as e:
                    # Invalid palette entry - skip this pixel silently
                    # This can happen with corrupted VRAM or uninitialized palette data
                    continue

    def _render_affine_sprite(self, sprite: dict):
        """Render a sprite with rotation/scaling transformation.
        
        Reads affine transformation matrix from OAM and applies
        rotation and scaling to sprite pixels.
        
        Args:
            sprite: Sprite dictionary with rotate_scale=True
        """
        y = sprite["y"]
        x = sprite["x"]
        width = sprite["width"]
        height = sprite["height"]
        tile_num = sprite["tile_num"]
        matrix_idx = sprite["matrix_idx"]
        
        # Read affine matrix parameters from OAM
        # Matrix format: PA, PB, PC, PD (4 × s16.8 = 8 bytes)
        # Followed by X, Y position (2 × s19.8 = 4 bytes) - not used for sprites
        matrix_base = self.OAM_AFFINE_BASE + 0x20 + (matrix_idx * self.OAM_AFFINE_STRIDE)
        
        try:
            pa = self._read_oam_fixed16_8(matrix_base + 0)
            pb = self._read_oam_fixed16_8(matrix_base + 2)
            pc = self._read_oam_fixed16_8(matrix_base + 4)
            pd = self._read_oam_fixed16_8(matrix_base + 6)
        except:
            # Default to identity if read fails
            pa, pb, pc, pd = 1.0, 0.0, 0.0, 1.0
        
        # Center of sprite for rotation
        cx = width / 2
        cy = height / 2
        
        # VRAM tile addressing - check DISPCNT bit 6 (obj_character_vram_mapping)
        vram_base = 0x06000000
        tile_size = 32
        tiles_per_row = 32
        vram_offset = 0
        if not self.obj_character_vram_mapping:
            vram_offset = 128
        
        # Render sprite with affine transformation
        for py in range(height):
            for px in range(width):
                # Calculate position relative to center
                rel_x = px - cx
                rel_y = py - cy
                
                # Apply inverse affine transformation
                src_x = pa * rel_x + pb * rel_y + cx
                src_y = pc * rel_x + pd * rel_y + cy
                
                # Check if source pixel is within sprite bounds
                if not (0 <= src_x < width and 0 <= src_y < height):
                    continue
                
                # Calculate source tile and pixel
                tile_x = int(src_x) // 8
                tile_y = int(src_y) // 8
                local_x = int(src_x) % 8
                local_y = int(src_y) % 8
                
                # Calculate global tile number (with 2D mode offset if applicable)
                global_tile = tile_num + vram_offset + tile_y * tiles_per_row + tile_x
                tile_addr = vram_base + global_tile * tile_size
                
                # Read pixel from tile
                byte_offset = local_y * 4 + (local_x // 2)
                byte_val = self.memory.read_u8(tile_addr + byte_offset)
                
                if local_x % 2 == 0:
                    color_idx = (byte_val >> 4) & 0x0F
                else:
                    color_idx = byte_val & 0x0F
                
                # Skip transparent
                if color_idx == 0:
                    continue
                
                # Calculate screen position
                screen_x = x + px
                screen_y = y + py
                
                if not (0 <= screen_x < self.screen_width and 
                        0 <= screen_y < self.screen_height):
                    continue
                
                # Get color from sprite palette
                sprite_palette_base = 0x05000200
                palette_addr = sprite_palette_base + (sprite["palette_num"] * 32) + (color_idx * 2)
                
                try:
                    color_val = self.memory.read_u16(palette_addr)
                    r = _c5to8((color_val >> 0) & 0x1F)
                    g = _c5to8((color_val >> 5) & 0x1F)
                    b = _c5to8((color_val >> 10) & 0x1F)
                    self.framebuffer[screen_y][screen_x] = (r, g, b)
                except Exception as e:
                    # Error reading palette - skip this pixel
                    continue

    def _read_oam_fixed16_8(self, addr: int) -> float:
        """Read a s1.7.8 fixed-point value from OAM.
        
        Args:
            addr: Memory address to read from
            
        Returns:
            Float value representing the fixed-point number
        """
        value = self.memory.read_u16(addr)
        # Convert from s1.7.8 to float
        if value & 0x8000:
            value = value - 0x10000
        return value / 256.0
    # MMIO Register addresses
    REG_DISPCNT = 0x04000000
    REG_GREENSWP = 0x04000002
    REG_DISPSTAT = 0x04000004
    REG_VCOUNT = 0x04000006

    # BG Control registers
    REG_BG0CNT = 0x04000008
    REG_BG1CNT = 0x0400000A
    REG_BG2CNT = 0x0400000C
    REG_BG3CNT = 0x0400000E

    # BG Scroll registers
    REG_BG0HOFS = 0x04000010
    REG_BG0VOFS = 0x04000012
    REG_BG1HOFS = 0x04000014
    REG_BG1VOFS = 0x04000016
    REG_BG2HOFS = 0x04000018
    REG_BG2VOFS = 0x0400001A
    REG_BG3HOFS = 0x0400001C
    REG_BG3VOFS = 0x0400001E

    # BG2 Affine parameters
    REG_BG2PA = 0x04000020  # 16.16 fixed point
    REG_BG2PB = 0x04000022
    REG_BG2PC = 0x04000024
    REG_BG2PD = 0x04000026
    REG_BG2X = 0x04000028  # 8.8 fixed point
    REG_BG2Y = 0x0400002C

    # BG3 Affine parameters
    REG_BG3PA = 0x04000030  # 16.16 fixed point
    REG_BG3PB = 0x04000032
    REG_BG3PC = 0x04000034
    REG_BG3PD = 0x04000036
    REG_BG3X = 0x04000038  # 8.8 fixed point
    REG_BG3Y = 0x0400003C

    # Window registers
    REG_WIN0H = 0x04000040
    REG_WIN1H = 0x04000042
    REG_WIN0V = 0x04000044
    REG_WIN1V = 0x04000046
    REG_WININ = 0x04000048
    REG_WINOUT = 0x0400004A
    REG_WINOBJ = 0x0400004C

    # Mosaic register
    REG_MOSAIC = 0x0400004E  # Actually at 0x0400004E or 0x040000F4

    # Blending registers
    REG_BLDCNT = 0x04000050
    REG_BLDALPHA = 0x04000052
    REG_BLDY = 0x04000054
    REG_BLDWIN = 0x04000056
    REG_BLDWIN = 0x04000056  # Window blend settings (bits 0-3=win0_alpha, 4-7=win0_y, 8-11=win1_alpha, 12-15=win1_y)

    # Sprite/OBJ registers
    REG_DISPSTAT2 = 0x04000056

    # Additional MMIO for mosaic (correct address)
    REG_MOSAIC_EXT = 0x040000F4

    def __init__(self, memory):
        self.memory = memory

        # Asset storage (for runtime tilemap/palette/sprite data)
        self.palette_bg = []
        self.tiles_4bpp = []
        self.bg0_tilemap = [0] * 1024
        self.bg1_tilemap = [0] * 1024
        self.bg2_tilemap = [0] * 1024
        self.bg3_tilemap = [0] * 1024
        self.sprite_list = []

        # Display control - use sensible defaults (mode 3, all BGs)
        # But read actual DISPCNT from memory if available
        self.mode = 3
        self.display_frame_select = 0
        self.hblank_interval_free = False
        self.obj_character_vram_mapping = False
        self.forced_blank = False
        self.bg0_enable = True
        self.bg1_enable = True
        self.bg2_enable = True
        self.bg3_enable = True
        self.obj_enable = True
        self.win0_enable = False
        
        # Read DISPCNT from memory to get actual mode
        if self.memory:
            dispcnt = self.memory.read_u16(self.REG_DISPCNT)
            mode = dispcnt & 0x7
            if mode <= 5:
                self.mode = mode
            self.bg0_enable = bool(dispcnt & 0x0100)
            self.bg1_enable = bool(dispcnt & 0x0200)
            self.bg2_enable = bool(dispcnt & 0x0400)
            self.bg3_enable = bool(dispcnt & 0x0800)
            self.obj_enable = bool(dispcnt & 0x1000)
        self.win1_enable = False
        self.obj_window_enable = False
        self.dispcnt = 0x0403
        self._obj_window_rects = []
        
        # Numba JIT control for PPU
        self.numba_ppu_enabled = is_numba_ppu_enabled()
        
        # Cache for VRAM/palette data (updated each frame for JIT)
        self._vram_cache = None
        self._palette_cache = None
        
        # Screen dimensions
        self.screen_width = 240
        self.screen_height = 160

        # Per-scanline BG2 affine snapshots for HBlank-DMA support.
        # Fixed-size array indexed by vcount (0..159) so that step_scanline() being
        # called from both the main loop and the fallback interpreter is idempotent:
        # the same vcount overwrites the same slot instead of appending duplicates.
        self._bg2_affine_snapshots = [None] * self.screen_height

        # BG configurations (per layer)
        self.bg_priority = [0] * 4
        self.bg_char_block = [0] * 4
        self.bg_mosaic = [False] * 4
        self.bg256 = [False] * 4
        self.bg_screen_block = [0] * 4
        self.bg_affine = [False] * 4
        self.bg_size = [0] * 4  # 0=256x256, 1=512x256, 2=256x512, 3=512x512
        
        # Read BGxCNT registers to get BG configuration (after initializing lists)
        if self.memory:
            for bg in range(4):
                bg_cnt_addr = 0x04000008 + bg * 2  # BG0CNT=0x04000008, BG1CNT=0x0400000A, etc.
                bg_cnt = self.memory.read_u16(bg_cnt_addr)
                self.bg_priority[bg] = bg_cnt & 0x03
                self.bg_char_block[bg] = (bg_cnt >> 2) & 0x03
                self.bg_mosaic[bg] = bool(bg_cnt & 0x0040)
                self.bg256[bg] = bool(bg_cnt & 0x0080)  # 8BPP if set
                self.bg_screen_block[bg] = (bg_cnt >> 8) & 0x1F
                self.bg_affine[bg] = bool(bg_cnt & 0x0100)  # Affine if bit 8 is set (for BG2/BG3)
                self.bg_size[bg] = (bg_cnt >> 14) & 0x03

        # BG scroll offsets
        self.bg_hofs = [0] * 4
        self.bg_vofs = [0] * 4

        # BG2 affine transformation parameters (read from MMIO)
        self.bg2_pa = 256  # 1.0 in 16.16 fixed point
        self.bg2_pb = 0
        self.bg2_pc = 0
        self.bg2_pd = 256  # 1.0 in 16.16 fixed point
        self.bg2_x = 0
        self.bg2_y = 0

        # BG3 affine transformation parameters (read from MMIO)
        self.bg3_pa = 256  # 1.0 in 16.16 fixed point
        self.bg3_pb = 0
        self.bg3_pc = 0
        self.bg3_pd = 256  # 1.0 in 16.16 fixed point
        self.bg3_x = 0
        self.bg3_y = 0

        # Blending configuration
        self.bldcnt = 0
        self.bldalpha_eva = 0
        self.bldalpha_evb = 0
        self.bldy = 0
        # Window blend configuration (from BLDWIN)
        self.bldwin_alpha_win0 = 0
        self.bldwin_y_win0 = 0
        self.bldwin_alpha_win1 = 0
        self.bldwin_y_win1 = 0

        # Window configuration
        self.win0_left = 0
        self.win0_right = 240
        self.win0_top = 0
        self.win0_bottom = 160
        self.win1_left = 0
        self.win1_right = 240
        self.win1_top = 0
        self.win1_bottom = 160

        # Window control bits (which layers enabled in each window)
        self.win0_in_enable = 0  # Bits: 0-3 = BG0-3, 4 = OBJ, 5 = Blend
        self.win0_out_enable = 0
        self.win1_in_enable = 0
        self.win1_out_enable = 0
        self.win_obj_enable = 0
        # WINOUT OBJ enable bit (OBJ displayed outside window area)
        self.winout_obj_enable = False

        # Mosaic configuration
        self.bg_mosaic_h = 1  # Horizontal size (1-16 pixels)
        self.bg_mosaic_v = 1  # Vertical size (1-16 pixels)
        self.obj_mosaic_h = 1
        self.obj_mosaic_v = 1
        self.mosaic_enabled = False

        # Display status
        self.vcount = 0
        self.vblank = False
        self.hblank = False
        self.vcount_trigger = False
        self.lyc = 0  # LY Compare register (bits 8-15 of DISPSTAT)
        self.vblank_irq_enable = False
        self.hblank_irq_enable = False
        self.vcount_irq_enable = False

        # Framebuffer
        self.framebuffer: List[List[Tuple[int, int, int]]] = []
        self._init_framebuffer()

    def get_surface(self) -> "pygame.Surface":
        """Convert framebuffer to pygame Surface for screenshot.

        Uses surfarray.blit_array() for bulk pixel transfer (~100x faster than set_at)."""
        import pygame

        try:
            import numpy as np

            arr = np.array(self.framebuffer, dtype=np.uint8)
            # Transpose from (height, width, 3) to (width, height, 3) for blit_array
            arr = np.transpose(arr, (1, 0, 2))
            surf = pygame.Surface((self.screen_width, self.screen_height))
            pygame.surfarray.blit_array(surf, arr)
            return surf
        except ImportError:
            # Fallback: per-pixel set_at if numpy not available
            surf = pygame.Surface((self.screen_width, self.screen_height))
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    color = self.framebuffer[y][x]
                    surf.set_at((x, y), color)
            return surf
    def _init_framebuffer(self):
        """Initialize the framebuffer with the backdrop color (palette entry 0)."""
        backdrop = (0, 0, 0)
        try:
            color_val = self.memory.read_u16(0x05000000)
            r = (color_val >> 0) & 0x1F
            g = (color_val >> 5) & 0x1F
            b = (color_val >> 10) & 0x1F
            backdrop = (_c5to8(r), _c5to8(g), _c5to8(b))
        except Exception:
            pass
        self.framebuffer = [
            [backdrop for _ in range(self.screen_width)] for _ in range(self.screen_height)
        ]
        # Track which BG layer (0-3) or OBJ (4) or backdrop (5) each pixel belongs to
        self.layer_origin = [[5]*240 for _ in range(160)]
        # Second target framebuffer for blend operations
        self.second_target_framebuffer = [[None]*240 for _ in range(160)]

    def _get_vram_data(self) -> bytes:
        """Get VRAM data as bytes for JIT functions.

        Returns 128KB = 96KB VRAM + 16KB copy of start for double buffering.
        Mode 3/5 page 1 (0x0600A000 + 0x18000 max) reads contiguously at 0xA000-0x1BFFF.
        """
        vram_start = 0x06000000
        vram_size = 0x18000  # 96KB
        pad_size = 0x4000    # 16KB
        try:
            raw = bytearray(self.memory.read_range(vram_start, vram_size))
            raw.extend(raw[:pad_size])
            return bytes(raw)
        except:
            return b'\x00' * (vram_size + pad_size)

    def _get_palette_data(self) -> bytes:
        """Get palette RAM data as bytes for JIT functions."""
        palette_start = 0x05000000
        palette_end = 0x05000400
        try:
            return bytes(self.memory.read_range(palette_start, palette_end - palette_start))
        except:
            return b'\x00' * (palette_end - palette_start)

    def _decode_tile_4bpp_jit_wrapper(self, tile_index: int, char_block_base: int) -> List[int]:
        """JIT-accelerated 4BPP tile decoding."""
        vram_data = self._get_vram_data()
        char_block = char_block_base * 0x4000
        tile_offset = tile_index * 32
        return _decode_tile_4bpp_jit(vram_data, char_block + tile_offset)

    def _decode_tile_8bpp_jit_wrapper(self, tile_index: int, char_block_base: int) -> List[int]:
        """JIT-accelerated 8BPP tile decoding."""
        vram_data = self._get_vram_data()
        char_block = char_block_base * 0x4000
        # Use modulo 256 to match mGBA behavior for out-of-range tile indices
        tile_offset = (tile_index % 256) * 64
        return _decode_tile_8bpp_jit(vram_data, char_block + tile_offset)

    def _get_palette_color_jit(self, palette_idx: int) -> Tuple[int, int, int]:
        """JIT-accelerated palette color lookup."""
        palette_data = self._get_palette_data()
        addr = palette_idx * 2
        color_val = _read_palette_jit(palette_data, addr)
        r = _c5to8_jit((color_val >> 0) & 0x1F)
        g = _c5to8_jit((color_val >> 5) & 0x1F)
        b = _c5to8_jit((color_val >> 10) & 0x1F)
        return (r, g, b)

    def _get_palette_color_256_jit(self, palette_idx: int) -> Tuple[int, int, int]:
        """JIT-accelerated 256-color palette lookup."""
        palette_data = self._get_palette_data()
        addr = palette_idx * 2
        color_val = _read_palette_jit(palette_data, addr)
        r = _c5to8_jit((color_val >> 0) & 0x1F)
        g = _c5to8_jit((color_val >> 5) & 0x1F)
        b = _c5to8_jit((color_val >> 10) & 0x1F)
        return (r, g, b)

    def write_register(self, addr: int, value: int):
        """Handle MMIO writes to PPU registers"""

        # Handle affine matrix registers for BG2
        if addr == self.REG_BG2PA:
            self.bg2_pa = value
        elif addr == self.REG_BG2PB:
            self.bg2_pb = value
        elif addr == self.REG_BG2PC:
            self.bg2_pc = value
        elif addr == self.REG_BG2PD:
            self.bg2_pd = value
        elif addr == self.REG_BG2X:
            self.bg2_x = (self.bg2_x & 0xFFFF0000) | (value & 0xFFFF)
        elif addr == self.REG_BG2X + 2:
            self.bg2_x = (self.bg2_x & 0x0000FFFF) | (value << 16)
            # Sign-extend from 28 bits
            self.bg2_x &= 0x0FFFFFFF
            if self.bg2_x & 0x08000000:
                self.bg2_x -= 0x10000000
        elif addr == self.REG_BG2Y:
            self.bg2_y = (self.bg2_y & 0xFFFF0000) | (value & 0xFFFF)
        elif addr == self.REG_BG2Y + 2:
            self.bg2_y = (self.bg2_y & 0x0000FFFF) | (value << 16)
            self.bg2_y &= 0x0FFFFFFF
            if self.bg2_y & 0x08000000:
                self.bg2_y -= 0x10000000

        # Handle affine matrix registers for BG3
        elif addr == self.REG_BG3PA:
            self.bg3_pa = value
        elif addr == self.REG_BG3PB:
            self.bg3_pb = value
        elif addr == self.REG_BG3PC:
            self.bg3_pc = value
        elif addr == self.REG_BG3PD:
            self.bg3_pd = value
        elif addr == self.REG_BG3X:
            self.bg3_x = (self.bg3_x & 0xFFFF0000) | (value & 0xFFFF)
        elif addr == self.REG_BG3X + 2:
            self.bg3_x = (self.bg3_x & 0x0000FFFF) | (value << 16)
            self.bg3_x &= 0x0FFFFFFF
            if self.bg3_x & 0x08000000:
                self.bg3_x -= 0x10000000
        elif addr == self.REG_BG3Y:
            self.bg3_y = (self.bg3_y & 0xFFFF0000) | (value & 0xFFFF)
        elif addr == self.REG_BG3Y + 2:
            self.bg3_y = (self.bg3_y & 0x0000FFFF) | (value << 16)
            self.bg3_y &= 0x0FFFFFFF
            if self.bg3_y & 0x08000000:
                self.bg3_y -= 0x10000000

        # Window registers
        elif addr == self.REG_WIN0H:
            # WIN0H: bits 0-7 = left, bits 8-15 = right
            self.win0_left = (value >> 0) & 0xFF
            self.win0_right = (value >> 8) & 0xFF
        elif addr == self.REG_WIN1H:
            self.win1_left = (value >> 0) & 0xFF
            self.win1_right = (value >> 8) & 0xFF
        elif addr == self.REG_WIN0V:
            self.win0_top = (value >> 0) & 0xFF
            self.win0_bottom = (value >> 8) & 0xFF
        elif addr == self.REG_WIN1V:
            self.win1_top = (value >> 0) & 0xFF
            self.win1_bottom = (value >> 8) & 0xFF
        elif addr == self.REG_WININ:
            # WININ: bits 0-5 = window 0 in, bits 8-13 = window 1 in
            self.win0_in_enable = value & 0x3F
            self.win1_in_enable = (value >> 8) & 0x3F
        elif addr == self.REG_WINOUT:
            # WINOUT: bits 0-3 = BG0-3 out, bit 4 = OBJ out, bit 5 = Blend out
            self.win0_out_enable = value & 0x1F
            self.win1_out_enable = (value >> 8) & 0x1F
            self.winout_obj_enable = bool((value >> 4) & 1)
        elif addr == self.REG_WINOBJ:
            # WINOBJ: bits 0-5 = OBJ window enable
            self.win_obj_enable = value & 0x3F

        # Mosaic register
        elif addr == self.REG_MOSAIC or addr == self.REG_MOSAIC_EXT:
            self.bg_mosaic_h = ((value >> 0) & 0xF) + 1
            self.bg_mosaic_v = ((value >> 4) & 0xF) + 1
            self.obj_mosaic_h = ((value >> 8) & 0xF) + 1
            self.obj_mosaic_v = ((value >> 12) & 0xF) + 1
            self.mosaic_enabled = value != 0

        elif addr == self.REG_BLDCNT:
            self.bldcnt = value & 0x3FFF
        elif addr == self.REG_BLDALPHA:
            self.bldalpha_eva = value & 0x1F
            self.bldalpha_evb = (value >> 8) & 0x1F
        elif addr == self.REG_BLDY:
            self.bldy = value & 0x1F

        # DISPCNT - Display Control
        elif addr == self.REG_DISPCNT:
            mode = value & 0x7
            if mode > 5:
                mode = 5  # Invalid mode, prefer Mode 5 (bitmapped) for visibility
            self.mode = mode
            self.display_frame_select = (value >> 4) & 1
            self.hblank_interval_free = bool((value >> 5) & 1)
            self.obj_character_vram_mapping = bool((value >> 6) & 1)
            self.forced_blank = bool((value >> 7) & 1)
            self.bg0_enable = bool((value >> 8) & 1)
            self.bg1_enable = bool((value >> 9) & 1)
            self.bg2_enable = bool((value >> 10) & 1)
            self.bg3_enable = bool((value >> 11) & 1)
            self.obj_enable = bool((value >> 12) & 1)
            self.win0_enable = bool((value >> 13) & 1)
            self.win1_enable = bool((value >> 14) & 1)
            self.obj_window_enable = bool((value >> 15) & 1)

        # DISPSTAT - Display Status (write LYC and IRQ enables)
        elif addr == self.REG_DISPSTAT:
            self.lyc = (value >> 8) & 0xFF
            self.vblank_irq_enable = bool((value >> 3) & 1)
            self.hblank_irq_enable = bool((value >> 4) & 1)
            self.vcount_irq_enable = bool((value >> 5) & 1)

        # BG Control registers
        elif addr == self.REG_BG0CNT:
            self._write_bg_control(0, value)
        elif addr == self.REG_BG1CNT:
            self._write_bg_control(1, value)
        elif addr == self.REG_BG2CNT:
            self._write_bg_control(2, value)
        elif addr == self.REG_BG3CNT:
            self._write_bg_control(3, value)

        # BG Scroll registers
        elif addr == self.REG_BG0HOFS:
            self.bg_hofs[0] = value & 0x1FF
        elif addr == self.REG_BG0VOFS:
            self.bg_vofs[0] = value & 0x1FF
        elif addr == self.REG_BG1HOFS:
            self.bg_hofs[1] = value & 0x1FF
        elif addr == self.REG_BG1VOFS:
            self.bg_vofs[1] = value & 0x1FF
        elif addr == self.REG_BG2HOFS:
            self.bg_hofs[2] = value & 0x1FF
        elif addr == self.REG_BG2VOFS:
            self.bg_vofs[2] = value & 0x1FF
        elif addr == self.REG_BG3HOFS:
            self.bg_hofs[3] = value & 0x1FF
        elif addr == self.REG_BG3VOFS:
            self.bg_vofs[3] = value & 0x1FF

    def _write_bg_control(self, bg_num: int, value: int):
        """Write to BG control register"""
        if bg_num < 0 or bg_num > 3:
            return
        self.bg_priority[bg_num] = value & 0x3
        self.bg_char_block[bg_num] = (value >> 2) & 0x3
        self.bg_mosaic[bg_num] = bool((value >> 6) & 1)
        self.bg256[bg_num] = bool((value >> 7) & 1)
        self.bg_screen_block[bg_num] = (value >> 8) & 0x1F
        self.bg_affine[bg_num] = bool((value >> 13) & 1)
        self.bg_size[bg_num] = (value >> 14) & 0x3

    def read_register(self, addr: int) -> int:
        """Handle MMIO reads from PPU registers - returns 16-bit values"""

        # Handle affine matrix registers for BG2 (read as signed 16-bit)
        if addr == self.REG_BG2PA:
            return self.bg2_pa & 0xFFFF
        elif addr == self.REG_BG2PB:
            return self.bg2_pb & 0xFFFF
        elif addr == self.REG_BG2PC:
            return self.bg2_pc & 0xFFFF
        elif addr == self.REG_BG2PD:
            return self.bg2_pd & 0xFFFF

        # Handle affine matrix registers for BG3 (read as signed 16-bit)
        elif addr == self.REG_BG3PA:
            return self.bg3_pa & 0xFFFF
        elif addr == self.REG_BG3PB:
            return self.bg3_pb & 0xFFFF
        elif addr == self.REG_BG3PC:
            return self.bg3_pc & 0xFFFF
        elif addr == self.REG_BG3PD:
            return self.bg3_pd & 0xFFFF

        # Window registers
        elif addr == self.REG_WIN0H:
            return self.win0_left | (self.win0_right << 8)
        elif addr == self.REG_WIN1H:
            return self.win1_left | (self.win1_right << 8)
        elif addr == self.REG_WIN0V:
            return self.win0_top | (self.win0_bottom << 8)
        elif addr == self.REG_WIN1V:
            return self.win1_top | (self.win1_bottom << 8)
        elif addr == self.REG_WININ:
            return self.win0_in_enable | (self.win1_in_enable << 8)
        elif addr == self.REG_WINOUT:
            return self.win0_out_enable | ((1 if self.winout_obj_enable else 0) << 4) | (self.win1_out_enable << 8)
        elif addr == self.REG_WINOBJ:
            return self.win_obj_enable

        # Mosaic register
        elif addr == self.REG_MOSAIC or addr == self.REG_MOSAIC_EXT:
            mosaic = 0
            mosaic |= ((self.bg_mosaic_h - 1) & 0xF) << 0
            mosaic |= ((self.bg_mosaic_v - 1) & 0xF) << 4
            mosaic |= ((self.obj_mosaic_h - 1) & 0xF) << 8
            mosaic |= ((self.obj_mosaic_v - 1) & 0xF) << 12
            return mosaic

        elif addr == self.REG_BLDCNT:
            return self.bldcnt
        elif addr == self.REG_BLDALPHA:
            return self.bldalpha_eva | (self.bldalpha_evb << 8)
        elif addr == self.REG_BLDY:
            return self.bldy

        # DISPCNT read
        elif addr == self.REG_DISPCNT:
            dispcnt = 0
            dispcnt |= self.mode & 0x7
            dispcnt |= (self.display_frame_select & 1) << 4
            dispcnt |= (self.hblank_interval_free & 1) << 5
            dispcnt |= (self.obj_character_vram_mapping & 1) << 6
            dispcnt |= (self.forced_blank & 1) << 7
            dispcnt |= (self.bg0_enable & 1) << 8
            dispcnt |= (self.bg1_enable & 1) << 9
            dispcnt |= (self.bg2_enable & 1) << 10
            dispcnt |= (self.bg3_enable & 1) << 11
            dispcnt |= (self.obj_enable & 1) << 12
            dispcnt |= (self.win0_enable & 1) << 13
            dispcnt |= (self.win1_enable & 1) << 14
            dispcnt |= (self.obj_window_enable & 1) << 15
            return dispcnt

        # VCOUNT read
        elif addr == self.REG_VCOUNT:
            return self.vcount

        # DISPSTAT read
        elif addr == self.REG_DISPSTAT:
            dispstat = 0
            dispstat |= (self.vblank & 1) << 0
            dispstat |= (self.hblank & 1) << 1
            dispstat |= (self.vcount_trigger & 1) << 2
            dispstat |= (self.vblank_irq_enable & 1) << 3
            dispstat |= (self.hblank_irq_enable & 1) << 4
            dispstat |= (self.vcount_irq_enable & 1) << 5
            dispstat |= (self.lyc & 0xFF) << 8
            return dispstat

        # BG Control registers read
        elif addr == self.REG_BG0CNT:
            return self._read_bg_control(0)
        elif addr == self.REG_BG1CNT:
            return self._read_bg_control(1)
        elif addr == self.REG_BG2CNT:
            return self._read_bg_control(2)
        elif addr == self.REG_BG3CNT:
            return self._read_bg_control(3)

        # BG Scroll read
        elif addr == self.REG_BG0HOFS:
            return self.bg_hofs[0]
        elif addr == self.REG_BG0VOFS:
            return self.bg_vofs[0]
        elif addr == self.REG_BG1HOFS:
            return self.bg_hofs[1]
        elif addr == self.REG_BG1VOFS:
            return self.bg_vofs[1]
        elif addr == self.REG_BG2HOFS:
            return self.bg_hofs[2]
        elif addr == self.REG_BG2VOFS:
            return self.bg_vofs[2]
        elif addr == self.REG_BG3HOFS:
            return self.bg_hofs[3]
        elif addr == self.REG_BG3VOFS:
            return self.bg_vofs[3]

        # BG2 affine X/Y read
        elif addr == self.REG_BG2X:
            return self.bg2_x & 0xFFFF
        elif addr == self.REG_BG2X + 2:
            return (self.bg2_x >> 16) & 0xFFFF
        elif addr == self.REG_BG2Y:
            return self.bg2_y & 0xFFFF
        elif addr == self.REG_BG2Y + 2:
            return (self.bg2_y >> 16) & 0xFFFF

        # BG3 affine X/Y read
        elif addr == self.REG_BG3X:
            return self.bg3_x & 0xFFFF
        elif addr == self.REG_BG3X + 2:
            return (self.bg3_x >> 16) & 0xFFFF
        elif addr == self.REG_BG3Y:
            return self.bg3_y & 0xFFFF
        elif addr == self.REG_BG3Y + 2:
            return (self.bg3_y >> 16) & 0xFFFF

        # Unmapped MMIO register — standard GBA behavior returns 0 for undefined addresses
        return 0

    def _read_bg_control(self, bg_num: int) -> int:
        """Read BG control register"""
        if bg_num < 0 or bg_num > 3:
            # Invalid BG number - return 0
            return 0
        value = 0
        value |= self.bg_priority[bg_num] & 0x3
        value |= (self.bg_char_block[bg_num] & 0x3) << 2
        value |= (self.bg_mosaic[bg_num] & 1) << 6
        value |= (self.bg256[bg_num] & 1) << 7
        value |= (self.bg_screen_block[bg_num] & 0x1F) << 8
        value |= (self.bg_affine[bg_num] & 1) << 13
        value |= (self.bg_size[bg_num] & 0x3) << 14
        return value

    def _decode_tile_4bpp(
    self,
    tile_index: int,
     char_block_base: int) -> List[int]:
        """Decode a 4bpp tile into 64 palette indices (8x8 pixels).

        Args:
            tile_index: Tile number (0-511 for 4bpp mode)
            char_block_base: Character Block Base Address (0-3)

        Returns:
            List of 64 palette indices (0-15) for each pixel in row-major order
        """
        # GBA VRAM structure for 4bpp tiles:
        # Each tile is 64 bytes (512 bits), storing 8x8 pixels with 4 bits per pixel
        # Each row of 8 pixels requires 4 bytes (32 bits)
        # Total: 8 rows * 4 bytes = 32 bytes per tile in standard mapping

        # VRAM address calculation
        vram_base = 0x06000000
        char_block = char_block_base * 0x4000  # Each block is 16KB
        # 32 bytes per 4bpp tile (lower resolution mapping)
        tile_offset = tile_index * 32

        addr = vram_base + char_block + tile_offset

        palette_indices = []

        for row in range(8):
            for col in range(8):
                byte_offset = row * 4 + (col // 2)
                byte_addr = addr + byte_offset

                try:
                    byte_val = self.memory.read_u8(byte_addr)

                    if col % 2 == 0:
                        color_idx = byte_val & 0x0F
                    else:
                        color_idx = (byte_val >> 4) & 0x0F

                    palette_indices.append(color_idx)
                except:
                    palette_indices.append(0)

        return palette_indices

    
    def _decode_tile_8bpp(
        self,
        tile_index: int,
        char_block_base: int) -> List[int]:
        """Decode an 8BPP tile into 64 palette indices (8x8 pixels).

        Args:
            tile_index: Tile number (0-255 for 8bpp mode)
            char_block_base: Character Block Base Address (0-1 for 8bpp)

        Returns:
            List of 64 palette indices (0-255) for each pixel in row-major order
        """
        # GBA VRAM structure for 8BPP tiles:
        # Each tile is 64 bytes, storing 8x8 pixels with 8 bits per pixel
        # Each row of 8 pixels requires 8 bytes (1 byte per pixel)
        # Total: 8 rows * 8 bytes = 64 bytes per tile

        # VRAM address calculation
        vram_base = 0x06000000
        char_block = char_block_base * 0x4000  # Each block is 16KB
        tile_offset = tile_index * 64  # 64 bytes per 8BPP tile

        addr = vram_base + char_block + tile_offset

        palette_indices = []

        for row in range(8):
            for col in range(8):
                byte_addr = addr + (row * 8) + col

                try:
                    color_idx = self.memory.read_u8(byte_addr)
                    palette_indices.append(color_idx)
                except:
                    palette_indices.append(0)

        return palette_indices

    def _get_palette_color(self, palette_idx: int) -> Tuple[int, int, int]:
        """Get RGB color from background palette.

        Args:
            palette_idx: Palette entry index (0-15 for BG palettes)

        Returns:
            Tuple of (R, G, B) values (0-255 each)
        """
        # GBA background palettes start at 0x05000000
        # Each palette entry is 2 bytes (15-bit RGB555)
        # Total: 256 entries = 512 bytes (16 palettes * 16 entries * 2 bytes)

        palette_addr = 0x05000000 + (palette_idx * 2)

        try:
            color_val = self.memory.read_u16(palette_addr)
            r = _c5to8((color_val >> 0) & 0x1F)
            g = _c5to8((color_val >> 5) & 0x1F)
            b = _c5to8((color_val >> 10) & 0x1F)
            return (r, g, b)
        except:
            return (0, 0, 0)

    def _apply_affine_transform(
        self, bg_num: int, x: int, y: int) -> Tuple[int, int]:
        """Apply affine transformation to coordinates using MMIO register values"""

        if bg_num == 2:
            pa = self._fixed_to_float(self.bg2_pa)
            pb = self._fixed_to_float(self.bg2_pb)
            pc = self._fixed_to_float(self.bg2_pc)
            pd = self._fixed_to_float(self.bg2_pd)
            offset_x = self._fixed_8_8_to_float(self.bg2_x)
            offset_y = self._fixed_8_8_to_float(self.bg2_y)
        elif bg_num == 3:
            pa = self._fixed_to_float(self.bg3_pa)
            pb = self._fixed_to_float(self.bg3_pb)
            pc = self._fixed_to_float(self.bg3_pc)
            pd = self._fixed_to_float(self.bg3_pd)
            offset_x = self._fixed_8_8_to_float(self.bg3_x)
            offset_y = self._fixed_8_8_to_float(self.bg3_y)
        else:
            return x, y

        # Apply transformation matrix
        new_x = pa * x + pb * y + offset_x
        new_y = pc * x + pd * y + offset_y

        return int(new_x), int(new_y)

    def _fixed_to_float(self, value: int) -> float:
        """Convert 16.16 fixed point to float"""
        # Handle signed value
        if value & 0x8000:
            value = value - 0x10000
        return value / 65536.0

    def _fixed_8_8_to_float(self, value: int) -> float:
        """Convert 8.8 fixed point to float"""
        if value & 0x800000:
            value = value - 0x1000000
        return value / 256.0

    def _s178_to_float(self, value: int) -> float:
        """Convert s1.7.8 fixed point to float (16-bit, 256 = 1.0)"""
        if value & 0x8000:
            value = value - 0x10000
        return value / 256.0

    def _is_in_window(self, x: int, y: int, win_num: int) -> bool:
        """Check if coordinate is inside specified window"""
        if win_num == 0:
            left, right = self.win0_left, self.win0_right
            top, bottom = self.win0_top, self.win0_bottom
        elif win_num == 1:
            left, right = self.win1_left, self.win1_right
            top, bottom = self.win1_top, self.win1_bottom
        else:
            return False

        # Handle edge cases
        if left <= right:
            in_h = left <= x <= right
        else:
            in_h = x >= left or x <= right

        if top <= bottom:
            in_v = top <= y <= bottom
        else:
            in_v = y >= top or y <= bottom

        return in_h and in_v

    def _is_in_obj_window(self, x: int, y: int) -> bool:
        for sx, sy, w, h in self._obj_window_rects:
            if sy <= y < sy + h and sx <= x < sx + w:
                return True
        return False

    def _get_window_layer_enable(self, x: int, y: int) -> int:
        """Get which layers are enabled at the given coordinate based on windows"""
        # Check WIN0 first
        if self.win0_enable and self._is_in_window(x, y, 0):
            return self.win0_in_enable

        # Check WIN1
        if self.win1_enable and self._is_in_window(x, y, 1):
            return self.win1_in_enable

        if self.obj_window_enable and self._obj_window_rects:
            if self._is_in_obj_window(x, y):
                return 0x10 if self.winout_obj_enable else 0
            else:
                return 0x10 if (self.win0_out_enable & 0x10) else 0

        # Default to out enables
        if self.win0_enable or self.win1_enable:
            return self.win0_out_enable

        return 0x3F  # All enabled by default (BG0-3 + OBJ + Blend)

    def _apply_mosaic(self, x: int, y: int,
                      is_obj: bool = False) -> Tuple[int, int]:
        """Apply mosaic effect to pixel coordinates"""
        if not self.mosaic_enabled:
            return x, y

        if is_obj:
            h_size = self.obj_mosaic_h
            v_size = self.obj_mosaic_v
        else:
            h_size = self.bg_mosaic_h
            v_size = self.bg_mosaic_v

        # Snap coordinates to block boundaries
        mosaic_x = (x // h_size) * h_size
        mosaic_y = (y // v_size) * v_size

        return mosaic_x, mosaic_y

    def _read_registers(self):
        """Read PPU state from MMIO registers before rendering.
        
        This is necessary because the PPU may be created before the ROM
        initializes DISPCNT/BGxCNT, and Memory writes do not notify the PPU.
        """
        if not self.memory:
            return
            
        # DISPCNT
        dispcnt = self.memory.read_u16(self.REG_DISPCNT)
        mode = dispcnt & 0x7
        if mode > 5:
            mode = 5
        self.mode = mode
        self.display_frame_select = (dispcnt >> 4) & 1
        self.hblank_interval_free = bool((dispcnt >> 5) & 1)
        self.obj_character_vram_mapping = bool((dispcnt >> 6) & 1)
        self.forced_blank = bool((dispcnt >> 7) & 1)
        self.bg0_enable = bool((dispcnt >> 8) & 1)
        self.bg1_enable = bool((dispcnt >> 9) & 1)
        self.bg2_enable = bool((dispcnt >> 10) & 1)
        self.bg3_enable = bool((dispcnt >> 11) & 1)
        self.obj_enable = bool((dispcnt >> 12) & 1)
        self.win0_enable = bool((dispcnt >> 13) & 1)
        self.win1_enable = bool((dispcnt >> 14) & 1)
        self.obj_window_enable = bool((dispcnt >> 15) & 1)
        
        # DISPSTAT
        dispstat = self.memory.read_u16(self.REG_DISPSTAT)
        self.lyc = (dispstat >> 8) & 0xFF
        self.vblank_irq_enable = bool((dispstat >> 3) & 1)
        self.hblank_irq_enable = bool((dispstat >> 4) & 1)
        self.vcount_irq_enable = bool((dispstat >> 5) & 1)
        
        # BG Control and scroll registers
        for bg in range(4):
            bg_cnt = self.memory.read_u16(self.REG_BG0CNT + bg * 2)
            self._write_bg_control(bg, bg_cnt)
            self.bg_hofs[bg] = self.memory.read_u16(self.REG_BG0HOFS + bg * 4) & 0x1FF
            self.bg_vofs[bg] = self.memory.read_u16(self.REG_BG0VOFS + bg * 4) & 0x1FF

        # Pre-scan OAM for OBJ window sprites (obj_mode == 3) once per frame
        self._obj_window_rects = []
        if self.obj_window_enable:
            OAM_BASE = 0x07000000
            for sprite_idx in range(128):
                sprite_addr = OAM_BASE + (sprite_idx * 8)
                try:
                    attr0 = self.memory.read_u16(sprite_addr)
                    attr1 = self.memory.read_u16(sprite_addr + 2)
                except Exception:
                    continue
                if ((attr0 >> 10) & 3) != 3:
                    continue
                sy = attr0 & 0xFF
                sx = attr1 & 0x1FF
                h = ((attr0 >> 12) & 7) * 8 + 8
                w = ((attr1 >> 8) & 0x3) * 8 + 8
                if w > 64:
                    w = 64
                if h > 64:
                    h = 64
                self._obj_window_rects.append((sx, sy, w, h))

    def step_scanline(self):
        """Advance one scanline during instruction execution.
        Updates VCount in MMIO, fires HBlank/VBlank DMA and IRQs.
        Called 160+ times per frame by the main loop between instruction batches.
        Does NOT render pixels — use render_frame() for that."""
        if self.vcount == 0:
            self._bg2_affine_snapshots = [None] * self.screen_height

        # Snapshot BG2 affine params for the CURRENT scanline BEFORE HBlank-DMA
        # modifies them. On hardware the PPU latches the affine matrix at the
        # start of the scanline; HBlank DMA fires later and prepares the
        # value for the NEXT scanline. Capturing before the vcount increment
        # guarantees snapshot[0] is populated.
        if 0 <= self.vcount < self.screen_height:
            try:
                self._bg2_affine_snapshots[self.vcount] = self._read_affine_bg2_params()
            except Exception:
                self._bg2_affine_snapshots[self.vcount] = None

        # Fire HBlank DMA AFTER the snapshot so DMA-written values land in the
        # next scanline's snapshot, not the current one.
        dma = self.memory._dma
        if dma is not None:
            dma.hblank_fire(self.vcount)

        self.vcount = (self.vcount + 1) % 228
        self.vblank = self.vcount >= self.screen_height

        io = self.memory.io
        io[6] = self.vcount & 0xFF
        io[7] = 0

        dispstat = io[4] | (io[5] << 8)
        if self.vblank:
            dispstat |= 0x0001
        else:
            dispstat &= ~0x0001
        dispstat |= 0x0002

        lyc = io[8] & 0xFF
        if self.vcount == lyc:
            dispstat |= 0x0004
        else:
            dispstat &= ~0x0004
        io[4] = dispstat & 0xFF
        io[5] = (dispstat >> 8) & 0xFF

        if dma is not None:
            if self.vblank:
                dma.vblank_fire()

        irq = self.memory._interrupts
        if irq is not None:
            if self.vblank and (dispstat & 0x0008):
                irq.vblank_irq()
            if dispstat & 0x0010:
                irq.hblank_irq()
            if (dispstat & 0x0004) and (dispstat & 0x0020):
                irq.vcounter_irq()

        if self.vblank:
            import sys
            mod = sys.modules.get("generated_rom")
            if mod is not None:
                mod.z = 1


    def render_frame(self):
        """Render one frame of graphics. Called once per frame after all scanlines."""
        self._read_registers()
        self._init_framebuffer()

        # Get current display mode
        mode = self.mode

        # Render based on mode
        if mode == 0:
            self._render_mode0()
        elif mode == 1:
            self._render_mode1()
        elif mode == 2:
            self._render_mode2()
        elif mode == 3:
            self._render_mode3()
        elif mode == 4:
            self._render_mode4()
        elif mode == 5:
            self._render_mode5()

        # Apply blending if enabled
        if self._blending_enabled():
            self._apply_blending_to_framebuffer()

        # Render sprites
        self._render_sprites()

    def _render_mode0(self):
        """Render Mode 0: Text backgrounds (BG0-3) with priority-based compositing"""
        any_bg = self.bg0_enable or self.bg1_enable or self.bg2_enable or self.bg3_enable
        if not any_bg and not self.obj_enable:
            return

        # Cache BG control registers per BG (avoids per-pixel read_u16)
        bg_enabled = [self.bg0_enable, self.bg1_enable, self.bg2_enable, self.bg3_enable]
        bg_cnt = [0, 0, 0, 0]
        bg_priority = [0, 0, 0, 0]
        bg_bpp8 = [False, False, False, False]
        bg_char_block = [0, 0, 0, 0]
        bg_screen_block = [0, 0, 0, 0]
        for bg in range(4):
            if not bg_enabled[bg]:
                continue
            cnt = self.memory.read_u16(0x04000008 + bg * 2)
            bg_cnt[bg] = cnt
            bg_priority[bg] = cnt & 0x03
            bg_bpp8[bg] = bool((cnt >> 7) & 1)
            bg_char_block[bg] = self.bg_char_block[bg]
            bg_screen_block[bg] = self.bg_screen_block[bg]

        # Tile decode cache: key=(tile_index, char_block, bpp8) → palette_indices list
        tile_cache = {}

        def get_tile(tile_index, char_block, bpp8):
            key = (tile_index, char_block, bpp8)
            cached = tile_cache.get(key)
            if cached is not None:
                return cached
            if bpp8:
                decoded = self._decode_tile_8bpp(tile_index, char_block)
            else:
                decoded = self._decode_tile_4bpp(tile_index, char_block)
            tile_cache[key] = decoded
            return decoded

        # Cache palette colors for speed (palette has 256 entries)
        palette_colors = [self._get_palette_color(i) for i in range(256)]

        # Check if windows are active
        win_active = self.win0_enable or self.win1_enable or self.obj_window_enable

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                if win_active:
                    layer_enable = self._get_window_layer_enable(x, y)
                else:
                    layer_enable = 0x0F  # All BGs enabled

                best_priority = 99
                best_color = None
                best_bg = -1

                for bg in range(4):
                    if not bg_enabled[bg]:
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    mx, my = self._apply_mosaic(x, y, is_obj=False)
                    tile_x = (mx + self.bg_hofs[bg]) % 256
                    tile_y = (my + self.bg_vofs[bg]) % 256

                    screen_block = bg_screen_block[bg]
                    tilemap_base = 0x06000000 + (screen_block * 0x0800)
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x
                    tilemap_addr = tilemap_base + (tilemap_index * 2)

                    tilemap_entry = self.memory.read_u16(tilemap_addr)
                    tile_index = tilemap_entry & 0x03FF
                    palette_bank = (tilemap_entry >> 12) & 0xF
                    h_flip = bool((tilemap_entry >> 10) & 1)
                    v_flip = bool((tilemap_entry >> 11) & 1)

                    pixel_x = tile_x % 8
                    pixel_y = tile_y % 8
                    if h_flip:
                        pixel_x = 7 - pixel_x
                    if v_flip:
                        pixel_y = 7 - pixel_y
                    pixel_index = pixel_y * 8 + pixel_x

                    palette_indices = get_tile(tile_index, bg_char_block[bg], bg_bpp8[bg])
                    if pixel_index >= len(palette_indices):
                        continue
                    color_idx = palette_indices[pixel_index]
                    if color_idx == 0:
                        continue

                    if bg_priority[bg] < best_priority:
                        best_priority = bg_priority[bg]
                        if bg_bpp8[bg]:
                            best_color = palette_colors[color_idx]
                        else:
                            best_color = palette_colors[palette_bank * 16 + color_idx]
                        best_bg = bg

                if best_color is not None:
                    self.framebuffer[y][x] = best_color
                    self.layer_origin[y][x] = best_bg

        if self.obj_enable:
            self._render_sprites(0x3F)


    def _render_mode1(self):
        """Render Mode 1: Text BG0/1 + Affine BG2
        
        BG0 and BG1: text-mode (4BPP tiled, same as Mode 0)
        BG2: affine background (256x256 or 512x512 pixels, 8-bit or 4-bit tiles)
        BG3: NOT available in Mode 1
        """
        any_bg = self.bg0_enable or self.bg1_enable or self.bg2_enable
        if not any_bg and not self.obj_enable:
            return

        # Cache BG control registers for BG0/1 (text mode)
        bg_enabled = [self.bg0_enable, self.bg1_enable, self.bg2_enable, False]
        bg_cnt = [0, 0, 0, 0]
        bg_priority = [0, 0, 0, 0]
        bg_bpp8 = [False, False, False, False]
        bg_char_block = [0, 0, 0, 0]
        bg_screen_block = [0, 0, 0, 0]
        bg_hofs = [0, 0, 0, 0]
        bg_vofs = [0, 0, 0, 0]
        
        for bg in range(3):
            if not bg_enabled[bg]:
                continue
            cnt = self.memory.read_u16(0x04000008 + bg * 2)
            bg_cnt[bg] = cnt
            bg_priority[bg] = cnt & 0x03
            bg_bpp8[bg] = bool((cnt >> 7) & 1)
            bg_char_block[bg] = self.bg_char_block[bg]
            bg_screen_block[bg] = self.bg_screen_block[bg]
            bg_hofs[bg] = self.bg_hofs[bg]
            bg_vofs[bg] = self.bg_vofs[bg]

        # Tile decode cache
        tile_cache = {}

        def get_tile(tile_index, char_block, bpp8):
            key = (tile_index, char_block, bpp8)
            cached = tile_cache.get(key)
            if cached is not None:
                return cached
            if bpp8:
                decoded = self._decode_tile_8bpp(tile_index, char_block)
            else:
                decoded = self._decode_tile_4bpp(tile_index, char_block)
            tile_cache[key] = decoded
            return decoded

        palette_colors = [self._get_palette_color(i) for i in range(256)]
        win_active = self.win0_enable or self.win1_enable or self.obj_window_enable

        # Per-scanline affine snapshots for BG2
        snaps = self._bg2_affine_snapshots
        if snaps and snaps[0] is not None:
            _, _, _, _, refx, refy, overflow0 = snaps[0]
        else:
            dx_f, dmx_f, dy_f, dmy_f, refx, refy, overflow0 = self._read_affine_bg2_params()

        sx = refx
        sy = refy

        for y in range(self.screen_height):
            # Get per-scanline affine params for BG2
            if y < len(snaps) and snaps[y] is not None:
                dx, dmx, dy, dmy, _, _, overflow = snaps[y]
            else:
                dx, dmx, dy, dmy, _, _, overflow = self._read_affine_bg2_params()

            row_fb = self.framebuffer[y]
            row_lo = self.layer_origin[y]
            
            for x in range(self.screen_width):
                if win_active:
                    layer_enable = self._get_window_layer_enable(x, y)
                else:
                    layer_enable = 0x0F

                best_priority = 99
                best_color = None
                best_bg = -1

                # Render text BGs (BG0, BG1)
                for bg in [0, 1]:
                    if not bg_enabled[bg]:
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    mx, my = self._apply_mosaic(x, y, is_obj=False)
                    tile_x = (mx + bg_hofs[bg]) % 256
                    tile_y = (my + bg_vofs[bg]) % 256

                    screen_block = bg_screen_block[bg]
                    tilemap_base = 0x06000000 + (screen_block * 0x0800)
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x
                    tilemap_addr = tilemap_base + (tilemap_index * 2)
                    tilemap_entry = self.memory.read_u16(tilemap_addr)

                    tile_index = tilemap_entry & 0x03FF
                    palette_num = (tilemap_entry >> 12) & 0x0F

                    pixel_x = tile_x % 8
                    pixel_y = tile_y % 8
                    pixel_index = pixel_y * 8 + pixel_x

                    palette_indices = get_tile(tile_index, bg_char_block[bg], bg_bpp8[bg])
                    if pixel_index >= len(palette_indices):
                        continue
                    color_idx = palette_indices[pixel_index]
                    if color_idx == 0:
                        continue

                    if bg_priority[bg] < best_priority:
                        best_priority = bg_priority[bg]
                        if bg_bpp8[bg]:
                            best_color = palette_colors[color_idx]
                        else:
                            best_color = palette_colors[palette_num * 16 + color_idx]
                        best_bg = bg

                # Render affine BG2
                if bg_enabled[2] and (layer_enable & 0x04):
                    # Apply affine transformation for BG2
                    x_float = float(x)
                    y_float = float(y)
                    
                    # source_x = refx + (x * dx) + (y * dmx)
                    # source_y = refy + (x * dy) + (y * dmy)
                    source_x = sx + (x_float * dx) + (y_float * dmx)
                    source_y = sy + (x_float * dy) + (y_float * dmy)
                    
                    # Convert to integer coordinates (8.8 fixed point)
                    tx = int(source_x) >> 8
                    ty = int(source_y) >> 8
                    
                    # Handle wrap-around or out-of-bounds
                    if overflow:
                        bg_size = self.bg_size[2]
                        if bg_size == 0:  # 256x256
                            tx &= 255
                            ty &= 255
                        elif bg_size == 1:  # 512x256
                            tx &= 511
                            ty &= 255
                        elif bg_size == 2:  # 256x512
                            tx &= 255
                            ty &= 511
                        else:  # 512x512
                            tx &= 511
                            ty &= 511
                    elif tx < 0 or ty < 0:
                        continue
                    
                    # Get BG2 size for bounds checking
                    bg_size = self.bg_size[2]
                    bg_width = 256 if bg_size in [0, 2] else 512
                    bg_height = 256 if bg_size in [0, 1] else 512
                    
                    if tx >= bg_width or ty >= bg_height:
                        continue

                    # Read tilemap
                    screen_block = bg_screen_block[2]
                    tilemap_base = 0x06000000 + (screen_block * 0x0800)
                    tilemap_x = tx // 8
                    tilemap_y = ty // 8
                    
                    # Handle screen size > 256x256 (tilemap is larger)
                    tilemap_width = 32 if bg_size in [0, 2] else 64
                    tilemap_index = tilemap_y * tilemap_width + tilemap_x
                    tilemap_addr = tilemap_base + (tilemap_index * 2)
                    
                    try:
                        tilemap_entry = self.memory.read_u16(tilemap_addr)
                    except:
                        continue

                    tile_index = tilemap_entry & 0x03FF
                    pixel_x = int(tx) % 8
                    pixel_y = int(ty) % 8
                    pixel_index = pixel_y * 8 + pixel_x

                    palette_indices = get_tile(tile_index, bg_char_block[2], bg_bpp8[2])
                    if pixel_index >= len(palette_indices):
                        continue
                    color_idx = palette_indices[pixel_index]
                    if color_idx == 0:
                        continue

                    if bg_priority[2] < best_priority:
                        best_priority = bg_priority[2]
                        if bg_bpp8[2]:
                            best_color = palette_colors[color_idx]
                        else:
                            palette_num = (tilemap_entry >> 12) & 0x0F
                            best_color = palette_colors[palette_num * 16 + color_idx]
                        best_bg = 2

                if best_color is not None:
                    row_fb[x] = best_color
                    row_lo[x] = best_bg

            # Accumulate affine offsets for next scanline
            sx += dmx
            sy += dmy

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _render_mode2(self):
        """Render Mode 2: Affine BG2/3 only
        
        BG2 and BG3: both affine backgrounds
        Same affine parameters as Mode 1's BG2
        BG2 and BG3 can both be affine-transformed independently
        """
        any_bg = self.bg2_enable or self.bg3_enable
        if not any_bg and not self.obj_enable:
            return

        # Cache BG control registers for BG2/3 (both affine)
        bg_enabled = [False, False, self.bg2_enable, self.bg3_enable]
        bg_priority = [0, 0, 0, 0]
        bg_bpp8 = [False, False, False, False]
        bg_char_block = [0, 0, 0, 0]
        bg_screen_block = [0, 0, 0, 0]
        bg_size = [0, 0, 0, 0]
        
        for bg in [2, 3]:
            if not bg_enabled[bg]:
                continue
            cnt = self.memory.read_u16(0x04000008 + bg * 2)
            bg_priority[bg] = cnt & 0x03
            bg_bpp8[bg] = bool((cnt >> 7) & 1)
            bg_char_block[bg] = self.bg_char_block[bg]
            bg_screen_block[bg] = self.bg_screen_block[bg]
            bg_size[bg] = self.bg_size[bg]

        # Tile decode cache
        tile_cache = {}

        def get_tile(tile_index, char_block, bpp8):
            key = (tile_index, char_block, bpp8)
            cached = tile_cache.get(key)
            if cached is not None:
                return cached
            if bpp8:
                decoded = self._decode_tile_8bpp(tile_index, char_block)
            else:
                decoded = self._decode_tile_4bpp(tile_index, char_block)
            tile_cache[key] = decoded
            return decoded

        palette_colors = [self._get_palette_color(i) for i in range(256)]
        win_active = self.win0_enable or self.win1_enable or self.obj_window_enable

        # Per-scanline affine snapshots
        snaps = self._bg2_affine_snapshots
        
        # For BG3, we need to read its affine params separately
        # BG3 uses different registers (BG3PA, BG3PB, etc.)
        def read_affine_bg3_params():
            """Read BG3 affine parameters from MMIO."""
            ap = self.memory._affine_params if hasattr(self.memory, '_affine_params') else None
            
            def _s16(lo, hi):
                v = lo | (hi << 8)
                return v - 0x10000 if v & 0x8000 else v
            
            # Read from BG3 registers directly
            try:
                bg3pa = self.memory.read_u16(0x04000030)
                bg3pb = self.memory.read_u16(0x04000032)
                bg3pc = self.memory.read_u16(0x04000034)
                bg3pd = self.memory.read_u16(0x04000036)
                bg3x_lo = self.memory.read_u16(0x04000038)
                bg3x_hi = self.memory.read_u16(0x0400003A)
                bg3y_lo = self.memory.read_u16(0x0400003C)
                bg3y_hi = self.memory.read_u16(0x0400003E)
                
                dx = _s16(bg3pa & 0xFF, (bg3pa >> 8) & 0xFF)
                dmx = _s16(bg3pb & 0xFF, (bg3pb >> 8) & 0xFF)
                dy = _s16(bg3pc & 0xFF, (bg3pc >> 8) & 0xFF)
                dmy = _s16(bg3pd & 0xFF, (bg3pd >> 8) & 0xFF)
                
                raw_refx = bg3x_lo | (bg3x_hi << 16)
                raw_refy = bg3y_lo | (bg3y_hi << 16)
                
                refx = raw_refx - 0x10000000 if raw_refx & 0x08000000 else raw_refx
                refy = raw_refy - 0x10000000 if raw_refy & 0x08000000 else raw_refy
                
                overflow = self.bg_affine[3]
                return dx, dmx, dy, dmy, refx, refy, overflow
            except:
                return 256, 0, 0, 256, 0, 0, False

        # Frame-start reference positions
        if snaps and snaps[0] is not None:
            _, _, _, _, refx_bg2, refy_bg2, overflow0_bg2 = snaps[0]
        else:
            dx_f, dmx_f, dy_f, dmy_f, refx_bg2, refy_bg2, overflow0_bg2 = self._read_affine_bg2_params()
        
        # BG3 reference position
        _, _, _, _, refx_bg3, refy_bg3, overflow0_bg3 = read_affine_bg3_params()

        sx_bg2 = refx_bg2
        sy_bg2 = refy_bg2
        sx_bg3 = refx_bg3
        sy_bg3 = refy_bg3

        for y in range(self.screen_height):
            # Get per-scanline affine params
            if y < len(snaps) and snaps[y] is not None:
                dx_bg2, dmx_bg2, dy_bg2, dmy_bg2, _, _, overflow_bg2 = snaps[y]
            else:
                dx_bg2, dmx_bg2, dy_bg2, dmy_bg2, _, _, overflow_bg2 = self._read_affine_bg2_params()
            
            dx_bg3, dmx_bg3, dy_bg3, dmy_bg3, _, _, overflow_bg3 = read_affine_bg3_params()

            row_fb = self.framebuffer[y]
            row_lo = self.layer_origin[y]
            
            for x in range(self.screen_width):
                if win_active:
                    layer_enable = self._get_window_layer_enable(x, y)
                else:
                    layer_enable = 0x0F

                best_priority = 99
                best_color = None
                best_bg = -1

                # Render affine BG2
                if bg_enabled[2] and (layer_enable & 0x04):
                    x_float = float(x)
                    y_float = float(y)
                    
                    source_x = sx_bg2 + (x_float * dx_bg2) + (y_float * dmx_bg2)
                    source_y = sy_bg2 + (x_float * dy_bg2) + (y_float * dmy_bg2)
                    
                    tx = int(source_x) >> 8
                    ty = int(source_y) >> 8
                    
                    # Handle wrap-around based on BG2 size
                    if overflow_bg2:
                        size = bg_size[2]
                        if size == 0:  # 256x256
                            tx &= 255
                            ty &= 255
                        elif size == 1:  # 512x256
                            tx &= 511
                            ty &= 255
                        elif size == 2:  # 256x512
                            tx &= 255
                            ty &= 511
                        else:  # 512x512
                            tx &= 511
                            ty &= 511
                    elif tx < 0 or ty < 0:
                        # Out of bounds (negative), skip this pixel
                        tx = -1
                    else:
                        # Check bounds
                        bg_width = 256 if bg_size[2] in [0, 2] else 512
                        bg_height = 256 if bg_size[2] in [0, 1] else 512
                        if tx >= bg_width or ty >= bg_height:
                            tx = -1  # Mark as invalid

                    if tx >= 0:
                        screen_block = bg_screen_block[2]
                        tilemap_base = 0x06000000 + (screen_block * 0x0800)
                        tilemap_x = tx // 8
                        tilemap_y = ty // 8
                        
                        tilemap_width = 32 if bg_size[2] in [0, 2] else 64
                        tilemap_index = tilemap_y * tilemap_width + tilemap_x
                        tilemap_addr = tilemap_base + (tilemap_index * 2)
                        
                        try:
                            tilemap_entry = self.memory.read_u16(tilemap_addr)
                            tile_index = tilemap_entry & 0x03FF
                            pixel_x = int(tx) % 8
                            pixel_y = int(ty) % 8
                            pixel_index = pixel_y * 8 + pixel_x

                            palette_indices = get_tile(tile_index, bg_char_block[2], bg_bpp8[2])
                            if pixel_index < len(palette_indices):
                                color_idx = palette_indices[pixel_index]
                                if color_idx > 0 and bg_priority[2] < best_priority:
                                    best_priority = bg_priority[2]
                                    if bg_bpp8[2]:
                                        best_color = palette_colors[color_idx]
                                    else:
                                        palette_num = (tilemap_entry >> 12) & 0x0F
                                        best_color = palette_colors[palette_num * 16 + color_idx]
                                    best_bg = 2
                        except:
                            # Error reading tilemap, skip this pixel
                            pass

                # Render affine BG3
                if bg_enabled[3] and (layer_enable & 0x08):
                    x_float = float(x)
                    y_float = float(y)
                    
                    source_x = sx_bg3 + (x_float * dx_bg3) + (y_float * dmx_bg3)
                    source_y = sy_bg3 + (x_float * dy_bg3) + (y_float * dmy_bg3)
                    
                    tx = int(source_x) >> 8
                    ty = int(source_y) >> 8
                    
                    # Handle wrap-around based on BG3 size
                    if overflow_bg3:
                        size = bg_size[3]
                        if size == 0:  # 256x256
                            tx &= 255
                            ty &= 255
                        elif size == 1:  # 512x256
                            tx &= 511
                            ty &= 255
                        elif size == 2:  # 256x512
                            tx &= 255
                            ty &= 511
                        else:  # 512x512
                            tx &= 511
                            ty &= 511
                    elif tx < 0 or ty < 0:
                        # Out of bounds (negative), skip this pixel
                        tx = -1
                    else:
                        bg_width = 256 if bg_size[3] in [0, 2] else 512
                        bg_height = 256 if bg_size[3] in [0, 1] else 512
                        if tx >= bg_width or ty >= bg_height:
                            tx = -1

                    if tx >= 0:
                        screen_block = bg_screen_block[3]
                        tilemap_base = 0x06000000 + (screen_block * 0x0800)
                        tilemap_x = tx // 8
                        tilemap_y = ty // 8
                        
                        tilemap_width = 32 if bg_size[3] in [0, 2] else 64
                        tilemap_index = tilemap_y * tilemap_width + tilemap_x
                        tilemap_addr = tilemap_base + (tilemap_index * 2)
                        
                        try:
                            tilemap_entry = self.memory.read_u16(tilemap_addr)
                            tile_index = tilemap_entry & 0x03FF
                            pixel_x = int(tx) % 8
                            pixel_y = int(ty) % 8
                            pixel_index = pixel_y * 8 + pixel_x

                            palette_indices = get_tile(tile_index, bg_char_block[3], bg_bpp8[3])
                            if pixel_index < len(palette_indices):
                                color_idx = palette_indices[pixel_index]
                                if color_idx > 0 and bg_priority[3] < best_priority:
                                    best_priority = bg_priority[3]
                                    if bg_bpp8[3]:
                                        best_color = palette_colors[color_idx]
                                    else:
                                        palette_num = (tilemap_entry >> 12) & 0x0F
                                        best_color = palette_colors[palette_num * 16 + color_idx]
                                    best_bg = 3
                        except:
                            # Error reading tilemap, skip this pixel
                            pass

                if best_color is not None:
                    row_fb[x] = best_color
                    row_lo[x] = best_bg

            # Accumulate affine offsets for next scanline
            sx_bg2 += dmx_bg2
            sy_bg2 += dmy_bg2
            sx_bg3 += dmx_bg3
            sy_bg3 += dmy_bg3

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _read_affine_bg2_params(self):
        """Read and sign-extend BG2 affine parameters from _affine_params.
        Returns (dx, dmx, dy, dmy, refx, refy, overflow).
        Matches mGBA's GBAVideoSoftwareBackground layout.
        """
        ap = self.memory._affine_params

        def _s16(lo, hi):
            v = lo | (hi << 8)
            return v - 0x10000 if v & 0x8000 else v

        dx = _s16(ap[0], ap[1])    # BG2PA: per-pixel X increment
        dmx = _s16(ap[2], ap[3])   # BG2PB: per-scanline X increment
        dy = _s16(ap[4], ap[5])    # BG2PC: per-pixel Y increment
        dmy = _s16(ap[6], ap[7])   # BG2PD: per-scanline Y increment

        raw_refx = (ap[8] | (ap[9] << 8) | (ap[10] << 16) | (ap[11] << 24)) & 0x0FFFFFFF
        refx = raw_refx - 0x10000000 if raw_refx & 0x08000000 else raw_refx
        raw_refy = (ap[12] | (ap[13] << 8) | (ap[14] << 16) | (ap[15] << 24)) & 0x0FFFFFFF
        refy = raw_refy - 0x10000000 if raw_refy & 0x08000000 else raw_refy

        overflow = self.bg_affine[2]
        return dx, dmx, dy, dmy, refx, refy, overflow

    def _render_mode3(self):
        """Render Mode 3: 240x160 16-bit bitmap via affine BG2 transformation.

        mGBA's GBAVideoSoftwareRendererDrawBackgroundMode3 applies the BG2 affine
        matrix per scanline. Per-scanline snapshots captured by step_scanline()
        before HBlank DMA provide the correct dx/dy/dmx/dmy values.
        """
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000
        try:
            vram_arr, vram_off = self.memory._buffer_for_addr(vram_base)
            vram_bytes = bytes(vram_arr[vram_off:vram_off + self.screen_height * self.screen_width * 2])
        except Exception:
            vram_bytes = bytes(self.screen_height * self.screen_width * 2)

        try:
            bdv = self.memory.read_u16(0x05000000)
            backdrop_rgb = (
                _c5to8((bdv >> 0) & 0x1F),
                _c5to8((bdv >> 5) & 0x1F),
                _c5to8((bdv >> 10) & 0x1F),
            )
        except Exception:
            backdrop_rgb = (0, 0, 0)

        snaps = self._bg2_affine_snapshots
        if snaps and snaps[0] is not None:
            _, _, _, _, refx, refy, overflow0 = snaps[0]
        else:
            dx_f, dmx_f, dy_f, dmy_f, refx, refy, overflow0 = self._read_affine_bg2_params()

        fb = self.framebuffer
        lo = self.layer_origin
        sw = self.screen_width
        sh = self.screen_height
        vlen = len(vram_bytes)
        n_snaps = len(snaps)

        sx = refx
        sy = refy

        for y in range(sh):
            if y < n_snaps and snaps[y] is not None:
                dx, dmx, dy, dmy, _, _, overflow = snaps[y]
            else:
                dx, dmx, dy, dmy, _, _, overflow = self._read_affine_bg2_params()
            row_fb = fb[y]
            row_lo = lo[y]
            x = sx - dx
            y_coord = sy - dy
            for px in range(sw):
                x += dx
                y_coord += dy
                tx = x >> 8
                ty = y_coord >> 8
                if overflow:
                    tx %= sw
                    ty %= sh
                elif tx < 0 or ty < 0 or tx >= sw or ty >= sh:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
                    continue
                offset = (tx + ty * sw) * 2
                if offset + 1 < vlen:
                    color_val = vram_bytes[offset] | (vram_bytes[offset + 1] << 8)
                    row_fb[px] = (
                        _c5to8((color_val >> 0) & 0x1F),
                        _c5to8((color_val >> 5) & 0x1F),
                        _c5to8((color_val >> 10) & 0x1F),
                    )
                    row_lo[px] = 2
                else:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
            sx += dmx
            sy += dmy

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _render_mode4(self):
        """Render Mode 4: 240x160 8BPP bitmap via affine BG2 transformation.

        Same affine pipeline as Mode 3, but pixels are palette-indexed (1 byte each).
        """
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        try:
            vram_arr, vram_off = self.memory._buffer_for_addr(vram_base)
            vram_bytes = bytes(vram_arr[vram_off:vram_off + self.screen_height * self.screen_width])
        except Exception:
            vram_bytes = bytes(self.screen_height * self.screen_width)
        try:
            pal_arr, pal_off = self.memory._buffer_for_addr(0x05000000)
            palette_bytes = bytes(pal_arr[pal_off:pal_off + 512])
        except Exception:
            palette_bytes = bytes(512)
        palette_rgb = []
        for i in range(256):
            cv = palette_bytes[i * 2] | (palette_bytes[i * 2 + 1] << 8)
            palette_rgb.append((
                _c5to8((cv >> 0) & 0x1F),
                _c5to8((cv >> 5) & 0x1F),
                _c5to8((cv >> 10) & 0x1F),
            ))

        # Per-scanline affine snapshots captured by step_scanline() before HBlank-DMA.
        snaps = self._bg2_affine_snapshots
        if snaps and snaps[0] is not None:
            _, _, _, _, refx, refy, overflow0 = snaps[0]
        else:
            dx_f, dmx_f, dy_f, dmy_f, refx, refy, overflow0 = self._read_affine_bg2_params()

        backdrop_rgb = palette_rgb[0]

        sx = refx
        sy = refy
        fb = self.framebuffer
        lo = self.layer_origin
        sw = self.screen_width
        sh = self.screen_height
        vlen = len(vram_bytes)
        n_snaps = len(snaps)

        for y in range(sh):
            if y < n_snaps and snaps[y] is not None:
                dx, dmx, dy, dmy, _, _, overflow = snaps[y]
            else:
                dx, dmx, dy, dmy, _, _, overflow = self._read_affine_bg2_params()
            row_fb = fb[y]
            row_lo = lo[y]
            x = sx - dx
            y_coord = sy - dy
            for px in range(sw):
                x += dx
                y_coord += dy
                tx = x >> 8
                ty = y_coord >> 8
                if overflow:
                    tx %= sw
                    ty %= sh
                elif tx < 0 or ty < 0 or tx >= sw or ty >= sh:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
                    continue
                offset = tx + ty * sw
                if offset < vlen:
                    row_fb[px] = palette_rgb[vram_bytes[offset]]
                    row_lo[px] = 2
                else:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
            sx += dmx
            sy += dmy

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _get_palette_color_256(self, palette_idx: int) -> Tuple[int, int, int]:
        """Get RGB color from 256-color palette (Mode 4)."""
        palette_addr = 0x05000000 + (palette_idx * 2)

        try:
            color_val = self.memory.read_u16(palette_addr)
            # On real hardware, palette entry 0 = color 0 = black.
            # Do NOT generate fallback grayscale for uninitialized entries.
            r = _c5to8((color_val >> 0) & 0x1F)
            g = _c5to8((color_val >> 5) & 0x1F)
            b = _c5to8((color_val >> 10) & 0x1F)
            return (r, g, b)
        except:
            return (0, 0, 0)

    def _render_mode5(self):
        """Render Mode 5: 160x128 16-bit bitmap via affine BG2 transformation.

        Same affine pipeline as Mode 3, but dimensions are 160x128.
        """
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000
        try:
            vram_arr, vram_off = self.memory._buffer_for_addr(vram_base)
            vram_bytes = bytes(vram_arr[vram_off:vram_off + 128 * 160 * 2])
        except Exception:
            vram_bytes = bytes(128 * 160 * 2)

        # Per-scanline affine snapshots captured by step_scanline() before HBlank-DMA.
        snaps = self._bg2_affine_snapshots
        if snaps and snaps[0] is not None:
            _, _, _, _, refx, refy, overflow0 = snaps[0]
        else:
            dx_f, dmx_f, dy_f, dmy_f, refx, refy, overflow0 = self._read_affine_bg2_params()

        sx = refx
        sy = refy
        fb = self.framebuffer
        lo = self.layer_origin
        bw = 160
        bh = 128
        vlen = len(vram_bytes)
        n_snaps = len(snaps)

        for y in range(bh):
            if y < n_snaps and snaps[y] is not None:
                dx, dmx, dy, dmy, _, _, overflow = snaps[y]
            else:
                dx, dmx, dy, dmy, _, _, overflow = self._read_affine_bg2_params()
            row_fb = fb[y]
            row_lo = lo[y]
            x = sx - dx
            y_coord = sy - dy
            for px in range(bw):
                x += dx
                y_coord += dy
                tx = x >> 8
                ty = y_coord >> 8
                if overflow:
                    tx %= bw
                    ty %= bh
                elif tx < 0 or ty < 0 or tx >= bw or ty >= bh:
                    row_fb[px] = (0, 0, 0)
                    row_lo[px] = 0
                    continue
                offset = (tx + ty * bw) * 2
                if offset + 1 < vlen:
                    color_val = vram_bytes[offset] | (vram_bytes[offset + 1] << 8)
                    row_fb[px] = (
                        _c5to8((color_val >> 0) & 0x1F),
                        _c5to8((color_val >> 5) & 0x1F),
                        _c5to8((color_val >> 10) & 0x1F),
                    )
                    row_lo[px] = 2
                else:
                    row_fb[px] = (0, 0, 0)
                    row_lo[px] = 0
            sx += dmx
            sy += dmy

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _blending_enabled(self) -> bool:
        return (self.bldcnt & 0x3FFF) != 0

    def _apply_blending_to_framebuffer(self):
        blend_mode = (self.bldcnt >> 6) & 0x3
        
        if blend_mode == 1:  # Special effect: alpha blend between 1st and 2nd targets
            eva = min(self.bldalpha_eva, 16)
            evb = min(self.bldalpha_evb, 16)
            if eva > 0 or evb > 0:
                # BLDCNT bits 0-5: 1st target (BG0=bit0, BG1=bit1, BG2=bit2, BG3=bit3, OBJ=bit4, BD=bit5)
                # BLDCNT bits 8-13: 2nd target (same mapping)
                first_target_mask = self.bldcnt & 0x3F
                second_target_mask = (self.bldcnt >> 8) & 0x3F
                
                # Read backdrop color for BD (bit 5 of each mask) from palette entry 0
                try:
                    backdrop_color_val = self.memory.read_u16(0x05000000)
                    bg_backdrop_r = _c5to8((backdrop_color_val >> 0) & 0x1F)
                    bg_backdrop_g = _c5to8((backdrop_color_val >> 5) & 0x1F)
                    bg_backdrop_b = _c5to8((backdrop_color_val >> 10) & 0x1F)
                except Exception:
                    bg_backdrop_r, bg_backdrop_g, bg_backdrop_b = 0, 0, 0
                if second_target_mask & (1 << 5):  # BD is 2nd target
                    pass  # backdrop already read above
                
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        source_layer = self.layer_origin[y][x]
                        r, g, b = self.framebuffer[y][x]
                        
                        # Check if this pixel's source layer is in 1st target
                        if (first_target_mask >> source_layer) & 1:
                            # Find 2nd target pixel color
                            second_r, second_g, second_b = bg_backdrop_r, bg_backdrop_g, bg_backdrop_b
                            
                            # Check if 2nd target includes backdrop (BD)
                            if (second_target_mask >> 5) & 1:
                                second_r, second_g, second_b = bg_backdrop_r, bg_backdrop_g, bg_backdrop_b
                            else:
                                # Look for 2nd target layer at this position
                                stf_color = self.second_target_framebuffer[y][x]
                                if stf_color is not None:
                                    second_r, second_g, second_b = stf_color
                            
                            # Apply blend formula: result = (pixel * eva + second_target * evb) / 16
                            r = (r * eva + second_r * evb) // 16
                            g = (g * eva + second_g * evb) // 16
                            b = (b * eva + second_b * evb) // 16
                        
                        self.framebuffer[y][x] = (r, g, b)
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    r = min(int(r + (255 - r) * factor), 255)
                    g = min(int(g + (255 - g) * factor), 255)
                    b = min(int(b + (255 - b) * factor), 255)
                    self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 2:  # Brightness increase (add white)
            # Formula: result = min(src + (255 - src) * Evy / 16, 255)
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    r = min(int(r + (255 - r) * factor), 255)
                    g = min(int(g + (255 - g) * factor), 255)
                    b = min(int(b + (255 - b) * factor), 255)
                    self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 3:  # Brightness decrease (multiply by dark)
            # Formula: result = int(src * (16 - Evy) / 16)
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    r = int(r * (1.0 - factor))
                    g = int(g * (1.0 - factor))
                    b = int(b * (1.0 - factor))
                    self.framebuffer[y][x] = (r, g, b)

    def save_screenshot(self, path: str):
        """Save current framebuffer as screenshot"""
        try:
            import PIL.Image

            img = PIL.Image.new("RGB", (self.screen_width, self.screen_height))
            pixels = img.load()
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    pixels[x, y] = (r, g, b)
            img.save(path)
        except ImportError:
            # Fallback if PIL not available - create PPM file
            with open(path.replace(".png", ".ppm"), "wb") as f:
                f.write(f"P6 {self.screen_width} {self.screen_height} 255\n".encode())
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        r, g, b = self.framebuffer[y][x]
                        f.write(bytes([r, g, b]))

    def _is_affine_sprite(self, attr1: int) -> bool:
        """Check if sprite uses affine transformation (attr1 bit 11)"""
        return bool((attr1 >> 11) & 1)

    def _get_sprite_affine_params(self, attr1: int) -> Tuple[int, int, int, int, int, int]:
        """Get affine parameters for sprite from OAM affine parameter table.
        
        attr1 bits 8-10 store the affine parameter table index (0-31).
        Each entry in the table is 8 bytes: PA, PB, PC, PD (16-bit each).
        """
        affine_index = (attr1 >> 8) & 0x1F
        affine_base = 0x07000020 + (affine_index * 8)
        pa = self.memory.read_u16(affine_base + 0)
        pb = self.memory.read_u16(affine_base + 2)
        pc = self.memory.read_u16(affine_base + 4)
        pd = self.memory.read_u16(affine_base + 6)
        center_x = 0
        center_y = 0
        return pa, pb, pc, pd, center_x, center_y

    def _apply_affine_transform_sprite(
        self, x: int, y: int, pa: int, pb: int, pc: int, pd: int, center_x: int, center_y: int
    ) -> Tuple[int, int]:
        """Apply affine transform using s1.7.8 fixed-point parameters."""
        pa_float = self._s178_to_float(pa)
        pb_float = self._s178_to_float(pb)
        pc_float = self._s178_to_float(pc)
        pd_float = self._s178_to_float(pd)
        new_x = pa_float * (x - center_x) + pb_float * (y - center_y) + center_x
        new_y = pc_float * (x - center_x) + pd_float * (y - center_y) + center_y
        return int(new_x), int(new_y)

    def _render_sprite_line(
        self,
        sprite_x: int,
        sprite_y: int,
        line: int,
        width: int,
        height: int,
        attr0: int,
        attr1: int,
    ) -> List[Tuple[int, int, int]]:
        colors = []

        if self._is_affine_sprite(attr1):
            pa, pb, pc, pd, _, _ = self._get_sprite_affine_params(attr1)
            sprite_width = ((attr1 >> 8) & 0x3) * 8 + 8 if width > 8 else 8
            
            # Check double-size flag (attr0 bit 8)
            double_size = bool(attr0 & 0x100)
            if double_size:
                # Double the bounding box dimensions
                sprite_width *= 2
                height *= 2
            
            center_x = sprite_width // 2
            center_y = height // 2

            local_line = line - sprite_y
            for px in range(width):
                local_x = px
                src_x, src_y = self._apply_affine_transform_sprite(
                    local_x, local_line, pa, pb, pc, pd, center_x, center_y
                )

                if 0 <= src_x < sprite_width and 0 <= src_y < height:
                    vram_addr = 0x06014000 + (src_y * sprite_width + src_x) * 2
                    try:
                        color_val = self.memory.read_u16(vram_addr)
                        r = _c5to8((color_val >> 0) & 0x1F)
                        g = _c5to8((color_val >> 5) & 0x1F)
                        b = _c5to8((color_val >> 10) & 0x1F)
                        if color_val & 0x8000:
                            colors.append((r, g, b))
                        else:
                            colors.append(None)
                    except:
                        colors.append(None)
                else:
                    colors.append(None)
        else:
            # Check flip flags for normal (non-affine) sprites
            hflip = bool(attr1 & 0x0800)  # bit 12
            vflip = bool(attr1 & 0x1000)  # bit 13
            
            for px in range(width):
                if sprite_x + px < 0 or sprite_x + px >= self.screen_width:
                    colors.append(None)
                    continue
                if line < 0 or line >= self.screen_height:
                    colors.append(None)
                    continue
                
                # Apply horizontal flip
                src_px = width - 1 - px if hflip else px
                
                # Apply vertical flip
                src_line = height - 1 - (line - sprite_y) if vflip else (line - sprite_y)
                
                vram_addr = 0x06014000 + (src_line * width + src_px) * 2
                try:
                    color_val = self.memory.read_u16(vram_addr)
                    if color_val & 0x8000:
                        r = _c5to8((color_val >> 0) & 0x1F)
                        g = _c5to8((color_val >> 5) & 0x1F)
                        b = _c5to8((color_val >> 10) & 0x1F)
                        colors.append((r, g, b))
                    else:
                        colors.append(None)
                except:
                    colors.append(None)

        return colors

    def _render_sprites(self, layer_enable: int = 0x3F):
        OAM_BASE = 0x07000000
        NUM_SPRITES = 128

        for sprite_idx in range(NUM_SPRITES):
            sprite_addr = OAM_BASE + (sprite_idx * 8)

            try:
                attr0 = self.memory.read_u16(sprite_addr + 0)
                attr1 = self.memory.read_u16(sprite_addr + 2)
                attr2 = self.memory.read_u16(sprite_addr + 4)
            except:
                continue

            if attr0 == 0 and attr1 == 0 and attr2 == 0:
                continue

            obj_mode = (attr0 >> 10) & 3
            if obj_mode == 2:
                continue

            sprite_y = attr0 & 0xFF
            sprite_x = attr1 & 0x1FF
            height = ((attr0 >> 12) & 7) * 8 + 8
            width = ((attr1 >> 8) & 0x3) * 8 + 8

            if width > 64:
                width = 64
            if height > 64:
                height = 64

            tile_num = attr2 & 0x3FF
            palette_num = (attr2 >> 12) & 0xF
            vflip = bool(attr1 & 0x1000)
            hflip = bool(attr1 & 0x0800)
            affine = self._is_affine_sprite(attr1)

            for dy in range(height):
                screen_y = sprite_y + dy
                if screen_y < 0 or screen_y >= self.screen_height:
                    continue

                pixel_y = dy
                if vflip:
                    pixel_y = height - 1 - dy

                for dx in range(width):
                    screen_x = sprite_x + dx
                    if screen_x < 0 or screen_x >= self.screen_width:
                        continue

                    pixel_x = dx
                    if hflip:
                        pixel_x = width - 1 - dx

                    tile_row = pixel_y // 8
                    tile_col = pixel_x // 8
                    tile_pixel_y = pixel_y % 8
                    tile_pixel_x = pixel_x % 8

                    tile_addr = tile_num + tile_row * (width // 8) + tile_col

                    tile_indices = self._decode_tile_4bpp(tile_addr, 4)

                    tile_pixel_idx = tile_pixel_y * 8 + tile_pixel_x
                    if tile_pixel_idx < len(tile_indices):
                        color_idx = tile_indices[tile_pixel_idx]
                        if color_idx != 0:
                            if self.win0_enable or self.win1_enable:
                                pixel_layer_enable = self._get_window_layer_enable(screen_x, screen_y)
                                if not (pixel_layer_enable & 0x10):
                                    continue

                            palette_idx = palette_num * 16 + color_idx
                            color = self._get_palette_color(palette_idx)
                            self.framebuffer[screen_y][screen_x] = color
                            self.layer_origin[screen_y][screen_x] = 4  # OBJ layer

    def _render_sprites_line(self, y: int, x: int, layer_enable: int):
        OAM_BASE = 0x07000000
        NUM_SPRITES = 128

        for sprite_idx in range(NUM_SPRITES):
            sprite_addr = OAM_BASE + (sprite_idx * 8)

            try:
                attr0 = self.memory.read_u16(sprite_addr + 0)
                attr1 = self.memory.read_u16(sprite_addr + 2)
                attr2 = self.memory.read_u16(sprite_addr + 4)
            except:
                continue

            sprite_y = attr0 & 0xFF
            sprite_x = attr1 & 0x1FF

            if sprite_y == 0 and sprite_x == 0 and attr2 == 0:
                continue

            obj_mode = (attr0 >> 10) & 3
            if obj_mode == 2:
                continue

            height = ((attr0 >> 12) & 7) * 8 + 8
            width = ((attr1 >> 8) & 0x3) * 8 + 8

            if width > 64:
                width = 64
            if height > 64:
                height = 64

            if y < sprite_y or y >= sprite_y + height:
                continue
            if x < sprite_x or x >= sprite_x + width:
                continue

            tile_num = attr2 & 0x3FF
            palette_num = (attr2 >> 12) & 0xF
            vflip = bool(attr1 & 0x1000)
            hflip = bool(attr1 & 0x0800)

            pixel_y = y - sprite_y
            if vflip:
                pixel_y = height - 1 - pixel_y

            pixel_x = x - sprite_x
            if hflip:
                pixel_x = width - 1 - pixel_x

            tile_w = 8
            tile_h = 8
            tile_row = pixel_y // tile_h
            tile_col = pixel_x // tile_w
            tile_pixel_y = pixel_y % tile_h
            tile_pixel_x = pixel_x % tile_w

            vram_addr = (
                0x06010000
                + (tile_num * 64)
                + (tile_row * 2 * tile_w // 8)
                + tile_row * tile_w
                + tile_pixel_y * tile_w // 8
                + tile_pixel_x // 8 * 2
                + tile_pixel_y % 2
            )

            try:
                char_data = self.memory.read_u16(vram_addr & 0x0601FFFF)

                bit_pos = 7 - (tile_pixel_x % 8)
                color_idx = (char_data >> (bit_pos * 2)) & 3

                if color_idx != 0 or (attr0 & 0x2000):
                    palette_addr = 0x05000200 + (palette_num * 32) + (color_idx * 2)
                    palette_val = self.memory.read_u16(palette_addr)

                    r = _c5to8((palette_val >> 0) & 0x1F)
                    g = _c5to8((palette_val >> 5) & 0x1F)
                    b = _c5to8((palette_val >> 10) & 0x1F)

                    self.framebuffer[y][x] = (r, g, b)
            except Exception:
                ...
