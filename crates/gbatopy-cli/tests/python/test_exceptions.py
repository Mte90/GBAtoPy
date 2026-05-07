import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "exceptions", os.path.join(os.path.dirname(__file__), "..", "gba_runtime", "exceptions.py")
)
exceptions_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exceptions_module)

GameError = exceptions_module.GameError
InvalidRom = exceptions_module.InvalidRom
InvalidAddress = exceptions_module.InvalidAddress


def test_game_error_base():
    err = GameError()
    assert isinstance(err, GameError)
    assert isinstance(err, Exception)


def test_game_error_with_message():
    err = GameError("test message")
    assert str(err) == "test message"


def test_invalid_rom_inherits_game_error():
    err = InvalidRom()
    assert isinstance(err, InvalidRom)
    assert isinstance(err, GameError)


def test_invalid_rom_with_message():
    err = InvalidRom("invalid ROM file")
    assert str(err) == "invalid ROM file"


def test_invalid_address_inherits_game_error():
    err = InvalidAddress()
    assert isinstance(err, InvalidAddress)
    assert isinstance(err, GameError)


def test_invalid_address_with_message():
    err = InvalidAddress("address 0x12345678 out of bounds")
    assert str(err) == "address 0x12345678 out of bounds"


def test_exception_can_be_raised_and_caught():
    with pytest.raises(GameError):
        raise GameError("base error")


def test_invalid_rom_exception():
    with pytest.raises(InvalidRom):
        raise InvalidRom("ROM validation failed")


def test_invalid_address_exception():
    with pytest.raises(InvalidAddress):
        raise InvalidAddress("invalid memory access")


def test_exception_hierarchical_catching():
    with pytest.raises(GameError):
        raise InvalidRom("ROM error")

    with pytest.raises(GameError):
        raise InvalidAddress("address error")
