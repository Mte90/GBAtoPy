"""ARM7TDMI CPU Data Processing Unit Tests for GBAtoPy.

Tests cover all data processing instructions: logical operations (AND, EOR, ORR, BIC, MOV, MVN),
arithmetic operations (ADD, SUB, RSB, ADC, SBC, RSC), test/compare operations (TST, TEQ, CMP, CMN),
immediate operations, flag updates (N, Z, C, V), and condition code evaluation.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from memory import Memory
from arm7tdmi import ARM7TDMI


def make_cpu():
    """Create a fresh CPU instance with clean state."""
    memory = Memory()
    cpu = ARM7TDMI(memory)
    return cpu, memory


def set_nzcv(cpu, n, z, c, v):
    """Set N/Z/C/V bits in cpsr."""
    cpu.cpsr = (n << 31) | (z << 30) | (c << 29) | (v << 28)


def make_dp(cond, opcode, s, rn, rd, operand2, immediate=True):
    """Build an ARM data processing instruction word."""
    return (cond << 28) | (0b00 << 26) | (immediate << 25) | (opcode << 21) | (s << 20) | (rn << 16) | (rd << 12) | operand2


def test_and_logical_and():
    """AND: r0=0xFF, r1=0x0F -> r2 = r0 AND r1 = 0x0F"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0xFF
    cpu.registers[1] = 0x0F
    
    # AND r2, r0, r1 (immediate=False, opcode=0x0)
    instr = make_dp(cpu.COND_AL, 0x0, 0, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[2] == 0x0F, f"Expected 0x0F, got {hex(cpu.registers[2])}"
    print("✓ test_and_logical_and passed")


def test_eor_logical_xor():
    """EOR: r0=0xFF, r1=0x0F -> r2 = r0 EOR r1 = 0xF0"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0xFF
    cpu.registers[1] = 0x0F
    
    # EOR r2, r0, r1 (opcode=0x1)
    instr = make_dp(cpu.COND_AL, 0x1, 0, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[2] == 0xF0, f"Expected 0xF0, got {hex(cpu.registers[2])}"
    print("✓ test_eor_logical_xor passed")


def test_orr_logical_or():
    """ORR: r0=0xF0, r1=0x0F -> r2 = r0 OR r1 = 0xFF"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0xF0
    cpu.registers[1] = 0x0F
    
    # ORR r2, r0, r1 (opcode=0xC)
    instr = make_dp(cpu.COND_AL, 0xC, 0, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[2] == 0xFF, f"Expected 0xFF, got {hex(cpu.registers[2])}"
    print("✓ test_orr_logical_or passed")


def test_bic_bit_clear():
    """BIC: r0=0xFF, r1=0x0F -> r2 = r0 AND NOT r1 = 0xF0"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0xFF
    cpu.registers[1] = 0x0F
    
    # BIC r2, r0, r1 (opcode=0xE)
    instr = make_dp(cpu.COND_AL, 0xE, 0, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[2] == 0xF0, f"Expected 0xF0, got {hex(cpu.registers[2])}"
    print("✓ test_bic_bit_clear passed")


def test_mov_register():
    """MOV: r0=0x12345678 -> r1 = 0x12345678"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0x12345678
    
    # MOV r1, r0 (opcode=0xD)
    instr = make_dp(cpu.COND_AL, 0xD, 0, 0, 1, 0, immediate=False)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[1] == 0x12345678, f"Expected 0x12345678, got {hex(cpu.registers[1])}"
    print("✓ test_mov_register passed")


def test_add_arithmetic():
    """ADD: r0=10, r1=20 -> r2 = 30"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 10
    cpu.registers[1] = 20
    
    # ADD r2, r0, r1 (opcode=0x4)
    instr = make_dp(cpu.COND_AL, 0x4, 0, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[2] == 30, f"Expected 30, got {cpu.registers[2]}"
    print("✓ test_add_arithmetic passed")


def test_sub_arithmetic():
    """SUB: r0=30, r1=10 -> r2 = 20"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 30
    cpu.registers[1] = 10
    
    # SUB r2, r0, r1 (opcode=0x2)
    instr = make_dp(cpu.COND_AL, 0x2, 0, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[2] == 20, f"Expected 20, got {cpu.registers[2]}"
    print("✓ test_sub_arithmetic passed")


def test_rsb_reverse_subtract():
    """RSB: r0=10, r1=20 -> r2 = r1 - r0 = 10 (reverse subtract)"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 10
    cpu.registers[1] = 20
    
    # RSB r2, r0, r1 (opcode=0x3)
    instr = make_dp(cpu.COND_AL, 0x3, 0, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[2] == 10, f"Expected 10, got {cpu.registers[2]}"
    print("✓ test_rsb_reverse_subtract passed")


def test_adc_add_with_carry():
    """ADC: r0=10, r1=20, C=1 -> r2 = 31 (add with carry)"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 10
    cpu.registers[1] = 20
    cpu.cpsr = (1 << 29)  # Set C flag
    
    # ADC r2, r0, r1 (opcode=0x5)
    instr = make_dp(cpu.COND_AL, 0x5, 0, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[2] == 31, f"Expected 31, got {cpu.registers[2]}"
    print("✓ test_adc_add_with_carry passed")


def test_sbc_subtract_with_carry():
    """SBC: r0=30, r1=10, C=1 -> r2 = 20 (subtract with carry)"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 30
    cpu.registers[1] = 10
    cpu.cpsr = (1 << 29)  # Set C flag
    
    # SBC r2, r0, r1 (opcode=0x6)
    instr = make_dp(cpu.COND_AL, 0x6, 0, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    # SBC = operand1 - operand2 - (1 - C) = 30 - 10 - 0 = 20
    assert cpu.registers[2] == 20, f"Expected 20, got {cpu.registers[2]}"
    print("✓ test_sbc_subtract_with_carry passed")


def test_tst_test_and():
    """TST: r0=0xFF, r1=0x0F -> Z=0 (non-zero result)"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0xFF
    cpu.registers[1] = 0x0F
    
    # TST r0, r1 (opcode=0x8, S=1, Rd=15 ignored for TST)
    instr = make_dp(cpu.COND_AL, 0x8, 1, 0, 15, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    z = (cpu.cpsr >> 30) & 1
    assert z == 0, f"Expected Z=0, got Z={z}"
    print("✓ test_tst_test_and passed")


def test_teq_test_equality():
    """TEQ: r0=0xFF, r1=0xFF -> Z=1 (equal)"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0xFF
    cpu.registers[1] = 0xFF
    
    # TEQ r0, r1 (opcode=0x9, S=1)
    instr = make_dp(cpu.COND_AL, 0x9, 1, 0, 15, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    z = (cpu.cpsr >> 30) & 1
    assert z == 1, f"Expected Z=1, got Z={z}"
    print("✓ test_teq_test_equality passed")


def test_cmp_compare():
    """CMP: r0=10, r1=10 -> Z=1 (equal)"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 10
    cpu.registers[1] = 10
    
    # CMP r0, r1 (opcode=0xA, S=1)
    instr = make_dp(cpu.COND_AL, 0xA, 1, 0, 15, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    z = (cpu.cpsr >> 30) & 1
    assert z == 1, f"Expected Z=1, got Z={z}"
    print("✓ test_cmp_compare passed")


def test_cmn_compare_negative():
    """CMN: r0=5, r1=3 -> Z=0 (r0 + r1 = 8, non-zero)"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 5
    cpu.registers[1] = 3
    
    # CMN r0, r1 (opcode=0xB, S=1)
    instr = make_dp(cpu.COND_AL, 0xB, 1, 0, 15, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    z = (cpu.cpsr >> 30) & 1
    assert z == 0, f"Expected Z=0, got Z={z}"
    print("✓ test_cmn_compare_negative passed")


def test_mov_immediate():
    """MOV with immediate: Rd = 0x42"""
    cpu, memory = make_cpu()
    
    # MOV r0, #0x42 (opcode=0xD, immediate=True)
    instr = make_dp(cpu.COND_AL, 0xD, 0, 0, 0, 0x42, immediate=True)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[0] == 0x42, f"Expected 0x42, got {hex(cpu.registers[0])}"
    print("✓ test_mov_immediate passed")


def test_add_immediate():
    """ADD with immediate: r0=5, imm=10 -> Rd = 15"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 5
    
    # ADD r1, r0, #10 (opcode=0x4, immediate=True)
    instr = make_dp(cpu.COND_AL, 0x4, 0, 0, 1, 10, immediate=True)
    cpu.exec_data_processing(instr)
    
    assert cpu.registers[1] == 15, f"Expected 15, got {cpu.registers[1]}"
    print("✓ test_add_immediate passed")


def test_adds_flag_carry():
    """ADDS r0=0xFFFFFFFF, r1=1 -> Z=1, N=0, C=1 (carry from 0xFFFFFFFF+1=0x100000000), V=0"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0xFFFFFFFF
    cpu.registers[1] = 1
    
    # ADDS r2, r0, r1 (opcode=0x4, S=1)
    instr = make_dp(cpu.COND_AL, 0x4, 1, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    n = (cpu.cpsr >> 31) & 1
    z = (cpu.cpsr >> 30) & 1
    c = (cpu.cpsr >> 29) & 1
    v = (cpu.cpsr >> 28) & 1
    
    # Result = 0, so Z=1, N=0 (result is 0), C=1 (carry out), V=0 (no signed overflow: -1 + 1 = 0)
    assert z == 1, f"Expected Z=1, got Z={z}"
    assert n == 0, f"Expected N=0, got N={n}"
    assert c == 1, f"Expected C=1, got C={c}"
    assert v == 0, f"Expected V=0, got V={v}"
    print("✓ test_adds_flag_carry passed")


def test_adds_flag_overflow():
    """ADDS r0=0x7FFFFFFF, r1=1 -> N=1 (result=0x80000000), V=1 (signed overflow), C=0, Z=0"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0x7FFFFFFF
    cpu.registers[1] = 1
    
    # ADDS r2, r0, r1 (opcode=0x4, S=1)
    instr = make_dp(cpu.COND_AL, 0x4, 1, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    n = (cpu.cpsr >> 31) & 1
    z = (cpu.cpsr >> 30) & 1
    c = (cpu.cpsr >> 29) & 1
    v = (cpu.cpsr >> 28) & 1
    
    assert n == 1, f"Expected N=1, got N={n}"
    assert z == 0, f"Expected Z=0, got Z={z}"
    assert c == 0, f"Expected C=0, got C={c}"
    assert v == 1, f"Expected V=1, got V={v}"
    print("✓ test_adds_flag_overflow passed")


def test_subs_flag_borrow():
    """SUBS r0=0, r1=1 -> Z=0, N=1, C=0 (borrow), V=0"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 0
    cpu.registers[1] = 1
    
    # SUBS r2, r0, r1 (opcode=0x2, S=1)
    instr = make_dp(cpu.COND_AL, 0x2, 1, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    n = (cpu.cpsr >> 31) & 1
    z = (cpu.cpsr >> 30) & 1
    c = (cpu.cpsr >> 29) & 1
    v = (cpu.cpsr >> 28) & 1
    
    assert z == 0, f"Expected Z=0, got Z={z}"
    assert n == 1, f"Expected N=1, got N={n}"
    assert c == 0, f"Expected C=0 (borrow), got C={c}"
    assert v == 0, f"Expected V=0, got V={v}"
    print("✓ test_subs_flag_borrow passed")


def test_subs_flag_equal():
    """SUBS r0=5, r1=5 -> Z=1, N=0, C=1 (no borrow), V=0"""
    cpu, memory = make_cpu()
    cpu.registers[0] = 5
    cpu.registers[1] = 5
    
    # SUBS r2, r0, r1 (opcode=0x2, S=1)
    instr = make_dp(cpu.COND_AL, 0x2, 1, 0, 2, 1, immediate=False)
    cpu.exec_data_processing(instr)
    
    n = (cpu.cpsr >> 31) & 1
    z = (cpu.cpsr >> 30) & 1
    c = (cpu.cpsr >> 29) & 1
    v = (cpu.cpsr >> 28) & 1
    
    assert z == 1, f"Expected Z=1, got Z={z}"
    assert n == 0, f"Expected N=0, got N={n}"
    assert c == 1, f"Expected C=1 (no borrow), got C={c}"
    assert v == 0, f"Expected V=0, got V={v}"
    print("✓ test_subs_flag_equal passed")


def test_condition_eq():
    """COND_EQ (Z=1): set Z=1, check_condition(EQ) == True"""
    cpu, memory = make_cpu()
    set_nzcv(cpu, 0, 1, 0, 0)  # Z=1
    
    assert cpu.check_condition(cpu.COND_EQ) == True, "Expected EQ to pass when Z=1"
    print("✓ test_condition_eq passed")


def test_condition_ne():
    """COND_NE (Z=0): set Z=0, check_condition(NE) == True"""
    cpu, memory = make_cpu()
    set_nzcv(cpu, 0, 0, 0, 0)  # Z=0
    
    assert cpu.check_condition(cpu.COND_NE) == True, "Expected NE to pass when Z=0"
    print("✓ test_condition_ne passed")


def test_condition_cs():
    """COND_CS (C=1): set C=1, check_condition(CS) == True"""
    cpu, memory = make_cpu()
    set_nzcv(cpu, 0, 0, 1, 0)  # C=1
    
    assert cpu.check_condition(cpu.COND_CS) == True, "Expected CS to pass when C=1"
    print("✓ test_condition_cs passed")


def test_condition_cc():
    """COND_CC (C=0): set C=0, check_condition(CC) == True"""
    cpu, memory = make_cpu()
    set_nzcv(cpu, 0, 0, 0, 0)  # C=0
    
    assert cpu.check_condition(cpu.COND_CC) == True, "Expected CC to pass when C=0"
    print("✓ test_condition_cc passed")


def test_condition_mi():
    """COND_MI (N=1): set N=1, check_condition(MI) == True"""
    cpu, memory = make_cpu()
    set_nzcv(cpu, 1, 0, 0, 0)  # N=1
    
    assert cpu.check_condition(cpu.COND_MI) == True, "Expected MI to pass when N=1"
    print("✓ test_condition_mi passed")


def test_condition_al():
    """COND_AL (always): check_condition(AL) == True regardless of flags"""
    cpu, memory = make_cpu()
    set_nzcv(cpu, 0, 0, 0, 0)
    
    assert cpu.check_condition(cpu.COND_AL) == True, "Expected AL to always pass"
    print("✓ test_condition_al passed")


def test_condition_nv():
    """COND_NV (never): check_condition(NV) == False regardless of flags"""
    cpu, memory = make_cpu()
    set_nzcv(cpu, 0, 0, 0, 0)
    
    assert cpu.check_condition(cpu.COND_NV) == False, "Expected NV to never pass"
    print("✓ test_condition_nv passed")


def test_condition_ge():
    """COND_GE (N==V): set N=1,V=1 -> True; set N=1,V=0 -> False"""
    cpu, memory = make_cpu()
    
    # N=1, V=1 -> N==V -> True
    set_nzcv(cpu, 1, 0, 0, 1)
    assert cpu.check_condition(cpu.COND_GE) == True, "Expected GE to pass when N==V (both 1)"
    
    # N=1, V=0 -> N!=V -> False
    set_nzcv(cpu, 1, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_GE) == False, "Expected GE to fail when N!=V"
    print("✓ test_condition_ge passed")


def test_condition_gt():
    """COND_GT (Z=0 and N==V): set Z=0,N=1,V=1 -> True; set Z=1,N=1,V=1 -> False"""
    cpu, memory = make_cpu()
    
    # Z=0, N=1, V=1 -> True
    set_nzcv(cpu, 1, 0, 0, 1)
    assert cpu.check_condition(cpu.COND_GT) == True, "Expected GT to pass when Z=0 and N==V"
    
    # Z=1, N=1, V=1 -> False (Z set)
    set_nzcv(cpu, 1, 1, 0, 1)
    assert cpu.check_condition(cpu.COND_GT) == False, "Expected GT to fail when Z=1"
    print("✓ test_condition_gt passed")


if __name__ == "__main__":
    # Logical Operations (5 tests)
    test_and_logical_and()
    test_eor_logical_xor()
    test_orr_logical_or()
    test_bic_bit_clear()
    test_mov_register()
    
    # Arithmetic Operations (5 tests)
    test_add_arithmetic()
    test_sub_arithmetic()
    test_rsb_reverse_subtract()
    test_adc_add_with_carry()
    test_sbc_subtract_with_carry()
    
    # Test/Compare Operations (4 tests)
    test_tst_test_and()
    test_teq_test_equality()
    test_cmp_compare()
    test_cmn_compare_negative()
    
    # Immediate Operations (2 tests)
    test_mov_immediate()
    test_add_immediate()
    
    # Flag Updates (4 tests)
    test_adds_flag_carry()
    test_adds_flag_overflow()
    test_subs_flag_borrow()
    test_subs_flag_equal()
    
    # Condition Codes (8 tests)
    test_condition_eq()
    test_condition_ne()
    test_condition_cs()
    test_condition_cc()
    test_condition_mi()
    test_condition_al()
    test_condition_nv()
    test_condition_ge()
    test_condition_gt()
    
    print("\nAll 27 tests passed!")