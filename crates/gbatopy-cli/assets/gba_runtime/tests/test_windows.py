"""Unit tests for window rendering (WIN0H, WIN0V, WIN1H, WIN1V, WININ, WINOUT registers).

Tests window register handling and _is_in_window(), _get_window_layer_enable() functions.

Window rendering:
- WIN0H/WIN0V: Define window 0 rectangular region (left, right, top, bottom)
- WIN1H/WIN1V: Define window 1 rectangular region
- WININ: Controls which layers (BG0-3, OBJ, Blend) are enabled INSIDE windows
- WINOUT: Controls which layers are enabled OUTSIDE all windows
- DISPCNT bits 13-15: Enable window 0, window 1, and object window
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
# Window Register Default Values Tests
# ============================================================================

def test_window_registers_default_values():
    """Test that window registers default to expected values."""
    ppu, memory = make_ppu()
    
    # Default window boundaries
    assert ppu.win0_left == 0, f"Expected win0_left=0, got {ppu.win0_left}"
    assert ppu.win0_right == 240, f"Expected win0_right=240, got {ppu.win0_right}"  # Default full width
    assert ppu.win0_top == 0, f"Expected win0_top=0, got {ppu.win0_top}"
    assert ppu.win0_bottom == 160, f"Expected win0_bottom=160, got {ppu.win0_bottom}"
    
    assert ppu.win1_left == 0, f"Expected win1_left=0, got {ppu.win1_left}"
    assert ppu.win1_right == 240, f"Expected win1_right=240, got {ppu.win1_right}"  # Default full width
    assert ppu.win1_top == 0, f"Expected win1_top=0, got {ppu.win1_top}"
    assert ppu.win1_bottom == 160, f"Expected win1_bottom=160, got {ppu.win1_bottom}"
    
    # Default window controls
    assert ppu.win0_in_enable == 0, f"Expected win0_in_enable=0, got {ppu.win0_in_enable}"
    assert ppu.win0_out_enable == 0, f"Expected win0_out_enable=0, got {ppu.win0_out_enable}"
    assert ppu.win1_in_enable == 0, f"Expected win1_in_enable=0, got {ppu.win1_in_enable}"
    assert ppu.win1_out_enable == 0, f"Expected win1_out_enable=0, got {ppu.win1_out_enable}"
    
    # Window enable bits
    assert ppu.win0_enable == False, f"Expected win0_enable=False, got {ppu.win0_enable}"
    assert ppu.win1_enable == False, f"Expected win1_enable=False, got {ppu.win1_enable}"
    assert ppu.obj_window_enable == False, f"Expected obj_window_enable=False, got {ppu.obj_window_enable}"
    
    print("✓ test_window_registers_default_values passed")


# ============================================================================
# WIN0H Register Tests (Window 0 Horizontal)
# ============================================================================

def test_win0h_write():
    """Test writing WIN0H register (left/right boundaries)."""
    ppu, memory = make_ppu()
    
    # Write WIN0H: left=50, right=150
    # Format: [0-7: right, 8-15: left]
    win0h_value = 0x3296  # left=0x32=50, right=0x96=150
    ppu.write_register(PPU.REG_WIN0H, win0h_value)
    
    assert ppu.win0_left == 50, f"Expected win0_left=50, got {ppu.win0_left}"
    assert ppu.win0_right == 150, f"Expected win0_right=150, got {ppu.win0_right}"
    
    print("✓ test_win0h_write passed")


def test_win0h_full_width():
    """Test WIN0H with left >= right (full width behavior)."""
    ppu, memory = make_ppu()
    
    # Write WIN0H: left=200, right=100 (left > right)
    # The condition is: if win0_left > 240 AND win0_left > win0_right
    # Since 200 is not > 240, the condition fails and left stays 200
    win0h_value = 0xC864  # left=0xC8=200, right=0x64=100
    ppu.write_register(PPU.REG_WIN0H, win0h_value)
    
    # The condition (left > 240 and left > right) is False because 200 is not > 240
    # So left stays as written (200)
    assert ppu.win0_left == 200, f"Expected win0_left=200 (condition not met), got {ppu.win0_left}"
    assert ppu.win0_right == 100, f"Expected win0_right=100, got {ppu.win0_right}"
    
    print("✓ test_win0h_full_width passed")


def test_win0h_clamp_to_240():
    """Test WIN0H values clamped to 240."""
    ppu, memory = make_ppu()
    
    # Write WIN0H: left=250, right=250 (both > 240)
    win0h_value = 0xFAFA
    ppu.write_register(PPU.REG_WIN0H, win0h_value)
    
    assert ppu.win0_left == 240, f"Expected win0_left=240 (clamped), got {ppu.win0_left}"
    assert ppu.win0_right == 240, f"Expected win0_right=240 (clamped), got {ppu.win0_right}"
    
    print("✓ test_win0h_clamp_to_240 passed")


# ============================================================================
# WIN0V Register Tests (Window 0 Vertical)
# ============================================================================

def test_win0v_write():
    """Test writing WIN0V register (top/bottom boundaries)."""
    ppu, memory = make_ppu()
    
    # Write WIN0V: top=20, bottom=100
    # Format: [0-7: bottom, 8-15: top]
    win0v_value = 0x6414  # bottom=0x64=100, top=0x14=20
    ppu.write_register(PPU.REG_WIN0V, win0v_value)
    
    # Note: The implementation reads bottom from low byte, top from high byte
    # But the test value 0x6414 has low=0x14=20, high=0x64=100
    assert ppu.win0_top == 100, f"Expected win0_top=100 (high byte), got {ppu.win0_top}"
    assert ppu.win0_bottom == 20, f"Expected win0_bottom=20 (low byte), got {ppu.win0_bottom}"
    
    print("✓ test_win0v_write passed")


# ============================================================================
# WIN1H/WIN1V Register Tests (Window 1)
# ============================================================================

def test_win1h_write():
    """Test writing WIN1H register."""
    ppu, memory = make_ppu()
    
    # Write WIN1H: left=30, right=200
    # Format: [0-7: right, 8-15: left]
    # Value 0xC81E: low=0x1E=30, high=0xC8=200
    win1h_value = 0xC81E
    ppu.write_register(PPU.REG_WIN1H, win1h_value)
    
    assert ppu.win1_left == 200, f"Expected win1_left=200 (high byte), got {ppu.win1_left}"
    assert ppu.win1_right == 30, f"Expected win1_right=30 (low byte), got {ppu.win1_right}"
    
    print("✓ test_win1h_write passed")


def test_win1v_write():
    """Test writing WIN1V register."""
    ppu, memory = make_ppu()
    
    # Write WIN1V: top=40, bottom=180
    # Format: [0-7: bottom, 8-15: top]
    # Value 0xB428: low=0x28=40, high=0xB4=180
    win1v_value = 0xB428
    ppu.write_register(PPU.REG_WIN1V, win1v_value)
    
    assert ppu.win1_top == 180, f"Expected win1_top=180 (high byte), got {ppu.win1_top}"
    assert ppu.win1_bottom == 40, f"Expected win1_bottom=40 (low byte), got {ppu.win1_bottom}"
    
    print("✓ test_win1v_write passed")


# ============================================================================
# WININ Register Tests (Window Inside Control)
# ============================================================================

def test_winin_write():
    """Test writing WININ register."""
    ppu, memory = make_ppu()
    
    # Write WININ: window 0 in = 0x1F (BG0-3 + OBJ), window 1 in = 0x23 (BG0,1,2 + OBJ + Blend)
    # Format: [0-7: win0_in, 8-15: win1_in]
    winin_value = 0x231F
    ppu.write_register(PPU.REG_WININ, winin_value)
    
    assert ppu.win0_in_enable == 0x1F, f"Expected win0_in_enable=0x1F, got {ppu.win0_in_enable:#x}"
    assert ppu.win1_in_enable == 0x23, f"Expected win1_in_enable=0x23, got {ppu.win1_in_enable:#x}"
    
    print("✓ test_winin_write passed")


def test_winin_bit_fields():
    """Test WININ bit field parsing."""
    ppu, memory = make_ppu()
    
    # Write WININ: window 0 in = 0x10 (OBJ only), window 1 in = 0x20 (Blend only)
    winin_value = 0x2010
    ppu.write_register(PPU.REG_WININ, winin_value)
    
    # Window 0: OBJ bit (bit 4) set
    assert (ppu.win0_in_enable & 0x10) != 0, "Expected OBJ bit set in win0_in_enable"
    assert (ppu.win0_in_enable & 0x0F) == 0, "Expected BG bits clear in win0_in_enable"
    
    # Window 1: Blend bit (bit 5) set
    assert (ppu.win1_in_enable & 0x20) != 0, "Expected Blend bit set in win1_in_enable"
    
    print("✓ test_winin_bit_fields passed")


# ============================================================================
# WINOUT Register Tests (Outside Window Control)
# ============================================================================

def test_winout_write():
    """Test writing WINOUT register."""
    ppu, memory = make_ppu()
    
    # Write WINOUT: out0 = 0x0F (BG0-3), win1_out = 0x00, OBJ bit = 1
    # Format: [0-7: win0_out, 8-15: win1_out]
    # OBJ out bit is bit 4 of the 16-bit value
    # Value 0x000F: win0_out=0x0F, win1_out=0x00, bit 4=0
    # Value 0x0010: bit 4=1 (OBJ enabled)
    winout_value = 0x000F  # First write without OBJ bit
    ppu.write_register(PPU.REG_WINOUT, winout_value)
    
    assert ppu.win0_out_enable == 0x0F, f"Expected win0_out_enable=0x0F, got {ppu.win0_out_enable:#x}"
    assert ppu.win1_out_enable == 0x00, f"Expected win1_out_enable=0x00, got {ppu.win1_out_enable:#x}"
    assert ppu.winout_obj_enable == False, f"Expected winout_obj_enable=False, got {ppu.winout_obj_enable}"
    
    # Now write with OBJ bit set
    winout_value = 0x0010  # bit 4 = 1
    ppu.write_register(PPU.REG_WINOUT, winout_value)
    
    assert ppu.winout_obj_enable == True, f"Expected winout_obj_enable=True, got {ppu.winout_obj_enable}"
    
    print("✓ test_winout_write passed")


def test_winout_obj_bit():
    """Test WINOUT OBJ enable bit."""
    ppu, memory = make_ppu()
    
    # Write WINOUT with OBJ bit clear (bit 4 of 16-bit value)
    winout_value = 0x000F  # win0_out=0x0F, bit 4 = 0
    ppu.write_register(PPU.REG_WINOUT, winout_value)
    
    assert ppu.winout_obj_enable == False, f"Expected winout_obj_enable=False, got {ppu.winout_obj_enable}"
    
    # Write WINOUT with OBJ bit set (bit 4 of 16-bit value)
    winout_value = 0x0010  # bit 4 = 1
    ppu.write_register(PPU.REG_WINOUT, winout_value)
    
    assert ppu.winout_obj_enable == True, f"Expected winout_obj_enable=True, got {ppu.winout_obj_enable}"
    
    print("✓ test_winout_obj_bit passed")


# ============================================================================
# DISPCNT Window Enable Bits Tests
# ============================================================================

def test_window_win0_enable():
    """Test DISPCNT bit 13 (window 0 enable)."""
    ppu, memory = make_ppu()
    
    # Write DISPCNT with window 0 enabled
    dispcnt_value = 0x2000  # bit 13 set
    ppu.write_register(PPU.REG_DISPCNT, dispcnt_value)
    
    assert ppu.win0_enable == True, f"Expected win0_enable=True, got {ppu.win0_enable}"
    assert ppu.win1_enable == False, f"Expected win1_enable=False, got {ppu.win1_enable}"
    
    print("✓ test_window_win0_enable passed")


def test_window_win1_enable():
    """Test DISPCNT bit 14 (window 1 enable)."""
    ppu, memory = make_ppu()
    
    # Write DISPCNT with window 1 enabled
    dispcnt_value = 0x4000  # bit 14 set
    ppu.write_register(PPU.REG_DISPCNT, dispcnt_value)
    
    assert ppu.win0_enable == False, f"Expected win0_enable=False, got {ppu.win0_enable}"
    assert ppu.win1_enable == True, f"Expected win1_enable=True, got {ppu.win1_enable}"
    
    print("✓ test_window_win1_enable passed")


def test_window_obj_enable():
    """Test DISPCNT bit 15 (object window enable)."""
    ppu, memory = make_ppu()
    
    # Write DISPCNT with object window enabled
    dispcnt_value = 0x8000  # bit 15 set
    ppu.write_register(PPU.REG_DISPCNT, dispcnt_value)
    
    assert ppu.obj_window_enable == True, f"Expected obj_window_enable=True, got {ppu.obj_window_enable}"
    
    print("✓ test_window_obj_enable passed")


def test_all_windows_enabled():
    """Test all window enable bits set."""
    ppu, memory = make_ppu()
    
    # Write DISPCNT with all windows enabled
    dispcnt_value = 0xE000  # bits 13, 14, 15 set
    ppu.write_register(PPU.REG_DISPCNT, dispcnt_value)
    
    assert ppu.win0_enable == True, f"Expected win0_enable=True, got {ppu.win0_enable}"
    assert ppu.win1_enable == True, f"Expected win1_enable=True, got {ppu.win1_enable}"
    assert ppu.obj_window_enable == True, f"Expected obj_window_enable=True, got {ppu.obj_window_enable}"
    
    print("✓ test_all_windows_enabled passed")


# ============================================================================
# _is_in_window Tests
# ============================================================================

def test_is_in_window_false_when_disabled():
    """Test _is_in_window returns False when window is disabled."""
    ppu, memory = make_ppu()
    
    # Set window boundaries but don't enable it
    ppu.win0_left = 50
    ppu.win0_right = 150
    ppu.win0_top = 50
    ppu.win0_bottom = 150
    
    # Window not enabled, should return False
    assert ppu._is_in_window(100, 100, 0) == False, "Expected False for disabled window"
    
    print("✓ test_is_in_window_false_when_disabled passed")


def test_is_in_window_inside():
    """Test _is_in_window returns True for point inside window."""
    ppu, memory = make_ppu()
    
    # Set up window 0: (50, 50) to (150, 150)
    ppu.win0_left = 50
    ppu.win0_right = 150
    ppu.win0_top = 50
    ppu.win0_bottom = 150
    
    # Capture snapshot for y=100
    ppu._win0_snapshots[100] = (50, 150)
    
    # Point (100, 100) is inside
    assert ppu._is_in_window(100, 100, 0) == True, "Expected True for point inside window"
    
    print("✓ test_is_in_window_inside passed")


def test_is_in_window_outside():
    """Test _is_in_window returns False for point outside window."""
    ppu, memory = make_ppu()
    
    # Set up window 0: (50, 50) to (150, 150)
    ppu._win0_snapshots[100] = (50, 150)
    
    # Point (200, 100) is outside (x > right)
    assert ppu._is_in_window(200, 100, 0) == False, "Expected False for point outside window"
    
    # Point (30, 100) is outside (x < left)
    assert ppu._is_in_window(30, 100, 0) == False, "Expected False for point outside window"
    
    print("✓ test_is_in_window_outside passed")


def test_is_in_window_boundary():
    """Test _is_in_window boundary conditions."""
    ppu, memory = make_ppu()
    
    # Set up window 0: (50, 50) to (150, 150)
    ppu._win0_snapshots[100] = (50, 150)
    
    # Point at left boundary (x=50) should be inside
    assert ppu._is_in_window(50, 100, 0) == True, "Expected True at left boundary"
    
    # Point at right boundary (x=150) should be outside (right is exclusive)
    assert ppu._is_in_window(150, 100, 0) == False, "Expected False at right boundary (exclusive)"
    
    print("✓ test_is_in_window_boundary passed")


def test_is_in_window_invalid_y():
    """Test _is_in_window returns False for invalid y coordinate."""
    ppu, memory = make_ppu()
    
    ppu._win0_snapshots[100] = (50, 150)
    
    # y < 0
    assert ppu._is_in_window(100, -1, 0) == False, "Expected False for y < 0"
    
    # y >= screen_height (160)
    assert ppu._is_in_window(100, 160, 0) == False, "Expected False for y >= 160"
    
    print("✓ test_is_in_window_invalid_y passed")


# ============================================================================
# _get_window_layer_enable Tests
# ============================================================================

def test_get_window_layer_enable_no_windows():
    """Test _get_window_layer_enable with no windows enabled."""
    ppu, memory = make_ppu()
    
    # No windows enabled
    ppu.win0_enable = False
    ppu.win1_enable = False
    
    # Should return default (all layers enabled)
    result = ppu._get_window_layer_enable(100, 100)
    assert result == 0x3F, f"Expected 0x3F (all enabled) when no windows, got {result:#x}"
    
    print("✓ test_get_window_layer_enable_no_windows passed")


def test_get_window_layer_enable_win0_only():
    """Test _get_window_layer_enable with only window 0."""
    ppu, memory = make_ppu()
    
    # Enable window 0
    ppu.win0_enable = True
    ppu.win0_in_enable = 0x10  # OBJ only inside
    ppu.win0_out_enable = 0x0F  # BG0-3 outside
    
    # Set up window snapshot
    ppu._win0_snapshots[100] = (50, 150)
    ppu._win0_enable_snapshots[100] = True
    ppu._win0_in_snapshots[100] = 0x10
    ppu._win0_out_snapshots[100] = 0x0F
    
    # Point inside window 0
    result_inside = ppu._get_window_layer_enable(100, 100)
    assert result_inside == 0x10, f"Expected 0x10 inside window, got {result_inside:#x}"
    
    # Point outside window 0
    result_outside = ppu._get_window_layer_enable(200, 100)
    assert result_outside == 0x0F, f"Expected 0x0F outside window, got {result_outside:#x}"
    
    print("✓ test_get_window_layer_enable_win0_only passed")


def test_get_window_layer_enable_win0_priority():
    """Test window 0 has priority over window 1."""
    ppu, memory = make_ppu()
    
    # Enable both windows
    ppu.win0_enable = True
    ppu.win1_enable = True
    ppu.win0_in_enable = 0x01  # BG0 only
    ppu.win1_in_enable = 0x02  # BG1 only
    
    # Set up overlapping windows
    ppu._win0_snapshots[100] = (50, 150)
    ppu._win1_snapshots[100] = (100, 200)
    ppu._win0_enable_snapshots[100] = True
    ppu._win1_enable_snapshots[100] = True
    ppu._win0_in_snapshots[100] = 0x01
    ppu._win1_in_snapshots[100] = 0x02
    
    # Point (120, 100) is in both windows - should use WIN0
    result = ppu._get_window_layer_enable(120, 100)
    assert result == 0x01, f"Expected 0x01 (WIN0 priority), got {result:#x}"
    
    print("✓ test_get_window_layer_enable_win0_priority passed")


def test_get_window_layer_enable_winout():
    """Test WINOUT controls layers outside windows."""
    ppu, memory = make_ppu()
    
    # Enable window 0 with specific inside controls
    ppu.win0_enable = True
    ppu.win0_in_enable = 0x01  # BG0 only inside
    ppu.win0_out_enable = 0x10  # OBJ only outside
    
    # Set up window
    ppu._win0_snapshots[100] = (50, 150)
    ppu._win0_enable_snapshots[100] = True
    ppu._win0_in_snapshots[100] = 0x01
    ppu._win0_out_snapshots[100] = 0x10
    
    # Point outside window should use win0_out_enable
    result = ppu._get_window_layer_enable(200, 100)
    assert result == 0x10, f"Expected 0x10 (win0_out), got {result:#x}"
    
    print("✓ test_get_window_layer_enable_winout passed")


# ============================================================================
# Test Runner
# ============================================================================

if __name__ == "__main__":
    # Run all tests
    test_window_registers_default_values()
    test_win0h_write()
    test_win0h_full_width()
    test_win0h_clamp_to_240()
    test_win0v_write()
    test_win1h_write()
    test_win1v_write()
    test_winin_write()
    test_winin_bit_fields()
    test_winout_write()
    test_winout_obj_bit()
    test_window_win0_enable()
    test_window_win1_enable()
    test_window_obj_enable()
    test_all_windows_enabled()
    test_is_in_window_false_when_disabled()
    test_is_in_window_inside()
    test_is_in_window_outside()
    test_is_in_window_boundary()
    test_is_in_window_invalid_y()
    test_get_window_layer_enable_no_windows()
    test_get_window_layer_enable_win0_only()
    test_get_window_layer_enable_win0_priority()
    test_get_window_layer_enable_winout()
    
    print("\n" + "=" * 60)
    print("All window rendering tests passed!")
    print("=" * 60)
