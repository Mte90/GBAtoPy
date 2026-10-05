"""Memory subsystem unit tests for GBAtoPy.

Tests cover all memory regions, read/write widths, address mirroring,
MMIO dispatch, and boundary conditions.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from memory import Memory


def test_bios_region_round_trip():
    """BIOS region: write_u8 then read_u8 round-trip."""
    memory = Memory()
    
    # Write to BIOS at base address
    memory.write_u8(0x00000000, 0xAB)
    
    # Read back - BIOS is read-only, write should be ignored
    # But we verify the memory subsystem handles the address correctly
    result = memory.read_u8(0x00000000)
    
    # BIOS[0] is initialized to 0xEA (BARMEM setup)
    # Writes to BIOS are ignored, so we get the initial value
    assert result == 0xEA, f"Expected 0xEA (BIOS read-only), got 0x{result:02X}"
    
    print("✓ test_bios_region_round_trip passed")


def test_ewram_region_round_trip():
    """EWRAM region: write_u8 then read_u8 round-trip."""
    memory = Memory()
    
    # Write to EWRAM at base address
    memory.write_u8(0x02000000, 0xCD)
    
    # Read back
    result = memory.read_u8(0x02000000)
    
    assert result == 0xCD, f"Expected 0xCD, got 0x{result:02X}"
    
    print("✓ test_ewram_region_round_trip passed")


def test_iwram_region_round_trip():
    """IWRAM region: write_u8 then read_u8 round-trip."""
    memory = Memory()
    
    # Write to IWRAM at base address
    memory.write_u8(0x03000000, 0xEF)
    
    # Read back
    result = memory.read_u8(0x03000000)
    
    assert result == 0xEF, f"Expected 0xEF, got 0x{result:02X}"
    
    print("✓ test_iwram_region_round_trip passed")


def test_io_region_round_trip():
    """IO region: write_u8 then read_u8 round-trip."""
    memory = Memory()
    
    # Write to IO at DISPCNT address
    memory.write_u8(0x04000000, 0x12)
    
    # Read back
    result = memory.read_u8(0x04000000)
    
    assert result == 0x12, f"Expected 0x12, got 0x{result:02X}"
    
    print("✓ test_io_region_round_trip passed")


def test_palette_region_round_trip():
    """Palette region: write_u8 then read_u8 round-trip."""
    memory = Memory()
    
    # Write to palette at base address
    memory.write_u8(0x05000000, 0x34)
    
    # Read back
    result = memory.read_u8(0x05000000)
    
    assert result == 0x34, f"Expected 0x34, got 0x{result:02X}"
    
    print("✓ test_palette_region_round_trip passed")


def test_vram_region_round_trip():
    """VRAM region: write_u8 then read_u8 round-trip."""
    memory = Memory()
    
    # Write to VRAM at base address
    memory.write_u8(0x06000000, 0x56)
    
    # Read back
    result = memory.read_u8(0x06000000)
    
    assert result == 0x56, f"Expected 0x56, got 0x{result:02X}"
    
    print("✓ test_vram_region_round_trip passed")


def test_oam_region_round_trip():
    """OAM region: write_u8 then read_u8 round-trip."""
    memory = Memory()
    
    # Write to OAM at base address
    memory.write_u8(0x07000000, 0x78)
    
    # Read back
    result = memory.read_u8(0x07000000)
    
    assert result == 0x78, f"Expected 0x78, got 0x{result:02X}"
    
    print("✓ test_oam_region_round_trip passed")


def test_sram_region_round_trip():
    """SRAM region: write_u8 then read_u8 round-trip."""
    memory = Memory()
    
    # Write to SRAM at base address
    memory.write_u8(0x0E000000, 0x9A)
    
    # Read back
    result = memory.read_u8(0x0E000000)
    
    assert result == 0x9A, f"Expected 0x9A, got 0x{result:02X}"
    
    print("✓ test_sram_region_round_trip passed")


def test_u16_round_trip():
    """16-bit write/read round-trip on EWRAM."""
    memory = Memory()
    
    # Write 16-bit value
    memory.write_u16(0x02000000, 0x1234)
    
    # Read back
    result = memory.read_u16(0x02000000)
    
    assert result == 0x1234, f"Expected 0x1234, got 0x{result:04X}"
    
    print("✓ test_u16_round_trip passed")


def test_u32_round_trip():
    """32-bit write/read round-trip on EWRAM."""
    memory = Memory()
    
    # Write 32-bit value
    memory.write_u32(0x02000000, 0x12345678)
    
    # Read back
    result = memory.read_u32(0x02000000)
    
    assert result == 0x12345678, f"Expected 0x12345678, got 0x{result:08X}"
    
    print("✓ test_u32_round_trip passed")


def test_u32_as_two_u16_little_endian():
    """32-bit write, read as two 16-bit values (little-endian)."""
    memory = Memory()
    
    # Write 32-bit value (little-endian: low word first)
    memory.write_u32(0x02000000, 0x12345678)
    
    # Read as two 16-bit values
    low = memory.read_u16(0x02000000)   # Should be 0x5678
    high = memory.read_u16(0x02000002)  # Should be 0x1234
    
    assert low == 0x5678, f"Expected low word 0x5678, got 0x{low:04X}"
    assert high == 0x1234, f"Expected high word 0x1234, got 0x{high:04X}"
    
    print("✓ test_u32_as_two_u16_little_endian passed")


def test_iwram_mirroring():
    """IWRAM mirror: write at 0x03000000, read at 0x03008000."""
    memory = Memory()
    
    # Write to IWRAM base
    memory.write_u8(0x03000000, 0xAA)
    
    # Read from mirror address (0x03008000)
    result = memory.read_u8(0x03008000)
    
    assert result == 0xAA, f"Expected 0xAA from mirror, got 0x{result:02X}"
    
    print("✓ test_iwram_mirroring passed")


def test_ewram_mirroring():
    """EWRAM mirror: write at 0x02000000, read at 0x02040000."""
    memory = Memory()
    
    # Write to EWRAM base
    memory.write_u8(0x02000000, 0xBB)
    
    # Read from mirror address (0x02040000)
    result = memory.read_u8(0x02040000)
    
    assert result == 0xBB, f"Expected 0xBB from mirror, got 0x{result:02X}"
    
    print("✓ test_ewram_mirroring passed")


def test_vram_mirroring():
    """VRAM mirror: write at 0x06000000, read at 0x06018000."""
    memory = Memory()
    
    # Write to VRAM base
    memory.write_u8(0x06000000, 0xCC)
    
    # Read from mirror address (0x06018000)
    result = memory.read_u8(0x06018000)
    
    assert result == 0xCC, f"Expected 0xCC from mirror, got 0x{result:02X}"
    
    print("✓ test_vram_mirroring passed")


def test_mmio_dispatch_dispcnt():
    """MMIO dispatch: write to DISPCNT, verify io[] buffer updated."""
    memory = Memory()
    
    # Write to DISPCNT (0x04000000) with value 0x0403 (Mode 3 + BG2 enable)
    memory.write_u16(0x04000000, 0x0403)
    
    # Verify io[] buffer has correct little-endian bytes
    assert memory.io[0] == 0x03, f"Expected io[0]=0x03, got 0x{memory.io[0]:02X}"
    assert memory.io[1] == 0x04, f"Expected io[1]=0x04, got 0x{memory.io[1]:02X}"
    
    print("✓ test_mmio_dispatch_dispcnt passed")


def test_read_bytes():
    """read_bytes: write 4 bytes, read back as bytes."""
    memory = Memory()
    
    # Write 4 bytes to EWRAM
    memory.write_u8(0x02000000, 0x11)
    memory.write_u8(0x02000001, 0x22)
    memory.write_u8(0x02000002, 0x33)
    memory.write_u8(0x02000003, 0x44)
    
    # Read back as bytes
    result = memory.read_bytes(0x02000000, 4)
    
    assert result == b'\x11\x22\x33\x44', f"Expected b'\\x11\\x22\\x33\\x44', got {result!r}"
    assert len(result) == 4, f"Expected length 4, got {len(result)}"
    
    print("✓ test_read_bytes passed")


def test_ewram_boundary():
    """Boundary test: write at last valid EWRAM address (0x0203FFFF)."""
    memory = Memory()
    
    # Write to last byte of EWRAM
    memory.write_u8(0x0203FFFF, 0xDE)
    
    # Read back
    result = memory.read_u8(0x0203FFFF)
    
    assert result == 0xDE, f"Expected 0xDE, got 0x{result:02X}"
    
    print("✓ test_ewram_boundary passed")


if __name__ == "__main__":
    test_bios_region_round_trip()
    test_ewram_region_round_trip()
    test_iwram_region_round_trip()
    test_io_region_round_trip()
    test_palette_region_round_trip()
    test_vram_region_round_trip()
    test_oam_region_round_trip()
    test_sram_region_round_trip()
    test_u16_round_trip()
    test_u32_round_trip()
    test_u32_as_two_u16_little_endian()
    test_iwram_mirroring()
    test_ewram_mirroring()
    test_vram_mirroring()
    test_mmio_dispatch_dispcnt()
    test_read_bytes()
    test_ewram_boundary()
    
    print("\nAll 17 memory tests passed!")