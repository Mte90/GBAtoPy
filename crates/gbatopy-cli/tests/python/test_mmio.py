import pytest
from gba_runtime.memory import Memory, MemoryMap
from gba_runtime.ppu import PPU
from gba_runtime.apu import APU
from gba_runtime.dma import DMA
from gba_runtime.timers import Timers
from gba_runtime.input import Input, DEFAULT_KEYS
from gba_runtime.interrupts import InterruptController


def test_ppu_dispcnt_dispatch():
    mem = Memory()
    ppu = PPU(mem)
    mem.attach_ppu(ppu)

    mem.write_u32(0x04000000, 0x0007)
    assert ppu.dispcnt == 0x0007


def test_ppu_dispcnt_u16_dispatch():
    mem = Memory()
    ppu = PPU(mem)
    mem.attach_ppu(ppu)

    mem.write_u16(0x04000000, 0x0403)
    assert ppu.dispcnt == 0x0403


def test_ppu_bgcnt_dispatch():
    mem = Memory()
    ppu = PPU(mem)
    mem.attach_ppu(ppu)

    mem.write_u16(0x04000008, 0x01FF)
    assert ppu.bg_cnt[0] == 0x01FF

    mem.write_u16(0x0400000A, 0x0080)
    assert ppu.bg_cnt[1] == 0x0080


def test_ppu_scroll_dispatch():
    mem = Memory()
    ppu = PPU(mem)
    mem.attach_ppu(ppu)

    mem.write_u16(0x04000010, 0x00FF)
    assert ppu.bg_hofs[0] == 0x00FF

    mem.write_u16(0x04000012, 0x00AB)
    assert ppu.bg_vofs[0] == 0x00AB


def test_ppu_no_dispatch_when_not_attached():
    mem = Memory()
    mem.write_u16(0x04000000, 0x0007)
    assert mem.read_u16(0x04000000) == 0x0007


def test_apu_dispatch():
    mem = Memory()
    apu = APU()
    mem.attach_apu(apu)

    mem.write_u16(0x04000062, 0x0040)
    assert apu.ch1.duty_cycle == 1
    assert apu.ch1.length == 0x40


def test_apu_ch2_dispatch():
    mem = Memory()
    apu = APU()
    mem.attach_apu(apu)

    mem.write_u16(0x04000068, 0x00C0)
    assert apu.ch2.duty_cycle == 3
    assert apu.ch2.length == 0


def test_apu_no_dispatch_when_not_attached():
    mem = Memory()
    mem.write_u16(0x04000062, 0xFFFF)
    assert mem.read_u16(0x04000062) == 0xFFFF


def test_timer_dispatch():
    mem = Memory()
    timers = Timers()
    mem.attach_timers(timers)

    mem.write_u16(0x04000100, 0x1234)
    assert timers.get_timer(0) == 0x1234


def test_timer_control_dispatch():
    mem = Memory()
    timers = Timers()
    mem.attach_timers(timers)

    mem.write_u16(0x04000102, 0x00C3)
    assert timers.get_control(0) == 0xC3
    assert timers.channels[0].enabled


def test_timer_channel1_dispatch():
    mem = Memory()
    timers = Timers()
    mem.attach_timers(timers)

    mem.write_u16(0x04000104, 0xBEEF)
    assert timers.get_timer(1) == 0xBEEF


def test_timer_no_dispatch_when_not_attached():
    mem = Memory()
    mem.write_u16(0x04000100, 0x1234)
    assert mem.read_u16(0x04000100) == 0x1234


def test_input_dispatch():
    mem = Memory()
    inp = Input()
    mem.attach_input(inp)

    keys = mem.read_u16(0x04000130)
    assert keys == DEFAULT_KEYS


def test_input_read_without_attach():
    mem = Memory()
    result = mem.read_u16(0x04000130)
    assert result == 0


def test_interrupt_dispatch():
    mem = Memory()
    irq = InterruptController()
    mem.attach_interrupts(irq)

    mem.write_u16(0x04000200, 0x0001)
    assert irq.read_ie() == 0x0001


def test_interrupt_if_write_clears():
    mem = Memory()
    irq = InterruptController()
    mem.attach_interrupts(irq)

    irq.if_reg = 0xFFFF
    mem.write_u16(0x04000204, 0x0001)
    assert irq.read_if() == 0xFFFE


def test_interrupt_ime_dispatch():
    mem = Memory()
    irq = InterruptController()
    mem.attach_interrupts(irq)

    mem.write_u16(0x04000208, 0x0001)
    assert irq.read_ime() == 0x0001

    mem.write_u16(0x04000208, 0x0000)
    assert irq.read_ime() == 0x0000


def test_interrupt_no_dispatch_when_not_attached():
    mem = Memory()
    mem.write_u16(0x04000200, 0xFFFF)
    assert mem.read_u16(0x04000200) == 0xFFFF


def test_dma_dispatch():
    mem = Memory()
    dma = DMA(mem)
    mem.attach_dma(dma)

    mem.write_u32(0x040000B0, 0x02000000)
    assert dma.channels[0].src_addr == 0x02000000

    mem.write_u32(0x040000B4, 0x03000000)
    assert dma.channels[0].dst_addr == 0x03000000

    mem.write_u32(0x040000B8, 0x0010)
    assert dma.channels[0].count == 0x0010


def test_dma_control_enables_channel():
    mem = Memory()
    dma = DMA(mem)
    mem.attach_dma(dma)

    mem.write_u32(0x040000BC, 0x80000000)
    assert dma.channels[0].enabled
    assert dma.channels[0].control == 0x80000000


def test_dma_channel1_dispatch():
    mem = Memory()
    dma = DMA(mem)
    mem.attach_dma(dma)

    mem.write_u32(0x040000C4, 0x06000000)
    assert dma.channels[1].dst_addr == 0x06000000


def test_dma_no_dispatch_when_not_attached():
    mem = Memory()
    mem.write_u32(0x040000B0, 0x02000000)
    assert mem.read_u32(0x040000B0) == 0x02000000


def test_attach_all_modules():
    mem = Memory()
    ppu = PPU(mem)
    apu = APU()
    timers = Timers()
    irq = InterruptController()
    inp = Input()

    mem.attach_ppu(ppu)
    mem.attach_apu(apu)
    mem.attach_timers(timers)
    mem.attach_interrupts(irq)
    mem.attach_input(inp)

    mem.write_u16(0x04000000, 0x0403)
    assert ppu.dispcnt == 0x0403

    mem.write_u16(0x04000100, 0x8000)
    assert timers.get_timer(0) == 0x8000

    keys = mem.read_u16(0x04000130)
    assert keys == DEFAULT_KEYS

    mem.write_u16(0x04000200, 0x0003)
    assert irq.read_ie() == 0x0003


def test_existing_memory_tests_still_pass():
    mem = Memory()
    mem.write_u32(0x03000000, 42)
    assert mem.read_u32(0x03000000) == 42

    mem.write_u32(0x02000000, 123)
    assert mem.read_u32(0x02000000) == 123

    mem.write_u16(0x05000000, 0x1234)
    assert mem.read_u16(0x05000000) == 0x1234

    mem.write_u16(0x06000000, 0xABCD)
    assert mem.read_u16(0x06000000) == 0xABCD

    mem.write_u32(0x07000000, 0xDEADBEEF)
    assert mem.read_u32(0x07000000) == 0xDEADBEEF
