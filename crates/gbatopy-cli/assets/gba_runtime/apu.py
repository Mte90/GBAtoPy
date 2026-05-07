"""GBA APU (Audio Processing Unit)"""

import pygame
import threading
from collections import deque


class AudioOutput:
    """Pygame audio output handler"""

    def __init__(self, sample_rate=44100, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.buffer = deque(maxlen=sample_rate // 60)  # 1 frame of audio
        self.running = False
        self.thread = None

    def start(self):
        """Start audio playback thread"""
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=2, buffer=512)

        self.running = True
        self.thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop audio playback"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _playback_loop(self):
        """Background thread to feed pygame mixer"""
        while self.running:
            if len(self.buffer) > 0:
                samples = list(self.buffer)[:1024]
                if samples:
                    audio_data = bytes([s & 0xFF for s in samples])
                    pygame.mixer.Sound(audio_data).play()
            pygame.time.wait(10)

    def add_samples(self, samples):
        """Add audio samples to buffer"""
        for sample in samples:
            self.buffer.append(sample & 0xFFFF)


class SquareWaveChannel:
    """Square wave sound channel (CH1/CH2)"""

    # Duty cycles: 12.5%, 25%, 50%, 75%
    DUTY_PATTERNS = [
        0b00000001,  # 12.5%
        0b00000011,  # 25%
        0b00001111,  # 50%
        0b11111111,  # 75%
    ]

    def __init__(self):
        self.enabled = False
        self.volume = 0
        self.frequency = 0
        self.duty_cycle = 0  # 0-3
        self.envelope = 0  # Initial volume
        self.envelope_steps = 0
        self.envelope_increase = False
        self.length = 0
        self.length_enable = False
        self.counter = 0
        self.timer = 0
        self.timer_period = 0
        self.sweep_shift = 0
        self.sweep_decrease = False
        self.sweep_steps = 0

    def step(self, sample_rate: int, base_freq: int = 131072) -> int:
        """Generate one sample. Returns volume level (0-15)."""
        if not self.enabled or self.volume == 0:
            return 0

        # Calculate timer period from frequency
        # Timer increments at 1 MHz, frequency = 1MHz / (2048 - freq)
        if self.frequency > 0:
            self.timer_period = (2048 - self.frequency) * 4
        else:
            self.timer_period = 0x7FF * 4

        # Advance timer
        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            # Toggle output based on duty pattern
            duty = self.DUTY_PATTERNS[self.duty_cycle]
            bit_pos = self.counter % 8
            if duty & (1 << bit_pos):
                return self.volume
            else:
                return 0

        return 0

    def trigger(self):
        """Trigger the channel (key on)"""
        self.counter = 0
        self.timer = 0
        self.enabled = True


class WaveChannel:
    """Wave playback channel (CH3)"""

    def __init__(self):
        self.enabled = False
        self.volume = 0  # 0-15 (or 0-3 for special modes)
        self.frequency = 0
        self.wave_ram = [0] * 32  # 16 4-bit nibbles = 32 bytes
        self.wave_bank = 0  # 0 or 1
        self.length = 0
        self.length_enable = False
        self.timer = 0
        self.timer_period = 0
        self.counter = 0
        self.output_nibble = 0
        self.format_8bit = False

    def step(self, sample_rate: int, base_freq: int = 131072) -> int:
        """Generate one sample."""
        if not self.enabled or self.volume == 0:
            return 0

        if self.frequency > 0:
            self.timer_period = (2048 - self.frequency) * 4

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            # Read from wave RAM
            nibble_index = self.counter % 64  # 32 bytes * 2 nibbles
            byte_index = nibble_index // 2
            wave_value = self.wave_ram[byte_index]

            if nibble_index % 2 == 0:
                # Lower nibble
                sample = wave_value & 0x0F
            else:
                # Upper nibble
                sample = (wave_value >> 4) & 0x0F

            # Apply volume
            if self.format_8bit:
                return sample  # 8-bit mode
            else:
                return (sample * self.volume) // 15

        return 0

    def trigger(self):
        """Trigger the channel"""
        self.counter = 0
        self.timer = 0
        self.enabled = True


class NoiseChannel:
    """Noise channel (CH4)"""

    # LFSR tap positions for different widths
    STAGES_15BIT = 14
    STAGES_7BIT = 6

    def __init__(self):
        self.enabled = False
        self.volume = 0
        self.envelope = 0
        self.envelope_steps = 0
        self.envelope_increase = False
        self.length = 0
        self.length_enable = False
        self.lfsr = 0x7FFF  # 15-bit LFSR starts all 1s
        self.width_7bit = False
        self.clock_shift = 0
        self.clock_divider = 0
        self.timer = 0
        self.timer_period = 0

    def step(self, sample_rate: int, base_freq: int = 131072) -> int:
        """Generate one sample."""
        if not self.enabled or self.volume == 0:
            return 0

        # Calculate timer period
        # Noise frequency = base / (2^(shift+1)) / divider
        divisor = max(1, self.clock_divider * 2)
        self.timer_period = (1 << (self.clock_shift + 1)) * divisor

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0

            # LFSR operation: tap bits and XOR
            if self.width_7bit:
                # 7-bit mode
                bit0 = self.lfsr & 1
                bit1 = (self.lfsr >> 1) & 1
                new_bit = bit0 ^ bit1
                self.lfsr = (self.lfsr >> 1) | (new_bit << 6)
                # Keep only 7 bits
                self.lfsr &= 0x7F
            else:
                # 15-bit mode
                bit0 = self.lfsr & 1
                bit14 = (self.lfsr >> 14) & 1
                new_bit = bit0 ^ bit14
                self.lfsr = (self.lfsr >> 1) | (new_bit << 14)

            # Output is the XOR result inverted
            if (self.lfsr & 1) == 0:
                return self.volume

        return 0

    def trigger(self):
        """Trigger the channel"""
        self.lfsr = 0x7FFF
        self.timer = 0
        self.enabled = True


class FIFO:
    """Direct Sound FIFO buffer for DMA audio transfers

    The GBA has two FIFO buffers (A and B) used for streaming audio data
    from ROM via DMA. Each FIFO can hold up to 8 bytes and is used for
    direct sound output from channels 1/2 (FIFO A) and channels 3/4 (FIFO B).
    """

    # Maximum FIFO depth (hardware limit)
    MAX_FIFO_SIZE = 8

    def __init__(self):
        self.data = deque()  # Queue of 8-bit samples (using deque for efficiency)
        self.max_size = self.MAX_FIFO_SIZE
        self.timer = 0
        self.timer_period = 0  # Set by DMA
        self.enabled = False
        self.volume_left = 0
        self.volume_right = 0
        self.priority = 0

    @property
    def size(self) -> int:
        """Current number of bytes in FIFO"""
        return len(self.data)

    @property
    def is_empty(self) -> bool:
        """Check if FIFO is empty"""
        return len(self.data) == 0

    @property
    def is_full(self) -> bool:
        """Check if FIFO is full"""
        return len(self.data) >= self.max_size

    def write(self, value: int):
        """Write a byte to FIFO (only if space available)"""
        if len(self.data) < self.max_size:
            self.data.append(value & 0xFF)

    def read(self) -> int:
        """Read a byte from FIFO (FIFO pops from front)"""
        if self.data:
            return self.data.popleft()
        return 0

    def peek(self) -> int:
        """Peek at next byte without removing it"""
        if self.data:
            return self.data[0]
        return 0

    def step(self, sample_rate: int) -> int:
        """Generate one sample from FIFO data."""
        if not self.enabled or not self.data:
            return 0

        # Timer controls how fast we consume samples
        # In real hardware this is controlled by DMA
        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            return self.read() >> 4  # Scale to 4-bit volume

        return 0

    def clear(self):
        """Clear the FIFO"""
        self.data.clear()


class APU:
    """GBA Audio Processing Unit"""

    # Register addresses
    REG_SOUND1CNT_L = 0x04000060  # Sweep
    REG_SOUND1CNT_H = 0x04000062  # Duty/Length
    REG_SOUND1CNT_X = 0x04000064  # Frequency/Envelope

    REG_SOUND2CNT_L = 0x04000068  # Duty/Length
    REG_SOUND2CNT_H = 0x0400006A  # Volume/Envelope
    REG_SOUND2CNT_X = 0x0400006C  # Frequency

    REG_SOUND3CNT_L = 0x04000070  # Wave bank/on/off
    REG_SOUND3CNT_H = 0x04000072  # Length
    REG_SOUND3CNT_X = 0x04000074  # Volume/Frequency

    REG_SOUND4CNT_L = 0x04000078  # Length
    REG_SOUND4CNT_H = 0x0400007A  # Volume/Envelope

    REG_SOUNDCNT_L = 0x04000080  # Master volume/ena
    REG_SOUNDCNT_H = 0x04000082  # Direct Sound A
    REG_SOUNDCNT_X = 0x04000084  # Direct Sound B

    REG_FIFO_A = 0x040000A0
    REG_FIFO_B = 0x040000A4

    REG_WAVE_RAM = 0x04000090

    # APU DMA (Audio Control Block) register addresses: 0x0400004E-0x0400005F
    REG_DMDSNDCTRL = 0x0400004E  # DMA/FIFO control
    REG_DMDSNDREPEAT = 0x04000050  # DMA/FIFO repeat mode
    REG_DMDSNDCOUNT = 0x04000052  # DMA/FIFO sample count
    REG_ACB_SOUND1 = 0x04000054  # Audio control block - ch1
    REG_ACB_SOUND2 = 0x04000056  # Audio control block - ch2
    REG_ACB_SOUND3 = 0x04000058  # Audio control block - ch3
    REG_ACB_SOUND4 = 0x0400005A  # Audio control block - ch4

    # DMA Channel 1 (Channel 1 Square Wave) registers: 0x040000B0-0x040000BF
    REG_D1SAD = 0x040000B0  # DMA 1 Source Address
    REG_D1DAD = 0x040000B4  # DMA 1 Destination Address (FIFO A: 0x040000A0)
    REG_D1CNT_L = 0x040000B8  # DMA 1 Transfer Count (Lower 16 bits)
    REG_D1CNT_H = 0x040000BA  # DMA 1 Control / Count High

    # DMA Channel 2 registers: 0x040000C0-0x040000CF
    REG_D2SAD = 0x040000C0  # DMA 2 Source Address
    REG_D2DAD = 0x040000C4  # DMA 2 Destination Address (FIFO B: 0x040000A4)
    REG_D2CNT_L = 0x040000C8  # DMA 2 Transfer Count
    REG_D2CNT_H = 0x040000CA  # DMA 2 Control / Count High

    # Sample rate (1 MHz base / 4 for audio)
    SAMPLE_RATE = 262144

    def __init__(self):
        # Sound channels
        self.ch1 = SquareWaveChannel()
        self.ch2 = SquareWaveChannel()
        self.ch3 = WaveChannel()
        self.ch4 = NoiseChannel()

        # FIFO channels
        self.fifo_a = FIFO()
        self.fifo_b = FIFO()

        # Wave RAM (2 banks of 16 bytes each)
        self.wave_ram = [[0] * 16, [0] * 16]
        self.wave_bank = 0

        self.master_volume_left = 0
        self.master_volume_right = 0
        self.ch1_enabled = False
        self.ch2_enabled = False
        self.ch3_enabled = False
        self.ch4_enabled = False
        self.sample_counter = 0

        self._audio_output = None

        # APU DMA (Audio Control Block) state
        self.dma_enabled = False
        self.dma_block_counter = 0  # ACBU - block counter
        self.dma_block_selector = 0  # ACBS - block selector
        self.dma_block_descriptor = 0  # ACBD - block descriptor
        self.dma_control = 0  # DMDSNDCTRL
        self.dma_repeat = 0  # DMDSNDREPEAT
        self.dma_count = 0  # DMDSNDCOUNT

        # Channel 1 DMA (Square Wave) registers: 0x040000B0-0x040000BF
        self.d1sa = 0  # Source Address
        self.d1da = 0  # Destination Address (FIFO A at 0x040000A0)
        self.d1rl = 0  # Transfer Count (Repeat Length)
        self.d1cr = 0  # Control Register

        # Channel 2 DMA registers: 0x040000C0-0x040000CF
        self.d2sa = 0
        self.d2da = 0
        self.d2rl = 0
        self.d2cr = 0

        self._mem = None

    def attach_memory(self, mem):
        """Attach memory interface for DMA transfers"""
        self._mem = mem

    def start(self):
        if self._audio_output is None:
            self._audio_output = AudioOutput()
        self._audio_output.start()

    def write_register(self, addr: int, value: int):
        """Handle MMIO writes to sound registers"""
        # Check APU DMA range first (0x0400004E-0x0400005F)
        if 0x0400004E <= addr <= 0x0400005F:
            reg = addr - 0x0400004E
            self._write_apu_dma(reg, value)
            return

        if self.REG_SOUND1CNT_L <= addr <= 0x04000061:
            # CH1 Sweep control
            reg = addr - self.REG_SOUND1CNT_L
            self._write_ch1_sweep(reg, value)
        elif self.REG_SOUND1CNT_H <= addr <= 0x04000065:
            # CH1 Duty/Length/Frequency
            reg = addr - self.REG_SOUND1CNT_H
            self._write_ch1_control(reg, value)
        elif self.REG_SOUND2CNT_L <= addr <= 0x0400006D:
            # CH2 control
            reg = addr - self.REG_SOUND2CNT_L
            self._write_ch2_control(reg, value)
        elif self.REG_SOUND3CNT_L <= addr <= 0x04000075:
            # CH3 control
            reg = addr - self.REG_SOUND3CNT_L
            self._write_ch3_control(reg, value)
        elif self.REG_SOUND4CNT_L <= addr <= 0x0400007B:
            # CH4 control
            reg = addr - self.REG_SOUND4CNT_L
            self._write_ch4_control(reg, value)
        elif self.REG_SOUNDCNT_L <= addr <= 0x04000085:
            # Master sound control
            reg = addr - self.REG_SOUNDCNT_L
            self._write_sound_control(reg, value)
        elif self.REG_FIFO_A <= addr <= 0x040000A3:
            # FIFO A write
            self._write_fifo_a(addr, value)
        elif self.REG_FIFO_B <= addr <= 0x040000A7:
            # FIFO B write
            self._write_fifo_b(addr, value)
        elif self.REG_WAVE_RAM <= addr <= 0x0400009F:
            # Wave RAM
            self._write_wave_ram(addr, value)
        elif self.REG_D1SAD <= addr <= 0x040000BF:
            # DMA Channel 1 registers (0x040000B0-0x040000BF)
            reg = addr - self.REG_D1SAD
            self._write_dma_ch1(reg, value)
        elif self.REG_D2SAD <= addr <= 0x040000CF:
            # DMA Channel 2 registers (0x040000C0-0x040000CF)
            reg = addr - self.REG_D2SAD
            self._write_dma_ch2(reg, value)

    def _write_ch1_sweep(self, reg: int, value: int):
        """Write to CH1 sweep registers"""
        if reg == 0:  # SOUND1CNT_L
            self.ch1.sweep_shift = (value >> 4) & 0x07
            self.ch1.sweep_decrease = bool(value & 0x08)
            self.ch1.sweep_steps = value & 0x07

    def _write_ch1_control(self, reg: int, value: int):
        """Write to CH1 control registers"""
        if reg == 0:  # SOUND1CNT_H - duty/len
            self.ch1.duty_cycle = (value >> 6) & 0x03
            self.ch1.length = value & 0x3F
        elif reg == 2:  # SOUND1CNT_X - freq/env
            # Frequency is lower 11 bits
            self.ch1.frequency = value & 0x7FF
            # Envelope
            self.ch1.envelope = (value >> 12) & 0x0F
            self.ch1.envelope_steps = (value >> 8) & 0x07
            self.ch1.envelope_increase = bool(value & 0x0800)
            # Trigger
            if value & 0x8000:
                self.ch1.trigger()

    def _write_ch2_control(self, reg: int, value: int):
        """Write to CH2 control registers"""
        if reg == 0:  # SOUND2CNT_L
            self.ch2.duty_cycle = (value >> 6) & 0x03
            self.ch2.length = value & 0x3F
        elif reg == 2:  # SOUND2CNT_H
            self.ch2.envelope = (value >> 12) & 0x0F
            self.ch2.envelope_steps = (value >> 8) & 0x07
            self.ch2.envelope_increase = bool(value & 0x0800)
        elif reg == 4:  # SOUND2CNT_X
            self.ch2.frequency = value & 0x7FF
            if value & 0x8000:
                self.ch2.trigger()

    def _write_ch3_control(self, reg: int, value: int):
        """Write to CH3 control registers"""
        if reg == 0:  # SOUND3CNT_L
            self.ch3.wave_bank = (value >> 5) & 0x01
            self.ch3.enabled = bool(value & 0x80)
        elif reg == 2:  # SOUND3CNT_H
            self.ch3.length = value & 0xFF
        elif reg == 4:  # SOUND3CNT_X
            self.ch3.volume = (value >> 8) & 0x0F
            self.ch3.format_8bit = bool(value & 0x0400)
            self.ch3.frequency = value & 0x3FF
            if value & 0x8000:
                self.ch3.trigger()

    def _write_ch4_control(self, reg: int, value: int):
        """Write to CH4 control registers"""
        if reg == 0:  # SOUND4CNT_L
            self.ch4.length = value & 0x3F
        elif reg == 2:  # SOUND4CNT_H
            self.ch4.envelope = (value >> 12) & 0x0F
            self.ch4.envelope_steps = (value >> 8) & 0x07
            self.ch4.envelope_increase = bool(value & 0x0800)
        elif reg == 4:  # (address not standard, but CH4 doesn't have freq)
            self.ch4.clock_shift = (value >> 4) & 0x0F
            self.ch4.clock_divider = value & 0x07
            self.ch4.width_7bit = bool(value & 0x08)
            if value & 0x8000:
                self.ch4.trigger()

    def _write_sound_control(self, reg: int, value: int):
        """Write to master sound control"""
        if reg == 0:  # SOUNDCNT_L
            self.master_volume_right = (value >> 4) & 0x07
            self.master_volume_left = value & 0x07
        elif reg == 2:  # SOUNDCNT_H - Direct Sound A
            self.fifo_a.volume_right = (value >> 4) & 0x0F
            self.fifo_a.volume_left = value & 0x0F
            self.fifo_a.enabled = bool(value & 0x0200)
            self.ch1_enabled = bool(value & 0x0001)
            self.ch2_enabled = bool(value & 0x0002)
        elif reg == 4:  # SOUNDCNT_X - Direct Sound B
            self.fifo_b.volume_right = (value >> 4) & 0x0F
            self.fifo_b.volume_left = value & 0x0F
            self.fifo_b.enabled = bool(value & 0x0200)
            self.ch3_enabled = bool(value & 0x0004)
            self.ch4_enabled = bool(value & 0x0008)

    def _write_fifo_a(self, addr: int, value: int):
        """Write to FIFO A"""
        # Writing any byte to FIFO A pushes it
        self.fifo_a.write(value & 0xFF)

    def _write_fifo_b(self, addr: int, value: int):
        """Write to FIFO B"""
        self.fifo_b.write(value & 0xFF)

    def _write_wave_ram(self, addr: int, value: int):
        """Write to wave RAM"""
        offset = addr - self.REG_WAVE_RAM
        bank = self.wave_bank
        self.wave_ram[bank][offset % 16] = value & 0xFF
        self.ch3.wave_ram = self.wave_ram[bank]

    def _write_apu_dma(self, reg: int, value: int):
        """Write to APU DMA registers (0x0400004E-0x0400005F)"""
        if reg == 0:  # DMDSNDCTRL
            self.dma_control = value
            self.dma_enabled = bool(value & 0x0001)
        elif reg == 2:  # DMDSNDREPEAT
            self.dma_repeat = value
        elif reg == 4:  # DMDSNDCOUNT
            self.dma_count = value
        elif reg == 6:  # ACB sound1 - block address
            self.dma_block_descriptor = value
        elif reg == 8:  # ACB sound2
            self.dma_block_counter = value

    def _write_dma_ch1(self, reg: int, value: int):
        """Write to DMA Channel 1 (Square Wave) registers"""
        if reg == 0:  # D1SAD - Source Address
            self.d1sa = value
        elif reg == 4:  # D1DAD - Destination Address
            self.d1da = value
        elif reg == 8:  # D1RL - Repeat Length (Count High)
            self.d1rl = value
        elif reg == 12:  # D1CNT_H - Control High
            self.d1cr = value & 0xFFFF

    def _write_dma_ch2(self, reg: int, value: int):
        """Write to DMA Channel 2 registers"""
        if reg == 0:  # D2SAD - Source Address
            self.d2sa = value
        elif reg == 4:  # D2DAD - Destination Address
            self.d2da = value
        elif reg == 8:  # D2RL - Repeat Length
            self.d2rl = value
        elif reg == 12:  # D2CNT_H - Control High
            self.d2cr = value & 0xFFFF

    def dma_transfer(self, channel: int, count: int):
        """Perform DMA transfer from ROM to audio buffer"""
        if self._mem is None:
            return
        rom_base = 0x08000000
        for i in range(count):
            addr = rom_base + (channel * 0x1000) + (i * 4)
            sample = self._mem.read_u32(addr) & 0xFF
            if channel == 0:
                self.fifo_a.write(sample)
            else:
                self.fifo_b.write(sample)

    def fifo_write(self, channel: int, sample: int):
        """Write a sample to the specified FIFO channel

        Args:
            channel: 0 for FIFO A, 1 for FIFO B
            sample: 8-bit audio sample
        """
        if channel == 0:
            self.fifo_a.write(sample)
        else:
            self.fifo_b.write(sample)

    def fifo_read(self, channel: int) -> int:
        """Read a sample from the specified FIFO channel

        Args:
            channel: 0 for FIFO A, 1 for FIFO B
        Returns:
            8-bit audio sample, or 0 if FIFO is empty
        """
        if channel == 0:
            return self.fifo_a.read()
        else:
            return self.fifo_b.read()

    def fifo_is_empty(self, channel: int) -> bool:
        """Check if the specified FIFO is empty

        Args:
            channel: 0 for FIFO A, 1 for FIFO B
        Returns:
            True if FIFO is empty, False otherwise
        """
        if channel == 0:
            return self.fifo_a.is_empty
        else:
            return self.fifo_b.is_empty

    def fifo_size(self, channel: int) -> int:
        """Get current size of the specified FIFO

        Args:
            channel: 0 for FIFO A, 1 for FIFO B
        Returns:
            Number of bytes currently in FIFO (0-8)
        """
        if channel == 0:
            return self.fifo_a.size
        else:
            return self.fifo_b.size

    def step(self):
        """Advance audio by one sample cycle"""
        # Generate samples from each active channel
        ch1_sample = self.ch1.step(self.SAMPLE_RATE) if self.ch1_enabled else 0
        ch2_sample = self.ch2.step(self.SAMPLE_RATE) if self.ch2_enabled else 0
        ch3_sample = self.ch3.step(self.SAMPLE_RATE) if self.ch3_enabled else 0
        ch4_sample = self.ch4.step(self.SAMPLE_RATE) if self.ch4_enabled else 0

        # FIFO samples (controlled by DMA in real hardware)
        fifo_a_sample = self.fifo_a.step(self.SAMPLE_RATE)
        fifo_b_sample = self.fifo_b.step(self.SAMPLE_RATE)

        self.sample_counter += 1

    def get_sample(self) -> int:
        """Return current mixed audio sample value (int)"""
        # Mix all channels
        mixed = 0

        if self.ch1_enabled:
            duty = SquareWaveChannel.DUTY_PATTERNS[self.ch1.duty_cycle]
            bit_pos = self.sample_counter % 8
            if duty & (1 << bit_pos):
                mixed += self.ch1.volume

        if self.ch2_enabled:
            duty = SquareWaveChannel.DUTY_PATTERNS[self.ch2.duty_cycle]
            bit_pos = self.sample_counter % 8
            if duty & (1 << bit_pos):
                mixed += self.ch2.volume

        if self.ch3_enabled and self.ch3.wave_ram:
            nibble_index = self.sample_counter % 64
            byte_index = nibble_index // 2
            wave_value = self.ch3.wave_ram[byte_index % 16]

            if nibble_index % 2 == 0:
                sample = wave_value & 0x0F
            else:
                sample = (wave_value >> 4) & 0x0F

            if self.ch3.format_8bit:
                mixed += sample
            else:
                mixed += (sample * self.ch3.volume) // 15

        # CH4 noise
        if self.ch4_enabled:
            divisor = max(1, self.ch4.clock_divider * 2)
            timer_period = (1 << (self.ch4.clock_shift + 1)) * divisor
            if self.sample_counter % timer_period == 0:
                # LFSR step
                if self.ch4.width_7bit:
                    bit0 = self.ch4.lfsr & 1
                    bit1 = (self.ch4.lfsr >> 1) & 1
                    new_bit = bit0 ^ bit1
                    self.ch4.lfsr = (self.ch4.lfsr >> 1) | (new_bit << 6)
                    self.ch4.lfsr &= 0x7F
                else:
                    bit0 = self.ch4.lfsr & 1
                    bit14 = (self.ch4.lfsr >> 14) & 1
                    new_bit = bit0 ^ bit14
                    self.ch4.lfsr = (self.ch4.lfsr >> 1) | (new_bit << 14)

        # Add FIFO samples
        if self.fifo_a.enabled and self.fifo_a.data:
            mixed += self.fifo_a.data[0] >> 4
        if self.fifo_b.enabled and self.fifo_b.data:
            mixed += self.fifo_b.data[0] >> 4

        # Apply master volume (simplified)
        master_vol = (self.master_volume_left + self.master_volume_right + 1) // 2
        mixed = (mixed * master_vol) // 7

        # Clamp to valid range
        return max(0, min(15, mixed))

    def read_register(self, addr: int) -> int:
        """Read from sound registers (for completeness)"""
        if self.REG_FIFO_A <= addr <= 0x040000A3:
            # FIFO A read
            return self.fifo_a.read() if self.fifo_a.data else 0
        elif self.REG_FIFO_B <= addr <= 0x040000A7:
            # FIFO B read
            return self.fifo_b.read() if self.fifo_b.data else 0
        elif self.REG_WAVE_RAM <= addr <= 0x0400009F:
            offset = addr - self.REG_WAVE_RAM
            return self.wave_ram[self.wave_bank][offset % 16]

        return 0
