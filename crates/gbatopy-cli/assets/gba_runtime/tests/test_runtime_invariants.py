"""Regression tests for runtime invariant pitfalls.

These tests verify that documented pitfalls do not regress.
See docs/codegen-pitfalls.md for pitfall descriptions.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from memory import Memory
from ppu import PPU


# ============================================================================
# Pitfall #11: DMA Double-Stepping
# ============================================================================
# The fallback interpreter (_interp_fallback in pipeline_cmd.rs) must be a
# PURE CPU executor — it must NEVER call step_scanline(). If it did, DMA
# transfers would be double-stepped (once by the CPU execution, once by the
# PPU step).
#
# Since _interp_fallback lives in Rust code, we test the RUNTIME side:
# verify that memory read operations (read_u8, read_u16, read_u32) do NOT
# call step_scanline().
# ============================================================================


def test_read_u16_does_not_step_scanline():
    """Regression test for pitfall #11: DMA Double-Stepping.
    
    Performing read_u16 must NOT call step_scanline().
    """
    memory = Memory()
    ppu = PPU(memory)
    memory.attach_ppu(ppu)
    
    # Track step_scanline calls by patching the method
    step_scanline_call_count = [0]
    original_step_scanline = ppu.step_scanline
    
    def counting_step_scanline(*args, **kwargs):
        step_scanline_call_count[0] += 1
        return original_step_scanline(*args, **kwargs)
    
    ppu.step_scanline = counting_step_scanline
    
    # Perform a read_u16 operation
    initial_count = step_scanline_call_count[0]
    memory.write_u8(0x02000000, 0x12)
    memory.write_u8(0x02000001, 0x34)
    result = memory.read_u16(0x02000000)
    final_count = step_scanline_call_count[0]
    
    # Verify no step_scanline was called during the read
    assert final_count == initial_count, \
        f"read_u16 called step_scanline {final_count - initial_count} times (expected 0)"
    assert result == 0x3412, f"Expected 0x3412, got 0x{result:04X}"
    
    print("✓ test_read_u16_does_not_step_scanline passed")


def test_read_u32_does_not_step_scanline():
    """Regression test for pitfall #11: DMA Double-Stepping.
    
    Performing read_u32 must NOT call step_scanline().
    """
    memory = Memory()
    ppu = PPU(memory)
    memory.attach_ppu(ppu)
    
    # Track step_scanline calls by patching the method
    step_scanline_call_count = [0]
    original_step_scanline = ppu.step_scanline
    
    def counting_step_scanline(*args, **kwargs):
        step_scanline_call_count[0] += 1
        return original_step_scanline(*args, **kwargs)
    
    ppu.step_scanline = counting_step_scanline
    
    # Perform a read_u32 operation
    initial_count = step_scanline_call_count[0]
    memory.write_u8(0x02000000, 0x12)
    memory.write_u8(0x02000001, 0x34)
    memory.write_u8(0x02000002, 0x56)
    memory.write_u8(0x02000003, 0x78)
    result = memory.read_u32(0x02000000)
    final_count = step_scanline_call_count[0]
    
    # Verify no step_scanline was called during the read
    assert final_count == initial_count, \
        f"read_u32 called step_scanline {final_count - initial_count} times (expected 0)"
    assert result == 0x78563412, f"Expected 0x78563412, got 0x{result:08X}"
    
    print("✓ test_read_u32_does_not_step_scanline passed")


def test_read_u8_does_not_step_scanline():
    """Regression test for pitfall #11: DMA Double-Stepping.
    
    Performing read_u8 must NOT call step_scanline().
    """
    memory = Memory()
    ppu = PPU(memory)
    memory.attach_ppu(ppu)
    
    # Track step_scanline calls by patching the method
    step_scanline_call_count = [0]
    original_step_scanline = ppu.step_scanline
    
    def counting_step_scanline(*args, **kwargs):
        step_scanline_call_count[0] += 1
        return original_step_scanline(*args, **kwargs)
    
    ppu.step_scanline = counting_step_scanline
    
    # Perform a read_u8 operation
    initial_count = step_scanline_call_count[0]
    memory.write_u8(0x02000000, 0xAB)
    result = memory.read_u8(0x02000000)
    final_count = step_scanline_call_count[0]
    
    # Verify no step_scanline was called during the read
    assert final_count == initial_count, \
        f"read_u8 called step_scanline {final_count - initial_count} times (expected 0)"
    assert result == 0xAB, f"Expected 0xAB, got 0x{result:02X}"
    
    print("✓ test_read_u8_does_not_step_scanline passed")


def test_step_scanline_not_in_memory_read_path():
    """Regression test for pitfall #11: DMA Double-Stepping.
    
    Instrument the memory object to track scanline calls, perform several
    reads across different regions (VRAM, PALRAM, OAM, IWRAM, EWRAM),
    verify zero scanline steps.
    """
    memory = Memory()
    ppu = PPU(memory)
    memory.attach_ppu(ppu)
    
    # Track step_scanline calls
    step_scanline_call_count = [0]
    original_step_scanline = ppu.step_scanline
    
    def counting_step_scanline(*args, **kwargs):
        step_scanline_call_count[0] += 1
        return original_step_scanline(*args, **kwargs)
    
    ppu.step_scanline = counting_step_scanline
    
    # Perform reads across different memory regions
    initial_count = step_scanline_call_count[0]
    
    # EWRAM read
    memory.write_u8(0x02000000, 0x01)
    _ = memory.read_u8(0x02000000)
    _ = memory.read_u16(0x02000000)
    _ = memory.read_u32(0x02000000)
    
    # IWRAM read
    memory.write_u8(0x03000000, 0x02)
    _ = memory.read_u8(0x03000000)
    _ = memory.read_u16(0x03000000)
    _ = memory.read_u32(0x03000000)
    
    # VRAM read
    memory.write_u8(0x06000000, 0x03)
    _ = memory.read_u8(0x06000000)
    _ = memory.read_u16(0x06000000)
    _ = memory.read_u32(0x06000000)
    
    # Palette RAM read
    memory.write_u8(0x05000000, 0x04)
    _ = memory.read_u8(0x05000000)
    _ = memory.read_u16(0x05000000)
    
    # OAM read
    memory.write_u8(0x07000000, 0x05)
    _ = memory.read_u8(0x07000000)
    _ = memory.read_u16(0x07000000)
    
    final_count = step_scanline_call_count[0]
    
    # Verify no step_scanline was called during any memory reads
    assert final_count == initial_count, \
        f"Memory reads called step_scanline {final_count - initial_count} times (expected 0)"
    
    print("✓ test_step_scanline_not_in_memory_read_path passed")


# ============================================================================
# Pitfall #12: Fast-Forward DISPSTAT Read
# ============================================================================
# Reading DISPSTAT (0x04000004) must NOT advance the PPU scanline.
# Previously, a "fast-forward" path was triggered on DISPSTAT reads that
# called step_scanline(), causing timing bugs.
# ============================================================================


def test_read_dispstat_does_not_advance_scanline():
    """Regression test for pitfall #12: Fast-Forward DISPSTAT Read.
    
    Reading DISPSTAT must NOT advance the VCOUNT scanline counter.
    """
    memory = Memory()
    ppu = PPU(memory)
    memory.attach_ppu(ppu)
    
    # Set initial VCOUNT to a known value
    initial_vcount = ppu.vcount
    
    # Read DISPSTAT multiple times
    for _ in range(10):
        _ = memory.read_u16(0x04000004)  # DISPSTAT address
    
    # Verify VCOUNT unchanged
    assert ppu.vcount == initial_vcount, \
        f"VCOUNT changed from {initial_vcount} to {ppu.vcount} after DISPSTAT reads"
    
    print("✓ test_read_dispstat_does_not_advance_scanline passed")


def test_read_dispstat_multiple_times_no_advance():
    """Regression test for pitfall #12: Fast-Forward DISPSTAT Read.
    
    Read DISPSTAT 100 times, verify VCOUNT unchanged.
    """
    memory = Memory()
    ppu = PPU(memory)
    memory.attach_ppu(ppu)
    
    # Set initial VCOUNT to a known value
    initial_vcount = ppu.vcount
    
    # Read DISPSTAT 100 times (simulating a tight poll loop)
    for _ in range(100):
        _ = memory.read_u16(0x04000004)  # DISPSTAT address
    
    # Verify VCOUNT unchanged
    assert ppu.vcount == initial_vcount, \
        f"VCOUNT changed from {initial_vcount} to {ppu.vcount} after 100 DISPSTAT reads"
    
    print("✓ test_read_dispstat_multiple_times_no_advance passed")


def test_read_other_mmio_no_scanline_advance():
    """Regression test for pitfall #12: Fast-Forward DISPSTAT Read.
    
    Read other MMIO registers, verify no scanline advance.
    """
    memory = Memory()
    ppu = PPU(memory)
    memory.attach_ppu(ppu)
    
    # Set initial VCOUNT to a known value
    initial_vcount = ppu.vcount
    
    # Read various MMIO registers
    _ = memory.read_u16(0x04000000)  # DISPCNT
    _ = memory.read_u16(0x04000006)  # VCOUNT
    _ = memory.read_u16(0x04000008)  # BG0CNT
    _ = memory.read_u16(0x04000050)  # BLDCNT
    
    # Verify VCOUNT unchanged
    assert ppu.vcount == initial_vcount, \
        f"VCOUNT changed from {initial_vcount} to {ppu.vcount} after MMIO reads"
    
    print("✓ test_read_other_mmio_no_scanline_advance passed")


if __name__ == "__main__":
    # Pitfall #11 tests
    test_read_u16_does_not_step_scanline()
    test_read_u32_does_not_step_scanline()
    test_read_u8_does_not_step_scanline()
    test_step_scanline_not_in_memory_read_path()
    
    # Pitfall #12 tests
    test_read_dispstat_does_not_advance_scanline()
    test_read_dispstat_multiple_times_no_advance()
    test_read_other_mmio_no_scanline_advance()
    
    print("\nAll 7 runtime invariant regression tests passed!")