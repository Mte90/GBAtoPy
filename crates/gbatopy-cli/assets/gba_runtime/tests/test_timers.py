"""
Timer Subsystem Test Suite for GBAtoPy Transpiler.

This test suite verifies the GBA timer controller behavior, including
prescaler values, overflow detection, IRQ callbacks, and cascade mode.

Run with: python3 -m pytest test_timers.py -v
"""

import unittest
import sys
import os

# Add parent directory to path to import gba_runtime modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from timers import Timers


class MockInterrupts:
    """Mock interrupt controller for testing timer IRQ callbacks."""
    
    def __init__(self):
        self.irq_calls = []
    
    def timer_irq(self, channel):
        """Record IRQ callback for a timer channel."""
        self.irq_calls.append(channel)


class TestTimerBasicOperations(unittest.TestCase):
    """Basic timer operations: initialization, get/set operations."""
    
    def test_initial_state(self):
        """All counts=0, controls=0, reloads=0, overflow_flags=False, _active_count=0."""
        timers = Timers()
        
        # Check all counts are 0
        for i in range(4):
            self.assertEqual(timers.get_timer(i), 0,
                f"Timer {i} count should be 0 initially")
            self.assertEqual(timers.get_control(i), 0,
                f"Timer {i} control should be 0 initially")
            self.assertEqual(timers.get_reload(i), 0,
                f"Timer {i} reload should be 0 initially")
            self.assertFalse(timers.get_overflow_flag(i),
                f"Timer {i} overflow flag should be False initially")
        
        # Check internal state
        self.assertEqual(timers._active_count, 0,
            "_active_count should be 0 initially")
        self.assertEqual(timers._cycle_subcount, [0, 0, 0, 0],
            "_cycle_subcount should be all 0 initially")
    
    def test_set_get_timer(self):
        """set_timer then get_timer returns value; values >0xFFFF are masked."""
        timers = Timers()
        
        # Set and get basic value
        timers.set_timer(0, 0x1234)
        self.assertEqual(timers.get_timer(0), 0x1234,
            "get_timer should return set value")
        
        # Test masking to 0xFFFF
        timers.set_timer(1, 0x12345)
        self.assertEqual(timers.get_timer(1), 0x2345,
            "Values >0xFFFF should be masked to 16 bits")
        
        # Test max value
        timers.set_timer(2, 0xFFFF)
        self.assertEqual(timers.get_timer(2), 0xFFFF,
            "Max value 0xFFFF should be accepted")
    
    def test_set_get_reload(self):
        """set_reload then get_reload; values >0xFFFF masked."""
        timers = Timers()
        
        # Set and get basic value
        timers.set_reload(0, 0x5678)
        self.assertEqual(timers.get_reload(0), 0x5678,
            "get_reload should return set value")
        
        # Test masking to 0xFFFF
        timers.set_reload(1, 0xABCD1234)
        self.assertEqual(timers.get_reload(1), 0x1234,
            "Values >0xFFFF should be masked to 16 bits")
    
    def test_set_get_control(self):
        """set_control then get_control."""
        timers = Timers()
        
        # Set and get basic value
        timers.set_control(0, 0x80)
        self.assertEqual(timers.get_control(0), 0x80,
            "get_control should return set value")
        
        # Test masking to 0xFF
        timers.set_control(1, 0x123)
        self.assertEqual(timers.get_control(1), 0x23,
            "Values >0xFF should be masked to 8 bits")
    
    def test_invalid_channel_raises(self):
        """get_timer/set_timer/etc with channel=-1 and channel=4 raises ValueError."""
        timers = Timers()
        
        # Test negative channel
        with self.assertRaises(ValueError):
            timers.get_timer(-1)
        with self.assertRaises(ValueError):
            timers.set_timer(-1, 0)
        with self.assertRaises(ValueError):
            timers.set_control(-1, 0)
        with self.assertRaises(ValueError):
            timers.set_reload(-1, 0)
        with self.assertRaises(ValueError):
            timers.get_control(-1)
        with self.assertRaises(ValueError):
            timers.get_reload(-1)
        with self.assertRaises(ValueError):
            timers.get_overflow_flag(-1)
        with self.assertRaises(ValueError):
            timers.clear_overflow_flag(-1)
        
        # Test out-of-range channel
        with self.assertRaises(ValueError):
            timers.get_timer(4)
        with self.assertRaises(ValueError):
            timers.set_timer(4, 0)
        with self.assertRaises(ValueError):
            timers.set_control(4, 0)
        with self.assertRaises(ValueError):
            timers.set_reload(4, 0)


class TestTimerCounting(unittest.TestCase):
    """Timer counting behavior with prescalers."""
    
    def test_enable_resets_to_reload(self):
        """Set reload=0x1000, enable timer (control=0x80), count should be 0x1000."""
        timers = Timers()
        
        timers.set_reload(0, 0x1000)
        self.assertEqual(timers.get_timer(0), 0,
            "Count should be 0 before enable")
        
        timers.set_control(0, 0x80)  # Enable timer
        self.assertEqual(timers.get_timer(0), 0x1000,
            "Count should be reset to reload value on enable")
    
    def test_basic_counting_prescaler_1(self):
        """Enable timer with prescaler=1 (control=0x80), step(100), count should be 100."""
        timers = Timers()
        
        timers.set_control(0, 0x80)  # Enable, prescaler=1
        timers.set_timer(0, 0)
        
        timers.step(100)
        self.assertEqual(timers.get_timer(0), 100,
            "With prescaler=1, count should increase by cycles")
    
    def test_prescaler_64(self):
        """control=0x81 (prescaler=64), step(128), count should be 2."""
        timers = Timers()
        
        timers.set_control(0, 0x81)  # Enable, prescaler=64
        timers.set_timer(0, 0)
        
        timers.step(128)
        self.assertEqual(timers.get_timer(0), 2,
            "With prescaler=64, 128 cycles should increment count by 2")
    
    def test_prescaler_256(self):
        """control=0x82 (prescaler=256), step(512), count should be 2."""
        timers = Timers()
        
        timers.set_control(0, 0x82)  # Enable, prescaler=256
        timers.set_timer(0, 0)
        
        timers.step(512)
        self.assertEqual(timers.get_timer(0), 2,
            "With prescaler=256, 512 cycles should increment count by 2")
    
    def test_prescaler_1024(self):
        """control=0x83 (prescaler=1024), step(2048), count should be 2."""
        timers = Timers()
        
        timers.set_control(0, 0x83)  # Enable, prescaler=1024
        timers.set_timer(0, 0)
        
        timers.step(2048)
        self.assertEqual(timers.get_timer(0), 2,
            "With prescaler=1024, 2048 cycles should increment count by 2")


class TestTimerOverflow(unittest.TestCase):
    """Timer overflow behavior: flags, wrapping, IRQ."""
    
    def test_overflow_sets_flag(self):
        """Enable timer with count=0xFFF0, prescaler=1, step(0x20), overflow flag should be True."""
        timers = Timers()
        
        timers.set_control(0, 0x80)  # Enable, prescaler=1
        timers.set_timer(0, 0xFFF0)
        
        timers.step(0x20)  # 0xFFF0 + 0x20 = 0x10010 > 0xFFFF
        self.assertTrue(timers.get_overflow_flag(0),
            "Overflow flag should be set when count exceeds 0xFFFF")
    
    def test_overflow_wraps_to_reload(self):
        """Enable timer with reload=0x1000, count=0xFFF0, prescaler=1, step(0x20),
        count should be (0xFFF0 + 0x20 - 0x10000) + 0x1000 = 0x1010."""
        timers = Timers()
        
        timers.set_control(0, 0x80)  # Enable, prescaler=1
        timers.set_reload(0, 0x1000)
        timers.set_timer(0, 0xFFF0)
        
        timers.step(0x20)  # 0xFFF0 + 0x20 = 0x10010, overflow
        # new_count = (0x10010 - 0x10000) + 0x1000 = 0x10 + 0x1000 = 0x1010
        self.assertEqual(timers.get_timer(0), 0x1010,
            "Count should wrap to (overflow - 0x10000) + reload")
    
    def test_overflow_irq(self):
        """Enable timer with IRQ enable (control=0xC0), count near overflow,
        step past overflow, MockInterrupts should have timer_irq called."""
        timers = Timers()
        interrupts = MockInterrupts()
        
        timers.attach_interrupts(interrupts)
        timers.set_control(0, 0xC0)  # Enable, IRQ enable, prescaler=1
        timers.set_timer(0, 0xFFF0)
        
        timers.step(0x20)  # Trigger overflow
        
        self.assertEqual(interrupts.irq_calls, [0],
            "timer_irq should be called with channel 0 on overflow")
    
    def test_disabled_timer_no_count(self):
        """Set control without bit 7, step, count should not change."""
        timers = Timers()
        
        timers.set_control(0, 0x40)  # IRQ enable only, NOT enabled
        timers.set_timer(0, 0)
        
        timers.step(1000)
        self.assertEqual(timers.get_timer(0), 0,
            "Disabled timer should not count")
    
    def test_no_active_timers_clears_flags(self):
        """Set overflow flag manually, step with no active timers, flags should be cleared."""
        timers = Timers()
        
        # Manually set overflow flag (via internal access)
        timers._overflow_flags[0] = True
        
        # Step with no active timers
        timers.step(100)
        
        self.assertFalse(timers.get_overflow_flag(0),
            "Overflow flags should be cleared when no timers are active")
    
    def test_overflow_flag_cleared_next_step(self):
        """Overflow happens in one step, next step without overflow clears the flag."""
        timers = Timers()
        
        timers.set_control(0, 0x80)  # Enable, prescaler=1
        timers.set_timer(0, 0xFFF0)
        
        # First step: trigger overflow
        timers.step(0x20)
        self.assertTrue(timers.get_overflow_flag(0),
            "Overflow flag should be set after overflow")
        
        # Second step: no overflow
        timers.step(100)
        self.assertFalse(timers.get_overflow_flag(0),
            "Overflow flag should be cleared on next step without overflow")


class TestTimerCascade(unittest.TestCase):
    """Timer cascade mode behavior."""
    
    def test_cascade_mode(self):
        """Enable timer0 with prescaler=1, enable timer1 with cascade (control=0x84),
        step to overflow timer0, then next step timer1 should increment.
        
        Cascade mode uses the overflow state from the PREVIOUS step (saved before
        clearing flags), so timer1 increments on the step AFTER timer0 overflows."""
        timers = Timers()
        
        # Enable timer0 with prescaler=1
        timers.set_control(0, 0x80)
        timers.set_timer(0, 0xFFF0)
        
        # Enable timer1 with cascade mode (bit 2) and prescaler=0
        # control = 0x80 (enable) | 0x04 (cascade) | 0x00 (prescaler=1)
        timers.set_control(1, 0x84)
        timers.set_timer(1, 0)
        
        # First step: timer0 overflows, but timer1 doesn't increment yet
        # (cascade uses previous step's overflow state, which was False)
        timers.step(0x20)
        
        # Timer0 should have overflowed
        self.assertTrue(timers.get_overflow_flag(0),
            "Timer0 should have overflowed")
        self.assertEqual(timers.get_timer(1), 0,
            "Timer1 should NOT increment on first overflow (cascade uses previous state)")
        
        # Second step: timer1 should now increment because timer0 overflowed in previous step
        timers.step(1)
        
        self.assertEqual(timers.get_timer(1), 1,
            "Timer1 should increment by 1 on step after timer0 overflows")


class TestOverflowFlagOperations(unittest.TestCase):
    """Overflow flag get/clear operations."""
    
    def test_clear_overflow_flag(self):
        """clear_overflow_flag sets flag to False."""
        timers = Timers()
        
        # Manually set overflow flag
        timers._overflow_flags[0] = True
        self.assertTrue(timers.get_overflow_flag(0))
        
        # Clear it
        timers.clear_overflow_flag(0)
        self.assertFalse(timers.get_overflow_flag(0),
            "clear_overflow_flag should set flag to False")
    
    def test_cascade_uses_saved_overflow_state(self):
        """Cascade mode uses overflow state saved BEFORE step() clears flags.
        
        The cascade tuple is captured at the start of step(), so a timer in
        cascade mode increments on the step AFTER its predecessor overflows."""
        timers = Timers()
        
        # Set up timer0 to overflow
        timers.set_control(0, 0x80)
        timers.set_timer(0, 0xFFF0)
        
        # Set up timer1 in cascade mode
        timers.set_control(1, 0x84)  # Enable + cascade
        timers.set_timer(1, 0)
        
        # First step: timer0 overflows, flag is set
        timers.step(0x20)
        self.assertTrue(timers.get_overflow_flag(0))
        self.assertEqual(timers.get_timer(1), 0,
            "Timer1 should not increment on first step (previous overflow was False)")
        
        # Second step: timer1 increments because timer0 overflowed in previous step
        timers.step(1)
        self.assertEqual(timers.get_timer(1), 1,
            "Timer1 should increment when timer0's previous overflow is detected")


if __name__ == '__main__':
    unittest.main()