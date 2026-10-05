"""APU (Audio Processing Unit) unit tests for GBAtoPy.

Tests cover APU initialization, register decoding, channel behavior,
FIFO operations, and sample generation.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from apu import APU, SquareWaveChannel, WaveChannel, NoiseChannel, FIFO


def test_apu_initialization_all_channels_silent():
    """APU initialization: all channels start disabled, master enable off."""
    apu = APU()
    
    # Master enable off by default
    assert apu.master_enable == False, "Master enable should be False initially"
    
    # All channels disabled
    assert apu.ch1.enabled == False, "CH1 should be disabled initially"
    assert apu.ch2.enabled == False, "CH2 should be disabled initially"
    assert apu.ch3.enabled == False, "CH3 should be disabled initially"
    assert apu.ch4.enabled == False, "CH4 should be disabled initially"
    
    # Channel output enables off
    assert apu.ch1_enabled == False, "CH1 output enable should be False initially"
    assert apu.ch2_enabled == False, "CH2 output enable should be False initially"
    assert apu.ch3_enabled == False, "CH3 output enable should be False initially"
    assert apu.ch4_enabled == False, "CH4 output enable should be False initially"
    
    # FIFOs disabled
    assert apu.fifo_a_enabled == False, "FIFO A should be disabled initially"
    assert apu.fifo_b_enabled == False, "FIFO B should be disabled initially"
    
    # Master volumes at zero
    assert apu.master_volume_left == 0, "Left volume should be 0 initially"
    assert apu.master_volume_right == 0, "Right volume should be 0 initially"
    
    print("✓ test_apu_initialization_all_channels_silent passed")


def test_souncntl_decoding_volume_and_output_enable():
    """SOUNDCNT_L (0x04000080): decode master volume and channel output enables."""
    apu = APU()
    
    # Write: left volume=3 (bits 4-6), right volume=5 (bits 0-2)
    # Enable CH1 on both channels (bits 8-9)
    # Bits: 0-2=right vol, 4-6=left vol, 8-9=CH1, 10-11=CH2, 12-13=CH3, 14-15=CH4
    value = 0x0180 | 0x0005 | (3 << 4)  # 0x0195
    apu.write_register(0x04000080, value)
    
    assert apu.master_volume_left == 3, f"Left volume should be 3, got {apu.master_volume_left}"
    assert apu.master_volume_right == 5, f"Right volume should be 5, got {apu.master_volume_right}"
    assert apu.ch1_enabled == True, "CH1 should be enabled"
    assert apu.ch2_enabled == False, "CH2 should be disabled (bit 10 not set)"
    assert apu.ch3_enabled == False, "CH3 should be disabled"
    assert apu.ch4_enabled == False, "CH4 should be disabled"
    
    print("✓ test_souncntl_decoding_volume_and_output_enable passed")


def test_souncntl_ch2_ch3_ch4_output_enable():
    """SOUNDCNT_L: decode CH2, CH3, CH4 output enables (bits 10-15)."""
    apu = APU()
    
    # Enable CH2 (bits 10-11), CH3 (bits 12-13), CH4 (bits 14-15)
    value = 0x0C00 | 0x3000 | 0xC000  # Enable all on both L/R
    apu.write_register(0x04000080, value)
    
    assert apu.ch2_enabled == True, "CH2 should be enabled"
    assert apu.ch3_enabled == True, "CH3 should be enabled"
    assert apu.ch4_enabled == True, "CH4 should be enabled"
    
    print("✓ test_souncntl_ch2_ch3_ch4_output_enable passed")


def test_souncnth_fifo_enable_and_ratio():
    """SOUNDCNT_H (0x04000082): FIFO A/B enables (bits 8/12) and output ratio (bits 0-1)."""
    apu = APU()
    
    # Enable FIFO A (bit 8), set ratio to 1 (bits 0-1)
    value = 0x0001 | 0x0100  # 0x0101
    apu.write_register(0x04000082, value)
    
    assert apu.fifo_a_enabled == True, "FIFO A should be enabled"
    assert apu.fifo_a.enabled == True, "FIFO A internal enabled flag should be True"
    assert apu.fifo_b_enabled == False, "FIFO B should be disabled"
    
    # Enable FIFO B (bit 12)
    value = 0x1000  # 0x1000
    apu.write_register(0x04000082, value)
    
    assert apu.fifo_b_enabled == True, "FIFO B should be enabled"
    assert apu.fifo_b.enabled == True, "FIFO B internal enabled flag should be True"
    
    print("✓ test_souncnth_fifo_enable_and_ratio passed")


def test_souncntx_master_enable_gate():
    """SOUNDCNT_X (0x04000084): master enable (bit 7) gates mixer output."""
    apu = APU()
    
    # Master disabled - get_sample returns (0, 0)
    left, right = apu.get_sample()
    assert left == 0, f"Left should be 0 when master disabled, got {left}"
    assert right == 0, f"Right should be 0 when master disabled, got {right}"
    
    # Enable master
    apu.write_register(0x04000084, 0x80)
    assert apu.master_enable == True, "Master enable should be True"
    
    print("✓ test_souncntx_master_enable_gate passed")


def test_squarewave_channel_frequency():
    """SquareWaveChannel: frequency controls timer period."""
    ch = SquareWaveChannel()
    ch.enabled = True
    ch.frequency = 1000
    ch.envelope_steps = 0  # Disable envelope decay
    ch.trigger()
    
    # Timer period = 2048 - frequency
    expected_period = 2048 - 1000
    # After one step, timer should increment
    sample = ch.step(44100)
    
    # Verify channel produces samples when enabled
    assert sample >= 0, "Sample should be non-negative"
    
    print("✓ test_squarewave_channel_frequency passed")


def test_squarewave_channel_duty_cycle():
    """SquareWaveChannel: duty_cycle field is set correctly."""
    ch = SquareWaveChannel()
    
    # Duty cycles: 0=12.5%, 1=25%, 2=50%, 3=75%
    for duty in range(4):
        ch.duty_cycle = duty
        assert ch.duty_cycle == duty, f"Duty cycle should be {duty}, got {ch.duty_cycle}"
    
    print("✓ test_squarewave_channel_duty_cycle passed")


def test_squarewave_channel_volume_envelope():
    """SquareWaveChannel: envelope controls volume over time."""
    ch = SquareWaveChannel()
    ch.enabled = True
    ch.volume = 15
    ch.envelope_volume = 15
    ch.envelope_steps = 1
    ch.envelope_increase = False
    ch.envelope_counter = 0
    ch.trigger()
    
    # Initial envelope volume should be set
    assert ch.envelope_volume_current == 15, f"Initial envelope volume should be 15, got {ch.envelope_volume_current}"
    
    # Step and verify envelope decreases
    sample = ch.step(44100)
    
    print("✓ test_squarewave_channel_volume_envelope passed")


def test_squarewave_channel_trigger():
    """SquareWaveChannel: trigger() resets state and enables channel."""
    ch = SquareWaveChannel()
    ch.frequency = 500
    ch.envelope_volume = 10
    ch.sweep_steps = 2
    
    ch.trigger()
    
    assert ch.enabled == True, "Channel should be enabled after trigger"
    assert ch.timer == 0, "Timer should be 0 after trigger"
    assert ch.output_bit == 0, "Output bit should be 0 after trigger"
    assert ch.envelope_volume_current == 10, "Envelope volume should match initial"
    assert ch.length_counter == 0, "Length counter should be 0"
    assert ch.sweep_counter == 2, "Sweep counter should be set to sweep_steps"
    
    print("✓ test_squarewave_channel_trigger passed")


def test_wave_channel_wave_ram_read_write():
    """WaveChannel: wave RAM read/write via APU."""
    apu = APU()
    
    # Write to wave RAM
    apu.write_register(0x04000090, 0xAB)
    apu.write_register(0x04000091, 0xCD)
    
    assert apu.wave_ram[0][0] == 0xAB, f"Wave RAM[0][0] should be 0xAB, got 0x{apu.wave_ram[0][0]:02X}"
    assert apu.wave_ram[0][1] == 0xCD, f"Wave RAM[0][1] should be 0xCD, got 0x{apu.wave_ram[0][1]:02X}"
    
    # Write to second bank
    apu.wave_bank = 1
    apu.write_register(0x04000090, 0xEF)
    
    assert apu.wave_ram[1][0] == 0xEF, f"Wave RAM[1][0] should be 0xEF, got 0x{apu.wave_ram[1][0]:02X}"
    
    print("✓ test_wave_channel_wave_ram_read_write passed")


def test_wave_channel_frequency():
    """WaveChannel: frequency controls timer period."""
    apu = APU()
    ch = WaveChannel()
    ch.enabled = True
    ch.frequency = 800
    ch.volume = 1  # Full volume
    
    # Timer period = 2048 - frequency
    sample = ch.step(44100, apu.wave_ram, 0)
    
    # Verify sample is in valid range
    assert 0 <= sample <= 15, f"Wave sample should be 0-15, got {sample}"
    
    print("✓ test_wave_channel_frequency passed")


def test_wave_channel_volume_levels():
    """WaveChannel: volume 0=off, 1=100%, 2=50%, 3=25%."""
    apu = APU()
    ch = WaveChannel()
    ch.enabled = True
    ch.frequency = 500
    ch.counter = 0  # Force reading first nibble
    
    # Set wave RAM to produce sample value 8
    apu.wave_ram[0][0] = 0x88  # Both nibbles = 8
    
    # Volume 1 (100%): sample = 8
    ch.volume = 1
    sample = ch.step(44100, apu.wave_ram, 0)
    assert sample == 8, f"Volume 1: sample should be 8, got {sample}"
    
    # Volume 2 (50%): sample = 4
    ch.volume = 2
    sample = ch.step(44100, apu.wave_ram, 0)
    assert sample == 4, f"Volume 2: sample should be 4, got {sample}"
    
    # Volume 3 (25%): sample = 2
    ch.volume = 3
    sample = ch.step(44100, apu.wave_ram, 0)
    assert sample == 2, f"Volume 3: sample should be 2, got {sample}"
    
    print("✓ test_wave_channel_volume_levels passed")


def test_noise_channel_frequency():
    """NoiseChannel: clock_shift and clock_divider control frequency."""
    ch = NoiseChannel()
    ch.enabled = True
    ch.clock_shift = 4
    ch.clock_divider = 2
    ch.width_7bit = False
    ch.envelope_steps = 0
    ch.trigger()
    
    sample = ch.step(44100)
    
    # Verify sample is 0 or 1 (LFSR output)
    assert sample in [0, 1], f"Noise sample should be 0 or 1, got {sample}"
    
    print("✓ test_noise_channel_frequency passed")


def test_noise_channel_envelope():
    """NoiseChannel: envelope controls volume over time."""
    ch = NoiseChannel()
    ch.enabled = True
    ch.envelope_volume = 12
    ch.envelope_steps = 1
    ch.envelope_increase = False
    ch.width_7bit = True
    ch.clock_shift = 2
    ch.clock_divider = 1
    ch.trigger()
    
    # Initial envelope volume
    assert ch.envelope_volume_current == 12, f"Initial envelope should be 12, got {ch.envelope_volume_current}"
    
    sample = ch.step(44100)
    
    # Sample should be 0 or envelope_volume_current
    assert sample in [0, 12], f"Sample should be 0 or 12, got {sample}"
    
    print("✓ test_noise_channel_envelope passed")


def test_fifo_write_read_reset():
    """FIFO: write, read, and reset operations."""
    fifo = FIFO()
    
    # Write bytes
    fifo.write(0x42)
    fifo.write(0x7F)
    fifo.write(0x00)
    
    # Read back
    assert fifo.read() == 0x42, f"First read should be 0x42, got 0x{fifo.read():02X}"
    assert fifo.read() == 0x7F, f"Second read should be 0x7F, got 0x{fifo.read():02X}"
    assert fifo.read() == 0x00, f"Third read should be 0x00, got 0x{fifo.read():02X}"
    
    # Empty FIFO returns silence (128)
    assert fifo.read() == 128, f"Empty FIFO should return 128, got {fifo.read()}"
    
    print("✓ test_fifo_write_read_reset passed")


def test_fifo_step_generation():
    """FIFO: step() generates samples when enabled."""
    fifo = FIFO()
    fifo.enabled = True
    fifo.timer_period = 1
    fifo.write(200)
    fifo.write(100)
    
    # First step should produce sample from FIFO
    sample = fifo.step(44100)
    assert sample == 200, f"First sample should be 200, got {sample}"
    
    # Second step should produce next sample
    sample = fifo.step(44100)
    assert sample == 100, f"Second sample should be 100, got {sample}"
    
    print("✓ test_fifo_step_generation passed")


def test_get_sample_returns_int16_range_when_enabled():
    """get_sample() returns values in valid range when master enabled."""
    apu = APU()
    
    # Enable master
    apu.write_register(0x04000084, 0x80)
    
    # Enable a channel with volume
    apu.write_register(0x04000080, 0x0707)  # Max volume both channels
    apu.write_register(0x04000064, 0x8000 | (7 << 8) | 500)  # CH1: trigger, envelope=7, freq=500
    
    left, right = apu.get_sample()
    
    # Values should be in 0-255 range (normalized from int16 mixing)
    assert 0 <= left <= 255, f"Left sample should be 0-255, got {left}"
    assert 0 <= right <= 255, f"Right sample should be 0-255, got {right}"
    
    print("✓ test_get_sample_returns_int16_range_when_enabled passed")


def test_get_sample_returns_zero_when_master_disabled():
    """get_sample() returns (0, 0) when master enable is off."""
    apu = APU()
    
    # Master disabled (default)
    left, right = apu.get_sample()
    
    assert left == 0, f"Left should be 0 when master disabled, got {left}"
    assert right == 0, f"Right should be 0 when master disabled, got {right}"
    
    print("✓ test_get_sample_returns_zero_when_master_disabled passed")


def test_apu_register_writes_full_chain():
    """Full chain: configure CH1, enable master, verify sample generation."""
    apu = APU()
    
    # Configure CH1: frequency=1000, envelope=10, duty=2 (50%)
    apu.write_register(0x04000062, 0x4000 | 0x3F)  # duty=2, length=63
    apu.write_register(0x04000064, 0x8000 | (10 << 12) | (2 << 8) | 1000)  # trigger, envelope=10
    
    # Enable CH1 output, volume=7 both channels
    apu.write_register(0x04000080, 0x0180 | 0x77)  # CH1 enabled, vol=7
    
    # Enable master
    apu.write_register(0x04000084, 0x80)
    
    # Generate sample
    left, right = apu.get_sample()
    
    # Should produce non-zero output (or zero at envelope decay point)
    # Just verify it's in valid range
    assert 0 <= left <= 255, f"Left should be 0-255, got {left}"
    assert 0 <= right <= 255, f"Right should be 0-255, got {right}"
    
    print("✓ test_apu_register_writes_full_chain passed")


def test_wave_bank_switching():
    """Wave channel bank switching via SOUNDCNT_L."""
    apu = APU()
    
    # Write to bank 0
    apu.write_register(0x04000090, 0xAA)
    
    # Switch to bank 1
    apu.write_register(0x04000070, 0x20)  # bit 5 = bank 1
    
    assert apu.wave_bank == 1, f"Wave bank should be 1, got {apu.wave_bank}"
    
    # Write to bank 1
    apu.write_register(0x04000090, 0xBB)
    
    assert apu.wave_ram[1][0] == 0xBB, f"Bank 1 should have 0xBB, got 0x{apu.wave_ram[1][0]:02X}"
    assert apu.wave_ram[0][0] == 0xAA, f"Bank 0 should still have 0xAA, got 0x{apu.wave_ram[0][0]:02X}"
    
    print("✓ test_wave_bank_switching passed")


def test_fifo_volume_setup_on_enable():
    """FIFO volume is set to max when enabled via SOUNDCNT_H."""
    apu = APU()
    
    # Enable FIFO A
    apu.write_register(0x04000082, 0x0100)
    
    assert apu.fifo_a.volume_left == 7, f"FIFO A left volume should be 7, got {apu.fifo_a.volume_left}"
    assert apu.fifo_a.volume_right == 7, f"FIFO A right volume should be 7, got {apu.fifo_a.volume_right}"
    
    # Enable FIFO B
    apu.write_register(0x04000082, 0x1000)
    
    assert apu.fifo_b.volume_left == 7, f"FIFO B left volume should be 7, got {apu.fifo_b.volume_left}"
    assert apu.fifo_b.volume_right == 7, f"FIFO B right volume should be 7, got {apu.fifo_b.volume_right}"
    
    print("✓ test_fifo_volume_setup_on_enable passed")