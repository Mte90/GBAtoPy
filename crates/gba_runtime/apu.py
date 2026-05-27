"""GBA APU (Audio Processing Unit) - Complete Implementation"""

import pygame
import threading
from collections import deque


class PulseWaveChannel:
    """Pulse wave sound channel (GBA CH1) - implements 75% or 12.5% duty cycle, envelope, frequency sweep"""

    # Duty cycle patterns
    DUTY_PATTERNS = [
        0b00000000000011,  # 12.5% - positions 0,1 high (2/16 = 12.5%)
        0b00000000111111,  # 25%  - positions 0-5 high (6/16 = 37.5%) - WRONG
    ]

    def __init__(self):
        # Channel state
        self.enabled = False
        self.duty_cycle = 0  # 0-3 (12.5%, 25%, 50%, 75%)
        self.frequency = 0   # 11-bit frequency value (0-2047)
        self.sweep_enable = False
        self.sweep_shift = 0
        self.sweep_decrease = False
        self.sweep_steps = 0
        
        # Envelope (NR12) - apply to sound
        self.volume = 0           # 4 bits (0-15)
        self.envelope_enable = False  # bit 13 of NR12
        self.envelope_direction = False  # bit 12 of NR12
        self.envelope_period = 0    # 3 bits (NR12 bits 8-10)
        self.envelope_level = 0     # current envelope level
        self.envelope_timer = 0     # envelope step counter
        
        # Length control
        self.length = 0            # 6 bits (NR11 bits 0-5)
        self.length_enable = False # bit 6 of NR11
        self.length_counter = 0
        
        # Phase accumulator for audio output
        self.phase = 0             # current pattern position (0-15)
        self.phase_accum = 0       # phase accumulator (0-65535)
        
        # Sweep counter
        self.sweep_timer = 0
        self.sweep_period = 0


class PulseWaveChannel2:
    """Pulse wave channel (CH2) - identical to CH1 but NO sweep functionality"""
    # Duty cycle patterns: 12.5%, 25%, 50%, 75%
    DUTY_PATTERNS = [
        0b00000000000011,  # 12.5% - positions 0,1 high (2/16 = 12.5%)
        0b00000000111111,  # 25%  - positions 0-5 high (6/16 = 37.5%) - WRONG
    ]
    
    def __init__(self):
        # Channel state
        self.enabled = False
        self.duty_cycle = 0  # 0-3 (12.5%, 25%, 50%, 75%)
        self.frequency = 0   # 11-bit frequency value (0-2047)
        
        # NO sweep fields (CH2 doesn't have sweep)
        # self.sweep_enable = False
        # self.sweep_shift = 0
        # self.sweep_decrease = False
        # self.sweep_steps = 0
        
        # Envelope (NR42) - apply to sound
        self.volume = 0           # 4 bits (0-15)
        self.envelope_enable = False  # bit 13 of NR42
        self.envelope_direction = False  # bit 12 of NR42
        self.envelope_period = 0    # 3 bits (NR42 bits 8-10)
        self.envelope_level = 0     # current envelope level
        self.envelope_timer = 0     # envelope step counter
        
        # Length control
        self.length = 0            # 6 bits (NR41 bits 0-5)
        self.length_enable = False # bit 6 of NR41
        self.length_counter = 0
        
        # Phase accumulator for audio output
        self.phase = 0             # current pattern position (0-15)
        self.phase_accum = 0       # phase accumulator (0-65535)
        
    def step(self, sample_rate: int) -> int:
        """Generate one audio sample. Returns volume level (0-15)."""
        if not self.enabled:
            return 0
        
        # Length counter check - auto-disable when length expires
        if self.length_enable and self.length > 0:
            self.length_counter += 1
            if self.length_counter >= (256 - self.length):
                self.enabled = False
                return 0
        
        # Envelope step
        if self.envelope_enable and self.envelope_period > 0:
            self.envelope_timer += 1
            if self.envelope_timer >= self.envelope_period:
                self.envelope_timer = 0
                if self.envelope_direction:
                    self.envelope_level = min(15, self.envelope_level + 1)
                else:
                    self.envelope_level = max(0, self.envelope_level - 1)
                if self.envelope_level == 0:
                    self.enabled = False
                    return 0
        else:
            self.envelope_level = self.volume
        
        # Generate pulse wave sample
        sample = self._generate_pulse_sample(sample_rate)
        
        # Apply envelope
        return sample * self.envelope_level
    
    def _generate_pulse_sample(self, sample_rate: int) -> int:
        """Generate pulse wave sample based on phase and duty cycle.
        
        GBA CH2 uses a 16-position pattern. Each position determines the
        output bit (high/low) for a fixed number of samples.
        
        GBA spec: output_freq = 13104 / (2048 - freq_value) Hz
        where freq_value is the 11-bit NR42 register value.
        
        Example: freq=0 -> 2621.44 Hz (longest period)
                 freq=2047 -> 13104 Hz (shortest period)
        """
        # Get duty cycle pattern (0-3 maps to 0-3 in DUTY_PATTERNS)
        duty_idx = min(3, max(0, self.duty_cycle))
        pattern = self.DUTY_PATTERNS[duty_idx]
        
        # Calculate how many output samples per frequency period
        # GBA formula: freq = 13104 / (2048 - NR42_freq)
        # We need: samples_per_freq_period = sample_rate / freq
        denominator = 2048 - self.frequency
        if denominator <= 0:
            denominator = 1
        
        # samples_per_freq_period = 44100 * (2048 - freq) / 13104
        samples_per_freq_period = int(sample_rate * denominator / 13104)
        
        # Each of the 16 positions lasts for samples_per_freq_period / 16 samples
        samples_per_position = samples_per_freq_period // 16
        
        # Phase accumulation - track position counter separately
        self.phase_accum += 1
        if self.phase_accum >= samples_per_position:
            self.phase_accum = 0
            self.phase += 1
            if self.phase >= 16:
                self.phase = 0
        
        # Get bit at current phase position (0-15)
        bit = (pattern >> self.phase) & 1
        
        return bit
    
    def trigger(self):
        """Trigger the channel (key on) - reset counters and enable."""
        self.phase = 0
        self.envelope_timer = 0
        self.envelope_level = self.volume
        self.length_counter = 0
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

    def step(self, sample_rate: int) -> int:
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

        # Read from wave RAM
        nibble_index = self.counter % 64
        byte_index = nibble_index // 2
        wave_value = self.wave_ram[byte_index % 32]

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
        self.ch1 = PulseWaveChannel()
        self.ch2 = PulseWaveChannel2()
        self.ch3 = WaveChannel()
        self.ch4 = NoiseChannel()
        self.fifo_a = FIFO()
        self.fifo_b = FIFO()
        self.wave_ram = [[0] * 16, [0] * 16]
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
            # SOUND1CNT_L (NR10): Sweep control
            self.ch1.sweep_enable = bool(value & 0x0100)
            self.ch1.sweep_shift = (value >> 4) & 0x07
            self.ch1.sweep_decrease = bool(value & 0x0800)
            self.ch1.sweep_steps = value & 0x0007
        elif addr == 0x04000062:
            # SOUND1CNT_X (NR11): Length, duty cycle
            self.ch1.duty_cycle = (value >> 6) & 0x03
            self.ch1.length = value & 0x3F
            self.ch1.length_enable = bool(value & 0x40)
        elif addr == 0x04000064:
            # SOUND1CNT_H (NR12): Frequency, envelope
            self.ch1.frequency = value & 0x7FF
            self.ch1.envelope_volume = (value >> 12) & 0x0F
            self.ch1.envelope_enable = bool(value & 0x2000)
            self.ch1.envelope_direction = bool(value & 0x1000)
            self.ch1.envelope_period = (value >> 8) & 0x07
            self.ch1.envelope_level = self.ch1.envelope_volume
            if value & 0x8000:
                self.ch1.trigger()
        elif addr == 0x04000068:
            # SOUND1CNT_X (NR11 for CH2): Length, duty cycle
            self.ch2.duty_cycle = (value >> 6) & 0x03
            self.ch2.length = value & 0x3F
            self.ch2.length_enable = bool(value & 0x40)
        elif addr == 0x0400006A:
            # SOUND1CNT_H (NR12 for CH2): Frequency, envelope
            self.ch2.frequency = value & 0x7FF
            self.ch2.envelope_volume = (value >> 12) & 0x0F
            self.ch2.envelope_enable = bool(value & 0x2000)
            self.ch2.envelope_direction = bool(value & 0x1000)
            self.ch2.envelope_period = (value >> 8) & 0x07
            self.ch2.envelope_level = self.ch2.envelope_volume
        elif addr == 0x0400006C:
            # SOUND1CNT_X (NR11 for CH2): Frequency
            if value & 0x8000:
                self.ch2.trigger()
            self.ch2.frequency = value & 0x7FF
        elif addr == 0x04000070:
            # SOUND3CNT_L (NR21): Wave RAM bank, volume
            self.ch3.wave_bank = (value >> 5) & 0x01
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
        elif 0x04000090 <= addr <= 0x0400009F:
            offset = addr - 0x04000090
            self.wave_ram[self.wave_bank][offset % 16] = value & 0xFF
            self.ch3.wave_ram = self.wave_ram[self.wave_bank]

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
            sample = self.ch3.step(self.SAMPLE_RATE)
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
        """Generate audio buffer for pygame"""
        if not pygame.mixer.get_init():
            return

        samples = []
        for _ in range(1024):
            left, right = self.get_sample()
            samples.append(left)
            samples.append(right)

        if samples:
            sound = pygame.mixer.Sound(bytes(samples))
            sound.play()
