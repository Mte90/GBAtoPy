import pytest
from gba_runtime.timers import Timers, TimerChannel


def test_timers_init():
    tmr = Timers()
    assert len(tmr.channels) == 4


def test_step_basic():
    tmr = Timers()
    tmr.set_control(0, 0x80)
    tmr.step(1)
    assert tmr.get_timer(0) == 0


def test_get_timer():
    tmr = Timers()
    tmr.set_timer(0, 100)
    assert tmr.get_timer(0) == 100


def test_set_timer():
    tmr = Timers()
    tmr.set_timer(0, 0x1234)
    assert tmr.get_timer(0) == 0x1234


def test_set_control():
    tmr = Timers()
    tmr.set_control(0, 0xFF)
    assert tmr.get_control(0) == 0xFF


def test_set_reload():
    tmr = Timers()
    tmr.set_reload(0, 0xABCD)
    assert tmr.get_reload(0) == 0xABCD


def test_invalid_channel():
    tmr = Timers()
    with pytest.raises(ValueError):
        tmr.get_timer(4)
    with pytest.raises(ValueError):
        tmr.set_timer(4, 0)


def test_prescaler_1():
    tmr = Timers()
    tmr.set_control(0, 0x80)
    tmr.set_timer(0, 0)
    tmr.set_reload(0, 0)
    tmr.step(10)
    assert tmr.get_timer(0) == 10


def test_prescaler_64():
    tmr = Timers()
    tmr.set_control(0, 0x81)
    tmr.set_timer(0, 0)
    tmr.set_reload(0, 0)
    tmr.step(64)
    assert tmr.get_timer(0) == 1


def test_prescaler_256():
    tmr = Timers()
    tmr.set_control(0, 0x82)
    tmr.set_timer(0, 0)
    tmr.set_reload(0, 0)
    tmr.step(256)
    assert tmr.get_timer(0) == 1


def test_prescaler_1024():
    tmr = Timers()
    tmr.set_control(0, 0x83)
    tmr.set_timer(0, 0)
    tmr.set_reload(0, 0)
    tmr.step(1024)
    assert tmr.get_timer(0) == 1


def test_overflow():
    tmr = Timers()
    tmr.set_control(0, 0x80)
    tmr.set_timer(0, 0xFFFF)
    tmr.set_reload(0, 0)
    tmr.step(1)
    assert tmr.get_timer(0) == 0
    assert tmr.get_overflow_flag(0) is True


def test_overflow_reload():
    tmr = Timers()
    tmr.set_control(0, 0x80)
    tmr.set_timer(0, 0xFFFE)
    tmr.set_reload(0, 0x00FF)
    tmr.step(4)
    assert tmr.get_timer(0) == 0x00FF


def test_cascade_mode():
    tmr = Timers()
    tmr.set_control(0, 0x80)
    tmr.set_control(1, 0x84)
    tmr.set_timer(0, 0xFFFF)
    tmr.set_timer(1, 0)
    tmr.set_reload(0, 0)
    tmr.set_reload(1, 0)
    tmr.step(1)
    assert tmr.get_timer(1) == 1


def test_disabled_timer():
    tmr = Timers()
    tmr.set_control(0, 0x00)
    tmr.set_timer(0, 100)
    tmr.step(1000)
    assert tmr.get_timer(0) == 100


def test_all_channels():
    tmr = Timers()
    for i in range(4):
        tmr.set_control(i, 0x80)
        tmr.set_timer(i, i * 10)
    tmr.step(10)
    for i in range(4):
        assert tmr.get_timer(i) == i * 10 + 10


def test_clear_overflow_flag():
    tmr = Timers()
    tmr.set_control(0, 0x80)
    tmr.set_timer(0, 0xFFFF)
    tmr.step(1)
    assert tmr.get_overflow_flag(0) is True
    tmr.clear_overflow_flag(0)
    assert tmr.get_overflow_flag(0) is False
