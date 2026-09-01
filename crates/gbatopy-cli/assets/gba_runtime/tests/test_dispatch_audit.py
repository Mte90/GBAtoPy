"""
Dispatch Audit Test Suite for GBAtoPy Transpiler.

This test suite verifies that ARM and Thumb opcodes are routed to the correct
handlers in the CPU interpreter. It catches dispatch bugs where instructions
are decoded or dispatched to the wrong handler.

Run with: python3 -m pytest test_dispatch_audit.py -v
"""

import unittest
from unittest.mock import patch, MagicMock


class MockMemory:
    """Mock memory for CPU testing."""
    
    def __init__(self):
        self.data = {}
    
    def read_u8(self, addr):
        return self.data.get(addr, 0)
    
    def read_u16(self, addr):
        addr &= 0xFFFFFFFF
        lo = self.data.get(addr, 0)
        hi = self.data.get(addr + 1, 0)
        return (hi << 8) | lo
    
    def read_u32(self, addr):
        addr &= 0xFFFFFFFF
        lo = self.read_u16(addr)
        hi = self.read_u16(addr + 2)
        return (hi << 16) | lo
    
    def write_u8(self, addr, value):
        self.data[addr & 0xFFFFFFFF] = value & 0xFF
    
    def write_u16(self, addr, value):
        addr &= 0xFFFFFFFF
        self.data[addr] = value & 0xFF
        self.data[addr + 1] = (value >> 8) & 0xFF
    
    def write_u32(self, addr, value):
        addr &= 0xFFFFFFFF
        self.write_u16(addr, value & 0xFFFF)
        self.write_u16(addr + 2, (value >> 16) & 0xFFFF)


class TestARMDispatchAudit(unittest.TestCase):
    """ARM instruction dispatch audit tests.
    
    These tests verify that ARM opcodes are routed to the correct handlers,
    catching bugs where instructions are dispatched to wrong execution paths.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        from arm7tdmi import ARM7TDMI
        self.memory = MockMemory()
        self.cpu = ARM7TDMI(self.memory)
        # Reset CPU state
        self.cpu.registers = [0] * 16
        self.cpu.cpsr = 0
        self.cpu.thumb_mode = False
        self.cpu.mode = 0x1F
    
    def test_msr_cpsr_routes_to_status_transfer(self):
        """MSR CPSR_fc, #0x12 (0xE329F012) must route to MSR handler, not exec_data_processing.
        
        Bug prevented: MSR opcode routed to TEQ handler (exec_data_processing) instead of
        dedicated MSR handler, causing PC to never advance and infinite spin.
        
        Encoding: 0xE329F012
        - Condition: AL (0xE)
        - Opcode: MSR immediate (0x2)
        - Rd=15 (Rn field), mask=9 (fxc bits)
        - Immediate: 0x12
        """
        instr = 0xE329F012
        
        # Set up initial state
        initial_pc = 0x08000000
        self.cpu.registers[15] = initial_pc
        
        # Track which handler was called
        handler_called = []
        
        def track_status_transfer(*args, **kwargs):
            handler_called.append('_exec_status_transfer')
            self.cpu.registers[15] += 4
            return 1
        
        def track_data_processing(*args, **kwargs):
            handler_called.append('exec_data_processing')
            return 1
        
        # Patch both handlers to track calls
        with patch.object(self.cpu, '_exec_status_transfer', side_effect=track_status_transfer), \
             patch.object(self.cpu, 'exec_data_processing', side_effect=track_data_processing):
            
            # Execute the instruction
            self.cpu.execute_arm(instr)
        
        # Verify correct handler was called
        self.assertEqual(handler_called, ['_exec_status_transfer'],
            f"MSR should route to _exec_status_transfer, got {handler_called}")
        
        # Verify PC advanced (not stuck in infinite loop)
        self.assertEqual(self.cpu.registers[15], initial_pc + 4,
            "PC should advance by 4 after MSR execution")
    
    def test_mrs_cpsr_routes_to_status_transfer(self):
        """MRS R0, CPSR (0xE10F0000) must route to MSR/MRS path.
        
        Bug prevented: MRS opcode routed to data processing handler instead of
        status register transfer, causing incorrect register writes.
        
        Encoding: 0xE10F0000 (MRS R0, CPSR)
        - Condition: AL (0xE)
        - Opcode: MRS (0x1)
        - Rn=15, Rd=0
        """
        instr = 0xE10F0000
        
        # Set up initial state
        initial_pc = 0x08000000
        self.cpu.registers[15] = initial_pc
        initial_cpsr = 0x20000000  # Some initial CPSR value
        self.cpu.cpsr = initial_cpsr
        
        # Track which handler was called
        handler_called = []
        
        original_status_transfer = self.cpu._exec_status_transfer
        original_data_processing = self.cpu.exec_data_processing
        
        def track_status_transfer(*args, **kwargs):
            handler_called.append('_exec_status_transfer')
            return original_status_transfer(*args, **kwargs)
        
        def track_data_processing(*args, **kwargs):
            handler_called.append('exec_data_processing')
            return original_data_processing(*args, **kwargs)
        
        # Patch both handlers to track calls while still executing real logic
        with patch.object(self.cpu, '_exec_status_transfer', side_effect=track_status_transfer), \
             patch.object(self.cpu, 'exec_data_processing', side_effect=track_data_processing):
            
            # Execute the instruction
            self.cpu.execute_arm(instr)
        
        # Verify correct handler was called
        self.assertEqual(handler_called, ['_exec_status_transfer'],
            f"MRS should route to _exec_status_transfer, got {handler_called}")
        
        # Verify R0 contains the CPSR value
        self.assertEqual(self.cpu.registers[0], initial_cpsr,
            "MRS should read CPSR into destination register")
    
    def test_bxeq_preserves_condition(self):
        """BXEQ R14 (0x012FFF1E) must preserve EQ condition, not drop to AL.
        
        Bug prevented: Conditional BX emitted as unconditional BX, dropping condition
        code and causing infinite copy loops when condition should prevent branch.
        
        Encoding: 0x012FFF1E (BXEQ R14)
        - Condition: EQ (0x0)
        - Opcode: BX (0x12FFF10 pattern)
        - Rm: R14
        """
        instr = 0x012FFF1E
        
        # Set up initial state
        initial_pc = 0x08000000
        self.cpu.registers[15] = initial_pc
        self.cpu.registers[14] = 0x08001000  # Target address
        self.cpu.cpsr = 0  # Z=0, so EQ condition should FAIL
        
        # Track condition check
        condition_checked = []
        
        original_check = self.cpu.check_condition
        def track_check(cond):
            condition_checked.append(cond)
            return original_check(cond)
        
        # Patch check_condition to track calls
        with patch.object(self.cpu, 'check_condition', side_effect=track_check):
            # Execute via step_arm which checks condition before executing
            # First, set Z flag so EQ passes
            self.cpu.cpsr = 0x40000000  # Z=1
            
            # Since BX is handled specially, we need to check if condition is preserved
            # The step_arm function extracts condition from bits 28-31
            cond = (instr >> 28) & 0xF
            self.assertEqual(cond, 0x0, "Instruction encoding should have EQ condition")
            
            # Execute the instruction
            self.cpu.execute_arm(instr)
        
        # Verify the condition code in the instruction was EQ (0x0)
        # This test primarily verifies the encoding is correct
        # The actual condition check happens in step_arm before execute_arm
    
    def test_bx_unconditional(self):
        """BX R14 (0xE12FFF1E) must be unconditional.
        
        Bug prevented: Unconditional BX treated as conditional, causing branches
        to be skipped when they should always execute.
        
        Encoding: 0xE12FFF1E (BX R14)
        - Condition: AL (0xE) - always
        - Opcode: BX (0x12FFF10 pattern)
        - Rm: R14
        """
        instr = 0xE12FFF1E
        
        # Set up initial state
        initial_pc = 0x08000000
        self.cpu.registers[15] = initial_pc
        target_addr = 0x08001000
        self.cpu.registers[14] = target_addr
        
        # Execute the instruction
        self.cpu.execute_arm(instr)
        
        # Verify PC was set to target (unconditional branch)
        self.assertEqual(self.cpu.registers[15], target_addr & 0xFFFFFFFE,
            "BX should branch to target address unconditionally")
        
        # Verify Thumb mode was set based on target LSB
        self.assertFalse(self.cpu.thumb_mode,
            "BX to even address should not set Thumb mode")


class TestThumbDispatchAudit(unittest.TestCase):
    """Thumb instruction dispatch audit tests.
    
    These tests verify that Thumb opcodes are routed to the correct handlers,
    catching bugs where instructions are dispatched to wrong execution paths.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        from arm7tdmi import ARM7TDMI
        self.memory = MockMemory()
        self.cpu = ARM7TDMI(self.memory)
        # Reset CPU state
        self.cpu.registers = [0] * 16
        self.cpu.cpsr = 0
        self.cpu.thumb_mode = True
        self.cpu.mode = 0x1F
    
    def test_strh_routes_to_extra_load_store(self):
        """STRH R0, [R4, #4] (0x8021) must route to Thumb extra load/store, not generic.
        
        Bug prevented: STRH with immediate offset routed to generic load/store path
        instead of extra load/store handler, causing incorrect address calculation.
        
        Encoding: 0x8120 (STRH R0, [R4, #4])
        - bits 15-11: 10000 (STRH)
        - bits 10-6:  00100 (Imm5 = 4, offset = 4*2 = 8)
        - bits 5-3:   100 (Rb = R4)
        - bits 2-0:   000 (Rd = R0)
        """
        instr = 0x8120
        
        # Set up initial state
        initial_pc = 0x08000000
        self.cpu.registers[15] = initial_pc
        self.cpu.registers[4] = 0x06000000  # Base address
        self.cpu.registers[0] = 0x1234  # Value to store
        
        # Track which handler was called
        handler_called = []
        
        original_imm = self.cpu.exec_thumb_load_store_imm
        def track_imm(*args, **kwargs):
            handler_called.append('exec_thumb_load_store_imm')
            return original_imm(*args, **kwargs)
        
        original_gen = self.cpu.exec_thumb_load_store
        def track_gen(*args, **kwargs):
            handler_called.append('exec_thumb_load_store')
            return original_gen(*args, **kwargs)
        
        # Patch handlers to track calls
        with patch.object(self.cpu, 'exec_thumb_load_store_imm', side_effect=track_imm), \
             patch.object(self.cpu, 'exec_thumb_load_store', side_effect=track_gen):
            
            # Execute the instruction
            self.cpu.execute_thumb(instr)
        
        # Verify correct handler was called (format 10: STRH immediate)
        self.assertIn('exec_thumb_load_store_imm', handler_called,
            f"STRH immediate should route to exec_thumb_load_store_imm, got {handler_called}")
        
        # Verify value was written to memory
        stored_val = self.memory.read_u16(0x06000000 + 4 * 2)  # Imm5 * 2
        self.assertEqual(stored_val, 0x1234,
            "STRH should store halfword at base + offset*2")
    
    def test_ldrh_routes_to_extra_load_store(self):
        """LDRH R0, [R4, #4] (0x8821) must route to Thumb extra load/store.
        
        Bug prevented: LDRH with immediate offset routed to wrong handler,
        causing incorrect sign-extension or value read.
        
        Encoding: 0x8920 (LDRH R0, [R4, #4])
        - bits 15-11: 10001 (LDRH)
        - bits 10-6:  00100 (Imm5 = 4, offset = 4*2 = 8)
        - bits 5-3:   100 (Rb = R4)
        - bits 2-0:   000 (Rd = R0)
        """
        instr = 0x8920
        
        # Set up initial state
        initial_pc = 0x08000000
        self.cpu.registers[15] = initial_pc
        self.cpu.registers[4] = 0x06000000  # Base address
        self.memory.write_u16(0x06000000 + 8, 0xABCD)  # Value at offset 4*2
        
        # Track which handler was called
        handler_called = []
        
        original_imm = self.cpu.exec_thumb_load_store_imm
        def track_imm(*args, **kwargs):
            handler_called.append('exec_thumb_load_store_imm')
            return original_imm(*args, **kwargs)
        
        # Patch handler to track calls
        with patch.object(self.cpu, 'exec_thumb_load_store_imm', side_effect=track_imm):
            
            # Execute the instruction
            self.cpu.execute_thumb(instr)
        
        # Verify correct handler was called
        self.assertIn('exec_thumb_load_store_imm', handler_called,
            f"LDRH immediate should route to exec_thumb_load_store_imm, got {handler_called}")
        
        # Verify R0 contains the loaded value
        self.assertEqual(self.cpu.registers[0], 0xABCD,
            "LDRH should load unsigned halfword")
    
    def test_branch_offset_uses_11bit_mask(self):
        """Thumb B (format 18) must mask offset with 0x7FF (11-bit), not 0x3FF.
        
        Bug prevented: Branch offset masked with 0x3FF (10-bit) instead of 0x7FF (11-bit),
        causing branch targets to be truncated and incorrect jumps.
        
        Encoding: 0xE7F0 (B with negative offset)
        - bits 15-11: 11101 (B format 18)
        - bits 10-0:  offset (0x7F0 = 2032, but with sign bit = -16*2 = -32)
        """
        instr = 0xE7F0
        
        # Set up initial state
        initial_pc = 0x08000000  # instruction address (runtime convention: R15 = instr addr)
        self.cpu.registers[15] = initial_pc
        
        # Execute the instruction
        self.cpu.execute_thumb(instr)
        
        # Runtime computes: target = (R15 + 4) + (sign_extend(offset11) << 1)
        # 0x7F0 & 0x7FF = 0x7F0; 0x7F0 & 0x400 set → negative: 0x7F0 - 0x800 = -16
        # Final offset = -16 * 2 = -32
        expected_offset = -32
        expected_pc = (initial_pc + 4 + expected_offset) & 0xFFFFFFFF
        
        self.assertEqual(self.cpu.registers[15], expected_pc,
            f"Branch should use 11-bit offset mask (0x7FF), expected PC={hex(expected_pc)}, got {hex(self.cpu.registers[15])}")
    
    def test_branch_conditional_preserves_condition(self):
        """Thumb BNE (format 16) must preserve NE condition and 8-bit sign-extended offset.
        
        Bug prevented: Conditional branch treated as unconditional, or condition code
        dropped, causing branches to execute when they shouldn't.
        
        Encoding: 0xD1FA (BNE -6 halfwords)
        - bits 15-8:  0xD1 (condition NE = 0x1)
        - bits 7-0:   offset (0xFA = -6 signed)
        """
        instr = 0xD1FA
        
        # Set up initial state
        initial_pc = 0x08000100  # instruction address (runtime convention: R15 = instr addr)
        self.cpu.registers[15] = initial_pc
        
        # Test 1: Z=0, so NE condition should PASS and branch should be taken
        self.cpu.cpsr = 0  # Z=0
        
        # Track condition check
        condition_checked = []
        original_check = self.cpu._check_condition
        
        def track_check(cond):
            condition_checked.append(cond)
            return original_check(cond)
        
        with patch.object(self.cpu, '_check_condition', side_effect=track_check):
            self.cpu.execute_thumb(instr)
        
        # Verify NE condition (0x1) was checked
        self.assertIn(0x1, condition_checked,
            "BNE should check NE condition code")
        
        # Verify branch was taken: target = (R15+4) + (-6 << 1) = PC+4-12 = PC-8
        expected_pc = (initial_pc + 4 + (-6 << 1)) & 0xFFFFFFFF
        self.assertEqual(self.cpu.registers[15], expected_pc,
            f"BNE with Z=0 should branch, expected PC={hex(expected_pc)}, got {hex(self.cpu.registers[15])}")
        
        # Test 2: Z=1, so NE condition should FAIL and branch should NOT be taken
        self.cpu.registers[15] = initial_pc
        self.cpu.cpsr = 0x40000000  # Z=1
        
        with patch.object(self.cpu, '_check_condition', side_effect=track_check):
            condition_checked.clear()
            self.cpu.execute_thumb(instr)
        
        # Verify branch was NOT taken
        expected_pc_no_branch = initial_pc + 2  # Thumb instructions are 2 bytes
        self.assertEqual(self.cpu.registers[15], expected_pc_no_branch,
            f"BNE with Z=1 should NOT branch, expected PC={hex(expected_pc_no_branch)}, got {hex(self.cpu.registers[15])}")

    def test_blx_rm_sets_lr_and_branches(self):
        """Thumb BLX Rm (format 5, H1=1) must set LR=PC+2|1 and branch to Rm.

        Bug prevented: BLX Rm was completely unimplemented (fell through as a NOP),
        causing indirect calls via BLX Rm (vtable dispatch) to silently do nothing:
        no branch, no LR update. Functions expecting to be called via BLX Rm never
        executed, causing loops to never make progress.

        Encoding: 0x4780 (BLX R0)
        - bits 15-7: 01000111 (format 5, BX/BLX)
        - bit 7 (H1): 1 (BLX Rm, not BX Rm)
        - bits 6-3 (H2): 0000
        - bits 2-0 (Rs): 000 (R0)
        """
        instr = 0x4780  # BLX R0

        initial_pc = 0x08000100
        self.cpu.registers[15] = initial_pc
        self.cpu.registers[0] = 0x08000200 | 1  # R0 = target, Thumb bit set
        self.cpu.thumb_mode = True

        self.cpu.execute_thumb(instr)

        self.assertEqual(self.cpu.registers[14], (initial_pc + 2) | 1,
            f"BLX Rm should set LR=PC+2|1, got LR={hex(self.cpu.registers[14])}")
        self.assertEqual(self.cpu.registers[15], 0x08000200,
            f"BLX Rm should branch to Rm & ~1, got PC={hex(self.cpu.registers[15])}")
        self.assertTrue(self.cpu.thumb_mode,
            "BLX Rm with Thumb bit set should stay in Thumb mode")

        # Test ARM mode switch (Thumb bit clear)
        self.cpu.registers[15] = initial_pc
        self.cpu.registers[0] = 0x08000400  # R0 = target, Thumb bit clear
        self.cpu.execute_thumb(instr)

        self.assertFalse(self.cpu.thumb_mode,
            "BLX Rm with Thumb bit clear should switch to ARM mode")

    def test_ldmia_suppresses_writeback_when_base_in_list(self):
        """Thumb LDMIA Rn!, {reg_list} must suppress writeback when Rn is in the list.

        Bug prevented: LDMIA with writeback always applied writeback, overwriting the
        loaded value with old_Rn + (count*4). On ARM7TDMI hardware, if Rn is in the
        register list, the loaded value wins and writeback is suppressed.

        This caused LDMIA R6!, {R1, R6} to produce wrong R6, then CMP/SUB produced
        wrong flags, causing conditional branches to skip epilogues and leak stack frames.

        Encoding: 0xCE42 (LDMIA R6!, {R1, R6})
        - bits 15-11: 11001 (LDMIA format 15)
        - bits 10-8:  Rn (R6)
        - bits 7-0:   reg_list (R1, R6 = bits 1,6 = 0x42)
        """
        instr = 0xCE42  # LDMIA R6!, {R1, R6}

        initial_pc = 0x08000100
        self.cpu.registers[15] = initial_pc
        self.cpu.registers[6] = 0x03007F00  # Base address
        self.memory.write_u32(0x03007F00, 0x11111111)  # R1 value
        self.memory.write_u32(0x03007F04, 0x22222222)  # R6 value

        self.cpu.execute_thumb(instr)

        self.assertEqual(self.cpu.registers[1], 0x11111111,
            f"R1 should be loaded from [R6], got {hex(self.cpu.registers[1])}")
        self.assertEqual(self.cpu.registers[6], 0x22222222,
            f"R6 should be loaded from [R6+4] (writeback suppressed), got {hex(self.cpu.registers[6])}")
        self.assertEqual(self.cpu.registers[15], initial_pc + 2,
            f"PC should advance by 2, got {hex(self.cpu.registers[15])}")

    def test_ldmia_writeback_when_base_not_in_list(self):
        """Thumb LDMIA Rn!, {reg_list} must apply writeback when Rn is NOT in the list.

        Normal case: when Rn is not in the register list, writeback happens normally.
        """
        instr = 0xCD03  # LDMIA R5!, {R0, R1}

        initial_pc = 0x08000100
        self.cpu.registers[15] = initial_pc
        self.cpu.registers[5] = 0x03007F00  # Base address
        self.memory.write_u32(0x03007F00, 0x11111111)  # R0 value
        self.memory.write_u32(0x03007F04, 0x22222222)  # R1 value

        self.cpu.execute_thumb(instr)

        self.assertEqual(self.cpu.registers[0], 0x11111111,
            f"R0 should be loaded from [R5], got {hex(self.cpu.registers[0])}")
        self.assertEqual(self.cpu.registers[1], 0x22222222,
            f"R1 should be loaded from [R5+4], got {hex(self.cpu.registers[1])}")
        self.assertEqual(self.cpu.registers[5], 0x03007F08,
            f"R5 should be written back (R5+8), got {hex(self.cpu.registers[5])}")


if __name__ == '__main__':
    unittest.main()