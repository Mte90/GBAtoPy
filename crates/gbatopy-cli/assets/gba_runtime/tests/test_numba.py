"""
Numba integration tests for GBAtoPy transpiler.

This test suite verifies the numba.py module:
- Numba availability detection
- set_numba_enabled() function
- _HAS_NUMBA and _NUMBA_ENABLED flags

Run with: python3 -m pytest test_numba.py -v
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numba


class TestNumbaModule(unittest.TestCase):
    """Numba module-level tests."""
    
    def test_has_numba_flag_exists(self):
        """_HAS_NUMBA flag should exist and be a boolean."""
        self.assertIsInstance(numba._HAS_NUMBA, bool)
    
    def test_numba_enabled_flag_exists(self):
        """_NUMBA_ENABLED flag should exist and be a boolean."""
        self.assertIsInstance(numba._NUMBA_ENABLED, bool)
    
    def test_njit_exists(self):
        """njit should be defined (either function or None)."""
        self.assertTrue(hasattr(numba, 'njit'))
        # njit is either a function (if numba installed) or None
        self.assertTrue(callable(numba.njit) or numba.njit is None)
    
    def test_prange_exists(self):
        """prange should be defined (either function or None)."""
        self.assertTrue(hasattr(numba, 'prange'))
        # prange is either a function (if numba installed) or None
        self.assertTrue(callable(numba.prange) or numba.prange is None)


class TestNumbaAvailability(unittest.TestCase):
    """Test numba availability detection."""
    
    def test_has_numba_is_boolean(self):
        """_HAS_NUMBA should be True or False."""
        self.assertIn(numba._HAS_NUMBA, [True, False])
    
    def test_njit_and_prange_consistency(self):
        """njit and prange should both be None or both be callable when _HAS_NUMBA is consistent."""
        if numba._HAS_NUMBA:
            # If numba is available, both should be callable
            self.assertTrue(callable(numba.njit), 
                "njit should be callable when _HAS_NUMBA is True")
            self.assertTrue(callable(numba.prange), 
                "prange should be callable when _HAS_NUMBA is True")
        else:
            # If numba is not available, both should be None
            self.assertIsNone(numba.njit, 
                "njit should be None when _HAS_NUMBA is False")
            self.assertIsNone(numba.prange, 
                "prange should be None when _HAS_NUMBA is False")


class TestSetNumbaEnabled(unittest.TestCase):
    """Test set_numba_enabled() function."""
    
    def setUp(self):
        """Reset _NUMBA_ENABLED before each test."""
        numba._NUMBA_ENABLED = numba._HAS_NUMBA
    
    def test_set_enabled_true_with_numba(self):
        """set_numba_enabled(True) should enable when numba is available."""
        numba.set_numba_enabled(True)
        if numba._HAS_NUMBA:
            self.assertTrue(numba._NUMBA_ENABLED,
                "_NUMBA_ENABLED should be True when numba available and enabled=True")
        else:
            self.assertFalse(numba._NUMBA_ENABLED,
                "_NUMBA_ENABLED should be False when numba not available")
    
    def test_set_enabled_false(self):
        """set_numba_enabled(False) should always disable."""
        numba.set_numba_enabled(False)
        self.assertFalse(numba._NUMBA_ENABLED,
            "_NUMBA_ENABLED should be False when enabled=False")
    
    def test_set_enabled_true_without_numba(self):
        """set_numba_enabled(True) should not enable when numba is not available."""
        if not numba._HAS_NUMBA:
            numba.set_numba_enabled(True)
            self.assertFalse(numba._NUMBA_ENABLED,
                "_NUMBA_ENABLED should remain False when numba not available")
    
    def test_toggle_numba_enabled(self):
        """Toggling enabled state should work correctly."""
        # Start disabled
        numba.set_numba_enabled(False)
        self.assertFalse(numba._NUMBA_ENABLED)
        
        # Enable
        numba.set_numba_enabled(True)
        if numba._HAS_NUMBA:
            self.assertTrue(numba._NUMBA_ENABLED)
        
        # Disable again
        numba.set_numba_enabled(False)
        self.assertFalse(numba._NUMBA_ENABLED)
    
    def test_multiple_calls_same_value(self):
        """Multiple calls with same value should be idempotent."""
        numba.set_numba_enabled(True)
        initial = numba._NUMBA_ENABLED
        
        numba.set_numba_enabled(True)
        self.assertEqual(numba._NUMBA_ENABLED, initial)
        
        numba.set_numba_enabled(False)
        numba.set_numba_enabled(False)
        self.assertFalse(numba._NUMBA_ENABLED)


class TestNumbaDecorator(unittest.TestCase):
    """Test njit decorator behavior (when available)."""
    
    @unittest.skipUnless(numba._HAS_NUMBA, "Numba not installed")
    def test_njit_decorator_applies(self):
        """njit should successfully decorate a function when numba is available."""
        @numba.njit
        def simple_add(a, b):
            return a + b
        
        # Should be able to call the decorated function
        result = simple_add(2, 3)
        self.assertEqual(result, 5)
    
    @unittest.skipUnless(numba._HAS_NUMBA, "Numba not installed")
    def test_njit_with_prange(self):
        """njit with prange should work for parallel loops when numba is available."""
        @numba.njit
        def sum_array(arr):
            total = 0
            for i in numba.prange(len(arr)):
                total += arr[i]
            return total
        
        arr = [1, 2, 3, 4, 5]
        result = sum_array(arr)
        self.assertEqual(result, 15)
    
    @unittest.skipIf(numba._HAS_NUMBA, "Numba is installed")
    def test_njit_none_raises_type_error(self):
        """Using njit when numba is not installed should fail gracefully."""
        self.assertIsNone(numba.njit)
        
        # Attempting to use njit as decorator when None should raise
        with self.assertRaises(TypeError):
            @numba.njit  # type: ignore
            def bad_func():
                pass


if __name__ == '__main__':
    unittest.main()
