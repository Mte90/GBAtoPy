pub fn generate_apu_code() -> String {
    r#"
"""GBA APU (Audio Processing Unit) - Pure Python implementation for GBAtoPy

This module handles GBA audio playback:
- CH1: Square wave with frequency sweep
- CH2: Square wave (no sweep)
- CH3: Wave RAM sample playback (8-bit or 4-bit)
- CH4: White noise generator

Sound registers: 0x04000060-0x0400008F
- SOUND1CNT_L (0x60): Sweep settings
- SOUND1CNT_H (0x64): Volume, envelope
- SOUND1CNT_X (0x68): Frequency, loop
- SOUND2CNT_L (0x6C): Volume, envelope  
- SOUND2CNT_H (0x70): Frequency, loop
- SOUND3CNT_L (0x74): Wave RAM bank, volume
- SOUND3CNT_H (0x78): Length, frequency
- SOUND3CNT_X (0x7C): Enable
- SOUND4CNT_L (0x80): Volume, envelope
- SOUND4CNT_H (0x84): Frequency, loop
- SOUNDCNT_L (0x80): Master volume, enable bits
- SOUNDCNT_H (0x82): Sound 1-4 enable
- SOUNDCNT_X (0x88): Master enable

Audio output via pygame.mixer in background thread.
"""

import pygame
import threading
import math
import time
import array
import wave
import io

# Sound register addresses
SOUND1_CNT_L = 0x04000060  # Sweep
SOUND1_CNT_H = 0x04000064  # Volume, envelope
SOUND1_CNT_X = 0x04000068  # Frequency, control

SOUND2_CNT_L = 0x0400006C
SOUND2_CNT_H = 0x04000070

SOUND3_CNT_L = 0x04000074
SOUND3_CNT_H = 0x04000078
SOUND3_CNT_X = 0x0400007C

SOUND4_CNT_L = 0x04000080
SOUND4_CNT_H = 0x04000084

SOUND_CNT_L = 0x04000080  # Master volume
SOUND_CNT_H = 0x04000082  # Channel enable
SOUND_CNT_X = 0x04000088  # Master enable

WAVE_RAM = 0x04000090  # 32 bytes (4 banks of 8 bytes)

# Register bit masks
SOUND_ENABLE_1 = 0x0001
SOUND_ENABLE_2 = 0x0002
SOUND_ENABLE_3 = 0x0004
SOUND_ENABLE_4 = 0x0008

class APU:
    """GBA Audio Processing Unit emulator"""
    
    def __init__(self, memory):
        """Initialize APU with GBA memory object"""
        self.memory = memory
        self.sample_rate = 44100
        self.channels = [None, None, None, None]  # pygame.mixer.Channel objects
        self.sounds = [None, None, None, None]   # pygame.mixer.Sound objects
        self.channel_enabled = [False, False, False, False]
        self.wave_ram = bytearray(32)
        
        # Sound register state
        self.sound1_cnt_l = 0  # Sweep
        self.sound1_cnt_h = 0  # Volume, envelope
        self.sound1_cnt_x = 0  # Frequency
        self.sound2_cnt_l = 0
        self.sound2_cnt_h = 0
        self.sound3_cnt_l = 0
        self.sound3_cnt_h = 0
        self.sound3_cnt_x = 0
        self.sound4_cnt_l = 0
        self.sound4_cnt_h = 0
        self.sound_cnt_l = 0
        self.sound_cnt_h = 0
        self.sound_cnt_x = 0
        
        # Initialize pygame.mixer
        self._init_mixer()
        
        # Background thread for audio
        self.running = True
        self.audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.audio_thread.start()
    
    def _init_mixer(self):
        """Initialize pygame.mixer"""
        try:
            pygame.mixer.init(frequency=self.sample_rate, 
                            size=-16, 
                            channels=2, 
                            buffer=512)
        except pygame.error:
            print("Warning: Could not initialize pygame.mixer")
            self.sample_rate = 0
    
    def write_register(self, addr, value):
        """Handle MMIO write to sound registers"""
        if self.sample_rate == 0:
            return
            
        if addr == SOUND1_CNT_L:
            self.sound1_cnt_l = value & 0xFFFF
        elif addr == SOUND1_CNT_H:
            self.sound1_cnt_h = value & 0xFFFF
        elif addr == SOUND1_CNT_X:
            self.sound1_cnt_x = value & 0xFFFF
            self._update_channel(0)
        elif addr == SOUND2_CNT_L:
            self.sound2_cnt_l = value & 0xFFFF
        elif addr == SOUND2_CNT_H:
            self.sound2_cnt_h = value & 0xFFFF
            self._update_channel(1)
        elif addr == SOUND3_CNT_L:
            self.sound3_cnt_l = value & 0xFFFF
        elif addr == SOUND3_CNT_H:
            self.sound3_cnt_h = value & 0xFFFF
        elif addr == SOUND3_CNT_X:
            self.sound3_cnt_x = value & 0xFFFF
            self._update_channel(2)
        elif addr == SOUND4_CNT_L:
            self.sound4_cnt_l = value & 0xFFFF
        elif addr == SOUND4_CNT_H:
            self.sound4_cnt_h = value & 0xFFFF
            self._update_channel(3)
        elif addr == SOUND_CNT_H:
            self.sound_cnt_h = value & 0xFFFF
            self._update_master_enable()
        elif addr == SOUND_CNT_X:
            self.sound_cnt_x = value & 0xFFFF
        elif WAVE_RAM <= addr < WAVE_RAM + 32:
            # Wave RAM write
            idx = addr - WAVE_RAM
            self.wave_ram[idx] = value & 0xFF
    
    def _update_master_enable(self):
        """Update which channels are enabled"""
        self.channel_enabled[0] = bool(self.sound_cnt_h & SOUND_ENABLE_1)
        self.channel_enabled[1] = bool(self.sound_cnt_h & SOUND_ENABLE_2)
        self.channel_enabled[2] = bool(self.sound_cnt_h & SOUND_ENABLE_3)
        self.channel_enabled[3] = bool(self.sound_cnt_h & SOUND_ENABLE_4)
    
    def _update_channel(self, ch):
        """Update audio for a specific channel"""
        if not self.channel_enabled[ch] or self.sample_rate == 0:
            return
        
        # Stop existing sound
        if self.sounds[ch] is not None:
            try:
                self.sounds[ch].stop()
            except:
                pass
        
        # Generate sound based on channel type
        if ch == 0:
            self._play_channel1()
        elif ch == 1:
            self._play_channel2()
        elif ch == 2:
            self._play_channel3()
        elif ch == 3:
            self._play_channel4()
    
    def _play_channel1(self):
        """CH1: Square wave with frequency sweep"""
        # Get frequency from SOUND1_CNT_X (11-bit frequency)
        freq = 131072 / (2048 - (self.sound1_cnt_x & 0x7FF))
        
        # Get volume from SOUND1_CNT_H (7-bit volume)
        volume = ((self.sound1_cnt_h >> 8) & 0x7F) / 127.0
        
        # Generate square wave with sweep
        samples = self._generate_square_wave(freq, volume, 0.5)
        self._play_sound(0, samples)
    
    def _play_channel2(self):
        """CH2: Square wave (no sweep)"""
        freq = 131072 / (2048 - (self.sound2_cnt_h & 0x7FF))
        volume = ((self.sound2_cnt_l >> 8) & 0x7F) / 127.0
        
        samples = self._generate_square_wave(freq, volume, 0.5)
        self._play_sound(1, samples)
    
    def _play_channel3(self):
        """CH3: Wave RAM sample playback"""
        # Get frequency from SOUND3_CNT_H (11-bit frequency)
        freq = 131072 / (2048 - (self.sound3_cnt_h & 0x7FF))
        
        # Get volume from SOUND3_CNT_L
        volume = ((self.sound3_cnt_l >> 11) & 0x07) / 7.0
        
        # Generate wave from Wave RAM
        samples = self._generate_wave_ram(freq, volume)
        self._play_sound(2, samples)
    
    def _play_channel4(self):
        """CH4: White noise generator"""
        # Get frequency from SOUND4_CNT_H (7-bit, special encoding)
        freq = 524288 / (2048 - ((self.sound4_cnt_h & 0x7) << 8 | (self.sound4_cnt_h >> 8) & 0xFF))
        
        # Get volume from SOUND4_CNT_L
        volume = ((self.sound4_cnt_l >> 12) & 0x07) / 7.0
        
        samples = self._generate_noise(freq, volume)
        self._play_sound(3, samples)
    
    def _generate_square_wave(self, freq, volume, duty=0.5):
        """Generate square wave samples"""
        duration = 0.1  # 100ms
        num_samples = int(self.sample_rate * duration)
        samples = array.array('h')
        
        samples_per_cycle = self.sample_rate / freq
        samples_high = int(samples_per_cycle * duty)
        
        amplitude = int(32767 * volume * 0.5)
        
        for i in range(num_samples):
            cycle_pos = i % int(samples_per_cycle)
            if cycle_pos < samples_high:
                samples.append(amplitude)
            else:
                samples.append(-amplitude)
        
        return samples
    
    def _generate_wave_ram(self, freq, volume):
        """Generate wave from Wave RAM data"""
        duration = 0.1
        num_samples = int(self.sample_rate * duration)
        samples = array.array('h')
        
        # Wave RAM is 32 bytes, interpreted as 16 4-bit samples (doubled to 8-bit)
        wave_data = []
        for i in range(0, 32, 2):
            if i + 1 < len(self.wave_ram):
                # Each pair of bytes is one 8-bit sample
                wave_data.append(self.wave_ram[i])
        
        if not wave_data:
            wave_data = [128] * 16
        
        # Repeat pattern
        samples_per_sample = int(self.sample_rate / freq / len(wave_data))
        amplitude = int(32767 * volume * 0.5)
        
        for _ in range(num_samples):
            idx = int((_ / samples_per_sample) % len(wave_data))
            val = wave_data[idx] - 128  # Convert to signed
            samples.append(int(val / 127.0 * amplitude))
        
        return samples
    
    def _generate_noise(self, freq, volume):
        """Generate white noise"""
        duration = 0.1
        num_samples = int(self.sample_rate * duration)
        samples = array.array('h')
        
        import random
        amplitude = int(32767 * volume * 0.5)
        
        # Simple noise: pseudo-random values
        rng_state = int(freq) & 0xFFFF
        for i in range(num_samples):
            rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
            val = ((rng_state >> 16) & 0xFF) - 128
            samples.append(int(val / 127.0 * amplitude))
        
        return samples
    
    def _play_sound(self, ch, samples):
        """Play a sound on a channel"""
        if self.sample_rate == 0 or not samples:
            return
            
        try:
            # Convert to stereo 16-bit
            stereo_samples = array.array('h')
            for s in samples:
                stereo_samples.append(s)
                stereo_samples.append(s)
            
            # Create sound from samples
            sound = pygame.mixer.Sound(buffer=stereo_samples)
            sound.set_volume(0.5)
            
            # Reserve channel
            if ch < 4:
                try:
                    channel = pygame.mixer.Channel(ch)
                    channel.play(sound, loops=-1)
                    self.sounds[ch] = sound
                except pygame.error:
                    pass
        except Exception as e:
            print(f"Warning: Could not play sound on channel {ch}: {e}")
    
    def _audio_loop(self):
        """Background thread for audio updates"""
        while self.running:
            time.sleep(0.01)  # 10ms update interval
    
    def shutdown(self):
        """Shutdown audio thread and release resources"""
        self.running = False
        for ch in range(4):
            if self.sounds[ch] is not None:
                try:
                    self.sounds[ch].stop()
                except:
                    pass


def get_apu(memory):
    """Get or create global APU instance"""
    global _apu_instance
    if _apu_instance is None:
        _apu_instance = APU(memory)
    return _apu_instance


_apu_instance = None
"#
    .to_string()
}
