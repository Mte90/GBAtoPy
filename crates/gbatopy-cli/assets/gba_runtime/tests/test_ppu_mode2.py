"""PPU Mode 2 (dual affine backgrounds) unit tests for GBAtoPy.

Tests cover Mode 2 rendering with two affine backgrounds (BG2 and BG3),
including identity transforms, scaling, disable flags, and priority ordering.
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


def test_mode2_renders_bg2_identity():
    """Mode 2: BG2 with identity affine matrix renders correctly."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 2 + BG2 enable (mode 2 = 0x0002, BG2 enable = 0x0400)
    memory.write_u16(0x04000000, 0x0402)
    
    # Set BG2CNT: priority=0, char base=0, 8BPP, screen base=1, size=1 (256x256)
    memory.write_u16(0x0400000C, 0x4180)
    
    ppu = PPU(memory)
    
    # Set identity affine params for BG2: PA=256, PD=256 (1.0 in 16.8 fixed point)
    memory.write_u16(0x04000020, 256)  # BG2PA
    memory.write_u16(0x04000022, 0)    # BG2PB
    memory.write_u16(0x04000024, 0)    # BG2PC
    memory.write_u16(0x04000026, 256)  # BG2PD
    memory.write_u32(0x04000028, 0)    # BG2X
    memory.write_u32(0x0400002C, 0)    # BG2X/Y
    memory.write_u32(0x04000030, 0)    # BG2Y
    
    # Write tile data: tile 0 is 64 bytes (8BPP), fill with palette index 1
    tile_addr = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr + i, 1)
    
    # Write affine tilemap: screen base 1 = 0x06000800, fill with tile 0
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)
    
    # Set palette[1] = red
    memory.write_u16(0x05000002, 0x001F)
    
    step_frame(ppu)
    
    # Identity transform = direct passthrough
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red from BG2, got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode2_renders_bg2_identity passed")


def test_mode2_renders_bg3_identity():
    """Mode 2: BG3 with identity affine matrix renders correctly."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 2 + BG3 enable (mode 2 = 0x0002, BG3 enable = 0x0800)
    memory.write_u16(0x04000000, 0x0802)
    
    # Set BG3CNT: priority=0, char base=0, 8BPP, screen base=1, size=1 (256x256)
    memory.write_u16(0x0400000E, 0x4180)
    
    ppu = PPU(memory)
    
    # Set identity affine params for BG3: PA=256, PD=256
    memory.write_u16(0x04000030, 256)  # BG3PA
    memory.write_u16(0x04000032, 0)    # BG3PB
    memory.write_u16(0x04000034, 0)    # BG3PC
    memory.write_u16(0x04000036, 256)  # BG3PD
    memory.write_u32(0x04000038, 0)    # BG3X
    memory.write_u32(0x0400003A, 0)    # BG3X/Y
    memory.write_u32(0x0400003C, 0)    # BG3Y
    
    # Write tile data: tile 0 is 64 bytes (8BPP), fill with palette index 2
    tile_addr = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr + i, 2)
    
    # Write affine tilemap: screen base 1 = 0x06000800, fill with tile 0
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)
    
    # Set palette[2] = blue
    memory.write_u16(0x05000004, 0x7C00)
    
    step_frame(ppu)
    
    # Identity transform = direct passthrough
    assert ppu.framebuffer[0][0] == (0, 0, 255), f"Expected blue from BG3, got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode2_renders_bg3_identity passed")


def test_mode2_renders_both_bg2_bg3():
    """Mode 2: Both BG2 and BG3 enabled with identity matrices."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 2 + BG2 + BG3 enable
    memory.write_u16(0x04000000, 0x0C02)
    
    # Set BG2CNT: priority=0, char base=0, 8BPP, screen base=1, size=1
    memory.write_u16(0x0400000C, 0x4180)
    # Set BG3CNT: priority=1, char base=1, 8BPP, screen base=2, size=1
    memory.write_u16(0x0400000E, 0x4184 | (1 << 8))  # char base=1, screen base=2
    
    ppu = PPU(memory)
    
    # Set identity affine params for BG2
    memory.write_u16(0x04000020, 256)  # BG2PA
    memory.write_u16(0x04000022, 0)
    memory.write_u16(0x04000024, 0)
    memory.write_u16(0x04000026, 256)  # BG2PD
    memory.write_u32(0x04000028, 0)
    memory.write_u32(0x0400002C, 0)
    memory.write_u32(0x04000030, 0)
    
    # Set identity affine params for BG3
    memory.write_u16(0x04000030, 256)  # BG3PA
    memory.write_u16(0x04000032, 0)
    memory.write_u16(0x04000034, 0)
    memory.write_u16(0x04000036, 256)  # BG3PD
    memory.write_u32(0x04000038, 0)
    memory.write_u32(0x0400003A, 0)
    memory.write_u32(0x0400003C, 0)
    
    # Write BG2 tile data: tile 0 at char base 0 with palette index 1 (red)
    tile_addr_bg2 = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr_bg2 + i, 1)
    
    # Write BG2 tilemap
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)
    
    # Write BG3 tile data: tile 0 at char base 1 (0x06004000) with palette index 2 (green)
    tile_addr_bg3 = 0x06004000
    for i in range(64):
        memory.write_u8(tile_addr_bg3 + i, 2)
    
    # Write BG3 tilemap at screen base 2 (0x06001000)
    for i in range(64):
        memory.write_u8(0x06001000 + i, 0)
    
    # Set palette: index 1 = red, index 2 = green
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x03E0)  # palette[2] = green
    
    step_frame(ppu)
    
    # BG2 has priority 0 (higher), BG3 has priority 1, so BG2 should be on top
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red (BG2 on top), got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode2_renders_both_bg2_bg3 passed")


def test_mode2_bg2_disabled_renders_only_bg3():
    """Mode 2: BG2 disabled, only BG3 renders."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 2 + BG3 enable only (BG2 disabled)
    # 0x0802 = mode 2 (0x0002) + BG3 enable (0x0800)
    memory.write_u16(0x04000000, 0x0802)
    
    # Set BG2CNT and BG3CNT (but BG2 is disabled in DISPCNT)
    memory.write_u16(0x0400000C, 0x4180)  # BG2 - won't render
    memory.write_u16(0x0400000E, 0x4184 | (2 << 8))  # BG3: char base=1, screen base=2
    
    # Create PPU AFTER setting DISPCNT so it reads the correct enable flags
    ppu = PPU(memory)
    
    # Set identity affine params for both
    memory.write_u16(0x04000020, 256)  # BG2PA
    memory.write_u16(0x04000026, 256)  # BG2PD
    memory.write_u16(0x04000030, 256)  # BG3PA
    memory.write_u16(0x04000036, 256)  # BG3PD
    memory.write_u32(0x04000028, 0)
    memory.write_u32(0x0400002C, 0)
    memory.write_u32(0x04000038, 0)
    memory.write_u32(0x0400003C, 0)
    
    # Write BG2 tile with red (won't be rendered since BG2 is disabled)
    tile_addr_bg2 = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr_bg2 + i, 1)
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)  # BG2 tilemap at screen base 1
    
    # Write BG3 tile with blue at a DIFFERENT char block
    # BG3 uses char base 1 (0x06004000) and screen base 2 (0x06001000)
    tile_addr_bg3 = 0x06004000
    for i in range(64):
        memory.write_u8(tile_addr_bg3 + i, 2)
    for i in range(64):
        memory.write_u8(0x06001000 + i, 0)  # BG3 tilemap at screen base 2
    
    # Set palette: index 1 = red, index 2 = blue
    memory.write_u16(0x05000002, 0x001F)  # red
    memory.write_u16(0x05000004, 0x7C00)  # blue
    
    step_frame(ppu)
    
    # BG2 disabled, so only BG3 (blue) should render
    assert ppu.framebuffer[0][0] == (0, 0, 255), f"Expected blue (BG3 only), got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode2_bg2_disabled_renders_only_bg3 passed")


def test_mode2_bg3_disabled_renders_only_bg2():
    """Mode 2: BG3 disabled, only BG2 renders."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 2 + BG2 enable only (BG3 disabled)
    memory.write_u16(0x04000000, 0x0402)
    
    # Set BG2CNT and BG3CNT
    memory.write_u16(0x0400000C, 0x4180)  # BG2
    memory.write_u16(0x0400000E, 0x4180)  # BG3
    
    ppu = PPU(memory)
    
    # Set identity affine params for both
    memory.write_u16(0x04000020, 256)  # BG2PA
    memory.write_u16(0x04000026, 256)  # BG2PD
    memory.write_u16(0x04000030, 256)  # BG3PA
    memory.write_u16(0x04000036, 256)  # BG3PD
    memory.write_u32(0x04000028, 0)
    memory.write_u32(0x0400002C, 0)
    memory.write_u32(0x04000038, 0)
    memory.write_u32(0x0400003C, 0)
    
    # Write BG2 tile with red
    tile_addr_bg2 = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr_bg2 + i, 1)
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)
    
    # Write BG3 tile with green
    tile_addr_bg3 = 0x06000000 + 64
    for i in range(64):
        memory.write_u8(tile_addr_bg3 + i, 2)
    for i in range(64):
        memory.write_u8(0x06000800 + 64 + i, 0)
    
    # Set palette: index 1 = red, index 2 = green
    memory.write_u16(0x05000002, 0x001F)  # red
    memory.write_u16(0x05000004, 0x03E0)  # green
    
    step_frame(ppu)
    
    # BG3 disabled, so only BG2 (red) should render
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red (BG2 only), got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode2_bg3_disabled_renders_only_bg2 passed")


def test_mode2_both_disabled_renders_backdrop():
    """Mode 2: Both BG2 and BG3 disabled, renders backdrop color."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 2 only (no BGs enabled)
    memory.write_u16(0x04000000, 0x0002)
    
    ppu = PPU(memory)
    
    # Set palette entry 0 to green (backdrop color)
    memory.write_u16(0x05000000, 0x03E0)
    
    step_frame(ppu)
    
    # All pixels should be backdrop (green)
    for y in range(160):
        for x in range(240):
            assert ppu.framebuffer[y][x] == (0, 255, 0), f"Expected green backdrop at ({x},{y}), got {ppu.framebuffer[y][x]}"
    
    print("✓ test_mode2_both_disabled_renders_backdrop passed")


def test_mode2_bg2_2x_scale():
    """Mode 2: BG2 with 2x scale affine transform (PA=128, PD=128)."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 2 + BG2 enable
    memory.write_u16(0x04000000, 0x0402)
    
    # Set BG2CNT: priority=0, char base=0, 8BPP, screen base=1, size=1
    memory.write_u16(0x0400000C, 0x4180)
    
    ppu = PPU(memory)
    
    # Set 2x scaling: PA=128, PD=128 (0.5 in 16.8 fixed point)
    memory.write_u16(0x04000020, 128)  # BG2PA
    memory.write_u16(0x04000022, 0)    # BG2PB
    memory.write_u16(0x04000024, 0)    # BG2PC
    memory.write_u16(0x04000026, 128)  # BG2PD
    memory.write_u32(0x04000028, 0)    # BG2X
    memory.write_u32(0x0400002C, 0)    # BG2X/Y
    memory.write_u32(0x04000030, 0)    # BG2Y
    
    # Write tile data: tile 0 with red, tile 1 with blue
    tile_addr = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr + i, 1)  # tile 0 = red
    for i in range(64):
        memory.write_u8(tile_addr + 64 + i, 2)  # tile 1 = blue
    
    # Write tilemap: all tile 0
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)
    
    # Set palette: index 1 = red, index 2 = blue
    memory.write_u16(0x05000002, 0x001F)  # red
    memory.write_u16(0x05000004, 0x7C00)  # blue
    
    step_frame(ppu)
    
    # 2x scale: each source pixel appears 2x on screen
    # First 2 pixels should be red (from tile 0)
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red, got {ppu.framebuffer[0][0]}"
    assert ppu.framebuffer[0][1] == (255, 0, 0), f"Expected red (scaled), got {ppu.framebuffer[0][1]}"
    
    print("✓ test_mode2_bg2_2x_scale passed")


def test_mode2_bg_priority_ordering():
    """Mode 2: BG2 and BG3 with different priority bits, verify correct z-order."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    
    # Set DISPCNT to mode 2 + BG2 + BG3 enable
    memory.write_u16(0x04000000, 0x0C02)
    
    # Set BG2CNT: priority=1 (lower)
    memory.write_u16(0x0400000C, 0x4180 | 1)  # priority = 1
    # Set BG3CNT: priority=0 (higher)
    memory.write_u16(0x0400000E, 0x4184)  # priority = 0, char base=1
    
    ppu = PPU(memory)
    
    # Set identity affine params for both
    memory.write_u16(0x04000020, 256)  # BG2PA
    memory.write_u16(0x04000026, 256)  # BG2PD
    memory.write_u16(0x04000030, 256)  # BG3PA
    memory.write_u16(0x04000036, 256)  # BG3PD
    memory.write_u32(0x04000028, 0)
    memory.write_u32(0x0400002C, 0)
    memory.write_u32(0x04000038, 0)
    memory.write_u32(0x0400003C, 0)
    
    # Write BG2 tile with red
    tile_addr_bg2 = 0x06000000
    for i in range(64):
        memory.write_u8(tile_addr_bg2 + i, 1)
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)
    
    # Write BG3 tile with blue at char base 1
    tile_addr_bg3 = 0x06004000
    for i in range(64):
        memory.write_u8(tile_addr_bg3 + i, 2)
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)
    
    # Set palette: index 1 = red, index 2 = blue
    memory.write_u16(0x05000002, 0x001F)  # red
    memory.write_u16(0x05000004, 0x7C00)  # blue
    
    step_frame(ppu)
    
    # BG3 has priority 0 (higher), BG2 has priority 1 (lower), so BG3 should be on top
    assert ppu.framebuffer[0][0] == (0, 0, 255), f"Expected blue (BG3 on top), got {ppu.framebuffer[0][0]}"
    
    print("✓ test_mode2_bg_priority_ordering passed")


if __name__ == "__main__":
    test_mode2_renders_bg2_identity()
    test_mode2_renders_bg3_identity()
    test_mode2_renders_both_bg2_bg3()
    test_mode2_bg2_disabled_renders_only_bg3()
    test_mode2_bg3_disabled_renders_only_bg2()
    test_mode2_both_disabled_renders_backdrop()
    test_mode2_bg2_2x_scale()
    test_mode2_bg_priority_ordering()
    print("\nAll 8 PPU Mode 2 tests passed!")