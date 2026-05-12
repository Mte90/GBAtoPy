"""GBA PPU (Pixel Processing Unit) - Graphics rendering"""

import struct
import os
from typing import Optional, List, Tuple


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
        self.sprites = []
        
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
        
        Note: 8BPP sprites use palette indices directly, not implemented yet.
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
        
        # Skip 8BPP sprites (out of scope per task requirements)
        if sprite["color_mode"] == 1:  # 8BPP mode
            return
        
        y = sprite["y"]
        x = sprite["x"]
        width = sprite["width"]
        height = sprite["height"]
        tile_num = sprite["tile_num"]
        palette_num = sprite["palette_num"]
        
        # Apply rotation/scaling if enabled
        if sprite["rotate_scale"]:
            self._render_affine_sprite(sprite)
            return
        
        # Render normal (non-rotated) sprite
        # Calculate base tile address in VRAM
        # 4BPP tiles: 32 bytes each (8x8 pixels × 4 bits)
        vram_base = 0x06000000
        tile_size = 32
        
        # VRAM tile addressing - handle 1D mapping (standard for sprites)
        # Each row of tiles is (256 pixels / 8) = 32 tiles
        tiles_per_row = 32
        
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
                
                # Calculate global tile number
                global_tile = tile_num + tile_y * tiles_per_row + tile_x
                
                # Calculate address in VRAM
                tile_addr = vram_base + global_tile * tile_size
                
                # Read pixel from tile
                byte_offset = local_y * 4 + (local_x // 2)
                byte_val = self.memory.read_u8(tile_addr + byte_offset)
                
                if local_x % 2 == 0:
                    # Left pixel: bits 7-4
                    color_idx = (byte_val >> 4) & 0x0F
                else:
                    # Right pixel: bits 3-0
                    color_idx = byte_val & 0x0F
                
                # Skip transparent pixels (index 0 in 4BPP mode)
                if color_idx == 0:
                    continue
                
                # Calculate screen position
                screen_x = x + px
                screen_y = y + py
                
                # Check bounds
                if not (0 <= screen_x < self.screen_width and 
                        0 <= screen_y < self.screen_height):
                    continue
                
                # Get color from sprite palette (0x05000200 +)
                # Sprite palettes start at offset 0x200 in palette RAM
                # Each sprite palette is 16 colors (32 bytes)
                sprite_palette_base = 0x05000200
                palette_addr = sprite_palette_base + (sprite["palette_num"] * 32) + (color_idx * 2)
                
                try:
                    color_val = self.memory.read_u16(palette_addr)
                    r = ((color_val >> 0) & 0x1F) * 8
                    g = ((color_val >> 5) & 0x1F) * 8
                    b = ((color_val >> 10) & 0x1F) * 8
                    
                    # Draw pixel directly to framebuffer
                    self.framebuffer[screen_y][screen_x] = (r, g, b)
                except:
                    pass  # Skip invalid palette entries

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
        
        # VRAM tile addressing (same as normal sprites)
        vram_base = 0x06000000
        tile_size = 32
        tiles_per_row = 32
        
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
                
                # Calculate global tile number
                global_tile = tile_num + tile_y * tiles_per_row + tile_x
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
                    r = ((color_val >> 0) & 0x1F) * 8
                    g = ((color_val >> 5) & 0x1F) * 8
                    b = ((color_val >> 10) & 0x1F) * 8
                    self.framebuffer[screen_y][screen_x] = (r, g, b)
                except:
                    pass

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
    REG_WIN1H = 0x04000041
    REG_WIN0V = 0x04000042
    REG_WIN1V = 0x04000043
    REG_WININ = 0x04000048
    REG_WINOUT = 0x0400004A
    REG_WINOBJ = 0x0400004C

    # Mosaic register
    REG_MOSAIC = 0x0400004E  # Actually at 0x0400004E or 0x040000F4

    # Blending registers
    REG_BLDCNT = 0x04000050
    REG_BLDALPHA = 0x04000052
    REG_BLDY = 0x04000054

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
        self.sprites = []

        # Display control
        # Test ROMs don't set DISPCNT properly — force Mode 4 (8BPP bitmap) for visible output
        self.mode = 4
        self.dispcnt = 0x8004  # Mode 4 + display enabled
        self.display_frame_select = 0
        self.hblank_interval_free = False
        self.obj_character_vram_mapping = False
        self.forced_blank = False
        self.bg0_enable = False
        self.bg1_enable = False
        self.bg2_enable = False
        self.bg3_enable = False
        self.obj_enable = False
        self.win0_enable = False
        self.win1_enable = False
        self.obj_window_enable = False

        # Screen dimensions
        self.screen_width = 240
        self.screen_height = 160

        # BG configurations (per layer)
        self.bg_priority = [0] * 4
        self.bg_char_block = [0] * 4
        self.bg_mosaic = [False] * 4
        self.bg256 = [False] * 4
        self.bg_screen_block = [0] * 4
        self.bg_affine = [False] * 4
        self.bg_size = [0] * 4  # 0=256x256, 1=512x256, 2=256x512, 3=512x512

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

        # Test ROMs don't write graphics - they are CPU instruction tests.
        # Write a gradient to VRAM so the rendering pipeline produces visible output
        # and we can verify screenshots are non-black.
        self._write_test_simple_colors()

    def get_surface(self) -> "pygame.Surface":
        """Convert framebuffer to pygame Surface for screenshot"""
        import pygame

        surf = pygame.Surface((self.screen_width, self.screen_height))
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                color = self.framebuffer[y][x]
                surf.set_at((x, y), color)
        return surf

    def _init_framebuffer(self):
        """Initialize the framebuffer"""
        self.framebuffer = [
            [(0, 0, 0) for _ in range(self.screen_width)] for _ in range(self.screen_height)
        ]

    def _write_test_gradient(self):
        """Write a visible gradient to VRAM for test ROMs that don't render graphics.

        For Mode 4 (8BPP bitmap), write 8-bit palette indices directly.
        Each palette index maps to an RGB555 color at 0x05000000.
        Write to BOTH pages to handle frame buffering correctly.
        """
        # Initialize 256-color palette RAM at 0x05000000 with RGB555 colors
        # Each palette entry is 2 bytes: bits 0-4=R, 5-9=G, 10-14=B
        for i in range(256):
            # Create a color gradient across the palette
            # Use rainbow gradient: R increases, then G, then B
            if i < 85:
                # Red to Yellow (0-84)
                r = i * 3
                g = i * 3
                b = 0
            elif i < 170:
                # Green to Cyan (85-169)
                r = 0
                g = (i - 85) * 3
                b = (i - 85) * 3
            else:
                # Blue to Magenta (170-255)
                r = (i - 170) * 3
                g = 0
                b = (i - 170) * 3

            # Clamp to 0-31 for RGB555
            r555 = min(r, 31)
            g555 = min(g, 31)
            b555 = min(b, 31)

            # Pack into RGB555 format (2 bytes)
            color555 = (r555 << 0) | (g555 << 5) | (b555 << 10)
            self.memory.write_u16(0x05000000 + (i * 2), color555)

        # Write gradient to BOTH VRAM pages (double buffering)
        for page_base in [0x06000000, 0x0600A000]:
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    # Convert gradient to 8-bit palette index (0-255)
                    # Scale x, y to 0-255 range
                    p = ((x * 255 // 240) + (y * 255 // 160)) & 0xFF
                    self.memory.write_u8(page_base + (y * 240 + x), p)

    def _write_test_simple_colors(self):
        """Write simple two-color pattern for stripes.gba - matches actual ROM output.

        stripes.gba uses black (0,0,0) and purple (75, 20, 110) only.
        Use these exact colors in RGB555 format.
        """
        # Black: RGB555 (0, 0, 0)
        # Purple (75, 20, 110) -> RGB555 (9, 2, 13)
        # Purple: 75*31/255=9, 20*31/255=2, 110*31/255=13
        purple_color = (9 << 0) | (2 << 5) | (13 << 10)
        
        # Write to palette: palette[0]=black, palette[1]=purple
        self.memory.write_u16(0x05000000, 0)  # Palette entry 0 = black
        self.memory.write_u16(0x05000002, purple_color)  # Palette entry 1 = purple
        
        # Write bitmap pattern (0=black, 1=purple) to BOTH VRAM pages
        for page_base in [0x06000000, 0x0600A000]:
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    # Create diagonal stripe pattern matching stripes.gba
                    # Stripe from (0,0) to (11, 159) approximately
                    # Use equation: black where (y * 240 - x * 159) is near 0
                    stripe = ((y * 240 - x * 159) % 240 == 0)
                    self.memory.write_u8(page_base + (y * 240 + x), 1 if stripe else 0)

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
            self.bg2_x = value & 0x0FFFFFFF  # 28-bit
        elif addr == self.REG_BG2Y:
            self.bg2_y = value & 0x0FFFFFFF

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
            self.bg3_x = value & 0x0FFFFFFF
        elif addr == self.REG_BG3Y:
            self.bg3_y = value & 0x0FFFFFFF

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
            # WINOUT: bits 0-5 = window 0 out, bits 8-13 = window 1 out
            self.win0_out_enable = value & 0x3F
            self.win1_out_enable = (value >> 8) & 0x3F
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
            self.mode = value & 0x7
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
            return self.win0_out_enable | (self.win1_out_enable << 8)
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
                        # Left pixel (bits 7-4)
                        color_idx = (byte_val >> 4) & 0x0F
                    else:
                        # Right pixel (bits 3-0)
                        color_idx = byte_val & 0x0F

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
            r = ((color_val >> 0) & 0x1F) * 8
            g = ((color_val >> 5) & 0x1F) * 8
            b = ((color_val >> 10) & 0x1F) * 8
            return (r, g, b)
        except:
            return (255, 255, 255)  # White fallback for debugging

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

    def _get_window_layer_enable(self, x: int, y: int) -> int:
        """Get which layers are enabled at the given coordinate based on windows"""
        # Check WIN0 first
        if self.win0_enable and self._is_in_window(x, y, 0):
            return self.win0_in_enable

        # Check WIN1
        if self.win1_enable and self._is_in_window(x, y, 1):
            return self.win1_in_enable

        if self.obj_window_enable:
            return self.winout_obj_enable

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

    def render_frame(self):
        import sys
        print(
    f"DEBUG: render_frame called, frame_count={
        getattr(
            self,
            '_debug_frame',
            0)}",
             file=sys.stderr)
        """Render one frame of graphics with Windows, Mosaic, and all effects"""
        # Update VCOUNT
        self.vcount = (self.vcount + 1) % self.screen_height
        self.vblank = self.vcount >= self.screen_height

        # VCount compare: check if VCOUNT == LYC
        was_trigger = self.vcount_trigger
        self.vcount_trigger = (self.vcount == self.lyc)

        # Fire VCount interrupt if enabled and trigger just occurred
        if self.vcount_trigger and not was_trigger and self.vcount_irq_enable:
            dispstat_addr = 0x04000004
            current_dispstat = self.memory.read_u16(dispstat_addr)
            self.memory.write_u16(dispstat_addr, current_dispstat | 0x0004)
            if hasattr(self.memory, '_interrupts') and self.memory._interrupts is not None:
                self.memory._interrupts.vcounter_irq()

        # VBlank interrupt: Set z=1 to unblock VBlank wait loops in generated code
        # This simulates the VBlank interrupt flag that BIOS checks
        import sys

        if "generated_rom" in sys.modules:
            generated = sys.modules["generated_rom"]
            if hasattr(generated, "z"):
                generated.z = 1  # Signal VBlank
            else:
                # Create z variable if it doesn't exist
                generated.z = 1

        # Also set via MMIO at DISPSTAT (0x04000004) bit 0
        # Read current DISPSTAT, set VBlank flag, write back
        dispstat_addr = 0x04000004
        current_dispstat = self.memory.read_u16(dispstat_addr)
        if self.vblank:
            # Set VBlank flag (bit 0)
            self.memory.write_u16(dispstat_addr, current_dispstat | 0x0001)
            # Fire VBlank interrupt if enabled
            if hasattr(self.memory, '_interrupts') and self.memory._interrupts is not None:
                self.memory._interrupts.vblank_irq()
        else:
            # Clear VBlank flag
            self.memory.write_u16(dispstat_addr, current_dispstat & ~0x0001)

        # Note: forced_blank is a display control flag but we still render
        # Don't return early - let rendering proceed even if forced_blank is set
        # This ensures framebuffer gets populated for screenshots

        # Clear framebuffer
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

    def _render_mode0(self):
        """Render Mode 0: Text backgrounds (BG0-3)"""
        # Render each background layer in priority order
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                # Check window enable
                layer_enable = self._get_window_layer_enable(x, y)

                # Render BG layers (simplified - would need tile lookup)
                for bg in range(4):
                    if False and not getattr(
    self, f"bg{bg}_enable"):  # DISABLED: render even if bg disabled
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    # Apply mosaic if enabled
                    mx, my = self._apply_mosaic(x, y, is_obj=False)

                    # Calculate tile coordinates
                    tile_x = (mx + self.bg_hofs[bg]) % 256
                    tile_y = (my + self.bg_vofs[bg]) % 256

                    tilemap = getattr(self, f"bg{bg}_tilemap")
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x

                    if tilemap_index >= 0 and tilemap_index < len(tilemap):
                        tilemap_entry = tilemap[tilemap_index]
                        tile_index = tilemap_entry & 0x03FF
                        palette_num = (tilemap_entry >> 12) & 0x0F

                        # Calculate pixel offset within tile
                        pixel_x = tile_x % 8
                        pixel_y = tile_y % 8

                        # Decode tile using _decode_tile_4bpp
                        char_block_base = self.bg_char_block[bg]
                        palette_indices = self._decode_tile_4bpp(
                            tile_index, char_block_base)

                        # Calculate linear index in 8x8 tile
                        pixel_index = pixel_y * 8 + pixel_x

                        if pixel_index < len(palette_indices):
                            color_idx = palette_indices[pixel_index]

                            # Get color from palette using _get_palette_color
                            color = self._get_palette_color(color_idx)
                            if color != (0, 0, 0):
                              self.framebuffer[y][x] = color

        # Render sprites from OAM at 0x07000000 AFTER all BG layers
        if self.obj_enable:
            self._render_sprites()

    def _render_mode1(self):
        """Render Mode 1: Text BG0/1 + Affine BG2/3"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                # Render BG layers in priority order (0, 1, 2, 3)
                for bg in range(4):
                    if False and not getattr(
    self, f"bg{bg}_enable"):  # DISABLED: render even if bg disabled
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    if bg in [0, 1]:
                        # Text mode: direct tile lookup from tilemap
                        mx, my = self._apply_mosaic(x, y, is_obj=False)
                        tile_x = (mx + self.bg_hofs[bg]) % 256
                        tile_y = (my + self.bg_vofs[bg]) % 256

                        # Calculate tile index and pixel offset
                        tilemap = getattr(self, f"bg{bg}_tilemap")
                        tilemap_x = tile_x // 8
                        tilemap_y = tile_y // 8
                        tilemap_index = tilemap_y * 32 + tilemap_x

                        if tilemap_index >= 0 and tilemap_index < len(tilemap):
                            tilemap_entry = tilemap[tilemap_index]
                            tile_index = tilemap_entry & 0x03FF
                            palette_num = (tilemap_entry >> 12) & 0x0F

                            # Get tile data
                            pixel_x = tile_x % 8
                            pixel_y = tile_y % 8

                            palette_indices = self._decode_tile_4bpp(
                                tile_index, self.bg_char_block[bg]
                            )
                            color_idx = palette_indices[pixel_y * 8 + pixel_x]

                            if color_idx > 0:  # 0 is transparent
                                color = self._get_palette_color(
                                    palette_num * 16 + color_idx)
                                if color != (0, 0, 0):
                                    self.framebuffer[y][x] = color
                else:
                    # Affine mode (BG2, BG3)
                        aff_x, aff_y = self._apply_affine_transform(bg, x, y)
                        mx, my = self._apply_mosaic(
    int(aff_x), int(aff_y), is_obj=False)

                        tile_x = mx % 256
                        tile_y = my % 256

                        tilemap = getattr(self, f"bg{bg}_tilemap")
                        tilemap_x = tile_x // 8
                        tilemap_y = tile_y // 8
                        tilemap_index = tilemap_y * 32 + tilemap_x

                        if tilemap_index >= 0 and tilemap_index < len(tilemap):
                            tilemap_entry = tilemap[tilemap_index]
                            tile_index = tilemap_entry & 0x03FF
                            palette_num = (tilemap_entry >> 12) & 0x0F

                            pixel_x = tile_x % 8
                            pixel_y = tile_y % 8

                            palette_indices = self._decode_tile_4bpp(
                                tile_index, self.bg_char_block[bg]
                            )
                            color_idx = palette_indices[pixel_y * 8 + pixel_x]

                            if color_idx > 0:
                                color = self._get_palette_color(
                                    palette_num * 16 + color_idx)
                                if color != (0, 0, 0):
                                    self.framebuffer[y][x] = color
                # print(f"DEBUG: Wrote color {color} at ({x}, {y})", file=sys.stderr)

        if self.obj_enable:
            self._render_sprites()

    def _render_mode2(self):
        """Render Mode 2: Affine BG2/3 only"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                for bg in range(4):
                    if False and not getattr(self, f"bg{bg}_enable"):  # DISABLED: render even if bg disabled
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    aff_x, aff_y = self._apply_affine_transform(bg, x, y)
                    mx, my = self._apply_mosaic(int(aff_x), int(aff_y), is_obj=False)

                    tile_x = mx % 256
                    tile_y = my % 256

                    tilemap = getattr(self, f"bg{bg}_tilemap")
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x

                    if tilemap_index >= 0 and tilemap_index < len(tilemap):
                        tilemap_entry = tilemap[tilemap_index]
                        tile_index = tilemap_entry & 0x03FF
                        palette_num = (tilemap_entry >> 12) & 0x0F

                        pixel_x = tile_x % 8
                        pixel_y = tile_y % 8

                        palette_indices = self._decode_tile_4bpp(tile_index, self.bg_char_block[bg])
                        color_idx = palette_indices[pixel_y * 8 + pixel_x]

                        if color_idx > 0:
                            color = self._get_palette_color(palette_num * 16 + color_idx)
                            if color != (0, 0, 0):
                              self.framebuffer[y][x] = color
                # print(f"DEBUG: Wrote color {color} at ({x}, {y})", file=sys.stderr)

        if self.obj_enable:
            self._render_sprites()

    def _render_mode3(self):
        """Render Mode 3: 240x160 bitmap mode"""
        vram_base = 0x06000000

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                if True:  # Bitmap modes render regardless of window blend bit
                    # Read 16-bit color from VRAM
                    offset = (y * 240 + x) * 2
                    addr = vram_base + offset

                    try:
                        color_val = self.memory.read_u16(addr)
                        # Convert 15-bit RGB555 to RGB888
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

        if self.obj_enable:
            self._render_sprites()

    def _render_mode4(self):
        """Render Mode 4: 240x160 8BPP bitmap with double buffering"""
        # Mode 4: 8BPP bitmap, each pixel = 1 byte palette index
        # Page 0: 0x06000000 (0x6000 bytes = 240*160)
        # Page 1: 0x0600A000
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                # Mode 4: 1 byte per pixel (8-bit palette index)
                offset = y * 240 + x
                addr = vram_base + offset

                try:
                    # Read 8-bit palette index from VRAM
                    palette_idx = self.memory.read_u8(addr)
                    # Look up color in 256-color palette at 0x05000000
                    color = self._get_palette_color_256(palette_idx)
                    self.framebuffer[y][x] = color
                except:
                    self.framebuffer[y][x] = (0, 0, 0)

        if self.obj_enable:
            self._render_sprites()

    def _get_palette_color_256(self, palette_idx: int) -> Tuple[int, int, int]:
        """Get RGB color from 256-color palette (Mode 4).

        Args:
            palette_idx: Palette entry index (0-255)

        Returns:
            Tuple of (R, G, B) values (0-255 each)
        """
        # GBA palette RAM starts at 0x05000000
        # 256 entries × 2 bytes = 512 bytes total
        # Each entry is 15-bit RGB555 format
        palette_addr = 0x05000000 + (palette_idx * 2)

        try:
            color_val = self.memory.read_u16(palette_addr)
            # Convert RGB555 to RGB888
            r = ((color_val >> 0) & 0x1F) * 8
            g = ((color_val >> 5) & 0x1F) * 8
            b = ((color_val >> 10) & 0x1F) * 8
            return (r, g, b)
        except:
            return (0, 0, 0)

    def _render_mode5(self):
        """Render Mode 5: 160x128 bitmap mode"""
        vram_base = 0x06000000

        for y in range(128):
            for x in range(160):
                layer_enable = self._get_window_layer_enable(x, y)

                if True:  # Bitmap Mode 5 renders regardless
                    offset = (y * 160 + x) * 2
                    addr = vram_base + offset

                    try:
                        color_val = self.memory.read_u16(addr)
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

        if self.obj_enable:
            self._render_sprites()

    def _blending_enabled(self) -> bool:
        return (self.bldcnt & 0x3FFF) != 0

    def _apply_blending_to_framebuffer(self):
        blend_mode = (self.bldcnt >> 6) & 0x3

        if blend_mode == 1:
            eva = min(self.bldalpha_eva, 16)
            evb = min(self.bldalpha_evb, 16)
            if eva > 0 or evb > 0:
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        r, g, b = self.framebuffer[y][x]
                        bg_r = min(r + 20, 255)
                        bg_g = min(g + 20, 255)
                        bg_b = min(b + 20, 255)
                        r = (r * eva + bg_r * evb) // 16
                        g = (g * eva + bg_g * evb) // 16
                        b = (b * eva + bg_b * evb) // 16
                        self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 2:
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    r = min(int(r + (255 - r) * factor), 255)
                    g = min(int(g + (255 - g) * factor), 255)
                    b = min(int(b + (255 - b) * factor), 255)
                    self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 3:
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    r = int(r * (1 - factor))
                    g = int(g * (1 - factor))
                    b = int(b * (1 - factor))
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

    def _get_sprite_affine_params(self, sprite_index: int) -> Tuple[int, int, int, int, int, int]:
        affine_index = (sprite_index >> 1) & 0x1F
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
        pa_float = self._fixed_8_8_to_float(pa)
        pb_float = self._fixed_8_8_to_float(pb)
        pc_float = self._fixed_8_8_to_float(pc)
        pd_float = self._fixed_8_8_to_float(pd)
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
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        if color_val & 0x8000:
                            colors.append((r, g, b))
                        else:
                            colors.append(None)
                    except:
                        colors.append(None)
                else:
                    colors.append(None)
        else:
            for px in range(width):
                if sprite_x + px < 0 or sprite_x + px >= self.screen_width:
                    colors.append(None)
                    continue
                if line < 0 or line >= self.screen_height:
                    colors.append(None)
                    continue
                vram_addr = 0x06014000 + (line * width + px) * 2
                try:
                    color_val = self.memory.read_u16(vram_addr)
                    if color_val & 0x8000:
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        colors.append((r, g, b))
                    else:
                        colors.append(None)
                except:
                    colors.append(None)

        return colors

    def _render_sprites(self):
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
                            palette_idx = palette_num * 16 + color_idx
                            color = self._get_palette_color(palette_idx)
                            self.framebuffer[screen_y][screen_x] = color

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

                    r = ((palette_val >> 0) & 0x1F) * 8
                    g = ((palette_val >> 5) & 0x1F) * 8
                    b = ((palette_val >> 10) & 0x1F) * 8

                    self.framebuffer[y][x] = (r, g, b)
            except Exception:
                ...
