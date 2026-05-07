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

The PPU reads from:
- VRAM (0x06000000): Tile data, tilemaps, bitmaps
- Palette RAM (0x05000000): 512x16-bit colors
- OAM (0x07000000): Sprite data

Rendering follows GBA timing:
- Mode 0: Text background (scanline mode)
- Mode 3: Bitmap background
"""

import pygame
import numpy as np

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
MODE3_ENABLE = 0x20

# Background control registers
BG0CNT = 0x04000008
BG1CNT = 0x0400000C

class PPU:
    """GBA Picture Processing Unit emulator"""
    
    def __init__(self, memory):
        """Initialize PPU with GBA memory object"""
        self.memory = memory
        self.screen = pygame.Surface((240, 160), pygame.SRCALPHA)
        self.framebuffer = np.zeros((160, 240, 3), dtype=np.uint8)
        
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
        
    def _parse_tilemaps(self):
        """Parse tilemap metadata from DISPCNT and BGxCNT"""
        # Extract BG0 mode (lower 4 bits of BG0CNT)
        bg0_mode = (self.bg0cntl >> 0) & 0xF
        # Extract BG0 size (lower 4 bits of BG0CNT + 4)
        bg0_size = (self.bg0cnt2 >> 0) & 0xF
        
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
    
    def _decode_tile_4bpp(self, tile_index):
        """Decode 4BPP tile data to 32x32 pixels"""
        # 4BPP = 2 bits per pixel = 32 pixels / 2 = 16 bytes per tile
        tile_data = self.memory.vram[tile_index * 16:(tile_index + 1) * 16]
        
        # For simplicity, return grayscale based on pattern
        pattern = 0
        for i in range(0, 16, 2):
            pattern = (pattern << 2) | (tile_data[i] >> 4 & 3) | (tile_data[i + 1] << 4 & 0x30)
        
        return pattern
    
    def _render_mode0_text_background(self, bg_num):
        """Render text background Mode 0"""
        # Mode 0: 160x160 text grid
        # Background is displayed at X=0 for BG0, X=160 for BG1, etc.
        
        pass  # Not implemented in detail
    
    def _render_mode3_bitmap(self):
        """Render bitmap Mode 3 (320x160, scaled to 240x160)"""
        # Read bitmap data
        bitmap_size = 320 * 160 // 4  # 4BPP
        bitmap_data = self.memory.vram[VRAM_BASE:VRAM_BASE + bitmap_size]
        
        # Scale 320x160 to 240x160
        for y in range(160):
            for x in range(120):  # 320/2 = 120 horizontal units
                # Sample two 320x160 pixels for each 240x160 pixel
                pattern = bitmap_data[y * 320 + x * 2] & 0x3
                color = self._get_palette_color(pattern)
                self.framebuffer[y, x * 2] = color
                self.framebuffer[y, x * 2 + 1] = color
    
    def render_frame(self):
        """Render current frame based on DISPCNT settings"""
        # Check which modes are enabled
        mode0_enabled = bool(self.dispcnt & BG0_ENABLE)
        mode3_enabled = bool(self.dispcnt & MODE3_ENABLE)
        
        if mode3_enabled:
            self._render_mode3_bitmap()
        elif mode0_enabled:
            self._render_mode0_text_background(0)
        
        # Copy framebuffer to pygame surface
        for y in range(160):
            for x in range(240):
                r, g, b = self.framebuffer[y, x]
                self.screen.set_at((x, y), (r, g, b))
        
        return self.screen.get_array()

def get_ppu(memory):
    """Get or create global PPU instance"""
    global _ppu_instance
    if _ppu_instance is None:
        _ppu_instance = PPU(memory)
    return _ppu_instance

_ppu_instance = None
"#,
    );
}
