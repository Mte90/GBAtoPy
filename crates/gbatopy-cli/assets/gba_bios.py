"""Minimal GBA BIOS Implementation - Pure Python

Provides 4 critical BIOS SWI handlers for GBAtoPy transpiler.
All functions follow ARM calling convention: r0-r3 = arguments, r0 = return value.
Eliminates need for external gba_bios.bin file - makes output truly standalone.
"""


def bios_halt():
    """Halt CPU execution until next interrupt.

    Called by ROMs in main loop to wait for VBlank.
    Sets flag that stops CPU step loop.
    Returns 0.
    """
    global _halted
    _halted = True
    return 0


def bios_vsync():
    """Wait for vertical blanking interval and trigger VBlank interrupt.

    Used by ROMs to synchronize rendering with display refresh.
    Sets VBlank flag in interrupt controller.
    Side effects: Sets VBlank interrupt flag, triggers IRQ handler if enabled.
    Returns 0.
    """
    global vblank_pending, irq_requested
    vblank_pending = True
    irq_requested = True
    return 0


def bios_div(dividend, divisor):
    """Perform 32-bit signed integer division.

    Used by ROMs for timing calculations, sprite positioning.
    Args: dividend (r0), divisor (r1)
    Returns: tuple (quotient in r0, remainder in r1)
    Division by zero returns (0, 0).
    """
    if divisor == 0:
        return (0, 0)
    quotient = int(dividend / divisor)
    remainder = dividend - (quotient * divisor)
    return (quotient, remainder)


def bios_sqrt(value):
    """Calculate integer square root using Newton's method.

    Used by ROMs for delay loops, distance calculations.
    Args: value (r0) - 32-bit unsigned integer
    Returns: int - floor(sqrt(value))
    sqrt(0) = 0, negative input returns 0.
    """
    if value <= 0:
        return 0
    guess = value
    while True:
        next_guess = (guess + value // guess) // 2
        if next_guess >= guess:
            return guess
        guess = next_guess


_halted = False
vblank_pending = False
irq_requested = False


def reset_bios_state():
    """Reset all BIOS internal state (called between ROM executions)."""
    global _halted, vblank_pending, irq_requested
    _halted = False
    vblank_pending = False
    irq_requested = False


def is_halted():
    """Check if CPU is in halted state."""
    return _halted


def clear_vblank_flag():
    """Clear VBlank pending flag after IRQ handler runs."""
    global vblank_pending
    vblank_pending = False


def clear_irq_flag():
    """Clear IRQ requested flag."""
    global irq_requested
    irq_requested = False
