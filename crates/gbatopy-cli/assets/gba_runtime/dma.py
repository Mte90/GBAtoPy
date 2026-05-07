"""GBA DMA Controller"""

from typing import List, Optional


DMA_ENABLE = 0x80000000
DMA_TIMING_MASK = 0x30000000
DMA_TIMING_IMMEDIATE = 0x80000000
DMA_TIMING_VBLANK = 0x40000000
DMA_TIMING_HBLANK = 0x30000000
DMA_TIMING_DISPLAY = 0x00000000

DMA_SRC_INCREMENT = 0x00000000
DMA_SRC_DECREMENT = 0x00100000
DMA_SRC_FIXED = 0x00200000
DMA_DST_INCREMENT = 0x00000000
DMA_DST_DECREMENT = 0x00001000
DMA_DST_FIXED = 0x00002000
DMA_REPEAT = 0x00000010
DMA_16BIT = 0x00000000
DMA_32BIT = 0x04000000
DMA_GAMEPAK_DRQ = 0x08000000

DMA0_SRC_ADDR = 0x040000B0
DMA0_DST_ADDR = 0x040000B4
DMA0_COUNT = 0x040000B8
DMA0_CONTROL = 0x040000BC

DMA1_SRC_ADDR = 0x040000C0
DMA1_DST_ADDR = 0x040000C4
DMA1_COUNT = 0x040000C8
DMA1_CONTROL = 0x040000CC

DMA2_SRC_ADDR = 0x040000D0
DMA2_DST_ADDR = 0x040000D4
DMA2_COUNT = 0x040000D8
DMA2_CONTROL = 0x040000DC

DMA3_SRC_ADDR = 0x040000E0
DMA3_DST_ADDR = 0x040000E4
DMA3_COUNT = 0x040000E8
DMA3_CONTROL = 0x040000EC


class DMAChannel:
    def __init__(self, channel_id: int, mem):
        self.channel_id = channel_id
        self.mem = mem
        self.src_addr: int = 0
        self.dst_addr: int = 0
        self.count: int = 0
        self.control: int = 0
        self.enabled: bool = False
        self.busy: bool = False
        self.pending: bool = False
        self.repeats: bool = False
        self.word_size_32bit: bool = False
        self.src_increment: int = 0
        self.dst_increment: int = 0

    def get_timing_bits(self) -> int:
        return self.control & DMA_TIMING_MASK

    def is_immediate(self) -> bool:
        return (self.control & DMA_TIMING_IMMEDIATE) == DMA_TIMING_IMMEDIATE

    def is_vblank(self) -> bool:
        timing = self.get_timing_bits()
        return timing == DMA_TIMING_VBLANK

    def is_hblank(self) -> bool:
        timing = self.get_timing_bits()
        return (self.control & 0x80000000) == 0x80000000 and timing == DMA_TIMING_HBLANK

    def is_display_sync(self) -> bool:
        timing = self.get_timing_bits()
        return timing == DMA_TIMING_DISPLAY and (self.control & 0x80000000) == 0

    def get_src_increment(self) -> int:
        return (self.control >> 20) & 0x3

    def get_dst_increment(self) -> int:
        return (self.control >> 12) & 0x3

    def is_32bit(self) -> bool:
        return (self.control & DMA_32BIT) != 0

    def is_repeat(self) -> bool:
        return (self.control & DMA_REPEAT) != 0

    def get_transfer_size(self) -> int:
        return 4 if self.is_32bit() else 2

    def read_from_memory(self):
        base = 0x040000B0 + (self.channel_id * 0x10)
        self.src_addr = self.mem.read_u32(base)
        self.dst_addr = self.mem.read_u32(base + 4)
        self.count = self.mem.read_u32(base + 8)
        self.control = self.mem.read_u32(base + 12)
        self.enabled = (self.control & DMA_ENABLE) != 0

    def write_to_memory(self):
        base = 0x040000B0 + (self.channel_id * 0x10)
        self.mem.write_u32(base, self.src_addr)
        self.mem.write_u32(base + 4, self.dst_addr)
        self.mem.write_u32(base + 8, self.count)
        self.mem.write_u32(base + 12, self.control)

    def get_count_value(self) -> int:
        if self.count == 0:
            return 0x10000 if self.is_32bit() else 0x4000
        return self.count


class DMA:
    def __init__(self, mem, interrupts):
        self.mem = mem
        self.interrupts = interrupts
        self.channels: List[DMAChannel] = [
            DMAChannel(0, mem),
            DMAChannel(1, mem),
            DMAChannel(2, mem),
            DMAChannel(3, mem),
        ]
        self._setup_mmio()

    def _setup_mmio(self):
        base = 0x040000B0
        for i in range(4):
            offset = base + (i * 0x10)
            self.mem.register_mmio_write(offset + 12, self._make_mmio_handler(i))

    def _make_mmio_handler(self, channel: int):
        def handler(addr: int, value: int):
            self.channels[channel].control = value
            self.channels[channel].enabled = (value & DMA_ENABLE) != 0
            if self.channels[channel].enabled and self.channels[channel].is_immediate():
                self.channels[channel].pending = True

        return handler

    def start_transfer(self, channel: int):
        if channel < 0 or channel > 3:
            return

        ch = self.channels[channel]
        ch.read_from_memory()

        if not ch.enabled:
            return

        self._do_transfer(ch)

    def _do_transfer(self, ch: DMAChannel):
        if ch.busy:
            return

        ch.busy = True

        src_inc = ch.get_src_increment()
        dst_inc = ch.get_dst_increment()
        count = ch.get_count_value()
        transfer_size = ch.get_transfer_size()

        src = ch.src_addr
        dst = ch.dst_addr

        for _ in range(count):
            if transfer_size == 4:
                value = self.mem.read_u32(src)
                self.mem.write_u32(dst, value)
                src += 4
                dst += 4
            else:
                value = self.mem.read_u16(src)
                self.mem.write_u16(dst, value)
                src += 2
                dst += 2

        ch.src_addr = self._adjust_address(ch.src_addr, src_inc, count * transfer_size)
        ch.dst_addr = self._adjust_address(ch.dst_addr, dst_inc, count * transfer_size)

        if ch.is_repeat():
            # Repeat DMA keeps enabled, source/dest will be adjusted on next trigger
            ch.busy = False  # Not busy during repeat delay
        else:
            ch.control &= ~DMA_ENABLE
            ch.enabled = False

        ch.write_to_memory()
        ch.busy = False

        # Fire DMA interrupt
        self.interrupts.dma_irq(ch.channel_id)

    def _adjust_address(self, addr: int, increment_mode: int, count: int) -> int:
        if increment_mode == 0:
            return addr + count
        elif increment_mode == 1:
            return addr - count
        else:
            return addr

    def step(self):
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_immediate():
                if ch.pending:
                    ch.pending = False
                    self._do_transfer(ch)

    def vblank_fire(self):
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_vblank():
                self._do_transfer(ch)
                ch.pending = False

    def hblank_fire(self):
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_hblank():
                self._do_transfer(ch)
                ch.pending = False

    def get_channel(self, channel: int) -> Optional[DMAChannel]:
        if 0 <= channel <= 3:
            return self.channels[channel]
        return None


def clear_dma_pending(dma_instance):
    for ch in dma_instance.channels:
        ch.pending = False
