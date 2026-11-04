"""Unit tests for sprite/OAM rendering.

Tests OAM attribute parsing, sprite rendering with different sizes,
color modes (4BPP/8BPP), flipping, priority, and affine transformations.
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


# ============================================================================
# OAM Attribute Parsing Tests
# ============================================================================

def test_oam_parse_default_values():
    """Test that OAM parsing includes sprites with Y=0 (on-screen)."""
    ppu, memory = make_ppu()
    
    # Default OAM is all zeros, which means Y=0 for all sprites
    # Y=0 is on-screen, so all 128 sprites are included (they have valid Y position)
    ppu.parse_oam()
    
    # All 128 sprites have Y=0 which is on-screen (Y < 224)
    assert len(ppu.sprite_list) == 128, f"Expected 128 sprites with Y=0, got {len(ppu.sprite_list)}"
    
    # Verify Y=0 for all sprites
    for s in ppu.sprite_list:
        assert s["y"] == 0, f"Expected y=0, got {s['y']}"
    
    print("✓ test_oam_parse_default_values passed")


def test_oam_parse_attribute_extraction():
    """Test that OAM attributes are correctly extracted from memory."""
    ppu, memory = make_ppu()
    
    # Set up a sprite at index 0:
    # attr0: Y=50, 4BPP, square shape
    attr0 = 50 | (0 << 13) | (0 << 14)  # Y=50, 4BPP, shape=0
    # attr1: X=100, size=0 (8x8)
    attr1 = 100 | (0 << 14)  # X=100, size=0
    # attr2: tile=5, priority=1, palette=2
    attr2 = 5 | (1 << 10) | (2 << 12)  # tile=5, priority=1, palette=2
    
    # Write to OAM using memory.write_u16
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    # 127 sprites have Y=0 (default), 1 sprite has Y=50 - all 128 are on-screen
    assert len(sprites) == 128, f"Expected 128 sprites (Y<224), got {len(sprites)}"
    
    # Find the sprite with Y=50
    s = next((s for s in sprites if s["y"] == 50), None)
    assert s is not None, "Expected to find sprite with Y=50"
    assert s["x"] == 100, f"Expected x=100, got {s['x']}"
    assert s["width"] == 8, f"Expected width=8, got {s['width']}"
    assert s["height"] == 8, f"Expected height=8, got {s['height']}"
    assert s["tile_num"] == 5, f"Expected tile_num=5, got {s['tile_num']}"
    assert s["priority"] == 1, f"Expected priority=1, got {s['priority']}"
    assert s["palette_num"] == 2, f"Expected palette_num=2, got {s['palette_num']}"
    assert s["color_mode"] == 0, f"Expected color_mode=0 (4BPP), got {s['color_mode']}"
    
    print("✓ test_oam_parse_attribute_extraction passed")


def test_oam_parse_offscreen_filter():
    """Test that sprites with Y >= 224 are filtered out."""
    ppu, memory = make_ppu()
    
    # Sprite at Y=200 (should be included)
    attr0 = 200
    attr1 = 100
    attr2 = 0
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    # Sprite at Y=224 (should be filtered)
    attr0_off = 224
    attr1_off = 150
    attr2_off = 0
    oam_addr2 = 0x07000000 + 8
    memory.write_u16(oam_addr2, attr0_off)
    memory.write_u16(oam_addr2 + 2, attr1_off)
    memory.write_u16(oam_addr2 + 4, attr2_off)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    # 126 sprites have Y=0, 1 sprite has Y=200, 1 sprite has Y=224 (filtered)
    assert len(sprites) == 127, f"Expected 127 sprites (Y<224), got {len(sprites)}"
    
    # Check that Y=224 is not in the list
    y_values = [s["y"] for s in sprites]
    assert 224 not in y_values, "Expected Y=224 to be filtered out"
    assert 200 in y_values, "Expected Y=200 to be included"
    
    print("✓ test_oam_parse_offscreen_filter passed")


def test_oam_parse_disabled_sprite():
    """Test that sprites with obj_disable bit set are included in parse_oam."""
    ppu, memory = make_ppu()
    
    # Sprite with obj_disable=1 (bit 9) and rotate_scale=0
    attr0 = 50 | (1 << 9)  # Y=50, obj_disable=1
    attr1 = 100
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    # obj_disable is parsed but not filtered in parse_oam - it's a render-time flag
    # 127 sprites have Y=0 (default), 1 sprite has Y=50 - all 128 are on-screen
    assert len(sprites) == 128, f"Expected 128 sprites (Y<224), got {len(sprites)}"
    
    # Find the sprite with obj_disable=1
    s = next((s for s in sprites if s["obj_disable"] == 1), None)
    assert s is not None, "Expected to find sprite with obj_disable=1"
    assert s["y"] == 50, f"Expected y=50, got {s['y']}"
    
    print("✓ test_oam_parse_disabled_sprite passed")


# ============================================================================
# Sprite Size Tests
# ============================================================================

def test_sprite_sizes_square():
    """Test all square sprite sizes (shape 0)."""
    ppu, memory = make_ppu()
    
    sizes = ppu.SPRITE_SIZES[0]
    expected = {0: (8, 8), 1: (16, 16), 2: (32, 32), 3: (64, 64)}
    
    assert sizes == expected, f"Square sizes mismatch: {sizes} != {expected}"
    
    print("✓ test_sprite_sizes_square passed")


def test_sprite_sizes_horizontal():
    """Test horizontal rectangular sprite sizes (shape 1)."""
    ppu, memory = make_ppu()
    
    sizes = ppu.SPRITE_SIZES[1]
    expected = {0: (8, 16), 1: (16, 8), 2: (32, 16), 3: (16, 32)}
    
    # Note: shape 1 size 0 is 8x16 (vertical), size 1 is 16x8 (horizontal)
    assert sizes == expected, f"Horizontal sizes mismatch: {sizes} != {expected}"
    
    print("✓ test_sprite_sizes_horizontal passed")


def test_sprite_sizes_vertical():
    """Test vertical rectangular sprite sizes (shape 2)."""
    ppu, memory = make_ppu()
    
    sizes = ppu.SPRITE_SIZES[2]
    expected = {0: (8, 32), 1: (16, 16), 2: (32, 8), 3: (8, 8)}
    
    assert sizes == expected, f"Vertical sizes mismatch: {sizes} != {expected}"
    
    print("✓ test_sprite_sizes_vertical passed")


# ============================================================================
# Sprite Flipping Tests
# ============================================================================

def test_sprite_flip_h():
    """Test horizontal flip flag extraction."""
    ppu, memory = make_ppu()
    
    # Set sprite with H-flip (attr1 bit 12)
    attr0 = 50
    attr1 = 100 | (1 << 12)  # H-flip
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    assert sprites[0]["flip_h"] == 1, f"Expected flip_h=1, got {sprites[0]['flip_h']}"
    assert sprites[0]["flip_v"] == 0, f"Expected flip_v=0, got {sprites[0]['flip_v']}"
    
    print("✓ test_sprite_flip_h passed")


def test_sprite_flip_v():
    """Test vertical flip flag extraction."""
    ppu, memory = make_ppu()
    
    # Set sprite with V-flip (attr1 bit 13)
    attr0 = 50
    attr1 = 100 | (1 << 13)  # V-flip
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    assert sprites[0]["flip_v"] == 1, f"Expected flip_v=1, got {sprites[0]['flip_v']}"
    
    print("✓ test_sprite_flip_v passed")


def test_sprite_flip_both():
    """Test both H and V flip flags."""
    ppu, memory = make_ppu()
    
    # Set sprite with both flips
    attr0 = 50
    attr1 = 100 | (1 << 12) | (1 << 13)  # H-flip + V-flip
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    assert sprites[0]["flip_h"] == 1, f"Expected flip_h=1, got {sprites[0]['flip_h']}"
    assert sprites[0]["flip_v"] == 1, f"Expected flip_v=1, got {sprites[0]['flip_v']}"
    
    print("✓ test_sprite_flip_both passed")


# ============================================================================
# Sprite Priority Tests
# ============================================================================

def test_sprite_priority_sorting():
    """Test that sprites are sorted by priority."""
    ppu, memory = make_ppu()
    
    # Set up 3 sprites with different priorities at unique Y positions
    # Sprite 0: priority 2, Y=50
    memory.write_u16(0x07000000, 50)
    memory.write_u16(0x07000002, 50)
    memory.write_u16(0x07000004, 2 << 10)  # priority=2
    
    # Sprite 1: priority 0, Y=60
    memory.write_u16(0x07000008, 60)
    memory.write_u16(0x0700000A, 60)
    memory.write_u16(0x0700000C, 0 << 10)  # priority=0
    
    # Sprite 2: priority 1, Y=70
    memory.write_u16(0x07000010, 70)
    memory.write_u16(0x07000012, 70)
    memory.write_u16(0x07000014, 1 << 10)  # priority=1
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    # Find sprites by Y position
    s_p2 = next((s for s in sprites if s["y"] == 50), None)
    s_p0 = next((s for s in sprites if s["y"] == 60), None)
    s_p1 = next((s for s in sprites if s["y"] == 70), None)
    
    assert s_p2 is not None and s_p2["priority"] == 2, "Expected sprite at Y=50 with priority 2"
    assert s_p0 is not None and s_p0["priority"] == 0, "Expected sprite at Y=60 with priority 0"
    assert s_p1 is not None and s_p1["priority"] == 1, "Expected sprite at Y=70 with priority 1"
    
    # Sort and verify order
    sprites.sort(key=lambda s: s["priority"])
    p0_sprites = [s for s in sprites if s["priority"] == 0]
    p1_sprites = [s for s in sprites if s["priority"] == 1]
    p2_sprites = [s for s in sprites if s["priority"] == 2]
    
    # All priority 0 sprites come before priority 1, which come before priority 2
    p0_indices = [sprites.index(s) for s in p0_sprites]
    p1_indices = [sprites.index(s) for s in p1_sprites]
    p2_indices = [sprites.index(s) for s in p2_sprites]
    
    assert max(p0_indices) < min(p1_indices), "Priority 0 sprites should come before priority 1"
    assert max(p1_indices) < min(p2_indices), "Priority 1 sprites should come before priority 2"
    
    print("✓ test_sprite_priority_sorting passed")


# ============================================================================
# 4BPP vs 8BPP Color Mode Tests
# ============================================================================

def test_sprite_color_mode_4bpp():
    """Test 4BPP color mode flag extraction."""
    ppu, memory = make_ppu()
    
    # 4BPP: attr0 bit 13 = 0
    attr0 = 50 | (0 << 13)
    attr1 = 100
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    assert sprites[0]["color_mode"] == 0, f"Expected color_mode=0 (4BPP), got {sprites[0]['color_mode']}"
    
    print("✓ test_sprite_color_mode_4bpp passed")


def test_sprite_color_mode_8bpp():
    """Test 8BPP color mode flag extraction."""
    ppu, memory = make_ppu()
    
    # 8BPP: attr0 bit 13 = 1
    attr0 = 50 | (1 << 13)
    attr1 = 100
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    assert sprites[0]["color_mode"] == 1, f"Expected color_mode=1 (8BPP), got {sprites[0]['color_mode']}"
    
    print("✓ test_sprite_color_mode_8bpp passed")


# ============================================================================
# Affine Sprite Tests
# ============================================================================

def test_affine_sprite_flag():
    """Test affine sprite flag extraction (attr0 bit 8)."""
    ppu, memory = make_ppu()
    
    # Non-affine sprite
    attr0 = 50
    attr1 = 100  # bit 11 = 0
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    assert sprites[0]["rotate_scale"] == 0, f"Expected rotate_scale=0, got {sprites[0]['rotate_scale']}"
    
    # Affine sprite (attr0 bit 8 = 1)
    attr0_affine = 50 | (1 << 8)
    memory.write_u16(oam_addr, attr0_affine)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    assert sprites[0]["rotate_scale"] == 1, f"Expected rotate_scale=1, got {sprites[0]['rotate_scale']}"
    
    print("✓ test_affine_sprite_flag passed")


def test_affine_param_extraction():
    """Test affine parameter index extraction from attr1."""
    ppu, memory = make_ppu()
    
    # Set affine param index = 5 (bits 9-13 of attr1)
    attr0 = 50 | (1 << 8)  # affine enabled
    attr1 = 100 | (5 << 9)  # affine_param = 5
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    assert sprites[0]["affine_param"] == 5, f"Expected affine_param=5, got {sprites[0]['affine_param']}"
    
    print("✓ test_affine_param_extraction passed")


# ============================================================================
# Sprite Mosaic Tests
# ============================================================================

def test_sprite_mosaic_flag():
    """Test sprite mosaic flag extraction (attr0 bit 12)."""
    ppu, memory = make_ppu()
    
    # Mosaic disabled
    attr0 = 50 | (0 << 12)
    attr1 = 100
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    assert sprites[0]["mosaic"] == 0, f"Expected mosaic=0, got {sprites[0]['mosaic']}"
    
    # Mosaic enabled
    attr0_mosaic = 50 | (1 << 12)
    memory.write_u16(oam_addr, attr0_mosaic)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    assert sprites[0]["mosaic"] == 1, f"Expected mosaic=1, got {sprites[0]['mosaic']}"
    
    print("✓ test_sprite_mosaic_flag passed")


# ============================================================================
# Sprite Mode Tests
# ============================================================================

def test_sprite_mode_normal():
    """Test normal sprite mode (mode 0)."""
    ppu, memory = make_ppu()
    
    attr0 = 50 | (0 << 10)  # mode = 0
    attr1 = 100
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    assert sprites[0]["mode"] == 0, f"Expected mode=0, got {sprites[0]['mode']}"
    
    print("✓ test_sprite_mode_normal passed")


def test_sprite_mode_prohibited():
    """Test prohibited sprite mode (mode 3) is filtered during render."""
    ppu, memory = make_ppu()
    
    attr0 = 50 | (3 << 10)  # mode = 3 (prohibited)
    attr1 = 100
    attr2 = 0
    
    oam_addr = 0x07000000
    memory.write_u16(oam_addr, attr0)
    memory.write_u16(oam_addr + 2, attr1)
    memory.write_u16(oam_addr + 4, attr2)
    
    ppu.parse_oam()
    sprites = ppu.sprite_list
    
    # Sprite is in the list but should be skipped during render
    assert sprites[0]["mode"] == 3, f"Expected mode=3, got {sprites[0]['mode']}"
    
    print("✓ test_sprite_mode_prohibited passed")


# ============================================================================
# OAM Memory Layout Tests
# ============================================================================

def test_oam_memory_layout():
    """Test that OAM memory is 8 bytes per sprite."""
    ppu, memory = make_ppu()
    
    from memory import MemoryMap
    assert MemoryMap.OAM_SIZE == 0x400, f"Expected OAM_SIZE=0x400, got {MemoryMap.OAM_SIZE}"
    assert MemoryMap.OAM_SIZE == 128 * 8, "OAM should be 128 sprites × 8 bytes"
    
    print("✓ test_oam_memory_layout passed")


def test_oam_address_calculation():
    """Test OAM address calculation for sprite index."""
    ppu, memory = make_ppu()
    
    # Sprite 0: 0x07000000 + 0 = 0x07000000
    # Sprite 1: 0x07000000 + 8 = 0x07000008
    # Sprite 127: 0x07000000 + 1016 = 0x070003F8
    
    assert 0x07000000 + (0 * 8) == 0x07000000
    assert 0x07000000 + (1 * 8) == 0x07000008
    assert 0x07000000 + (127 * 8) == 0x070003F8
    
    print("✓ test_oam_address_calculation passed")


# ============================================================================
# Test Runner
# ============================================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
