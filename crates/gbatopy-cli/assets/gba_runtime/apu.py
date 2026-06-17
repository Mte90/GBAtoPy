"""GBA APU (Audio Processing Unit) - Optimized Implementation"""

import pygame
import threading
from collections import deque
import array

# Optional Numba JIT support
try:
    from numba import njit
    numba_available = True
except ImportError:
    numba_available = False
    def njit(f=None, **kwargs):
        return f if f else lambda x: x


class SquareWaveChannel:
    """Square wave sound channel (CH1/CH2)"""

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
        self.duty_cycle = 0
        self.envelope_volume = 0
        self.envelope_steps = 0
        self.envelope_increase = False
        self.length = 0
        self.length_enable = False
        self.length_counter = 0
        self.envelope_counter = 0
        self.envelope_volume_current = 0
        self.sweep_shift = 0
        self.sweep_decrease = False
        self.sweep_steps = 0
        self.sweep_counter = 0
        self.timer = 0
        self.timer_period = 0
        self.output_bit = 0

    def step(self, sample_rate: int) -> int:
        """Generate one sample. Returns volume level (0-15)."""
        if not self.enabled:
            return 0

        # Length counter
        if self.length_enable and self.length > 0:
            self.length_counter += 1
            if self.length_counter >= (256 - self.length):
                self.enabled = False
                return 0

        # Envelope
        if self.envelope_steps > 0:
            self.envelope_counter += 1
            if self.envelope_counter >= self.envelope_steps:
                self.envelope_counter = 0
                if self.envelope_increase:
                    self.envelope_volume_current = min(15, self.envelope_volume_current + 1)
                else:
                    self.envelope_volume_current = max(0, self.envelope_volume_current - 1)
                if self.envelope_volume_current == 0:
                    self.enabled = False
                    return 0
        else:
            self.envelope_volume_current = self.envelope_volume

        # Timer/frequency
        if self.frequency > 0:
            self.timer_period = 2048 - self.frequency
        else:
            self.timer_period = 2048

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            self.output_bit = 1 - self.output_bit

            # Sweep
            if self.sweep_steps > 0:
                self.sweep_counter -= 1
                if self.sweep_counter <= 0:
                    self.sweep_counter = self.sweep_steps
                    if self.sweep_decrease:
                        self.frequency -= self.frequency >> self.sweep_shift
                    else:
                        self.frequency += self.frequency >> self.sweep_shift
                    if self.frequency > 2047:
                        self.enabled = False
                        return 0

        return self.output_bit * self.envelope_volume_current

    def trigger(self):
        """Trigger the channel (key on)"""
        self.timer = 0
        self.output_bit = 0
        self.envelope_counter = 0
        self.envelope_volume_current = self.envelope_volume
        self.length_counter = 0
        self.sweep_counter = self.sweep_steps
        self.enabled = True


class WaveChannel:
    """Wave playback channel (CH3)"""

    def __init__(self):
        self.enabled = False
        self.volume = 0
        self.frequency = 0
        self.wave_ram = [0] * 32
        self.wave_bank = 0
        self.length = 0
        self.length_enable = False
        self.length_counter = 0
        self.timer = 0
        self.timer_period = 0
        self.counter = 0
        self.format_8bit = False

    def step(self, sample_rate: int, wave_ram: list, wave_bank: int) -> int:
        """Generate one sample."""
        if not self.enabled:
            return 0

        # Length counter
        if self.length_enable and self.length > 0:
            self.length_counter += 1
            if self.length_counter >= 256:
                self.enabled = False
                return 0

        # Frequency timer
        if self.frequency > 0:
            self.timer_period = 2048 - self.frequency
        else:
            self.timer_period = 2048

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            self.counter += 1

        # Read from wave RAM — select bank based on wave_bank register
        nibble_index = self.counter % 64
        byte_index = nibble_index // 2
        wave_value = wave_ram[wave_bank][byte_index % 32]

        if nibble_index % 2 == 0:
            sample = wave_value & 0x0F
        else:
            sample = (wave_value >> 4) & 0x0F

        # Apply volume
        if self.volume == 0:
            return 0
        elif self.volume == 1:
            return sample
        elif self.volume == 2:
            return sample // 2
        else:  # volume == 3
            return sample // 4

    def trigger(self):
        """Trigger the channel"""
        self.timer = 0
        self.counter = 0
        self.length_counter = 0
        self.enabled = True


class NoiseChannel:
    """Noise channel (CH4)"""

    def __init__(self):
        self.enabled = False
        self.volume = 0
        self.envelope_volume = 0
        self.envelope_steps = 0
        self.envelope_increase = False
        self.length = 0
        self.length_enable = False
        self.length_counter = 0
        self.lfsr = 0x7FFF
        self.width_7bit = False
        self.clock_shift = 0
        self.clock_divider = 0
        self.envelope_counter = 0
        self.envelope_volume_current = 0
        self.timer = 0
        self.timer_period = 0
        self.output_bit = 0

    def step(self, sample_rate: int) -> int:
        """Generate one sample."""
        if not self.enabled:
            return 0

        # Length counter
        if self.length_enable and self.length > 0:
            self.length_counter += 1
            if self.length_counter >= (256 - self.length):
                self.enabled = False
                return 0

        # Envelope
        if self.envelope_steps > 0:
            self.envelope_counter += 1
            if self.envelope_counter >= self.envelope_steps:
                self.envelope_counter = 0
                if self.envelope_increase:
                    self.envelope_volume_current = min(15, self.envelope_volume_current + 1)
                else:
                    self.envelope_volume_current = max(0, self.envelope_volume_current - 1)
                if self.envelope_volume_current == 0:
                    self.enabled = False
                    return 0
        else:
            self.envelope_volume_current = self.envelope_volume

        # Timer
        divisor = max(1, self.clock_divider)
        self.timer_period = (1 << self.clock_shift) * divisor
        if self.timer_period == 0:
            self.timer_period = 1

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0

            # LFSR step
            if self.width_7bit:
                bit0 = self.lfsr & 1
                bit1 = (self.lfsr >> 1) & 1
                new_bit = bit0 ^ bit1
                self.lfsr = (self.lfsr >> 1) | (new_bit << 6)
                self.lfsr &= 0x7F
            else:
                bit0 = self.lfsr & 1
                bit14 = (self.lfsr >> 14) & 1
                new_bit = bit0 ^ bit14
                self.lfsr = (self.lfsr >> 1) | (new_bit << 14)

            self.output_bit = self.lfsr & 1

        return self.output_bit * self.envelope_volume_current

    def trigger(self):
        """Trigger the channel"""
        self.lfsr = 0x7FFF
        self.timer = 0
        self.output_bit = 0
        self.envelope_counter = 0
        self.envelope_volume_current = self.envelope_volume
        self.length_counter = 0
        self.enabled = True


class FIFO:
    """Direct Sound FIFO buffer"""

    def __init__(self):
        self.data = deque(maxlen=8)
        self.timer = 0
        self.timer_period = 1  # Will be set by DMA
        self.enabled = False
        self.volume_left = 0
        self.volume_right = 0

    def write(self, value: int):
        """Write a byte to FIFO"""
        self.data.append(value & 0xFF)

    def read(self) -> int:
        """Read a byte from FIFO"""
        if self.data:
            return self.data.popleft()
        return 128  # Silence

    def step(self, sample_rate: int) -> int:
        """Generate one sample from FIFO."""
        if not self.enabled:
            return 0

        self.timer += 1
        if self.timer >= self.timer_period and self.data:
            self.timer = 0
            return self.read()

        return 0


class APU:
    """GBA Audio Processing Unit"""

    SAMPLE_RATE = 44100

    def __init__(self):
        self.ch1 = SquareWaveChannel()
        self.ch2 = SquareWaveChannel()
        self.ch3 = WaveChannel()
        self.ch4 = NoiseChannel()
        self.fifo_a = FIFO()
        self.fifo_b = FIFO()
        self.wave_ram = [[0] * 32, [0] * 32]
        self.wave_bank = 0
        self.master_volume_left = 0
        self.master_volume_right = 0
        self.ch1_enabled = False
        self.ch2_enabled = False
        self.ch3_enabled = False
        self.ch4_enabled = False
        self.fifo_a_enabled = False
        self.fifo_b_enabled = False
        self._audio_output = None
        self._sound_buffer_a = None
        self._sound_buffer_b = None
        self._current_buffer = 'a'
        self._channel = None
        self._audio_channel = None  # Dedicated channel for continuous playback
        self._buffer_queue = deque(maxlen=4)  # Queue buffers for seamless playback

    def start(self):
        """Start audio playback"""
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=self.SAMPLE_RATE, size=-8, channels=2, buffer=512)

    def stop(self):
        """Stop audio playback"""
        try:
            pygame.mixer.stop()
        except pygame.error:
            pass

    def write_register(self, addr: int, value: int):
        """Handle MMIO writes to sound registers"""
        if addr == 0x04000060:
            self.ch1.sweep_shift = (value >> 4) & 0x07
            self.ch1.sweep_decrease = bool(value & 0x08)
            self.ch1.sweep_steps = value & 0x07
        elif addr == 0x04000062:
            self.ch1.duty_cycle = (value >> 6) & 0x03
            self.ch1.length = value & 0x3F
        elif addr == 0x04000064:
            self.ch1.frequency = value & 0x7FF
            self.ch1.envelope_volume = (value >> 12) & 0x0F
            self.ch1.envelope_steps = (value >> 8) & 0x07
            self.ch1.envelope_increase = bool(value & 0x0800)
            if value & 0x8000:
                self.ch1.trigger()
        elif addr == 0x04000068:
            self.ch2.duty_cycle = (value >> 6) & 0x03
            self.ch2.length = value & 0x3F
        elif addr == 0x0400006A:
            self.ch2.envelope_volume = (value >> 12) & 0x0F
            self.ch2.envelope_steps = (value >> 8) & 0x07
            self.ch2.envelope_increase = bool(value & 0x0800)
        elif addr == 0x0400006C:
            self.ch2.frequency = value & 0x7FF
            if value & 0x8000:
                self.ch2.trigger()
        elif addr == 0x04000070:
            self.ch3.wave_bank = (value >> 5) & 0x01
            self.wave_bank = self.ch3.wave_bank
            self.ch3.enabled = bool(value & 0x80)
        elif addr == 0x04000072:
            self.ch3.length = value & 0xFF
        elif addr == 0x04000074:
            volume_shift = (value >> 8) & 0x03
            self.ch3.volume = 0 if volume_shift == 0 else (1 if volume_shift == 1 else (2 if volume_shift == 2 else 3))
            self.ch3.format_8bit = bool(value & 0x0400)
            self.ch3.frequency = value & 0x3FF
            if value & 0x8000:
                self.ch3.trigger()
        elif addr == 0x04000078:
            self.ch4.length = value & 0x3F
        elif addr == 0x0400007A:
            self.ch4.envelope_volume = (value >> 12) & 0x0F
            self.ch4.envelope_steps = (value >> 8) & 0x07
            self.ch4.envelope_increase = bool(value & 0x0800)
        elif addr == 0x0400007C:
            self.ch4.clock_shift = (value >> 4) & 0x0F
            self.ch4.clock_divider = value & 0x07
            self.ch4.width_7bit = bool(value & 0x08)
            if value & 0x8000:
                self.ch4.trigger()
        elif addr == 0x04000080:
            self.master_volume_right = (value >> 4) & 0x07
            self.master_volume_left = value & 0x07
        elif addr == 0x04000082:
            self.fifo_a.volume_right = (value >> 4) & 0x0F
            self.fifo_a.volume_left = value & 0x0F
            self.fifo_a.enabled = bool(value & 0x0200)
            self.ch1_enabled = bool(value & 0x0001)
            self.ch2_enabled = bool(value & 0x0002)
        elif addr == 0x04000084:
            self.fifo_b.volume_right = (value >> 4) & 0x0F
            self.fifo_b.volume_left = value & 0x0F
            self.fifo_b.enabled = bool(value & 0x0200)
            self.ch3_enabled = bool(value & 0x0004)
            self.ch4_enabled = bool(value & 0x0008)
        elif 0x040000A0 <= addr <= 0x040000A3:
            self.fifo_a.write(value & 0xFF)
        elif 0x040000A4 <= addr <= 0x040000A7:
            self.fifo_b.write(value & 0xFF)
        elif 0x04000090 <= addr <= 0x040000AF:
            offset = addr - 0x04000090
            self.wave_ram[self.wave_bank][offset % 32] = value & 0xFF

    def get_sample(self) -> tuple:
        """Return mixed stereo sample (left, right)"""
        # Mix channels
        left = 0
        right = 0

        if self.ch1_enabled:
            sample = self.ch1.step(self.SAMPLE_RATE)
            left += sample * self.master_volume_left
            right += sample * self.master_volume_right

        if self.ch2_enabled:
            sample = self.ch2.step(self.SAMPLE_RATE)
            left += sample * self.master_volume_left
            right += sample * self.master_volume_right

        if self.ch3_enabled:
            sample = self.ch3.step(self.SAMPLE_RATE, self.wave_ram, self.wave_bank)
            left += sample * self.master_volume_left
            right += sample * self.master_volume_right

        if self.ch4_enabled:
            sample = self.ch4.step(self.SAMPLE_RATE)
            left += sample * self.master_volume_left
            right += sample * self.master_volume_right

        if self.fifo_a_enabled:
            sample = self.fifo_a.step(self.SAMPLE_RATE)
            left += sample * self.fifo_a.volume_left
            right += sample * self.fifo_a.volume_right

        if self.fifo_b_enabled:
            sample = self.fifo_b.step(self.SAMPLE_RATE)
            left += sample * self.fifo_b.volume_left
            right += sample * self.fifo_b.volume_right

        # Normalize to 0-255 range
        left = min(255, max(0, left // 7))
        right = min(255, max(0, right // 7))

        return (left, right)

    def update(self):
        if not pygame.mixer.get_init():
            return

        if not (self.ch1_enabled or self.ch2_enabled or
                self.ch3_enabled or self.ch4_enabled or
                self.fifo_a_enabled or self.fifo_b_enabled):
            return

        # Use dedicated FIFO channel (channel 1) for continuous playback
        # Channel 0 is reserved for regular audio channels
        if self._audio_channel is None:
            try:
                # Use channel 1 for FIFO to avoid conflict
                if pygame.mixer.get_num_channels() < 2:
                    pygame.mixer.set_num_channels(2)
                self._audio_channel = pygame.mixer.Channel(1)
                self._fifo_buffer_queue = deque(maxlen=8)
                self._fifo_initial_buffers_queued = False
            except pygame.error:
                return

        BUFFER_SIZE = 2048  # Larger buffer for smoother playback

        # Process CH1-CH4 when FIFO is not enabled
        if not (self.fifo_a_enabled or self.fifo_b_enabled):
            if not (self.ch1_enabled or self.ch2_enabled or self.ch3_enabled or self.ch4_enabled):
                return

            try:
                if not self._fifo_initial_buffers_queued:
                    samples = array.array('B')
                    for _ in range(BUFFER_SIZE):
                        left, right = self.get_sample()
                        samples.append(left)
                        samples.append(right)

                    if len(samples) == 0:
                        return

                    sound = pygame.mixer.Sound(buffer=samples.tobytes())
                    self._audio_channel.play(sound)

                    for _ in range(3):
                        samples = array.array('B')
                        for _ in range(BUFFER_SIZE):
                            left, right = self.get_sample()
                            samples.append(left)
                            samples.append(right)
                        if samples:
                            buf_sound = pygame.mixer.Sound(buffer=samples.tobytes())
                            self._audio_channel.queue(buf_sound)

                    self._fifo_initial_buffers_queued = True

                else:
                    if self._audio_channel.get_busy():
                        samples = array.array('B')
                        for _ in range(BUFFER_SIZE):
                            left, right = self.get_sample()
                            samples.append(left)
                            samples.append(right)

                        if samples:
                            sound = pygame.mixer.Sound(buffer=samples.tobytes())
                            self._audio_channel.queue(sound)
                    else:
                        self._fifo_initial_buffers_queued = False

            except pygame.error:
                return

            return

        try:
            if not self._fifo_initial_buffers_queued:
                samples = array.array('B')
                for _ in range(BUFFER_SIZE):
                    left, right = self.get_sample()
                    samples.append(left)
                    samples.append(right)

                if len(samples) == 0:
                    return

                sound = pygame.mixer.Sound(buffer=samples.tobytes())
                self._audio_channel.play(sound)

                for _ in range(3):
                    samples = array.array('B')
                    for _ in range(BUFFER_SIZE):
                        left, right = self.get_sample()
                        samples.append(left)
                        samples.append(right)
                    if samples:
                        buf_sound = pygame.mixer.Sound(buffer=samples.tobytes())
                        self._audio_channel.queue(buf_sound)

                self._fifo_initial_buffers_queued = True

            else:
                if self._audio_channel.get_busy():
                    samples = array.array('B')
                    for _ in range(BUFFER_SIZE):
                        left, right = self.get_sample()
                        samples.append(left)
                        samples.append(right)

                    if samples:
                        sound = pygame.mixer.Sound(buffer=samples.tobytes())
                        self._audio_channel.queue(sound)
                else:
                    self._fifo_initial_buffers_queued = False

        except pygame.error:
            pass
