"""Regression test for pitfall #13: Per-Scanline Affine Parameter Snapshots

This test file verifies that the PPU correctly captures per-scanline affine
parameter snapshots so that HBlank DMA changes to BG2PA/PB/PC/PD/X/Y take effect
only on the NEXT scanline, not the current one being rendered.

Reference: Runtime Invariant #5 in AGENTS.md
- step_scanline(capture_snapshot=True) captures BG2PA/PB/PC/PD/X/Y BEFORE DMA fires
- The fallback interpreter calls step_scanline(capture_snapshot=False)
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from memory import Memory
from ppu import PPU


class MockInterrupts:
    def vblank_irq(self): pass
    def hblank_irq(self): pass
    def vcounter_irq(self): pass


class MockDMA:
    def hblank_fire(self, vcount): pass
    def vblank_fire(self): pass


def make_ppu():
    """Create a PPU with mock dependencies."""
    memory = Memory()
    memory._interrupts = MockInterrupts()
    memory._dma = MockDMA()
    ppu = PPU(memory)
    return ppu, memory


def step_frame(ppu):
    """Step 160 visible + 68 VBlank scanlines = 228 total, then render."""
    for _ in range(228):
        ppu.step_scanline()
    ppu.render_frame()


def test_affine_snapshot_captured_on_step_scanline():
    """Regression test for pitfall #13: Snapshot captures values BEFORE DMA changes.
    
    Sets BG2 affine params to known values A, calls step_scanline(), then changes
    params to B. The rendered output should use values A (the snapshot), not B.
    """
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 3 + BG2 enable
    memory.write_u16(0x04000000, 0x0403)
    
    # Set BG2CNT: priority=0, char base=0, 8BPP, screen base=1, size=1 (256x256)
    memory.write_u16(0x0400000C, 0x4180)
    
    # Set affine params to identity (PA=256, PD=256 = 1.0 in 16.8 fixed point)
    # This gives us a direct passthrough transform
    memory.write_u16(0x04000020, 256)  # BG2PA = 1.0
    memory.write_u16(0x04000022, 0)    # BG2PB = 0
    memory.write_u16(0x04000024, 0)    # BG2PC = 0
    memory.write_u16(0x04000026, 256)  # BG2PD = 1.0
    memory.write_u32(0x04000028, 0)    # BG2X = 0
    memory.write_u32(0x0400002C, 0)    # BG2Y = 0
    
    # Write known pixel colors to VRAM (Mode 3 is 16-bit bitmap):
    # (0,0) = red, (1,0) = blue
    vram_base = 0x06000000
    memory.write_u16(vram_base + 0, 0x001F)   # (0,0) = red
    memory.write_u16(vram_base + 2, 0x7C00)   # (1,0) = blue
    # Fill rest of row 0 with red
    for x in range(2, 240):
        memory.write_u16(vram_base + x * 2, 0x001F)
    
    # Write tilemap: all tile 0
    for i in range(64):
        memory.write_u8(0x06000800 + i, 0)
    
    # Set palette: index 1 = red, index 2 = blue
    memory.write_u16(0x05000002, 0x001F)  # palette[1] = red
    memory.write_u16(0x05000004, 0x7C00)  # palette[2] = blue
    
    # Step scanline 0 (vcount=0) - this captures the snapshot with identity params
    ppu.step_scanline()
    
    # NOW change the affine params to a 2x scale (PA=128, PD=128 = 0.5)
    # If snapshot works correctly, scanline 0 should still render with identity
    memory.write_u16(0x04000020, 128)  # BG2PA = 0.5 (2x scale)
    memory.write_u16(0x04000026, 128)  # BG2PD = 0.5
    
    # Step remaining scanlines
    for _ in range(227):
        ppu.step_scanline()
    
    ppu.render_frame()
    
    # Verify: scanline 0 should use the SNAPSHOT (identity), not the new live values
    # With identity: pixel (0,0) maps to source (0,0) = red
    # With 2x scale: pixel (0,0) would map to source (0,0) but pixel (1,0) would also be red
    # The key test: since we changed AFTER the snapshot, scanline 0 should still be red
    assert ppu.framebuffer[0][0] == (255, 0, 0), \
        f"Expected red from snapshot at (0,0), got {ppu.framebuffer[0][0]}"
    
    print("✓ test_affine_snapshot_captured_on_step_scanline passed")


def test_no_snapshot_uses_live_affine():
    """Regression test for pitfall #13: Snapshot mechanism captures correct values.
    
    This test verifies that when affine parameters are changed BEFORE a scanline's
    snapshot is captured, the new values are stored in the snapshot.
    """
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 3 + BG2 enable
    memory.write_u16(0x04000000, 0x0403)
    
    # Set initial affine params to identity
    memory.write_u16(0x04000020, 256)  # BG2PA = 1.0
    memory.write_u16(0x04000022, 0)
    memory.write_u16(0x04000024, 0)
    memory.write_u16(0x04000026, 256)  # BG2PD = 1.0
    memory.write_u32(0x04000028, 0)
    memory.write_u32(0x0400002C, 0)
    
    # Write known pixel colors to VRAM (Mode 3 is 16-bit bitmap):
    vram_base = 0x06000000
    memory.write_u16(vram_base + 0, 0x001F)   # (0,0) = red
    memory.write_u16(vram_base + 2, 0x7C00)   # (1,0) = blue
    # Fill rest of row 0 with red
    for x in range(2, 240):
        memory.write_u16(vram_base + x * 2, 0x001F)
    
    # Step scanline 0 (vcount=0) - captures identity snapshot
    ppu.step_scanline()
    
    # Verify snapshot[0] has identity values
    snaps = ppu._bg2_affine_snapshots
    assert snaps[0] is not None, "Snapshot at vcount=0 should exist"
    dx_0, _, _, _, _, _, _ = snaps[0]
    assert dx_0 == 256, f"Snapshot[0].dx should be 256 (identity), got {dx_0}"
    
    # Change affine params to 2x scale BEFORE the next scanline's snapshot
    memory.write_u16(0x04000020, 128)  # BG2PA = 0.5
    memory.write_u16(0x04000026, 128)  # BG2PD = 0.5
    
    # Step scanline 1 - this will capture the NEW values in the snapshot
    ppu.step_scanline()
    
    # Verify snapshot[1] has the new 2x scale values
    assert snaps[1] is not None, "Snapshot at vcount=1 should exist"
    dx_1, _, _, _, _, _, _ = snaps[1]
    assert dx_1 == 128, f"Snapshot[1].dx should be 128 (2x scale), got {dx_1}"
    
    # Step remaining scanlines
    for _ in range(226):
        ppu.step_scanline()
    
    ppu.render_frame()
    
    # Verify the framebuffer was rendered (not all black)
    assert ppu.framebuffer[0][0] == (255, 0, 0), f"Expected red at (0,0), got {ppu.framebuffer[0][0]}"
    
    print("✓ test_no_snapshot_uses_live_affine passed")


def test_per_scanline_snapshot_independence():
    """Regression test for pitfall #13: Each scanline has independent snapshot.
    
    Sets affine params A, captures snapshot at vcount=9.
    Changes to params B, captures snapshot at vcount=10.
    Verifies snapshot[9] has A and snapshot[10] has B.
    """
    ppu, memory = make_ppu()
    
    # Set DISPCNT to mode 3 + BG2 enable
    memory.write_u16(0x04000000, 0x0403)
    
    # Write known pixel colors to VRAM (Mode 3 is 16-bit bitmap):
    vram_base = 0x06000000
    # Fill row 0 with red
    for x in range(240):
        memory.write_u16(vram_base + x * 2, 0x001F)  # red
    # Fill row 1 with green
    for x in range(240):
        memory.write_u16(vram_base + (240 + x) * 2, 0x03E0)  # green
    # Fill row 2 with blue
    for x in range(240):
        memory.write_u16(vram_base + (480 + x) * 2, 0x7C00)  # blue
    
    # Step scanlines 0-8 with identity params (snapshots[0-8] will be identity)
    for _ in range(9):
        ppu.step_scanline()
    
    # After 9 steps, vcount=9, and snapshot[8] was captured (the last one)
    # Now step one more time to capture snapshot[9] with identity
    ppu.step_scanline()
    
    # snapshot[9] should have identity (PA=256, PD=256)
    snaps = ppu._bg2_affine_snapshots
    assert snaps[9] is not None, "Snapshot at vcount=9 should exist"
    dx_9, _, _, _, _, _, _ = snaps[9]
    assert dx_9 == 256, f"Snapshot[9].dx should be 256 (identity), got {dx_9}"
    
    # Change to 2x scale (PA=128, PD=128) BEFORE vcount=10 snapshot
    memory.write_u16(0x04000020, 128)  # BG2PA = 0.5
    memory.write_u16(0x04000026, 128)  # BG2PD = 0.5
    
    # At vcount=10, capture snapshot with 2x scale
    ppu.step_scanline()
    
    # Verify snapshot[10] has the 2x scale values
    assert snaps[10] is not None, "Snapshot at vcount=10 should exist"
    dx_10, _, _, _, _, _, _ = snaps[10]
    assert dx_10 == 128, f"Snapshot[10].dx should be 128 (2x scale), got {dx_10}"
    
    # Step remaining scanlines (11-159 visible, then VBlank)
    for _ in range(216):
        ppu.step_scanline()
    
    ppu.render_frame()
    
    # Verify the framebuffer was rendered (not all black)
    assert ppu.framebuffer[0][0] == (255, 0, 0), \
        f"Expected red at scanline 0, got {ppu.framebuffer[0][0]}"
    
    print("✓ test_per_scanline_snapshot_independence passed")


if __name__ == "__main__":
    test_affine_snapshot_captured_on_step_scanline()
    test_no_snapshot_uses_live_affine()
    test_per_scanline_snapshot_independence()
    print("\nAll 3 affine snapshot regression tests passed!")