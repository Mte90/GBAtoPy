"""GBA DMA Controller"""

from typing import List, Optional


# DMA Control Register Bits
DMA_ENABLE = 0x80000000
DMA_TIMING_MASK = 0x30000000
DMA_TIMING_IMMEDIATE = 0x30000000  # 0b11
DMA_TIMING_VBLANK = 0x20000000     # 0b10
DMA_TIMING_HBLANK = 0x10000000     # 0b01
DMA_TIMING_CUSTOM = 0x00000000
DMA3_TRIGGER_MASK = 0x0F000000
DMA3_TRIGGER_IMMEDIATE = 0x00000000
DMA3_TRIGGER_VBLANK = 0x01000000
DMA3_TRIGGER_HBLANK = 0x02000000
DMA3_TRIGGER_FIFO_A = 0x03000000
DMA3_TRIGGER_FIFO_B = 0x04000000

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

# MMIO Register Addresses
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
        self._irq_enabled: bool = False

    def attach_interrupts(self, interrupts):
        """Attach interrupt controller for DMA completion IRQs"""
        self._interrupts = interrupts

    @property
    def irq_enabled(self) -> bool:
        """Check if IRQ on completion is enabled (bit 14)"""
        return (self.control & 0x40000000) != 0

    def get_timing_bits(self) -> int:
        """Extract timing mode bits (bits 29-28)"""
        return self.control & DMA_TIMING_MASK

    def is_immediate(self) -> bool:
        """Check if timing is immediate (start right away)"""
        return self.get_timing_bits() == DMA_TIMING_IMMEDIATE

    def is_vblank(self) -> bool:
        """Check if timing is VBlank"""
        return self.get_timing_bits() == DMA_TIMING_VBLANK

    def is_hblank(self) -> bool:
        """Check if timing is HBlank"""
        return self.get_timing_bits() == DMA_TIMING_HBLANK

    def is_custom(self) -> bool:
        return self.get_timing_bits() == DMA_TIMING_CUSTOM

    def get_dma3_trigger_bits(self) -> int:
        if self.channel_id != 3:
            return 0
        return self.control & DMA3_TRIGGER_MASK

    def is_fifo_a_trigger(self) -> bool:
        if self.channel_id != 3:
            return False
        return self.get_dma3_trigger_bits() == DMA3_TRIGGER_FIFO_A

    def is_fifo_b_trigger(self) -> bool:
        if self.channel_id != 3:
            return False
        return self.get_dma3_trigger_bits() == DMA3_TRIGGER_FIFO_B

    def get_src_increment(self) -> int:
        """Get source increment mode (bits 21-20)"""
        return (self.control >> 20) & 0x3

    def get_dst_increment(self) -> int:
        """Get destination increment mode (bits 13-12)"""
        return (self.control >> 12) & 0x3

    def is_32bit(self) -> bool:
        """Check if transfer is 32-bit"""
        return (self.control & DMA_32BIT) != 0

    def is_repeat(self) -> bool:
        """Check if repeat mode is enabled"""
        return (self.control & DMA_REPEAT) != 0

    def get_transfer_size(self) -> int:
        """Get transfer size in bytes"""
        return 4 if self.is_32bit() else 2

    def read_from_memory(self):
        """Read DMA registers from memory"""
        base = 0x040000B0 + (self.channel_id * 0x10)
        self.src_addr = self.mem.read_u32(base)
        self.dst_addr = self.mem.read_u32(base + 4)
        self.count = self.mem.read_u32(base + 8)
        self.control = self.mem.read_u32(base + 12)
        self.enabled = (self.control & DMA_ENABLE) != 0

    def write_to_memory(self):
        """Write DMA registers to memory"""
        base = 0x040000B0 + (self.channel_id * 0x10)
        self.mem.write_u32(base, self.src_addr)
        self.mem.write_u32(base + 4, self.dst_addr)
        self.mem.write_u32(base + 8, self.count)
        self.mem.write_u32(base + 12, self.control)

    def get_count_value(self) -> int:
        """Get actual transfer count (0 = 0x10000 or 0x4000)"""
        if self.count == 0:
            return 0x10000 if self.is_32bit() else 0x4000
        return self.count


class DMA:
    """GBA DMA Controller with 4 channels"""
    
    # FIFO addresses for sound DMA
    FIFO_A_ADDR = 0x040000A0
    FIFO_B_ADDR = 0x040000A4
    
    def __init__(self):
        self.mem = None  # Set by attach_memory
        self._interrupts = None
        self._apu = None  # Set by attach_apu for FIFO support
        self.channels: List[DMAChannel] = [
            DMAChannel(0, None),
            DMAChannel(1, None),
            DMAChannel(2, None),
            DMAChannel(3, None),
        ]
        self._setup_mmio()

    def attach_memory(self, mem):
        """Attach memory for DMA transfers"""
        self.mem = mem
        for ch in self.channels:
            ch.mem = mem

    def attach_apu(self, apu):
        """Attach APU for FIFO trigger support"""
        self._apu = apu

    def fifo_a_is_empty(self) -> bool:
        """Check if FIFO A is empty (trigger condition)"""
        if self._apu is None:
            return False
        return len(self._apu.fifo_a.data) == 0

    def fifo_b_is_empty(self) -> bool:
        """Check if FIFO B is empty (trigger condition)"""
        if self._apu is None:
            return False
        return len(self._apu.fifo_b.data) == 0

    def attach_interrupts(self, interrupts):
        """Attach interrupt controller for DMA completion IRQs"""
        self._interrupts = interrupts
        for ch in self.channels:
            ch.attach_interrupts(interrupts)

    def _setup_mmio(self):
        """Setup MMIO write handlers"""
        pass  # Handled in memory.py directly

    def _make_mmio_handler(self, channel: int):
        """Create MMIO handler for channel control register"""
        def handler(addr: int, value: int):
            ch = self.channels[channel]
            ch.control = value
            ch.enabled = (value & DMA_ENABLE) != 0
            
            # Immediate DMA starts immediately when enabled
            if ch.enabled and ch.is_immediate():
                ch.pending = True
                
            # Custom trigger (VCount/timer) starts when trigger fires
            if ch.enabled and ch.is_custom():
                ch.pending = True

        return handler

    def start_transfer(self, channel: int):
        """Manually start a DMA transfer"""
        if channel < 0 or channel > 3:
            return

        ch = self.channels[channel]
        ch.read_from_memory()

        if not ch.enabled:
            return

        self._do_transfer(ch)

    def _do_transfer(self, ch: DMAChannel):
        """Execute DMA transfer for a channel"""
        if ch.busy:
            return

        ch.busy = True

        src_inc = ch.get_src_increment()
        dst_inc = ch.get_dst_increment()
        count = ch.get_count_value()
        transfer_size = ch.get_transfer_size()

        src = ch.src_addr
        dst = ch.dst_addr

        # Perform the actual memory transfer
        for _ in range(count):
            if transfer_size == 4:
                value = self.mem.read_u32(src)
                self.mem.write_u32(dst, value)
                src += 4
                dst += 4
            else:  # 16-bit
                value = self.mem.read_u16(src)
                self.mem.write_u16(dst, value)
                src += 2
                dst += 2

        # Update addresses based on increment mode
        ch.src_addr = self._adjust_address(ch.src_addr, src_inc, count * transfer_size)
        ch.dst_addr = self._adjust_address(ch.dst_addr, dst_inc, count * transfer_size)

        # Handle repeat mode
        if ch.is_repeat():
            ch.count = ch.get_count_value()  # Reload count
        else:
            # Disable DMA after transfer (clear enable bit)
            ch.control &= ~DMA_ENABLE
            ch.enabled = False

        # Write back updated values
        ch.write_to_memory()
        
        ch.busy = False
        ch.pending = False  # Clear pending flag after transfer completes
        
        # Fire DMA completion interrupt if enabled
        if ch.irq_enabled and self._interrupts:
            self._interrupts.dma_irq(ch.channel_id)

    def _adjust_address(self, addr: int, increment_mode: int, transfer_bytes: int) -> int:
        """Adjust address based on increment mode"""
        if increment_mode == 0:  # Increment
            return addr + transfer_bytes
        elif increment_mode == 1:  # Decrement
            return addr - transfer_bytes
        else:  # Fixed (2) or reserved (3)
            return addr

    def step(self):
        """Process DMA step (called every frame for immediate DMA)"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            # Handle immediate DMA (should have already fired, but check pending)
            if ch.is_immediate():
                if ch.pending:
                    ch.pending = False
                    self._do_transfer(ch)

    def vblank_fire(self):
        """Process VBlank-triggered DMA transfers"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_vblank():
                self._do_transfer(ch)
                ch.pending = False

    def hblank_fire(self):
        """Process HBlank-triggered DMA transfers"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_hblank():
                self._do_transfer(ch)
                ch.pending = False

    def custom_fire(self):
        """Process custom-triggered DMA (VCount/timer)"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_custom() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def timer_trigger(self, timer_index: int):
        """Trigger DMA from timer overflow (DMA1/2 only for sound)"""
        # DMA channel 1 and 2 can be triggered by timer
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            # Custom timing means triggered by VCount or timer
            if ch.is_custom() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False
    
    def attach_apu(self, apu):
        """Attach APU for FIFO support - DMA1/2 write to FIFO A/B for audio"""
        self._apu = apu
    
    def _fifo_dma_transfer(self, channel: int):
        """
        DMA to FIFO transfer for audio channels 1 and 2.
        
        GBA DMA FIFO behavior:
        - DMA1 writes to FIFO A (0x040000A0) - Square wave channel
        - DMA2 writes to FIFO B (0x040000A4) - Triangle/noise channel
        - 16-bit DMA count transfers 16-bit values (samples)
        - DMA reads 16-bit samples from WAVE_RAM (0x04000090)
        """
        if channel < 0 or channel > 2:
            return
        
        ch = self.channels[channel]
        
        # Get DMA timer period from SOUNDCNT register (bits 2-5)
        timer_period = ch.timer_period if ch.timer_period > 0 else 0
        
        # Read 16-bit samples from WAVE_RAM and write to FIFO
        fifo_addr = self.FIFO_A_ADDR if channel == 1 else self.FIFO_B_ADDR
        base = (channel - 1) * 0x200  # WAVE_RAM: CH1=0x0, CH2=0x200
        
        for _ in range(ch.get_count_value()):
            if not ch.enabled or ch.busy:
                break
            
            # Read 16-bit sample from WAVE_RAM (little-endian)
            sample = self.mem.read_u16(base)
            
            # Write to FIFO (16-bit read becomes 8-bit byte for FIFO)
            if sample & 0x8000:  # MSB indicates next byte is high byte
                self.mem.write_u8(fifo_addr, (sample & 0xFF) >> 4)  # Scale by 1/16
                fifo_addr += 1
                self.mem.write_u8(fifo_addr, (sample >> 12) & 0x0F)  # Scale high byte
                fifo_addr += 1
            else:
                self.mem.write_u8(fifo_addr, (sample >> 4) & 0x0F)  # Scale by 1/16
                fifo_addr += 1
        
        ch.busy = False
    
    def fifo_a_step(self):
        """Step FIFO A - processes audio samples from DMA"""
        if not self._apu:
            return
        self._apu.fifo_a.timer += 1
        
        if self._apu.fifo_a.timer >= self._apu.fifo_a.timer_period:
            self._apu.fifo_a.timer = 0
            self._apu.fifo_a.read()  # Generate sample for audio channel

    def fifo_a_empty_fire(self):
        """Process FIFO A empty trigger for DMA3"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_fifo_a_trigger() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def fifo_b_empty_fire(self):
        """Process FIFO B empty trigger for DMA3"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_fifo_b_trigger() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def _fifo_dma_write(self, channel: int, fifo_addr: int):
        """DMA write to FIFO A/B for audio data (16-bit to 8-bit scaling)"""
        if channel < 0 or channel > 2:
            return
        
        ch = self.channels[channel]
        if not ch.enabled or ch.busy:
            return
        
        # Get timer period for this DMA channel (used for audio timing)
        # In real hardware, SOUNDCNT_H bits 2-5 control timer period
        period = ch.timer_period if ch.timer_period > 0 else 0
        ch.timer_period = period
        
        # Transfer from source to FIFO
        count = ch.get_count_value()
        src = ch.src_addr
        
        for _ in range(count):
            if not ch.enabled or ch.busy:
                break
            
            # Read 16-bit sample (little-endian)
            sample = self.mem.read_u16(src)
            
            # Write to FIFO: scale 16-bit sample to 8-bit (shift right by 4)
            # GBA DMA FIFO takes 8-bit values for audio
            scaled = (sample >> 4) & 0x0F  # Scale by 1/16
            self.mem.write_u8(fifo_addr, scaled)
            src += 2
            fifo_addr += 1
        
        # Mark busy/done
        if ch.control & DMA_ENABLE:  # Still enabled
            ch.busy = True
        else:
            ch.busy = False

    def get_channel(self, channel: int) -> Optional[DMAChannel]:
        """Get DMA channel by index"""
        if 0 <= channel <= 3:
            return self.channels[channel]
        return None


def clear_dma_pending(dma_instance):
    """Clear pending flags on all DMA channels"""
    for ch in dma_instance.channels:
        ch.pending = False