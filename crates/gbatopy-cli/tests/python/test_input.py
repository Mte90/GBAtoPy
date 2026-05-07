import pytest
from gba_runtime.input import Input, GBA_KEYS, KEYBOARD_MAP, DEFAULT_KEYS


def test_input_init():
    inp = Input()
    assert isinstance(inp.get_keys(), int)


def test_default_keys_no_pygame():
    inp = Input()
    keys = inp.get_keys()
    assert keys == 0x03FF
    assert isinstance(keys, int)


def test_gba_keys_constants():
    assert GBA_KEYS["A"] == 0x01
    assert GBA_KEYS["B"] == 0x02
    assert GBA_KEYS["SELECT"] == 0x04
    assert GBA_KEYS["START"] == 0x08
    assert GBA_KEYS["RIGHT"] == 0x10
    assert GBA_KEYS["LEFT"] == 0x20
    assert GBA_KEYS["UP"] == 0x40
    assert GBA_KEYS["DOWN"] == 0x80
    assert GBA_KEYS["R"] == 0x100
    assert GBA_KEYS["L"] == 0x200


def test_keyboard_map_z_to_a():
    assert KEYBOARD_MAP["z"] == "A"


def test_keyboard_map_x_to_b():
    assert KEYBOARD_MAP["x"] == "B"


def test_keyboard_map_return_to_start():
    assert KEYBOARD_MAP["return"] == "START"


def test_keyboard_map_shift_to_select():
    assert KEYBOARD_MAP["left shift"] == "SELECT"
    assert KEYBOARD_MAP["right shift"] == "SELECT"


def test_keyboard_map_arrows():
    assert KEYBOARD_MAP["right"] == "RIGHT"
    assert KEYBOARD_MAP["left"] == "LEFT"
    assert KEYBOARD_MAP["up"] == "UP"
    assert KEYBOARD_MAP["down"] == "DOWN"


def test_keyboard_map_a_to_l():
    assert KEYBOARD_MAP["a"] == "L"


def test_keyboard_map_s_to_r():
    assert KEYBOARD_MAP["s"] == "R"


def test_poll_returns_bool():
    inp = Input()
    result = inp.poll()
    assert isinstance(result, bool)
    assert result is True


def test_get_keys_returns_int():
    inp = Input()
    keys = inp.get_keys()
    assert isinstance(keys, int)
    assert keys == 0x03FF


def test_keys_in_valid_range():
    inp = Input()
    inp.poll()
    keys = inp.get_keys()
    assert 0 <= keys <= 0x03FF


def test_default_keys_all_released():
    inp = Input()
    assert inp.get_keys() == 0x03FF
