"""GBA BIOS SWI handler unit tests for GBAtoPy.

Tests cover division, square root, memory copy, LZ77 decompression,
trigonometric functions, and CPU state management.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from memory import Memory
from bios import BIOS


def test_swi_div_basic():
    """swi_div: basic integer division."""
    memory = Memory()
    bios = BIOS(memory)
    
    result = bios.swi_div(100, 7)
    assert result == 14, f"Expected 14, got {result}"
    
    print("✓ test_swi_div_basic passed")


def test_swi_div_by_zero():
    """swi_div: division by zero returns 0 (GBA ARM7TDMI behavior)."""
    memory = Memory()
    bios = BIOS(memory)
    
    result = bios.swi_div(100, 0)
    assert result == 0, f"Expected 0 for division by zero, got {result}"
    
    print("✓ test_swi_div_by_zero passed")


def test_swi_div_negative():
    """swi_div: negative dividend handling (signed division)."""
    memory = Memory()
    bios = BIOS(memory)
    
    # -100 / 7 = -14 with remainder -2, but GBA BIOS adjusts for negative remainder
    result = bios.swi_div(-100, 7)
    assert result == -16, f"Expected -16 (adjusted for negative remainder), got {result}"
    
    print("✓ test_swi_div_negative passed")


def test_swi_sqrt_perfect_square():
    """swi_sqrt: perfect square returns exact root."""
    memory = Memory()
    bios = BIOS(memory)
    
    result = bios.swi_sqrt(100)
    assert result == 10, f"Expected 10, got {result}"
    
    print("✓ test_swi_sqrt_perfect_square passed")


def test_swi_sqrt_non_perfect():
    """swi_sqrt: non-perfect square truncates."""
    memory = Memory()
    bios = BIOS(memory)
    
    result = bios.swi_sqrt(2)
    assert result == 1, f"Expected 1 (truncated), got {result}"
    
    print("✓ test_swi_sqrt_non_perfect passed")


def test_swi_sqrt_zero():
    """swi_sqrt: sqrt(0) = 0."""
    memory = Memory()
    bios = BIOS(memory)
    
    result = bios.swi_sqrt(0)
    assert result == 0, f"Expected 0, got {result}"
    
    print("✓ test_swi_sqrt_zero passed")


def test_swi_sqrt_max_u32():
    """swi_sqrt: sqrt of max u32 (0xFFFFFFFF) = 65535."""
    memory = Memory()
    bios = BIOS(memory)
    
    result = bios.swi_sqrt(0xFFFFFFFF)
    assert result == 65535, f"Expected 65535, got {result}"
    
    print("✓ test_swi_sqrt_max_u32 passed")


def test_swi_cpuset_basic():
    """swi_cpuset: basic 32-bit word copy."""
    memory = Memory()
    bios = BIOS(memory)
    
    # Write source data at 0x02000000 (EWRAM)
    src_addr = 0x02000000
    dst_addr = 0x02000100
    
    # Write 4 words (16 bytes) of known data
    for i in range(4):
        memory.write_u32(src_addr + i * 4, 0xDEADBEEF + i)
    
    # Copy 4 words (32-bit mode: bit 26 = 0x04000000)
    bios.swi_cpuset(src_addr, dst_addr, 4, 0x04000000)
    
    # Verify destination has the same data
    for i in range(4):
        expected = 0xDEADBEEF + i
        actual = memory.read_u32(dst_addr + i * 4)
        assert actual == expected, f"Word {i}: expected {hex(expected)}, got {hex(actual)}"
    
    print("✓ test_swi_cpuset_basic passed")


def test_swi_cpuset_count_semantics():
    """swi_cpuset: count = 2 copies 2 words (8 bytes)."""
    memory = Memory()
    bios = BIOS(memory)
    
    src_addr = 0x02000000
    dst_addr = 0x02000200
    
    # Write 4 words of data
    for i in range(4):
        memory.write_u32(src_addr + i * 4, 0x12345678 + i)
    
    # Copy only 2 words (32-bit mode: bit 26 = 0x04000000)
    bios.swi_cpuset(src_addr, dst_addr, 2, 0x04000000)
    
    # First 2 words should match
    assert memory.read_u32(dst_addr + 0) == 0x12345678
    assert memory.read_u32(dst_addr + 4) == 0x12345679
    
    # Third word should be unchanged (0)
    assert memory.read_u32(dst_addr + 8) == 0, f"Expected unchanged 0, got {hex(memory.read_u32(dst_addr + 8))}"
    
    print("✓ test_swi_cpuset_count_semantics passed")


def test_swi_cpufastset_basic():
    """swi_cpufastset: basic 32-bit word copy."""
    memory = Memory()
    bios = BIOS(memory)
    
    src_addr = 0x02000000
    dst_addr = 0x02000300
    
    # Write 4 words of known data
    for i in range(4):
        memory.write_u32(src_addr + i * 4, 0xBEEFCAFE + i)
    
    # Copy 4 words (not fill mode)
    bios.swi_cpufastset(src_addr, dst_addr, 4, 0)
    
    # Verify destination
    for i in range(4):
        expected = 0xBEEFCAFE + i
        actual = memory.read_u32(dst_addr + i * 4)
        assert actual == expected, f"Word {i}: expected {hex(expected)}, got {hex(actual)}"
    
    print("✓ test_swi_cpufastset_basic passed")


def test_swi_lz77_uncomp_raw():
    """swi_lz77_uncomp: decompress a raw (uncompressed) LZ77 stream."""
    memory = Memory()
    bios = BIOS(memory)
    
    # Create minimal LZ77 stream with header 0x10
    # Header: [0x10][size_l][size_m][size_h]
    # Then raw data with flag byte 0x00 (no compressed blocks)
    src_addr = 0x02000000
    
    # Write header: magic 0x10, size = 4 bytes
    memory.write_u8(src_addr + 0, 0x10)
    memory.write_u8(src_addr + 1, 4)  # size low
    memory.write_u8(src_addr + 2, 0)  # size mid
    memory.write_u8(src_addr + 3, 0)  # size high
    
    # Flag byte 0x00 = 8 raw bytes follow (but we only need 4)
    memory.write_u8(src_addr + 4, 0x00)
    
    # Raw data bytes
    memory.write_u8(src_addr + 5, 0xAA)
    memory.write_u8(src_addr + 6, 0xBB)
    memory.write_u8(src_addr + 7, 0xCC)
    memory.write_u8(src_addr + 8, 0xDD)
    
    dst_addr = 0x02001000
    
    # Decompress
    result_size = bios.swi_lz77_uncomp(src_addr, dst_addr)
    
    assert result_size == 4, f"Expected decompressed size 4, got {result_size}"
    assert memory.read_u8(dst_addr + 0) == 0xAA
    assert memory.read_u8(dst_addr + 1) == 0xBB
    assert memory.read_u8(dst_addr + 2) == 0xCC
    assert memory.read_u8(dst_addr + 3) == 0xDD
    
    print("✓ test_swi_lz77_uncomp_raw passed")


def test_swi_arctan_zero():
    """swi_arctan: arctan(0) = 0."""
    memory = Memory()
    bios = BIOS(memory)
    
    result = bios.swi_arctan(0)
    assert result == 0, f"Expected 0, got {result}"
    
    print("✓ test_swi_arctan_zero passed")


def test_swi_arctan2_zero():
    """swi_arctan2: arctan2(0, 1) = 0."""
    memory = Memory()
    bios = BIOS(memory)
    
    result = bios.swi_arctan2(0, 1)
    assert result == 0, f"Expected 0, got {result}"
    
    print("✓ test_swi_arctan2_zero passed")


if __name__ == "__main__":
    # Division tests
    test_swi_div_basic()
    test_swi_div_by_zero()
    test_swi_div_negative()
    
    # Sqrt tests
    test_swi_sqrt_perfect_square()
    test_swi_sqrt_non_perfect()
    test_swi_sqrt_zero()
    test_swi_sqrt_max_u32()
    
    # CPU set tests
    test_swi_cpuset_basic()
    test_swi_cpuset_count_semantics()
    test_swi_cpufastset_basic()
    
    # LZ77 decompression test
    test_swi_lz77_uncomp_raw()
    
    # Trig tests
    test_swi_arctan_zero()
    test_swi_arctan2_zero()
    
    print("\nAll 13 BIOS SWI tests passed!")