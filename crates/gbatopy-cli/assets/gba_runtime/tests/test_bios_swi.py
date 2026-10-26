"""GBA BIOS SWI handler unit tests for GBAtoPy.

Tests cover division, square root, memory copy, LZ77 decompression,
trigonometric functions, sound driver SWIs, and CPU state management.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from memory import Memory
from bios import BIOS
import arm7tdmi


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


def test_swi_sound_driver_init():
    """SWI 0x19 SoundDriverInit: stores work area pointer."""
    memory = Memory()
    cpu = arm7tdmi.ARM7TDMI(memory)
    
    # Set up work area pointer in r0
    work_area = 0x03005000
    cpu.registers[0] = work_area
    
    # Call SWI 0x19
    cpu.swi_handler(0x19)
    
    # Verify work area was stored
    assert hasattr(cpu, '_sound_work_area'), "CPU should have _sound_work_area attribute"
    assert cpu._sound_work_area == work_area, f"Expected work area {hex(work_area)}, got {hex(cpu._sound_work_area)}"
    
    print("✓ test_swi_sound_driver_init passed")


def test_swi_sound_driver_mode():
    """SWI 0x1A SoundDriverMode: stores mode value."""
    memory = Memory()
    cpu = arm7tdmi.ARM7TDMI(memory)
    
    # Set mode in r0
    mode = 0x0003  # Example mode flags
    cpu.registers[0] = mode
    
    # Call SWI 0x1A
    cpu.swi_handler(0x1A)
    
    # Verify mode was stored
    assert hasattr(cpu, '_sound_mode'), "CPU should have _sound_mode attribute"
    assert cpu._sound_mode == mode, f"Expected mode {hex(mode)}, got {hex(cpu._sound_mode)}"
    
    print("✓ test_swi_sound_driver_mode passed")


def test_swi_sound_driver_main():
    """SWI 0x1B SoundDriverMain: minimal processing, no crash."""
    memory = Memory()
    cpu = arm7tdmi.ARM7TDMI(memory)
    
    # Set up work area first
    cpu._sound_work_area = 0x03005000
    
    # Call SWI 0x1B - should not crash
    cpu.swi_handler(0x1B)
    
    # Just verify it returns cleanly
    assert True
    
    print("✓ test_swi_sound_driver_main passed")


def test_swi_sound_driver_vsync():
    """SWI 0x1C SoundDriverVSync: VBlank processing, no crash."""
    memory = Memory()
    cpu = arm7tdmi.ARM7TDMI(memory)
    
    # Set up work area first
    cpu._sound_work_area = 0x03005000
    
    # Call SWI 0x1C - should not crash
    cpu.swi_handler(0x1C)
    
    # Just verify it returns cleanly
    assert True
    
    print("✓ test_swi_sound_driver_vsync passed")


def test_swi_sound_channel_clear():
    """SWI 0x1D SoundChannelClear: no-op, no crash."""
    memory = Memory()
    cpu = arm7tdmi.ARM7TDMI(memory)
    
    # Call SWI 0x1D - should not crash
    cpu.swi_handler(0x1D)
    
    # Just verify it returns cleanly
    assert True
    
    print("✓ test_swi_sound_channel_clear passed")


def test_swi_midi_key_to_freq():
    """SWI 0x1E MidiKey2Freq: convert MIDI key to frequency."""
    memory = Memory()
    cpu = arm7tdmi.ARM7TDMI(memory)
    
    # Test case 1: MIDI key 69 = A4 = 440 Hz
    # In fixed-point (8.8 format): 69 * 256 = 17664
    cpu.registers[1] = 69 * 256  # 69.0 in fixed-point
    cpu.swi_handler(0x1E)
    
    # Expected: 440 Hz * 256 = 112640 (fixed-point)
    expected_440 = int(440.0 * 256)
    actual = cpu.registers[0]
    assert abs(actual - expected_440) < 100, f"Key 69: expected ~{expected_440} (440Hz), got {actual}"
    
    # Test case 2: MIDI key 81 = A5 = 880 Hz (one octave up)
    cpu.registers[1] = 81 * 256  # 81.0 in fixed-point
    cpu.swi_handler(0x1E)
    
    # Expected: 880 Hz * 256 = 225280 (fixed-point)
    expected_880 = int(880.0 * 256)
    actual = cpu.registers[0]
    assert abs(actual - expected_880) < 100, f"Key 81: expected ~{expected_880} (880Hz), got {actual}"
    
    # Test case 3: MIDI key 60 = C4 (middle C) ≈ 261.63 Hz
    cpu.registers[1] = 60 * 256  # 60.0 in fixed-point
    cpu.swi_handler(0x1E)
    
    # Expected: 261.63 Hz * 256 ≈ 66977
    expected_c4 = int(261.63 * 256)
    actual = cpu.registers[0]
    assert abs(actual - expected_c4) < 200, f"Key 60: expected ~{expected_c4} (261.63Hz), got {actual}"
    
    print("✓ test_swi_midi_key_to_freq passed")


def test_swi_midi_key_to_freq_fractional():
    """SWI 0x1E MidiKey2Freq: fractional key values."""
    memory = Memory()
    cpu = arm7tdmi.ARM7TDMI(memory)
    
    # Test with key 69.5 (half step between A4 and A#4)
    # 69.5 * 256 = 17792
    cpu.registers[1] = 17792
    cpu.swi_handler(0x1E)
    
    # Expected: 440 * 2^(0.5/12) ≈ 466.16 Hz * 256 ≈ 119337
    expected = int(440.0 * (2.0 ** (0.5 / 12.0)) * 256)
    actual = cpu.registers[0]
    assert abs(actual - expected) < 200, f"Key 69.5: expected ~{expected}, got {actual}"
    
    print("✓ test_swi_midi_key_to_freq_fractional passed")


def test_swi_sound_vsync_off():
    """SWI 0x1F SoundDriverVSyncOff: disables VSync processing."""
    memory = Memory()
    cpu = arm7tdmi.ARM7TDMI(memory)
    
    # Initially vsync should be enabled (default)
    assert not hasattr(cpu, '_sound_vsync_enabled') or cpu._sound_vsync_enabled == True
    
    # Call SWI 0x1F
    cpu.swi_handler(0x1F)
    
    # Verify vsync is disabled
    assert hasattr(cpu, '_sound_vsync_enabled'), "CPU should have _sound_vsync_enabled attribute"
    assert cpu._sound_vsync_enabled == False, f"Expected vsync disabled, got {cpu._sound_vsync_enabled}"
    
    print("✓ test_swi_sound_vsync_off passed")


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
    
    # Sound driver SWI tests (0x19-0x1F)
    test_swi_sound_driver_init()
    test_swi_sound_driver_mode()
    test_swi_sound_driver_main()
    test_swi_sound_driver_vsync()
    test_swi_sound_channel_clear()
    test_swi_midi_key_to_freq()
    test_swi_midi_key_to_freq_fractional()
    test_swi_sound_vsync_off()
    
    print("\nAll 21 BIOS SWI tests passed!")