"""LDM/STM writeback audit tests for ARM7TDMI.

Verifies that all 4 ARM addressing modes (IA, IB, DA, DB) compute correct
addresses and writeback values, and that Thumb LDM/STM writeback is correct.

Run: python3 -m pytest test_ldm_stm.py -v
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class MockMemory:
    def __init__(self):
        self.data = {}

    def read_u32(self, addr):
        addr &= 0xFFFFFFFF
        return (self.data.get(addr, 0)
                | (self.data.get(addr + 1, 0) << 8)
                | (self.data.get(addr + 2, 0) << 16)
                | (self.data.get(addr + 3, 0) << 24))

    def write_u32(self, addr, value):
        addr &= 0xFFFFFFFF
        self.data[addr] = value & 0xFF
        self.data[addr + 1] = (value >> 8) & 0xFF
        self.data[addr + 2] = (value >> 16) & 0xFF
        self.data[addr + 3] = (value >> 24) & 0xFF


# ARM LDM/STM encoding: cond(4) | 100(3) | P(1) U(1) S(1) W(1) L(1) | Rn(4) | reglist(16)
# P=pre/post  U=up/down  S=0  W=writeback  L=load(1)/store(0)

def stmia(rn, reglist, w=1):
    return 0xE8800000 | (w << 21) | (rn << 16) | reglist

def stmib(rn, reglist, w=1):
    return 0xE9800000 | (w << 21) | (rn << 16) | reglist

def stmda(rn, reglist, w=1):
    return 0xE8000000 | (w << 21) | (rn << 16) | reglist

def stmdb(rn, reglist, w=1):
    return 0xE9000000 | (w << 21) | (rn << 16) | reglist

def ldmia(rn, reglist, w=1):
    return 0xE8900000 | (w << 21) | (rn << 16) | reglist

def ldmib(rn, reglist, w=1):
    return 0xE9900000 | (w << 21) | (rn << 16) | reglist

def ldmda(rn, reglist, w=1):
    return 0xE8100000 | (w << 21) | (rn << 16) | reglist

def ldmdm(rn, reglist, w=1):
    return 0xE9100000 | (w << 21) | (rn << 16) | reglist


class TestARMBlockTransfer(unittest.TestCase):

    def setUp(self):
        from arm7tdmi import ARM7TDMI
        self.memory = MockMemory()
        self.cpu = ARM7TDMI(self.memory)
        self.cpu.registers = [0] * 16
        self.cpu.cpsr = 0
        self.cpu.thumb_mode = False
        self.cpu.mode = 0x1F
        self.cpu.registers[15] = 0x08000000

    # ---- STM tests: verify values written and writeback ----

    def test_stmia_store_and_writeback(self):
        """STMIA R0!, {R1, R2, R3}: store at base+0, base+4, base+8; writeback base+12."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.cpu.registers[1] = 0xAA
        self.cpu.registers[2] = 0xBB
        self.cpu.registers[3] = 0xCC

        self.cpu.exec_block_transfer(stmia(0, 0b1110))

        self.assertEqual(self.memory.read_u32(base + 0), 0xAA)
        self.assertEqual(self.memory.read_u32(base + 4), 0xBB)
        self.assertEqual(self.memory.read_u32(base + 8), 0xCC)
        self.assertEqual(self.cpu.registers[0], base + 12)

    def test_stmib_store_and_writeback(self):
        """STMIB R0!, {R1, R2, R3}: store at base+4, base+8, base+12; writeback base+12."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.cpu.registers[1] = 0xAA
        self.cpu.registers[2] = 0xBB
        self.cpu.registers[3] = 0xCC

        self.cpu.exec_block_transfer(stmib(0, 0b1110))

        self.assertEqual(self.memory.read_u32(base + 4), 0xAA)
        self.assertEqual(self.memory.read_u32(base + 8), 0xBB)
        self.assertEqual(self.memory.read_u32(base + 12), 0xCC)
        self.assertEqual(self.cpu.registers[0], base + 12)

    def test_stmda_store_and_writeback(self):
        """STMDA R0!, {R1, R2, R3}: store at base, base-4, base-8; writeback base-12."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.cpu.registers[1] = 0xAA
        self.cpu.registers[2] = 0xBB
        self.cpu.registers[3] = 0xCC

        self.cpu.exec_block_transfer(stmda(0, 0b1110))

        # DA: lowest reg → lowest addr. base-8, base-4, base
        self.assertEqual(self.memory.read_u32(base - 8), 0xAA)
        self.assertEqual(self.memory.read_u32(base - 4), 0xBB)
        self.assertEqual(self.memory.read_u32(base + 0), 0xCC)
        self.assertEqual(self.cpu.registers[0], base - 12)

    def test_stmdb_store_and_writeback(self):
        """STMDB R0!, {R1, R2, R3}: store at base-4, base-8, base-12; writeback base-12."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.cpu.registers[1] = 0xAA
        self.cpu.registers[2] = 0xBB
        self.cpu.registers[3] = 0xCC

        self.cpu.exec_block_transfer(stmdb(0, 0b1110))

        self.assertEqual(self.memory.read_u32(base - 12), 0xAA)
        self.assertEqual(self.memory.read_u32(base - 8), 0xBB)
        self.assertEqual(self.memory.read_u32(base - 4), 0xCC)
        self.assertEqual(self.cpu.registers[0], base - 12)

    # ---- LDM tests: verify values loaded and writeback ----

    def test_ldmia_load_and_writeback(self):
        """LDMIA R0!, {R1, R2, R3}: load from base+0, +4, +8; writeback base+12."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.memory.write_u32(base + 0, 0x1111)
        self.memory.write_u32(base + 4, 0x2222)
        self.memory.write_u32(base + 8, 0x3333)

        self.cpu.exec_block_transfer(ldmia(0, 0b1110))

        self.assertEqual(self.cpu.registers[1], 0x1111)
        self.assertEqual(self.cpu.registers[2], 0x2222)
        self.assertEqual(self.cpu.registers[3], 0x3333)
        self.assertEqual(self.cpu.registers[0], base + 12)

    def test_ldmib_load_and_writeback(self):
        """LDMIB R0!, {R1, R2, R3}: load from base+4, +8, +12; writeback base+12."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.memory.write_u32(base + 4, 0x1111)
        self.memory.write_u32(base + 8, 0x2222)
        self.memory.write_u32(base + 12, 0x3333)

        self.cpu.exec_block_transfer(ldmib(0, 0b1110))

        self.assertEqual(self.cpu.registers[1], 0x1111)
        self.assertEqual(self.cpu.registers[2], 0x2222)
        self.assertEqual(self.cpu.registers[3], 0x3333)
        self.assertEqual(self.cpu.registers[0], base + 12)

    def test_ldmda_load_and_writeback(self):
        """LDMDA R0!, {R1, R2, R3}: load from base-8, -4, 0; writeback base-12."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.memory.write_u32(base - 8, 0x1111)
        self.memory.write_u32(base - 4, 0x2222)
        self.memory.write_u32(base + 0, 0x3333)

        self.cpu.exec_block_transfer(ldmda(0, 0b1110))

        self.assertEqual(self.cpu.registers[1], 0x1111)
        self.assertEqual(self.cpu.registers[2], 0x2222)
        self.assertEqual(self.cpu.registers[3], 0x3333)
        self.assertEqual(self.cpu.registers[0], base - 12)

    def test_ldmdb_load_and_writeback(self):
        """LDMDB R0!, {R1, R2, R3}: load from base-12, -8, -4; writeback base-12."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.memory.write_u32(base - 12, 0x1111)
        self.memory.write_u32(base - 8, 0x2222)
        self.memory.write_u32(base - 4, 0x3333)

        self.cpu.exec_block_transfer(ldmdm(0, 0b1110))

        self.assertEqual(self.cpu.registers[1], 0x1111)
        self.assertEqual(self.cpu.registers[2], 0x2222)
        self.assertEqual(self.cpu.registers[3], 0x3333)
        self.assertEqual(self.cpu.registers[0], base - 12)

    # ---- No-writeback tests ----

    def test_stmia_no_writeback(self):
        """STMIA R0, {R1} without W bit: base register unchanged."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.cpu.registers[1] = 0x42

        self.cpu.exec_block_transfer(stmia(0, 0b0010, w=0))

        self.assertEqual(self.memory.read_u32(base), 0x42)
        self.assertEqual(self.cpu.registers[0], base)

    def test_ldmia_no_writeback(self):
        """LDMIA R0, {R1} without W bit: base register unchanged."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.memory.write_u32(base, 0x99)

        self.cpu.exec_block_transfer(ldmia(0, 0b0010, w=0))

        self.assertEqual(self.cpu.registers[1], 0x99)
        self.assertEqual(self.cpu.registers[0], base)

    # ---- Register order: lowest reg to lowest address ----

    def test_stmia_register_order(self):
        """STMIA stores R0 first (lowest addr), R15 last (highest addr)."""
        base = 0x02000000
        self.cpu.registers[0] = base
        self.cpu.registers[1] = 0x01
        self.cpu.registers[4] = 0x04
        self.cpu.registers[5] = 0x05

        self.cpu.exec_block_transfer(stmia(0, (1 << 1) | (1 << 4) | (1 << 5)))

        # R1 → lowest addr, R4 → next, R5 → highest
        self.assertEqual(self.memory.read_u32(base + 0), 0x01)
        self.assertEqual(self.memory.read_u32(base + 4), 0x04)
        self.assertEqual(self.memory.read_u32(base + 8), 0x05)

    def test_stmdb_register_order(self):
        """STMDB stores R1 at base-12, R4 at base-8, R5 at base-4 (ascending in memory)."""
        base = 0x02000020
        self.cpu.registers[0] = base
        self.cpu.registers[1] = 0x01
        self.cpu.registers[4] = 0x04
        self.cpu.registers[5] = 0x05

        self.cpu.exec_block_transfer(stmdb(0, (1 << 1) | (1 << 4) | (1 << 5)))

        self.assertEqual(self.memory.read_u32(base - 12), 0x01)
        self.assertEqual(self.memory.read_u32(base - 8), 0x04)
        self.assertEqual(self.memory.read_u32(base - 4), 0x05)

    # ---- Empty register list ----

    def test_empty_reglist_arm(self):
        """ARM LDM/STM with empty register list returns 2, no memory access."""
        base = 0x02000100
        self.cpu.registers[0] = base

        cycles = self.cpu.exec_block_transfer(ldmia(0, 0, w=1))

        self.assertEqual(cycles, 2)
        self.assertEqual(self.cpu.registers[0], base)

    # ---- Single register ----

    def test_stmia_single_reg(self):
        """STMIA R0!, {R5}: one register, writeback base+4."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.cpu.registers[5] = 0xDEAD

        self.cpu.exec_block_transfer(stmia(0, (1 << 5)))

        self.assertEqual(self.memory.read_u32(base), 0xDEAD)
        self.assertEqual(self.cpu.registers[0], base + 4)


class TestThumbBlockTransfer(unittest.TestCase):

    def setUp(self):
        from arm7tdmi import ARM7TDMI
        self.memory = MockMemory()
        self.cpu = ARM7TDMI(self.memory)
        self.cpu.registers = [0] * 16
        self.cpu.cpsr = 0
        self.cpu.thumb_mode = True
        self.cpu.mode = 0x1F
        self.cpu.registers[15] = 0x08000000

    def _thumb_ldm_stm(self, is_load, rb, reglist):
        return (is_load << 11) | (rb << 8) | reglist

    def test_thumb_stm_writeback(self):
        """Thumb STM R0!, {R1, R2}: stores at base, base+4; writeback base+8."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.cpu.registers[1] = 0xAA
        self.cpu.registers[2] = 0xBB

        instr = self._thumb_ldm_stm(0, 0, 0b110)
        self.cpu.exec_thumb_ldm_stm(instr)

        self.assertEqual(self.memory.read_u32(base + 0), 0xAA)
        self.assertEqual(self.memory.read_u32(base + 4), 0xBB)
        self.assertEqual(self.cpu.registers[0], base + 8)

    def test_thumb_ldm_writeback(self):
        """Thumb LDM R0!, {R1, R2}: loads from base, base+4; writeback base+8."""
        base = 0x02000100
        self.cpu.registers[0] = base
        self.memory.write_u32(base + 0, 0x1111)
        self.memory.write_u32(base + 4, 0x2222)

        instr = self._thumb_ldm_stm(1, 0, 0b110)
        self.cpu.exec_thumb_ldm_stm(instr)

        self.assertEqual(self.cpu.registers[1], 0x1111)
        self.assertEqual(self.cpu.registers[2], 0x2222)
        self.assertEqual(self.cpu.registers[0], base + 8)

    def test_thumb_stm_single_reg(self):
        """Thumb STM R3!, {R4}: one register, writeback base+4."""
        base = 0x03000000
        self.cpu.registers[3] = base
        self.cpu.registers[4] = 0x77

        instr = self._thumb_ldm_stm(0, 3, (1 << 4))
        self.cpu.exec_thumb_ldm_stm(instr)

        self.assertEqual(self.memory.read_u32(base), 0x77)
        self.assertEqual(self.cpu.registers[3], base + 4)

    def test_thumb_ldm_empty_reglist(self):
        """Thumb LDM with empty register list: just advances PC by 2, no writeback."""
        base = 0x02000100
        self.cpu.registers[0] = base

        instr = self._thumb_ldm_stm(1, 0, 0)
        cycles = self.cpu.exec_thumb_ldm_stm(instr)

        self.assertEqual(cycles, 1)
        self.assertEqual(self.cpu.registers[0], base)

    def test_thumb_stm_many_regs(self):
        """Thumb STM R7!, {R0-R6}: stores 7 registers, writeback base+28."""
        base = 0x02000000
        self.cpu.registers[7] = base
        for i in range(7):
            self.cpu.registers[i] = 0x100 + i

        instr = self._thumb_ldm_stm(0, 7, 0x7F)
        self.cpu.exec_thumb_ldm_stm(instr)

        for i in range(7):
            self.assertEqual(self.memory.read_u32(base + i * 4), 0x100 + i)
        self.assertEqual(self.cpu.registers[7], base + 28)


if __name__ == '__main__':
    unittest.main()
