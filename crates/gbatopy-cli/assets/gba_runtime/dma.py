"""GBA DMA Controller

Register layout (GBATEK / mGBA dma.h):
  Each channel is 12 bytes (0x0C spacing):
    +0: Source Address      (32-bit)
    +4: Destination Address (32-bit)
    +8: Word Count          (16-bit)
    +A: Control             (16-bit)

  Control bits (16-bit) — verified against mGBA dma.h:
    15:     Enable
    14:     IRQ on completion (DoIRQ)
    13-12:  Start timing (0=immediate, 1=VBlank, 2=HBlank, 3=special)
    11:     DRQ (DMA3 only)
    10:     Transfer width (0=16-bit, 1=32-bit)
    9:      Repeat
    8-7:    Source control (0=increment, 1=decrement, 2=fixed, 3=prohibited)
    6-5:    Destination control (0=increment, 1=decrement, 2=fixed, 3=reload)
    4-0:    Reserved
"""

from typing import List, Optional


DMA_ENABLE         = 0x8000  # bit 15
DMA_IRQ_ENABLE     = 0x4000  # bit 14
DMA_TIMING_MASK    = 0x3000  # bits 13-12
DMA_TIMING_IMMEDIATE = 0x0000
DMA_TIMING_VBLANK    = 0x1000
DMA_TIMING_HBLANK     = 0x2000
DMA_TIMING_SPECIAL    = 0x3000
DMA_DRQ            = 0x0800  # bit 11 (DMA3 only)
DMA_32BIT          = 0x0400  # bit 10
DMA_REPEAT          = 0x0200  # bit 9
DMA_SRC_CTRL_MASK   = 0x0180  # bits 8-7
DMA_DST_CTRL_MASK   = 0x0060  # bits 6-5

DMA_CHANNEL_SPACING = 0x0C

DMA0_SRC_ADDR = 0x040000B0  # GBATEK §12.2: DMA0SAD
DMA1_SRC_ADDR = 0x040000BC  # GBATEK §12.2: DMA1SAD (channel spacing 0x0C)
DMA2_SRC_ADDR = 0x040000C8  # GBATEK §12.2: DMA2SAD
DMA3_SRC_ADDR = 0x040000D4  # GBATEK §12.2: DMA3SAD

# DMA_OFFSET[] = { +1, -1, 0, +1 } — matches mGBA dma.c
# Indexed by SrcControl/DestControl value:
#   0=increment, 1=decrement, 2=fixed, 3=reload(same as increment during transfer)
_DMA_OFFSET = {0: 1, 1: -1, 2: 0, 3: 1}


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
        self._orig_src = 0
        self._orig_dst = 0
        self._orig_count = 0
        self.latch: int = 0
    def attach_interrupts(self, interrupts):
        self._interrupts = interrupts

    @property
    def irq_enabled(self) -> bool:
        return (self.control & DMA_IRQ_ENABLE) != 0

    def _timing_bits(self) -> int:
        return (self.control >> 12) & 0x3

    def is_immediate(self) -> bool:
        return self._timing_bits() == 0

    def is_vblank(self) -> bool:
        return self._timing_bits() == 1

    def is_hblank(self) -> bool:
        return self._timing_bits() == 2

    def is_special(self) -> bool:
        return self._timing_bits() == 3

    def get_src_increment(self) -> int:
        return (self.control >> 7) & 0x3

    def get_dst_increment(self) -> int:
        return (self.control >> 5) & 0x3

    def is_32bit(self) -> bool:
        return (self.control & DMA_32BIT) != 0

    def is_repeat(self) -> bool:
        return (self.control & DMA_REPEAT) != 0

    def get_transfer_size(self) -> int:
        return 4 if self.is_32bit() else 2

    def _base(self) -> int:
        return 0x040000B0 + (self.channel_id * DMA_CHANNEL_SPACING)

    def read_from_memory(self):
        """Load DMA registers (GBATEK §12.2: SAD, DAD, DCNT)."""
        b = self._base() - 0x04000000
        new_control = self.mem.io[b+10] | (self.mem.io[b+11] << 8)
        new_enabled = (new_control & DMA_ENABLE) != 0

        if new_enabled and not self.enabled:
            # GBATEK §12.5: Address writeback — SAD/DAD updated after transfer
            # On REPEAT+reload (DestControl=3), DAD reloads to original value
            self.src_addr = self.mem.io[b] | (self.mem.io[b+1] << 8) | (self.mem.io[b+2] << 16) | (self.mem.io[b+3] << 24)
            self.dst_addr = self.mem.io[b+4] | (self.mem.io[b+5] << 8) | (self.mem.io[b+6] << 16) | (self.mem.io[b+7] << 24)
            self.count = self.mem.io[b+8] | (self.mem.io[b+9] << 8)
            self._orig_src = self.src_addr
            self._orig_dst = self.dst_addr
            self._orig_count = self.count
        elif not new_enabled:
            self.src_addr = self.mem.io[b] | (self.mem.io[b+1] << 8) | (self.mem.io[b+2] << 16) | (self.mem.io[b+3] << 24)
            self.dst_addr = self.mem.io[b+4] | (self.mem.io[b+5] << 8) | (self.mem.io[b+6] << 16) | (self.mem.io[b+7] << 24)
            self.count = self.mem.io[b+8] | (self.mem.io[b+9] << 8)

        self.control = new_control
        self.enabled = new_enabled

    def _write_control_to_memory(self):
        b = self._base() - 0x04000000
        self.mem.io[b+10] = self.control & 0xFF
        self.mem.io[b+11] = (self.control >> 8) & 0xFF

    def write_to_memory(self):
        b = self._base() - 0x04000000
        self.mem.io[b] = self.src_addr & 0xFF
        self.mem.io[b+1] = (self.src_addr >> 8) & 0xFF
        self.mem.io[b+2] = (self.src_addr >> 16) & 0xFF
        self.mem.io[b+3] = (self.src_addr >> 24) & 0xFF
        self.mem.io[b+4] = self.dst_addr & 0xFF
        self.mem.io[b+5] = (self.dst_addr >> 8) & 0xFF
        self.mem.io[b+6] = (self.dst_addr >> 16) & 0xFF
        self.mem.io[b+7] = (self.dst_addr >> 24) & 0xFF
        self.mem.io[b+8] = self.count & 0xFF
        self.mem.io[b+9] = (self.count >> 8) & 0xFF
        self.mem.io[b+10] = self.control & 0xFF
        self.mem.io[b+11] = (self.control >> 8) & 0xFF

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
        # Wire FIFO empty triggers to DMA
        if apu:
            apu.fifo_a.attach_dma(self)
            apu.fifo_b.attach_dma(self)

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

    def _step_for(self, ctrl: int, width: int) -> int:
        return _DMA_OFFSET.get(ctrl, 0) * width

    def _do_transfer(self, ch: DMAChannel):
        """GBATEK §12.3: Control register bits (ENABLE=15, IRQ=14, Timing=12-13, etc.).
        
        GBATEK §12.4: HBlank DMA fires at start of HBlank, runs during visible period.
        GBATEK §12.4: VBlank DMA fires at start of VBlank.
        GBATEK §12.5: ENABLE bit cleared on completion for non-repeat transfers.
        """
        if ch.busy:
            return

        ch.busy = True

        src_ctrl = ch.get_src_increment()
        dst_ctrl = ch.get_dst_increment()
        count = ch.get_count_value()
        transfer_size = ch.get_transfer_size()

        src_step = self._step_for(src_ctrl, transfer_size)
        dst_step = self._step_for(dst_ctrl, transfer_size)

        src = ch.src_addr
        dst = ch.dst_addr
        orig_dst = ch.dst_addr
        orig_src = ch.src_addr

        for _ in range(count):
            if transfer_size == 4:
                if src >= 0x02000000:
                    ch.latch = self.mem.read_u32(src)
                value = ch.latch
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
            else:
                if src >= 0x02000000:
                    ch.latch = self.mem.read_u16(src)
                    ch.latch = ch.latch | (ch.latch << 16)
                value = (ch.latch >> (8 * (dst & 2))) & 0xFFFF
                if dst == DMA.FIFO_A_ADDR and self._apu:
                    self._apu.fifo_a.write(value & 0xFF)
                    self._apu.fifo_a.write((value >> 8) & 0xFF)
                elif dst == DMA.FIFO_B_ADDR and self._apu:
                    self._apu.fifo_b.write(value & 0xFF)
                    self._apu.fifo_b.write((value >> 8) & 0xFF)
                else:
                    self.mem.write_u16(dst, value)

            src += src_step
            dst += dst_step

        # GBATEK §12.5: Address writeback after transfer completes
        # DestControl=3 (increment/reload) resets DAD to original on repeat
        if ch.is_repeat() and dst_ctrl == 3:
            ch.dst_addr = orig_dst
        else:
            ch.dst_addr = dst
        if ch.is_repeat() and src_ctrl == 3:
            ch.src_addr = orig_src
        else:
            ch.src_addr = src

        if ch.is_repeat():
            ch.count = ch._orig_count if ch._orig_count else ch.get_count_value()
            if ch.is_repeat() and src_ctrl == 3:
                ch.src_addr = orig_src
            if ch.is_repeat() and dst_ctrl == 3:
                ch.dst_addr = orig_dst
        else:
            # GBATEK §12.3: ENABLE bit (15) cleared on completion (non-repeat)
            ch.control &= ~DMA_ENABLE
            ch.enabled = False
            ch.count = 0

        ch.write_to_memory()

        ch.busy = False
        ch.pending = False

        if ch.irq_enabled and self._interrupts:
            self._interrupts.dma_irq(ch.channel_id)

    def step(self):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_immediate():
                if ch.pending:
                    ch.pending = False
                    self._do_transfer(ch)

    def _do_transfer_single(self, ch: DMAChannel):
        """GBATEK §12.4: HBlank/VBlank DMA single-unit transfer per trigger.
        
        Repeat bit enables repeated transfers; channel stays enabled until
        count exhausted, then reloads (DestControl=3) or disables.
        """
        if ch.busy:
            return
        ch.busy = True

        src_ctrl = ch.get_src_increment()
        dst_ctrl = ch.get_dst_increment()
        transfer_size = ch.get_transfer_size()
        src_step = self._step_for(src_ctrl, transfer_size)
        dst_step = self._step_for(dst_ctrl, transfer_size)

        src = ch.src_addr
        dst = ch.dst_addr

        if transfer_size == 4:
            if src >= 0x02000000:
                ch.latch = self.mem.read_u32(src)
            value = ch.latch
            if dst == DMA.FIFO_A_ADDR and self._apu:
                self._apu.fifo_a.write(value & 0xFF)
                self._apu.fifo_a.write((value >> 8) & 0xFF)
                self._apu.fifo_a.write((value >> 16) & 0xFF)
                self._apu.fifo_a.write((value >> 24) & 0xFF)
            elif dst == DMA.FIFO_B_ADDR and self._apu:
                self._apu.fifo_b.write(value & 0xFF)
                self._apu.fifo_b.write((value >> 8) & 0xFF)
                self._apu.fifo_b.write((value >> 16) & 0xFF)
                self._apu.fifo_b.write((value >> 24) & 0xFF)
            else:
                self.mem.write_u32(dst, value)
        else:
            if src >= 0x02000000:
                ch.latch = self.mem.read_u16(src)
                ch.latch = ch.latch | (ch.latch << 16)
            value = (ch.latch >> (8 * (dst & 2))) & 0xFFFF
            if dst == DMA.FIFO_A_ADDR and self._apu:
                self._apu.fifo_a.write(value & 0xFF)
                self._apu.fifo_a.write((value >> 8) & 0xFF)
            elif dst == DMA.FIFO_B_ADDR and self._apu:
                self._apu.fifo_b.write(value & 0xFF)
                self._apu.fifo_b.write((value >> 8) & 0xFF)
            else:
                self.mem.write_u16(dst, value)
        ch.src_addr = src + src_step
        ch.dst_addr = dst + dst_step
        ch.count = max(0, ch.count - 1)

        if ch.count == 0:
            if ch.is_repeat():
                ch.count = ch._orig_count if ch._orig_count else 0x10000
                if dst_ctrl == 3:
                    ch.dst_addr = ch._orig_dst
                if src_ctrl == 3:
                    ch.src_addr = ch._orig_src
            else:
                ch.control &= ~DMA_ENABLE
                ch.enabled = False
                ch._write_control_to_memory()

        ch.busy = False
        ch.pending = False

        if ch.irq_enabled and self._interrupts:
            self._interrupts.dma_irq(ch.channel_id)

    def vblank_fire(self):
        """GBATEK §12.4: VBlank DMA fires at start of VBlank (timing=01)."""
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_vblank():
                self._do_transfer(ch)

    def hblank_fire(self, vcount: int = 0):
        """GBATEK §12.4: HBlank DMA fires at start of HBlank (timing=10).
        
        Transfer runs during visible period of next scanline.
        """
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_hblank():
                self._do_transfer(ch)

    def custom_fire(self):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_special() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def timer_trigger_fire(self, timer_id: int):
        """GBATEK §12.4: Timer-triggered DMA (timing=11, special mode).
        
        Timer overflow triggers full-count burst for channels with
        timing mode 3 (special) matched to the timer ID.
        """
        if timer_id < 0 or timer_id > 3:
            return
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            # Timer-triggered DMA uses timing mode 3 (special)
            # Only channels 0-3 can be triggered by timers 0-3
            if ch.is_special() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def fifo_a_empty_fire(self):
        """GBATEK §12.4: DMA1 special mode — FIFO A empty trigger."""
        ch = self.channels[1]
        ch.read_from_memory()
        if ch.enabled and not ch.busy and ch.is_special() and ch.pending:
            self._do_transfer(ch)
            ch.pending = False

    def fifo_b_empty_fire(self):
        """GBATEK §12.4: DMA2 special mode — FIFO B empty trigger."""
        ch = self.channels[2]
        ch.read_from_memory()
        if ch.enabled and not ch.busy and ch.is_special() and ch.pending:
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
