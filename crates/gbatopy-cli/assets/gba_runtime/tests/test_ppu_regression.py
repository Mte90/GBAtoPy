"""PPU regression tests for documented codegen pitfalls.

Regression tests for pitfalls documented in docs/codegen-pitfalls.md:
- Pitfall #3: PPU Default Mode Hard-coded
- Pitfall #4: Character Block Base as Number Not Address
- Pitfall #6: Mode 4 Palette Fallback
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


# ============================================================================
# Regression test for pitfall #3: PPU Default Mode Hard-coded
# ============================================================================

def test_ppu_mode_derived_from_dispcnt():
    """Regression test for pitfall #3: PPU mode must be derived from DISPCNT bits 0-2, not hard-coded.
    
    Test that setting DISPCNT to different mode values results in ppu.mode matching.
    """
    # Test all valid modes (0-5)
    for mode in range(6):
        ppu, memory = make_ppu()
        
        # Set DISPCNT to the desired mode (bits 0-2)
        dispcnt_value = mode
        memory.write_u16(0x04000000, dispcnt_value)
        
        # Create a new PPU to read the DISPCNT value
        ppu = PPU(memory)
        
        # Verify mode matches DISPCNT bits 0-2
        assert ppu.mode == mode, f"Expected mode {mode}, got {ppu.mode} for DISPCNT=0x{dispcnt_value:04X}"
    
    print("✓ test_ppu_mode_derived_from_dispcnt passed")


def test_ppu_mode_changes_mid_frame():
    """Regression test for pitfall #3: Changing DISPCNT mid-frame should change the mode.
    
    Test that modifying DISPCNT after PPU initialization updates the mode.
    """
    ppu, memory = make_ppu()
    
    # Start with mode 0
    memory.write_u16(0x04000000, 0)
    ppu = PPU(memory)
    assert ppu.mode == 0, f"Expected mode 0, got {ppu.mode}"
    
    # Change to mode 3 via write_register
    ppu.write_register(0x04000000, 3)
    assert ppu.mode == 3, f"Expected mode 3 after register write, got {ppu.mode}"
    
    # Change to mode 4
    ppu.write_register(0x04000000, 4)
    assert ppu.mode == 4, f"Expected mode 4 after register write, got {ppu.mode}"
    
    print("✓ test_ppu_mode_changes_mid_frame passed")


# ============================================================================
# Regression test for pitfall #4: Character Block Base as Number Not Address
# ============================================================================

def test_char_base_block_address_conversion():
    """Regression test for pitfall #4: Character base block must be converted to VRAM address.
    
    The BGCNT character base block (bits 2-3) must be converted to a VRAM base address
    (0x6000000 + block * 0x4000), not used as a raw block number.
    
    Test: set different char base blocks and verify the PPU reads tile data from the correct VRAM address.
    """
    # Test char base block 0 (VRAM address 0x06000000)
    ppu0, memory0 = make_ppu()
    memory0.write_u16(0x04000000, 0x0100)  # mode 0 + BG0 enable
    # BG0CNT: priority=0, char base=0, 4BPP, screen base=1
    memory0.write_u16(0x04000008, 0x0100)  # char base block 0
    
    # Write tile data at VRAM address 0x06000000 (block 0) with palette index 1 (red)
    tile_addr_0 = 0x06000000
    for i in range(32):  # 4BPP tile = 32 bytes
        memory0.write_u8(tile_addr_0 + i, 0x11)  # Both nibbles = 1
    memory0.write_u16(0x06000800, 0x0000)  # tile 0 at map entry (0,0)
    memory0.write_u16(0x05000002, 0x001F)  # palette[1] = red
    
    step_frame(ppu0)
    assert ppu0.framebuffer[0][0] == (255, 0, 0), f"Expected red from char block 0, got {ppu0.framebuffer[0][0]}"
    
    # Test char base block 1 (VRAM address 0x06004000)
    ppu1, memory1 = make_ppu()
    memory1.write_u16(0x04000000, 0x0100)  # mode 0 + BG0 enable
    # BG0CNT: priority=0, char base=1, 4BPP, screen base=1
    memory1.write_u16(0x04000008, 0x0104)  # char base block 1 (bits 2-3 = 1)
    
    # Write tile data at VRAM address 0x06004000 (block 1) with palette index 2 (green)
    tile_addr_1 = 0x06004000
    for i in range(32):  # 4BPP tile = 32 bytes
        memory1.write_u8(tile_addr_1 + i, 0x22)  # Both nibbles = 2
    memory1.write_u16(0x06000800, 0x0000)  # tile 0 at map entry (0,0)
    memory1.write_u16(0x05000004, 0x03E0)  # palette[2] = green
    
    step_frame(ppu1)
    assert ppu1.framebuffer[0][0] == (0, 255, 0), f"Expected green from char block 1, got {ppu1.framebuffer[0][0]}"
    
    # Test char base block 2 (VRAM address 0x06008000)
    ppu2, memory2 = make_ppu()
    memory2.write_u16(0x04000000, 0x0100)  # mode 0 + BG0 enable
    # BG0CNT: priority=0, char base=2, 4BPP, screen base=1
    memory2.write_u16(0x04000008, 0x0108)  # char base block 2 (bits 2-3 = 2)
    
    # Write tile data at VRAM address 0x06008000 (block 2) with palette index 3 (blue)
    tile_addr_2 = 0x06008000
    for i in range(32):  # 4BPP tile = 32 bytes
        memory2.write_u8(tile_addr_2 + i, 0x33)  # Both nibbles = 3
    memory2.write_u16(0x06000800, 0x0000)  # tile 0 at map entry (0,0)
    memory2.write_u16(0x05000006, 0x7C00)  # palette[3] = blue
    
    step_frame(ppu2)
    assert ppu2.framebuffer[0][0] == (0, 0, 255), f"Expected blue from char block 2, got {ppu2.framebuffer[0][0]}"
    
    # Test char base block 3 (VRAM address 0x0600C000)
    ppu3, memory3 = make_ppu()
    memory3.write_u16(0x04000000, 0x0100)  # mode 0 + BG0 enable
    # BG0CNT: priority=0, char base=3, 4BPP, screen base=1
    memory3.write_u16(0x04000008, 0x010C)  # char base block 3 (bits 2-3 = 3)
    
    # Write tile data at VRAM address 0x0600C000 (block 3) with palette index 4 (white)
    tile_addr_3 = 0x0600C000
    for i in range(32):  # 4BPP tile = 32 bytes
        memory3.write_u8(tile_addr_3 + i, 0x44)  # Both nibbles = 4
    memory3.write_u16(0x06000800, 0x0000)  # tile 0 at map entry (0,0)
    memory3.write_u16(0x05000008, 0x7FFF)  # palette[4] = white (max RGB)
    
    step_frame(ppu3)
    assert ppu3.framebuffer[0][0] == (255, 255, 255), f"Expected white from char block 3, got {ppu3.framebuffer[0][0]}"
    
    print("✓ test_char_base_block_address_conversion passed")


# ============================================================================
# Regression test for pitfall #6: Mode 4 Palette Fallback
# ============================================================================

def test_mode4_palette_black_fallback():
    """Regression test for pitfall #6: Mode 4 undefined palette entries must render as black.
    
    In Mode 4 (bitmap), undefined/zero palette entries must render as black (RGB 0,0,0),
    not a grayscale fallback or any other color.
    
    Test: set palette entry 0 to black, entry 1 to red, entry 2 to green.
    Set bitmap pixel 0 to index 1, pixel 1 to index 2, pixel 2 to index 0.
    Verify the framebuffer matches. Then set all palette entries to 0 and verify all pixels are black.
    """
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 4 + BG2 enable
    memory.write_u16(0x04000000, 0x0404)
    
    # Set palette: entry 0 = black, entry 1 = red, entry 2 = green
    memory.write_u16(0x05000000, 0x0000)  # palette[0] = black (0,0,0)
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x03E0)  # palette[2] = green
    
    # Write palette indices to VRAM (Mode 4 uses 8-bit palette indices)
    vram_base = 0x06000000
    memory.write_u8(vram_base + 0, 1)  # (0,0) = index 1 (red)
    memory.write_u8(vram_base + 1, 2)  # (1,0) = index 2 (green)
    memory.write_u8(vram_base + 2, 0)  # (2,0) = index 0 (black)
    
    step_frame(ppu)
    
    # Verify pixel colors
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red at (0,0), got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][1] == (0, 255, 0), f"Expected green at (1,0), got {ppu.framebuffer[0][1]}"
    assert ppu.framebuffer[0][2] == (0, 0, 0), f"Expected black at (2,0), got {ppu.framebuffer[0][2]}"
    
    # Now set all palette entries to 0 (black) and verify all pixels render as black
    memory.write_u16(0x05000000, 0x0000)  # palette[0] = black
    memory.write_u16(0x05000002, 0x0000)  # palette[1] = black
    memory.write_u16(0x05000004, 0x0000)  # palette[2] = black
    
    step_frame(ppu)
    
    # All pixels should now be black regardless of palette index
    assert ppu.framebuffer[0][0] == (0, 0, 0), f"Expected black at (0,0) with zeroed palette, got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][1] == (0, 0, 0), f"Expected black at (1,0) with zeroed palette, got {ppu.framebuffer[0][1]}"
    assert ppu.framebuffer[0][2] == (0, 0, 0), f"Expected black at (2,0) with zeroed palette, got {ppu.framebuffer[0][2]}"
    
    print("✓ test_mode4_palette_black_fallback passed")


def test_mode4_undefined_palette_is_black():
    """Regression test for pitfall #6: Undefined (unwritten) palette entries must be black.
    
    Test that palette entries that have not been explicitly written (remain at 0)
    render as black, not some other fallback color.
    """
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 4 + BG2 enable
    memory.write_u16(0x04000000, 0x0404)
    
    # Do NOT write any palette entries - they should remain at 0 (black)
    # Write palette index 5 to VRAM (which should be undefined/black)
    vram_base = 0x06000000
    memory.write_u8(vram_base + 0, 5)  # (0,0) = index 5 (undefined, should be black)
    memory.write_u8(vram_base + 1, 128)  # (1,0) = index 128 (undefined, should be black)
    memory.write_u8(vram_base + 2, 255)  # (2,0) = index 255 (undefined, should be black)
    
    step_frame(ppu)
    
    # All undefined palette entries should render as black
    assert ppu.framebuffer[0][0] == (0, 0, 0), f"Expected black for undefined palette index 5, got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][1] == (0, 0, 0), f"Expected black for undefined palette index 128, got {ppu.framebuffer[0][1]}"
    assert ppu.framebuffer[0][2] == (0, 0, 0), f"Expected black for undefined palette index 255, got {ppu.framebuffer[0][2]}"
    
    print("✓ test_mode4_undefined_palette_is_black passed")


if __name__ == "__main__":
    test_ppu_mode_derived_from_dispcnt()
    test_ppu_mode_changes_mid_frame()
    test_char_base_block_address_conversion()
    test_mode4_palette_black_fallback()
    test_mode4_undefined_palette_is_black()
    print("\nAll 5 PPU regression tests passed!")