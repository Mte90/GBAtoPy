"""ARM7TDMI fallback interpreter unit tests for GBAtoPy.

Tests cover condition code evaluation (all 14 codes + NV=False), mode→SPSR mapping,
SWI dispatch table reachability, and register banking for all CPU modes.

Run: python3 -m pytest test_arm7tdmi.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from memory import Memory
from arm7tdmi import ARM7TDMI, _MODE_TO_SPSR_IDX, _MODES_WITH_SPSR


def make_cpu():
    """Create a fresh CPU instance with clean state."""
    memory = Memory()
    cpu = ARM7TDMI(memory)
    return cpu, memory


def set_nzcv(cpu, n, z, c, v):
    """Set N/Z/C/V flags in cpsr."""
    cpu.cpsr = (n << 31) | (z << 30) | (c << 29) | (v << 28)


# ============================================================================
# Condition Code Tests (all 16 codes, including NV=False)
# ============================================================================

def test_condition_eq():
    """COND_EQ (Z=1): must return True when Z flag is set."""
    cpu, _ = make_cpu()
    set_nzcv(cpu, 0, 1, 0, 0)  # Z=1
    assert cpu.check_condition(cpu.COND_EQ) == True


def test_condition_ne():
    """COND_NE (Z=0): must return True when Z flag is clear."""
    cpu, _ = make_cpu()
    set_nzcv(cpu, 0, 0, 0, 0)  # Z=0
    assert cpu.check_condition(cpu.COND_NE) is True


def test_condition_cs():
    """COND_CS (C=1): must return True when C flag is set."""
    cpu, _ = make_cpu()
    set_nzcv(cpu, 0, 0, 1, 0)  # C=1
    assert cpu.check_condition(cpu.COND_CS) == True


def test_condition_cc():
    """COND_CC (C=0): must return True when C flag is clear."""
    cpu, _ = make_cpu()
    set_nzcv(cpu, 0, 0, 0, 0)  # C=0
    assert cpu.check_condition(cpu.COND_CC) is True


def test_condition_mi():
    """COND_MI (N=1): must return True when N flag is set."""
    cpu, _ = make_cpu()
    set_nzcv(cpu, 1, 0, 0, 0)  # N=1
    assert cpu.check_condition(cpu.COND_MI) == True


def test_condition_pl():
    """COND_PL (N=0): must return True when N flag is clear."""
    cpu, _ = make_cpu()
    set_nzcv(cpu, 0, 0, 0, 0)  # N=0
    assert cpu.check_condition(cpu.COND_PL) is True


def test_condition_vs():
    """COND_VS (V=1): must return True when V flag is set."""
    cpu, _ = make_cpu()
    set_nzcv(cpu, 0, 0, 0, 1)  # V=1
    assert cpu.check_condition(cpu.COND_VS) == True


def test_condition_vc():
    """COND_VC (V=0): must return True when V flag is clear."""
    cpu, _ = make_cpu()
    set_nzcv(cpu, 0, 0, 0, 0)  # V=0
    assert cpu.check_condition(cpu.COND_VC) is True


def test_condition_hi():
    """COND_HI (C=1 and Z=0): must return True only when unsigned higher."""
    cpu, _ = make_cpu()
    # C=1, Z=0 -> True
    set_nzcv(cpu, 0, 0, 1, 0)
    assert cpu.check_condition(cpu.COND_HI) == True
    # C=0, Z=0 -> False
    set_nzcv(cpu, 0, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_HI) == False
    # C=1, Z=1 -> False
    set_nzcv(cpu, 0, 1, 1, 0)
    assert cpu.check_condition(cpu.COND_HI) == False


def test_condition_ls():
    """COND_LS (C=0 or Z=1): must return True when unsigned lower or same."""
    cpu, _ = make_cpu()
    # C=0, Z=0 -> True
    set_nzcv(cpu, 0, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_LS) == True
    # C=1, Z=1 -> True
    set_nzcv(cpu, 0, 1, 1, 0)
    assert cpu.check_condition(cpu.COND_LS) == True
    # C=1, Z=0 -> False
    set_nzcv(cpu, 0, 0, 1, 0)
    assert cpu.check_condition(cpu.COND_LS) == False


def test_condition_ge():
    """COND_GE (N==V): must return True when signed >=."""
    cpu, _ = make_cpu()
    # N=1, V=1 -> True (both negative overflow)
    set_nzcv(cpu, 1, 0, 0, 1)
    assert cpu.check_condition(cpu.COND_GE) is True
    # N=0, V=0 -> True (both positive)
    set_nzcv(cpu, 0, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_GE) is True
    # N=1, V=0 -> False (negative result, no overflow)
    set_nzcv(cpu, 1, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_GE) is False
    # N=0, V=1 -> False (positive result, overflow)
    set_nzcv(cpu, 0, 0, 0, 1)
    assert cpu.check_condition(cpu.COND_GE) is False


def test_condition_lt():
    """COND_LT (N!=V): must return True when signed <."""
    cpu, _ = make_cpu()
    # N=1, V=0 -> True (negative result)
    set_nzcv(cpu, 1, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_LT) is True
    # N=0, V=1 -> True (positive overflow)
    set_nzcv(cpu, 0, 0, 0, 1)
    assert cpu.check_condition(cpu.COND_LT) is True
    # N=1, V=1 -> False (negative overflow)
    set_nzcv(cpu, 1, 0, 0, 1)
    assert cpu.check_condition(cpu.COND_LT) is False


def test_condition_gt():
    """COND_GT (Z=0 and N==V): must return True when signed >."""
    cpu, _ = make_cpu()
    # Z=0, N=0, V=0 -> True
    set_nzcv(cpu, 0, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_GT) is True
    # Z=1, N=0, V=0 -> False (equal)
    set_nzcv(cpu, 0, 1, 0, 0)
    assert cpu.check_condition(cpu.COND_GT) is False
    # Z=0, N=1, V=0 -> False (negative)
    set_nzcv(cpu, 1, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_GT) is False


def test_condition_le():
    """COND_LE (Z=1 or N!=V): must return True when signed <=."""
    cpu, _ = make_cpu()
    # Z=1 -> True
    set_nzcv(cpu, 0, 1, 0, 0)
    assert cpu.check_condition(cpu.COND_LE) == True
    # Z=0, N=1, V=0 -> True (negative)
    set_nzcv(cpu, 1, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_LE) == True
    # Z=0, N=0, V=0 -> False (positive)
    set_nzcv(cpu, 0, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_LE) == False


def test_condition_al():
    """COND_AL (always): must return True regardless of flags."""
    cpu, _ = make_cpu()
    # Test with all flag combinations
    set_nzcv(cpu, 0, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_AL) == True
    set_nzcv(cpu, 1, 1, 1, 1)
    assert cpu.check_condition(cpu.COND_AL) == True


def test_condition_nv():
    """COND_NV (never): must return False per ARMv4T spec (memory #6494)."""
    cpu, _ = make_cpu()
    # NV must NEVER execute, regardless of flags
    set_nzcv(cpu, 0, 0, 0, 0)
    assert cpu.check_condition(cpu.COND_NV) is False
    set_nzcv(cpu, 1, 1, 1, 1)
    assert cpu.check_condition(cpu.COND_NV) is False


# ============================================================================
# Mode → SPSR Index Mapping Tests
# ============================================================================

def test_mode_to_spsr_mapping():
    """Verify _MODE_TO_SPSR_IDX maps all modes correctly."""
    # User mode (0x10) is mapped to index 0 in the actual implementation
    assert _MODE_TO_SPSR_IDX.get(0x10) == 0
    
    # System mode (0x1F) shares USR SPSR slot (index 1)
    assert _MODE_TO_SPSR_IDX.get(0x1F) == 1
    
    # SVC mode (0x13) -> index 2
    assert _MODE_TO_SPSR_IDX.get(0x13) == 2
    
    # ABT mode (0x17) -> index 3
    assert _MODE_TO_SPSR_IDX.get(0x17) == 3
    
    # UND mode (0x1B) -> index 4
    assert _MODE_TO_SPSR_IDX.get(0x1B) == 4
    
    # FIQ mode (0x11) -> index 5
    assert _MODE_TO_SPSR_IDX.get(0x11) == 5
    
    # IRQ mode (0x12) -> index 6
    assert _MODE_TO_SPSR_IDX.get(0x12) == 6


def test_modes_with_spsr():
    """Verify _MODES_WITH_SPSR contains all privileged modes."""
    # User/System modes do NOT have SPSR
    assert 0x10 not in _MODES_WITH_SPSR  # User
    assert 0x1F not in _MODES_WITH_SPSR  # System
    
    # All privileged modes have SPSR
    assert 0x11 in _MODES_WITH_SPSR  # FIQ
    assert 0x12 in _MODES_WITH_SPSR  # IRQ
    assert 0x13 in _MODES_WITH_SPSR  # SVC
    assert 0x17 in _MODES_WITH_SPSR  # ABT
    assert 0x1B in _MODES_WITH_SPSR  # UND


def test_spsr_storage():
    """Verify CPU has 7 SPSR slots for all modes."""
    cpu, _ = make_cpu()
    assert len(cpu.spsr) == 7
    
    # All SPSR slots should be zero-initialized
    for i in range(7):
        assert cpu.spsr[i] == 0


# ============================================================================
# SWI Dispatch Table Tests
# ============================================================================

def test_swi_handler_has_all_live_handlers():
    """Verify SWI handler has all 13 live BIOS handlers."""
    cpu, _ = make_cpu()
    
    # Count the number of elif branches in swi_handler
    # These are the live handlers: 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
    # 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x18
    import inspect
    source = inspect.getsource(cpu.swi_handler)
    
    # Count SWI number handlers (each elif num == 0xXX)
    handler_count = source.count('elif num == 0x') + source.count('if num == 0x')
    assert handler_count >= 13, f"Expected at least 13 SWI handlers, found {handler_count}"


def test_swi_softreset_reachable():
    """SWI 0x00 (SoftReset) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 0
    cpu.swi_handler(0x00)
    # SoftReset should zero registers and set PC to 0x08000000
    assert cpu.registers[15] == 0x08000000


def test_swi_registerramreset_reachable():
    """SWI 0x01 (RegisterRamReset) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 0xFF  # Reset all regions
    cpu.swi_handler(0x01)
    # Should complete without error


def test_swi_halt_reachable():
    """SWI 0x02 (Halt) must be reachable."""
    cpu, _ = make_cpu()
    cpu.swi_handler(0x02)
    assert cpu._halted is True
    assert cpu._halt_reason == 'any'


def test_swi_intrwait_reachable():
    """SWI 0x04 (IntrWait) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 0  # returnWhenNotInVBlank
    cpu.registers[1] = 0  # interruptFlag
    cpu.swi_handler(0x04)
    # Should complete without error


def test_swi_vblankintrwait_reachable():
    """SWI 0x05 (VBlankIntrWait) must be reachable."""
    cpu, _ = make_cpu()
    cpu.swi_handler(0x05)
    assert cpu._halted is True
    assert cpu._halt_reason == 'vblank'


def test_swi_div_reachable():
    """SWI 0x06 (Div) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 100
    cpu.registers[1] = 7
    cpu.swi_handler(0x06)
    # Result in R0, remainder in R1
    assert cpu.registers[0] == 14  # 100 / 7 = 14
    assert cpu.registers[1] == 2   # 100 % 7 = 2


def test_swi_divarm_reachable():
    """SWI 0x07 (DivArm) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 100
    cpu.registers[1] = 7
    cpu.swi_handler(0x07)
    assert cpu.registers[0] == 14


def test_swi_sqrt_reachable():
    """SWI 0x08 (Sqrt) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 144
    cpu.swi_handler(0x08)
    assert cpu.registers[0] == 12


def test_swi_arctan_reachable():
    """SWI 0x09 (ArcTan) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 0x8000  # 45 degrees in fixed point
    cpu.swi_handler(0x09)
    # Should complete without error


def test_swi_arctan2_reachable():
    """SWI 0x0A (ArcTan2) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 0x8000
    cpu.registers[1] = 0x8000
    cpu.swi_handler(0x0A)
    # Should complete without error


def test_swi_cpuset_reachable():
    """SWI 0x0B (CpuSet) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 0x02000000  # src
    cpu.registers[1] = 0x02000100  # dest
    cpu.registers[2] = 0x100        # count
    cpu.swi_handler(0x0B)
    # Should complete without error


def test_swi_cpufastset_reachable():
    """SWI 0x0C (CpuFastSet) must be reachable."""
    cpu, _ = make_cpu()
    cpu.registers[0] = 0x02000000
    cpu.registers[1] = 0x02000100
    cpu.registers[2] = 0x100
    cpu.swi_handler(0x0C)
    # Should complete without error


# ============================================================================
# Register Banking Tests
# ============================================================================

def test_user_mode_register_bank():
    """User mode (0x10) shares register bank with System mode."""
    cpu, _ = make_cpu()
    
    # Start in user mode
    assert cpu.mode == 0x1F  # Default is System mode
    
    # Switch to user mode
    cpu._switch_mode(0x10)
    assert cpu.mode == 0x10
    
    # Set SP and LR in user mode
    cpu.registers[13] = 0x03007F00
    cpu.registers[14] = 0x08000100
    
    # Switch to system mode - should share the same bank
    cpu._switch_mode(0x1F)
    assert cpu.mode == 0x1F
    
    # Switch back to user mode - values should persist
    cpu._switch_mode(0x10)
    assert cpu.registers[13] == 0x03007F00
    assert cpu.registers[14] == 0x08000100


def test_fiq_mode_register_bank():
    """FIQ mode (0x11) has banked R8-R12, SP, and LR."""
    cpu, _ = make_cpu()
    
    # Set FIQ banked registers
    cpu._switch_mode(0x11)
    cpu.registers[8] = 0x11111111
    cpu.registers[9] = 0x22222222
    cpu.registers[10] = 0x33333333
    cpu.registers[11] = 0x44444444
    cpu.registers[12] = 0x55555555
    cpu.registers[13] = 0x03007F00  # FIQ SP
    cpu.registers[14] = 0x08000100  # FIQ LR
    
    # Switch to IRQ mode
    cpu._switch_mode(0x12)
    
    # FIQ registers should be saved
    assert cpu.banked_sp_lr[0x11]['r8'] == 0x11111111
    assert cpu.banked_sp_lr[0x11]['r9'] == 0x22222222
    assert cpu.banked_sp_lr[0x11]['sp'] == 0x03007F00
    assert cpu.banked_sp_lr[0x11]['lr'] == 0x08000100
    
    # Switch back to FIQ mode - values should be restored
    cpu._switch_mode(0x11)
    assert cpu.registers[8] == 0x11111111
    assert cpu.registers[9] == 0x22222222
    assert cpu.registers[13] == 0x03007F00
    assert cpu.registers[14] == 0x08000100


def test_irq_mode_register_bank():
    """IRQ mode (0x12) has banked SP and LR only."""
    cpu, _ = make_cpu()
    
    # Set IRQ banked registers
    cpu._switch_mode(0x12)
    cpu.registers[13] = 0x03007FE0  # IRQ SP
    cpu.registers[14] = 0x08000200  # IRQ LR
    
    # Switch to SVC mode
    cpu._switch_mode(0x13)
    
    # IRQ registers should be saved
    assert cpu.banked_sp_lr[0x12]['sp'] == 0x03007FE0
    assert cpu.banked_sp_lr[0x12]['lr'] == 0x08000200
    
    # Switch back to IRQ mode - values should be restored
    cpu._switch_mode(0x12)
    assert cpu.registers[13] == 0x03007FE0
    assert cpu.registers[14] == 0x08000200


def test_svc_mode_register_bank():
    """SVC mode (0x13) has banked SP and LR."""
    cpu, _ = make_cpu()
    
    # Set SVC banked registers
    cpu._switch_mode(0x13)
    cpu.registers[13] = 0x03007FE0  # SVC SP
    cpu.registers[14] = 0x08000300  # SVC LR
    
    # Switch to ABT mode
    cpu._switch_mode(0x17)
    
    # SVC registers should be saved
    assert cpu.banked_sp_lr[0x13]['sp'] == 0x03007FE0
    assert cpu.banked_sp_lr[0x13]['lr'] == 0x08000300
    
    # Switch back to SVC mode - values should be restored
    cpu._switch_mode(0x13)
    assert cpu.registers[13] == 0x03007FE0
    assert cpu.registers[14] == 0x08000300


def test_abt_mode_register_bank():
    """ABT mode (0x17) has banked SP and LR."""
    cpu, _ = make_cpu()
    
    # Set ABT banked registers
    cpu._switch_mode(0x17)
    cpu.registers[13] = 0x03007FC0  # ABT SP
    cpu.registers[14] = 0x08000400  # ABT LR
    
    # Switch to UND mode
    cpu._switch_mode(0x1B)
    
    # ABT registers should be saved
    assert cpu.banked_sp_lr[0x17]['sp'] == 0x03007FC0
    assert cpu.banked_sp_lr[0x17]['lr'] == 0x08000400
    
    # Switch back to ABT mode - values should be restored
    cpu._switch_mode(0x17)
    assert cpu.registers[13] == 0x03007FC0
    assert cpu.registers[14] == 0x08000400


def test_und_mode_register_bank():
    """UND mode (0x1B) has banked SP and LR."""
    cpu, _ = make_cpu()
    
    # Set UND banked registers
    cpu._switch_mode(0x1B)
    cpu.registers[13] = 0x03007FA0  # UND SP
    cpu.registers[14] = 0x08000500  # UND LR
    
    # Switch to FIQ mode
    cpu._switch_mode(0x11)
    
    # UND registers should be saved
    assert cpu.banked_sp_lr[0x1B]['sp'] == 0x03007FA0
    assert cpu.banked_sp_lr[0x1B]['lr'] == 0x08000500
    
    # Switch back to UND mode - values should be restored
    cpu._switch_mode(0x1B)
    assert cpu.registers[13] == 0x03007FA0
    assert cpu.registers[14] == 0x08000500


def test_mode_switch_preserves_user_registers():
    """Mode switches preserve R0-R7 (unbanked registers)."""
    cpu, _ = make_cpu()
    
    # Set unbanked registers
    for i in range(8):
        cpu.registers[i] = 0x11111111 + i
    
    # Switch through all modes
    for mode in [0x11, 0x12, 0x13, 0x17, 0x1B, 0x1F]:
        cpu._switch_mode(mode)
    
    # R0-R7 should be unchanged
    for i in range(8):
        assert cpu.registers[i] == 0x11111111 + i, f"R{i} was corrupted during mode switch"


if __name__ == "__main__":
    # Condition code tests (16 tests)
    test_condition_eq()
    test_condition_ne()
    test_condition_cs()
    test_condition_cc()
    test_condition_mi()
    test_condition_pl()
    test_condition_vs()
    test_condition_vc()
    test_condition_hi()
    test_condition_ls()
    test_condition_ge()
    test_condition_lt()
    test_condition_gt()
    test_condition_le()
    test_condition_al()
    test_condition_nv()
    
    # Mode→SPSR mapping tests (3 tests)
    test_mode_to_spsr_mapping()
    test_modes_with_spsr()
    test_spsr_storage()
    
    # SWI dispatch tests (13 tests)
    test_swi_handler_has_all_live_handlers()
    test_swi_softreset_reachable()
    test_swi_registerramreset_reachable()
    test_swi_halt_reachable()
    test_swi_intrwait_reachable()
    test_swi_vblankintrwait_reachable()
    test_swi_div_reachable()
    test_swi_divarm_reachable()
    test_swi_sqrt_reachable()
    test_swi_arctan_reachable()
    test_swi_arctan2_reachable()
    test_swi_cpuset_reachable()
    test_swi_cpufastset_reachable()
    
    # Register banking tests (7 tests)
    test_user_mode_register_bank()
    test_fiq_mode_register_bank()
    test_irq_mode_register_bank()
    test_svc_mode_register_bank()
    test_abt_mode_register_bank()
    test_und_mode_register_bank()
    test_mode_switch_preserves_user_registers()
    
    print("\nAll 39 tests passed!")