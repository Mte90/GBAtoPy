"""Tests for GBA Interrupt Controller"""

import pytest
from gba_runtime.interrupts import InterruptController


class TestInterruptController:
    """Test InterruptController class"""

    def test_qa_requirement(self):
        """QA: irq = InterruptController(); irq.fire(0); assert irq.if_reg & 0x0001"""
        irq = InterruptController()
        irq.fire(0)
        assert irq.if_reg & 0x0001

    def test_if_reg_set_on_fire(self):
        """Test that firing an interrupt sets the IF flag"""
        irq = InterruptController()
        irq.fire(0)
        assert irq.if_reg == 0x0001
        irq.fire(1)
        assert irq.if_reg == 0x0003
        irq.fire(13)
        assert irq.if_reg == 0x2003

    def test_if_reg_write_1_to_clear(self):
        """Test that writing 1 to IF register clears the flag"""
        irq = InterruptController()
        irq.fire(0)
        assert irq.if_reg & 0x0001
        irq.write_if(0x0001)
        assert irq.if_reg == 0x0000

    def test_ie_reg_write(self):
        """Test IE register write"""
        irq = InterruptController()
        irq.write_ie(0x0001)
        assert irq.ie_reg == 0x0001
        irq.write_ie(0xFFFF)
        assert irq.ie_reg == 0xFFFF

    def test_ime_reg_write(self):
        """Test IME register write"""
        irq = InterruptController()
        irq.write_ime(1)
        assert irq.ime_reg == 0x0001
        irq.write_ime(0)
        assert irq.ime_reg == 0x0000

    def test_handler_called_when_enabled(self):
        """Test that handler is called when IME=1 and IE bit is set"""
        irq = InterruptController()
        called = []

        def handler():
            called.append(True)

        irq.register_handler(0, handler)
        irq.ime_reg = 0x0001
        irq.ie_reg = 0x0001
        irq.fire(0)
        assert len(called) == 1

    def test_handler_not_called_when_ime_disabled(self):
        """Test that handler is NOT called when IME=0"""
        irq = InterruptController()
        called = []

        def handler():
            called.append(True)

        irq.register_handler(0, handler)
        irq.ime_reg = 0x0000
        irq.ie_reg = 0x0001
        irq.fire(0)
        assert len(called) == 0

    def test_handler_not_called_when_ie_disabled(self):
        """Test that handler is NOT called when IE bit is not set"""
        irq = InterruptController()
        called = []

        def handler():
            called.append(True)

        irq.register_handler(0, handler)
        irq.ime_reg = 0x0001
        irq.ie_reg = 0x0000
        irq.fire(0)
        assert len(called) == 0

    def test_vblank_irq_convenience(self):
        """Test vblank_irq convenience method"""
        irq = InterruptController()
        irq.vblank_irq()
        assert irq.if_reg & 0x0001

    def test_timer_irq_convenience(self):
        """Test timer_irq convenience method"""
        irq = InterruptController()
        irq.timer_irq(0)
        assert irq.if_reg & (1 << 3)
        irq.timer_irq(3)
        assert irq.if_reg & (1 << 6)

    def test_read_methods(self):
        """Test read methods"""
        irq = InterruptController()
        irq.write_ie(0x1234)
        irq.write_if(0x5678)
        irq.write_ime(1)
        assert irq.read_ie() == 0x1234
        assert irq.read_if() == 0x5678
        assert irq.read_ime() == 1

    def test_get_pending_interrupts(self):
        """Test pending interrupt bitmask calculation"""
        irq = InterruptController()
        irq.ie_reg = 0x000F
        irq.if_reg = 0x0007
        pending = irq.get_pending_interrupts()
        assert pending == 0x0007

    def test_has_pending_interrupt(self):
        """Test has_pending_interrupt method"""
        irq = InterruptController()
        irq.ime_reg = 0x0001
        irq.ie_reg = 0x0001
        irq.if_reg = 0x0001
        assert irq.has_pending_interrupt() is True
        irq.ime_reg = 0x0000
        assert irq.has_pending_interrupt() is False

    def test_clear_if(self):
        """Test clearing all IF flags"""
        irq = InterruptController()
        irq.fire(0)
        irq.fire(1)
        assert irq.if_reg != 0
        irq.clear_if()
        assert irq.if_reg == 0x0000

    def test_set_ime(self):
        """Test set_ime method"""
        irq = InterruptController()
        irq.set_ime(True)
        assert irq.ime_reg == 0x0001
        irq.set_ime(False)
        assert irq.ime_reg == 0x0000

    def test_multiple_interrupts_fire(self):
        """Test firing multiple different interrupts"""
        irq = InterruptController()
        irq.fire(0)
        irq.fire(3)
        irq.fire(8)
        irq.fire(12)
        expected = (1 << 0) | (1 << 3) | (1 << 8) | (1 << 12)
        assert irq.if_reg == expected

    def test_register_handler_various_ids(self):
        """Test registering handlers for various IRQ IDs"""
        irq = InterruptController()

        def dummy():
            pass

        for irq_id in [0, 1, 2, 3, 6, 8, 11, 12, 13]:
            irq.register_handler(irq_id, dummy)
            assert irq_id in irq._handlers
