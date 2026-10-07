"""PPU Mode 0 4BPP tile rendering unit tests for GBAtoPy.

Tests cover 4BPP (16-color) tile decoding, palette bank selection,
horizontal/vertical flipping, and multi-tile screen composition.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from memory import Memory
from ppu import PPU


class MockInterrupts:
    def vblank_irq(self): pass
    def hblank_irq(self): pass
    def vcounter_irq(self): pass


class MockDMA:
    def hblank_fire(self, vcount): pass
    def vblank_fire(self): pass


def make_ppu():
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    ppu = PPU(memory)
    return ppu, memory


def step_frame(ppu):
    """Step 160 visible + 68 VBlank scanlines = 228 total, then render."""
    for _ in range(228):
        ppu.step_scanline()
    ppu.render_frame()


def test_mode0_4bpp_single_tile_two_colors():
    """Mode 0 4BPP: renders a single tile with 2 colors (palette index 0 and 1)."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: priority=0, char base=0, 4BPP (bit 7=0), screen base=1, size=0
    # Value = 0x0100 (screen base block 1) = 0x0100
    memory.write_u16(0x04000008, 0x0100)
    
    # Write tile data: tile 0 is 32 bytes (4BPP)
    # Fill with alternating palette indices: even pixels = 0 (transparent), odd pixels = 1
    # Each byte packs 2 pixels: low nibble = even column, high nibble = odd column
    tile_addr = 0x06000000
    for row in range(8):
        for col in range(4):
            # Byte at (col*2) packs pixels at columns (col*2) and (col*2+1)
            # Even column (col*2): index 0 (transparent) -> low nibble
            # Odd column (col*2+1): index 1 -> high nibble
            byte_val = 0x10  # high nibble=1, low nibble=0
            memory.write_u8(tile_addr + row * 4 + col, byte_val)
    
    # Write tilemap: entry (0,0) = tile 0
    # Screen base block 1 = 0x06000800
    memory.write_u16(0x06000800, 0x0000)  # tile 0 at map entry (0,0)
    
    # Set palette[1] = red (palette[0] is backdrop)
    memory.write_u16(0x05000002, 0x001F)
    
    step_frame(ppu)
    
    # Even columns (0,2,4,6) should be transparent (backdrop/black)
    # Odd columns (1,3,5,7) should be red
    assert ppu.framebuffer[0][0] == (0, 0, 0), f"Expected backdrop at (0,0), got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][1] == (255, 0, 0), f"Expected red at (1,0), got {ppu.framebuffer[0][1]}"
    assert ppu.framebuffer[0][2] == (0, 0, 0), f"Expected backdrop at (2,0), got {ppu.framebuffer[0][2]}"
    assert ppu.framebuffer[0][3] == (255, 0, 0), f"Expected red at (3,0), got {ppu.framebuffer[0][3]}"
    
    print("✓ test_mode0_4bpp_single_tile_two_colors passed")


def test_mode0_4bpp_palette_bank_selection():
    """Mode 0 4BPP: uses correct palette bank from tilemap entry bits 12-15."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 4BPP, char base=0, screen base=1
    memory.write_u16(0x04000008, 0x0100)
    
    # Write tile data: all pixels = index 1
    tile_addr = 0x06000000
    for i in range(32):
        memory.write_u8(tile_addr + i, 0x11)  # Both nibbles = 1
    
    # Write tilemap with palette bank 2 (bits 12-15 = 0x2000)
    # entry = tile_index(10 bits) | palette_bank(4 bits) = 0x0000 | 0x2000 = 0x2000
    memory.write_u16(0x06000800, 0x2000)  # tile 0, palette bank 2
    
    # Set palette bank 2, entry 1 = green
    # Palette bank 2 starts at offset 2*16*2 = 64 bytes = 0x40
    memory.write_u16(0x05000000 + 64 + 2, 0x03E0)  # palette[33] = green
    
    step_frame(ppu)
    
    # Should use palette bank 2, index 1 = green
    assert ppu.framebuffer[0][0] == (0, 255, 0), f"Expected green from palette bank 2, got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode0_4bpp_palette_bank_selection passed")


def test_mode0_4bpp_h_flip():
    """Mode 0 4BPP: renders with horizontal flip."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 4BPP, char base=0, screen base=1
    memory.write_u16(0x04000008, 0x0100)
    
    # Write tile with distinct pattern:
    # Column 0 = index 1 (red), Column 7 = index 2 (blue)
    tile_addr = 0x06000000
    for row in range(8):
        # Byte 0: pixels 0-1, Byte 1: pixels 2-3, Byte 2: pixels 4-5, Byte 3: pixels 6-7
        # Pixel 0 (even): low nibble = 1, Pixel 1 (odd): high nibble = 1
        memory.write_u8(tile_addr + row * 4 + 0, 0x11)  # pixels 0,1 = index 1 (red)
        memory.write_u8(tile_addr + row * 4 + 1, 0)      # pixels 2,3 = index 0
        memory.write_u8(tile_addr + row * 4 + 2, 0)      # pixels 4,5 = index 0
        # Pixel 6 (even): low nibble = 2, Pixel 7 (odd): high nibble = 2
        memory.write_u8(tile_addr + row * 4 + 3, 0x22)   # pixels 6,7 = index 2 (blue)
    
    # Write tilemap with H-flip (bit 10 = 0x0400)
    memory.write_u16(0x06000800, 0x0400)  # tile 0, H-flip
    
    # Set palette
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x7C00)  # palette[2] = blue
    
    step_frame(ppu)
    
    # With H-flip: column 0 should show what was column 7 (blue)
    # Column 7 should show what was column 0 (red)
    assert ppu.framebuffer[0][0] == (0, 0, 255), f"Expected blue (H-flipped) at (0,0), got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][7] == (255, 0, 0), f"Expected red (H-flipped) at (7,0), got {ppu.framebuffer[0][7]}"
    
    print("✓ test_mode0_4bpp_h_flip passed")


def test_mode0_4bpp_v_flip():
    """Mode 0 4BPP: renders with vertical flip."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 4BPP, char base=0, screen base=1
    memory.write_u16(0x04000008, 0x0100)
    
    # Write tile with distinct pattern:
    # Row 0 = index 1 (red), Row 7 = index 2 (blue)
    tile_addr = 0x06000000
    for row in range(8):
        for col in range(4):
            if row == 0:
                memory.write_u8(tile_addr + row * 4 + col, 0x11)  # pixels col*2, col*2+1 = index 1
            elif row == 7:
                memory.write_u8(tile_addr + row * 4 + col, 0x22)  # pixels col*2, col*2+1 = index 2
            else:
                memory.write_u8(tile_addr + row * 4 + col, 0)
    
    # Write tilemap with V-flip (bit 11 = 0x0800)
    memory.write_u16(0x06000800, 0x0800)  # tile 0, V-flip
    
    # Set palette
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x7C00)  # palette[2] = blue
    
    step_frame(ppu)
    
    # With V-flip: row 0 should show what was row 7 (blue)
    # Row 7 should show what was row 0 (red)
    assert ppu.framebuffer[0][0] == (0, 0, 255), f"Expected blue (V-flipped) at (0,0), got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[7][0] == (255, 0, 0), f"Expected red (V-flipped) at (7,0), got {ppu.framebuffer[7][0]}"
    
    print("✓ test_mode0_4bpp_v_flip passed")


def test_mode0_4bpp_h_flip_and_v_flip():
    """Mode 0 4BPP: renders with both horizontal and vertical flip."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 4BPP, char base=0, screen base=1
    memory.write_u16(0x04000008, 0x0100)
    
    # Write tile with distinct pattern at corners:
    # (0,0) = index 1 (red), (7,0) = index 2 (blue)
    # (0,7) = index 3 (green), (7,7) = index 4 (yellow)
    tile_addr = 0x06000000
    for row in range(8):
        for col in range(4):
            byte_val = 0
            if row == 0 and col == 0:
                byte_val = 0x11  # pixels 0,1 = red
            elif row == 0 and col == 3:
                byte_val = 0x22  # pixels 6,7 = blue
            elif row == 7 and col == 0:
                byte_val = 0x33  # pixels 0,1 = green
            elif row == 7 and col == 3:
                byte_val = 0x44  # pixels 6,7 = yellow
            memory.write_u8(tile_addr + row * 4 + col, byte_val)
    
    # Write tilemap with H-flip + V-flip (bits 10-11 = 0x0C00)
    memory.write_u16(0x06000800, 0x0C00)  # tile 0, H-flip + V-flip
    
    # Set palette
    memory.write_u16(0x05000002, 0x001F)   # palette[1] = red (5-bit: R:7, G:0, B:0)
    memory.write_u16(0x05000004, 0x7C00)   # palette[2] = blue (5-bit: R:0, G:0, B:31)
    memory.write_u16(0x05000006, 0x03E0)   # palette[3] = green (5-bit: R:0, G:31, B:0)
    memory.write_u16(0x05000008, 0x03FF)   # palette[4] = yellow (5-bit: R:31, G:31, B:0)
    
    step_frame(ppu)
    
    # With H+V flip:
    # (0,0) should show what was (7,7) = yellow
    # (7,0) should show what was (0,7) = green
    # (0,7) should show what was (7,0) = blue
    # (7,7) should show what was (0,0) = red
    assert ppu.framebuffer[0][0] == (255, 255, 0), f"Expected yellow at (0,0), got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][7] == (0, 255, 0), f"Expected green at (7,0), got {ppu.framebuffer[0][7]}"
    assert ppu.framebuffer[7][0] == (0, 0, 255), f"Expected blue at (0,7), got {ppu.framebuffer[7][0]}"
    assert ppu.framebuffer[7][7] == (255, 0, 0), f"Expected red at (7,7), got {ppu.framebuffer[7][7]}"
    
    print("✓ test_mode0_4bpp_h_flip_and_v_flip passed")


def test_mode0_4bpp_multiple_tiles_in_screen():
    """Mode 0 4BPP: renders multiple tiles in a screen."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 4BPP, char base=0, screen base=1
    memory.write_u16(0x04000008, 0x0100)
    
    # Write tile 0: all pixels = index 1 (red)
    tile_addr_0 = 0x06000000
    for i in range(32):
        memory.write_u8(tile_addr_0 + i, 0x11)
    
    # Write tile 1: all pixels = index 2 (blue)
    tile_addr_1 = 0x06000000 + 32
    for i in range(32):
        memory.write_u8(tile_addr_1 + i, 0x22)
    
    # Write tilemap: 2x2 grid of tiles
    # (0,0) = tile 0, (1,0) = tile 1
    # (0,1) = tile 1, (1,1) = tile 0
    screen_base = 0x06000800
    memory.write_u16(screen_base + 0, 0x0000)      # tile 0 at (0,0)
    memory.write_u16(screen_base + 2, 0x0001)      # tile 1 at (1,0)
    memory.write_u16(screen_base + 64, 0x0001)     # tile 1 at (0,1)
    memory.write_u16(screen_base + 66, 0x0000)     # tile 0 at (1,1)
    
    # Set palette
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x7C00)  # palette[2] = blue
    
    step_frame(ppu)
    
    # Top-left 8x8 (tile 0) should be red
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red at (0,0), got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[7][7] == (255, 0, 0), f"Expected red at (7,7), got {ppu.framebuffer[7][7]}"
    
    # Top-right 8x8 (tile 1) should be blue
    assert ppu.framebuffer[0][8] == (0, 0, 255), f"Expected blue at (8,0), got {ppu.framebuffer[0][8]}"
    assert ppu.framebuffer[7][15] == (0, 0, 255), f"Expected blue at (15,7), got {ppu.framebuffer[7][15]}"
    
    # Bottom-left 8x8 (tile 1) should be blue
    assert ppu.framebuffer[8][0] == (0, 0, 255), f"Expected blue at (0,8), got {ppu.framebuffer[8][0]}"
    
    # Bottom-right 8x8 (tile 0) should be red
    assert ppu.framebuffer[8][8] == (255, 0, 0), f"Expected red at (8,8), got {ppu.framebuffer[8][8]}"
    
    print("✓ test_mode0_4bpp_multiple_tiles_in_screen passed")


def test_mode0_4bpp_high_palette_indices():
    """Mode 0 4BPP: renders with high palette indices (8-15)."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 4BPP, char base=0, screen base=1
    memory.write_u16(0x04000008, 0x0100)
    
    # Write tile with palette indices 8-15
    tile_addr = 0x06000000
    for row in range(8):
        for col in range(4):
            # Each byte packs 2 pixels: low nibble = even column, high nibble = odd column
            idx_even = 8 + col * 2      # even column index
            idx_odd = 8 + col * 2 + 1   # odd column index
            byte_val = (idx_odd << 4) | idx_even
            memory.write_u8(tile_addr + row * 4 + col, byte_val)
    
    # Write tilemap: tile 0, palette bank 0
    memory.write_u16(0x06000800, 0x0000)
    
    # Set palette indices 8-15 to distinct colors
    for i in range(8, 16):
        # Color = (i*16, 0, 0) in 5-bit red
        color_val = (i * 2) & 0x1F
        memory.write_u16(0x05000000 + i * 2, color_val)
    
    step_frame(ppu)
    
    # Verify high palette indices render correctly
    # Pixel at (0,0) uses index 8
    expected_8 = ((8 * 2) << 3) | ((8 * 2) >> 2)  # 5-bit to 8-bit expansion
    assert ppu.framebuffer[0][0][0] == expected_8, f"Expected red shade {expected_8} at (0,0), got {ppu.framebuffer[0][0]}"
    
    # Pixel at (1,0) uses index 9
    expected_9 = ((9 * 2) << 3) | ((9 * 2) >> 2)
    assert ppu.framebuffer[0][1][0] == expected_9, f"Expected red shade {expected_9} at (1,0), got {ppu.framebuffer[0][1]}"
    
    print("✓ test_mode0_4bpp_high_palette_indices passed")


def test_mode0_4bpp_empty_tilemap():
    """Mode 0 4BPP with empty tilemap (all zeros) renders backdrop."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 4BPP, char base=0, screen base=0
    memory.write_u16(0x04000008, 0x0000)
    
    # Leave tilemap all zeros (tile index 0, no flip, palette bank 0)
    # Don't write any tilemap entries - they should be zero-initialized
    
    # Set palette[0] to green (backdrop color)
    memory.write_u16(0x05000000, 0x03E0)
    
    step_frame(ppu)
    
    # All pixels should be backdrop (green) since tilemap is empty
    for y in range(8):  # Check first 8 rows
        for x in range(8):  # Check first 8 columns
            assert ppu.framebuffer[y][x] == (0, 255, 0), f"Expected green backdrop at ({x},{y}), got {ppu.framebuffer[y][x]}"
    
    print("✓ test_mode0_4bpp_empty_tilemap passed")


if __name__ == "__main__":
    test_mode0_4bpp_single_tile_two_colors()
    test_mode0_4bpp_palette_bank_selection()
    test_mode0_4bpp_h_flip()
    test_mode0_4bpp_v_flip()
    test_mode0_4bpp_h_flip_and_v_flip()
    test_mode0_4bpp_multiple_tiles_in_screen()
    test_mode0_4bpp_high_palette_indices()
    test_mode0_4bpp_empty_tilemap()
    print("\nAll 8 Mode 0 4BPP tests passed!")