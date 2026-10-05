"""DMA (Direct Memory Access) unit tests for GBAtoPy.

Tests cover immediate transfers, HBlank/VBlank timing, increment/decrement modes,
repeat mode, and critical runtime invariants (full-count burst for HBlank/VBlank).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from memory import Memory
from dma import DMA, DMAChannel


class MockInterrupts:
    def vblank_irq(self): pass
    def hblank_irq(self): pass
    def vcounter_irq(self): pass
    def dma_irq(self, channel_id): pass


def setup_dma(memory, channel, src, dst, count, timing=0, bit32=False, repeat=False, src_inc=0, dst_inc=0, irq=False):
    """Configure DMA channel registers in MMIO.
    
    Control register layout (verified against dma.py):
      bit 15: Enable
      bit 14: IRQ enable
      bits 13-12: Timing (0=immediate, 1=VBlank, 2=HBlank, 3=special)
      bit 11: DRQ (DMA3 only)
      bit 10: 32-bit (0=16-bit, 1=32-bit)
      bit 9: Repeat
      bits 8-7: Source control (0=inc, 1=dec, 2=fixed, 3=prohibited)
      bits 6-5: Destination control (0=inc, 1=dec, 2=fixed, 3=reload)
    """
    base = 0x040000B0 + channel * 0x0C
    memory.write_u32(base + 0, src)       # source
    memory.write_u32(base + 4, dst)       # destination
    memory.write_u16(base + 8, count)     # count
    ctrl = (1 << 15) | (irq << 14) | (timing << 12) | (bit32 << 10) | (repeat << 9)
    # source control: bits 7-8
    ctrl |= (src_inc << 7)
    # destination control: bits 5-6
    ctrl |= (dst_inc << 5)
    memory.write_u16(base + 10, ctrl)     # control


def make_dma():
    """Create Memory + DMA with mock interrupts."""
    memory = Memory()
    dma = DMA()
    interrupts = MockInterrupts()
    dma.attach_memory(memory)
    dma.attach_interrupts(interrupts)
    return memory, dma


# =============================================================================
# 1. Immediate Transfer Tests
# =============================================================================

def test_16bit_immediate_transfer():
    """16-bit immediate transfer: 4 halfwords from EWRAM to IWRAM."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM: 4 halfwords with known values
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0x1234)
    memory.write_u16(src_addr + 2, 0x5678)
    memory.write_u16(src_addr + 4, 0x9ABC)
    memory.write_u16(src_addr + 6, 0xDEF0)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 for immediate 16-bit transfer of 4 halfwords
    setup_dma(memory, 0, src_addr, dst_addr, 4, timing=0, bit32=False)
    
    # Trigger immediate transfer
    dma.start_transfer(0)
    
    # Verify destination contains source data
    assert memory.read_u16(dst_addr + 0) == 0x1234, f"Expected 0x1234, got {hex(memory.read_u16(dst_addr + 0))}"
    assert memory.read_u16(dst_addr + 2) == 0x5678, f"Expected 0x5678, got {hex(memory.read_u16(dst_addr + 2))}"
    assert memory.read_u16(dst_addr + 4) == 0x9ABC, f"Expected 0x9ABC, got {hex(memory.read_u16(dst_addr + 4))}"
    assert memory.read_u16(dst_addr + 6) == 0xDEF0, f"Expected 0xDEF0, got {hex(memory.read_u16(dst_addr + 6))}"
    
    print("✓ test_16bit_immediate_transfer passed")


def test_32bit_immediate_transfer():
    """32-bit immediate transfer: 2 words from EWRAM to IWRAM."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM: 2 words with known values
    src_addr = 0x02000000
    memory.write_u32(src_addr + 0, 0x12345678)
    memory.write_u32(src_addr + 4, 0x9ABCDEF0)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 for immediate 32-bit transfer of 2 words
    setup_dma(memory, 0, src_addr, dst_addr, 2, timing=0, bit32=True)
    
    # Trigger immediate transfer
    dma.start_transfer(0)
    
    # Verify destination contains source data
    assert memory.read_u32(dst_addr + 0) == 0x12345678, f"Expected 0x12345678, got {hex(memory.read_u32(dst_addr + 0))}"
    assert memory.read_u32(dst_addr + 4) == 0x9ABCDEF0, f"Expected 0x9ABCDEF0, got {hex(memory.read_u32(dst_addr + 4))}"
    
    print("✓ test_32bit_immediate_transfer passed")


def test_fixed_source_transfer():
    """Fixed source (src=2): all 4 halfwords get same value."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM: single value
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0xABCD)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 with fixed source (src_inc=2)
    setup_dma(memory, 0, src_addr, dst_addr, 4, timing=0, bit32=False, src_inc=2)
    
    # Trigger immediate transfer
    dma.start_transfer(0)
    
    # All 4 halfwords should have the same value
    assert memory.read_u16(dst_addr + 0) == 0xABCD, f"Expected 0xABCD, got {hex(memory.read_u16(dst_addr + 0))}"
    assert memory.read_u16(dst_addr + 2) == 0xABCD, f"Expected 0xABCD, got {hex(memory.read_u16(dst_addr + 2))}"
    assert memory.read_u16(dst_addr + 4) == 0xABCD, f"Expected 0xABCD, got {hex(memory.read_u16(dst_addr + 4))}"
    assert memory.read_u16(dst_addr + 6) == 0xABCD, f"Expected 0xABCD, got {hex(memory.read_u16(dst_addr + 6))}"
    
    print("✓ test_fixed_source_transfer passed")


# =============================================================================
# 2. HBlank/VBlank Timing Tests
# =============================================================================

def test_hblank_trigger():
    """HBlank trigger: data NOT transferred until hblank_fire() is called."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0x1111)
    memory.write_u16(src_addr + 2, 0x2222)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 for HBlank timing (timing=2)
    setup_dma(memory, 0, src_addr, dst_addr, 2, timing=2, bit32=False)
    
    # Before hblank_fire, destination should be empty (zeros)
    assert memory.read_u16(dst_addr + 0) == 0, f"Expected 0 before hblank_fire, got {hex(memory.read_u16(dst_addr + 0))}"
    
    # Trigger HBlank
    dma.hblank_fire(0)
    
    # After hblank_fire, data should be transferred
    assert memory.read_u16(dst_addr + 0) == 0x1111, f"Expected 0x1111, got {hex(memory.read_u16(dst_addr + 0))}"
    assert memory.read_u16(dst_addr + 2) == 0x2222, f"Expected 0x2222, got {hex(memory.read_u16(dst_addr + 2))}"
    
    print("✓ test_hblank_trigger passed")


def test_vblank_trigger():
    """VBlank trigger: data NOT transferred until vblank_fire() is called."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0x3333)
    memory.write_u16(src_addr + 2, 0x4444)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 for VBlank timing (timing=1)
    setup_dma(memory, 0, src_addr, dst_addr, 2, timing=1, bit32=False)
    
    # Before vblank_fire, destination should be empty (zeros)
    assert memory.read_u16(dst_addr + 0) == 0, f"Expected 0 before vblank_fire, got {hex(memory.read_u16(dst_addr + 0))}"
    
    # Trigger VBlank
    dma.vblank_fire()
    
    # After vblank_fire, data should be transferred
    assert memory.read_u16(dst_addr + 0) == 0x3333, f"Expected 0x3333, got {hex(memory.read_u16(dst_addr + 0))}"
    assert memory.read_u16(dst_addr + 2) == 0x4444, f"Expected 0x4444, got {hex(memory.read_u16(dst_addr + 2))}"
    
    print("✓ test_vblank_trigger passed")


def test_no_transfer_when_disabled():
    """No transfer when enable bit not set."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0x5555)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 with enable bit NOT set (remove bit 15 from control)
    base = 0x040000B0
    memory.write_u32(base + 0, src_addr)       # source
    memory.write_u32(base + 4, dst_addr)       # destination
    memory.write_u16(base + 8, 1)              # count
    ctrl = (2 << 22)  # HBlank timing, NO enable bit
    memory.write_u16(base + 10, ctrl)          # control
    
    # Trigger HBlank
    dma.hblank_fire(0)
    
    # Destination should still be zero (DMA was disabled)
    assert memory.read_u16(dst_addr + 0) == 0, f"Expected 0 (DMA disabled), got {hex(memory.read_u16(dst_addr + 0))}"
    
    print("✓ test_no_transfer_when_disabled passed")


# =============================================================================
# 3. Increment/Decrement Tests
# =============================================================================

def test_destination_increment():
    """Destination increment: source has 4 different values, dest receives them in order."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM: 4 different values
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0x1000)
    memory.write_u16(src_addr + 2, 0x2000)
    memory.write_u16(src_addr + 4, 0x3000)
    memory.write_u16(src_addr + 6, 0x4000)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 with destination increment (dst_inc=0, default)
    setup_dma(memory, 0, src_addr, dst_addr, 4, timing=0, bit32=False, dst_inc=0)
    
    # Trigger transfer
    dma.start_transfer(0)
    
    # Verify values are in order
    assert memory.read_u16(dst_addr + 0) == 0x1000, f"Expected 0x1000, got {hex(memory.read_u16(dst_addr + 0))}"
    assert memory.read_u16(dst_addr + 2) == 0x2000, f"Expected 0x2000, got {hex(memory.read_u16(dst_addr + 2))}"
    assert memory.read_u16(dst_addr + 4) == 0x3000, f"Expected 0x3000, got {hex(memory.read_u16(dst_addr + 4))}"
    assert memory.read_u16(dst_addr + 6) == 0x4000, f"Expected 0x4000, got {hex(memory.read_u16(dst_addr + 6))}"
    
    print("✓ test_destination_increment passed")


def test_source_decrement():
    """Source decrement: source address starts at end, decrements through data."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM: 4 values
    src_addr = 0x02000000 + 6  # Start at end (last halfword)
    memory.write_u16(src_addr - 6, 0x1000)  # First value
    memory.write_u16(src_addr - 4, 0x2000)
    memory.write_u16(src_addr - 2, 0x3000)
    memory.write_u16(src_addr + 0, 0x4000)  # Last value (at src_addr)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 with source decrement (src_inc=1)
    setup_dma(memory, 0, src_addr, dst_addr, 4, timing=0, bit32=False, src_inc=1)
    
    # Trigger transfer
    dma.start_transfer(0)
    
    # Values should be read in reverse order
    assert memory.read_u16(dst_addr + 0) == 0x4000, f"Expected 0x4000, got {hex(memory.read_u16(dst_addr + 0))}"
    assert memory.read_u16(dst_addr + 2) == 0x3000, f"Expected 0x3000, got {hex(memory.read_u16(dst_addr + 2))}"
    assert memory.read_u16(dst_addr + 4) == 0x2000, f"Expected 0x2000, got {hex(memory.read_u16(dst_addr + 4))}"
    assert memory.read_u16(dst_addr + 6) == 0x1000, f"Expected 0x1000, got {hex(memory.read_u16(dst_addr + 6))}"
    
    print("✓ test_source_decrement passed")


# =============================================================================
# 4. Repeat Mode Test
# =============================================================================

def test_repeat_mode():
    """Repeat mode: data transfers on each hblank_fire(), not just once."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM - single value that will be reloaded
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0xAAAA)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 with repeat=1, HBlank timing, source reload (src_inc=3), dest reload (dst_inc=3)
    # This keeps both src and dst addresses fixed across repeats
    setup_dma(memory, 0, src_addr, dst_addr, 1, timing=2, bit32=False, repeat=True, src_inc=3, dst_inc=3)
    
    # First HBlank
    dma.hblank_fire(0)
    val1 = memory.read_u16(dst_addr + 0)
    assert val1 == 0xAAAA, f"First transfer: Expected 0xAAAA, got {hex(val1)}"
    
    # Second HBlank - should transfer again (repeat mode)
    dma.hblank_fire(0)
    val2 = memory.read_u16(dst_addr + 0)
    assert val2 == 0xAAAA, f"Second transfer: Expected 0xAAAA, got {hex(val2)}"
    
    # Third HBlank
    dma.hblank_fire(0)
    val3 = memory.read_u16(dst_addr + 0)
    assert val3 == 0xAAAA, f"Third transfer: Expected 0xAAAA, got {hex(val3)}"
    
    print("✓ test_repeat_mode passed")


# =============================================================================
# 5. Invariant Verification Tests
# =============================================================================

def test_hblank_uses_full_count_burst():
    """Invariant #4: HBlank uses _do_transfer - full count transferred in one call."""
    memory, dma = make_dma()
    
    # Set up source data: 4 halfwords
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0x1111)
    memory.write_u16(src_addr + 2, 0x2222)
    memory.write_u16(src_addr + 4, 0x3333)
    memory.write_u16(src_addr + 6, 0x4444)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 for HBlank with count=4
    setup_dma(memory, 0, src_addr, dst_addr, 4, timing=2, bit32=False)
    
    # Single hblank_fire() should transfer ALL 4 halfwords (full-count burst)
    dma.hblank_fire(0)
    
    # Verify all 4 values transferred in one call
    assert memory.read_u16(dst_addr + 0) == 0x1111, f"Expected 0x1111, got {hex(memory.read_u16(dst_addr + 0))}"
    assert memory.read_u16(dst_addr + 2) == 0x2222, f"Expected 0x2222, got {hex(memory.read_u16(dst_addr + 2))}"
    assert memory.read_u16(dst_addr + 4) == 0x3333, f"Expected 0x3333, got {hex(memory.read_u16(dst_addr + 4))}"
    assert memory.read_u16(dst_addr + 6) == 0x4444, f"Expected 0x4444, got {hex(memory.read_u16(dst_addr + 6))}"
    
    print("✓ test_hblank_uses_full_count_burst passed")


def test_vblank_uses_full_count_burst():
    """Invariant #4: VBlank uses _do_transfer - full count transferred in one call."""
    memory, dma = make_dma()
    
    # Set up source data: 4 halfwords
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0x5555)
    memory.write_u16(src_addr + 2, 0x6666)
    memory.write_u16(src_addr + 4, 0x7777)
    memory.write_u16(src_addr + 6, 0x8888)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 for VBlank with count=4
    setup_dma(memory, 0, src_addr, dst_addr, 4, timing=1, bit32=False)
    
    # Single vblank_fire() should transfer ALL 4 halfwords (full-count burst)
    dma.vblank_fire()
    
    # Verify all 4 values transferred in one call
    assert memory.read_u16(dst_addr + 0) == 0x5555, f"Expected 0x5555, got {hex(memory.read_u16(dst_addr + 0))}"
    assert memory.read_u16(dst_addr + 2) == 0x6666, f"Expected 0x6666, got {hex(memory.read_u16(dst_addr + 2))}"
    assert memory.read_u16(dst_addr + 4) == 0x7777, f"Expected 0x7777, got {hex(memory.read_u16(dst_addr + 4))}"
    assert memory.read_u16(dst_addr + 6) == 0x8888, f"Expected 0x8888, got {hex(memory.read_u16(dst_addr + 6))}"
    
    print("✓ test_vblank_uses_full_count_burst passed")


# =============================================================================
# 6. Edge Case Tests
# =============================================================================

def test_zero_count():
    """Zero count: count=0 means max (0x4000 for 16-bit)."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM - fill with pattern
    src_addr = 0x02000000
    for i in range(16):
        memory.write_u16(src_addr + i * 2, 0xABCD)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA0 with count=0 (should mean max = 0x4000 for 16-bit)
    setup_dma(memory, 0, src_addr, dst_addr, 0, timing=0, bit32=False)
    
    # Get channel to check what count value was used
    ch = dma.get_channel(0)
    ch.read_from_memory()
    actual_count = ch.get_count_value()
    
    # count=0 should resolve to max (0x4000 for 16-bit)
    assert actual_count == 0x4000, f"Expected max count 0x4000 for count=0, got {hex(actual_count)}"
    
    print("✓ test_zero_count passed")


def test_channel_3_special():
    """Channel 3 special: test that channel 3 is configurable."""
    memory, dma = make_dma()
    
    # Set up source data in EWRAM
    src_addr = 0x02000000
    memory.write_u16(src_addr + 0, 0xDEAD)
    
    # Destination in IWRAM
    dst_addr = 0x03000000
    
    # Configure DMA3 (channel 3) with special timing (timing=3)
    setup_dma(memory, 3, src_addr, dst_addr, 1, timing=3, bit32=False)
    
    # Verify channel 3 is accessible and configured
    ch = dma.get_channel(3)
    assert ch is not None, "Channel 3 should exist"
    ch.read_from_memory()
    assert ch.is_special(), "Channel 3 should be configured for special timing"
    assert ch.enabled, "Channel 3 should be enabled"
    assert ch.src_addr == src_addr, f"Expected src_addr {hex(src_addr)}, got {hex(ch.src_addr)}"
    assert ch.dst_addr == dst_addr, f"Expected dst_addr {hex(dst_addr)}, got {hex(ch.dst_addr)}"
    
    print("✓ test_channel_3_special passed")


# =============================================================================
# 7. Register Read-Back Test
# =============================================================================

def test_register_read_back():
    """Write DMA control registers to MMIO, verify channel properties reflect configuration."""
    memory, dma = make_dma()
    
    # Configure DMA0 via MMIO
    src_addr = 0x02000000
    dst_addr = 0x03000000
    count = 0x0100
    base = 0x040000B0
    
    memory.write_u32(base + 0, src_addr)       # source
    memory.write_u32(base + 4, dst_addr)       # destination
    memory.write_u16(base + 8, count)          # count
    # control: enable(15), IRQ(14), VBlank(12), 32-bit(10), repeat(9), dst_dec(5)
    ctrl = (1 << 15) | (1 << 14) | (1 << 12) | (1 << 10) | (1 << 9) | (1 << 5)
    memory.write_u16(base + 10, ctrl)          # control
    
    # Read back via channel
    ch = dma.get_channel(0)
    ch.read_from_memory()
    
    # Verify all properties
    assert ch.irq_enabled, "IRQ should be enabled"
    assert ch.is_vblank(), "Timing should be VBlank"
    assert ch.is_32bit(), "Should be 32-bit"
    assert ch.is_repeat(), "Should be repeat mode"
    assert ch.get_dst_increment() == 1, f"Expected dst_dec (1), got {ch.get_dst_increment()}"
    assert ch.src_addr == src_addr, f"Expected src_addr {hex(src_addr)}, got {hex(ch.src_addr)}"
    assert ch.dst_addr == dst_addr, f"Expected dst_addr {hex(dst_addr)}, got {hex(ch.dst_addr)}"
    assert ch.count == count, f"Expected count {hex(count)}, got {hex(ch.count)}"
    
    print("✓ test_register_read_back passed")


# =============================================================================
# Main: Run All Tests
# =============================================================================

if __name__ == "__main__":
    # 1. Immediate Transfer Tests
    test_16bit_immediate_transfer()
    test_32bit_immediate_transfer()
    test_fixed_source_transfer()
    
    # 2. HBlank/VBlank Timing Tests
    test_hblank_trigger()
    test_vblank_trigger()
    test_no_transfer_when_disabled()
    
    # 3. Increment/Decrement Tests
    test_destination_increment()
    test_source_decrement()
    
    # 4. Repeat Mode Test
    test_repeat_mode()
    
    # 5. Invariant Verification Tests
    test_hblank_uses_full_count_burst()
    test_vblank_uses_full_count_burst()
    
    # 6. Edge Case Tests
    test_zero_count()
    test_channel_3_special()
    
    # 7. Register Read-Back Test
    test_register_read_back()
    
    print("\nAll 13 DMA tests passed!")