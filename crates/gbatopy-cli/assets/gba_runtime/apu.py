"""GBA APU (Audio Processing Unit) - Complete Implementation"""

import pygame
import threading
import math
from collections import deque


# ============================================================================
# ============================================================================

class LowPassFilter:
    """Simple first-order low-pass filter using bi-linear approximation.
    
    Implements a one-pole low-pass filter with adjustable cutoff frequency
    and resonance (Q factor). Uses bi-linear transform for stability.
    
    Filter equation:
        y[n] = (1 - alpha) * x[n] + alpha * y[n-1]
    
    Where alpha controls the cutoff frequency:
        alpha = f_s / (f_s + f_c) for bi-linear transform
    """
    
    def __init__(self, sample_rate: int = 44100, cutoff_freq: float = 20000.0, q: float = 1.0):
        """Initialize low-pass filter.
        
        Args:
            sample_rate: Audio sample rate (default: 44100 Hz)
            cutoff_freq: Cutoff frequency in Hz (default: 20 kHz, full bandwidth)
            q: Quality factor/resonance (default: 1.0, affects slope)
        """
        self.sample_rate = sample_rate
        self.cutoff_freq = max(10.0, min(cutoff_freq, sample_rate / 2))
        self.q = max(0.1, min(q, 10.0))
        
        # Calculate filter coefficient using bi-linear transform
        # alpha = f_s / (f_s + f_c) ensures stability
        self._update_coefficients()
    
    def _update_coefficients(self):
        """Recalculate filter coefficients based on current settings."""
        # Bi-linear transform coefficient
        # For low-pass: H(z) = (1 - alpha) + alpha * z^-1
        # alpha = f_s / (f_s + f_c)
        self.alpha = self.sample_rate / (self.sample_rate + self.cutoff_freq)
        # Clamp alpha to (0, 1) for stability
        self.alpha = max(0.001, min(self.alpha, 0.999))
    
    def set_cutoff(self, freq_hz: float):
        """Set cutoff frequency (Hz)."""
        self.cutoff_freq = max(10.0, min(freq_hz, self.sample_rate / 2))
        self._update_coefficients()
    
    def set_sample_rate(self, sample_rate: int):
        """Update sample rate and recalculate coefficients."""
        self.sample_rate = sample_rate
        self._update_coefficients()
    
    def process(self, sample: float) -> float:
        """Process single sample through low-pass filter.
        
        Args:
            sample: Input sample value (typically 0.0 to 1.0)
            
        Returns:
            Filtered sample value
        """
        # One-pole low-pass filter
        # y[n] = (1 - alpha) * x[n] + alpha * y[n-1]
        filtered = (1.0 - self.alpha) * sample + self.alpha * self.last_output
        self.last_output = filtered
        return filtered
    
    def process_sample_array(self, samples: list) -> list:
        """Process array of samples.
        
        Args:
            samples: List of input samples
            
        Returns:
            List of filtered samples
        """
        return [self.process(s) for s in samples]


class PitchShift:
    """Simple pitch shifter using time-domain overlap-add.
    
    Implements basic pitch shifting by changing playback rate and using
    overlap-add to reduce artifacts. This is a simplified implementation
    suitable for real-time audio processing.
    
    Characteristics:
        - Pitch range: -2 to +2 semitones
        - Real-time capable
        - Minimal latency
        - Simple algorithm (no granular synthesis)
    """
    
    def __init__(self, sample_rate: int = 44100, pitch_semitones: float = 0.0):
        """Initialize pitch shifter.
        
        Args:
            sample_rate: Audio sample rate (default: 44100 Hz)
            pitch_semitones: Pitch shift in semitones (-2 to +2, default: 0)
        """
        self.sample_rate = sample_rate
        self.pitch_semitones = max(-2.0, min(pitch_semitones, 2.0))
        
        # Calculate pitch ratio: 2^(semitones/12)
        # +12 semitones = octave up (ratio = 2.0)
        # -12 semitones = octave down (ratio = 0.5)
        self.pitch_ratio = 2 ** (self.pitch_semitones / 12.0)
        self.pitch_ratio = max(0.5, min(self.pitch_ratio, 2.0))
        
        # Overlap buffer for smooth pitch transitions
        self.buffer_size = int(0.01 * sample_rate)  # 10ms buffer
        self.buffer = [0.0] * self.buffer_size
        self.buffer_pos = 0
        self.write_pos = 0
        self.overlap_count = 0
    
    def set_pitch(self, semitones: float):
        """Set pitch shift in semitones."""
        self.pitch_semitones = max(-2.0, min(semitones, 2.0))
        self.pitch_ratio = 2 ** (self.pitch_semitones / 12.0)
        self.pitch_ratio = max(0.5, min(self.pitch_ratio, 2.0))
    
    def process(self, sample: float) -> float:
        """Process single sample with pitch shift.
        
        Args:
            sample: Input sample value (typically 0.0 to 1.0)
            
        Returns:
            Pitch-shifted sample
        """
        # Resampling approach: play input samples at adjusted rate
        # Using simple linear interpolation for pitch shift
        
        # Read from buffer at adjusted position
        read_pos = (self.buffer_pos + self.overlap_count) % len(self.buffer)
        
        # Store current sample in buffer
        self.buffer[self.write_pos] = sample
        self.write_pos = (self.write_pos + 1) % len(self.buffer)
        
        # Advance read position based on pitch ratio
        # Lower ratio = slower playback = pitch up
        # Higher ratio = faster playback = pitch down
        self.overlap_count = int(self.buffer_size * (1.0 / self.pitch_ratio - 1.0))
        if self.overlap_count < 0:
            self.overlap_count = max(0, int(self.buffer_size * (1.0 - self.pitch_ratio)))
        
        return self.buffer[read_pos]
    
    def reset(self):
        """Clear buffer."""
        self.buffer = [0.0] * len(self.buffer)
        self.buffer_pos = 0
        self.overlap_count = 0


class DelayLine:
    """Audio delay line for echo and reverb effects.
    
    Implements a circular buffer delay line with adjustable delay time,
    feedback, and wet/dry mix control. Supports mono and stereo.
    
    Features:
        - Adjustable delay time (0 to 1 second)
        - Feedback control (0 to 0.9)
        - Wet/dry mix
        - Linear interpolation for sub-sample delay
    """
    
    def __init__(self, sample_rate: int = 44100, delay_time_ms: float = 100.0,
                 feedback: float = 0.4, wet_mix: float = 0.5, dry_mix: float = 0.5):
        """Initialize delay line.
        
        Args:
            sample_rate: Audio sample rate (default: 44100 Hz)
            delay_time_ms: Delay time in milliseconds (default: 100ms)
            feedback: Feedback amount 0-0.9 (default: 0.4)
            wet_mix: Wet signal mix 0-1 (default: 0.5)
            dry_mix: Dry signal mix 0-1 (default: 0.5)
        """
        self.sample_rate = sample_rate
        self.delay_time_ms = max(1.0, min(delay_time_ms, 1000.0))
        self.feedback = max(0.0, min(feedback, 0.9))
        self.wet_mix = max(0.0, min(wet_mix, 1.0))
        self.dry_mix = max(0.0, min(dry_mix, 1.0))
        
        # Calculate delay line size
        self.delay_samples = int(self.sample_rate * (self.delay_time_ms / 1000.0))
        self.delay_samples = max(1, min(self.delay_samples, sample_rate))
        
        # Circular buffer
        self.buffer = [0.0] * self.delay_samples
        self.write_index = 0
        self.read_index = 0
        self.delay_samples_float = float(self.delay_samples)
    
    def set_delay(self, time_ms: float):
        """Set delay time in milliseconds."""
        self.delay_time_ms = max(1.0, min(time_ms, 1000.0))
        old_samples = self.delay_samples
        
        # Update buffer size if needed
        new_samples = int(self.sample_rate * (self.delay_time_ms / 1000.0))
        new_samples = max(1, min(new_samples, self.sample_rate))
        
        if new_samples != old_samples:
            if new_samples > self.delay_samples:
                # Expand buffer
                while len(self.buffer) < new_samples:
                    self.buffer.append(0.0)
            else:
                # Shrink buffer and clear overflow
                self.buffer = self.buffer[:new_samples]
        
        self.delay_samples = new_samples
        self.delay_samples_float = float(self.delay_samples)
    
    def set_feedback(self, value: float):
        """Set feedback amount (0 to 0.9)."""
        self.feedback = max(0.0, min(value, 0.9))
    
    def set_mix(self, wet: float = None, dry: float = None):
        """Set wet/dry mix.
        
        Args:
            wet: Wet mix 0-1 (if None, uses dry)
            dry: Dry mix 0-1 (if None, uses wet)
        """
        if wet is not None:
            self.wet_mix = max(0.0, min(wet, 1.0))
        if dry is not None:
            self.dry_mix = max(0.0, min(dry, 1.0))
    
    def process(self, sample: float) -> float:
        """Process sample through delay line.
        
        Args:
            sample: Input sample
            
        Returns:
            Mixed (wet + dry) output
        """
        # Calculate fractional delay position
        fractional_samples = self.sample_rate * (self.delay_time_ms / 1000.0) / self.sample_rate
        
        # Read delayed sample with linear interpolation
        delay_idx = int(self.read_index)
        frac = fractional_samples - delay_idx
        
        # Linear interpolation
        prev_sample = self.buffer[delay_idx]
        next_idx = (delay_idx + 1) % self.delay_samples
        next_sample = self.buffer[next_idx]
        
        delayed_sample = prev_sample * (1.0 - frac) + next_sample * frac
        
        # Write new sample to buffer
        self.buffer[self.write_index] = sample * self.dry_mix + delayed_sample * self.feedback * self.wet_mix
        self.write_index = (self.write_index + 1) % self.delay_samples
        
        # Update read index
        self.read_index = (self.read_index + fractional_samples) % self.delay_samples_float
        
        # Apply wet mix and return
        return delayed_sample * self.wet_mix
    
    def clear(self):
        """Clear buffer."""
        self.buffer = [0.0] * len(self.buffer)


class EffectChain:
    """Effect chain for serial processing of DSP effects.
    
    Connects multiple effects in series where the output of one effect
    becomes the input of the next. Supports dynamic addition/removal
    of effects.
    
    Effect order (signal flow):
        Input -> [Effect1] -> [Effect2] -> ... -> Output
    """
    
    def __init__(self, sample_rate: int = 44100):
        """Initialize effect chain.
        
        Args:
            sample_rate: Audio sample rate (default: 44100 Hz)
        """
        self.sample_rate = sample_rate
        self.effects = []
        self.enabled = True
    
    def add_effect(self, effect):
        """Add effect to the chain.
        
        Args:
            effect: DSP effect instance (LowPassFilter, PitchShift, DelayLine)
        """
        if effect not in self.effects:
            self.effects.append(effect)
    
    def remove_effect(self, effect):
        """Remove effect from chain.
        
        Args:
            effect: DSP effect instance to remove
        """
        if effect in self.effects:
            self.effects.remove(effect)
    
    def insert_effect(self, index: int, effect):
        """Insert effect at specific position.
        
        Args:
            index: Position to insert (0 = first, negative = from end)
            effect: DSP effect to insert
        """
        if index < 0:
            index = len(self.effects) + index
        if 0 <= index <= len(self.effects):
            self.effects.insert(index, effect)
    
    def process(self, sample: float) -> float:
        """Process sample through all effects in chain.
        
        Args:
            sample: Input sample
            
        Returns:
            Processed sample
        """
        if not self.enabled:
            return sample
        
        for effect in self.effects:
            sample = effect.process(sample)
        
        return sample
    
    def process_sample_array(self, samples: list) -> list:
        """Process array of samples.
        
        Args:
            samples: List of input samples
            
        Returns:
            List of processed samples
        """
        if not self.enabled or not self.effects:
            return samples
        
        return [self.process(s) for s in samples]


# ============================================================================
# DSP Effects - Audio Processing Pipeline
# ============================================================================

import math
from collections import deque


class LowPassFilter:
    """Simple first-order low-pass filter using bi-linear approximation.
    
    Implements a one-pole low-pass filter with adjustable cutoff frequency
    and resonance (Q factor). Uses bi-linear transform for stability.
    
    Filter equation:
        y[n] = (1 - alpha) * x[n] + alpha * y[n-1]
    
    Where alpha controls the cutoff frequency:
        alpha = f_s / (f_s + f_c) for bi-linear transform
    """
    
    def __init__(self, sample_rate: int = 44100, cutoff_freq: float = 20000.0, q: float = 1.0):
        """Initialize low-pass filter.
        
        Args:
            sample_rate: Audio sample rate (default: 44100 Hz)
            cutoff_freq: Cutoff frequency in Hz (default: 20 kHz, full bandwidth)
            q: Quality factor/resonance (default: 1.0, affects slope)
        """
        self.sample_rate = sample_rate
        self.cutoff_freq = max(10.0, min(cutoff_freq, sample_rate / 2))
        self.q = max(0.1, min(q, 10.0))
        
        # Calculate filter coefficient using bi-linear transform
        # alpha = f_s / (f_s + f_c) ensures stability
        self._update_coefficients()
    
    def _update_coefficients(self):
        """Recalculate filter coefficients based on current settings."""
        # Bi-linear transform coefficient
        # For low-pass: H(z) = (1 - alpha) + alpha * z^-1
        # alpha = f_s / (f_s + f_c)
        self.alpha = self.sample_rate / (self.sample_rate + self.cutoff_freq)
        # Clamp alpha to (0, 1) for stability
        self.alpha = max(0.001, min(self.alpha, 0.999))
    
    def set_cutoff(self, freq_hz: float):
        """Set cutoff frequency (Hz)."""
        self.cutoff_freq = max(10.0, min(freq_hz, self.sample_rate / 2))
        self._update_coefficients()
    
    def set_sample_rate(self, sample_rate: int):
        """Update sample rate and recalculate coefficients."""
        self.sample_rate = sample_rate
        self._update_coefficients()
    
    def process(self, sample: float) -> float:
        """Process single sample through low-pass filter.
        
        Args:
            sample: Input sample value (typically 0.0 to 1.0)
            
        Returns:
            Filtered sample value
        """
        # One-pole low-pass filter
        # y[n] = (1 - alpha) * x[n] + alpha * y[n-1]
        filtered = (1.0 - self.alpha) * sample + self.alpha * self.last_output
        self.last_output = filtered
        return filtered
    
    def process_sample_array(self, samples: list) -> list:
        """Process array of samples.
        
        Args:
            samples: List of input samples
            
        Returns:
            List of filtered samples
        """
        return [self.process(s) for s in samples]


class PitchShift:
    """Simple pitch shifter using time-domain overlap-add.
    
    Implements basic pitch shifting by changing playback rate and using
    overlap-add to reduce artifacts. This is a simplified implementation
    suitable for real-time audio processing.
    
    Characteristics:
        - Pitch range: -2 to +2 semitones
        - Real-time capable
        - Minimal latency
        - Simple algorithm (no granular synthesis)
    """
    
    def __init__(self, sample_rate: int = 44100, pitch_semitones: float = 0.0):
        """Initialize pitch shifter.
        
        Args:
            sample_rate: Audio sample rate (default: 44100 Hz)
            pitch_semitones: Pitch shift in semitones (-2 to +2, default: 0)
        """
        self.sample_rate = sample_rate
        self.pitch_semitones = max(-2.0, min(pitch_semitones, 2.0))
        
        # Calculate pitch ratio: 2^(semitones/12)
        # +12 semitones = octave up (ratio = 2.0)
        # -12 semitones = octave down (ratio = 0.5)
        self.pitch_ratio = 2 ** (self.pitch_semitones / 12.0)
        self.pitch_ratio = max(0.5, min(self.pitch_ratio, 2.0))
        
        # Overlap buffer for smooth pitch transitions
        self.buffer_size = int(0.01 * sample_rate)  # 10ms buffer
        self.buffer = [0.0] * self.buffer_size
        self.buffer_pos = 0
        self.write_pos = 0
        self.overlap_count = 0
    
    def set_pitch(self, semitones: float):
        """Set pitch shift in semitones."""
        self.pitch_semitones = max(-2.0, min(semitones, 2.0))
        self.pitch_ratio = 2 ** (self.pitch_semitones / 12.0)
        self.pitch_ratio = max(0.5, min(self.pitch_ratio, 2.0))
    
    def process(self, sample: float) -> float:
        """Process single sample with pitch shift.
        
        Args:
            sample: Input sample value (typically 0.0 to 1.0)
            
        Returns:
            Pitch-shifted sample
        """
        # Resampling approach: play input samples at adjusted rate
        # Using simple linear interpolation for pitch shift
        
        # Read from buffer at adjusted position
        read_pos = (self.buffer_pos + self.overlap_count) % len(self.buffer)
        
        # Store current sample in buffer
        self.buffer[self.write_pos] = sample
        self.write_pos = (self.write_pos + 1) % len(self.buffer)
        
        # Advance read position based on pitch ratio
        # Lower ratio = slower playback = pitch up
        # Higher ratio = faster playback = pitch down
        self.overlap_count = int(self.buffer_size * (1.0 / self.pitch_ratio - 1.0))
        if self.overlap_count < 0:
            self.overlap_count = max(0, int(self.buffer_size * (1.0 - self.pitch_ratio)))
        
        return self.buffer[read_pos]
    
    def reset(self):
        """Clear buffer."""
        self.buffer = [0.0] * len(self.buffer)
        self.buffer_pos = 0
        self.overlap_count = 0


class DelayLine:
    """Audio delay line for echo and reverb effects.
    
    Implements a circular buffer delay line with adjustable delay time,
    feedback, and wet/dry mix control. Supports mono and stereo.
    
    Features:
        - Adjustable delay time (0 to 1 second)
        - Feedback control (0 to 0.9)
        - Wet/dry mix
        - Linear interpolation for sub-sample delay
    """
    
    def __init__(self, sample_rate: int = 44100, delay_time_ms: float = 100.0,
                 feedback: float = 0.4, wet_mix: float = 0.5, dry_mix: float = 0.5):
        """Initialize delay line.
        
        Args:
            sample_rate: Audio sample rate (default: 44100 Hz)
            delay_time_ms: Delay time in milliseconds (default: 100ms)
            feedback: Feedback amount 0-0.9 (default: 0.4)
            wet_mix: Wet signal mix 0-1 (default: 0.5)
            dry_mix: Dry signal mix 0-1 (default: 0.5)
        """
        self.sample_rate = sample_rate
        self.delay_time_ms = max(1.0, min(delay_time_ms, 1000.0))
        self.feedback = max(0.0, min(feedback, 0.9))
        self.wet_mix = max(0.0, min(wet_mix, 1.0))
        self.dry_mix = max(0.0, min(dry_mix, 1.0))
        
        # Calculate delay line size
        self.delay_samples = int(self.sample_rate * (self.delay_time_ms / 1000.0))
        self.delay_samples = max(1, min(self.delay_samples, sample_rate))
        
        # Circular buffer
        self.buffer = [0.0] * self.delay_samples
        self.write_index = 0
        self.read_index = 0
        self.delay_samples_float = float(self.delay_samples)
    
    def set_delay(self, time_ms: float):
        """Set delay time in milliseconds."""
        self.delay_time_ms = max(1.0, min(time_ms, 1000.0))
        old_samples = self.delay_samples
        
        # Update buffer size if needed
        new_samples = int(self.sample_rate * (self.delay_time_ms / 1000.0))
        new_samples = max(1, min(new_samples, self.sample_rate))
        
        if new_samples != old_samples:
            if new_samples > self.delay_samples:
                # Expand buffer
                while len(self.buffer) < new_samples:
                    self.buffer.append(0.0)
            else:
                # Shrink buffer and clear overflow
                self.buffer = self.buffer[:new_samples]
        
        self.delay_samples = new_samples
        self.delay_samples_float = float(self.delay_samples)
    
    def set_feedback(self, value: float):
        """Set feedback amount (0 to 0.9)."""
        self.feedback = max(0.0, min(value, 0.9))
    
    def set_mix(self, wet: float = None, dry: float = None):
        """Set wet/dry mix.
        
        Args:
            wet: Wet mix 0-1 (if None, uses dry)
            dry: Dry mix 0-1 (if None, uses wet)
        """
        if wet is not None:
            self.wet_mix = max(0.0, min(wet, 1.0))
        if dry is not None:
            self.dry_mix = max(0.0, min(dry, 1.0))
    
    def process(self, sample: float) -> float:
        """Process sample through delay line.
        
        Args:
            sample: Input sample
            
        Returns:
            Mixed (wet + dry) output
        """
        # Calculate fractional delay position
        fractional_samples = self.sample_rate * (self.delay_time_ms / 1000.0) / self.sample_rate
        
        # Read delayed sample with linear interpolation
        delay_idx = int(self.read_index)
        frac = fractional_samples - delay_idx
        
        # Linear interpolation
        prev_sample = self.buffer[delay_idx]
        next_idx = (delay_idx + 1) % self.delay_samples
        next_sample = self.buffer[next_idx]
        
        delayed_sample = prev_sample * (1.0 - frac) + next_sample * frac
        
        # Write new sample to buffer
        self.buffer[self.write_index] = sample * self.dry_mix + delayed_sample * self.feedback * self.wet_mix
        self.write_index = (self.write_index + 1) % self.delay_samples
        
        # Update read index
        self.read_index = (self.read_index + fractional_samples) % self.delay_samples_float
        
        # Apply wet mix and return
        return delayed_sample * self.wet_mix
    
    def clear(self):
        """Clear buffer."""
        self.buffer = [0.0] * len(self.buffer)


class EffectChain:
    """Effect chain for serial processing of DSP effects.
    
    Connects multiple effects in series where the output of one effect
    becomes the input of the next. Supports dynamic addition/removal
    of effects.
    
    Effect order (signal flow):
        Input -> [Effect1] -> [Effect2] -> ... -> Output
    """
    
    def __init__(self, sample_rate: int = 44100):
        """Initialize effect chain.
        
        Args:
            sample_rate: Audio sample rate (default: 44100 Hz)
        """
        self.sample_rate = sample_rate
        self.effects = []
        self.enabled = True
    
    def add_effect(self, effect):
        """Add effect to the chain.
        
        Args:
            effect: DSP effect instance (LowPassFilter, PitchShift, DelayLine)
        """
        if effect not in self.effects:
            self.effects.append(effect)
    
    def remove_effect(self, effect):
        """Remove effect from chain.
        
        Args:
            effect: DSP effect instance to remove
        """
        if effect in self.effects:
            self.effects.remove(effect)
    
    def insert_effect(self, index: int, effect):
        """Insert effect at specific position.
        
        Args:
            index: Position to insert (0 = first, negative = from end)
            effect: DSP effect to insert
        """
        if index < 0:
            index = len(self.effects) + index
        if 0 <= index <= len(self.effects):
            self.effects.insert(index, effect)
    
    def process(self, sample: float) -> float:
        """Process sample through all effects in chain.
        
        Args:
            sample: Input sample
            
        Returns:
            Processed sample
        """
        if not self.enabled:
            return sample
        
        for effect in self.effects:
            sample = effect.process(sample)
        
        return sample
    
    def process_sample_array(self, samples: list) -> list:
        """Process array of samples.
        
        Args:
            samples: List of input samples
            
        Returns:
            List of processed samples
        """
        if not self.enabled or not self.effects:
            return samples
        
        return [self.process(s) for s in samples]


# ============================================================================
# GBA APU (Audio Processing Unit)
# ============================================================================class PulseWaveChannel:
    """Pulse wave sound channel - implements duty cycle, envelope, frequency sweep (CH1) or envelope only (CH2).
    
    CH1 (channel_id=1): Has sweep functionality
    CH2 (channel_id=2): No sweep, only envelope
    """
    DUTY_PATTERNS = [
        0b0000000000000011,  # 12.5% - 2 bits (positions 0,1)
        0b0000000000001111,  # 25%   - 4 bits (positions 0-3)
        0b0000000011111111,  # 50%   - 8 bits (positions 0-7)
        0b0000111111111111,  # 75%   - 12 bits (positions 0-11)
    ]
    
    def __init__(self, channel_id: int = 1):
        """Initialize pulse channel. channel_id=1 for CH1 (with sweep), channel_id=2 for CH2 (no sweep)."""
        self.enabled = False
        self.duty_cycle = 0  # 0-3 (12.5%, 25%, 50%, 75%)
        self.frequency = 0   # 11-bit frequency value (0-2047)
        self.sweep_enable = (channel_id == 1)  # CH1 has sweep, CH2 does not
        self.sweep_shift = 0
        self.sweep_decrease = False
        self.sweep_steps = 0
        self.volume = 0           # 4 bits (0-15)
        self.envelope_enable = False  # bit 13 of NR12
        self.envelope_direction = False  # bit 12 of NR12 (increase/decrease)
        self.envelope_period = 0    # 3 bits (NR12 bits 8-10)
        self.envelope_level = 0
        self.envelope_timer = 0
        self.length = 0            # 6 bits (NR11 bits 0-5)
        self.length_enable = False # bit 6 of NR11
        self.length_counter = 0
        self.phase = 0
        self.phase_accum = 0
        self.sweep_timer = 0
        self.sweep_period = 0
    
    def step(self, sample_rate: int) -> int:
        """Generate one audio sample."""
        if not self.enabled:
            return 0
        
        if self.length_enable and self.length > 0:
            self.length_counter += 1
            if self.length_counter >= (256 - self.length):
                self.enabled = False
                return 0
        
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
        
        sample = self._generate_pulse_sample(sample_rate)
        return sample * self.envelope_level
    
    def _generate_pulse_sample(self, sample_rate: int) -> int:
        """Generate pulse wave sample based on phase and duty cycle."""
        duty_idx = min(3, max(0, self.duty_cycle))
        pattern = self.DUTY_PATTERNS[duty_idx]
        
        denominator = 2048 - self.frequency
        if denominator <= 0:
            denominator = 1
        
        samples_per_freq_period = int(sample_rate * denominator / 13104)
        samples_per_position = samples_per_freq_period // 16
        
        self.phase_accum += 1
        if self.phase_accum >= samples_per_position:
            self.phase_accum = 0
            self.phase += 1
            if self.phase >= 16:
                self.phase = 0
        
        bit = (pattern >> self.phase) & 1
        return bit
    
    def trigger(self):
        """Trigger the channel (key on) - reset counters and enable."""
        self.timer = 0
        self.phase = 0
        self.envelope_timer = 0
        self.envelope_level = self.volume
        self.length_counter = 0
        self.enabled = True
    """Pulse wave sound channel (GBA CH1) - implements 75% or 12.5% duty cycle, envelope, frequency sweep"""

    # Duty cycle patterns: GBA CH1 uses a 16-position counter
    # Each duty setting determines how many positions are "high" in the pattern
    # The pattern wraps every 16 positions
    # 12.5% = 2/16 positions, 25% = 4/16, 50% = 8/16, 75% = 12/16
    # Patterns use bit-shifting to create the appropriate duty cycle
    # We simulate by cycling through all 16 positions
    DUTY_PATTERNS = [
        0b00000000000011,  # 12.5% - 2 positions (0,1)
        0b00000000111111,  # 25%  - 6 positions (0-5) + 4 extra = 10 positions
        0b00000011111111,  # 37.5% - 8 positions (0-7) + 2 more = 10... need to fix
    ]
    # Actually, let's just use consecutive bits for simplicity:
    DUTY_PATTERNS = [
        0b0000000000000011,  # 12.5% - 2 bits (positions 0,1)
        0b0000000000001111,  # 25%   - 4 bits (positions 0-3)
        0b0000000011111111,  # 50%   - 8 bits (positions 0-7)
        0b0000111111111111,  # 75%   - 12 bits (positions 0-11)
    ]

    def __init__(self):
        # Channel state
        self.enabled = False
        self.duty_cycle = 0  # 0-3 (12.5%, 25%, 50%, 75%)
        self.frequency = 0   # 11-bit frequency value (0-2047)
        self.sweep_enable = False
        self.sweep_shift = 0      # 3 bits (shift amount)
        self.sweep_decrease = False
        self.sweep_steps = 0      # 3 bits (steps per sweep)
        
        # Envelope (NR12) - apply to sound
        self.volume = 0           # 4 bits (0-15)
        self.envelope_enable = False  # bit 13 of NR12
        self.envelope_direction = False  # bit 12 of NR12 (increase/decrease)
        self.envelope_period = 0    # 3 bits (NR12 bits 8-10)
        self.envelope_level = 0     # current envelope level
        self.envelope_timer = 0     # envelope step counter
        
        # Length control
        self.length = 0            # 6 bits (NR11 bits 0-5)
        self.length_enable = False # bit 6 of NR11
        self.length_counter = 0
        
        # Phase accumulator for audio output
        # 16-bit phase accumulator for 16-position pattern
        self.phase = 0             # current pattern position (0-15)
        self.phase_accum = 0       # phase accumulator (0-65535)
        
        # Sweep counter
        self.sweep_timer = 0
        self.sweep_period = 0

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
        
        GBA CH1 uses a 16-position pattern. Each position determines the
        output bit (high/low) for a fixed number of samples.
        
        GBA spec: output_freq = 13104 / (2048 - freq_value) Hz
        where freq_value is the 11-bit NR12 register value.
        
        Example: freq=0 -> 2621.44 Hz (longest period)
                 freq=2047 -> 13104 Hz (shortest period)
        """
        # Get duty cycle pattern (0-3 maps to 0-3 in DUTY_PATTERNS)
        duty_idx = min(3, max(0, self.duty_cycle))
        pattern = self.DUTY_PATTERNS[duty_idx]
        
        # Calculate how many output samples per frequency period
        # GBA formula: freq = 13104 / (2048 - NR12_freq)
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
        self.timer = 0
        self.phase = 0
        self.envelope_timer = 0
        self.envelope_level = self.volume
        self.length_counter = 0
        self.enabled = True


class WaveChannel:
    """Wave playback channel (CH3) - Direct Sound sample playback
    
    GBA CH3 plays 4-bit or 8-bit PCM samples from Wave RAM (32 bytes).
    Uses timer-controlled sample rate with rate conversion for pygame.
    """

    def __init__(self):
        self.enabled = False
        self.volume = 0  # 0-3: 0%=0, 1%=50%, 2%=100%, 3=reserved
        self.frequency = 0  # Sample rate timer (12-bit from NR44)
        self.wave_ram = [0] * 32  # Wave RAM buffer
        self.wave_bank = 0  # Bank 0 or 1 (via NR43)
        self.length = 0  # 0xFF = infinite, 0-0xFE = length in samples
        self.length_enable = False  # NR41 bit 7
        self.length_counter = 0
        self.timer = 0
        self.timer_period = 0
        self.counter = 0  # Sample counter
        self.format_8bit = False  # NR43 bit 4
        self.timer_clock = 0  # Timer clock source (NR43 bits 0-1)
        self.silent = False  # NR43 bit 5
        
        self.dma_fifo = None  # Reference to DMA controller for FIFO A

        # Sample rate configuration
        self.sample_clock = 0  # 131072, 8192, or 4096
        self.estimated_rate = 0

    def step(self, sample_rate: int) -> int:
        """Generate one audio sample.
        
        Args:
            sample_rate: Target output sample rate (e.g., 44100)
            
        Returns:
            Sample value (0-15 for 4-bit, 0-255 for 8-bit)
        """
        if not self.enabled or self.silent:
            return 0

        # Length counter - enable = length INCREMENT rate
        if self.length_enable and self.length != 0xFF:
            self.length_counter += 1
            # Length decrements at sample_rate / sample_clock ratio
            length_ratio = sample_rate / self.sample_clock
            if self.length_counter >= length_ratio:
                self.length_counter = 0
                self.length -= 1
                if self.length <= 0:
                    self.enabled = False
                    return 0

        # Advance sample timer
        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            self.counter += 1

        # Determine byte index based on format and counter
        # 4-bit: 16-bit words (2 bytes per sample, 8 samples per 32 bytes)
        # 8-bit: 8-bit bytes (1 byte per sample, 32 samples per 32 bytes)
        if self.format_8bit:
            byte_index = self.counter % 32
        else:
            word_index = self.counter // 2  # 2 bytes per 16-bit sample
            byte_index = (word_index * 2) % 32

        # Read sample data
        if self.format_8bit:
            sample = self.wave_ram[byte_index]
        else:
            # 4-bit mode: read high nibble for even counter, low for odd
            word_start = byte_index
            if self.counter % 2 == 0:
                sample = self.wave_ram[word_start] >> 4
            else:
                sample = self.wave_ram[word_start] & 0x0F

        # Convert to full byte and apply volume
        # 4-bit -> 8-bit: left shift and scale
        if not self.format_8bit:
            sample = (sample << 4) | (sample & 0x0F)
        
        # Apply volume: NR42 bits 6-7 (00=0%, 01=50%, 10=100%, 11=reserved)
        if self.volume == 0:  # 0%
            return 0
        elif self.volume == 1:  # 50%
            return sample >> 1
        elif self.volume == 2:  # 100%
            return sample
        else:  # Reserved, treat as 0%
            return 0

    def trigger(self):
        """Trigger the channel (key on) - reset counters and enable."""
        self.timer = 0
        self.counter = 0
        self.length_counter = 0
        self.enabled = True

    def write_wave_ram(self, data: bytes):
        """Write wave RAM data."""
        if len(data) == 32:
            self.wave_ram = list(data)

    def set_sample_rate(self, clock: int, div: int):
        """Set sample rate based on timer clock and divider.
        
        Args:
            clock: 131072, 8192, or 4096 (from NR43 bits 0-1)
            div: 1, 16, 64, or 1024 (from NR43 bits 4-6)
        """
        self.sample_clock = clock
        self.estimated_rate = clock // div

    def set_length(self, length: int):
        """Set length counter (0xFF = infinite)."""
        self.length = length if length != 0xFF else length
        self.length_enable = True

    def set_length_infinite(self):
        """Disable length counter."""
        self.length = 0xFF
        self.length_enable = True


class NoiseChannel:
    """Noise channel (CH4) - LFSR-based white noise generator with envelope.
    
    GBA CH4 is a noise generator used for percussion sounds and special effects.
    - 7-bit or 15-bit LFSR modes (NR43 bit 3)
    - Attack/decay envelope (NR42 bits 8-15, same as CH1/CH2)
    - Volume control: 0%, 50%, 100% (NR42 bits 6-7)
    - Length counter (64 samples, NR41 bits 0-5)
    - Timer-based clock rate (NR43 bits 0-6)
    
    LFSR Specifications:
    - 15-bit LFSR (default): Feedback from bit 14, output from bit 0
    - 7-bit LFSR (NR43 bit 3=1): Feedback from bit 1, output from bit 0
    - Both use taps XORed into MSB position
    """

    def __init__(self):
        self.enabled = False
        self.volume = 0  # NR42 bits 10-11: 00=0%, 01=50%, 10=100%, 11=reserved
        self.envelope_volume = 0  # NR42 bits 12-15: 4-bit envelope level (0-15)
        self.envelope_steps = 0  # NR42 bits 8-11: 4-bit period (0=continuous)
        self.envelope_increase = False  # NR42 bit 13: direction (increase/decrease)
        self.length = 0  # NR41 bits 0-5: 6-bit length value (64 - value = samples)
        self.length_enable = False  # NR41 bit 7
        self.length_counter = 0
        self.lfsr = 0x7FFF  # Initial 15-bit state (must have bit 0 = 1)
        self.width_7bit = False  # NR43 bit 3: 7-bit LFSR mode
        self.clock_shift = 0  # NR43 bits 0-2: 3-bit timer clock divisor (0-7)
        self.clock_divider = 0  # NR43 bits 4-6: 3-bit divider (1, 2, 8, 32)
        self.envelope_timer = 0  # Envelope step counter
        self.envelope_level = 0  # Current envelope level (0-15)
        self.timer = 0  # Noise timer (counts between LFSR advances)
        self.timer_period = 1  # Timer period (sample_rate / sample_clock)

    def step(self, sample_rate: int) -> int:
        """Generate one noise sample.
        
        GBA CH4 generates noise at a rate determined by the timer. Each timer tick
        advances the LFSR by one bit and produces one noise bit. The envelope
        controls the volume of this bit, and the length counter determines how
        long the noise continues before auto-disabling.
        
        Args:
            sample_rate: Target output sample rate (e.g., 44100)
            
        Returns:
            Sample value (0-255)
        """
        if not self.enabled:
            return 0
        
        # Length counter check - auto-disable when length expires
        # Length = 64 - NR41 value, so we decrement from (64 - value) samples
        if self.length_enable and self.length > 0:
            self.length_counter += 1
            length_samples = 64 - self.length
            if self.length_counter >= length_samples:
                self.length_counter = 0
                self.length -= 1
                if self.length <= 0:
                    self.enabled = False
                    return 0
        
        # Envelope (attack/decay - same as CH1/CH2)
        # Steps 0 means continuous (no envelope changes)
        if self.envelope_steps > 0:
            self.envelope_timer += 1
            if self.envelope_timer >= self.envelope_steps:
                self.envelope_timer = 0
                if self.envelope_increase:
                    self.envelope_level = min(15, self.envelope_level + 1)
                else:
                    self.envelope_level = max(0, self.envelope_level - 1)
                if self.envelope_level == 0:
                    self.enabled = False
                    return 0
        else:
            self.envelope_level = self.volume
        
        # Advance timer - LFSR advances once per timer period
        # Timer clock = sample_rate / (2 * clock_divider * 2^clock_shift)
        divisor = max(1, self.clock_divider)
        self.timer_period = (1 << self.clock_shift) * divisor
        if self.timer_period == 0:
            self.timer_period = 1
        
        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            
            # LFSR step - XOR feedback at specific taps based on width mode
            # LFSR generates pseudo-random noise by shifting and XORing feedback
            if self.width_7bit:
                # 7-bit LFSR: feedback from bit 1, output from bit 0
                # Polynomial: x^7 + x^2 + 1 (taps at positions 7 and 2)
                bit0 = self.lfsr & 1
                bit1 = (self.lfsr >> 1) & 1
                # Output bit (noise value)
                noise_bit = bit0
                # New MSB = old bit 0
                # Shift right and insert new bit at MSB
                self.lfsr = (self.lfsr >> 1) | bit0
                # Keep only 7 bits
                self.lfsr &= 0x7F
            else:
                # 15-bit LFSR: feedback from bit 14, output from bit 0
                # Polynomial: x^15 + x^14 + 1 (taps at positions 15 and 14)
                bit0 = self.lfsr & 1
                bit14 = (self.lfsr >> 14) & 1
                # Output bit (noise value)
                noise_bit = bit0
                # New MSB = old bit 0
                # Shift right and insert new bit at MSB
                self.lfsr = (self.lfsr >> 1) | bit0
                # Keep only 15 bits
                self.lfsr &= 0x7FFF
            
            # Convert noise bit (0 or 1) to sample value
            # GBA outputs single bit scaled to 0-255 range
            # 0 -> 0, 1 -> 255 (binary values)
            # Common practice: 0 -> 0, 1 -> 128 (centered) or 0 -> 0, 1 -> 255
            # Using 0/255 binary values for simplicity
            noise_sample = noise_bit * 255
        
        # Apply envelope level (0-15) to noise sample
        # GBA envelope level scales the output linearly
        # Level 0 = silent, Level 15 = full volume
        # Scale envelope to match volume settings:
        # volume 0% -> 0, volume 50% -> 0-127, volume 100% -> 0-255
        envelope_scale = self.envelope_level / 15.0
        result = int(noise_sample * envelope_scale)
        
        return result

    def trigger(self):
        """Trigger the channel (key on) - reset counters and enable.
        
        When triggered:
        - LFSR resets to 0x7FFF (15-bit) or 0x01 (7-bit)
        - All counters reset (timer, envelope, length)
        - Channel enabled
        """
        if self.width_7bit:
            # 7-bit LFSR needs odd initial state (bit 0 = 1)
            self.lfsr = 0x01
        else:
            # 15-bit LFSR needs odd initial state (bit 0 = 1)
            self.lfsr = 0x7FFF
        
        self.timer = 0
        self.timer_period = (1 << self.clock_shift) * max(1, self.clock_divider)
        self.noise_counter = 0
        self.envelope_timer = 0
        self.envelope_level = self.envelope_volume
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
        self.ch1 = PulseWaveChannel(channel_id=1)
        self.ch2 = PulseWaveChannel(channel_id=2)
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
        elif addr == 0x04000070:
            self.ch3.wave_bank = (value >> 5) & 0x01
            self.ch3.enabled = bool(value & 0x80)
        elif addr == 0x04000072:
            self.ch3.length = value & 0xFF
            if self.ch3.length == 0xFF:
                self.ch3.set_length_infinite()
            else:
                self.ch3.set_length(value & 0xFF)
        elif addr == 0x04000074:
            volume_shift = (value >> 8) & 0x03
            self.ch3.volume = 0 if volume_shift == 0 else (1 if volume_shift == 1 else (2 if volume_shift == 2 else 3))
            self.ch3.format_8bit = bool(value & 0x0400)
            self.ch3.frequency = value & 0x3FF
            if value & 0x8000:
                self.ch3.trigger()
        elif addr == 0x04000078:  # NR41: Noise Length and EN interrupt
            self.ch4.length = value & 0x3F  # bits 0-5
            self.ch4.length_enable = bool(value & 0x40)  # bit 7
        elif addr == 0x0400007A:  # NR42: Noise Envelope
            self.ch4.envelope_volume = (value >> 12) & 0x0F  # bits 12-15: level
            self.ch4.envelope_steps = value & 0x0F  # bits 0-3: period
            self.ch4.envelope_increase = bool(value & 0x0800)  # bit 11: attack vs decay
            if value & 0x4000:  # bit 14: key on/off
                self.ch4.trigger()
        elif addr == 0x0400007C:  # NR43: Noise Freq and Control
            self.ch4.clock_shift = (value >> 4) & 0x0F  # bits 4-7: timer divisor (0-15)
            self.ch4.clock_divider = value & 0x07  # bits 0-2: divider (1, 2, 8, 32)
            self.ch4.width_7bit = bool(value & 0x08)  # bit 3: 7-bit mode
            if value & 0x8000:  # bit 15: key on/off
                self.ch4.trigger()
        elif addr == 0x0400007E:  # NR44: Noise/IRQ Control
            self.ch4.volume = (value >> 10) & 0x03  # bits 10-11: volume (0%, 50%, 100%)
            self.ch4_enabled = bool(value & 0x80)  # bit 7: sound 4 on/off
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
            if self.ch3_enabled:
                ch3.dma_fifo = self
            self.ch4_enabled = bool(value & 0x0008)
            if self.ch4_enabled:
                ch4.dma_fifo = self
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
