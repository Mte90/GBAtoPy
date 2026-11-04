"""
Exception hierarchy tests for GBAtoPy transpiler.

This test suite verifies the exception classes in exceptions.py:
- Exception construction and inheritance
- String representation
- Edge cases (empty args, special characters)

Run with: python3 -m pytest test_exceptions.py -v
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from exceptions import GameError, GBARuntimeError, InvalidRom, InvalidROMError, InvalidAddress


class TestGameError(unittest.TestCase):
    """Base exception class tests."""
    
    def test_instantiation_no_args(self):
        """GameError() with no arguments should not raise."""
        exc = GameError()
        self.assertIsInstance(exc, GameError)
        self.assertIsInstance(exc, Exception)
    
    def test_instantiation_with_message(self):
        """GameError('message') should store and return the message."""
        exc = GameError("test message")
        self.assertEqual(str(exc), "test message")
    
    def test_instantiation_with_empty_string(self):
        """GameError('') should handle empty message."""
        exc = GameError("")
        self.assertEqual(str(exc), "")
    
    def test_instantiation_with_special_chars(self):
        """GameError should handle special characters in messages."""
        exc = GameError("test\nwith\tnewlines and spaces")
        self.assertIn("newlines", str(exc))
    
    def test_instantiation_with_unicode(self):
        """GameError should handle unicode characters."""
        exc = GameError("日本語テスト")
        self.assertEqual(str(exc), "日本語テスト")
    
    def test_args_attribute(self):
        """GameError.args should contain the message."""
        exc = GameError("test")
        self.assertEqual(exc.args, ("test",))
    
    def test_inheritance_from_exception(self):
        """GameError should inherit from Exception."""
        self.assertTrue(issubclass(GameError, Exception))


class TestGBARuntimeError(unittest.TestCase):
    """GBARuntimeError subclass tests."""
    
    def test_inherits_from_game_error(self):
        """GBARuntimeError should inherit from GameError."""
        self.assertTrue(issubclass(GBARuntimeError, GameError))
    
    def test_instantiation_no_args(self):
        """GBARuntimeError() with no arguments should not raise."""
        exc = GBARuntimeError()
        self.assertIsInstance(exc, GBARuntimeError)
    
    def test_instantiation_with_message(self):
        """GBARuntimeError('message') should store and return the message."""
        exc = GBARuntimeError("runtime error occurred")
        self.assertEqual(str(exc), "runtime error occurred")
    
    def test_catch_as_game_error(self):
        """GBARuntimeError should be catchable as GameError."""
        try:
            raise GBARuntimeError("test")
        except GameError as e:
            self.assertEqual(str(e), "test")
        else:
            self.fail("GBARuntimeError should be catchable as GameError")


class TestInvalidRom(unittest.TestCase):
    """InvalidRom subclass tests."""
    
    def test_inherits_from_game_error(self):
        """InvalidRom should inherit from GameError."""
        self.assertTrue(issubclass(InvalidRom, GameError))
    
    def test_instantiation_no_args(self):
        """InvalidRom() with no arguments should not raise."""
        exc = InvalidRom()
        self.assertIsInstance(exc, InvalidRom)
    
    def test_instantiation_with_message(self):
        """InvalidRom('message') should store and return the message."""
        exc = InvalidRom("ROM file is corrupted")
        self.assertEqual(str(exc), "ROM file is corrupted")
    
    def test_catch_as_game_error(self):
        """InvalidRom should be catchable as GameError."""
        try:
            raise InvalidRom("test")
        except GameError as e:
            self.assertEqual(str(e), "test")
        else:
            self.fail("InvalidRom should be catchable as GameError")


class TestInvalidROMError(unittest.TestCase):
    """InvalidROMError (subclass of InvalidRom) tests."""
    
    def test_inherits_from_invalid_rom(self):
        """InvalidROMError should inherit from InvalidRom."""
        self.assertTrue(issubclass(InvalidROMError, InvalidRom))
    
    def test_inherits_from_game_error(self):
        """InvalidROMError should transitively inherit from GameError."""
        self.assertTrue(issubclass(InvalidROMError, GameError))
    
    def test_instantiation_no_args(self):
        """InvalidROMError() with no arguments should not raise."""
        exc = InvalidROMError()
        self.assertIsInstance(exc, InvalidROMError)
    
    def test_instantiation_with_message(self):
        """InvalidROMError('message') should store and return the message."""
        exc = InvalidROMError("invalid ROM header")
        self.assertEqual(str(exc), "invalid ROM header")
    
    def test_catch_as_invalid_rom(self):
        """InvalidROMError should be catchable as InvalidRom."""
        try:
            raise InvalidROMError("test")
        except InvalidRom as e:
            self.assertEqual(str(e), "test")
        else:
            self.fail("InvalidROMError should be catchable as InvalidRom")
    
    def test_catch_as_game_error(self):
        """InvalidROMError should be catchable as GameError."""
        try:
            raise InvalidROMError("test")
        except GameError as e:
            self.assertEqual(str(e), "test")
        else:
            self.fail("InvalidROMError should be catchable as GameError")


class TestInvalidAddress(unittest.TestCase):
    """InvalidAddress subclass tests."""
    
    def test_inherits_from_game_error(self):
        """InvalidAddress should inherit from GameError."""
        self.assertTrue(issubclass(InvalidAddress, GameError))
    
    def test_instantiation_no_args(self):
        """InvalidAddress() with no arguments should not raise."""
        exc = InvalidAddress()
        self.assertIsInstance(exc, InvalidAddress)
    
    def test_instantiation_with_message(self):
        """InvalidAddress('message') should store and return the message."""
        exc = InvalidAddress("address 0xDEADBEEF is out of range")
        self.assertEqual(str(exc), "address 0xDEADBEEF is out of range")
    
    def test_instantiation_with_hex_address(self):
        """InvalidAddress should handle hex address strings."""
        exc = InvalidAddress(f"Invalid address: {hex(0x08000000)}")
        # Python's hex() omits leading zeros, so check for '0x8000000'
        self.assertIn("0x8000000", str(exc))
    
    def test_catch_as_game_error(self):
        """InvalidAddress should be catchable as GameError."""
        try:
            raise InvalidAddress("test")
        except GameError as e:
            self.assertEqual(str(e), "test")
        else:
            self.fail("InvalidAddress should be catchable as GameError")


class TestExceptionRaising(unittest.TestCase):
    """Test raising and catching exceptions."""
    
    def test_raise_game_error(self):
        """Raising GameError should work normally."""
        with self.assertRaises(GameError) as ctx:
            raise GameError("test error")
        self.assertEqual(str(ctx.exception), "test error")
    
    def test_raise_specific_exception(self):
        """Raising specific exception should preserve type."""
        with self.assertRaises(InvalidROMError) as ctx:
            raise InvalidROMError("bad ROM")
        self.assertIsInstance(ctx.exception, InvalidROMError)
        self.assertIsInstance(ctx.exception, InvalidRom)
        self.assertIsInstance(ctx.exception, GameError)


if __name__ == '__main__':
    unittest.main()
