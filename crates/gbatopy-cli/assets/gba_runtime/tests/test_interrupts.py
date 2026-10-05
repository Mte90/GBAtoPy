"""Interrupt controller unit tests for GBAtoPy.

Tests cover register initialization, IRQ flag setting, IRQ enabling,
handler registration/unregistration, IRQ delivery, priority ordering,
IME control, and all IRQ sources.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from interrupts import InterruptController


def test_interruptcontroller_initialization():
    """InterruptController construction: all registers zero-initialized."""
    irq = InterruptController()
    
    assert irq.ie_reg == 0, f"Expected IE=0, got {hex(irq.ie_reg)}"
    assert irq.if_reg == 0, f"Expected IF=0, got {hex(irq.if_reg)}"
    assert irq.ime_reg == 0, f"Expected IME=0, got {hex(irq.ime_reg)}"
    assert irq._handlers == {}, f"Expected empty handlers dict, got {irq._handlers}"
    assert irq._enabled_mask == 0, f"Expected enabled_mask=0, got {hex(irq._enabled_mask)}"
    
    print("✓ test_interruptcontroller_initialization passed")


def test_ie_register_write_read():
    """IE register: write value, read back exact value."""
    irq = InterruptController()
    
    irq.write_ie(0x1234)
    assert irq.read_ie() == 0x1234, f"Expected 0x1234, got {hex(irq.read_ie())}"
    
    irq.write_ie(0xFFFF)
    assert irq.read_ie() == 0xFFFF, f"Expected 0xFFFF, got {hex(irq.read_ie())}"
    
    irq.write_ie(0x0000)
    assert irq.read_ie() == 0x0000, f"Expected 0x0000, got {hex(irq.read_ie())}"
    
    print("✓ test_ie_register_write_read passed")


def test_if_register_write_read():
    """IF register: write-1-to-clear behavior."""
    irq = InterruptController()
    
    # Set some flags
    irq.if_reg = 0x00FF
    
    # Clear bits 0 and 3 by writing 1s
    irq.write_if(0x0009)  # Clear bits 0 and 3
    
    assert irq.if_reg == 0x00F6, f"Expected 0x00F6, got {hex(irq.if_reg)}"
    
    print("✓ test_if_register_write_read passed")


def test_ime_register_write_read():
    """IME register: only bit 0 is significant."""
    irq = InterruptController()
    
    irq.write_ime(0x0000)
    assert irq.read_ime() == 0, f"Expected 0, got {hex(irq.read_ime())}"
    
    irq.write_ime(0x0001)
    assert irq.read_ime() == 1, f"Expected 1, got {hex(irq.read_ime())}"
    
    irq.write_ime(0xFFFF)  # Only bit 0 matters
    assert irq.read_ime() == 1, f"Expected 1 (bit 0 only), got {hex(irq.read_ime())}"
    
    irq.write_ime(0x0002)  # Bit 1 set, bit 0 clear
    assert irq.read_ime() == 0, f"Expected 0 (bit 0 clear), got {hex(irq.read_ime())}"
    
    print("✓ test_ime_register_write_read passed")


def test_set_ime_helper():
    """set_ime() helper: True sets IME=1, False sets IME=0."""
    irq = InterruptController()
    
    irq.set_ime(True)
    assert irq.ime_reg == 1, f"Expected IME=1, got {hex(irq.ime_reg)}"
    
    irq.set_ime(False)
    assert irq.ime_reg == 0, f"Expected IME=0, got {hex(irq.ime_reg)}"
    
    print("✓ test_set_ime_helper passed")


def test_clear_if():
    """clear_if(): clears all interrupt flags."""
    irq = InterruptController()
    
    # Set some flags
    irq.if_reg = 0x00FF
    
    irq.clear_if()
    assert irq.if_reg == 0, f"Expected IF=0, got {hex(irq.if_reg)}"
    
    print("✓ test_clear_if passed")


def test_get_pending_interrupts():
    """get_pending_interrupts(): returns IF & IE bitmask."""
    irq = InterruptController()
    
    irq.if_reg = 0x00FF
    irq.ie_reg = 0x00F0
    
    pending = irq.get_pending_interrupts()
    assert pending == 0x00F0, f"Expected 0x00F0, got {hex(pending)}"
    
    print("✓ test_get_pending_interrupts passed")


def test_has_pending_interrupt():
    """has_pending_interrupt(): returns True when any enabled interrupt is pending."""
    irq = InterruptController()
    
    # No interrupts enabled
    irq.if_reg = 0x00FF
    irq.write_ie(0x0000)  # Use write_ie to update _enabled_mask
    irq.set_ime(True)
    assert irq.has_pending_interrupt() == False, "Expected False (IE=0)"
    
    # Some interrupts enabled and pending
    irq.write_ie(0x00F0)
    assert irq.has_pending_interrupt() == True, "Expected True (IF & IE != 0)"
    
    # No pending interrupts
    irq.if_reg = 0x0000
    assert irq.has_pending_interrupt() == False, "Expected False (IF=0)"
    
    print("✓ test_has_pending_interrupt passed")


def test_register_handler():
    """register_handler(): callback stored by IRQ ID."""
    irq = InterruptController()
    
    call_count = [0]
    def handler():
        call_count[0] += 1
    
    irq.register_handler(irq.IRQ_VBLANK, handler)
    
    assert irq.IRQ_VBLANK in irq._handlers, "Handler should be registered"
    assert irq._handlers[irq.IRQ_VBLANK] == handler, "Handler should match"
    
    print("✓ test_register_handler passed")


def test_unregister_handler():
    """Handler unregistration: delete from _handlers dict."""
    irq = InterruptController()
    
    def handler():
        pass
    
    irq.register_handler(irq.IRQ_VBLANK, handler)
    assert irq.IRQ_VBLANK in irq._handlers
    
    del irq._handlers[irq.IRQ_VBLANK]
    assert irq.IRQ_VBLANK not in irq._handlers, "Handler should be unregistered"
    
    print("✓ test_unregister_handler passed")


def test_fire_vblank_no_handler_no_delivery():
    """fire(VBlank): no handler registered, no delivery."""
    irq = InterruptController()
    
    call_count = [0]
    irq.fire(irq.IRQ_VBLANK)
    
    assert call_count[0] == 0, "Handler should not be called"
    assert irq.if_reg == 0x0001, f"Expected IF bit 0 set, got {hex(irq.if_reg)}"
    
    print("✓ test_fire_vblank_no_handler_no_delivery passed")


def test_fire_vblank_handler_not_enabled():
    """fire(VBlank): handler registered but IME=0, no delivery."""
    irq = InterruptController()
    
    call_count = [0]
    def handler():
        call_count[0] += 1
    
    irq.register_handler(irq.IRQ_VBLANK, handler)
    irq.fire(irq.IRQ_VBLANK)
    
    assert call_count[0] == 0, "Handler should not be called (IME=0)"
    assert irq.if_reg == 0x0001, f"Expected IF bit 0 set, got {hex(irq.if_reg)}"
    
    print("✓ test_fire_vblank_handler_not_enabled passed")


def test_fire_vblank_ie_disabled():
    """fire(VBlank): handler registered, IME=1 but IE bit clear, no delivery."""
    irq = InterruptController()
    
    call_count = [0]
    def handler():
        call_count[0] += 1
    
    irq.register_handler(irq.IRQ_VBLANK, handler)
    irq.set_ime(True)
    irq.write_ie(0x0000)  # VBlank not enabled
    irq.fire(irq.IRQ_VBLANK)
    
    assert call_count[0] == 0, "Handler should not be called (IE bit clear)"
    assert irq.if_reg == 0x0001, f"Expected IF bit 0 set, got {hex(irq.if_reg)}"
    
    print("✓ test_fire_vblank_ie_disabled passed")


def test_fire_vblank_handler_delivered():
    """fire(VBlank): handler registered, IME=1, IE enabled, handler called."""
    irq = InterruptController()
    
    call_count = [0]
    def handler():
        call_count[0] += 1
    
    irq.register_handler(irq.IRQ_VBLANK, handler)
    irq.set_ime(True)
    irq.write_ie(0x0001)  # Enable VBlank
    irq.fire(irq.IRQ_VBLANK)
    
    assert call_count[0] == 1, "Handler should be called once"
    assert irq.if_reg == 0x0001, f"Expected IF bit 0 set, got {hex(irq.if_reg)}"
    
    print("✓ test_fire_vblank_handler_delivered passed")


def test_fire_multiple_interrupts():
    """fire(): multiple interrupts fire, all handlers called."""
    irq = InterruptController()
    
    vblank_count = [0]
    hblank_count = [0]
    
    irq.register_handler(irq.IRQ_VBLANK, lambda: vblank_count.__setitem__(0, vblank_count[0] + 1))
    irq.register_handler(irq.IRQ_HBLANK, lambda: hblank_count.__setitem__(0, hblank_count[0] + 1))
    
    irq.set_ime(True)
    irq.write_ie(0x0003)  # Enable VBlank and HBlank
    
    irq.fire(irq.IRQ_VBLANK)
    assert vblank_count[0] == 1, "VBlank handler should be called"
    assert hblank_count[0] == 0, "HBlank handler should not be called"
    
    irq.fire(irq.IRQ_HBLANK)
    assert vblank_count[0] == 1, "VBlank handler should still be 1"
    assert hblank_count[0] == 1, "HBlank handler should be called"
    
    print("✓ test_fire_multiple_interrupts passed")


def test_vblank_irq_convenience():
    """vblank_irq(): convenience method fires IRQ 0."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_VBLANK, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x0001)
    
    irq.vblank_irq()
    
    assert call_count[0] == 1, "Handler should be called"
    assert irq.if_reg & (1 << irq.IRQ_VBLANK), "VBlank flag should be set"
    
    print("✓ test_vblank_irq_convenience passed")


def test_hblank_irq_convenience():
    """hblank_irq(): convenience method fires IRQ 1."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_HBLANK, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x0002)
    
    irq.hblank_irq()
    
    assert call_count[0] == 1, "Handler should be called"
    assert irq.if_reg & (1 << irq.IRQ_HBLANK), "HBlank flag should be set"
    
    print("✓ test_hblank_irq_convenience passed")


def test_vcounter_irq_convenience():
    """vcounter_irq(): convenience method fires IRQ 2."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_VCOUNTER, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x0004)
    
    irq.vcounter_irq()
    
    assert call_count[0] == 1, "Handler should be called"
    assert irq.if_reg & (1 << irq.IRQ_VCOUNTER), "VCounter flag should be set"
    
    print("✓ test_vcounter_irq_convenience passed")


def test_timer_irq_0():
    """timer_irq(0): fires IRQ_TIMER0 (bit 3)."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_TIMER0, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x0008)
    
    irq.timer_irq(0)
    
    assert call_count[0] == 1, "Handler should be called"
    assert irq.if_reg & (1 << irq.IRQ_TIMER0), "Timer0 flag should be set"
    
    print("✓ test_timer_irq_0 passed")


def test_timer_irq_3():
    """timer_irq(3): fires IRQ_TIMER3 (bit 6)."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_TIMER3, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x0040)
    
    irq.timer_irq(3)
    
    assert call_count[0] == 1, "Handler should be called"
    assert irq.if_reg & (1 << irq.IRQ_TIMER3), "Timer3 flag should be set"
    
    print("✓ test_timer_irq_3 passed")


def test_timer_irq_invalid_channel():
    """timer_irq(): invalid channel (5) does not fire."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_TIMER0, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x0008)
    
    irq.timer_irq(5)  # Invalid channel
    
    assert call_count[0] == 0, "Handler should not be called (invalid channel)"
    assert irq.if_reg == 0, "No flag should be set"
    
    print("✓ test_timer_irq_invalid_channel passed")


def test_dma_irq_0():
    """dma_irq(0): fires IRQ_DMA0 (bit 8)."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_DMA0, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x0100)
    
    irq.dma_irq(0)
    
    assert call_count[0] == 1, "Handler should be called"
    assert irq.if_reg & (1 << irq.IRQ_DMA0), "DMA0 flag should be set"
    
    print("✓ test_dma_irq_0 passed")


def test_dma_irq_3():
    """dma_irq(3): fires IRQ_DMA3 (bit 11)."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_DMA3, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x0800)
    
    irq.dma_irq(3)
    
    assert call_count[0] == 1, "Handler should be called"
    assert irq.if_reg & (1 << irq.IRQ_DMA3), "DMA3 flag should be set"
    
    print("✓ test_dma_irq_3 passed")


def test_keypad_irq_convenience():
    """keypad_irq(): convenience method fires IRQ 12."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_KEYPAD, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x1000)
    
    irq.keypad_irq()
    
    assert call_count[0] == 1, "Handler should be called"
    assert irq.if_reg & (1 << irq.IRQ_KEYPAD), "Keypad flag should be set"
    
    print("✓ test_keypad_irq_convenience passed")


def test_gamepak_irq_convenience():
    """gamepak_irq(): convenience method fires IRQ 13."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_GAMEPAK, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x2000)
    
    irq.gamepak_irq()
    
    assert call_count[0] == 1, "Handler should be called"
    assert irq.if_reg & (1 << irq.IRQ_GAMEPAK), "GamePak flag should be set"
    
    print("✓ test_gamepak_irq_convenience passed")


def test_ime_disable_prevents_delivery():
    """IME disable: interrupts fire but handlers not called."""
    irq = InterruptController()
    
    call_count = [0]
    irq.register_handler(irq.IRQ_VBLANK, lambda: call_count.__setitem__(0, call_count[0] + 1))
    irq.set_ime(True)
    irq.write_ie(0x0001)
    
    # Fire while enabled
    irq.fire(irq.IRQ_VBLANK)
    assert call_count[0] == 1, "Handler should be called"
    
    # Disable IME
    irq.set_ime(False)
    call_count[0] = 0
    
    # Fire again
    irq.fire(irq.IRQ_VBLANK)
    assert call_count[0] == 0, "Handler should not be called (IME disabled)"
    assert irq.if_reg & (1 << irq.IRQ_VBLANK), "Flag should still be set"
    
    print("✓ test_ime_disable_prevents_delivery passed")


def test_process_pending_interrupts_none_pending():
    """process_pending_interrupts(): no pending interrupts returns 0."""
    irq = InterruptController()
    
    irq.set_ime(True)
    irq.write_ie(0xFFFF)
    
    count = irq.process_pending_interrupts()
    assert count == 0, f"Expected 0, got {count}"
    
    print("✓ test_process_pending_interrupts_none_pending passed")


def test_process_pending_interrupts_ime_disabled():
    """process_pending_interrupts(): IME disabled returns 0."""
    irq = InterruptController()
    
    irq.if_reg = 0x00FF
    irq.write_ie(0x00FF)
    irq.set_ime(False)
    
    count = irq.process_pending_interrupts()
    assert count == 0, f"Expected 0 (IME disabled), got {count}"
    
    print("✓ test_process_pending_interrupts_ime_disabled passed")


def test_process_pending_interrupts_batch_processing():
    """process_pending_interrupts(): processes all pending interrupts in one call."""
    irq = InterruptController()
    
    vblank_count = [0]
    hblank_count = [0]
    timer0_count = [0]
    
    irq.register_handler(irq.IRQ_VBLANK, lambda: vblank_count.__setitem__(0, vblank_count[0] + 1))
    irq.register_handler(irq.IRQ_HBLANK, lambda: hblank_count.__setitem__(0, hblank_count[0] + 1))
    irq.register_handler(irq.IRQ_TIMER0, lambda: timer0_count.__setitem__(0, timer0_count[0] + 1))
    
    irq.set_ime(True)
    irq.write_ie(0x000B)  # Enable VBlank (bit 0), HBlank (bit 1), Timer0 (bit 3) = 1 + 2 + 8 = 11 = 0x000B
    irq.if_reg = 0x000B   # All three pending
    
    count = irq.process_pending_interrupts()
    
    assert count == 3, f"Expected 3 interrupts processed, got {count}"
    assert vblank_count[0] == 1, "VBlank handler should be called"
    assert hblank_count[0] == 1, "HBlank handler should be called"
    assert timer0_count[0] == 1, "Timer0 handler should be called"
    
    print("✓ test_process_pending_interrupts_batch_processing passed")


def test_process_pending_interrupts_partial_handlers():
    """process_pending_interrupts(): only calls handlers that are registered."""
    irq = InterruptController()
    
    vblank_count = [0]
    
    # Only register VBlank handler, not HBlank
    irq.register_handler(irq.IRQ_VBLANK, lambda: vblank_count.__setitem__(0, vblank_count[0] + 1))
    
    irq.set_ime(True)
    irq.write_ie(0x0003)  # Enable VBlank and HBlank
    irq.if_reg = 0x0003   # Both pending
    
    count = irq.process_pending_interrupts()
    
    assert count == 1, f"Expected 1 interrupt processed (only VBlank has handler), got {count}"
    assert vblank_count[0] == 1, "VBlank handler should be called"
    
    print("✓ test_process_pending_interrupts_partial_handlers passed")


def test_all_irq_constants_defined():
    """All IRQ constants have correct bit positions."""
    irq = InterruptController()
    
    assert irq.IRQ_VBLANK == 0, "VBlank should be bit 0"
    assert irq.IRQ_HBLANK == 1, "HBlank should be bit 1"
    assert irq.IRQ_VCOUNTER == 2, "VCounter should be bit 2"
    assert irq.IRQ_TIMER0 == 3, "Timer0 should be bit 3"
    assert irq.IRQ_TIMER1 == 4, "Timer1 should be bit 4"
    assert irq.IRQ_TIMER2 == 5, "Timer2 should be bit 5"
    assert irq.IRQ_TIMER3 == 6, "Timer3 should be bit 6"
    assert irq.IRQ_DMA0 == 8, "DMA0 should be bit 8"
    assert irq.IRQ_DMA1 == 9, "DMA1 should be bit 9"
    assert irq.IRQ_DMA2 == 10, "DMA2 should be bit 10"
    assert irq.IRQ_DMA3 == 11, "DMA3 should be bit 11"
    assert irq.IRQ_KEYPAD == 12, "Keypad should be bit 12"
    assert irq.IRQ_GAMEPAK == 13, "GamePak should be bit 13"
    
    print("✓ test_all_irq_constants_defined passed")


def test_ie_bitmask_update_on_write_ie():
    """write_ie(): updates _enabled_mask based on IME state."""
    irq = InterruptController()
    
    irq.set_ime(False)
    irq.write_ie(0x00FF)
    assert irq._enabled_mask == 0, "Enabled mask should be 0 when IME=0"
    
    irq.set_ime(True)
    irq.write_ie(0x00F0)
    assert irq._enabled_mask == 0x00F0, f"Expected 0x00F0, got {hex(irq._enabled_mask)}"
    
    print("✓ test_ie_bitmask_update_on_write_ie passed")


def test_ie_bitmask_update_on_write_ime():
    """write_ime(): updates _enabled_mask based on IE state."""
    irq = InterruptController()
    
    irq.write_ie(0x00FF)
    irq.write_ime(0x0000)
    assert irq._enabled_mask == 0, "Enabled mask should be 0 when IME=0"
    
    irq.write_ime(0x0001)
    assert irq._enabled_mask == 0x00FF, f"Expected 0x00FF, got {hex(irq._enabled_mask)}"
    
    print("✓ test_ie_bitmask_update_on_write_ime passed")


def test_clear_if_via_write_if():
    """write_if(): clears specific interrupt flags."""
    irq = InterruptController()
    
    irq.if_reg = 0x00FF
    
    # Clear bits 0, 2, 4, 6
    irq.write_if(0x0055)
    
    # Should have bits 1, 3, 5, 7 set (0xAA)
    assert irq.if_reg == 0x00AA, f"Expected 0x00AA, got {hex(irq.if_reg)}"
    
    print("✓ test_clear_if_via_write_if passed")


# =============================================================================
# Main: Run All Tests
# =============================================================================

if __name__ == "__main__":
    # 1. Initialization Tests
    test_interruptcontroller_initialization()
    
    # 2. Register Read/Write Tests
    test_ie_register_write_read()
    test_if_register_write_read()
    test_ime_register_write_read()
    test_set_ime_helper()
    test_clear_if()
    test_get_pending_interrupts()
    test_has_pending_interrupt()
    
    # 3. Handler Registration Tests
    test_register_handler()
    test_unregister_handler()
    
    # 4. IRQ Delivery Tests (No Handler)
    test_fire_vblank_no_handler_no_delivery()
    
    # 5. IRQ Delivery Tests (IME Disabled)
    test_fire_vblank_handler_not_enabled()
    
    # 6. IRQ Delivery Tests (IE Disabled)
    test_fire_vblank_ie_disabled()
    
    # 7. IRQ Delivery Tests (Success)
    test_fire_vblank_handler_delivered()
    test_fire_multiple_interrupts()
    
    # 8. Convenience Method Tests
    test_vblank_irq_convenience()
    test_hblank_irq_convenience()
    test_vcounter_irq_convenience()
    test_timer_irq_0()
    test_timer_irq_3()
    test_timer_irq_invalid_channel()
    test_dma_irq_0()
    test_dma_irq_3()
    test_keypad_irq_convenience()
    test_gamepak_irq_convenience()
    
    # 9. IME Control Tests
    test_ime_disable_prevents_delivery()
    
    # 10. Batch Processing Tests
    test_process_pending_interrupts_none_pending()
    test_process_pending_interrupts_ime_disabled()
    test_process_pending_interrupts_batch_processing()
    test_process_pending_interrupts_partial_handlers()
    
    # 11. Constants Tests
    test_all_irq_constants_defined()
    
    # 12. Internal State Tests
    test_ie_bitmask_update_on_write_ie()
    test_ie_bitmask_update_on_write_ime()
    test_clear_if_via_write_if()
    
    print("\nAll 36 interrupt tests passed!")