"""GBA PPU (Pixel Processing Unit) - Graphics rendering"""

import struct
import os
from typing import Optional, List, Tuple


class PPU:
    """Game Boy Advance Pixel Processing Unit"""

    def oam_write(self, offset: int, value: int):
        """Write to OAM buffer at given offset (0x07000000 base address stripped)

        Args:
            offset: Offset from 0x07000000 (0-1023 for 1KB OAM)
            value: 16-bit value to write
        """
        if 0 <= offset < len(self.oam):
            self.oam[offset] = value & 0xFF
            if offset + 1 < len(self.oam):
                self.oam[offset + 1] = (value >> 8) & 0xFF

    def parse_oam(self):
        """Parse OAM entries from OAM buffer and decode sprite attributes.

        Each sprite has 3 attributes (8 bytes total):
        - Attribute 0 (2 bytes): Y position, shape, mode, priority, mosaic
        - Attribute 1 (2 bytes): X position, size, tile index, flags
        - Attribute 2 (2 bytes): Priority, palette number, tile number

        Returns:
            List of sprite dictionaries with decoded attributes
        """
        self.sprite_list = []
        self.sprite_count = 0

        for i in range(128):
            base_offset = i * 8

            attr0 = self.oam[base_offset] | (self.oam[base_offset + 1] << 8)
            attr1 = self.oam[base_offset + 2] | (self.oam[base_offset + 3] << 8)
            attr2 = self.oam[base_offset + 4] | (self.oam[base_offset + 5] << 8)

            y = attr0 & 0xFF
            x = (attr1 >> 8) & 0x1FF
            shape = (attr0 >> 6) & 0x3
            size = (attr1 >> 14) & 0x3

            width, height = self.SPRITE_SIZES.get((shape, size), (8, 8))

            sprite = {
                "index": i,
                "y": y,
                "x": x,
                "attr0": attr0,
                "attr1": attr1,
                "attr2": attr2,
                "shape": shape,
                "size": size,
                "width": width,
                "height": height,
                "mode": (attr0 >> 8) & 0x3,
                "mosaic": bool((attr0 >> 12) & 1),
                "color_mode": bool((attr1 >> 12) & 1),
                "rotate_scale": bool((attr1 >> 11) & 1),
                "tile_num": attr2 & 0x3FF,
                "palette": (attr2 >> 9) & 0x1F,
                "priority": (attr2 >> 10) & 0x3,
                "hflip": bool((attr1 >> 12) & 1),
                "vflip": bool((attr1 >> 13) & 1),
            }

            if y < 240 and x < 512:
                self.sprite_list.append(sprite)
                self.sprite_count += 1

        return self.sprite_list

    def decode_sprite_tile(self, sprite_index: int) -> List[int]:
        """Decode a sprite tile into pixel palette indices.

        Args:
            sprite_index: Index of the sprite in sprite_list (0-based)

        Returns:
            List of 64 palette indices (0-15) for each pixel in row-major order,
            or empty list if sprite not found
        """
        # Get sprite from parsed OAM data
        if not hasattr(self, "sprite_list") or sprite_index >= len(self.sprite_list):
            return []

        sprite = self.sprite_list[sprite_index]

        # Extract tile number and palette from attribute 2
        # Tile number: bits 0-9 (10 bits, max 1023)
        # Palette number: bits 10-15 (6 bits, but only lower 5 used)
        tile_num = sprite.get("tile_num", sprite["attr2"] & 0x3FF)
        palette_num = sprite.get("palette", (sprite["attr2"] >> 9) & 0x1F)

        # Get flip flags from attribute 1
        hflip = sprite.get("hflip", bool((sprite["attr1"] >> 12) & 1))
        vflip = sprite.get("vflip", bool((sprite["attr1"] >> 13) & 1))

        # Look up tile data from tiles_4bpp
        # tiles_4bpp contains 128 tiles × 16 bytes each (64 pixels × 4 bits)
        # Each tile is 8×8 = 64 pixels
        if not hasattr(self, "tiles_4bpp") or not self.tiles_4bpp:
            # If tiles_4bpp not populated, return empty list
            return []

        # Get the tile data (list of 64 palette indices)
        if tile_num >= len(self.tiles_4bpp):
            return []

        tile_data = self.tiles_4bpp[tile_num]

        # Apply palette offset to each pixel (add 16 * palette_num for OBJ palette)
        # OBJ palette starts at index 256 in the full palette
        palette_offset = 16 * palette_num

        # Apply horizontal and vertical flip if needed
        decoded_pixels = []
        for py in range(8):
            for px in range(8):
                # Apply flip transformations
                if hflip:
                    src_x = 7 - px
                else:
                    src_x = px

                if vflip:
                    src_y = 7 - py
                else:
                    src_y = py

                # Calculate source index in tile data
                src_index = src_y * 8 + src_x

                if src_index < len(tile_data):
                    pixel_idx = tile_data[src_index]
                    # Apply palette offset (pixel index 0 = transparent, keep as 0)
                    if pixel_idx > 0:
                        pixel_idx = pixel_idx + palette_offset
                    decoded_pixels.append(pixel_idx)
                else:
                    decoded_pixels.append(0)

        return decoded_pixels

    def render_sprites(self):
        for sprite in self.sprite_list:
            attr0 = sprite["attr0"]
            attr1 = sprite["attr1"]
            attr2 = sprite["attr2"]

            y = attr0 & 0xFF
            x = (attr1 >> 8) & 0x1FF
            shape = (attr0 >> 6) & 0x3
            size = (attr1 >> 14) & 0x3
            mosaic = (attr1 >> 13) & 0x1
            color_mode = (attr1 >> 12) & 0x1
            rotate_scale = (attr1 >> 11) & 0x1
            mode = (attr0 >> 8) & 0x3
            palette = (attr2 >> 9) & 0x1F
            tile_num = attr2 & 0x3FF
            priority = (attr2 >> 10) & 0x3

            if mode == 1 or mode == 2:
                continue

            tile_addr = 0x06000000 + (tile_num * 32)

            for py in range(8):
                for px in range(8):
                    tile_x = px
                    tile_y = py
                    pixel = self.memory.read_u8(tile_addr + tile_y * 4 + tile_x // 2)
                    if tile_x % 2 == 1:
                        pixel = (pixel >> 4) & 0xF
                    else:
                        pixel = pixel & 0xF

                    if pixel != 0:
                        screen_x = x + px
                        screen_y = y + py
                        if 0 <= screen_x < 240 and 0 <= screen_y < 160:
                            color_addr = 0x05000000 + (palette * 16) + (pixel * 2)
                            color = self.memory.read_u16(color_addr)
                            fb_addr = screen_y * 240 * 2 + screen_x * 2
                            current = self.memory.read_u16(0x06000000 + fb_addr)
                            if (current >> 15) == 0:
                                self.memory.write_u16(0x06000000 + fb_addr, color)

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

        # GBA VRAM buffers (96KB total: 0x06000000-0x06017FFF)
        # VRAM stores: tiles, tilemaps, and bitmap framebuffer
        self.vram = bytearray(96 * 1024)  # 96KB VRAM buffer

        # Tile buffers (128 tiles × 16 bytes each for 4BPP = 2KB)
        self.tile_buffer = bytearray(128 * 16)

        # Palette buffer (512 colors × 2 bytes each = 1KB)
        self.palette_buffer = bytearray(512 * 2)

        # Tilemap buffer (4KB for text mode tilemaps)
        self.tilemap_buffer = bytearray(4096)

        # OAM (Object Attribute Memory) - 1KB for 128 sprites × 8 bytes each
        # GBA OAM address: 0x07000000-0x070003FF
        self.oam = bytearray(1024)  # 128 sprites × 8 bytes = 1024 bytes
        self.sprite_count = 0
        self.sprite_list = []  # List of decoded sprite objects

        # Sprite size tables (shape × size = dimensions in pixels)
        # Shape: 0=square, 1=horizontal, 2=vertical, 3=prohibited
        # Size: 0=small, 1=medium, 2=large, 3=extra-large
        self.SPRITE_SIZES = {
            # Square sizes
            (0, 0): (8, 8),
            (0, 1): (16, 16),
            (0, 2): (32, 32),
            (0, 3): (64, 64),
            # Horizontal rectangle sizes
            (1, 0): (16, 8),
            (1, 1): (32, 8),
            (1, 2): (32, 16),
            (1, 3): (64, 32),
            # Vertical rectangle sizes
            (2, 0): (8, 16),
            (2, 1): (8, 32),
            (2, 2): (16, 32),
            (2, 3): (32, 64),
        }

        # Asset storage (for runtime tilemap/palette/sprite data)
        self.palette_bg = []
        self.tiles_4bpp = []
        self.bg0_tilemap = [0] * 1024
        self.bg1_tilemap = [0] * 1024
        self.bg2_tilemap = [0] * 1024
        self.bg3_tilemap = [0] * 1024
        self.sprites = []

        # Display control
        self.mode = 0
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

    def dispcnt_write(self, value: int):
        """Write to DISPCNT register (0x04000000).

        Args:
            value: 16-bit display control value
        """
        self.mode = value & 0x07
        self.display_frame_select = (value >> 7) & 1
        self.hblank_interval_free = (value >> 8) & 1
        self.obj_character_vram_mapping = (value >> 9) & 1
        self.forced_blank = (value >> 10) & 1
        self.bg0_enable = (value >> 11) & 1
        self.bg1_enable = (value >> 12) & 1
        self.bg2_enable = (value >> 13) & 1
        self.bg3_enable = (value >> 14) & 1
        self.obj_enable = (value >> 15) & 1

    def bg0_cnt_write(self, value: int):
        """Write to BG0CNT register (0x04000008).

        Args:
            value: 16-bit background control value
        """
        self.bg_priority[0] = value & 0x03
        self.bg_char_block[0] = (value >> 2) & 0x1F
        self.bg_mosaic[0] = bool((value >> 6) & 1)
        self.bg_size[0] = (value >> 7) & 0x03
        self.bg_palette_enable[0] = bool((value >> 12) & 1)

    def bg1_cnt_write(self, value: int):
        """Write to BG1CNT register (0x0400000A)."""
        self.bg_priority[1] = value & 0x03
        self.bg_char_block[1] = (value >> 2) & 0x1F
        self.bg_mosaic[1] = bool((value >> 6) & 1)
        self.bg_size[1] = (value >> 7) & 0x03
        self.bg_palette_enable[1] = bool((value >> 12) & 1)

    def bg2_cnt_write(self, value: int):
        """Write to BG2CNT register (0x0400000C)."""
        self.bg_priority[2] = value & 0x03
        self.bg_char_block[2] = (value >> 2) & 0x1F
        self.bg_mosaic[2] = bool((value >> 6) & 1)
        self.bg_size[2] = (value >> 7) & 0x03
        self.bg_palette_enable[2] = bool((value >> 12) & 1)

    def bg3_cnt_write(self, value: int):
        """Write to BG3CNT register (0x0400000E)."""
        self.bg_priority[3] = value & 0x03
        self.bg_char_block[3] = (value >> 2) & 0x1F
        self.bg_mosaic[3] = bool((value >> 6) & 1)
        self.bg_size[3] = (value >> 7) & 0x03
        self.bg_palette_enable[3] = bool((value >> 12) & 1)

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

        # Blending mode flags
        self.blend_enable = False
        self.blend_mode = 0  # 0=off, 1=alpha, 2=additive, 3=subtract
        self.blend_alpha = 0xFF  # Alpha value 0-255 for blending

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
        self.win0_in_enable = 0
        self.win0_out_enable = 0
        self.win1_in_enable = 0
        self.win1_out_enable = 0
        self.win_obj_enable = 0

        self.window_enabled = False

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

        # Framebuffer
        self.framebuffer: List[List[Tuple[int, int, int]]] = []
        self._init_framebuffer()

    def vram_write(self, offset: int, value: int):
        """Write to VRAM buffer at given offset (0x06000000 base address stripped)

        Args:
            offset: Offset from 0x06000000 (0-98303 for 96KB VRAM)
            value: 16-bit value to write
        """
        if 0 <= offset < len(self.vram):
            self.vram[offset] = value & 0xFF
            self.vram[offset + 1] = (value >> 8) & 0xFF

    def get_surface(self) -> "pygame.Surface":
        """Convert framebuffer to pygame Surface for screenshot"""
        import pygame

        surf = pygame.Surface((self.screen_width, self.screen_height))
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                color = self.framebuffer[y][x]
                surf.set_at((x, y), color)
        return surf

    def render_mode0(self) -> "pygame.Surface":
        """Render Mode 0: 4 text background layers (BG0-BG3).

        Reads DISPCNT to determine which BG layers are enabled.
        For each enabled BG:
        - Reads tilemap from VRAM (based on BG screen block)
        - For each tile position (32×32 grid):
          - Gets tile index from tilemap
          - Reads 8×8 tile data from VRAM (tile bank)
          - Looks up palette from palette RAM
        - Renders to pygame Surface and returns it.

        Layer priority: BG0 (highest) to BG3 (lowest). Higher priority
        BG overwrites lower priority pixels (except palette index 0 = transparent).

        Returns:
            pygame.Surface: 240x160 surface with rendered backgrounds
        """
        import pygame

        width = 240
        height = 160
        surf = pygame.Surface((width, height))

        # Check which BG layers are enabled via DISPCNT
        bg_enabled = [
            self.bg0_enable,
            self.bg1_enable,
            self.bg2_enable,
            self.bg3_enable,
        ]

        # Render each pixel
        for y in range(height):
            for x in range(width):
                color = None

                # Render BG layers in priority order (BG0 = highest priority)
                for bg in range(4):
                    if not bg_enabled[bg]:
                        continue

                    # Apply scroll offsets
                    tile_x = (x + self.bg_hofs[bg]) % 256
                    tile_y = (y + self.bg_vofs[bg]) % 256

                    # Get tilemap for this BG
                    tilemap = getattr(self, f"bg{bg}_tilemap")
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x

                    if tilemap_index >= 0 and tilemap_index < len(tilemap):
                        tilemap_entry = tilemap[tilemap_index]
                        tile_index = tilemap_entry & 0x03FF
                        palette_num = (tilemap_entry >> 12) & 0x0F

                        # Get pixel position within tile
                        pixel_x = tile_x % 8
                        pixel_y = tile_y % 8

                        # Decode tile (4BPP = 8x8 pixels, 4 bits per pixel)
                        char_block_base = self.bg_char_block[bg]
                        palette_indices = self._decode_tile_4bpp(tile_index, char_block_base)
                        pixel_index = pixel_y * 8 + pixel_x

                        if pixel_index < len(palette_indices):
                            color_idx = palette_indices[pixel_index]

                            # Palette index 0 is transparent
                            if color_idx > 0:
                                # Get color from palette (BG palette starts at 0x05000000)
                                # Each BG has 16 colors in its palette bank
                                palette_addr = 0x05000000 + (palette_num * 16 + color_idx) * 2

                                try:
                                    color_val = self.memory.read_u16(palette_addr)
                                    r = ((color_val >> 0) & 0x1F) * 8
                                    g = ((color_val >> 5) & 0x1F) * 8
                                    b = ((color_val >> 10) & 0x1F) * 8
                                    color = (r, g, b)
                                except:
                                    pass

                    # If we got a non-transparent pixel, stop (higher priority BG)
                    if color is not None:
                        break

                # Default to black if no BG rendered
                if color is None:
                    color = (0, 0, 0)

                surf.set_at((x, y), color)

        # Render background sprites (priority=0) on top of all BG layers
        self._render_bg_sprites(surf)

        # Render foreground sprites (priority>0) on top of background sprites
        self._render_fg_sprites(surf)

        # Apply OBJ mosaic to final surface
        self._apply_mosaic_to_surface(surf, is_obj=True)

        return surf

    def _render_bg_sprites(self, surf: "pygame.Surface"):
        """Render sprites with priority=0 (background sprites) on top of backgrounds.

        These sprites render behind all background layers with higher priority.
        Sprite transparency: palette index 0 is transparent.
        """
        if not self.obj_enable:
            return

        # Parse OAM to get sprite list
        sprites = self.parse_oam()

        # Filter sprites with priority=0 (background sprites)
        bg_sprites = [s for s in sprites if s.get("priority", 0) == 0]

        for sprite in bg_sprites:
            x = sprite.get("x", 0)
            y = sprite.get("y", 0)
            width = sprite.get("width", 8)
            height = sprite.get("height", 8)
            sprite_idx = sprite.get("index", 0)

            # Get decoded sprite tile pixels
            sprite_pixels = self.decode_sprite_tile(sprite_idx)

            if not sprite_pixels:
                continue

            # Draw sprite pixels onto surface
            for py in range(height):
                for px in range(width):
                    # Calculate source pixel index
                    src_idx = py * width + px
                    if src_idx >= len(sprite_pixels):
                        break

                    pixel_idx = sprite_pixels[src_idx]

                    # Skip transparent pixels (palette index 0)
                    if pixel_idx == 0:
                        continue

                    # Calculate screen position (with wrapping for off-screen sprites)
                    screen_x = (x + px) % 512
                    screen_y = (y + py) % 256

                    # Clip to screen boundaries
                    if screen_x >= self.screen_width or screen_y >= self.screen_height:
                        continue

                    # Get color from OBJ palette (starts at 0x05000200 = palette index 256)
                    # pixel_idx already has palette offset applied in decode_sprite_tile
                    palette_addr = 0x05000200 + (pixel_idx * 2)

                    try:
                        color_val = self.memory.read_u16(palette_addr)
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        src_color = (r, g, b)
                        if self.blend_enable and self.blend_mode != 0:
                            dst_color = surf.get_at((screen_x, screen_y))
                            final_color = self._apply_blending(src_color, dst_color)
                        else:
                            final_color = src_color
                        surf.set_at((screen_x, screen_y), final_color)
                    except:
                        pass

    def _render_fg_sprites(self, surf: "pygame.Surface"):
        """Render sprites with priority>0 (foreground sprites) on top of backgrounds.

        These sprites render after all background layers and priority=0 sprites.
        Higher priority values (1, 2, 3) render on top of lower priority sprites.
        Sprite transparency: palette index 0 is transparent.
        """
        if not self.obj_enable:
            return

        # Parse OAM to get sprite list
        sprites = self.parse_oam()

        # Filter sprites with priority>0 (foreground sprites)
        fg_sprites = [s for s in sprites if s.get("priority", 0) > 0]

        # Sort by priority (lower priority values render first, higher on top)
        fg_sprites.sort(key=lambda s: s.get("priority", 0))

        for sprite in fg_sprites:
            x = sprite.get("x", 0)
            y = sprite.get("y", 0)
            width = sprite.get("width", 8)
            height = sprite.get("height", 8)
            sprite_idx = sprite.get("index", 0)

            # Get decoded sprite tile pixels
            sprite_pixels = self.decode_sprite_tile(sprite_idx)

            if not sprite_pixels:
                continue

            # Draw sprite pixels onto surface
            for py in range(height):
                for px in range(width):
                    # Calculate source pixel index
                    src_idx = py * width + px
                    if src_idx >= len(sprite_pixels):
                        break

                    pixel_idx = sprite_pixels[src_idx]

                    # Skip transparent pixels (palette index 0)
                    if pixel_idx == 0:
                        continue

                    # Calculate screen position (with wrapping for off-screen sprites)
                    screen_x = (x + px) % 512
                    screen_y = (y + py) % 256

                    # Clip to screen boundaries
                    if screen_x >= self.screen_width or screen_y >= self.screen_height:
                        continue

                    # Get color from OBJ palette (starts at 0x05000200 = palette index 256)
                    # pixel_idx already has palette offset applied in decode_sprite_tile
                    palette_addr = 0x05000200 + (pixel_idx * 2)

                    try:
                        color_val = self.memory.read_u16(palette_addr)
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        src_color = (r, g, b)
                        if self.blend_enable and self.blend_mode != 0:
                            dst_color = surf.get_at((screen_x, screen_y))
                            final_color = self._apply_blending(src_color, dst_color)
                        else:
                            final_color = src_color
                        surf.set_at((screen_x, screen_y), final_color)
                    except:
                        pass

    def render_mode3(self) -> "pygame.Surface":
        """Render Mode 3: 240x160 direct bitmap mode.

        Reads VRAM as bitmap data (RGB555 format, 2 bytes per pixel).
        Creates pygame Surface from framebuffer and returns it.

        VRAM layout: 240×160 pixels × 2 bytes = 76,800 bytes
        Pixel format: RGB555 (5 bits per channel: R:0-4, G:5-9, B:10-14)
        Byte order: little-endian (low byte first)

        Returns:
            pygame.Surface: 240x160 surface with converted RGB888 pixels
        """
        import pygame

        # Mode 3: 240x160 bitmap at VRAM base
        width = 240
        height = 160
        vram_base = 0x06000000

        # Create pygame Surface
        surf = pygame.Surface((width, height))

        # Read bitmap data from VRAM and convert to surface
        for y in range(height):
            for x in range(width):
                # Calculate offset in VRAM (row-major, 2 bytes per pixel)
                offset = (y * width + x) * 2
                addr = vram_base + offset

                try:
                    # Read 16-bit RGB555 color from memory
                    color_val = self.memory.read_u16(addr)

                    # Extract RGB555 components and expand to RGB888
                    # Format: 0bBBBBBGGGGGRRRRR (5 bits each, 1 unused bit)
                    r5 = (color_val >> 0) & 0x1F  # Bits 0-4
                    g5 = (color_val >> 5) & 0x1F  # Bits 5-9
                    b5 = (color_val >> 10) & 0x1F  # Bits 10-14

                    # Scale 5-bit (0-31) to 8-bit (0-255): multiply by 8 (or 255/31 ≈ 8.225)
                    r = r5 * 8
                    g = g5 * 8
                    b = b5 * 8

                    surf.set_at((x, y), (r, g, b))
                except Exception:
                    # Default to black on error
                    surf.set_at((x, y), (0, 0, 0))

        return surf

    def _init_framebuffer(self):
        """Initialize the framebuffer"""
        self.framebuffer = [
            [(0, 0, 0) for _ in range(self.screen_width)] for _ in range(self.screen_height)
        ]

    def parse_tiles_4bpp(self):
        """Parse 4BPP tiles from VRAM buffer

        Reads 128 tiles × 16 bytes each from VRAM and decodes to pixel indices.
        Each tile is 8×8 pixels (64 pixels), 2 pixels per nibble (4 bits).

        Returns:
            List of 128 tiles, each tile is a list of 64 color indices (0-15)
        """
        self.decoded_tiles = []

        for tile_num in range(128):
            tile_data = []
            tile_offset = tile_num * 16  # 16 bytes per 4BPP tile

            for byte_idx in range(16):
                byte_val = self.vram[tile_offset + byte_idx]
                # Extract 2 pixels per byte (4 bits each)
                for pixel_idx in range(2):
                    pixel = (byte_val >> (4 * pixel_idx)) & 0xF
                    tile_data.append(pixel)

            self.decoded_tiles.append(tile_data)

        return self.decoded_tiles

    def parse_palette(self):
        """Parse palette data from VRAM buffer

        Reads 512 colors × 2 bytes each from VRAM palette area and decodes to RGB.
        GBA palette format: 16-bit RGB555 (5 bits per channel, 1 bit unused)

        Returns:
            List of 512 RGB tuples with 8-bit channels
        """
        self.decoded_palette = []

        for color_idx in range(512):
            # Palette is stored as 16-bit little-endian values
            offset = color_idx * 2
            color_val = self.vram[offset] | (self.vram[offset + 1] << 8)

            # Extract RGB555 components (5 bits each)
            blue = color_val & 0x1F
            green = (color_val >> 5) & 0x1F
            red = (color_val >> 10) & 0x1F

            # Expand from 5-bit to 8-bit (scale 0-31 to 0-255)
            red_8bit = (red * 255) // 31
            green_8bit = (green * 255) // 31
            blue_8bit = (blue * 255) // 31

            self.decoded_palette.append((red_8bit, green_8bit, blue_8bit))

        return self.decoded_palette

    def parse_tilemap(self):
        """Parse tilemap data from VRAM buffer

        Reads 1024 tile entries × 2 bytes each from VRAM tilemap area.
        GBA tilemap format: 32×32 grid = 1024 entries, each 2 bytes
        Each entry: bits 0-9 = tile index, bits 10-13 = palette bank, bits 14-15 = attributes

        Returns:
            List of 1024 tile indices (0-1023)
        """
        self.decoded_tilemap = []

        # Tilemap starts after palette data (palette = 1024 bytes = 0x400)
        tilemap_offset = 0x400  # 1024 bytes = 512 colors × 2 bytes

        for entry_idx in range(1024):
            # Tilemap entries are 2 bytes each, little-endian
            offset = tilemap_offset + (entry_idx * 2)
            entry = self.vram[offset] | (self.vram[offset + 1] << 8)

            # Extract tile index (lower 10 bits)
            tile_index = entry & 0x3FF

            self.decoded_tilemap.append(tile_index)

        return self.decoded_tilemap

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
            self.blend_enable = bool((value >> 8) & 0x1)
            self.blend_mode = (value >> 9) & 0x3
        elif addr == self.REG_BLDALPHA:
            self.bldalpha_eva = value & 0x1F
            self.bldalpha_evb = (value >> 8) & 0x1F
            eva = self.bldalpha_eva / 16.0
            evb = self.bldalpha_evb / 16.0
            self.blend_alpha = int((eva + evb) * 255)
        elif addr == self.REG_BLDY:
            self.bldy = value & 0x1F
            if self.blend_mode == 2:
                self.blend_alpha = int(self.bldy / 16.0 * 255)

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
            self.window_enabled = self.win0_enable or self.win1_enable

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

        return 0

    def _read_bg_control(self, bg_num: int) -> int:
        """Read BG control register"""
        if bg_num < 0 or bg_num > 3:
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

    def _decode_tile_4bpp(self, tile_index: int, char_block_base: int) -> List[int]:
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

    def _apply_affine_transform(self, bg_num: int, x: int, y: int) -> Tuple[int, int]:
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

    def _apply_mosaic(self, x: int, y: int, is_obj: bool = False) -> Tuple[int, int]:
        """Convert screen coordinates to mosaic-adjusted source coordinates.

        For mosaic effect: sample from top-left corner of each NxN block.
        This returns the coordinates to read color from.
        """
        if not self.mosaic_enabled:
            return x, y

        if is_obj:
            h_size = self.obj_mosaic_h
            v_size = self.obj_mosaic_v
        else:
            h_size = self.bg_mosaic_h
            v_size = self.bg_mosaic_v

        # Snap to block origin
        mosaic_x = (x // h_size) * h_size
        mosaic_y = (y // v_size) * v_size

        return mosaic_x, mosaic_y

    def _apply_mosaic_to_surface(self, surf: "pygame.Surface", is_obj: bool = False):
        """Apply mosaic effect to a rendered surface by pixelating blocks.

        Reads color from each block's top-left corner and fills the block.
        """
        if not self.mosaic_enabled:
            return surf

        if is_obj:
            h_size = self.obj_mosaic_h
            v_size = self.obj_mosaic_v
        else:
            h_size = self.bg_mosaic_h
            v_size = self.bg_mosaic_v

        if h_size <= 1 and v_size <= 1:
            return surf

        width, height = surf.get_size()
        import pygame

        # Create a copy to read source colors from
        src_surf = surf.copy()

        # Iterate through blocks
        for block_y in range(0, height, v_size):
            for block_x in range(0, width, h_size):
                # Sample color from top-left corner of block
                sample_x = block_x
                sample_y = block_y

                if sample_x < width and sample_y < height:
                    color = src_surf.get_at((sample_x, sample_y))

                    # Fill the block with this color
                    for dy in range(v_size):
                        for dx in range(h_size):
                            px = block_x + dx
                            py = block_y + dy
                            if px < width and py < height:
                                surf.set_at((px, py), color)

        return surf

    def _apply_blending(
        self, src_color: Tuple[int, int, int], dst_color: Tuple[int, int, int]
    ) -> Tuple[int, int, int]:
        if not self.blend_enable or self.blend_mode == 0:
            return src_color

        if self.blend_mode == 1:
            alpha = self.blend_alpha / 255.0
            r = int(src_color[0] * alpha + dst_color[0] * (1 - alpha))
            g = int(src_color[1] * alpha + dst_color[1] * (1 - alpha))
            b = int(src_color[2] * alpha + dst_color[2] * (1 - alpha))
            return (min(255, r), min(255, g), min(255, b))
        elif self.blend_mode == 2:
            r = min(255, src_color[0] + dst_color[0])
            g = min(255, src_color[1] + dst_color[1])
            b = min(255, src_color[2] + dst_color[2])
            return (r, g, b)
        elif self.blend_mode == 3:
            r = max(0, src_color[0] - dst_color[0])
            g = max(0, src_color[1] - dst_color[1])
            b = max(0, src_color[2] - dst_color[2])
            return (r, g, b)

        return src_color

    def _is_in_window(self, x: int, y: int) -> bool:
        if not self.window_enabled:
            return False

        if self.win0_enable:
            if self.win0_left <= x < self.win0_right and self.win0_top <= y < self.win0_bottom:
                return True

        if self.win1_enable:
            if self.win1_left <= x < self.win1_right and self.win1_top <= y < self.win1_bottom:
                return True

        return False

    def render_frame(self):
        import sys

        print(
            f"DEBUG: render_frame called, frame_count={getattr(self, '_debug_frame', 0)}",
            file=sys.stderr,
        )
        """Render one frame of graphics with Windows, Mosaic, and all effects"""
        # Update VCOUNT
        self.vcount = (self.vcount + 1) % self.screen_height
        self.vblank = self.vcount >= self.screen_height

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
                        self, f"bg{bg}_enable"
                    ):  # DISABLED: render even if bg disabled
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
                        palette_indices = self._decode_tile_4bpp(tile_index, char_block_base)

                        # Calculate linear index in 8x8 tile
                        pixel_index = pixel_y * 8 + pixel_x

                        if pixel_index < len(palette_indices):
                            color_idx = palette_indices[pixel_index]

                            # Get color from palette using _get_palette_color
                            color = self._get_palette_color(color_idx)
                            if color != (0, 0, 0):
                                self.framebuffer[y][x] = color
                # Mode 3 rendering complete - framebuffer contains bitmap data

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
                        self, f"bg{bg}_enable"
                    ):  # DISABLED: render even if bg disabled
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
                                color = self._get_palette_color(palette_num * 16 + color_idx)
                                if color != (0, 0, 0):
                                    self.framebuffer[y][x] = color
                else:
                    # Affine mode (BG2, BG3)
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

    def _render_mode2(self):
        """Render Mode 2: Affine BG2/3 only"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                for bg in range(4):
                    if False and not getattr(
                        self, f"bg{bg}_enable"
                    ):  # DISABLED: render even if bg disabled
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
        """Render Mode 4: 240x160 bitmap with double buffering"""
        # Page 0: 0x06000000, Page 1: 0x0600A000
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                if True:  # Bitmap Mode 4 renders regardless
                    offset = (y * 240 + x) * 2
                    addr = vram_base + offset

                    try:
                        color_val = self.memory.read_u16(addr)
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

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
        window_active = self.window_enabled

        if blend_mode == 1:
            eva = min(self.bldalpha_eva, 16)
            evb = min(self.bldalpha_evb, 16)
            if eva > 0 or evb > 0:
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        if window_active and not self._is_in_window(x, y):
                            continue
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
                    if window_active and not self._is_in_window(x, y):
                        continue
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
                    if window_active and not self._is_in_window(x, y):
                        continue
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
