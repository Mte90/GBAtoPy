"""Test PPU VCOUNT increment and DISPSTAT latching per scanline."""

import sys
sys.path.insert(0, '/home/d.scasciafratte/gbatopy/crates/gbatopy-cli/assets/gba_runtime')

from memory import Memory
from ppu import PPU


class MockInterrupts:
    """Mock interrupt controller for testing."""
    def vblank_irq(self):
        pass
    
    def hblank_irq(self):
        pass
    
    def vcounter_irq(self):
        pass


class MockDMA:
    """Mock DMA controller for testing."""
    def hblank_fire(self, vcount):
        pass
    
    def vblank_fire(self):
        pass


def test_vcount_increments_0_to_227():
    """Test that VCOUNT increments from 0 to 227 and wraps."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    ppu = PPU(memory)
    
    # Initial state
    assert ppu.vcount == 0, f"Initial vcount should be 0, got {ppu.vcount}"
    
    # Step through all 228 scanlines
    for expected_vcount in range(228):
        # Read VCOUNT from MMIO before stepping
        io_vcount = memory.io[6] | (memory.io[7] << 8)
        assert io_vcount == expected_vcount, \
            f"Before step {expected_vcount}: VCOUNT should be {expected_vcount}, got {io_vcount}"
        
        # Step one scanline
        ppu.step_scanline()
        
        # After step, vcount should be incremented (with wrap at 228)
        expected_after = (expected_vcount + 1) % 228
        assert ppu.vcount == expected_after, \
            f"After step {expected_vcount}: vcount should be {expected_after}, got {ppu.vcount}"
    
    # After 228 steps, should wrap back to 0
    assert ppu.vcount == 0, f"After 228 steps, vcount should wrap to 0, got {ppu.vcount}"
    
    print("✓ test_vcount_increments_0_to_227 passed")


def test_vcount_snapshot_captured():
    """Test that VCOUNT snapshot is captured for each scanline."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    ppu = PPU(memory)
    
    # Step through visible scanlines (0-159)
    for vcount in range(160):
        ppu.step_scanline()
        # Snapshot should be captured for this scanline
        snapshot_vcount = ppu._vcount_snapshot[vcount]
        assert snapshot_vcount == vcount, \
            f"Snapshot for scanline {vcount}: expected {vcount}, got {snapshot_vcount}"
    
    print("✓ test_vcount_snapshot_captured passed")


def test_dispstat_vblank_bit():
    """Test that DISPSTAT bit 0 (VBlank) is set correctly."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    ppu = PPU(memory)
    
    # Visible scanlines (0-158): After stepping, vcount becomes 1-159, still not VBlank
    for vcount in range(159):
        ppu.step_scanline()
        dispstat = memory.io[4] | (memory.io[5] << 8)
        vblank_bit = dispstat & 0x0001
        assert vblank_bit == 0, \
            f"After step from {vcount}: VBlank bit should be 0, got {vblank_bit}"
    
    # After stepping from scanline 159, vcount becomes 160, entering VBlank
    ppu.step_scanline()
    dispstat = memory.io[4] | (memory.io[5] << 8)
    vblank_bit = dispstat & 0x0001
    assert vblank_bit == 1, \
        f"After step from 159: VBlank bit should be 1 (entered VBlank), got {vblank_bit}"
    
    # Remaining VBlank scanlines (160-226): VBlank bit should stay 1
    # Note: stepping from 227 wraps to 0, exiting VBlank
    for vcount in range(160, 227):
        ppu.step_scanline()
        dispstat = memory.io[4] | (memory.io[5] << 8)
        vblank_bit = dispstat & 0x0001
        assert vblank_bit == 1, \
            f"VBlank scanline {vcount}: VBlank bit should be 1, got {vblank_bit}"
    
    # Stepping from 227 wraps to 0, exiting VBlank
    ppu.step_scanline()
    dispstat = memory.io[4] | (memory.io[5] << 8)
    vblank_bit = dispstat & 0x0001
    assert vblank_bit == 0, \
        f"After step from 227: VBlank bit should be 0 (exited VBlank), got {vblank_bit}"
    
    print("✓ test_dispstat_vblank_bit passed")


def test_dispstat_hblank_bit():
    """Test that DISPSTAT bit 1 (HBlank) is always set."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    ppu = PPU(memory)
    
    # HBlank bit should be 1 on all scanlines
    for vcount in range(228):
        ppu.step_scanline()
        dispstat = memory.io[4] | (memory.io[5] << 8)
        hblank_bit = (dispstat >> 1) & 0x0001
        assert hblank_bit == 1, \
            f"Scanline {vcount}: HBlank bit should be 1, got {hblank_bit}"
    
    print("✓ test_dispstat_hblank_bit passed")


def test_dispstat_vcount_match():
    """Test that DISPSTAT bit 2 (VCOUNT match) is set when vcount == LYC."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    ppu = PPU(memory)
    
    # Set LYC to 50
    lyc_value = 50
    dispstat_initial = 0x0100 | (lyc_value << 8)  # Set LYC to 50
    memory.io[4] = dispstat_initial & 0xFF
    memory.io[5] = (dispstat_initial >> 8) & 0xFF
    
    # Step through scanlines
    for vcount in range(228):
        ppu.step_scanline()
        dispstat = memory.io[4] | (memory.io[5] << 8)
        vcount_match_bit = (dispstat >> 2) & 0x0001
        
        if vcount == lyc_value:
            assert vcount_match_bit == 1, \
                f"Scanline {vcount} (LYC={lyc_value}): VCOUNT match bit should be 1, got {vcount_match_bit}"
        else:
            assert vcount_match_bit == 0, \
                f"Scanline {vcount} (LYC={lyc_value}): VCOUNT match bit should be 0, got {vcount_match_bit}"
    
    print("✓ test_dispstat_vcount_match passed")


def test_dispstat_snapshot_latched():
    """Test that DISPSTAT is latched correctly for each scanline."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    ppu = PPU(memory)
    
    # Set LYC to 100
    lyc_value = 100
    dispstat_initial = (lyc_value << 8)
    memory.io[4] = dispstat_initial & 0xFF
    memory.io[5] = (dispstat_initial >> 8) & 0xFF
    
    # Step through scanlines and verify snapshots
    for vcount in range(160):
        ppu.step_scanline()
        
        # Read the latched snapshot for this scanline
        latched_dispstat = ppu._dispstat_snapshot[vcount]
        latched_vcount = ppu._vcount_snapshot[vcount]
        
        # VCOUNT snapshot should match the scanline number
        assert latched_vcount == vcount, \
            f"Snapshot vcount for scanline {vcount}: expected {vcount}, got {latched_vcount}"
        
        # DISPSTAT snapshot should have correct LYC match bit
        expected_match_bit = 1 if vcount == lyc_value else 0
        actual_match_bit = (latched_dispstat >> 2) & 0x0001
        assert actual_match_bit == expected_match_bit, \
            f"Snapshot DISPSTAT for scanline {vcount}: match bit should be {expected_match_bit}, got {actual_match_bit}"
    
    print("✓ test_dispstat_snapshot_latched passed")


if __name__ == "__main__":
    test_vcount_increments_0_to_227()
    test_vcount_snapshot_captured()
    test_dispstat_vblank_bit()
    test_dispstat_hblank_bit()
    test_dispstat_vcount_match()
    test_dispstat_snapshot_latched()
    print("\n✅ All tests passed!")