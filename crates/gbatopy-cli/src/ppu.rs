//! PPU (Picture Processing Unit) Generator
//! Generates embedded Python PPU class for GBA rendering
//! Implements Mode 0 (text backgrounds) and Mode 3 (bitmap)

/// Generate Python PPU class code as a string
pub fn generate_ppu_code() -> String {
    r#"
"""GBA PPU (Picture Processing Unit) - Pure Python implementation for GBAtoPy

This module handles GBA PPU rendering:
- Mode 0: 4 text backgrounds (160x160 pixels each, displayed as 240x160)
- Mode 3: Bitmap mode (320x160 pixels, scaled to 240x160)
- Mode 4: 8BPP bitmap mode (240x160 pixels, 1 byte per pixel)

The PPU reads from:
- VRAM (0x06000000): Tile data, tilemaps, bitmaps
- Palette RAM (0x05000000): 512x16-bit colors
- OAM (0x07000000): Sprite data

Rendering follows GBA timing:
- Mode 0: Text background (scanline mode)
- Mode 3: 16-bit bitmap background (BGR555)
- Mode 4: 8-bit palette bitmap (256-color)
"""

import pygame


# GBA Display Control Register
DISPCNT_BASE = 0x04000000
VRAM_BASE = 0x06000000
PALETTE_BASE = 0x05000000
OAM_BASE = 0x07000000

# Background enable bits
BG0_ENABLE = 0x01
BG1_ENABLE = 0x02
BG2_ENABLE = 0x04
BG3_ENABLE = 0x08

# Background control registers
BG0CNT = 0x04000008
BG1CNT = 0x0400000C

class PPU:
    """GBA Picture Processing Unit emulator"""
    
    def __init__(self, memory):
        """Initialize PPU with GBA memory object"""
        self.memory = memory
        self.screen = pygame.Surface((240, 160), pygame.SRCALPHA)
        # Use bytearray instead of numpy array for compatibility
        self.framebuffer = bytearray(160 * 240 * 3)  # 120KB for RGB pixels
        
        # Cache display control registers
        self.dispcnt = memory.read_32(DISPCNT_BASE)
        self.bg0cntl = memory.read_32(BG0CNT)
        self.bg0cnt2 = memory.read_32(BG0CNT + 4)  # Mode bits in upper 16 bits
        self.bg1cntl = memory.read_32(BG1CNT)
        self.bg1cnt2 = memory.read_32(BG1CNT + 4)
        
        # Pre-compute tilemap info for Mode 0
        self._parse_tilemaps()
        
        # Single background for Mode 3
        self.mode3_tilemap = bytearray(0x100)  # 32x16 tilemap for Mode 3
        self.mode3_tiles = bytearray(0x800)  # 40x32 tiles (4BPP)
        self.mode3_bitmap = bytearray(0x8000)  # 320x160 bitmap
        
        # Mode 4 double buffering page select
        self.display_frame_select = 0
        

    def _parse_tilemaps(self):
        """Parse tilemap metadata from DISPCNT and BGxCNT"""
        # Extract BG0 mode (lower 4 bits of BG0CNT)
        bg0_mode = (self.bg0cntl >> 0) & 0xF
        # Extract BG0 size (lower 4 bits of BG0CNT + 4)
        bg0_size = (self.bg0cnt2 >> 0) & 0xF
        
        # Force Mode 4 if DISPCNT is 0 (test ROMs don't set DISPCNT)
        # This is a workaround for test ROMs that don't enable display
        if self.dispcnt == 0:
            print("DISPCNT is 0, forcing Mode 4 for testing")
            self.dispcnt = 0x8004  # Mode 4 + Display Enable
        
        print(f"BG0 Mode: {bg0_mode}, Size: {bg0_size}")
        print(f"DISPCNT: 0x{self.dispcnt:08X}")
        
    def _get_palette_color(self, palette_idx):
        """Convert 16-bit palette index to RGB"""
        if palette_idx >= len(self.memory.palette) // 2:
            return (0, 0, 0)  # Black for out of bounds
        
        # 16-bit color: bit 15-10 = R, bit 9-4 = G, bit 3-0 = B
        addr = palette_idx * 2
        
        r = ((self.memory.palette[addr] << 8) | 
              (self.memory.palette[addr + 1])) >> 10 & 0x3F
        g = (self.memory.palette[addr] >> 4) & 0x3F
        b = (self.memory.palette[addr] >> 0) & 0x3F
        
        # Scale to 0-255
        return (r * 4, g * 4, b * 4)
    
    def _decode_tile_4bpp(self, tile_index, char_block_base):
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
                    byte_val = self.memory.read_8(byte_addr)

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
    
    def _render_mode0_text_background(self, bg_num):
        """Render text background Mode 0"""
        # Get BG control register address
        bg_cnt_addr = BG0CNT + bg_num * 4
        bg_cnt = self.memory.read_32(bg_cnt_addr)
        
        # Extract BG control fields
        # Bits 2-3: Character base block (tile data address >> 14)
        char_base = ((bg_cnt >> 2) & 0x3) * 0x4000
        # Bits 8-12: Screen base block (tilemap address >> 11)
        screen_base = ((bg_cnt >> 8) & 0x1F) * 0x800
        # Bits 14-15: Screen size (0=256x256, 1=512x256, 2=256x512, 3=512x512)
        screen_size = (bg_cnt >> 14) & 0x3
        
        # Calculate tilemap dimensions based on screen size
        if screen_size == 0:
            map_width = 32   # 256 pixels / 8 pixels per tile
            map_height = 32
        elif screen_size == 1:
            map_width = 64   # 512 pixels / 8
            map_height = 32
        elif screen_size == 2:
            map_width = 32
            map_height = 64
        else:  # screen_size == 3
            map_width = 64
            map_height = 64
        
        # Render visible area (240x160) but respect scroll offsets
        # For simplicity, start at origin (0,0) of the background
        for screen_y in range(160):
            for screen_x in range(240):
                # Calculate which tile in the tilemap this screen position corresponds to
                tile_x = screen_x // 8
                tile_y = screen_y // 8
                
                # Wrap around if beyond tilemap
                tile_x = tile_x % map_width
                tile_y = tile_y % map_height
                
                # Read tilemap entry (16-bit per tile)
                tile_index = tile_y * map_width + tile_x
                tile_addr = screen_base + tile_index * 2
                
                # Bounds check for VRAM
                if tile_addr + 1 >= len(self.memory.vram):
                    continue
                
                # Read tile entry (16-bit)
                tile_entry = self.memory.vram[tile_addr] | (self.memory.vram[tile_addr + 1] << 8)
                
                # Extract tile data
                tile_num = tile_entry & 0x3FF  # Tile number (0-1023)
                palette_bank = (tile_entry >> 12) & 0xF  # Palette bank (0-15)
                h_flip = bool(tile_entry & 0x0400)  # Horizontal flip
                v_flip = bool(tile_entry & 0x0800)  # Vertical flip
                
                # Calculate pixel position within tile
                px_in_tile = screen_x % 8
                py_in_tile = screen_y % 8
                
                # Apply flipping
                if h_flip:
                    px_in_tile = 7 - px_in_tile
                if v_flip:
                    py_in_tile = 7 - py_in_tile
                
                # Read 4BPP tile data from VRAM
                # Each tile is 8x8 pixels with 4 bits per pixel = 32 bytes per tile
                # VRAM address: char_block_base + tile_number * 32
                tile_data_addr = char_base + tile_num * 32
                
                # Decode 4BPP tile pixel
                # In 4BPP mode: each row of 8 pixels = 4 bytes (2 pixels per byte)
                # byte_offset = row * 4 + (col // 2)
                # bit_offset = (col % 2) * 4  (4 bits per pixel, not 2)
                byte_offset = py_in_tile * 4 + (px_in_tile // 2)
                bit_offset = (px_in_tile % 2) * 4  # 4 bits per pixel
                
                pixel_data_addr = tile_data_addr + byte_offset
                
                if pixel_data_addr < len(self.memory.vram):
                    byte_val = self.memory.vram[pixel_data_addr]
                    color_idx = (byte_val >> bit_offset) & 0x0F  # Get 4-bit color index
                    
                    # Combine with palette bank for final palette index
                    # Palette bank 0-15, each has 16 colors
                    final_palette_idx = palette_bank * 16 + color_idx
                    
                    # Get color from palette
                    # Palette RAM is 512 bytes (256 entries × 2 bytes RGB555)
                    # Entry 0 is transparent for 4BPP mode
                    if final_palette_idx < len(self.memory.palette) // 2:
                        addr = final_palette_idx * 2
                        color_r = (self.memory.palette[addr + 1] << 3) | (self.memory.palette[addr] >> 5)
                        color_g = ((self.memory.palette[addr] & 0x1C) << 3) | (self.memory.palette[addr + 1] >> 2)
                        color_b = (self.memory.palette[addr] & 0x1F) << 3
                        self.framebuffer[screen_y * 240 + screen_x * 3] = color_r
                        self.framebuffer[screen_y * 240 + screen_x * 3 + 1] = color_g
                        self.framebuffer[screen_y * 240 + screen_x * 3 + 2] = color_b
                    else:
                        self.framebuffer[screen_y * 240 + screen_x * 3] = 0
                        self.framebuffer[screen_y * 240 + screen_x * 3 + 1] = 0
                        self.framebuffer[screen_y * 240 + screen_x * 3 + 2] = 0
    
    def _convert_bgr555_to_rgb(self, color16):
        """Convert 16-bit BGR555 format to RGB tuple
        
        GBA Mode 3 uses BGR555 format:
        - Bits 0-4: Blue (0-31)
        - Bits 5-9: Green (0-31)  
        - Bits 10-14: Red (0-31)
        - Bit 15: Not used
        """
        r = ((color16 >> 10) & 0x1F) * 8  # Scale 5-bit to 8-bit
        g = ((color16 >> 5) & 0x1F) * 8
        b = (color16 & 0x1F) * 8
        return (r, g, b)
    
    def _render_mode4_bitmap(self):
        """Render Mode 4: 240x160 8BPP bitmap from VRAM

        Mode 4 uses 8-bit palette indices in VRAM:
        - VRAM at 0x06000000 contains 8-bit palette indices (1 byte per pixel)
        - Page 0: 0x06000000 (240x160 = 38400 bytes)
        - Page 1: 0x0600A000
        - Double buffering: flip on VBlank via display_frame_select

        Each palette index (0-255) maps to an RGB555 color at 0x05000000.
        """
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        for y in range(160):
            for x in range(240):
                # Mode 4: 1 byte per pixel
                offset = y * 240 + x
                addr = vram_base + offset

                palette_idx = self.memory.read_8(addr)
                color = self._get_palette_color_256(palette_idx)
                # Write RGB bytes to bytearray
                pos = (y * 240 + x) * 3
                self.framebuffer[pos] = color[0]
                self.framebuffer[pos + 1] = color[1]
                self.framebuffer[pos + 2] = color[2]

    def _get_palette_color_256(self, palette_idx):
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
            color_val = self.memory.read_32(palette_addr) & 0xFFFF
            # Convert RGB555 to RGB888
            r = ((color_val >> 0) & 0x1F) * 8
            g = ((color_val >> 5) & 0x1F) * 8
            b = ((color_val >> 10) & 0x1F) * 8
            return (r, g, b)
        except:
            return (0, 0, 0)

    def _render_mode3_bitmap(self):
        """Render bitmap Mode 3 (320x160, scaled to 240x160)
        
        Mode 3 is a 16-bit bitmap mode:
        - Resolution: 320x160 pixels
        - Color format: BGR555 (16-bit per pixel)
        - VRAM is used directly as pixel data
        """
        # Mode 3: 320x160 pixels at 16-bits per pixel = 102,400 bytes
        # Display is 240x160, so we need to scale horizontally
        
        for y in range(160):
            for x in range(240):
                # Calculate source pixel in 320x160 bitmap
                # Scale 240 -> 320
                src_x = (x * 320) // 240
                
                # Read 16-bit color from VRAM (BGR555 format)
                vram_addr = (y * 320 + src_x) * 2  # 2 bytes per pixel
                
                if vram_addr + 1 < len(self.memory.vram):
                    # Read 16-bit value (little-endian)
                    color16 = self.memory.vram[vram_addr] | (self.memory.vram[vram_addr + 1] << 8)
                    color = self._convert_bgr555_to_rgb(color16)
                else:
                    color = (0, 0, 0)
                
                # Write RGB bytes to bytearray for Mode 3
                pos = (y * 320 + src_x) * 3  # Mode 3 uses 320-wide bitmap
                self.framebuffer[pos] = color[0]
                self.framebuffer[pos + 1] = color[1]
                self.framebuffer[pos + 2] = color[2]
    
    def render_frame(self):
        """Render current frame based on DISPCNT settings

        Supports multiple display modes:
        - Mode 0: Text backgrounds (tiled)
        - Mode 3: 320x160 16-bit bitmap (BGR555)
        - Mode 4: 240x160 8-bit palette bitmap (256-color)
        """
        display_mode = self.dispcnt & 0x7  # Bits 0-2 for mode (0-5 valid)
        
        if display_mode == 3:
            self._render_mode3_bitmap()
        elif display_mode == 4:
            self._render_mode4_bitmap()
        elif display_mode == 0:
            self._render_mode0_text_background(0)

        # Copy framebuffer to pygame surface
        for y in range(160):
            for x in range(240):
                pos = (y * 240 + x) * 3
                r, g, b = self.framebuffer[pos], self.framebuffer[pos+1], self.framebuffer[pos+2]
                self.screen.set_at((x, y), (r, g, b))
    
        return self.screen

def get_ppu(memory):
    """Get or create global PPU instance"""
    global _ppu_instance
    if _ppu_instance is None:
        _ppu_instance = PPU(memory)
    return _ppu_instance

_ppu_instance = None
"#
    .to_string()
}
