"""Test GBA input constants against GBATEK specification.

This test validates that the KEYINPUT bit masks in input.py match the
GBATEK specification for the GBA button register (0x04000130).

Reference: docs/reference/io-registers.md § "KEYINPUT Bit Mapping"
"""

import sys
import os

# Add parent directory to path to import gba_runtime modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from input import GBA_KEYS, DEFAULT_KEYS


def test_gba_keys_contains_all_buttons():
    """Assert all 10 GBA buttons are present in GBA_KEYS dict."""
    expected_buttons = {"A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L"}
    assert set(GBA_KEYS.keys()) == expected_buttons, (
        f"GBA_KEYS missing buttons: {expected_buttons - set(GBA_KEYS.keys())}"
    )


def test_dpad_button_masks():
    """Assert D-pad button masks match GBATEK spec (bits 4-7)."""
    assert GBA_KEYS["RIGHT"] == 0x10, "RIGHT should be bit 4 (0x10)"
    assert GBA_KEYS["LEFT"] == 0x20, "LEFT should be bit 5 (0x20)"
    assert GBA_KEYS["UP"] == 0x40, "UP should be bit 6 (0x40)"
    assert GBA_KEYS["DOWN"] == 0x80, "DOWN should be bit 7 (0x80)"


def test_action_button_masks():
    """Assert action button masks match GBATEK spec (bits 0-3)."""
    assert GBA_KEYS["A"] == 0x01, "A should be bit 0 (0x01)"
    assert GBA_KEYS["B"] == 0x02, "B should be bit 1 (0x02)"
    assert GBA_KEYS["SELECT"] == 0x04, "SELECT should be bit 2 (0x04)"
    assert GBA_KEYS["START"] == 0x08, "START should be bit 3 (0x08)"


def test_shoulder_button_masks():
    """Assert shoulder button masks match GBATEK spec (bits 8-9)."""
    assert GBA_KEYS["R"] == 0x100, "R should be bit 8 (0x100)"
    assert GBA_KEYS["L"] == 0x200, "L should be bit 9 (0x200)"


def test_default_keys_all_released():
    """Assert DEFAULT_KEYS = 0x3FF (10 bits, all released)."""
    assert DEFAULT_KEYS == 0x3FF, "DEFAULT_KEYS should be 0x3FF (all 10 bits set to 1 = released)"


def test_bit_contiguity():
    """Assert bit positions are contiguous from bit 0 to bit 9 with no gaps."""
    masks = sorted(GBA_KEYS.values())
    expected_masks = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x100, 0x200]
    assert masks == expected_masks, (
        f"Bit masks not contiguous. Expected {expected_masks}, got {masks}"
    )


def test_no_duplicate_bit_positions():
    """Assert no two buttons share the same bit position."""
    masks = list(GBA_KEYS.values())
    assert len(masks) == len(set(masks)), "Duplicate bit masks found in GBA_KEYS"


def test_all_masks_are_power_of_two():
    """Assert all button masks are single-bit values (power of two)."""
    for button, mask in GBA_KEYS.items():
        assert mask > 0 and (mask & (mask - 1)) == 0, (
            f"{button} mask 0x{mask:X} is not a power of two"
        )


def test_total_bits_within_10_bit_range():
    """Assert all button masks fit within 10 bits (0-9)."""
    for button, mask in GBA_KEYS.items():
        assert mask <= 0x200, f"{button} mask 0x{mask:X} exceeds 10-bit range (max 0x200)"
