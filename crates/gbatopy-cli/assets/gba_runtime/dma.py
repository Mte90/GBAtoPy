"""GBA DMA Controller

Register layout (GBATEK):
  Each channel is 12 bytes (0x0C spacing):
    +0: Source Address      (32-bit)
    +4: Destination Address (32-bit)
    +8: Word Count          (16-bit)
    +A: Control             (16-bit)

  Control bits (16-bit):
    15:    Enable
    14:    IRQ on completion
    13-12: Dest control (0=inc, 1=dec, 2=fixed, 3=reload)
    11-10: Source control (0=inc, 1=dec, 2=fixed, 3=prohibited)
    8:     16-bit(0) / 32-bit(1)
    4:     Repeat
    3-2:   Start timing (DMA3)
    1-0:   Start timing (DMA0/1/2): 0=immediate, 1=VBlank, 2=HBlank, 3=special
"""

from typing import List, Optional


DMA_ENABLE = 0x8000
DMA_IRQ_ENABLE = 0x4000
DMA_TIMING_MASK = 0x0003
DMA_TIMING_IMMEDIATE = 0x0000
DMA_TIMING_VBLANK = 0x0001
DMA_TIMING_HBLANK = 0x0002
DMA_TIMING_SPECIAL = 0x0003
DMA3_TIMING_MASK = 0x000C
DMA3_TRIGGER_MASK = 0x0060

DMA_SRC_CTRL_MASK = 0x0C00
DMA_DST_CTRL_MASK = 0x3000
DMA_REPEAT = 0x0010
DMA_32BIT = 0x0100

DMA_CHANNEL_SPACING = 0x0C

DMA0_SRC_ADDR = 0x040000B0
DMA1_SRC_ADDR = 0x040000BC
DMA2_SRC_ADDR = 0x040000C8
DMA3_SRC_ADDR = 0x040000D4


class DMAChannel:
    """Individual DMA channel (0-3)"""

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
        self._interrupts = None

    def attach_interrupts(self, interrupts):
        self._interrupts = interrupts

    @property
    def irq_enabled(self) -> bool:
        return (self.control & DMA_IRQ_ENABLE) != 0

    def _timing_bits(self) -> int:
        if self.channel_id == 3:
            return (self.control >> 2) & 0x3
        return self.control & DMA_TIMING_MASK

    def is_immediate(self) -> bool:
        return self._timing_bits() == 0

    def is_vblank(self) -> bool:
        return self._timing_bits() == 1

    def is_hblank(self) -> bool:
        return self._timing_bits() == 2

    def is_special(self) -> bool:
        return self._timing_bits() == 3

    def get_src_increment(self) -> int:
        return (self.control >> 10) & 0x3

    def get_dst_increment(self) -> int:
        return (self.control >> 12) & 0x3

    def is_32bit(self) -> bool:
        return (self.control & DMA_32BIT) != 0

    def is_repeat(self) -> bool:
        return (self.control & DMA_REPEAT) != 0

    def get_transfer_size(self) -> int:
        return 4 if self.is_32bit() else 2

    def _base(self) -> int:
        return 0x040000B0 + (self.channel_id * DMA_CHANNEL_SPACING)

    def read_from_memory(self):
        b = self._base()
        self.src_addr = self.mem.read_u32(b)
        self.dst_addr = self.mem.read_u32(b + 4)
        self.count = self.mem.read_u16(b + 8)
        self.control = self.mem.read_u16(b + 10)
        self.enabled = (self.control & DMA_ENABLE) != 0

    def write_to_memory(self):
        b = self._base()
        self.mem.write_u32(b, self.src_addr)
        self.mem.write_u32(b + 4, self.dst_addr)
        self.mem.write_u16(b + 8, self.count & 0xFFFF)
        self.mem.write_u16(b + 10, self.control & 0xFFFF)

    def get_count_value(self) -> int:
        if self.count == 0:
            return 0x10000 if self.is_32bit() else 0x4000
        return self.count


class DMA:
    """GBA DMA Controller with 4 channels"""

    FIFO_A_ADDR = 0x040000A0
    FIFO_B_ADDR = 0x040000A4

    def __init__(self):
        self.mem = None
        self._interrupts = None
        self._apu = None
        self.channels: List[DMAChannel] = [
            DMAChannel(0, None),
            DMAChannel(1, None),
            DMAChannel(2, None),
            DMAChannel(3, None),
        ]

    def attach_memory(self, mem):
        self.mem = mem
        for ch in self.channels:
            ch.mem = mem

    def attach_apu(self, apu):
        self._apu = apu

    def attach_interrupts(self, interrupts):
        self._interrupts = interrupts
        for ch in self.channels:
            ch.attach_interrupts(interrupts)

    def fifo_a_is_empty(self) -> bool:
        if self._apu is None:
            return False
        return len(self._apu.fifo_a.data) == 0

    def fifo_b_is_empty(self) -> bool:
        if self._apu is None:
            return False
        return len(self._apu.fifo_b.data) == 0

    def start_transfer(self, channel: int):
        if not 0 <= channel <= 3:
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
                if dst == DMA.FIFO_A_ADDR and self._apu:
                    self._apu.fifo_a.write(value & 0xFF)
                    if count > 1:
                        self._apu.fifo_a.write((value >> 8) & 0xFF)
                        self._apu.fifo_a.write((value >> 16) & 0xFF)
                        self._apu.fifo_a.write((value >> 24) & 0xFF)
                elif dst == DMA.FIFO_B_ADDR and self._apu:
                    self._apu.fifo_b.write(value & 0xFF)
                    if count > 1:
                        self._apu.fifo_b.write((value >> 8) & 0xFF)
                        self._apu.fifo_b.write((value >> 16) & 0xFF)
                        self._apu.fifo_b.write((value >> 24) & 0xFF)
                else:
                    self.mem.write_u32(dst, value)
                src += 4
                dst += 4
            else:
                value = self.mem.read_u16(src)
                if dst == DMA.FIFO_A_ADDR and self._apu:
                    self._apu.fifo_a.write(value & 0xFF)
                    self._apu.fifo_a.write((value >> 8) & 0xFF)
                elif dst == DMA.FIFO_B_ADDR and self._apu:
                    self._apu.fifo_b.write(value & 0xFF)
                    self._apu.fifo_b.write((value >> 8) & 0xFF)
                else:
                    self.mem.write_u16(dst, value)
                src += 2
                dst += 2

        ch.src_addr = self._adjust_address(ch.src_addr, src_inc, count * transfer_size)
        ch.dst_addr = self._adjust_address(ch.dst_addr, dst_inc, count * transfer_size)

        if ch.is_repeat():
            ch.count = ch.get_count_value()
        else:
            ch.control &= ~DMA_ENABLE
            ch.enabled = False

        ch.write_to_memory()

        ch.busy = False
        ch.pending = False

        if ch.irq_enabled and self._interrupts:
            self._interrupts.dma_irq(ch.channel_id)

    def _adjust_address(self, addr: int, increment_mode: int, transfer_bytes: int) -> int:
        if increment_mode == 0:
            return addr + transfer_bytes
        elif increment_mode == 1:
            return addr - transfer_bytes
        elif increment_mode == 3:
            return addr  # Reload mode (destination only): keep original
        return addr  # Fixed (2)

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

    def custom_fire(self):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_special() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def timer_trigger(self, timer_index: int):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_special() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def fifo_a_empty_fire(self):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.channel_id == 3 and (ch.control & 0x0060) == 0x0020 and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def fifo_b_empty_fire(self):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.channel_id == 3 and (ch.control & 0x0060) == 0x0040 and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def fifo_a_step(self):
        if not self._apu:
            return
        self._apu.fifo_a.timer += 1
        if self._apu.fifo_a.timer >= self._apu.fifo_a.timer_period:
            self._apu.fifo_a.timer = 0
            self._apu.fifo_a.read()

    def get_channel(self, channel: int) -> Optional[DMAChannel]:
        if 0 <= channel <= 3:
            return self.channels[channel]
        return None


def clear_dma_pending(dma_instance):
    for ch in dma_instance.channels:
        ch.pending = False
