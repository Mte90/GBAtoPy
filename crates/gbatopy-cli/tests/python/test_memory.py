import pytest
from gba_runtime.memory import Memory, MemoryMap


def test_memory_init():
    mem = Memory()
    assert len(mem.bios) == MemoryMap.BIOS_SIZE
    assert len(mem.ewram) == MemoryMap.EWRAM_SIZE
    assert len(mem.iwram) == MemoryMap.IWRAM_SIZE
    assert len(mem.io) == MemoryMap.IO_SIZE


def test_memory_default():
    mem = Memory()
    assert mem.rom is None
    assert mem.rom_size == 0


def test_iwram_read_write():
    mem = Memory()
    mem.write_u32(0x03000000, 42)
    assert mem.read_u32(0x03000000) == 42


def test_ewram_read_write():
    mem = Memory()
    mem.write_u32(0x02000000, 123)
    assert mem.read_u32(0x02000000) == 123


def test_io_read_write():
    mem = Memory()
    mem.write_u16(0x04000000, 0xFFFF)
    assert mem.read_u16(0x04000000) == 0xFFFF


def test_palette_read_write():
    mem = Memory()
    mem.write_u16(0x05000000, 0x1234)
    assert mem.read_u16(0x05000000) == 0x1234


def test_vram_read_write():
    mem = Memory()
    mem.write_u16(0x06000000, 0xABCD)
    assert mem.read_u16(0x06000000) == 0xABCD


def test_oam_read_write():
    mem = Memory()
    mem.write_u32(0x07000000, 0xDEADBEEF)
    assert mem.read_u32(0x07000000) == 0xDEADBEEF


def test_sram_read_write():
    mem = Memory()
    mem.write_u8(0x0A000000, 0x42)
    assert mem.read_u8(0x0A000000) == 0x42


def test_bios_read_only():
    mem = Memory()
    original = mem.read_u8(0x00000000)
    mem.write_u8(0x00000000, 0xFF)
    assert mem.read_u8(0x00000000) == original


def test_open_bus():
    mem = Memory()
    mem.write_u8(0x03000000, 0xAB)
    result = mem.read_u8(0xFFFFFFFF)
    assert result == 0xAB


def test_mmio_dispatch():
    mem = Memory()
    calls = []
    
    def handler(addr, value):
        calls.append((addr, value))
    
    mem.register_mmio_write(0x00, handler)
    mem.write_u8(0x04000000, 0x42)
    
    assert len(calls) == 1
    assert calls[0] == (0x04000000, 0x42)


def test_address_mirror():
    mem = Memory()
    mem.write_u32(0x03000000, 0xDEADBEEF)
    assert mem.read_u32(0x03001000) == 0xDEADBEEF


def test_16bit_aligned_read():
    mem = Memory()
    mem.write_u16(0x03000000, 0x1234)
    assert mem.read_u16(0x03000000) == 0x1234


def test_32bit_aligned_read():
    mem = Memory()
    mem.write_u32(0x03000000, 0x12345678)
    assert mem.read_u32(0x03000000) == 0x12345678