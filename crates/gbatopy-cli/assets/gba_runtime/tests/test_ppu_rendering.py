"""PPU rendering unit tests for GBAtoPy.

Tests cover Modes 3, 4, 5 bitmap rendering, forced blank, affine transformations,
8BPP tile rendering, and backdrop color behavior.
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


def test_mode3_renders_bitmap():
    """Mode 3: 240x160 16-bit bitmap rendering."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 3 + BG2 enable
    memory.write_u16(0x04000000, 0x0403)
    
    # Write known pixel colors to VRAM at (0,0), (1,0), (0,1)
    # Red = 0x001F (bits 0-4), Green = 0x03E0 (bits 5-9), Blue = 0x7C00 (bits 10-14)
    vram_base = 0x06000000
    memory.write_u16(vram_base + 0, 0x001F)  # (0,0) = red
    memory.write_u16(vram_base + 2, 0x03E0)  # (1,0) = green
    memory.write_u16(vram_base + 240 * 2, 0x7C00)  # (0,1) = blue
    
    step_frame(ppu)
    
    # Verify pixel colors (5-bit to 8-bit expansion)
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red, got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][1] == (0, 255, 0), f"Expected green, got {ppu.framebuffer[0][1]}"
    assert ppu.framebuffer[1][0] == (0, 0, 255), f"Expected blue, got {ppu.framebuffer[1][0]}"
    
    print("✓ test_mode3_renders_bitmap passed")


def test_mode4_renders_indexed_bitmap():
    """Mode 4: 240x160 8-bit indexed bitmap rendering."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 4 + BG2 enable
    memory.write_u16(0x04000000, 0x0404)
    
    # Set palette entry 1 to red, entry 2 to blue
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x7C00)  # palette[2] = blue
    
    # Write palette indices to VRAM
    vram_base = 0x06000000
    memory.write_u8(vram_base + 0, 1)  # (0,0) = index 1 (red)
    memory.write_u8(vram_base + 1, 2)  # (1,0) = index 2 (blue)
    
    step_frame(ppu)
    
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red, got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][1] == (0, 0, 255), f"Expected blue, got {ppu.framebuffer[0][1]}"
    
    print("✓ test_mode4_renders_indexed_bitmap passed")


def test_mode5_renders_small_bitmap():
    """Mode 5: 160x128 16-bit bitmap rendering with backdrop outside bitmap."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 5 + BG2 enable
    memory.write_u16(0x04000000, 0x0405)
    
    # Write red pixel at (0,0) within the 160x128 region
    vram_base = 0x06000000
    memory.write_u16(vram_base + 0, 0x001F)  # (0,0) = red
    
    step_frame(ppu)
    
    # (0,0) is within bitmap
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red, got {ppu.framebuffer[0][0]}"
    # x=160 is outside the 160-wide bitmap, should be backdrop (black)
    assert ppu.framebuffer[0][160] == (0, 0, 0), f"Expected backdrop, got {ppu.framebuffer[0][160]}"
    
    print("✓ test_mode5_renders_small_bitmap passed")


def test_forced_blank_renders_white():
    """Forced blank (DISPCNT bit 7) renders white screen."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT bit 7 (forced blank)
    memory.write_u16(0x04000000, 0x0080)
    
    step_frame(ppu)
    
    # All pixels should be white
    for y in range(160):
        for x in range(240):
            assert ppu.framebuffer[y][x] == (255, 255, 255), f"Expected white at ({x},{y}), got {ppu.framebuffer[y][x]}"
    
    print("✓ test_forced_blank_renders_white passed")


def test_mode3_affine_identity():
    """Mode 3 with identity affine params: pixel-perfect passthrough."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 3 + BG2 enable
    memory.write_u16(0x04000000, 0x0403)
    
    # Set identity affine params: PA=256, PD=256 (1.0 in 16.8 fixed point)
    memory.write_u16(0x04000020, 256)  # PA
    memory.write_u16(0x04000022, 0)    # PB
    memory.write_u16(0x04000024, 0)    # PC
    memory.write_u16(0x04000026, 256)  # PD
    memory.write_u32(0x04000028, 0)    # X, Y
    memory.write_u32(0x0400002C, 0)
    
    # Write known pixels to VRAM
    vram_base = 0x06000000
    memory.write_u16(vram_base + 0, 0x001F)  # (0,0) = red
    memory.write_u16(vram_base + 2, 0x03E0)  # (1,0) = green
    
    step_frame(ppu)
    
    # Identity transform = direct passthrough
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red, got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][1] == (0, 255, 0), f"Expected green, got {ppu.framebuffer[0][1]}"
    
    print("✓ test_mode3_affine_identity passed")


def test_mode3_affine_2x_scale():
    """Mode 3 with 2x scaling: PA=128, PD=128."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 3 + BG2 enable
    memory.write_u16(0x04000000, 0x0403)
    
    # Set 2x scaling: PA=128, PD=128 (0.5 in 16.8 fixed point)
    memory.write_u16(0x04000020, 128)  # PA
    memory.write_u16(0x04000022, 0)    # PB
    memory.write_u16(0x04000024, 0)    # PC
    memory.write_u16(0x04000026, 128)  # PD
    memory.write_u32(0x04000028, 0)    # X, Y
    memory.write_u32(0x0400002C, 0)
    
    # Write red at (0,0), blue at (1,0)
    vram_base = 0x06000000
    memory.write_u16(vram_base + 0, 0x001F)  # (0,0) = red
    memory.write_u16(vram_base + 2, 0x7C00)  # (1,0) = blue
    
    step_frame(ppu)
    
    # 2x scale: each source pixel appears 2x on screen
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red, got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][1] == (255, 0, 0), f"Expected red (scaled), got {ppu.framebuffer[0][1]}"
    assert ppu.framebuffer[0][2] == (0, 0, 255), f"Expected blue, got {ppu.framebuffer[0][2]}"
    assert ppu.framebuffer[0][3] == (0, 0, 255), f"Expected blue (scaled), got {ppu.framebuffer[0][3]}"
    
    print("✓ test_mode3_affine_2x_scale passed")


def test_mode4_page_flip():
    """Mode 4 page flip: DISPCNT bit 4 selects VRAM page."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT mode 4, page 0
    memory.write_u16(0x04000000, 0x0404)
    
    # Write palette index 1 to page 0 VRAM
    memory.write_u8(0x06000000, 1)
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    
    # Write palette index 2 to page 1 VRAM
    memory.write_u8(0x0600A000, 2)
    memory.write_u16(0x05000004, 0x7C00)  # palette[2] = blue
    
    step_frame(ppu)
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red (page 0), got {ppu.framebuffer[0][0]}"
    
    # Switch to page 1
    memory.write_u16(0x04000000, 0x0414)  # bit 4 set
    step_frame(ppu)
    assert ppu.framebuffer[0][0] == (0, 0, 255), f"Expected blue (page 1), got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode4_page_flip passed")


def test_8bpp_tile_rendering():
    """8BPP tile rendering in Mode 0."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: priority=0, char base=0, 8BPP (bit 6=1), screen base=1, size=0
    # Value = 0x0040 (8BPP) | 0x0100 (screen base block 1) = 0x0140
    memory.write_u16(0x04000008, 0x0140)
    
    # Write tile data: tile 0 is 64 bytes, fill with palette index 1
    tile_addr = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr + i, 1)
    
    # Write tilemap: entry (0,0) = tile 0
    # Screen base block 1 = 0x06000800
    memory.write_u16(0x06000800, 0x0000)  # tile 0 at map entry (0,0)
    
    # Set palette[1] = red
    memory.write_u16(0x05000002, 0x001F)
    
    step_frame(ppu)
    
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red from 8BPP tile, got {ppu.framebuffer[0][0]}"
    
    print("✓ test_8bpp_tile_rendering passed")


def test_8bpp_different_char_base_blocks():
    """8BPP tiles at different character base blocks (0x6000000, 0x6004000)."""
    # Test char block 0
    ppu0, memory0 = make_ppu()
    memory0.write_u16(0x04000000, 0x0100)  # mode 0 + BG0
    memory0.write_u16(0x04000008, 0x0180)  # 8BPP, char base=0, screen base=1
    
    # Write tile 0 at char block 0 with palette index 1 (red)
    tile_addr_0 = 0x06000000
    for i in range(64):
        memory0.write_u8(tile_addr_0 + i, 1)
    memory0.write_u16(0x06000800, 0x0000)  # tile 0 at (0,0)
    memory0.write_u16(0x05000002, 0x001F)  # palette[1] = red
    
    step_frame(ppu0)
    assert ppu0.framebuffer[0][0] == (255, 0, 0), f"Expected red from char block 0, got {ppu0.framebuffer[0][0]}"
    
    # Test char block 1
    ppu1, memory1 = make_ppu()
    memory1.write_u16(0x04000000, 0x0100)  # mode 0 + BG0
    memory1.write_u16(0x04000008, 0x0184)  # 8BPP, char base=1, screen base=1
    
    # Write tile 0 at char block 1 (0x06004000) with palette index 2 (green)
    tile_addr_1 = 0x06004000
    for i in range(64):
        memory1.write_u8(tile_addr_1 + i, 2)
    memory1.write_u16(0x06000800, 0x0000)  # tile 0 at (0,0)
    memory1.write_u16(0x05000004, 0x03E0)  # palette[2] = green
    
    step_frame(ppu1)
    assert ppu1.framebuffer[0][0] == (0, 255, 0), f"Expected green from char block 1, got {ppu1.framebuffer[0][0]}"
    
    print("✓ test_8bpp_different_char_base_blocks passed")


def test_8bpp_different_screen_base_blocks():
    """8BPP tiles with different screen base blocks (0, 1, 2, 3)."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Test screen base block 2 (0x06002000)
    memory.write_u16(0x04000008, 0x0080 | (2 << 8))  # 8BPP, char base=0, screen base=2
    
    # Write tile data at char block 0
    tile_addr = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr + i, 1)
    
    # Write tilemap at screen base block 2
    memory.write_u16(0x06002000, 0x0000)  # tile 0 at (0,0)
    
    # Set palette
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    
    step_frame(ppu)
    
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red from screen block 2, got {ppu.framebuffer[0][0]}"
    
    print("✓ test_8bpp_different_screen_base_blocks passed")


def test_8bpp_256_color_palette():
    """8BPP tile using full 256-color palette (indices 0-255)."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 8BPP, char base=0, screen base=1 (avoid VRAM overlap)
    memory.write_u16(0x04000008, 0x0180)
    
    # Write tile with varying palette indices (0-63 in first 8 rows)
    # Row-major order: pixel (x,y) -> index = y*8 + x
    tile_addr = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr + i, i)  # indices 0-63
    
    # Write tilemap at screen base block 1 (0x06000800)
    memory.write_u16(0x06000800, 0x0000)  # tile 0 at map entry (0,0)
    
    # Set palette colors: index i = color (i*4, 0, 0) in 5-bit
    for i in range(256):
        r = (i * 4) & 0x1F  # 5-bit red
        color_val = r
        memory.write_u16(0x05000000 + i * 2, color_val)
    
    step_frame(ppu)
    
    # Verify pixel at (0,0) uses palette index 0 (transparent, should be backdrop)
    # Pixel at (1,0) uses palette index 1
    # Pixel at (7,0) uses palette index 7
    assert ppu.framebuffer[0][0] == (0, 0, 0), f"Expected transparent (backdrop) at (0,0), got {ppu.framebuffer[0][0]}"
    
    # Palette index 1: r=4 (5-bit) -> 8-bit expansion: (4<<3)|(4>>2) = 32|1 = 33
    expected_color_1 = (33, 0, 0)
    assert ppu.framebuffer[0][1] == expected_color_1, f"Expected {expected_color_1} at (1,0), got {ppu.framebuffer[0][1]}"
    
    # Palette index 7: r=28 (5-bit) -> 8-bit expansion: (28<<3)|(28>>2) = 224|7 = 231
    expected_color_7 = (231, 0, 0)
    assert ppu.framebuffer[0][7] == expected_color_7, f"Expected {expected_color_7} at (7,0), got {ppu.framebuffer[0][7]}"
    
    print("✓ test_8bpp_256_color_palette passed")


def test_8bpp_h_flip_v_flip():
    """8BPP tile with horizontal and vertical flip."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 8BPP, char base=0, screen base=1 (avoid VRAM overlap)
    memory.write_u16(0x04000008, 0x0180)
    
    # Write tile with distinct pattern:
    # Row 0: all index 1 (red)
    # Row 7: all index 2 (blue)
    tile_addr = 0x06000000
    for i in range(64):
        row = i // 8
        if row == 0:
            memory.write_u8(tile_addr + i, 1)  # red
        elif row == 7:
            memory.write_u8(tile_addr + i, 2)  # blue
        else:
            memory.write_u8(tile_addr + i, 0)  # transparent
    
    # Write tilemap with H-flip and V-flip at screen base block 1
    # bit 10 = H-flip, bit 11 = V-flip
    memory.write_u16(0x06000800, 0x0C00)  # tile 0, H-flip + V-flip
    
    # Set palette
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x7C00)  # palette[2] = blue
    
    step_frame(ppu)
    
    # With V-flip: row 0 of screen should show what was row 7 of tile (blue)
    # With H-flip: pixel order in row is reversed (but all same color here)
    assert ppu.framebuffer[0][0] == (0, 0, 255), f"Expected blue (V-flipped) at (0,0), got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][7] == (0, 0, 255), f"Expected blue (V-flipped) at (0,7), got {ppu.framebuffer[0][7]}"
    
    # Row 7 of screen should show what was row 0 of tile (red)
    assert ppu.framebuffer[7][0] == (255, 0, 0), f"Expected red (V-flipped) at (7,0), got {ppu.framebuffer[7][0]}"
    assert ppu.framebuffer[7][7] == (255, 0, 0), f"Expected red (V-flipped) at (7,7), got {ppu.framebuffer[7][7]}"
    
    print("✓ test_8bpp_h_flip_v_flip passed")


def test_8bpp_empty_tilemap():
    """8BPP with empty tilemap (all zeros) renders backdrop."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 8BPP, char base=0, screen base=0
    memory.write_u16(0x04000008, 0x0080)
    
    # Leave tilemap all zeros (tile index 0, no flip, palette 0)
    # Don't write any tilemap entries - they should be zero-initialized
    
    # Set palette[0] to green (backdrop color)
    memory.write_u16(0x05000000, 0x03E0)
    
    step_frame(ppu)
    
    # All pixels should be backdrop (green) since tilemap is empty
    for y in range(8):  # Check first 8 rows
        for x in range(8):  # Check first 8 columns
            assert ppu.framebuffer[y][x] == (0, 255, 0), f"Expected green backdrop at ({x},{y}), got {ppu.framebuffer[y][x]}"
    
    print("✓ test_8bpp_empty_tilemap passed")


def test_8bpp_max_tile_index():
    """8BPP with maximum tile index (255) in 8BPP mode."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0 + BG0 enable
    memory.write_u16(0x04000000, 0x0100)
    
    # Set BG0CNT: 8BPP, char base=0, screen base=1 (avoid VRAM overlap)
    memory.write_u16(0x04000008, 0x0180)
    
    # Write tile 255 at char block 0 (0x06000000 + 255*64 = 0x06003FC0)
    # Char block 0 is 16KB = 0x4000 bytes, so tile 255 fits at offset 0x3FC0
    tile_addr = 0x06000000 + 255 * 64
    for i in range(64):
        memory.write_u8(tile_addr + i, 1)
    
    # Write tilemap with tile index 255 at screen base block 1
    memory.write_u16(0x06000800, 0x00FF)  # tile 255 at (0,0)
    
    # Set palette
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    
    step_frame(ppu)
    
    # Verify tile 255 renders correctly
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red from tile 255, got {ppu.framebuffer[0][0]}"
    
    print("✓ test_8bpp_max_tile_index passed")


def test_backdrop_color_no_bg_enabled():
    """No BGs enabled: entire screen is backdrop color."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 0, no BGs enabled
    memory.write_u16(0x04000000, 0x0000)
    
    # Set palette entry 0 to green
    memory.write_u16(0x05000000, 0x03E0)
    
    step_frame(ppu)
    
    # All pixels should be backdrop (green)
    for y in range(160):
        for x in range(240):
            assert ppu.framebuffer[y][x] == (0, 255, 0), f"Expected green backdrop at ({x},{y}), got {ppu.framebuffer[y][x]}"
    
    print("✓ test_backdrop_color_no_bg_enabled passed")


def test_mode3_bg2_disabled_renders_backdrop():
    """Mode 3 with BG2 disabled: renders backdrop color, not bitmap."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()

    # Set backdrop to blue (0x7C00) so it's distinguishable from zero-VRAM black
    # 0x7C00 = bits 10-14 set (blue channel in RGB555)
    memory.write_u16(0x05000000, 0x7C00)

    # Set DISPCNT to mode 3 but BG2 NOT enabled (value = 0x0003)
    memory.write_u16(0x04000000, 0x0003)

    ppu = PPU(memory)

    step_frame(ppu)

    # With bg2_enable check: bitmap is skipped, backdrop (blue) shows.
    # Without the check: zero-VRAM bitmap renders as black.
    for y in range(160):
        for x in range(240):
            assert ppu.framebuffer[y][x] == (0, 0, 255), f"Expected blue backdrop at ({x},{y}), got {ppu.framebuffer[y][x]}"

    print("✓ test_mode3_bg2_disabled_renders_backdrop passed")


def test_mode1_text_bg0_renders():
    """Mode 1: BG0 text mode with 4BPP tile, BG2 disabled."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 1 + BG0 enable (0x0100 | 0x0001 = 0x0101)
    # Mode 1 = bits 0-2 = 001, BG0 enable = bit 8 = 0x0100
    memory.write_u16(0x04000000, 0x0101)
    
    # Set BG0CNT: priority=0, char base=0, 4BPP (bit 7=0), screen base=1, size=0
    # Value = 0x0100 (screen base block 1) = 0x0100
    memory.write_u16(0x04000008, 0x0100)
    
    # Write tile data: tile 0 is 32 bytes (4BPP), fill with palette index 1
    tile_addr = 0x06000000
    for i in range(32):
        memory.write_u8(tile_addr + i, 0x01)  # Each byte = 2 pixels (4BPP)
    
    # Write tilemap: entry (0,0) = tile 0
    # Screen base block 1 = 0x06000800
    memory.write_u16(0x06000800, 0x0000)  # tile 0 at map entry (0,0)
    
    # Set palette[1] = red
    memory.write_u16(0x05000002, 0x001F)
    
    step_frame(ppu)
    
    # Verify red pixel from BG0 text tile
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red from BG0 text, got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode1_text_bg0_renders passed")


def test_mode1_affine_bg2_renders():
    """Mode 1: BG2 affine with identity matrix, 8BPP tile data."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 1 + BG2 enable BEFORE creating PPU (PPU reads config at init)
    # Mode 1 = bits 0-2 = 001, BG2 enable = bit 10 = 0x0400
    # Value = 0x0400 | 0x0001 = 0x0401
    memory.write_u16(0x04000000, 0x0401)
    
    # Set BG2CNT: priority=0, char base=0, 8BPP, screen base=1, size=1 (256x256)
    # Value = 0x0000 (priority 0) | 0x0000 (char base 0) | 0x0080 (8BPP) | 0x0100 (screen base 1) | 0x4000 (size 1) = 0x4180
    memory.write_u16(0x0400000C, 0x4180)
    
    ppu = PPU(memory)
    
    # Set identity affine params: PA=256, PD=256 (1.0 in 16.8 fixed point)
    memory.write_u16(0x04000020, 256)  # BG2PA
    memory.write_u16(0x04000022, 0)    # BG2PB
    memory.write_u16(0x04000024, 0)    # BG2PC
    memory.write_u16(0x04000026, 256)  # BG2PD
    memory.write_u32(0x04000028, 0)    # BG2X (lower 16 bits)
    memory.write_u32(0x0400002C, 0)    # BG2X (upper 16 bits) + BG2Y
    memory.write_u32(0x04000030, 0)    # BG2Y (upper 16 bits) + reserved
    
    # Write tile data: tile 0 is 64 bytes (8BPP), fill with palette index 1
    tile_addr = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr + i, 1)  # 8BPP = 1 byte per pixel
    
    # Write affine tilemap: screen base 1 = 0x06000800, 32x32 map for 256x256 BG
    # Each entry is 1 byte (8-bit tilemap for affine)
    # Fill first 8x8 tiles with tile index 0
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)  # tile 0 at each map entry
    
    # Set palette[1] = red
    memory.write_u16(0x05000002, 0x001F)
    
    step_frame(ppu)
    
    # Identity transform = direct passthrough
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red, got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode1_affine_bg2_renders passed")


def test_mode1_text_plus_affine_composite():
    """Mode 1: BG0 text + BG2 affine both visible, verify priority ordering."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 1 + BG0 + BG2 enable BEFORE creating PPU
    # Mode 1 = bits 0-2 = 001, BG0 enable = bit 8 = 0x0100, BG2 enable = bit 10 = 0x0400
    # Value = 0x0400 | 0x0100 | 0x0001 = 0x0501
    memory.write_u16(0x04000000, 0x0501)
    
    # Set BG0CNT: priority=1, char base=0, 4BPP, screen base=2 (avoid overlap with BG2)
    memory.write_u16(0x04000008, 0x0200 | 0x0002)  # priority=1, screen base=2
    
    # Set BG2CNT: priority=0 (higher than BG0), char base=1, 8BPP, screen base=1, size=1 (256x256)
    # Value = 0x0000 (priority 0) | 0x0004 (char base 1) | 0x0080 (8BPP) | 0x0100 (screen base 1) | 0x4000 (size 1) = 0x4184
    memory.write_u16(0x0400000C, 0x4184)
    
    ppu = PPU(memory)
    
    # Set identity affine params for BG2
    memory.write_u16(0x04000020, 256)  # BG2PA
    memory.write_u16(0x04000022, 0)    # BG2PB
    memory.write_u16(0x04000024, 0)    # BG2PC
    memory.write_u16(0x04000026, 256)  # BG2PD
    memory.write_u32(0x04000028, 0)    # BG2X
    memory.write_u32(0x0400002C, 0)    # BG2X/Y
    memory.write_u32(0x04000030, 0)    # BG2Y
    
    # Write BG0 tile data: tile 0 with palette index 1 (red)
    tile_addr_bg0 = 0x06000000
    for i in range(32):
        memory.write_u8(tile_addr_bg0 + i, 0x01)
    
    # Write BG0 tilemap: entry (0,0) = tile 0 at screen base block 2
    # screen base 2 = 0x06000000 + (2 * 0x0800) = 0x06001000
    memory.write_u16(0x06001000, 0x0000)
    
    # Write BG2 tile data: tile 0 at char base 1 (0x06004000) with palette index 2 (green)
    tile_addr_bg2 = 0x06004000
    for i in range(64):
        memory.write_u8(tile_addr_bg2 + i, 0x02)
    
    # Write BG2 affine tilemap: screen base 1 = 0x06000800, 8-bit entries
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)  # tile 0 at each map entry
    
    # Set palette: index 1 = red, index 2 = green
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x03E0)  # palette[2] = green
    
    step_frame(ppu)
    
    # BG2 has priority 0, BG0 has priority 1, so BG2 should be on top
    assert ppu.framebuffer[0][0] == (0, 255, 0), f"Expected green (BG2 on top), got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode1_text_plus_affine_composite passed")


def test_mode1_bg_priority_ordering():
    """Mode 1: BG0 and BG1 with different priority bits, verify correct z-order."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 1 + BG0 + BG1 enable BEFORE creating PPU
    # Mode 1 = bits 0-2 = 001, BG0 enable = bit 8 = 0x0100, BG1 enable = bit 9 = 0x0200
    # Value = 0x0300 | 0x0001 = 0x0301
    memory.write_u16(0x04000000, 0x0301)
    
    # Set BG0CNT: priority=1, char base=0, 4BPP, screen base=1
    memory.write_u16(0x04000008, 0x0100 | 0x0001)  # priority = 1
    
    # Set BG1CNT: priority=0 (higher than BG0), char base=0, 4BPP, screen base=2
    # Value = 0x0000 (priority 0) | 0x0200 (screen base 2) = 0x0200
    memory.write_u16(0x0400000A, 0x0200)
    
    ppu = PPU(memory)
    
    # Write BG0 tile data: tile 0 with palette index 1 (red)
    tile_addr_bg0 = 0x06000000
    for i in range(32):
        memory.write_u8(tile_addr_bg0 + i, 0x01)
    
    # Write BG0 tilemap: entry (0,0) = tile 0 at screen base block 1
    memory.write_u16(0x06000800, 0x0000)
    
    # Write BG1 tile data: tile 0 with palette index 2 (blue)
    tile_addr_bg1 = 0x06000000 + 32  # Share char block, offset tile
    for i in range(32):
        memory.write_u8(tile_addr_bg1 + i, 0x02)
    
    # Write BG1 tilemap: entry (0,0) = tile 1 at screen base block 2
    # screen base 2 = 0x06000000 + (2 * 0x0800) = 0x06001000
    memory.write_u16(0x06001000, 0x0001)  # tile 1
    
    # Set palette: index 1 = red, index 2 = blue
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x7C00)  # palette[2] = blue
    
    step_frame(ppu)
    
    # BG1 has priority 0, BG0 has priority 1, so BG1 should be on top
    assert ppu.framebuffer[0][0] == (0, 0, 255), f"Expected blue (BG1 on top), got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode1_bg_priority_ordering passed")


def test_mode1_empty():
    """Mode 1 with no tiles/data, verify backdrop color fills screen."""
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 1, no BGs enabled
    # Mode 1 = bits 0-2 = 001 = 0x0001
    memory.write_u16(0x04000000, 0x0001)
    
    # Set palette entry 0 to green (backdrop color)
    memory.write_u16(0x05000000, 0x03E0)
    
    step_frame(ppu)
    
    # All pixels should be backdrop (green)
    for y in range(160):
        for x in range(240):
            assert ppu.framebuffer[y][x] == (0, 255, 0), f"Expected green backdrop at ({x},{y}), got {ppu.framebuffer[y][x]}"
    
    print("✓ test_mode1_empty passed")


if __name__ == "__main__":
    test_mode3_renders_bitmap()
    test_mode4_renders_indexed_bitmap()
    test_mode5_renders_small_bitmap()
    test_forced_blank_renders_white()
    test_mode3_affine_identity()
    test_mode3_affine_2x_scale()
    test_mode4_page_flip()
    test_8bpp_tile_rendering()
    test_8bpp_different_char_base_blocks()
    test_8bpp_different_screen_base_blocks()
    test_8bpp_256_color_palette()
    test_8bpp_h_flip_v_flip()
    test_8bpp_empty_tilemap()
    test_8bpp_max_tile_index()
    test_backdrop_color_no_bg_enabled()
    test_mode3_bg2_disabled_renders_backdrop()
    test_mode1_text_bg0_renders()
    test_mode1_affine_bg2_renders()
    test_mode1_text_plus_affine_composite()
    test_mode1_bg_priority_ordering()
    test_mode1_empty()
    print("\nAll 21 PPU rendering tests passed!")