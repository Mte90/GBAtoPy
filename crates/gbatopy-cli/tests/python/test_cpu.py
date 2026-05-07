"""CPU unit tests"""

import pytest
from gba_runtime.cpu import CPU


def test_cpu_init():
    cpu = CPU()
    assert len(cpu.registers) == 16
    assert cpu.flag_n is False
    assert cpu.flag_z is False
    assert cpu.flag_c is False
    assert cpu.flag_v is False
    assert cpu.thumb_mode is False


def test_get_register(cpu):
    assert cpu.get_register(0) == 0
    assert cpu.get_register(15) == 0


def test_set_register(cpu):
    cpu.set_register(0, 42)
    assert cpu.get_register(0) == 42


def test_set_register_32bit_mask(cpu):
    cpu.set_register(0, 0x1FFFFFFFF)
    assert cpu.get_register(0) == 0xFFFFFFFF


def test_invalid_register():
    cpu = CPU()
    with pytest.raises(ValueError):
        cpu.get_register(20)
    with pytest.raises(ValueError):
        cpu.set_register(20, 0)


def test_reset():
    cpu = CPU()
    cpu.reset(0x08000000)
    assert cpu.get_register(15) == 0x08000000
    assert cpu.get_register(13) == 0x03007F00


def test_cpsr_flags(cpu):
    cpu.set_cpsr_flag("N", True)
    assert cpu.get_cpsr_flag("N") is True

    cpu.set_cpsr_flag("Z", True)
    assert cpu.get_cpsr_flag("Z") is True

    cpu.set_cpsr_flag("C", True)
    assert cpu.get_cpsr_flag("C") is True

    cpu.set_cpsr_flag("V", True)
    assert cpu.get_cpsr_flag("V") is True


def test_invalid_cpsr_flag(cpu):
    with pytest.raises(ValueError):
        cpu.get_cpsr_flag("X")
    with pytest.raises(ValueError):
        cpu.set_cpsr_flag("X", True)


def test_condition_eq(cpu):
    cpu.set_cpsr_flag("Z", True)
    assert cpu.check_condition(0) is True
    cpu.set_cpsr_flag("Z", False)
    assert cpu.check_condition(0) is False


def test_condition_ne(cpu):
    cpu.set_cpsr_flag("Z", False)
    assert cpu.check_condition(1) is True
    cpu.set_cpsr_flag("Z", True)
    assert cpu.check_condition(1) is False


def test_condition_cs(cpu):
    cpu.set_cpsr_flag("C", True)
    assert cpu.check_condition(2) is True
    cpu.set_cpsr_flag("C", False)
    assert cpu.check_condition(2) is False


def test_condition_cc(cpu):
    cpu.set_cpsr_flag("C", False)
    assert cpu.check_condition(3) is True
    cpu.set_cpsr_flag("C", True)
    assert cpu.check_condition(3) is False


def test_condition_mi(cpu):
    cpu.set_cpsr_flag("N", True)
    assert cpu.check_condition(4) is True
    cpu.set_cpsr_flag("N", False)
    assert cpu.check_condition(4) is False


def test_condition_pl(cpu):
    cpu.set_cpsr_flag("N", False)
    assert cpu.check_condition(5) is True
    cpu.set_cpsr_flag("N", True)
    assert cpu.check_condition(5) is False


def test_condition_vs(cpu):
    cpu.set_cpsr_flag("V", True)
    assert cpu.check_condition(6) is True
    cpu.set_cpsr_flag("V", False)
    assert cpu.check_condition(6) is False


def test_condition_vc(cpu):
    cpu.set_cpsr_flag("V", False)
    assert cpu.check_condition(7) is True
    cpu.set_cpsr_flag("V", True)
    assert cpu.check_condition(7) is False


def test_condition_hi(cpu):
    cpu.set_cpsr_flag("C", True)
    cpu.set_cpsr_flag("Z", False)
    assert cpu.check_condition(8) is True

    cpu.set_cpsr_flag("C", False)
    assert cpu.check_condition(8) is False
    cpu.set_cpsr_flag("C", True)
    cpu.set_cpsr_flag("Z", True)
    assert cpu.check_condition(8) is False


def test_condition_ls(cpu):
    cpu.set_cpsr_flag("C", False)
    assert cpu.check_condition(9) is True
    cpu.set_cpsr_flag("Z", True)
    assert cpu.check_condition(9) is True

    cpu.set_cpsr_flag("C", True)
    cpu.set_cpsr_flag("Z", False)
    assert cpu.check_condition(9) is False


def test_condition_ge(cpu):
    cpu.set_cpsr_flag("N", True)
    cpu.set_cpsr_flag("V", True)
    assert cpu.check_condition(10) is True

    cpu.set_cpsr_flag("N", False)
    cpu.set_cpsr_flag("V", False)
    assert cpu.check_condition(10) is True

    cpu.set_cpsr_flag("N", True)
    cpu.set_cpsr_flag("V", False)
    assert cpu.check_condition(10) is False


def test_condition_lt(cpu):
    cpu.set_cpsr_flag("N", True)
    cpu.set_cpsr_flag("V", False)
    assert cpu.check_condition(11) is True

    cpu.set_cpsr_flag("N", False)
    cpu.set_cpsr_flag("V", True)
    assert cpu.check_condition(11) is True

    cpu.set_cpsr_flag("N", True)
    cpu.set_cpsr_flag("V", True)
    assert cpu.check_condition(11) is False


def test_condition_gt(cpu):
    cpu.set_cpsr_flag("Z", False)
    cpu.set_cpsr_flag("N", True)
    cpu.set_cpsr_flag("V", True)
    assert cpu.check_condition(12) is True

    cpu.set_cpsr_flag("Z", True)
    assert cpu.check_condition(12) is False

    cpu.set_cpsr_flag("Z", False)
    cpu.set_cpsr_flag("N", True)
    cpu.set_cpsr_flag("V", False)
    assert cpu.check_condition(12) is False


def test_condition_le(cpu):
    cpu.set_cpsr_flag("Z", True)
    assert cpu.check_condition(13) is True

    cpu.set_cpsr_flag("Z", False)
    cpu.set_cpsr_flag("N", True)
    cpu.set_cpsr_flag("V", False)
    assert cpu.check_condition(13) is True

    cpu.set_cpsr_flag("Z", False)
    cpu.set_cpsr_flag("N", True)
    cpu.set_cpsr_flag("V", True)
    assert cpu.check_condition(13) is False


def test_condition_al(cpu):
    assert cpu.check_condition(14) is True


def test_condition_nv(cpu):
    assert cpu.check_condition(15) is False


def test_condition_invalid(cpu):
    with pytest.raises(ValueError):
        cpu.check_condition(16)


def test_thumb_mode(cpu):
    assert cpu.thumb_mode is False
    cpu.thumb_mode = True
    assert cpu.thumb_mode is True
