import pytest
from gba_runtime.apu import APU, SquareWaveChannel, WaveChannel, NoiseChannel, FIFO


def test_apu_init():
    apu = APU()
    assert apu is not None
    assert apu.ch1 is not None
    assert apu.ch2 is not None
    assert apu.ch3 is not None
    assert apu.ch4 is not None
    assert apu.fifo_a is not None
    assert apu.fifo_b is not None


def test_apu_step():
    apu = APU()
    apu.step()
    assert True


def test_apu_get_sample():
    apu = APU()
    sample = apu.get_sample()
    assert isinstance(sample, int)
    assert 0 <= sample <= 15


def test_square_wave_channel():
    ch = SquareWaveChannel()
    ch.enabled = True
    ch.volume = 10
    ch.duty_cycle = 2
    ch.frequency = 512
    sample = ch.step(262144)
    assert sample >= 0


def test_wave_channel():
    ch = WaveChannel()
    ch.enabled = True
    ch.volume = 8
    ch.frequency = 256
    ch.wave_ram = [0x12, 0x34] * 16
    sample = ch.step(262144)
    assert sample >= 0


def test_noise_channel():
    ch = NoiseChannel()
    ch.enabled = True
    ch.volume = 5
    ch.clock_shift = 4
    ch.clock_divider = 1
    sample = ch.step(262144)
    assert sample >= 0


def test_fifo():
    fifo = FIFO()
    fifo.write(0xAB)
    fifo.write(0xCD)
    assert len(fifo.data) == 2
    assert fifo.read() == 0xAB
    assert fifo.read() == 0xCD


def test_write_register_ch1():
    apu = APU()
    apu.write_register(0x04000060, 0x12)
    apu.write_register(0x04000062, 0xC0)
    apu.write_register(0x04000064, 0x8000)
    assert apu.ch1.duty_cycle == 3


def test_write_register_ch2():
    apu = APU()
    apu.write_register(0x04000068, 0x80)
    apu.write_register(0x0400006A, 0xF000)
    apu.write_register(0x0400006C, 0x8000)
    assert apu.ch2.enabled == True


def test_write_register_ch3():
    apu = APU()
    apu.write_register(0x04000070, 0x80)
    apu.write_register(0x04000072, 0xFF)
    apu.write_register(0x04000074, 0x8000)
    assert apu.ch3.enabled == True


def test_write_register_ch4():
    apu = APU()
    apu.write_register(0x04000078, 0x20)
    apu.write_register(0x0400007A, 0xF000)
    apu.write_register(0x0400007C, 0x8000)
    assert apu.ch4.enabled == True


def test_write_register_sound_control():
    apu = APU()
    apu.write_register(0x04000080, 0x32)
    apu.write_register(0x04000082, 0x0203)
    apu.write_register(0x04000084, 0x0C0F)
    assert apu.master_volume_left == 2
    assert apu.master_volume_right == 3
    assert apu.ch1_enabled == True
    assert apu.ch2_enabled == True


def test_write_fifo_a():
    apu = APU()
    apu.write_register(0x040000A0, 0x42)
    assert len(apu.fifo_a.data) == 1
    assert apu.fifo_a.data[0] == 0x42


def test_write_fifo_b():
    apu = APU()
    apu.write_register(0x040000A4, 0xAB)
    assert len(apu.fifo_b.data) == 1
    assert apu.fifo_b.data[0] == 0xAB


def test_write_wave_ram():
    apu = APU()
    apu.write_register(0x04000090, 0x12)
    apu.write_register(0x04000091, 0x34)
    assert apu.wave_ram[0][0] == 0x12
    assert apu.wave_ram[0][1] == 0x34


def test_read_register_fifo_a():
    apu = APU()
    apu.write_register(0x040000A0, 0x42)
    val = apu.read_register(0x040000A0)
    assert val == 0x42


def test_read_register_fifo_b():
    apu = APU()
    apu.write_register(0x040000A4, 0xAB)
    val = apu.read_register(0x040000A4)
    assert val == 0xAB


def test_read_register_wave_ram():
    apu = APU()
    apu.write_register(0x04000090, 0x55)
    val = apu.read_register(0x04000090)
    assert val == 0x55


def test_channel_trigger():
    apu = APU()
    apu.write_register(0x04000064, 0x8000)
    assert apu.ch1.enabled == True
    apu.ch1.enabled = False

    apu.write_register(0x0400006C, 0x8000)
    assert apu.ch2.enabled == True
    apu.ch2.enabled = False

    apu.write_register(0x04000074, 0x8000)
    assert apu.ch3.enabled == True
    apu.ch3.enabled = False

    apu.write_register(0x0400007C, 0x8000)
    assert apu.ch4.enabled == True
