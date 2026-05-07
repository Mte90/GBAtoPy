"""GBA Interrupt Controller"""


class InterruptController:
    """Interrupt controller managing IE, IF, and IME registers.

    Interrupt sources (bit positions):
        - VBlank: 0
        - HBlank: 1
        - VCounter: 2
        - Timer0-3: 3-6
        - DMA0-3: 8-11
        - KeyPad: 12
        - GamePak: 13
    """

    # Interrupt source bit positions
    IRQ_VBLANK = 0
    IRQ_HBLANK = 1
    IRQ_VCOUNTER = 2
    IRQ_TIMER0 = 3
    IRQ_TIMER1 = 4
    IRQ_TIMER2 = 5
    IRQ_TIMER3 = 6
    IRQ_DMA0 = 8
    IRQ_DMA1 = 9
    IRQ_DMA2 = 10
    IRQ_DMA3 = 11
    IRQ_KEYPAD = 12
    IRQ_GAMEPAK = 13

    def __init__(self):
        # IE: Interrupt Enable register (16-bit) - enables per-interrupt sources
        self.ie_reg = 0x0000
        # IF: Interrupt Flags register (16-bit) - raised interrupts, write 1 to clear
        self.if_reg = 0x0000
        # IME: Interrupt Master Enable register (1-bit)
        self.ime_reg = 0x0000
        # Handlers stored by interrupt source bit position
        self._handlers = {}

    def register_handler(self, irq_id: int, callback):
        """Register a callback for a specific interrupt source.

        Args:
            irq_id: Interrupt source bit position (0-13)
            callback: Function to call when interrupt fires and is enabled
        """
        self._handlers[irq_id] = callback

    def fire(self, irq_id: int):
        """Fire an interrupt - set the IF flag and call handler if enabled.

        Args:
            irq_id: Interrupt source bit position (0-13)
        """
        # Set the interrupt flag in IF register
        self.if_reg |= 1 << irq_id

        # Check if interrupt is enabled (IME=1 and IE bit for this irq is set)
        if self.ime_reg & 0x0001 and (self.ie_reg & (1 << irq_id)):
            # Call the handler if registered
            if irq_id in self._handlers:
                self._handlers[irq_id]()

    def vblank_irq(self):
        """Convenience method to fire a VBlank interrupt (IRQ 0)."""
        self.fire(self.IRQ_VBLANK)

    def hblank_irq(self):
        """Convenience method to fire a HBlank interrupt (IRQ 1)."""
        self.fire(self.IRQ_HBLANK)

    def vcounter_irq(self):
        """Convenience method to fire a VCounter interrupt (IRQ 2)."""
        self.fire(self.IRQ_VCOUNTER)

    def timer_irq(self, channel: int):
        """Convenience method to fire a timer interrupt.

        Args:
            channel: Timer channel (0-3), maps to IRQ 3-6
        """
        if 0 <= channel <= 3:
            self.fire(self.IRQ_TIMER0 + channel)

    def dma_irq(self, channel: int):
        """Convenience method to fire a DMA interrupt.

        Args:
            channel: DMA channel (0-3), maps to IRQ 8-11
        """
        if 0 <= channel <= 3:
            self.fire(self.IRQ_DMA0 + channel)

    def keypad_irq(self):
        """Convenience method to fire a KeyPad interrupt (IRQ 12)."""
        self.fire(self.IRQ_KEYPAD)

    def gamepak_irq(self):
        """Convenience method to fire a GamePak interrupt (IRQ 13)."""
        self.fire(self.IRQ_GAMEPAK)

    def write_ie(self, val: int):
        """Write to IE (Interrupt Enable) register.

        Args:
            val: 16-bit value to write
        """
        self.ie_reg = val & 0xFFFF

    def write_if(self, val: int):
        """Write to IF (Interrupt Flags) register.

        Writing 1 to a bit clears that interrupt flag.

        Args:
            val: 16-bit value to write
        """
        # Clear bits where val has 1s (write-1-to-clear behavior)
        self.if_reg &= ~(val & 0xFFFF)

    def write_ime(self, val: int):
        """Write to IME (Interrupt Master Enable) register.

        Args:
            val: 16-bit value (only bit 0 is significant)
        """
        self.ime_reg = val & 0x0001

    def read_ie(self) -> int:
        """Read IE register."""
        return self.ie_reg

    def read_if(self) -> int:
        """Read IF register."""
        return self.if_reg

    def read_ime(self) -> int:
        """Read IME register."""
        return self.ime_reg

    def get_pending_interrupts(self) -> int:
        """Get bitmask of pending and enabled interrupts."""
        return self.if_reg & self.ie_reg

    def has_pending_interrupt(self) -> bool:
        """Check if any enabled interrupt is pending."""
        return (self.ime_reg & 0x0001) and (self.if_reg & self.ie_reg) != 0

    def clear_if(self):
        """Clear all interrupt flags."""
        self.if_reg = 0x0000


def set_vblank_flag():
    interrupts.fire(InterruptController.IRQ_VBLANK)

    def set_ime(self, enabled: bool):
        """Set IME register.

        Args:
            enabled: True to enable interrupts, False to disable
        """
        self.ime_reg = 0x0001 if enabled else 0x0000
