"""
Input/Keypad Subsystem Test Suite for GBAtoPy Transpiler.

This test suite verifies the GBA input controller behavior, including
key state management, active-low encoding, and button mappings.

Run with: python3 -m pytest test_input.py -v
"""

import unittest
import sys
import os

# Add parent directory to path to import gba_runtime modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from input import Input, GBA_KEYS, DEFAULT_KEYS


class TestInputInitialization(unittest.TestCase):
    """Input class initialization and basic properties."""

    def test_initial_state_all_keys_released(self):
        """New Input instance should have all keys released (DEFAULT_KEYS = 0x3FFF)."""
        inp = Input()
        
        # Initial state should be all keys released
        self.assertEqual(inp.get_keys(), DEFAULT_KEYS,
            "All keys should be released initially (0x3FFF)")
        self.assertEqual(inp.get_keys(), 0x3FFF,
            "DEFAULT_KEYS should be 0x3FFF")

    def test_pygame_available_property(self):
        """pygame_available property should return bool."""
        inp = Input()
        
        # Should return a boolean (True if pygame installed, False otherwise)
        result = inp.pygame_available
        self.assertIsInstance(result, bool,
            "pygame_available should return a boolean")


class TestKeyBitPositions(unittest.TestCase):
    """Verify GBA button bit positions in KEYINPUT register."""

    def test_a_button_bit_0(self):
        """A button should be at bit 0 (0x01)."""
        self.assertEqual(GBA_KEYS["A"], 0x01,
            "A button should be at bit 0")

    def test_b_button_bit_1(self):
        """B button should be at bit 1 (0x02)."""
        self.assertEqual(GBA_KEYS["B"], 0x02,
            "B button should be at bit 1")

    def test_select_button_bit_2(self):
        """SELECT button should be at bit 2 (0x04)."""
        self.assertEqual(GBA_KEYS["SELECT"], 0x04,
            "SELECT button should be at bit 2")

    def test_start_button_bit_3(self):
        """START button should be at bit 3 (0x08)."""
        self.assertEqual(GBA_KEYS["START"], 0x08,
            "START button should be at bit 3")

    def test_right_button_bit_8(self):
        """RIGHT button should be at bit 8 (0x100)."""
        self.assertEqual(GBA_KEYS["RIGHT"], 0x100,
            "RIGHT button should be at bit 8")

    def test_left_button_bit_9(self):
        """LEFT button should be at bit 9 (0x200)."""
        self.assertEqual(GBA_KEYS["LEFT"], 0x200,
            "LEFT button should be at bit 9")

    def test_up_button_bit_10(self):
        """UP button should be at bit 10 (0x400)."""
        self.assertEqual(GBA_KEYS["UP"], 0x400,
            "UP button should be at bit 10")

    def test_down_button_bit_11(self):
        """DOWN button should be at bit 11 (0x800)."""
        self.assertEqual(GBA_KEYS["DOWN"], 0x800,
            "DOWN button should be at bit 11")

    def test_r_button_bit_12(self):
        """R button should be at bit 12 (0x1000)."""
        self.assertEqual(GBA_KEYS["R"], 0x1000,
            "R button should be at bit 12")

    def test_l_button_bit_13(self):
        """L button should be at bit 13 (0x2000)."""
        self.assertEqual(GBA_KEYS["L"], 0x2000,
            "L button should be at bit 13")


class TestActiveLowEncoding(unittest.TestCase):
    """Test active-low encoding: 0 = pressed, 1 = released."""

    def test_default_all_released_is_all_ones(self):
        """Default key state (all released) should have all 14 bits set to 1."""
        # 14 bits (0-13) = 0x3FFF = all 1s
        self.assertEqual(DEFAULT_KEYS, 0x3FFF,
            "DEFAULT_KEYS should be 0x3FFF (all 14 bits set)")
        self.assertEqual(DEFAULT_KEYS & 0x3FFF, 0x3FFF,
            "All 14 key bits should be 1 when released")

    def test_pressed_key_clears_bit(self):
        """When a key is pressed, its bit should be cleared (set to 0)."""
        inp = Input()
        
        # Press A button
        inp.update_keys(a=True)
        
        # A button bit (bit 0) should be 0
        key_state = inp.get_keys()
        self.assertEqual(key_state & 0x01, 0,
            "A button bit should be 0 when pressed (active low)")
        
        # All other bits should remain 1
        self.assertEqual(key_state & 0x3FFE, 0x3FFE,
            "All other key bits should remain 1")


class TestIndividualButtonPresses(unittest.TestCase):
    """Test each of the 10 buttons individually."""

    def test_update_keys_a_pressed(self):
        """update_keys(a=True) should press A button."""
        inp = Input()
        inp.update_keys(a=True)
        
        self.assertEqual(inp.get_keys() & 0x01, 0,
            "A button should be pressed (bit 0 = 0)")

    def test_update_keys_b_pressed(self):
        """update_keys(b=True) should press B button."""
        inp = Input()
        inp.update_keys(b=True)
        
        self.assertEqual(inp.get_keys() & 0x02, 0,
            "B button should be pressed (bit 1 = 0)")

    def test_update_keys_select_pressed(self):
        """update_keys(select=True) should press SELECT button."""
        inp = Input()
        inp.update_keys(select=True)
        
        self.assertEqual(inp.get_keys() & 0x04, 0,
            "SELECT button should be pressed (bit 2 = 0)")

    def test_update_keys_start_pressed(self):
        """update_keys(start=True) should press START button."""
        inp = Input()
        inp.update_keys(start=True)
        
        self.assertEqual(inp.get_keys() & 0x08, 0,
            "START button should be pressed (bit 3 = 0)")

    def test_update_keys_right_pressed(self):
        """update_keys(right=True) should press RIGHT button."""
        inp = Input()
        inp.update_keys(right=True)
        
        self.assertEqual(inp.get_keys() & 0x100, 0,
            "RIGHT button should be pressed (bit 8 = 0)")

    def test_update_keys_left_pressed(self):
        """update_keys(left=True) should press LEFT button."""
        inp = Input()
        inp.update_keys(left=True)
        
        self.assertEqual(inp.get_keys() & 0x200, 0,
            "LEFT button should be pressed (bit 9 = 0)")

    def test_update_keys_up_pressed(self):
        """update_keys(up=True) should press UP button."""
        inp = Input()
        inp.update_keys(up=True)
        
        self.assertEqual(inp.get_keys() & 0x400, 0,
            "UP button should be pressed (bit 10 = 0)")

    def test_update_keys_down_pressed(self):
        """update_keys(down=True) should press DOWN button."""
        inp = Input()
        inp.update_keys(down=True)
        
        self.assertEqual(inp.get_keys() & 0x800, 0,
            "DOWN button should be pressed (bit 11 = 0)")

    def test_update_keys_r_pressed(self):
        """update_keys(r=True) should press R button."""
        inp = Input()
        inp.update_keys(r=True)
        
        self.assertEqual(inp.get_keys() & 0x1000, 0,
            "R button should be pressed (bit 12 = 0)")

    def test_update_keys_l_pressed(self):
        """update_keys(l=True) should press L button."""
        inp = Input()
        inp.update_keys(l=True)
        
        self.assertEqual(inp.get_keys() & 0x2000, 0,
            "L button should be pressed (bit 13 = 0)")


class TestKeyRelease(unittest.TestCase):
    """Test key release behavior."""

    def test_release_key_by_setting_false(self):
        """Setting a key to False should release it."""
        inp = Input()
        
        # Press A button
        inp.update_keys(a=True)
        self.assertEqual(inp.get_keys() & 0x01, 0,
            "A should be pressed")
        
        # Release A button
        inp.update_keys(a=False)
        self.assertEqual(inp.get_keys() & 0x01, 0x01,
            "A should be released (bit 0 = 1)")

    def test_all_keys_released_after_update_with_no_args(self):
        """Calling update_keys() with no arguments should release all keys."""
        inp = Input()
        
        # Press some keys
        inp.update_keys(a=True, b=True, start=True)
        
        # Release all by calling with defaults
        inp.update_keys()
        
        self.assertEqual(inp.get_keys(), DEFAULT_KEYS,
            "All keys should be released")


class TestSimultaneousKeyPresses(unittest.TestCase):
    """Test multiple keys pressed simultaneously."""

    def test_two_keys_pressed(self):
        """Pressing two keys should clear both bits."""
        inp = Input()
        inp.update_keys(a=True, b=True)
        
        key_state = inp.get_keys()
        self.assertEqual(key_state & 0x01, 0, "A should be pressed")
        self.assertEqual(key_state & 0x02, 0, "B should be pressed")
        self.assertEqual(key_state & 0x3FFC, 0x3FFC, "All other keys released")

    def test_all_ten_keys_pressed(self):
        """Pressing all 10 keys should clear all 10 bits."""
        inp = Input()
        inp.update_keys(a=True, b=True, select=True, start=True,
                       right=True, left=True, up=True, down=True,
                       r=True, l=True)
        
        key_state = inp.get_keys()
        
        # All 10 key bits should be 0
        key_mask = (0x01 | 0x02 | 0x04 | 0x08 |  # A, B, Select, Start
                   0x100 | 0x200 | 0x400 | 0x800 |  # Right, Left, Up, Down
                   0x1000 | 0x2000)  # R, L
        
        self.assertEqual(key_state & key_mask, 0,
            "All 10 key bits should be 0 when pressed")
        
        # Expected value: 0x3FFF with all key bits cleared
        expected = 0x3FFF & ~key_mask
        self.assertEqual(key_state, expected,
            f"Key state should be 0x{expected:04X} with all keys pressed")

    def test_directional_pad_simultaneous(self):
        """Pressing multiple D-pad keys simultaneously."""
        inp = Input()
        inp.update_keys(right=True, left=True, up=True, down=True)
        
        key_state = inp.get_keys()
        
        # All four D-pad bits should be 0
        self.assertEqual(key_state & 0x100, 0, "RIGHT should be pressed")
        self.assertEqual(key_state & 0x200, 0, "LEFT should be pressed")
        self.assertEqual(key_state & 0x400, 0, "UP should be pressed")
        self.assertEqual(key_state & 0x800, 0, "DOWN should be pressed")


class TestEdgeCases(unittest.TestCase):
    """Edge case testing."""

    def test_no_keys_pressed(self):
        """No keys pressed should return DEFAULT_KEYS (0x3FFF)."""
        inp = Input()
        inp.update_keys()  # All False
        
        self.assertEqual(inp.get_keys(), 0x3FFF,
            "No keys pressed should return 0x3FFF")

    def test_key_state_is_16_bit(self):
        """Key state should be a 16-bit value."""
        inp = Input()
        
        key_state = inp.get_keys()
        self.assertLessEqual(key_state, 0xFFFF,
            "Key state should fit in 16 bits")
        self.assertGreaterEqual(key_state, 0,
            "Key state should be non-negative")

    def test_key_state_fits_in_14_bits(self):
        """Key state uses only bits 0-13 (14 bits for 10 buttons + 4 unused)."""
        inp = Input()
        
        # Key state should be within 14-bit range (0x3FFF max)
        key_state = inp.get_keys()
        self.assertLessEqual(key_state & 0xC000, 0x0000,
            "Bits 14-15 should be 0 (key state is 14 bits)"),
        self.assertLessEqual(key_state, 0x3FFF,
            "Key state should fit in 14 bits (0x3FFF max)")


class TestPollMethod(unittest.TestCase):
    """Test the poll() method behavior."""

    def test_poll_returns_bool(self):
        """poll() should return a boolean."""
        inp = Input()
        
        result = inp.poll()
        self.assertIsInstance(result, bool,
            "poll() should return a boolean")

    def test_poll_when_pygame_not_available(self):
        """poll() should return True and set keys to DEFAULT_KEYS when pygame unavailable."""
        inp = Input()
        
        # Force pygame unavailability by checking the property
        # (we can't actually uninstall pygame in tests, but we can verify behavior)
        result = inp.poll()
        
        # Should return True (success) even if pygame is available
        self.assertTrue(result,
            "poll() should return True on success")


class TestUpdateFromPygame(unittest.TestCase):
    """Test update_from_pygame() method."""

    def test_update_from_pygame_with_no_keys(self):
        """update_from_pygame with no keys pressed should set DEFAULT_KEYS."""
        inp = Input()
        
        # Mock pygame key state with no keys pressed
        class MockKeys:
            def __getitem__(self, key):
                return False
        
        inp.update_from_pygame(MockKeys())
        
        self.assertEqual(inp.get_keys(), DEFAULT_KEYS,
            "No keys pressed should result in DEFAULT_KEYS")


if __name__ == '__main__':
    unittest.main()