import pytest
from gba_runtime.dma import DMA, DMAChannel
from gba_runtime.memory import Memory


def test_dma_init():
    mem = Memory()
    dma = DMA(mem)
    assert len(dma.channels) == 4


def test_start_transfer_basic():
    mem = Memory()
    dma = DMA(mem)
    dma.start_transfer(0)
    assert True


def test_channel_properties():
    mem = Memory()
    dma = DMA(mem)
    ch = dma.channels[0]
    assert ch.channel_id == 0
    assert ch.enabled is False
    assert ch.busy is False


def test_read_from_memory():
    mem = Memory()
    mem.write_u32(0x040000B0, 0x02000000)
    mem.write_u32(0x040000B4, 0x05000000)
    mem.write_u32(0x040000B8, 0x0010)
    mem.write_u32(0x040000BC, 0x80000000)

    ch = DMAChannel(0, mem)
    ch.read_from_memory()

    assert ch.src_addr == 0x02000000
    assert ch.dst_addr == 0x05000000
    assert ch.count == 0x0010
    assert ch.enabled is True


def test_write_to_memory():
    mem = Memory()
    ch = DMAChannel(0, mem)
    ch.src_addr = 0x02000000
    ch.dst_addr = 0x05000000
    ch.count = 0x0010
    ch.control = 0x80000000

    ch.write_to_memory()

    assert mem.read_u32(0x040000B0) == 0x02000000
    assert mem.read_u32(0x040000B4) == 0x05000000
    assert mem.read_u32(0x040000B8) == 0x0010
    assert mem.read_u32(0x040000BC) == 0x80000000


def test_timing_bits():
    mem = Memory()
    ch = DMAChannel(0, mem)

    ch.control = 0x80000000
    assert ch.is_immediate() is True
    assert ch.is_vblank() is False
    assert ch.is_hblank() is False

    ch.control = 0x40000000
    assert ch.is_immediate() is False
    assert ch.is_vblank() is True

    ch.control = 0x80000000 | 0x20000000
    assert ch.is_hblank() is True


def test_get_channel():
    mem = Memory()
    dma = DMA(mem)

    assert dma.get_channel(0) is not None
    assert dma.get_channel(3) is not None
    assert dma.get_channel(4) is None


def test_step():
    mem = Memory()
    dma = DMA(mem)
    dma.step()


def test_vblank_fire():
    mem = Memory()
    dma = DMA(mem)
    dma.vblank_fire()


def test_hblank_fire():
    mem = Memory()
    dma = DMA(mem)
    dma.hblank_fire()


def test_32bit_transfer():
    mem = Memory()
    for i in range(16):
        mem.ewram[i] = i + 1

    mem.write_u32(0x040000B0, 0x02000000)
    mem.write_u32(0x040000B4, 0x03000000)
    mem.write_u32(0x040000B8, 4)
    mem.write_u32(0x040000BC, 0x84000000)

    dma = DMA(mem)
    dma.start_transfer(0)

    assert mem.iwram[0] == 1
    assert mem.iwram[1] == 2
    assert mem.iwram[2] == 3
    assert mem.iwram[3] == 4


def test_16bit_transfer():
    mem = Memory()
    for i in range(8):
        mem.ewram[i] = i + 1

    mem.write_u32(0x040000B0, 0x02000000)
    mem.write_u32(0x040000B4, 0x03000000)
    mem.write_u32(0x040000B8, 4)
    mem.write_u32(0x040000BC, 0x80000000)

    dma = DMA(mem)
    dma.start_transfer(0)

    assert mem.iwram[0] == 1
    assert mem.iwram[1] == 2


def test_count_zero_max():
    mem = Memory()
    ch = DMAChannel(0, mem)

    ch.count = 0
    ch.control = 0x80000000
    assert ch.get_count_value() == 0x10000

    ch.control = 0x80000000 & ~DMA_32BIT
    assert ch.get_count_value() == 0x4000


def test_all_channels_accessible():
    mem = Memory()
    dma = DMA(mem)

    for i in range(4):
        assert dma.channels[i].channel_id == i


def test_transfer_disabled():
    mem = Memory()
    mem.write_u32(0x040000B0, 0x02000000)
    mem.write_u32(0x040000B4, 0x03000000)
    mem.write_u32(0x040000B8, 4)
    mem.write_u32(0x040000BC, 0x00000000)

    dma = DMA(mem)
    dma.start_transfer(0)
    assert mem.iwram[0] == 0


def test_invalid_channel_start():
    mem = Memory()
    dma = DMA(mem)
    dma.start_transfer(-1)
    dma.start_transfer(4)
