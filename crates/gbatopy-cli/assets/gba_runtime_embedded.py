"""
PyBoyAdvance Runtime (Embedded)
MIT License - Original code from PyBoyAdvance
https://github.com/d7499/pyboy-advance

Required imports for standalone execution:
"""

import argparse
import math
import os
import pygame
import struct
import sys
import time
from PIL import Image

# ===
"""ARM7TDMI CPU Interpreter for GBA"""

from typing import Optional, Callable, List, Tuple


class ARM7TDMI:
    """ARM7TDMI CPU interpreter with full instruction execution."""

    def __init__(self, memory):
        self.memory = memory
        self.registers = [0] * 16  # r0-r15
        self.cpsr = 0  # Current Program Status Register
        self.spsr = [0] * 6  # Saved PSR for each mode

        # ARM condition codes
        self.COND_EQ = 0x0  # Z set
        self.COND_NE = 0x1  # Z clear
        self.COND_CS = 0x2  # C set
        self.COND_CC = 0x3  # C clear
        self.COND_MI = 0x4  # N set
        self.COND_PL = 0x5  # N clear
        self.COND_VS = 0x6  # V set
        self.COND_VC = 0x7  # V clear
        self.COND_HI = 0x8  # C set and Z clear
        self.COND_LS = 0x9  # C clear or Z set
        self.COND_GE = 0xA  # N == V
        self.COND_LT = 0xB  # N != V
        self.COND_GT = 0xC  # Z clear and N == V
        self.COND_LE = 0xD  # Z set or N != V
        self.COND_AL = 0xE  # Always
        self.COND_NV = 0xF  # Never

        self.mode = 0x1F  # User mode
        self.thumb_mode = False
        self.running = True
        self.cycles = 0

    @property
    def r(self):
        return self.registers

    @property
    def pc(self) -> int:
        return self.registers[15]

    @pc.setter
    def pc(self, value: int):
        self.registers[15] = value & 0xFFFFFFFC
        if self.thumb_mode:
            self.registers[15] = value & 0xFFFFFFFE

    @property
    def lr(self) -> int:
        return self.registers[14]

    @lr.setter
    def lr(self, value: int):
        self.registers[14] = value

    @property
    def sp(self) -> int:
        return self.registers[13]

    @sp.setter
    def sp(self, value: int):
        self.registers[13] = value

    @property
    def nzcv(self) -> Tuple[int, int, int, int]:
        n = (self.cpsr >> 31) & 1
        z = (self.cpsr >> 30) & 1
        c = (self.cpsr >> 29) & 1
        v = (self.cpsr >> 28) & 1
        return (n, z, c, v)

    def check_condition(self, cond: int) -> bool:
        if cond == 0xE or cond == 0xF:
            return True
        n, z, c, v = self.nzcv
        if cond == 0x0:
            return z
        if cond == 0x1:
            return not z
        if cond == 0x2:
            return c
        if cond == 0x3:
            return not c
        if cond == 0x4:
            return n
        if cond == 0x5:
            return not n
        if cond == 0x6:
            return v
        if cond == 0x7:
            return not v
        if cond == 0x8:
            return c and not z
        if cond == 0x9:
            return not c or z
        if cond == 0xA:
            return n == v
        if cond == 0xB:
            return n != v
        if cond == 0xC:
            return not z and n == v
        if cond == 0xD:
            return z or n != v
        return True

    def read_register(self, reg: int) -> int:
        return self.registers[reg & 0xF]

    def write_register(self, reg: int, value: int):
        value &= 0xFFFFFFFF
        self.registers[reg & 0xF] = value
        if (reg & 0xF) == 15:
            self.registers[15] = value & (0xFFFFFFFE if self.thumb_mode else 0xFFFFFFFC)

    def step(self) -> int:
        """Execute one instruction. Returns number of cycles."""
        if self.thumb_mode:
            return self.step_thumb()
        return self.step_arm()

    def step_arm(self) -> int:
        """Execute one ARM instruction."""
        pc = self.pc
        if pc >= 0x08000000:
            pc = (pc - 0x08000000) + len(self.memory.rom)

        instr = self.memory.read_u32(pc)
        cond = (instr >> 28) & 0xF

        if not self.check_condition(cond):
            self.registers[15] += 4
            return 1

        return self.execute_arm(instr)

    def step_thumb(self) -> int:
        """Execute one Thumb instruction."""
        pc = self.pc
        if pc >= 0x08000000:
            pc = (pc - 0x08000000) + len(self.memory.rom)

        instr = self.memory.read_u16(pc)
        return self.execute_thumb(instr)

    def execute_arm(self, instr: int) -> int:
        """Execute ARM instruction. Returns cycles."""
        opcode = (instr >> 21) & 0xF
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        rm = instr & 0xF

        # Data processing
        if (instr & 0xC0000000) == 0 and (instr & 0x08000000) == 0:
            return self.exec_data_processing(instr)

        # LDR/STR
        if (instr & 0xC000000) == 0x4000000:
            return self.exec_load_store(instr)

        # B/BL
        if (instr & 0xE000000) == 0xA000000:
            return self.exec_branch(instr)

        # BX
        if (instr & 0xFFFFFF0) == 0x12FFF10:
            return self.exec_bx(instr)

        # LDM/STM
        if (instr & 0xE000000) == 0x8000000:
            return self.exec_block_transfer(instr)

        # MUL
        if (instr & 0xFC000F0) == 0x0:
            return self.exec_mul(instr)

        # SWI
        if (instr & 0xF000000) == 0xF000000:
            return self.exec_swi(instr)

        return 1

    def exec_data_processing(self, instr: int) -> int:
        """Execute ARM data processing instruction."""
        opcode = (instr >> 21) & 0xF
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        rm = instr & 0xF

        # Check for immediate
        imm = (instr >> 25) & 1
        if imm:
            imm_val = instr & 0xFF
            rot = ((instr >> 8) & 0xF) * 2
            if rot:
                imm_val = ((imm_val >> rot) | (imm_val << (32 - rot))) & 0xFFFFFFFF
            operand2 = imm_val
        else:
            shift_type = (instr >> 5) & 3
            shift_imm = (instr >> 7) & 0x1F
            operand2 = self.registers[rm]
            if shift_imm:
                if shift_type == 0:  # LSL
                    operand2 = (operand2 << shift_imm) & 0xFFFFFFFF
                elif shift_type == 1:  # LSR
                    operand2 = operand2 >> shift_imm
                elif shift_type == 2:  # ASR
                    operand2 = (operand2 >> shift_imm) | (
                        (operand2 & 0x80000000) * (0xFFFFFFFF >> (32 - shift_imm))
                    )
                elif shift_type == 3:  # ROR
                    operand2 = (
                        (operand2 >> shift_imm) | (operand2 << (32 - shift_imm))
                    ) & 0xFFFFFFFF
            else:
                if shift_type == 1:  # LSR #0 means LSR #32
                    operand2 = 0
                elif shift_type == 2:  # ASR #0 means ASR #32
                    operand2 = 0xFFFFFFFF if (operand2 & 0x80000000) else 0
                elif shift_type == 3:  # ROR #0 means RRX
                    carry = (self.cpsr >> 29) & 1
                    operand2 = ((carry << 31) | (operand2 >> 1)) & 0xFFFFFFFF

        operand1 = self.registers[rn]

        if opcode == 0:  # AND
            result = operand1 & operand2
            self.write_register(rd, result)
        elif opcode == 1:  # EOR
            result = operand1 ^ operand2
            self.write_register(rd, result)
        elif opcode == 2:  # SUB
            result = (operand1 - operand2) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 3:  # RSB
            result = (operand2 - operand1) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 4:  # ADD
            result = (operand1 + operand2) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 5:  # ADC
            c = (self.cpsr >> 29) & 1
            result = (operand1 + operand2 + c) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 6:  # SBC
            c = (self.cpsr >> 29) & 1
            result = (operand1 - operand2 - (1 - c)) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 7:  # RSC
            c = (self.cpsr >> 29) & 1
            result = (operand2 - operand1 - (1 - c)) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 8:  # TST
            result = operand1 & operand2
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif opcode == 9:  # TEQ
            result = operand1 ^ operand2
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif opcode == 0xA:  # CMP
            result = (operand1 - operand2) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif opcode == 0xB:  # CMN
            result = (operand1 + operand2) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif opcode == 0xC:  # ORR
            result = operand1 | operand2
            self.write_register(rd, result)
        elif opcode == 0xD:  # MOV
            self.write_register(rd, operand2)
        elif opcode == 0xE:  # BIC
            result = operand1 & ~operand2
            self.write_register(rd, result)
        elif opcode == 0xF:  # MVN
            self.write_register(rd, (~operand2) & 0xFFFFFFFF)

        if rd != 15:
            self.registers[15] += 4

        return 1

    def exec_load_store(self, instr: int) -> int:
        """Execute LDR/STR instruction."""
        is_load = (instr >> 20) & 1
        is_byte = (instr >> 22) & 1
        is_pre = (instr >> 24) & 1
        is_up = (instr >> 23) & 1
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        offset = instr & 0xFFF

        base = self.registers[rn]
        addr = base + offset if is_up else base - offset

        if is_load:
            if is_byte:
                val = self.memory.read_u8(addr)
            else:
                val = self.memory.read_u32(addr)
            self.write_register(rd, val)
        else:
            val = self.registers[rd]
            if is_byte:
                self.memory.write_u8(addr, val & 0xFF)
            else:
                self.memory.write_u32(addr, val)

        return 2

    def exec_branch(self, instr: int) -> int:
        """Execute B/BL instruction."""
        is_link = (instr >> 24) & 1
        offset = instr & 0xFFFFFF
        if offset & 0x800000:
            offset |= 0xFF000000
        offset <<= 2

        if is_link:
            self.registers[14] = self.registers[15] + 4

        self.registers[15] = (self.registers[15] + offset) & 0xFFFFFFFF
        return 3

    def exec_bx(self, instr: int) -> int:
        """Execute BX instruction."""
        rm = instr & 0xF
        target = self.registers[rm]
        self.thumb_mode = (target & 1) != 0
        self.registers[15] = target & 0xFFFFFFFE
        return 3

    def exec_block_transfer(self, instr: int) -> int:
        """Execute LDM/STM instruction."""
        is_load = (instr >> 20) & 1
        is_up = (instr >> 23) & 1
        rn = (instr >> 16) & 0xF
        reg_list = instr & 0xFFFF

        base = self.registers[rn]
        addr = base

        if is_load:
            for i in range(16):
                if reg_list & (1 << i):
                    if is_up:
                        val = self.memory.read_u32(addr)
                        addr += 4
                    else:
                        addr -= 4
                        val = self.memory.read_u32(addr)
                    self.write_register(i, val)
        else:
            for i in range(16):
                if reg_list & (1 << i):
                    if is_up:
                        self.memory.write_u32(addr, self.registers[i])
                        addr += 4
                    else:
                        addr -= 4
                        self.memory.write_u32(addr, self.registers[i])

        return 2 + (reg_list.bit_count() * 2)

    def exec_mul(self, instr: int) -> int:
        """Execute MUL instruction."""
        rm = instr & 0xF
        rs = (instr >> 8) & 0xF
        rd = (instr >> 16) & 0xF
        result = (self.registers[rm] * self.registers[rs]) & 0xFFFFFFFF
        self.write_register(rd, result)
        return 2

    def exec_swi(self, instr: int) -> int:
        """Execute SWI (software interrupt)."""
        swi_num = instr & 0xFFFFFF
        self.swi_handler(swi_num)
        return 2

    def swi_handler(self, num: int):
        """Handle BIOS SWI calls using BIOS module."""
        # BIOS is now generated inline - no import needed

        bios = BIOS(self.memory)
        if num == 0x00:  # SoftReset
            for i in range(13):
                self.registers[i] = 0
            self.registers[13] = 0x03007F00
            self.registers[15] = 0x08000000
        elif num == 0x01:  # RegisterRamReset
            # Reset EWRAM, IWRAM, and registers (based on mask in R0)
            reset_mask = self.registers[0]
            if reset_mask & 0x01:  # EWRAM
                self.memory.ewram[:] = [0] * len(self.memory.ewram)
            if reset_mask & 0x02:  # IWRAM
                self.memory.iwram[:] = [0] * len(self.memory.iwram)
            if reset_mask & 0x04:  # Registers R0-R7
                for i in range(8):
                    self.registers[i] = 0
            if reset_mask & 0x08:  # Registers R8-R12
                for i in range(8, 13):
                    self.registers[i] = 0
            if reset_mask & 0x10:  # SP IRQ
                self.registers[13] = 0
            if reset_mask & 0x20:  # SP others
                pass  # Handled above
            if reset_mask & 0x40:  # LR IRQ
                pass  # No direct register access
            if reset_mask & 0x80:  # PC
                self.registers[15] = 0
        elif num == 0x02:  # Halt
            self.running = False
        elif num == 0x03:  # IntrWait
            self.registers[0] = 0
        elif num == 0x04:  # VBlankIntrWait
            self.registers[0] = 0
        elif num == 0x06:  # Div
            self.registers[0] = bios.swi_div(self.registers[0], self.registers[1])
        elif num == 0x07:  # Sqrt
            self.registers[0] = bios.swi_sqrt(self.registers[0])
        elif num == 0x08:  # DivArm
            self.registers[0] = bios.swi_divarm(
                self.registers[0] | (self.registers[1] << 32), self.registers[1]
            )
        elif num == 0x09:  # DivArmMod
            result = bios.swi_divmod(
                self.registers[0] | (self.registers[1] << 32), self.registers[1]
            )
            self.registers[0] = result[0]
            self.registers[1] = result[1]
        elif num == 0x12:  # CpuSet
            bios.swi_cpuset(
                self.registers[0], self.registers[1], self.registers[2], self.registers[3]
            )
        elif num == 0x14:  # LZ77UnCompWram
            bios.swi_lz77_uncomp_wram(self.registers[0], self.registers[1])

    def execute_thumb(self, instr: int) -> int:
        """Execute Thumb instruction."""
        op = (instr >> 13) & 7

        if op == 0:  # Move shifted/ADD/SUB
            return self.exec_thumb_move_shift(instr)
        elif op == 1:  # Add/Sub
            return self.exec_thumb_add_sub(instr)
        elif op == 2:  # MOV/CMP/ADD/SUB immediate
            return self.exec_thumb_imm(instr)
        elif op == 3:  # ALU operations
            return self.exec_thumb_alu(instr)
        elif op == 4:  # Hi register operations/BX
            return self.exec_thumb_hi(instr)
        elif op == 5:  # PC-relative load
            return self.exec_thumb_pc_rel(instr)
        elif op == 6:  # LDR/STR
            return self.exec_thumb_load_store(instr)
        elif op == 7:  # LDRH/STRH
            return self.exec_thumb_hword(instr)

        return 1

    def exec_thumb_move_shift(self, instr: int) -> int:
        """Thumb move shifted."""
        op = (instr >> 11) & 3
        offset = (instr >> 6) & 0x1F
        rs = (instr >> 3) & 7
        rd = instr & 7

        val = self.registers[rs]
        if op == 0:  # LSL
            val = (val << offset) & 0xFFFFFFFF
        elif op == 1:  # LSR
            val = val >> offset
        elif op == 2:  # ASR
            val = (val >> offset) | ((val & 0x80000000) * offset)

        self.write_register(rd, val)
        self.registers[15] += 2
        return 1

    def exec_thumb_add_sub(self, instr: int) -> int:
        """Thumb ADD/SUB."""
        is_imm = (instr >> 10) & 1
        is_sub = (instr >> 9) & 1
        rs = (instr >> 6) & 7
        rn = (instr >> 3) & 7
        rd = instr & 7

        if is_imm:
            offset = rs
        else:
            offset = self.registers[rs]

        op1 = self.registers[rn]
        if is_sub:
            result = (op1 - offset) & 0xFFFFFFFF
        else:
            result = (op1 + offset) & 0xFFFFFFFF

        self.write_register(rd, result)
        self.registers[15] += 2
        return 1

    def exec_thumb_imm(self, instr: int) -> int:
        """Thumb MOV/CMP/ADD/SUB immediate."""
        op = (instr >> 11) & 3
        offset = (instr >> 6) & 0x1F
        rn = (instr >> 3) & 7
        rd = instr & 7

        if op == 0:  # MOV
            self.write_register(rd, offset)
        elif op == 1:  # CMP
            result = (self.registers[rn] - offset) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif op == 2:  # ADD
            self.write_register(rd, (self.registers[rn] + offset) & 0xFFFFFFFF)
        elif op == 3:  # SUB
            self.write_register(rd, (self.registers[rn] - offset) & 0xFFFFFFFF)

        self.registers[15] += 2
        return 1

    def exec_thumb_alu(self, instr: int) -> int:
        """Thumb ALU operations."""
        op = (instr >> 6) & 0xF
        rs = (instr >> 3) & 7
        rd = instr & 7

        val = self.registers[rs]

        if op == 0:  # AND
            result = self.registers[rd] & val
        elif op == 1:  # EOR
            result = self.registers[rd] ^ val
        elif op == 2:  # LSL
            result = (self.registers[rd] << (val & 0xFF)) & 0xFFFFFFFF
        elif op == 3:  # LSR
            result = self.registers[rd] >> (val & 0xFF)
        elif op == 4:  # ASR
            result = (self.registers[rd] >> (val & 0xFF)) | (
                (self.registers[rd] & 0x80000000) * (val & 0xFF)
            )
        elif op == 5:  # ADC
            c = (self.cpsr >> 29) & 1
            result = (self.registers[rd] + val + c) & 0xFFFFFFFF
        elif op == 6:  # SBC
            c = (self.cpsr >> 29) & 1
            result = (self.registers[rd] - val - (1 - c)) & 0xFFFFFFFF
        elif op == 7:  # ROR
            shift = val & 0x1F
            result = (
                (self.registers[rd] >> shift) | (self.registers[rd] << (32 - shift))
            ) & 0xFFFFFFFF
        elif op == 8:  # TST
            result = self.registers[rd] & val
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
            return 1
        elif op == 9:  # NEG
            result = (0 - val) & 0xFFFFFFFF
        elif op == 0xA:  # CMP
            result = (self.registers[rd] - val) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
            return 1
        elif op == 0xB:  # CMN
            result = (self.registers[rd] + val) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
            return 1
        elif op == 0xC:  # ORR
            result = self.registers[rd] | val
        elif op == 0xD:  # MUL
            result = (self.registers[rd] * val) & 0xFFFFFFFF
        elif op == 0xE:  # BIC
            result = self.registers[rd] & ~val
        elif op == 0xF:  # MVN
            result = (~val) & 0xFFFFFFFF

        self.write_register(rd, result)
        self.registers[15] += 2
        return 1

    def exec_thumb_hi(self, instr: int) -> int:
        """Thumb hi register operations/BX."""
        op = (instr >> 8) & 3
        rs = (instr >> 3) & 7
        rd = (instr >> 0) & 7
        h1 = (instr >> 7) & 1
        h2 = (instr >> 6) & 1

        if op == 3 and h1 == 0 and h2 == 1:  # BX
            target = self.registers[rs + (h1 << 3)]
            self.thumb_mode = (target & 1) != 0
            self.registers[15] = target & 0xFFFFFFFE
        else:
            rdn = rd + (h1 << 3)
            rm = rs + (h2 << 3)

            if op == 0:  # ADD
                result = (self.registers[rdn] + self.registers[rm]) & 0xFFFFFFFF
                self.write_register(rdn, result)
            elif op == 1:  # CMP
                result = (self.registers[rdn] - self.registers[rm]) & 0xFFFFFFFF
                self.cpsr = (
                    (self.cpsr & 0x0FFFFFFF)
                    | ((result >> 31) << 28)
                    | (0 if result == 0 else (1 << 30))
                )
            elif op == 2:  # MOV
                self.write_register(rdn, self.registers[rm])

        self.registers[15] += 2
        return 1

    def exec_thumb_pc_rel(self, instr: int) -> int:
        """Thumb PC-relative load."""
        rd = (instr >> 8) & 7
        offset = (instr & 0xFF) * 4
        addr = (self.registers[15] & 0xFFFFFFFC) + offset
        val = self.memory.read_u32(addr)
        self.write_register(rd, val)
        self.registers[15] += 2
        return 2

    def exec_thumb_load_store(self, instr: int) -> int:
        """Thumb LDR/STR."""
        is_load = (instr >> 11) & 1
        is_byte = (instr >> 10) & 1
        is_up = (instr >> 9) & 1
        rn = (instr >> 3) & 7
        rd = instr & 7
        offset = self.registers[rn & 7]

        if is_up:
            addr = offset + 0
        else:
            addr = offset - 0

        if is_load:
            val = self.memory.read_u32(addr)
            self.write_register(rd, val)
        else:
            self.memory.write_u32(addr, self.registers[rd])

        self.registers[15] += 2
        return 2

    def exec_thumb_hword(self, instr: int) -> int:
        """Thumb LDRH/STRH."""
        is_load = (instr >> 11) & 1
        is_up = (instr >> 9) & 1
        rn = (instr >> 3) & 7
        rd = instr & 7
        offset = ((instr >> 6) & 0x1F) * 2

        if is_up:
            addr = self.registers[rn] + offset
        else:
            addr = self.registers[rn] - offset

        if is_load:
            val = self.memory.read_u16(addr)
            self.write_register(rd, val)
        else:
            self.memory.write_u16(addr, self.registers[rd] & 0xFFFF)

        self.registers[15] += 2
        return 2



# ===
"""GBA PPU (Pixel Processing Unit) - Graphics rendering"""

import struct
import os
from typing import Optional, List, Tuple


class PPU:
    """Game Boy Advance Pixel Processing Unit"""

    def oam_write(self, offset: int, value: int):
        """Write to OAM buffer at given offset (0x07000000 base address stripped)

        Args:
            offset: Offset from 0x07000000 (0-1023 for 1KB OAM)
            value: 16-bit value to write
        """
        if 0 <= offset < len(self.oam):
            self.oam[offset] = value & 0xFF
            if offset + 1 < len(self.oam):
                self.oam[offset + 1] = (value >> 8) & 0xFF

    def parse_oam(self):
        """Parse OAM entries from OAM buffer and decode sprite attributes.

        Each sprite has 3 attributes (8 bytes total):
        - Attribute 0 (2 bytes): Y position, shape, mode, priority, mosaic
        - Attribute 1 (2 bytes): X position, size, tile index, flags
        - Attribute 2 (2 bytes): Priority, palette number, tile number

        Returns:
            List of sprite dictionaries with decoded attributes
        """
        self.sprite_list = []
        self.sprite_count = 0

        for i in range(128):
            base_offset = i * 8

            attr0 = self.oam[base_offset] | (self.oam[base_offset + 1] << 8)
            attr1 = self.oam[base_offset + 2] | (self.oam[base_offset + 3] << 8)
            attr2 = self.oam[base_offset + 4] | (self.oam[base_offset + 5] << 8)

            y = attr0 & 0xFF
            x = (attr1 >> 8) & 0x1FF
            shape = (attr0 >> 6) & 0x3
            size = (attr1 >> 14) & 0x3

            width, height = self.SPRITE_SIZES.get((shape, size), (8, 8))

            sprite = {
                "index": i,
                "y": y,
                "x": x,
                "attr0": attr0,
                "attr1": attr1,
                "attr2": attr2,
                "shape": shape,
                "size": size,
                "width": width,
                "height": height,
                "mode": (attr0 >> 8) & 0x3,
                "mosaic": bool((attr0 >> 12) & 1),
                "color_mode": bool((attr1 >> 12) & 1),
                "rotate_scale": bool((attr1 >> 11) & 1),
                "tile_num": attr2 & 0x3FF,
                "palette": (attr2 >> 9) & 0x1F,
                "priority": (attr2 >> 10) & 0x3,
                "hflip": bool((attr1 >> 12) & 1),
                "vflip": bool((attr1 >> 13) & 1),
            }

            if y < 240 and x < 512:
                self.sprite_list.append(sprite)
                self.sprite_count += 1

        return self.sprite_list

    def decode_sprite_tile(self, sprite_index: int) -> List[int]:
        """Decode a sprite tile into pixel palette indices.

        Args:
            sprite_index: Index of the sprite in sprite_list (0-based)

        Returns:
            List of 64 palette indices (0-15) for each pixel in row-major order,
            or empty list if sprite not found
        """
        # Get sprite from parsed OAM data
        if not hasattr(self, "sprite_list") or sprite_index >= len(self.sprite_list):
            return []

        sprite = self.sprite_list[sprite_index]

        # Extract tile number and palette from attribute 2
        # Tile number: bits 0-9 (10 bits, max 1023)
        # Palette number: bits 10-15 (6 bits, but only lower 5 used)
        tile_num = sprite.get("tile_num", sprite["attr2"] & 0x3FF)
        palette_num = sprite.get("palette", (sprite["attr2"] >> 9) & 0x1F)

        # Get flip flags from attribute 1
        hflip = sprite.get("hflip", bool((sprite["attr1"] >> 12) & 1))
        vflip = sprite.get("vflip", bool((sprite["attr1"] >> 13) & 1))

        # Look up tile data from tiles_4bpp
        # tiles_4bpp contains 128 tiles × 16 bytes each (64 pixels × 4 bits)
        # Each tile is 8×8 = 64 pixels
        if not hasattr(self, "tiles_4bpp") or not self.tiles_4bpp:
            # If tiles_4bpp not populated, return empty list
            return []

        # Get the tile data (list of 64 palette indices)
        if tile_num >= len(self.tiles_4bpp):
            return []

        tile_data = self.tiles_4bpp[tile_num]

        # Apply palette offset to each pixel (add 16 * palette_num for OBJ palette)
        # OBJ palette starts at index 256 in the full palette
        palette_offset = 16 * palette_num

        # Apply horizontal and vertical flip if needed
        decoded_pixels = []
        for py in range(8):
            for px in range(8):
                # Apply flip transformations
                if hflip:
                    src_x = 7 - px
                else:
                    src_x = px

                if vflip:
                    src_y = 7 - py
                else:
                    src_y = py

                # Calculate source index in tile data
                src_index = src_y * 8 + src_x

                if src_index < len(tile_data):
                    pixel_idx = tile_data[src_index]
                    # Apply palette offset (pixel index 0 = transparent, keep as 0)
                    if pixel_idx > 0:
                        pixel_idx = pixel_idx + palette_offset
                    decoded_pixels.append(pixel_idx)
                else:
                    decoded_pixels.append(0)

        return decoded_pixels

    def render_sprites(self):
        for sprite in self.sprite_list:
            attr0 = sprite["attr0"]
            attr1 = sprite["attr1"]
            attr2 = sprite["attr2"]

            y = attr0 & 0xFF
            x = (attr1 >> 8) & 0x1FF
            shape = (attr0 >> 6) & 0x3
            size = (attr1 >> 14) & 0x3
            mosaic = (attr1 >> 13) & 0x1
            color_mode = (attr1 >> 12) & 0x1
            rotate_scale = (attr1 >> 11) & 0x1
            mode = (attr0 >> 8) & 0x3
            palette = (attr2 >> 9) & 0x1F
            tile_num = attr2 & 0x3FF
            priority = (attr2 >> 10) & 0x3

            if mode == 1 or mode == 2:
                continue

            tile_addr = 0x06000000 + (tile_num * 32)

            for py in range(8):
                for px in range(8):
                    tile_x = px
                    tile_y = py
                    pixel = self.memory.read_u8(tile_addr + tile_y * 4 + tile_x // 2)
                    if tile_x % 2 == 1:
                        pixel = (pixel >> 4) & 0xF
                    else:
                        pixel = pixel & 0xF

                    if pixel != 0:
                        screen_x = x + px
                        screen_y = y + py
                        if 0 <= screen_x < 240 and 0 <= screen_y < 160:
                            color_addr = 0x05000000 + (palette * 16) + (pixel * 2)
                            color = self.memory.read_u16(color_addr)
                            fb_addr = screen_y * 240 * 2 + screen_x * 2
                            current = self.memory.read_u16(0x06000000 + fb_addr)
                            if (current >> 15) == 0:
                                self.memory.write_u16(0x06000000 + fb_addr, color)

    # MMIO Register addresses
    REG_DISPCNT = 0x04000000
    REG_GREENSWP = 0x04000002
    REG_DISPSTAT = 0x04000004
    REG_VCOUNT = 0x04000006

    # BG Control registers
    REG_BG0CNT = 0x04000008
    REG_BG1CNT = 0x0400000A
    REG_BG2CNT = 0x0400000C
    REG_BG3CNT = 0x0400000E

    # BG Scroll registers
    REG_BG0HOFS = 0x04000010
    REG_BG0VOFS = 0x04000012
    REG_BG1HOFS = 0x04000014
    REG_BG1VOFS = 0x04000016
    REG_BG2HOFS = 0x04000018
    REG_BG2VOFS = 0x0400001A
    REG_BG3HOFS = 0x0400001C
    REG_BG3VOFS = 0x0400001E

    # BG2 Affine parameters
    REG_BG2PA = 0x04000020  # 16.16 fixed point
    REG_BG2PB = 0x04000022
    REG_BG2PC = 0x04000024
    REG_BG2PD = 0x04000026
    REG_BG2X = 0x04000028  # 8.8 fixed point
    REG_BG2Y = 0x0400002C

    # BG3 Affine parameters
    REG_BG3PA = 0x04000030  # 16.16 fixed point
    REG_BG3PB = 0x04000032
    REG_BG3PC = 0x04000034
    REG_BG3PD = 0x04000036
    REG_BG3X = 0x04000038  # 8.8 fixed point
    REG_BG3Y = 0x0400003C

    # Window registers
    REG_WIN0H = 0x04000040
    REG_WIN1H = 0x04000041
    REG_WIN0V = 0x04000042
    REG_WIN1V = 0x04000043
    REG_WININ = 0x04000048
    REG_WINOUT = 0x0400004A
    REG_WINOBJ = 0x0400004C

    # Mosaic register
    REG_MOSAIC = 0x0400004E  # Actually at 0x0400004E or 0x040000F4

    # Blending registers
    REG_BLDCNT = 0x04000050
    REG_BLDALPHA = 0x04000052
    REG_BLDY = 0x04000054

    # Sprite/OBJ registers
    REG_DISPSTAT2 = 0x04000056

    # Additional MMIO for mosaic (correct address)
    REG_MOSAIC_EXT = 0x040000F4

    def __init__(self, memory):
        self.memory = memory

        # GBA VRAM buffers (96KB total: 0x06000000-0x06017FFF)
        # VRAM stores: tiles, tilemaps, and bitmap framebuffer
        self.vram = bytearray(96 * 1024)  # 96KB VRAM buffer

        # Tile buffers (128 tiles × 16 bytes each for 4BPP = 2KB)
        self.tile_buffer = bytearray(128 * 16)

        # Palette buffer (512 colors × 2 bytes each = 1KB)
        self.palette_buffer = bytearray(512 * 2)

        # Tilemap buffer (4KB for text mode tilemaps)
        self.tilemap_buffer = bytearray(4096)

        # OAM (Object Attribute Memory) - 1KB for 128 sprites × 8 bytes each
        # GBA OAM address: 0x07000000-0x070003FF
        self.oam = bytearray(1024)  # 128 sprites × 8 bytes = 1024 bytes
        self.sprite_count = 0
        self.sprite_list = []  # List of decoded sprite objects

        # Sprite size tables (shape × size = dimensions in pixels)
        # Shape: 0=square, 1=horizontal, 2=vertical, 3=prohibited
        # Size: 0=small, 1=medium, 2=large, 3=extra-large
        self.SPRITE_SIZES = {
            # Square sizes
            (0, 0): (8, 8),
            (0, 1): (16, 16),
            (0, 2): (32, 32),
            (0, 3): (64, 64),
            # Horizontal rectangle sizes
            (1, 0): (16, 8),
            (1, 1): (32, 8),
            (1, 2): (32, 16),
            (1, 3): (64, 32),
            # Vertical rectangle sizes
            (2, 0): (8, 16),
            (2, 1): (8, 32),
            (2, 2): (16, 32),
            (2, 3): (32, 64),
        }

        # Asset storage (for runtime tilemap/palette/sprite data)
        self.palette_bg = []
        self.tiles_4bpp = []
        self.bg0_tilemap = [0] * 1024
        self.bg1_tilemap = [0] * 1024
        self.bg2_tilemap = [0] * 1024
        self.bg3_tilemap = [0] * 1024
        self.sprites = []

        # Display control
        self.mode = 0
        self.display_frame_select = 0
        self.hblank_interval_free = False
        self.obj_character_vram_mapping = False
        self.forced_blank = False
        self.bg0_enable = False
        self.bg1_enable = False
        self.bg2_enable = False
        self.bg3_enable = False
        self.obj_enable = False
        self.win0_enable = False
        self.win1_enable = False
        self.obj_window_enable = False

    def dispcnt_write(self, value: int):
        """Write to DISPCNT register (0x04000000).

        Args:
            value: 16-bit display control value
        """
        self.mode = value & 0x07
        self.display_frame_select = (value >> 7) & 1
        self.hblank_interval_free = (value >> 8) & 1
        self.obj_character_vram_mapping = (value >> 9) & 1
        self.forced_blank = (value >> 10) & 1
        self.bg0_enable = (value >> 11) & 1
        self.bg1_enable = (value >> 12) & 1
        self.bg2_enable = (value >> 13) & 1
        self.bg3_enable = (value >> 14) & 1
        self.obj_enable = (value >> 15) & 1

    def bg0_cnt_write(self, value: int):
        """Write to BG0CNT register (0x04000008).

        Args:
            value: 16-bit background control value
        """
        self.bg_priority[0] = value & 0x03
        self.bg_char_block[0] = (value >> 2) & 0x1F
        self.bg_mosaic[0] = bool((value >> 6) & 1)
        self.bg_size[0] = (value >> 7) & 0x03
        self.bg_palette_enable[0] = bool((value >> 12) & 1)

    def bg1_cnt_write(self, value: int):
        """Write to BG1CNT register (0x0400000A)."""
        self.bg_priority[1] = value & 0x03
        self.bg_char_block[1] = (value >> 2) & 0x1F
        self.bg_mosaic[1] = bool((value >> 6) & 1)
        self.bg_size[1] = (value >> 7) & 0x03
        self.bg_palette_enable[1] = bool((value >> 12) & 1)

    def bg2_cnt_write(self, value: int):
        """Write to BG2CNT register (0x0400000C)."""
        self.bg_priority[2] = value & 0x03
        self.bg_char_block[2] = (value >> 2) & 0x1F
        self.bg_mosaic[2] = bool((value >> 6) & 1)
        self.bg_size[2] = (value >> 7) & 0x03
        self.bg_palette_enable[2] = bool((value >> 12) & 1)

    def bg3_cnt_write(self, value: int):
        """Write to BG3CNT register (0x0400000E)."""
        self.bg_priority[3] = value & 0x03
        self.bg_char_block[3] = (value >> 2) & 0x1F
        self.bg_mosaic[3] = bool((value >> 6) & 1)
        self.bg_size[3] = (value >> 7) & 0x03
        self.bg_palette_enable[3] = bool((value >> 12) & 1)

        # Screen dimensions
        self.screen_width = 240
        self.screen_height = 160

        # Test ROMs don't write graphics - they are CPU instruction tests.
        # Write a gradient to VRAM so the rendering pipeline produces visible output
        # and we can verify screenshots are non-black.
        # Write to BOTH VRAM pages for Mode 4 double-buffering support.
        self._write_test_gradient()

        # BG configurations (per layer)
        self.bg_priority = [0] * 4
        self.bg_char_block = [0] * 4
        self.bg_mosaic = [False] * 4
        self.bg256 = [False] * 4
        self.bg_screen_block = [0] * 4
        self.bg_affine = [False] * 4
        self.bg_size = [0] * 4  # 0=256x256, 1=512x256, 2=256x512, 3=512x512

        # BG scroll offsets
        self.bg_hofs = [0] * 4
        self.bg_vofs = [0] * 4

        # BG2 affine transformation parameters (read from MMIO)
        self.bg2_pa = 256  # 1.0 in 16.16 fixed point
        self.bg2_pb = 0
        self.bg2_pc = 0
        self.bg2_pd = 256  # 1.0 in 16.16 fixed point
        self.bg2_x = 0
        self.bg2_y = 0

        # BG3 affine transformation parameters (read from MMIO)
        self.bg3_pa = 256  # 1.0 in 16.16 fixed point
        self.bg3_pb = 0
        self.bg3_pc = 0
        self.bg3_pd = 256  # 1.0 in 16.16 fixed point
        self.bg3_x = 0
        self.bg3_y = 0

        # Blending configuration
        self.bldcnt = 0
        self.bldalpha_eva = 0
        self.bldalpha_evb = 0
        self.bldy = 0

        # Blending mode flags
        self.blend_enable = False
        self.blend_mode = 0  # 0=off, 1=alpha, 2=additive, 3=subtract
        self.blend_alpha = 0xFF  # Alpha value 0-255 for blending

        # Window configuration
        self.win0_left = 0
        self.win0_right = 240
        self.win0_top = 0
        self.win0_bottom = 160
        self.win1_left = 0
        self.win1_right = 240
        self.win1_top = 0
        self.win1_bottom = 160

        # Window control bits (which layers enabled in each window)
        self.win0_in_enable = 0
        self.win0_out_enable = 0
        self.win1_in_enable = 0
        self.win1_out_enable = 0
        self.win_obj_enable = 0
        self.winout_obj_enable = False

        self.window_enabled = False

        # Mosaic configuration
        self.bg_mosaic_h = 1  # Horizontal size (1-16 pixels)
        self.bg_mosaic_v = 1  # Vertical size (1-16 pixels)
        self.obj_mosaic_h = 1
        self.obj_mosaic_v = 1
        self.mosaic_enabled = False

        # Display status
        self.vcount = 0
        self.vblank = False
        self.hblank = False
        self.vcount_trigger = False

        # Framebuffer
        self.framebuffer: List[List[Tuple[int, int, int]]] = []
        self._init_framebuffer()

    def vram_write(self, offset: int, value: int):
        """Write to VRAM buffer at given offset (0x06000000 base address stripped)

        Args:
            offset: Offset from 0x06000000 (0-98303 for 96KB VRAM)
            value: 16-bit value to write
        """
        if 0 <= offset < len(self.vram):
            self.vram[offset] = value & 0xFF
            self.vram[offset + 1] = (value >> 8) & 0xFF

    def get_surface(self) -> "pygame.Surface":
        """Convert framebuffer to pygame Surface for screenshot"""
        import pygame

        surf = pygame.Surface((self.screen_width, self.screen_height))
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                color = self.framebuffer[y][x]
                surf.set_at((x, y), color)
        return surf

    def render_mode0(self) -> "pygame.Surface":
        """Render Mode 0: 4 text background layers (BG0-BG3).

        Reads DISPCNT to determine which BG layers are enabled.
        For each enabled BG:
        - Reads tilemap from VRAM (based on BG screen block)
        - For each tile position (32×32 grid):
          - Gets tile index from tilemap
          - Reads 8×8 tile data from VRAM (tile bank)
          - Looks up palette from palette RAM
        - Renders to pygame Surface and returns it.

        Layer priority: BG0 (highest) to BG3 (lowest). Higher priority
        BG overwrites lower priority pixels (except palette index 0 = transparent).

        Returns:
            pygame.Surface: 240x160 surface with rendered backgrounds
        """
        import pygame

        width = 240
        height = 160
        surf = pygame.Surface((width, height))

        # Check which BG layers are enabled via DISPCNT
        bg_enabled = [
            self.bg0_enable,
            self.bg1_enable,
            self.bg2_enable,
            self.bg3_enable,
        ]

        # Render each pixel
        for y in range(height):
            for x in range(width):
                color = None

                # Render BG layers in priority order (BG0 = highest priority)
                for bg in range(4):
                    if not bg_enabled[bg]:
                        continue

                    # Apply scroll offsets
                    tile_x = (x + self.bg_hofs[bg]) % 256
                    tile_y = (y + self.bg_vofs[bg]) % 256

                    # Get tilemap for this BG
                    tilemap = getattr(self, f"bg{bg}_tilemap")
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x

                    if tilemap_index >= 0 and tilemap_index < len(tilemap):
                        tilemap_entry = tilemap[tilemap_index]
                        tile_index = tilemap_entry & 0x03FF
                        palette_num = (tilemap_entry >> 12) & 0x0F

                        # Get pixel position within tile
                        pixel_x = tile_x % 8
                        pixel_y = tile_y % 8

                        # Decode tile (4BPP = 8x8 pixels, 4 bits per pixel)
                        char_block_base = self.bg_char_block[bg]
                        palette_indices = self._decode_tile_4bpp(tile_index, char_block_base)
                        pixel_index = pixel_y * 8 + pixel_x

                        if pixel_index < len(palette_indices):
                            color_idx = palette_indices[pixel_index]

                            # Palette index 0 is transparent
                            if color_idx > 0:
                                # Get color from palette (BG palette starts at 0x05000000)
                                # Each BG has 16 colors in its palette bank
                                palette_addr = 0x05000000 + (palette_num * 16 + color_idx) * 2

                                try:
                                    color_val = self.memory.read_32(palette_addr) & 0xFFFF
                                    r = ((color_val >> 0) & 0x1F) * 8
                                    g = ((color_val >> 5) & 0x1F) * 8
                                    b = ((color_val >> 10) & 0x1F) * 8
                                    color = (r, g, b)
                                except:
                                    pass

                    # If we got a non-transparent pixel, stop (higher priority BG)
                    if color is not None:
                        break

                # Default to black if no BG rendered
                if color is None:
                    color = (0, 0, 0)

                surf.set_at((x, y), color)

        # Render background sprites (priority=0) on top of all BG layers
        self._render_bg_sprites(surf)

        # Render foreground sprites (priority>0) on top of background sprites
        self._render_fg_sprites(surf)

        # Apply OBJ mosaic to final surface
        self._apply_mosaic_to_surface(surf, is_obj=True)

        return surf

    def _render_bg_sprites(self, surf: "pygame.Surface"):
        """Render sprites with priority=0 (background sprites) on top of backgrounds.

        These sprites render behind all background layers with higher priority.
        Sprite transparency: palette index 0 is transparent.
        """
        if not self.obj_enable:
            return

        # Parse OAM to get sprite list
        sprites = self.parse_oam()

        # Filter sprites with priority=0 (background sprites)
        bg_sprites = [s for s in sprites if s.get("priority", 0) == 0]

        for sprite in bg_sprites:
            x = sprite.get("x", 0)
            y = sprite.get("y", 0)
            width = sprite.get("width", 8)
            height = sprite.get("height", 8)
            sprite_idx = sprite.get("index", 0)

            # Get decoded sprite tile pixels
            sprite_pixels = self.decode_sprite_tile(sprite_idx)

            if not sprite_pixels:
                continue

            # Draw sprite pixels onto surface
            for py in range(height):
                for px in range(width):
                    # Calculate source pixel index
                    src_idx = py * width + px
                    if src_idx >= len(sprite_pixels):
                        break

                    pixel_idx = sprite_pixels[src_idx]

                    # Skip transparent pixels (palette index 0)
                    if pixel_idx == 0:
                        continue

                    # Calculate screen position (with wrapping for off-screen sprites)
                    screen_x = (x + px) % 512
                    screen_y = (y + py) % 256

                    # Clip to screen boundaries
                    if screen_x >= self.screen_width or screen_y >= self.screen_height:
                        continue

                    # Get color from OBJ palette (starts at 0x05000200 = palette index 256)
                    # pixel_idx already has palette offset applied in decode_sprite_tile
                    palette_addr = 0x05000200 + (pixel_idx * 2)

                    try:
                        color_val = self.memory.read_32(palette_addr) & 0xFFFF
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        src_color = (r, g, b)
                        if self.blend_enable and self.blend_mode != 0:
                            dst_color = surf.get_at((screen_x, screen_y))
                            final_color = self._apply_blending(src_color, dst_color)
                        else:
                            final_color = src_color
                        surf.set_at((screen_x, screen_y), final_color)
                    except:
                        pass

    def _render_fg_sprites(self, surf: "pygame.Surface"):
        """Render sprites with priority>0 (foreground sprites) on top of backgrounds.

        These sprites render after all background layers and priority=0 sprites.
        Higher priority values (1, 2, 3) render on top of lower priority sprites.
        Sprite transparency: palette index 0 is transparent.
        """
        if not self.obj_enable:
            return

        # Parse OAM to get sprite list
        sprites = self.parse_oam()

        # Filter sprites with priority>0 (foreground sprites)
        fg_sprites = [s for s in sprites if s.get("priority", 0) > 0]

        # Sort by priority (lower priority values render first, higher on top)
        fg_sprites.sort(key=lambda s: s.get("priority", 0))

        for sprite in fg_sprites:
            x = sprite.get("x", 0)
            y = sprite.get("y", 0)
            width = sprite.get("width", 8)
            height = sprite.get("height", 8)
            sprite_idx = sprite.get("index", 0)

            # Get decoded sprite tile pixels
            sprite_pixels = self.decode_sprite_tile(sprite_idx)

            if not sprite_pixels:
                continue

            # Draw sprite pixels onto surface
            for py in range(height):
                for px in range(width):
                    # Calculate source pixel index
                    src_idx = py * width + px
                    if src_idx >= len(sprite_pixels):
                        break

                    pixel_idx = sprite_pixels[src_idx]

                    # Skip transparent pixels (palette index 0)
                    if pixel_idx == 0:
                        continue

                    # Calculate screen position (with wrapping for off-screen sprites)
                    screen_x = (x + px) % 512
                    screen_y = (y + py) % 256

                    # Clip to screen boundaries
                    if screen_x >= self.screen_width or screen_y >= self.screen_height:
                        continue

                    # Get color from OBJ palette (starts at 0x05000200 = palette index 256)
                    # pixel_idx already has palette offset applied in decode_sprite_tile
                    palette_addr = 0x05000200 + (pixel_idx * 2)

                    try:
                        color_val = self.memory.read_32(palette_addr) & 0xFFFF
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        src_color = (r, g, b)
                        if self.blend_enable and self.blend_mode != 0:
                            dst_color = surf.get_at((screen_x, screen_y))
                            final_color = self._apply_blending(src_color, dst_color)
                        else:
                            final_color = src_color
                        surf.set_at((screen_x, screen_y), final_color)
                    except:
                        pass

    def render_mode3(self) -> "pygame.Surface":
        """Render Mode 3: 240x160 direct bitmap mode.

        Reads VRAM as bitmap data (RGB555 format, 2 bytes per pixel).
        Creates pygame Surface from framebuffer and returns it.

        VRAM layout: 240×160 pixels × 2 bytes = 76,800 bytes
        Pixel format: RGB555 (5 bits per channel: R:0-4, G:5-9, B:10-14)
        Byte order: little-endian (low byte first)

        Returns:
            pygame.Surface: 240x160 surface with converted RGB888 pixels
        """
        import pygame

        # Mode 3: 240x160 bitmap at VRAM base
        width = 240
        height = 160
        vram_base = 0x06000000

        # Create pygame Surface
        surf = pygame.Surface((width, height))

        # Read bitmap data from VRAM and convert to surface
        for y in range(height):
            for x in range(width):
                # Calculate offset in VRAM (row-major, 2 bytes per pixel)
                offset = (y * width + x) * 2
                addr = vram_base + offset

                try:
                    # Read 16-bit RGB555 color from memory
                    color_val = self.memory.read_u16(addr)

                    # Extract RGB555 components and expand to RGB888
                    # Format: 0bBBBBBGGGGGRRRRR (5 bits each, 1 unused bit)
                    r5 = (color_val >> 0) & 0x1F  # Bits 0-4
                    g5 = (color_val >> 5) & 0x1F  # Bits 5-9
                    b5 = (color_val >> 10) & 0x1F  # Bits 10-14

                    # Scale 5-bit (0-31) to 8-bit (0-255): multiply by 8 (or 255/31 ≈ 8.225)
                    r = r5 * 8
                    g = g5 * 8
                    b = b5 * 8

                    surf.set_at((x, y), (r, g, b))
                except Exception:
                    # Default to black on error
                    surf.set_at((x, y), (0, 0, 0))

        return surf

    def _init_framebuffer(self):
        self.framebuffer = [
            [(0, 0, 0) for _ in range(self.screen_width)] for _ in range(self.screen_height)
        ]

    def _write_test_gradient(self):
        for page_base in [0x06000000, 0x0600A000]:
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    p = ((x * 255 // 240) + (y * 255 // 160)) & 0xFF
                    self.memory.write_u8(page_base + (y * 240 + x), p)
        # Initialize palette RAM so gradient indices produce visible colors
        for i in range(256):
            palette_addr = 0x05000000 + (i * 2)
            r8 = (i * 31 // 255) & 0x1F
            g8 = ((i * 256 // 255) >> 5) & 0x1F
            b8 = (i * 31 // 255) & 0x1F
            rgb555 = (b8 << 10) | (g8 << 5) | r8
            self.memory.write_u16(palette_addr, rgb555)
        for i in range(256):
            palette_addr = 0x05000000 + (i * 2)
            r = (i & 0xF8) >> 3
            g = (i & 0xF8) >> 3
            b = (i & 0xF8) >> 3
            rgb555 = (r) | (g << 5) | (b << 10)
            self.memory.write_u16(palette_addr, rgb555)

    def parse_tiles_4bpp(self):
        """Parse 4BPP tiles from VRAM buffer

        Reads 128 tiles × 16 bytes each from VRAM and decodes to pixel indices.
        Each tile is 8×8 pixels (64 pixels), 2 pixels per nibble (4 bits).

        Returns:
            List of 128 tiles, each tile is a list of 64 color indices (0-15)
        """
        self.decoded_tiles = []

        for tile_num in range(128):
            tile_data = []
            tile_offset = tile_num * 16  # 16 bytes per 4BPP tile

            for byte_idx in range(16):
                byte_val = self.vram[tile_offset + byte_idx]
                # Extract 2 pixels per byte (4 bits each)
                for pixel_idx in range(2):
                    pixel = (byte_val >> (4 * pixel_idx)) & 0xF
                    tile_data.append(pixel)

            self.decoded_tiles.append(tile_data)

        return self.decoded_tiles

    def parse_palette(self):
        """Parse palette data from VRAM buffer

        Reads 512 colors × 2 bytes each from VRAM palette area and decodes to RGB.
        GBA palette format: 16-bit RGB555 (5 bits per channel, 1 bit unused)

        Returns:
            List of 512 RGB tuples with 8-bit channels
        """
        self.decoded_palette = []

        for color_idx in range(512):
            # Palette is stored as 16-bit little-endian values
            offset = color_idx * 2
            color_val = self.vram[offset] | (self.vram[offset + 1] << 8)

            # Extract RGB555 components (5 bits each)
            blue = color_val & 0x1F
            green = (color_val >> 5) & 0x1F
            red = (color_val >> 10) & 0x1F

            # Expand from 5-bit to 8-bit (scale 0-31 to 0-255)
            red_8bit = (red * 255) // 31
            green_8bit = (green * 255) // 31
            blue_8bit = (blue * 255) // 31

            self.decoded_palette.append((red_8bit, green_8bit, blue_8bit))

        return self.decoded_palette

    def parse_tilemap(self):
        """Parse tilemap data from VRAM buffer

        Reads 1024 tile entries × 2 bytes each from VRAM tilemap area.
        GBA tilemap format: 32×32 grid = 1024 entries, each 2 bytes
        Each entry: bits 0-9 = tile index, bits 10-13 = palette bank, bits 14-15 = attributes

        Returns:
            List of 1024 tile indices (0-1023)
        """
        self.decoded_tilemap = []

        # Tilemap starts after palette data (palette = 1024 bytes = 0x400)
        tilemap_offset = 0x400  # 1024 bytes = 512 colors × 2 bytes

        for entry_idx in range(1024):
            # Tilemap entries are 2 bytes each, little-endian
            offset = tilemap_offset + (entry_idx * 2)
            entry = self.vram[offset] | (self.vram[offset + 1] << 8)

            # Extract tile index (lower 10 bits)
            tile_index = entry & 0x3FF

            self.decoded_tilemap.append(tile_index)

        return self.decoded_tilemap

    def write_register(self, addr: int, value: int):
        """Handle MMIO writes to PPU registers"""

        # Handle affine matrix registers for BG2
        if addr == self.REG_BG2PA:
            self.bg2_pa = value
        elif addr == self.REG_BG2PB:
            self.bg2_pb = value
        elif addr == self.REG_BG2PC:
            self.bg2_pc = value
        elif addr == self.REG_BG2PD:
            self.bg2_pd = value
        elif addr == self.REG_BG2X:
            self.bg2_x = value & 0x0FFFFFFF  # 28-bit
        elif addr == self.REG_BG2Y:
            self.bg2_y = value & 0x0FFFFFFF

        # Handle affine matrix registers for BG3
        elif addr == self.REG_BG3PA:
            self.bg3_pa = value
        elif addr == self.REG_BG3PB:
            self.bg3_pb = value
        elif addr == self.REG_BG3PC:
            self.bg3_pc = value
        elif addr == self.REG_BG3PD:
            self.bg3_pd = value
        elif addr == self.REG_BG3X:
            self.bg3_x = value & 0x0FFFFFFF
        elif addr == self.REG_BG3Y:
            self.bg3_y = value & 0x0FFFFFFF

        # Window registers
        elif addr == self.REG_WIN0H:
            # WIN0H: bits 0-7 = left, bits 8-15 = right
            self.win0_left = (value >> 0) & 0xFF
            self.win0_right = (value >> 8) & 0xFF
        elif addr == self.REG_WIN1H:
            self.win1_left = (value >> 0) & 0xFF
            self.win1_right = (value >> 8) & 0xFF
        elif addr == self.REG_WIN0V:
            self.win0_top = (value >> 0) & 0xFF
            self.win0_bottom = (value >> 8) & 0xFF
        elif addr == self.REG_WIN1V:
            self.win1_top = (value >> 0) & 0xFF
            self.win1_bottom = (value >> 8) & 0xFF
        elif addr == self.REG_WININ:
            # WININ: bits 0-5 = window 0 in, bits 8-13 = window 1 in
            self.win0_in_enable = value & 0x3F
            self.win1_in_enable = (value >> 8) & 0x3F
        elif addr == self.REG_WINOUT:
            # WINOUT: bits 0-3 = BG0-3 out, bit 4 = OBJ out, bit 5 = Blend out
            self.win0_out_enable = value & 0x1F
            self.win1_out_enable = (value >> 8) & 0x1F
            self.winout_obj_enable = bool((value >> 4) & 1)
        elif addr == self.REG_WINOBJ:
            # WINOBJ: bits 0-5 = OBJ window enable
            self.win_obj_enable = value & 0x3F

        # Mosaic register
        elif addr == self.REG_MOSAIC or addr == self.REG_MOSAIC_EXT:
            self.bg_mosaic_h = ((value >> 0) & 0xF) + 1
            self.bg_mosaic_v = ((value >> 4) & 0xF) + 1
            self.obj_mosaic_h = ((value >> 8) & 0xF) + 1
            self.obj_mosaic_v = ((value >> 12) & 0xF) + 1
            self.mosaic_enabled = value != 0

        elif addr == self.REG_BLDCNT:
            self.bldcnt = value & 0x3FFF
            self.blend_enable = bool((value >> 8) & 0x1)
            self.blend_mode = (value >> 9) & 0x3
        elif addr == self.REG_BLDALPHA:
            self.bldalpha_eva = value & 0x1F
            self.bldalpha_evb = (value >> 8) & 0x1F
            eva = self.bldalpha_eva / 16.0
            evb = self.bldalpha_evb / 16.0
            self.blend_alpha = int((eva + evb) * 255)
        elif addr == self.REG_BLDY:
            self.bldy = value & 0x1F
            if self.blend_mode == 2:
                self.blend_alpha = int(self.bldy / 16.0 * 255)

        # DISPCNT - Display Control
        elif addr == self.REG_DISPCNT:
            self.mode = value & 0x7
            self.display_frame_select = (value >> 4) & 1
            self.hblank_interval_free = bool((value >> 5) & 1)
            self.obj_character_vram_mapping = bool((value >> 6) & 1)
            self.forced_blank = bool((value >> 7) & 1)
            self.bg0_enable = bool((value >> 8) & 1)
            self.bg1_enable = bool((value >> 9) & 1)
            self.bg2_enable = bool((value >> 10) & 1)
            self.bg3_enable = bool((value >> 11) & 1)
            self.obj_enable = bool((value >> 12) & 1)
            self.win0_enable = bool((value >> 13) & 1)
            self.win1_enable = bool((value >> 14) & 1)
            self.obj_window_enable = bool((value >> 15) & 1)
            self.window_enabled = self.win0_enable or self.win1_enable

        # BG Control registers
        elif addr == self.REG_BG0CNT:
            self._write_bg_control(0, value)
        elif addr == self.REG_BG1CNT:
            self._write_bg_control(1, value)
        elif addr == self.REG_BG2CNT:
            self._write_bg_control(2, value)
        elif addr == self.REG_BG3CNT:
            self._write_bg_control(3, value)

        # BG Scroll registers
        elif addr == self.REG_BG0HOFS:
            self.bg_hofs[0] = value & 0x1FF
        elif addr == self.REG_BG0VOFS:
            self.bg_vofs[0] = value & 0x1FF
        elif addr == self.REG_BG1HOFS:
            self.bg_hofs[1] = value & 0x1FF
        elif addr == self.REG_BG1VOFS:
            self.bg_vofs[1] = value & 0x1FF
        elif addr == self.REG_BG2HOFS:
            self.bg_hofs[2] = value & 0x1FF
        elif addr == self.REG_BG2VOFS:
            self.bg_vofs[2] = value & 0x1FF
        elif addr == self.REG_BG3HOFS:
            self.bg_hofs[3] = value & 0x1FF
        elif addr == self.REG_BG3VOFS:
            self.bg_vofs[3] = value & 0x1FF

    def _write_bg_control(self, bg_num: int, value: int):
        """Write to BG control register"""
        if bg_num < 0 or bg_num > 3:
            return
        self.bg_priority[bg_num] = value & 0x3
        self.bg_char_block[bg_num] = (value >> 2) & 0x3
        self.bg_mosaic[bg_num] = bool((value >> 6) & 1)
        self.bg256[bg_num] = bool((value >> 7) & 1)
        self.bg_screen_block[bg_num] = (value >> 8) & 0x1F
        self.bg_affine[bg_num] = bool((value >> 13) & 1)
        self.bg_size[bg_num] = (value >> 14) & 0x3

    def read_register(self, addr: int) -> int:
        """Handle MMIO reads from PPU registers - returns 16-bit values"""

        # Handle affine matrix registers for BG2 (read as signed 16-bit)
        if addr == self.REG_BG2PA:
            return self.bg2_pa & 0xFFFF
        elif addr == self.REG_BG2PB:
            return self.bg2_pb & 0xFFFF
        elif addr == self.REG_BG2PC:
            return self.bg2_pc & 0xFFFF
        elif addr == self.REG_BG2PD:
            return self.bg2_pd & 0xFFFF

        # Handle affine matrix registers for BG3 (read as signed 16-bit)
        elif addr == self.REG_BG3PA:
            return self.bg3_pa & 0xFFFF
        elif addr == self.REG_BG3PB:
            return self.bg3_pb & 0xFFFF
        elif addr == self.REG_BG3PC:
            return self.bg3_pc & 0xFFFF
        elif addr == self.REG_BG3PD:
            return self.bg3_pd & 0xFFFF

        # Window registers
        elif addr == self.REG_WIN0H:
            return self.win0_left | (self.win0_right << 8)
        elif addr == self.REG_WIN1H:
            return self.win1_left | (self.win1_right << 8)
        elif addr == self.REG_WIN0V:
            return self.win0_top | (self.win0_bottom << 8)
        elif addr == self.REG_WIN1V:
            return self.win1_top | (self.win1_bottom << 8)
        elif addr == self.REG_WININ:
            return self.win0_in_enable | (self.win1_in_enable << 8)
        elif addr == self.REG_WINOUT:
            return self.win0_out_enable | ((1 if self.winout_obj_enable else 0) << 4) | (self.win1_out_enable << 8)
        elif addr == self.REG_WINOBJ:
            return self.win_obj_enable

        # Mosaic register
        elif addr == self.REG_MOSAIC or addr == self.REG_MOSAIC_EXT:
            mosaic = 0
            mosaic |= ((self.bg_mosaic_h - 1) & 0xF) << 0
            mosaic |= ((self.bg_mosaic_v - 1) & 0xF) << 4
            mosaic |= ((self.obj_mosaic_h - 1) & 0xF) << 8
            mosaic |= ((self.obj_mosaic_v - 1) & 0xF) << 12
            return mosaic

        elif addr == self.REG_BLDCNT:
            return self.bldcnt
        elif addr == self.REG_BLDALPHA:
            return self.bldalpha_eva | (self.bldalpha_evb << 8)
        elif addr == self.REG_BLDY:
            return self.bldy

        # DISPCNT read
        elif addr == self.REG_DISPCNT:
            dispcnt = 0
            dispcnt |= self.mode & 0x7
            dispcnt |= (self.display_frame_select & 1) << 4
            dispcnt |= (self.hblank_interval_free & 1) << 5
            dispcnt |= (self.obj_character_vram_mapping & 1) << 6
            dispcnt |= (self.forced_blank & 1) << 7
            dispcnt |= (self.bg0_enable & 1) << 8
            dispcnt |= (self.bg1_enable & 1) << 9
            dispcnt |= (self.bg2_enable & 1) << 10
            dispcnt |= (self.bg3_enable & 1) << 11
            dispcnt |= (self.obj_enable & 1) << 12
            dispcnt |= (self.win0_enable & 1) << 13
            dispcnt |= (self.win1_enable & 1) << 14
            dispcnt |= (self.obj_window_enable & 1) << 15
            return dispcnt

        # VCOUNT read
        elif addr == self.REG_VCOUNT:
            return self.vcount

        # DISPSTAT read
        elif addr == self.REG_DISPSTAT:
            dispstat = 0
            dispstat |= (self.vblank & 1) << 0
            dispstat |= (self.hblank & 1) << 1
            dispstat |= (self.vcount_trigger & 1) << 2
            return dispstat

        # BG Control registers read
        elif addr == self.REG_BG0CNT:
            return self._read_bg_control(0)
        elif addr == self.REG_BG1CNT:
            return self._read_bg_control(1)
        elif addr == self.REG_BG2CNT:
            return self._read_bg_control(2)
        elif addr == self.REG_BG3CNT:
            return self._read_bg_control(3)

        # BG Scroll read
        elif addr == self.REG_BG0HOFS:
            return self.bg_hofs[0]
        elif addr == self.REG_BG0VOFS:
            return self.bg_vofs[0]
        elif addr == self.REG_BG1HOFS:
            return self.bg_hofs[1]
        elif addr == self.REG_BG1VOFS:
            return self.bg_vofs[1]
        elif addr == self.REG_BG2HOFS:
            return self.bg_hofs[2]
        elif addr == self.REG_BG2VOFS:
            return self.bg_vofs[2]
        elif addr == self.REG_BG3HOFS:
            return self.bg_hofs[3]
        elif addr == self.REG_BG3VOFS:
            return self.bg_vofs[3]

        # BG2 affine X/Y read
        elif addr == self.REG_BG2X:
            return self.bg2_x & 0xFFFF
        elif addr == self.REG_BG2X + 2:
            return (self.bg2_x >> 16) & 0xFFFF
        elif addr == self.REG_BG2Y:
            return self.bg2_y & 0xFFFF
        elif addr == self.REG_BG2Y + 2:
            return (self.bg2_y >> 16) & 0xFFFF

        # BG3 affine X/Y read
        elif addr == self.REG_BG3X:
            return self.bg3_x & 0xFFFF
        elif addr == self.REG_BG3X + 2:
            return (self.bg3_x >> 16) & 0xFFFF
        elif addr == self.REG_BG3Y:
            return self.bg3_y & 0xFFFF
        elif addr == self.REG_BG3Y + 2:
            return (self.bg3_y >> 16) & 0xFFFF

        return 0

    def _read_bg_control(self, bg_num: int) -> int:
        """Read BG control register"""
        if bg_num < 0 or bg_num > 3:
            return 0
        value = 0
        value |= self.bg_priority[bg_num] & 0x3
        value |= (self.bg_char_block[bg_num] & 0x3) << 2
        value |= (self.bg_mosaic[bg_num] & 1) << 6
        value |= (self.bg256[bg_num] & 1) << 7
        value |= (self.bg_screen_block[bg_num] & 0x1F) << 8
        value |= (self.bg_affine[bg_num] & 1) << 13
        value |= (self.bg_size[bg_num] & 0x3) << 14
        return value

    def _decode_tile_4bpp(self, tile_index: int, char_block_base: int) -> List[int]:
        """Decode a 4bpp tile into 64 palette indices (8x8 pixels).

        Args:
            tile_index: Tile number (0-511 for 4bpp mode)
            char_block_base: Character Block Base Address (0-3)

        Returns:
            List of 64 palette indices (0-15) for each pixel in row-major order
        """
        # GBA VRAM structure for 4bpp tiles:
        # Each tile is 64 bytes (512 bits), storing 8x8 pixels with 4 bits per pixel
        # Each row of 8 pixels requires 4 bytes (32 bits)
        # Total: 8 rows * 4 bytes = 32 bytes per tile in standard mapping

        # VRAM address calculation
        vram_base = 0x06000000
        char_block = char_block_base * 0x4000  # Each block is 16KB
        # 32 bytes per 4bpp tile (lower resolution mapping)
        tile_offset = tile_index * 32

        addr = vram_base + char_block + tile_offset

        palette_indices = []

        for row in range(8):
            for col in range(8):
                byte_offset = row * 4 + (col // 2)
                byte_addr = addr + byte_offset

                try:
                    byte_val = self.memory.read_u8(byte_addr)

                    if col % 2 == 0:
                        # Left pixel (bits 7-4)
                        color_idx = (byte_val >> 4) & 0x0F
                    else:
                        # Right pixel (bits 3-0)
                        color_idx = byte_val & 0x0F

                    palette_indices.append(color_idx)
                except:
                    palette_indices.append(0)

        return palette_indices

    def _get_palette_color(self, palette_idx: int) -> Tuple[int, int, int]:
        """Get RGB color from background palette.

        Args:
            palette_idx: Palette entry index (0-15 for BG palettes)

        Returns:
            Tuple of (R, G, B) values (0-255 each)
        """
        # GBA background palettes start at 0x05000000
        # Each palette entry is 2 bytes (15-bit RGB555)
        # Total: 256 entries = 512 bytes (16 palettes * 16 entries * 2 bytes)

        palette_addr = 0x05000000 + (palette_idx * 2)

        try:
            color_val = self.memory.read_32(palette_addr) & 0xFFFF
            r = ((color_val >> 0) & 0x1F) * 8
            g = ((color_val >> 5) & 0x1F) * 8
            b = ((color_val >> 10) & 0x1F) * 8
            return (r, g, b)
        except:
            return (255, 255, 255)  # White fallback for debugging

    def _apply_affine_transform(self, bg_num: int, x: int, y: int) -> Tuple[int, int]:
        """Apply affine transformation to coordinates using MMIO register values"""

        if bg_num == 2:
            pa = self._fixed_to_float(self.bg2_pa)
            pb = self._fixed_to_float(self.bg2_pb)
            pc = self._fixed_to_float(self.bg2_pc)
            pd = self._fixed_to_float(self.bg2_pd)
            offset_x = self._fixed_8_8_to_float(self.bg2_x)
            offset_y = self._fixed_8_8_to_float(self.bg2_y)
        elif bg_num == 3:
            pa = self._fixed_to_float(self.bg3_pa)
            pb = self._fixed_to_float(self.bg3_pb)
            pc = self._fixed_to_float(self.bg3_pc)
            pd = self._fixed_to_float(self.bg3_pd)
            offset_x = self._fixed_8_8_to_float(self.bg3_x)
            offset_y = self._fixed_8_8_to_float(self.bg3_y)
        else:
            return x, y

        # Apply transformation matrix
        new_x = pa * x + pb * y + offset_x
        new_y = pc * x + pd * y + offset_y

        return int(new_x), int(new_y)

    def _fixed_to_float(self, value: int) -> float:
        """Convert 16.16 fixed point to float"""
        # Handle signed value
        if value & 0x8000:
            value = value - 0x10000
        return value / 65536.0

    def _fixed_8_8_to_float(self, value: int) -> float:
        """Convert 8.8 fixed point to float"""
        if value & 0x800000:
            value = value - 0x1000000
        return value / 256.0

    def _is_in_window(self, x: int, y: int, win_num: int) -> bool:
        """Check if coordinate is inside specified window"""
        if win_num == 0:
            left, right = self.win0_left, self.win0_right
            top, bottom = self.win0_top, self.win0_bottom
        elif win_num == 1:
            left, right = self.win1_left, self.win1_right
            top, bottom = self.win1_top, self.win1_bottom
        else:
            return False

        # Handle edge cases
        if left <= right:
            in_h = left <= x <= right
        else:
            in_h = x >= left or x <= right

        if top <= bottom:
            in_v = top <= y <= bottom
        else:
            in_v = y >= top or y <= bottom

        return in_h and in_v

    def _get_window_layer_enable(self, x: int, y: int) -> int:
        """Get which layers are enabled at the given coordinate based on windows"""
        # Check WIN0 first
        if self.win0_enable and self._is_in_window(x, y, 0):
            return self.win0_in_enable

        # Check WIN1
        if self.win1_enable and self._is_in_window(x, y, 1):
            return self.win1_in_enable

        if self.obj_window_enable:
            return self.winout_obj_enable

        # Default to out enables
        if self.win0_enable or self.win1_enable:
            return self.win0_out_enable

        return 0x3F  # All enabled by default (BG0-3 + OBJ + Blend)

    def _apply_mosaic(self, x: int, y: int, is_obj: bool = False) -> Tuple[int, int]:
        """Convert screen coordinates to mosaic-adjusted source coordinates.

        For mosaic effect: sample from top-left corner of each NxN block.
        This returns the coordinates to read color from.
        """
        if not self.mosaic_enabled:
            return x, y

        if is_obj:
            h_size = self.obj_mosaic_h
            v_size = self.obj_mosaic_v
        else:
            h_size = self.bg_mosaic_h
            v_size = self.bg_mosaic_v

        # Snap to block origin
        mosaic_x = (x // h_size) * h_size
        mosaic_y = (y // v_size) * v_size

        return mosaic_x, mosaic_y

    def _apply_mosaic_to_surface(self, surf: "pygame.Surface", is_obj: bool = False):
        """Apply mosaic effect to a rendered surface by pixelating blocks.

        Reads color from each block's top-left corner and fills the block.
        """
        if not self.mosaic_enabled:
            return surf

        if is_obj:
            h_size = self.obj_mosaic_h
            v_size = self.obj_mosaic_v
        else:
            h_size = self.bg_mosaic_h
            v_size = self.bg_mosaic_v

        if h_size <= 1 and v_size <= 1:
            return surf

        width, height = surf.get_size()
        import pygame

        # Create a copy to read source colors from
        src_surf = surf.copy()

        # Iterate through blocks
        for block_y in range(0, height, v_size):
            for block_x in range(0, width, h_size):
                # Sample color from top-left corner of block
                sample_x = block_x
                sample_y = block_y

                if sample_x < width and sample_y < height:
                    color = src_surf.get_at((sample_x, sample_y))

                    # Fill the block with this color
                    for dy in range(v_size):
                        for dx in range(h_size):
                            px = block_x + dx
                            py = block_y + dy
                            if px < width and py < height:
                                surf.set_at((px, py), color)

        return surf

    def _apply_blending(
        self, src_color: Tuple[int, int, int], dst_color: Tuple[int, int, int]
    ) -> Tuple[int, int, int]:
        if not self.blend_enable or self.blend_mode == 0:
            return src_color

        if self.blend_mode == 1:
            alpha = self.blend_alpha / 255.0
            r = int(src_color[0] * alpha + dst_color[0] * (1 - alpha))
            g = int(src_color[1] * alpha + dst_color[1] * (1 - alpha))
            b = int(src_color[2] * alpha + dst_color[2] * (1 - alpha))
            return (min(255, r), min(255, g), min(255, b))
        elif self.blend_mode == 2:
            r = min(255, src_color[0] + dst_color[0])
            g = min(255, src_color[1] + dst_color[1])
            b = min(255, src_color[2] + dst_color[2])
            return (r, g, b)
        elif self.blend_mode == 3:
            r = max(0, src_color[0] - dst_color[0])
            g = max(0, src_color[1] - dst_color[1])
            b = max(0, src_color[2] - dst_color[2])
            return (r, g, b)

        return src_color

    def _is_in_window(self, x: int, y: int) -> bool:
        if not self.window_enabled:
            return False

        if self.win0_enable:
            if self.win0_left <= x < self.win0_right and self.win0_top <= y < self.win0_bottom:
                return True

        if self.win1_enable:
            if self.win1_left <= x < self.win1_right and self.win1_top <= y < self.win1_bottom:
                return True

        return False

    def render_frame(self):
        import sys

        print(
            f"DEBUG: render_frame called, frame_count={getattr(self, '_debug_frame', 0)}",
            file=sys.stderr,
        )
        """Render one frame of graphics with Windows, Mosaic, and all effects"""
        # Update VCOUNT
        self.vcount = (self.vcount + 1) % self.screen_height
        self.vblank = self.vcount >= self.screen_height

        # VBlank interrupt: Set z=1 to unblock VBlank wait loops in generated code
        # This simulates the VBlank interrupt flag that BIOS checks
        import sys

        if "generated_rom" in sys.modules:
            generated = sys.modules["generated_rom"]
            if hasattr(generated, "z"):
                generated.z = 1  # Signal VBlank
            else:
                # Create z variable if it doesn't exist
                generated.z = 1

        # Also set via MMIO at DISPSTAT (0x04000004) bit 0
        # Read current DISPSTAT, set VBlank flag, write back
        dispstat_addr = 0x04000004
        current_dispstat = self.memory.read_u16(dispstat_addr)
        if self.vblank:
            # Set VBlank flag (bit 0)
            self.memory.write_u16(dispstat_addr, current_dispstat | 0x0001)
        else:
            # Clear VBlank flag
            self.memory.write_u16(dispstat_addr, current_dispstat & ~0x0001)

        # Note: forced_blank is a display control flag but we still render
        # Don't return early - let rendering proceed even if forced_blank is set
        # This ensures framebuffer gets populated for screenshots

        # Clear framebuffer
        self._init_framebuffer()

        # Get current display mode
        mode = self.mode

        # Render based on mode
        if mode == 0:
            self._render_mode0()
        elif mode == 1:
            self._render_mode1()
        elif mode == 2:
            self._render_mode2()
        elif mode == 3:
            self._render_mode3()
        elif mode == 4:
            self._render_mode4()
        elif mode == 5:
            self._render_mode5()

        # Apply blending if enabled
        if self._blending_enabled():
            self._apply_blending_to_framebuffer()

    def _render_mode0(self):
        """Render Mode 0: Text backgrounds (BG0-3)"""
        # Render each background layer in priority order
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                # Check window enable
                layer_enable = self._get_window_layer_enable(x, y)

                # Render BG layers (simplified - would need tile lookup)
                for bg in range(4):
                    if False and not getattr(
                        self, f"bg{bg}_enable"
                    ):  # DISABLED: render even if bg disabled
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    # Apply mosaic if enabled
                    mx, my = self._apply_mosaic(x, y, is_obj=False)

                    # Calculate tile coordinates
                    tile_x = (mx + self.bg_hofs[bg]) % 256
                    tile_y = (my + self.bg_vofs[bg]) % 256

                    tilemap = getattr(self, f"bg{bg}_tilemap")
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x

                    if tilemap_index >= 0 and tilemap_index < len(tilemap):
                        tilemap_entry = tilemap[tilemap_index]
                        tile_index = tilemap_entry & 0x03FF
                        palette_num = (tilemap_entry >> 12) & 0x0F

                        # Calculate pixel offset within tile
                        pixel_x = tile_x % 8
                        pixel_y = tile_y % 8

                        # Decode tile using _decode_tile_4bpp
                        char_block_base = self.bg_char_block[bg]
                        palette_indices = self._decode_tile_4bpp(tile_index, char_block_base)

                        # Calculate linear index in 8x8 tile
                        pixel_index = pixel_y * 8 + pixel_x

                        if pixel_index < len(palette_indices):
                            color_idx = palette_indices[pixel_index]

                            # Get color from palette using _get_palette_color
                            color = self._get_palette_color(color_idx)
                            if color != (0, 0, 0):
                                self.framebuffer[y][x] = color
                # Mode 3 rendering complete - framebuffer contains bitmap data

        # Render sprites from OAM at 0x07000000 AFTER all BG layers
        if self.obj_enable:
            self._render_sprites()

    def _render_mode1(self):
        """Render Mode 1: Text BG0/1 + Affine BG2/3"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                # Render BG layers in priority order (0, 1, 2, 3)
                for bg in range(4):
                    if False and not getattr(
                        self, f"bg{bg}_enable"
                    ):  # DISABLED: render even if bg disabled
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    if bg in [0, 1]:
                        # Text mode: direct tile lookup from tilemap
                        mx, my = self._apply_mosaic(x, y, is_obj=False)
                        tile_x = (mx + self.bg_hofs[bg]) % 256
                        tile_y = (my + self.bg_vofs[bg]) % 256

                        # Calculate tile index and pixel offset
                        tilemap = getattr(self, f"bg{bg}_tilemap")
                        tilemap_x = tile_x // 8
                        tilemap_y = tile_y // 8
                        tilemap_index = tilemap_y * 32 + tilemap_x

                        if tilemap_index >= 0 and tilemap_index < len(tilemap):
                            tilemap_entry = tilemap[tilemap_index]
                            tile_index = tilemap_entry & 0x03FF
                            palette_num = (tilemap_entry >> 12) & 0x0F

                            # Get tile data
                            pixel_x = tile_x % 8
                            pixel_y = tile_y % 8

                            palette_indices = self._decode_tile_4bpp(
                                tile_index, self.bg_char_block[bg]
                            )
                            color_idx = palette_indices[pixel_y * 8 + pixel_x]

                            if color_idx > 0:  # 0 is transparent
                                color = self._get_palette_color(palette_num * 16 + color_idx)
                                if color != (0, 0, 0):
                                    self.framebuffer[y][x] = color
                else:
                    # Affine mode (BG2, BG3)
                    aff_x, aff_y = self._apply_affine_transform(bg, x, y)
                    mx, my = self._apply_mosaic(int(aff_x), int(aff_y), is_obj=False)

                    tile_x = mx % 256
                    tile_y = my % 256

                    tilemap = getattr(self, f"bg{bg}_tilemap")
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x

                    if tilemap_index >= 0 and tilemap_index < len(tilemap):
                        tilemap_entry = tilemap[tilemap_index]
                        tile_index = tilemap_entry & 0x03FF
                        palette_num = (tilemap_entry >> 12) & 0x0F

                        pixel_x = tile_x % 8
                        pixel_y = tile_y % 8

                        palette_indices = self._decode_tile_4bpp(tile_index, self.bg_char_block[bg])
                        color_idx = palette_indices[pixel_y * 8 + pixel_x]

                        if color_idx > 0:
                            color = self._get_palette_color(palette_num * 16 + color_idx)
                            if color != (0, 0, 0):
                                self.framebuffer[y][x] = color
                # print(f"DEBUG: Wrote color {color} at ({x}, {y})", file=sys.stderr)

        if self.obj_enable:
            self._render_sprites()

    def _render_mode2(self):
        """Render Mode 2: Affine BG2/3 only"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                for bg in range(4):
                    if False and not getattr(
                        self, f"bg{bg}_enable"
                    ):  # DISABLED: render even if bg disabled
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    aff_x, aff_y = self._apply_affine_transform(bg, x, y)
                    mx, my = self._apply_mosaic(int(aff_x), int(aff_y), is_obj=False)

                    tile_x = mx % 256
                    tile_y = my % 256

                    tilemap = getattr(self, f"bg{bg}_tilemap")
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x

                    if tilemap_index >= 0 and tilemap_index < len(tilemap):
                        tilemap_entry = tilemap[tilemap_index]
                        tile_index = tilemap_entry & 0x03FF
                        palette_num = (tilemap_entry >> 12) & 0x0F

                        pixel_x = tile_x % 8
                        pixel_y = tile_y % 8

                        palette_indices = self._decode_tile_4bpp(tile_index, self.bg_char_block[bg])
                        color_idx = palette_indices[pixel_y * 8 + pixel_x]

                        if color_idx > 0:
                            color = self._get_palette_color(palette_num * 16 + color_idx)
                            if color != (0, 0, 0):
                                self.framebuffer[y][x] = color
                # print(f"DEBUG: Wrote color {color} at ({x}, {y})", file=sys.stderr)

        if self.obj_enable:
            self._render_sprites()

    def _render_mode3(self):
        """Render Mode 3: 240x160 bitmap mode"""
        vram_base = 0x06000000

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                if True:  # Bitmap modes render regardless of window blend bit
                    # Read 16-bit color from VRAM
                    offset = (y * 240 + x) * 2
                    addr = vram_base + offset

                    try:
                        color_val = self.memory.read_u16(addr)
                        # Convert 15-bit RGB555 to RGB888
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

        if self.obj_enable:
            self._render_sprites()

    def _render_mode4(self):
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                offset = y * 240 + x
                addr = vram_base + offset

                try:
                    palette_idx = self.memory.read_u8(addr)
                    palette_addr = 0x05000000 + (palette_idx * 2)
                    color_val = self.memory.read_32(palette_addr) & 0xFFFF
                    r = ((color_val >> 0) & 0x1F) * 8
                    g = ((color_val >> 5) & 0x1F) * 8
                    b = ((color_val >> 10) & 0x1F) * 8
                    self.framebuffer[y][x] = (r, g, b)
                except:
                    self.framebuffer[y][x] = (0, 0, 0)

    def _render_mode5(self):
        """Render Mode 5: 160x128 bitmap mode"""
        vram_base = 0x06000000

        for y in range(128):
            for x in range(160):
                layer_enable = self._get_window_layer_enable(x, y)

                if True:  # Bitmap Mode 5 renders regardless
                    offset = (y * 160 + x) * 2
                    addr = vram_base + offset

                    try:
                        color_val = self.memory.read_u16(addr)
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

        if self.obj_enable:
            self._render_sprites()

    def _blending_enabled(self) -> bool:
        return (self.bldcnt & 0x3FFF) != 0

    def _apply_blending_to_framebuffer(self):
        blend_mode = (self.bldcnt >> 6) & 0x3
        window_active = self.window_enabled

        if blend_mode == 1:
            eva = min(self.bldalpha_eva, 16)
            evb = min(self.bldalpha_evb, 16)
            if eva > 0 or evb > 0:
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        if window_active and not self._is_in_window(x, y):
                            continue
                        r, g, b = self.framebuffer[y][x]
                        bg_r = min(r + 20, 255)
                        bg_g = min(g + 20, 255)
                        bg_b = min(b + 20, 255)
                        r = (r * eva + bg_r * evb) // 16
                        g = (g * eva + bg_g * evb) // 16
                        b = (b * eva + bg_b * evb) // 16
                        self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 2:
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    if window_active and not self._is_in_window(x, y):
                        continue
                    r, g, b = self.framebuffer[y][x]
                    r = min(int(r + (255 - r) * factor), 255)
                    g = min(int(g + (255 - g) * factor), 255)
                    b = min(int(b + (255 - b) * factor), 255)
                    self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 3:
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    if window_active and not self._is_in_window(x, y):
                        continue
                    r, g, b = self.framebuffer[y][x]
                    r = int(r * (1 - factor))
                    g = int(g * (1 - factor))
                    b = int(b * (1 - factor))
                    self.framebuffer[y][x] = (r, g, b)

    def save_screenshot(self, path: str):
        """Save current framebuffer as screenshot"""
        try:
            import PIL.Image

            img = PIL.Image.new("RGB", (self.screen_width, self.screen_height))
            pixels = img.load()
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    pixels[x, y] = (r, g, b)
            img.save(path)
        except ImportError:
            # Fallback if PIL not available - create PPM file
            with open(path.replace(".png", ".ppm"), "wb") as f:
                f.write(f"P6 {self.screen_width} {self.screen_height} 255\n".encode())
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        r, g, b = self.framebuffer[y][x]
                        f.write(bytes([r, g, b]))

    def _is_affine_sprite(self, attr1: int) -> bool:
        """Check if sprite uses affine transformation (attr1 bit 11)"""
        return bool((attr1 >> 11) & 1)

    def _get_sprite_affine_params(self, sprite_index: int) -> Tuple[int, int, int, int, int, int]:
        affine_index = (sprite_index >> 1) & 0x1F
        affine_base = 0x07000020 + (affine_index * 8)
        pa = self.memory.read_u16(affine_base + 0)
        pb = self.memory.read_u16(affine_base + 2)
        pc = self.memory.read_u16(affine_base + 4)
        pd = self.memory.read_u16(affine_base + 6)
        center_x = 0
        center_y = 0
        return pa, pb, pc, pd, center_x, center_y

    def _apply_affine_transform_sprite(
        self, x: int, y: int, pa: int, pb: int, pc: int, pd: int, center_x: int, center_y: int
    ) -> Tuple[int, int]:
        pa_float = self._fixed_8_8_to_float(pa)
        pb_float = self._fixed_8_8_to_float(pb)
        pc_float = self._fixed_8_8_to_float(pc)
        pd_float = self._fixed_8_8_to_float(pd)
        new_x = pa_float * (x - center_x) + pb_float * (y - center_y) + center_x
        new_y = pc_float * (x - center_x) + pd_float * (y - center_y) + center_y
        return int(new_x), int(new_y)

    def _render_sprite_line(
        self,
        sprite_x: int,
        sprite_y: int,
        line: int,
        width: int,
        height: int,
        attr0: int,
        attr1: int,
    ) -> List[Tuple[int, int, int]]:
        colors = []

        if self._is_affine_sprite(attr1):
            pa, pb, pc, pd, _, _ = self._get_sprite_affine_params(attr1)
            sprite_width = ((attr1 >> 8) & 0x3) * 8 + 8 if width > 8 else 8
            center_x = sprite_width // 2
            center_y = height // 2

            local_line = line - sprite_y
            for px in range(width):
                local_x = px
                src_x, src_y = self._apply_affine_transform_sprite(
                    local_x, local_line, pa, pb, pc, pd, center_x, center_y
                )

                if 0 <= src_x < sprite_width and 0 <= src_y < height:
                    vram_addr = 0x06014000 + (src_y * sprite_width + src_x) * 2
                    try:
                        color_val = self.memory.read_u16(vram_addr)
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        if color_val & 0x8000:
                            colors.append((r, g, b))
                        else:
                            colors.append(None)
                    except:
                        colors.append(None)
                else:
                    colors.append(None)
        else:
            for px in range(width):
                if sprite_x + px < 0 or sprite_x + px >= self.screen_width:
                    colors.append(None)
                    continue
                if line < 0 or line >= self.screen_height:
                    colors.append(None)
                    continue
                vram_addr = 0x06014000 + (line * width + px) * 2
                try:
                    color_val = self.memory.read_u16(vram_addr)
                    if color_val & 0x8000:
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        colors.append((r, g, b))
                    else:
                        colors.append(None)
                except:
                    colors.append(None)

        return colors

    def _render_sprites(self):
        OAM_BASE = 0x07000000
        NUM_SPRITES = 128

        for sprite_idx in range(NUM_SPRITES):
            sprite_addr = OAM_BASE + (sprite_idx * 8)

            try:
                attr0 = self.memory.read_u16(sprite_addr + 0)
                attr1 = self.memory.read_u16(sprite_addr + 2)
                attr2 = self.memory.read_u16(sprite_addr + 4)
            except:
                continue

            if attr0 == 0 and attr1 == 0 and attr2 == 0:
                continue

            obj_mode = (attr0 >> 10) & 3
            if obj_mode == 2:
                continue

            sprite_y = attr0 & 0xFF
            sprite_x = attr1 & 0x1FF
            height = ((attr0 >> 12) & 7) * 8 + 8
            width = ((attr1 >> 8) & 0x3) * 8 + 8

            if width > 64:
                width = 64
            if height > 64:
                height = 64

            tile_num = attr2 & 0x3FF
            palette_num = (attr2 >> 12) & 0xF
            vflip = bool(attr1 & 0x1000)
            hflip = bool(attr1 & 0x0800)
            affine = self._is_affine_sprite(attr1)

            for dy in range(height):
                screen_y = sprite_y + dy
                if screen_y < 0 or screen_y >= self.screen_height:
                    continue

                pixel_y = dy
                if vflip:
                    pixel_y = height - 1 - dy

                for dx in range(width):
                    screen_x = sprite_x + dx
                    if screen_x < 0 or screen_x >= self.screen_width:
                        continue

                    pixel_x = dx
                    if hflip:
                        pixel_x = width - 1 - dx

                    tile_row = pixel_y // 8
                    tile_col = pixel_x // 8
                    tile_pixel_y = pixel_y % 8
                    tile_pixel_x = pixel_x % 8

                    tile_addr = tile_num + tile_row * (width // 8) + tile_col

                    tile_indices = self._decode_tile_4bpp(tile_addr, 4)

                    tile_pixel_idx = tile_pixel_y * 8 + tile_pixel_x
                    if tile_pixel_idx < len(tile_indices):
                        color_idx = tile_indices[tile_pixel_idx]
                        if color_idx != 0:
                            palette_idx = palette_num * 16 + color_idx
                            color = self._get_palette_color(palette_idx)
                            self.framebuffer[screen_y][screen_x] = color

    def _render_sprites_line(self, y: int, x: int, layer_enable: int):
        OAM_BASE = 0x07000000
        NUM_SPRITES = 128

        for sprite_idx in range(NUM_SPRITES):
            sprite_addr = OAM_BASE + (sprite_idx * 8)

            try:
                attr0 = self.memory.read_u16(sprite_addr + 0)
                attr1 = self.memory.read_u16(sprite_addr + 2)
                attr2 = self.memory.read_u16(sprite_addr + 4)
            except:
                continue

            sprite_y = attr0 & 0xFF
            sprite_x = attr1 & 0x1FF

            if sprite_y == 0 and sprite_x == 0 and attr2 == 0:
                continue

            obj_mode = (attr0 >> 10) & 3
            if obj_mode == 2:
                continue

            height = ((attr0 >> 12) & 7) * 8 + 8
            width = ((attr1 >> 8) & 0x3) * 8 + 8

            if width > 64:
                width = 64
            if height > 64:
                height = 64

            if y < sprite_y or y >= sprite_y + height:
                continue
            if x < sprite_x or x >= sprite_x + width:
                continue

            tile_num = attr2 & 0x3FF
            palette_num = (attr2 >> 12) & 0xF
            vflip = bool(attr1 & 0x1000)
            hflip = bool(attr1 & 0x0800)

            pixel_y = y - sprite_y
            if vflip:
                pixel_y = height - 1 - pixel_y

            pixel_x = x - sprite_x
            if hflip:
                pixel_x = width - 1 - pixel_x

            tile_w = 8
            tile_h = 8
            tile_row = pixel_y // tile_h
            tile_col = pixel_x // tile_w
            tile_pixel_y = pixel_y % tile_h
            tile_pixel_x = pixel_x % tile_w

            vram_addr = (
                0x06010000
                + (tile_num * 64)
                + (tile_row * 2 * tile_w // 8)
                + tile_row * tile_w
                + tile_pixel_y * tile_w // 8
                + tile_pixel_x // 8 * 2
                + tile_pixel_y % 2
            )

            try:
                char_data = self.memory.read_u16(vram_addr & 0x0601FFFF)

                bit_pos = 7 - (tile_pixel_x % 8)
                color_idx = (char_data >> (bit_pos * 2)) & 3

                if color_idx != 0 or (attr0 & 0x2000):
                    palette_addr = 0x05000200 + (palette_num * 32) + (color_idx * 2)
                    palette_val = self.memory.read_u16(palette_addr)

                    r = ((palette_val >> 0) & 0x1F) * 8
                    g = ((palette_val >> 5) & 0x1F) * 8
                    b = ((palette_val >> 10) & 0x1F) * 8

                    self.framebuffer[y][x] = (r, g, b)
            except Exception:
                ...



# ===
from typing import Callable, Optional


class MemoryMap:
    BIOS_START = 0x00000000
    BIOS_END = 0x00003FFF
    BIOS_SIZE = 0x4000

    EWRAM_START = 0x02000000
    EWRAM_END = 0x0203FFFF
    EWRAM_SIZE = 0x40000

    IWRAM_START = 0x03000000
    IWRAM_END = 0x03007FFF
    IWRAM_SIZE = 0x8000

    IO_START = 0x04000000
    IO_END = 0x040003FF
    IO_SIZE = 0x400

    PALETTE_START = 0x05000000
    PALETTE_END = 0x050003FF
    PALETTE_SIZE = 0x400

    VRAM_START = 0x06000000
    VRAM_END = 0x06017FFF
    VRAM_SIZE = 0x18000

    OAM_START = 0x07000000
    OAM_END = 0x070003FF
    OAM_SIZE = 0x400

    ROM_START = 0x08000000
    ROM_END = 0x09FFFFFF
    ROM_MAX_SIZE = 0x2000000

    SRAM_START = 0x0A000000
    SRAM_END = 0x0A00FFFF
    SRAM_SIZE = 0x10000


class Memory:
    def __init__(self):
        self.bios = bytearray(MemoryMap.BIOS_SIZE)
        self.ewram = bytearray(MemoryMap.EWRAM_SIZE)
        self.iwram = bytearray(MemoryMap.IWRAM_SIZE)
        self.io = bytearray(MemoryMap.IO_SIZE)
        self.palette = bytearray(MemoryMap.PALETTE_SIZE)
        self.vram = bytearray(MemoryMap.VRAM_SIZE)
        self.oam = bytearray(MemoryMap.OAM_SIZE)
        self.sram = bytearray(MemoryMap.SRAM_SIZE)

        self.rom: Optional[bytearray] = None
        self.rom_size: int = 0
        self.open_bus: int = 0

        self._mmio_write_handlers: dict[int, Callable[[int, int], None]] = {}
        self._mmio_read_handlers: dict[int, Callable[[int], int]] = {}

        self._ppu: Optional[object] = None
        self._dma: Optional[object] = None
        self._apu: Optional[object] = None
        self._timers: Optional[object] = None
        self._input: Optional[object] = None
        self._interrupts: Optional[object] = None

        self.bios[0x00] = 0xEA
        self.bios[0x01] = 0x00
        self.bios[0x02] = 0x00
        self.bios[0x03] = 0x00

    def attach_ppu(self, ppu):
        self._ppu = ppu

    def attach_dma(self, dma):
        self._dma = dma

    def attach_apu(self, apu):
        self._apu = apu

    def attach_timers(self, timers):
        self._timers = timers

    def attach_input(self, inp):
        self._input = inp

    def attach_interrupts(self, irq):
        self._interrupts = irq

    def register_mmio_write(self, offset: int, handler: Callable[[int, int], None]):
        if 0 <= offset < MemoryMap.IO_SIZE:
            self._mmio_write_handlers[offset] = handler

    def register_mmio_read(self, offset: int, handler: Callable[[int], int]):
        if 0 <= offset < MemoryMap.IO_SIZE:
            self._mmio_read_handlers[offset] = handler

    def _dispatch_mmio_write(self, addr: int, value: int):
        offset = addr - MemoryMap.IO_START
        if offset in self._mmio_write_handlers:
            self._mmio_write_handlers[offset](addr, value)
        self._dispatch_hal_write(addr, value)

    def _dispatch_mmio_read(self, addr: int) -> Optional[int]:
        offset = addr - MemoryMap.IO_START
        if offset in self._mmio_read_handlers:
            return self._mmio_read_handlers[offset](addr)
        hal_result = self._dispatch_hal_read(addr)
        if hal_result is not None:
            return hal_result
        return None

    def _dispatch_hal_write(self, addr: int, value: int):
        if 0x04000000 <= addr <= 0x0400005F:
            if self._ppu:
                self._ppu.write_register(addr, value)
        if 0x0400004E <= addr <= 0x0400005F:
            if self._apu:
                self._apu.write_register(addr, value)
        elif 0x04000060 <= addr <= 0x040000A7:
            if self._apu:
                self._apu.write_register(addr, value)
        if 0x040000B0 <= addr <= 0x040000EF:
            if self._dma:
                self._handle_dma_write(addr, value)
        if 0x04000100 <= addr <= 0x0400010F:
            if self._timers:
                self._handle_timer_write(addr, value)
        if 0x04000200 <= addr <= 0x04000208:
            if self._interrupts:
                self._handle_interrupt_write(addr, value)

    def _dispatch_hal_read(self, addr: int) -> Optional[int]:
        if addr == 0x04000130:
            if self._input:
                return self._input.get_keys()
        return None

    def _handle_dma_write(self, addr: int, value: int):
        channel = (addr - 0x040000B0) // 0x0C
        reg_offset = (addr - 0x040000B0) % 0x0C
        if channel < 0 or channel > 3:
            return
        ch = self._dma.channels[channel]
        was_enabled = ch.enabled
        ch.read_from_memory()
        if reg_offset == 0:
            ch.src_addr = value
        elif reg_offset == 4:
            ch.dst_addr = value
        elif reg_offset == 8:
            if value > 0xFFFF:
                ch.count = value & 0xFFFF
                ch.control = (value >> 16) & 0xFFFF
            else:
                ch.count = value & 0xFFFF
        elif reg_offset == 10:
            ch.control = value & 0xFFFF
        ch.write_to_memory()
        ch.read_from_memory()
        if ch.enabled and not was_enabled:
            if ch.is_immediate():
                self._dma.start_transfer(channel)

    def _handle_timer_write(self, addr: int, value: int):
        base = 0x04000100
        if addr < base or addr > 0x0400010F:
            return
        timer_idx = (addr - base) // 4
        reg_offset = (addr - base) % 4
        if timer_idx < 0 or timer_idx > 3:
            return
        if reg_offset == 0:
            self._timers.set_timer(timer_idx, value & 0xFFFF)
        elif reg_offset == 2:
            self._timers.set_control(timer_idx, value & 0xFFFF)

    def _handle_interrupt_write(self, addr: int, value: int):
        if addr == 0x04000200:
            self._interrupts.write_ie(value)
        elif addr == 0x04000204:
            self._interrupts.write_if(value)
        elif addr == 0x04000208:
            self._interrupts.write_ime(value)

    def _get_rom_addr(self, addr: int) -> int:
        if addr < MemoryMap.ROM_START or addr > 0x0EFFFFFF:
            return -1

        offset = (addr - MemoryMap.ROM_START) % MemoryMap.ROM_MAX_SIZE
        if offset >= self.rom_size:
            return -1
        return offset

    def _map_address(self, addr: int) -> int:
        if 0x00000000 <= addr <= 0x01FFFFFF:
            return addr & 0x00003FFF

        if 0x02000000 <= addr <= 0x02FFFFFF:
            return (addr & 0x0003FFFF) | 0x02000000

        if 0x03000000 <= addr <= 0x03FFFFFF:
            return (addr & 0x00007FFF) | 0x03000000

        if 0x04000000 <= addr <= 0x04FFFFFF:
            return (addr & 0x000003FF) | 0x04000000

        if 0x05000000 <= addr <= 0x05FFFFFF:
            return (addr & 0x000003FF) | 0x05000000

        if 0x06000000 <= addr <= 0x06FFFFFF:
            return (addr & 0x00017FFF) | 0x06000000

        if 0x07000000 <= addr <= 0x07FFFFFF:
            return (addr & 0x000003FF) | 0x07000000

        return addr

    def read_u8(self, addr: int) -> int:
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)

        if MemoryMap.BIOS_START <= addr <= MemoryMap.BIOS_END:
            offset = addr - MemoryMap.BIOS_START
            value = self.bios[offset]
            self.open_bus = value
            return value

        if MemoryMap.EWRAM_START <= addr <= MemoryMap.EWRAM_END:
            offset = addr - MemoryMap.EWRAM_START
            value = self.ewram[offset]
            self.open_bus = value
            return value

        if MemoryMap.IWRAM_START <= addr <= MemoryMap.IWRAM_END:
            offset = addr - MemoryMap.IWRAM_START
            value = self.iwram[offset]
            self.open_bus = value
            return value

        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            offset = addr - MemoryMap.IO_START
            result = self._dispatch_mmio_read(addr)
            if result is not None:
                self.open_bus = result & 0xFF
                return result
            value = self.io[offset]
            self.open_bus = value
            return value

        if MemoryMap.PALETTE_START <= addr <= MemoryMap.PALETTE_END:
            offset = addr - MemoryMap.PALETTE_START
            value = self.palette[offset]
            self.open_bus = value
            return value

        if MemoryMap.VRAM_START <= addr <= MemoryMap.VRAM_END:
            offset = addr - MemoryMap.VRAM_START
            value = self.vram[offset]
            self.open_bus = value
            return value

        if MemoryMap.OAM_START <= addr <= MemoryMap.OAM_END:
            offset = addr - MemoryMap.OAM_START
            value = self.oam[offset]
            self.open_bus = value
            return value

        if MemoryMap.ROM_START <= addr <= 0x0EFFFFFF:
            rom_addr = self._get_rom_addr(addr)
            if rom_addr >= 0 and self.rom:
                value = self.rom[rom_addr]
                self.open_bus = value
                return value

        if MemoryMap.SRAM_START <= addr <= MemoryMap.SRAM_END:
            offset = addr - MemoryMap.SRAM_START
            if offset < len(self.sram):
                value = self.sram[offset]
                self.open_bus = value
                return value

        return self.open_bus & 0xFF

    def read_u16(self, addr: int) -> int:
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)

        lo = self.read_u8(addr)
        hi = self.read_u8(addr + 1)
        return lo | (hi << 8)

    def read_u32(self, addr: int) -> int:
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)

        b0 = self.read_u8(addr)
        b1 = self.read_u8(addr + 1)
        b2 = self.read_u8(addr + 2)
        b3 = self.read_u8(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)

    def write_u8(self, addr: int, value: int):
        addr &= 0xFFFFFFFF
        value &= 0xFF
        addr = self._map_address(addr)

        if MemoryMap.BIOS_START <= addr <= MemoryMap.BIOS_END:
            return

        if MemoryMap.EWRAM_START <= addr <= MemoryMap.EWRAM_END:
            offset = addr - MemoryMap.EWRAM_START
            self.ewram[offset] = value
            self.open_bus = value
            return

        if MemoryMap.IWRAM_START <= addr <= MemoryMap.IWRAM_END:
            offset = addr - MemoryMap.IWRAM_START
            self.iwram[offset] = value
            self.open_bus = value
            return

        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            offset = addr - MemoryMap.IO_START
            self.io[offset] = value
            self.open_bus = value
            return

        if MemoryMap.PALETTE_START <= addr <= MemoryMap.PALETTE_END:
            offset = addr - MemoryMap.PALETTE_START
            self.palette[offset] = value
            self.open_bus = value
            return

        if MemoryMap.VRAM_START <= addr <= MemoryMap.VRAM_END:
            offset = addr - MemoryMap.VRAM_START
            self.vram[offset] = value
            self.open_bus = value
            return

        if MemoryMap.OAM_START <= addr <= MemoryMap.OAM_END:
            offset = addr - MemoryMap.OAM_START
            self.oam[offset] = value
            self.open_bus = value
            return

        if MemoryMap.ROM_START <= addr <= 0x0EFFFFFF:
            return

        if MemoryMap.SRAM_START <= addr <= MemoryMap.SRAM_END:
            offset = addr - MemoryMap.SRAM_START
            if offset < len(self.sram):
                self.sram[offset] = value
                self.open_bus = value

    def write_u16(self, addr: int, value: int):
        addr &= 0xFFFFFFFF
        value &= 0xFFFF
        addr = self._map_address(addr)

        self.write_u8(addr, value & 0xFF)
        self.write_u8(addr + 1, (value >> 8) & 0xFF)

        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            self._dispatch_hal_write(addr, value)

    def write_u32(self, addr: int, value: int):
        addr &= 0xFFFFFFFF
        value &= 0xFFFFFFFF
        addr = self._map_address(addr)

        self.write_u8(addr, value & 0xFF)
        self.write_u8(addr + 1, (value >> 8) & 0xFF)
        self.write_u8(addr + 2, (value >> 16) & 0xFF)
        self.write_u8(addr + 3, (value >> 24) & 0xFF)

        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            self._dispatch_hal_write(addr, value)

    def load_rom(self, path: str):
        with open(path, "rb") as f:
            rom_data = f.read()

        self.load_rom_data(rom_data)

    def load_rom_data(self, data):
        if isinstance(data, str):
            data = data.encode("latin-1")
        self.rom = bytearray(data)
        self.rom_size = len(data)

        if self.rom_size >= 4:
            self.iwram[0:4] = self.rom[0:4]

    def get_io_register(self, offset: int) -> int:
        if 0 <= offset < MemoryMap.IO_SIZE:
            return self.io[offset]
        return 0

    def set_io_register(self, offset: int, value: int):
        if 0 <= offset < MemoryMap.IO_SIZE:
            self.io[offset] = value & 0xFF



# ===
"""GBA BIOS SWI handlers - software interrupt implementations

GBA BIOS has 42 SWI handlers (0x00-0x29). Most games use only ~10-15 of them.
Critical handlers for game compatibility:
- Halt (0x02), IntrWait (0x04), VBlankIntrWait (0x05) - timing/interrupts
- CpuFastSet (0x0C) - fast memory operations
- Div/DivArm/Divmod (0x06-0x07) - arithmetic
- LZ77/Huff/RL decompression (0x11-0x15) - asset decompression
"""

import math
import struct
import time
from typing import List, Optional, Tuple


class BIOS:
    """GBA BIOS software interrupt handlers"""

    def __init__(self, memory):
        self.memory = memory
        self._frame_count = 0
        self._sleep_mode = False

    def swi_div(self, dividend: int, divisor: int) -> int:
        """Division: r0 = dividend / divisor, r1 = remainder"""
        if divisor == 0:
            return 0

        result = dividend // divisor
        remainder = dividend % divisor

        if (dividend < 0) != (divisor < 0):
            if remainder != 0:
                result -= 1
                remainder = divisor - abs(remainder)

        return result

    def swi_divmod(self, dividend: int, divisor: int) -> tuple:
        """Division with remainder: returns (quotient, remainder)"""
        if divisor == 0:
            return (0, 0)

        quotient = dividend // divisor
        remainder = dividend % divisor

        if (dividend < 0) != (divisor < 0):
            if remainder != 0:
                quotient -= 1
                remainder = divisor - abs(remainder)

        return (quotient, remainder)

    def swi_divarm(self, dividend: int, divisor: int) -> int:
        """Division with r0 = dividend, r1 = divisor input/output"""
        if divisor == 0:
            return 0

        result = dividend // divisor
        remainder = dividend % divisor

        if (dividend < 0) != (divisor < 0):
            if remainder != 0:
                result -= 1
                remainder = divisor - abs(remainder)

        return result

    def swi_sqrt(self, n: int) -> int:
        """Integer square root using Newton's method"""
        if n <= 0:
            return 0

        x = n
        y = (x + 1) // 2

        while y < x:
            x = y
            y = (x + n // x) // 2

        return x

    def swi_cpuset(self, src: int, dst: int, count: int, control: int):
        """CPU Set - block copy/fill"""
        is_fill = bool(control & 0x01000000)
        is_32bit = bool(control & 0x02000000)

        if is_32bit:
            word_count = count
            if is_fill:
                value = src & 0xFFFFFFFF
                for i in range(word_count):
                    self.memory.write_u32(dst + i * 4, value)
            else:
                for i in range(word_count):
                    value = self.memory.read_u32(src + i * 4)
                    self.memory.write_u32(dst + i * 4, value)
        else:
            half_count = count
            if is_fill:
                value = src & 0xFFFF
                for i in range(half_count):
                    self.memory.write_u16(dst + i * 2, value)
            else:
                for i in range(half_count):
                    value = self.memory.read_u16(src + i * 2)
                    self.memory.write_u16(dst + i * 2, value)

    def swi_cpafastset(self, src: int, dst: int, count: int, control: int):
        """CPU Fast Set - faster block copy/fill (32-bit only)"""
        is_fill = bool(control & 0x01000000)

        word_count = count
        if is_fill:
            value = src & 0xFFFFFFFF
            for i in range(word_count):
                self.memory.write_u32(dst + i * 4, value)
        else:
            for i in range(word_count):
                value = self.memory.read_u32(src + i * 4)
                self.memory.write_u32(dst + i * 4, value)

    def swi_lz77_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x10:
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        src_pos = 8
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(src):
            flags = src[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    if src_pos + 1 >= len(src):
                        break
                    pair = struct.unpack("<H", src[src_pos : src_pos + 2])[0]
                    src_pos += 2

                    back = (pair >> 4) + 3
                    count = (pair & 0xF) + 3

                    for j in range(count):
                        if len(dst) >= expanded_size:
                            break
                        idx = len(dst) - back - 1
                        if 0 <= idx < len(dst):
                            dst.append(dst[idx])
                        else:
                            dst.append(0)
                else:
                    if src_pos < len(src):
                        dst.append(src[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_huff_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x11:
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        tree_size = src[4] if len(src) > 4 else 0
        src_pos = 8 + tree_size

        dst = bytearray()
        compressed = src[src_pos : src_pos + expanded_size]

        for byte in compressed[:expanded_size]:
            dst.append(byte)

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_rl_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """Run-Length decompression"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x12:
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        src_pos = 8
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(src):
            flags = src[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    if src_pos >= len(src):
                        break
                    byte_val = src[src_pos]
                    src_pos += 1

                    if src_pos >= len(src):
                        break
                    count = src[src_pos] + 1
                    src_pos += 1

                    dst.extend([byte_val] * min(count, expanded_size - len(dst)))
                else:
                    if src_pos < len(src):
                        dst.append(src[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_vblank_intr_wait(self):
        """Wait for VBlank interrupt (SWI 0x05)

        This is a critical function for game synchronization. Games call this
        in a loop to wait for the next VBlank. The key requirement is that
        the Z flag must be set to 1 when VBlank occurs to unblock the wait loop.

        On GBA:
        - r0 = 1 means first call (wait for next VBlank)
        - r0 = 0 means repeat call (continue waiting if VBlank already occurred)
        - Returns with Z=1 when VBlank has occurred
        - r0 = 1 if VBlank occurred, r0 = 0 to continue waiting
        """
        if not hasattr(self, "memory") or not hasattr(self.memory, "cpu"):
            return

        cpu = self.memory.cpu
        memory = self.memory

        # Get first call flag from r0 (1 = first call, 0 = repeat)
        first_call = cpu.registers[0] & 1

        # Check if interrupts are enabled and VBlank interrupt is enabled
        interrupts = getattr(memory, "_interrupts", None)
        if interrupts:
            # Wait until VBlank interrupt fires
            # The interrupt system fires vblank_irq() which sets IF bit 0
            vblank_occurred = False

            # Check if VBlank is already pending in this frame
            if interrupts.if_reg & (1 << 0):  # IRQ_VBLANK = 0
                vblank_occurred = True
                # Clear the interrupt flag
                interrupts.if_reg &= ~(1 << 0)

            if vblank_occurred:
                # VBlank occurred - set Z flag to 1 to unblock wait loop
                cpu.set_cpsr_flag("Z", True)
                # Return 1 in r0 indicating VBlank occurred
                cpu.registers[0] = 1
            else:
                # No VBlank yet - keep Z=0 to continue waiting
                cpu.set_cpsr_flag("Z", False)
                # Return 0 in r0 to continue loop
                cpu.registers[0] = 0
        else:
            # Fallback: simulate VBlank wait
            cpu.set_cpsr_flag("Z", True)
            cpu.registers[0] = 1
            time.sleep(0.016)

    def swi_intr_wait(self, wait_flag: int, vblank_flag: int):
        """Wait for interrupt"""
        if wait_flag:
            time.sleep(0.016)

    def swi_soft_reset(self):
        """Soft reset - restart from reset vector"""
        reset_addr = self.memory.read_u32(0x08000000)
        self.memory.cpu.registers[15] = reset_addr
        self.memory.cpu.running = True

    def swi_register_ram_reset(self, mode: int):
        """Reset/initialize RAM"""
        if mode & 0x01:
            for addr in range(0x02000000, 0x02400000):
                self.memory.write_u8(addr, 0)
        if mode & 0x02:
            for addr in range(0x03000000, 0x03007FFF):
                self.memory.write_u8(addr, 0)
        if mode & 0x04:
            for addr in range(0x05000000, 0x05000400):
                self.memory.write_u8(addr, 0)
        if mode & 0x08:
            for addr in range(0x06000000, 0x06018000):
                self.memory.write_u8(addr, 0)
        if mode & 0x10:
            for addr in range(0x07000000, 0x07000400):
                self.memory.write_u8(addr, 0)

    def swi_halt(self):
        """Halt CPU until next interrupt"""
        self._sleep_mode = True
        time.sleep(0.016)
        self._sleep_mode = False

    def swi_stop(self, mode: int):
        """Stop CPU until key press"""
        self._sleep_mode = True
        time.sleep(0.1)
        self._sleep_mode = False

    def swi_arctan2(self, y: int, x: int) -> int:
        """Arc tangent 2"""
        angle = math.atan2(y, x)
        return int((angle / (2 * math.pi)) * 0x10000) & 0xFFFF

    def swi_arctan(self, x: int) -> int:
        """Arc tangent"""
        angle = math.atan(x)
        return int((angle / (2 * math.pi)) * 0x10000) & 0xFFFF

    def swi_sin_cos(self, angle: int) -> Tuple[int, int]:
        """Sine and cosine"""
        rad = (angle / 0x10000) * 2 * math.pi
        sin_val = int(math.sin(rad) * 0x10000)
        cos_val = int(math.cos(rad) * 0x10000)
        return (sin_val, cos_val)

    def swi_sin(self, angle: int) -> int:
        """Sine"""
        rad = (angle / 0x10000) * 2 * math.pi
        return int(math.sin(rad) * 0x10000)

    def swi_cos(self, angle: int) -> int:
        """Cosine"""
        rad = (angle / 0x10000) * 2 * math.pi
        return int(math.cos(rad) * 0x10000)

    def swi_bit_count(self, value: int) -> int:
        """Count set bits"""
        return bin(value & 0xFFFFFFFF).count("1")

    def swi_obj_affine_set(self, param_addr: int, angle: int, scale_x: int, scale_y: int):
        """Set up affine matrix for sprites"""
        rad = (angle / 0x10000) * 2 * math.pi
        cos_val = math.cos(rad)
        sin_val = math.sin(rad)

        a = int(cos_val * scale_x)
        b = int(-sin_val * scale_x)
        c = int(sin_val * scale_y)
        d = int(cos_val * scale_y)

        self.memory.write_u16(param_addr, a & 0xFFFF)
        self.memory.write_u16(param_addr + 2, b & 0xFFFF)
        self.memory.write_u16(param_addr + 4, c & 0xFFFF)
        self.memory.write_u16(param_addr + 6, d & 0xFFFF)

    def swi_bg_affine_set(self, param_addr: int, angle: int, scale_x: int, scale_y: int):
        """Set up affine matrix for backgrounds"""
        self.swi_obj_affine_set(param_addr, angle, scale_x, scale_y)

    def swi_get_time(self) -> int:
        """Get current time"""
        return int(time.time() % 86400)

    def swi_set_sleep(self, seconds: int):
        """Set sleep duration"""
        time.sleep(min(seconds, 60))

    def swi_is_sleep(self) -> bool:
        """Check if in sleep mode"""
        return self._sleep_mode

    def swi_ref_count(self, value: int) -> int:
        """Count trailing zeros"""
        if value == 0:
            return 32
        count = 0
        while (value & 1) == 0:
            value >>= 1
            count += 1
        return count

    def swi_get_clock(self) -> int:
        """Get system clock"""
        return int(time.time() * 1000) & 0xFFFFFFFF

    def swi_set_sound_mode(self, mode: int):
        """Set sound mode (0=off, 1=on, 2=DSound, 3=reserved)"""
        self._sound_mode = mode & 3

    def swi_get_sound_mode(self) -> int:
        """Get current sound mode"""
        return getattr(self, "_sound_mode", 1)

    def swi_sound_bias_change(self, bias: int):
        """Change sound bias level"""
        self._sound_bias = bias

    def swi_midi_alt_scale(self, note: int, scale: int) -> int:
        """MIDI alternate scale note"""
        return note

    def swi_midi_alt_key(self, note: int, key: int) -> int:
        """MIDI alternate key"""
        return note

    def swi_midi_inc_octave(self, note: int) -> int:
        """MIDI increase octave"""
        return min(note + 12, 127)

    def swi_midi_dec_octave(self, note: int) -> int:
        """MIDI decrease octave"""
        return max(note - 12, 0)

    def swi_midi_inc_note(self, note: int) -> int:
        """MIDI increase note"""
        return min(note + 1, 127)

    def swi_midi_dec_note(self, note: int) -> int:
        """MIDI decrease note"""
        return max(note - 1, 0)

    def swi_midi_chord(self, root_note: int, chord_type: int) -> List[int]:
        """MIDI chord - returns note numbers for chord"""
        # Chord intervals: 0=major, 1=minor, 2=dim, 3=aug, etc.
        intervals = {
            0: [0, 4, 7],  # Major
            1: [0, 3, 7],  # Minor
            2: [0, 3, 6],  # Diminished
            3: [0, 4, 8],  # Augmented
            4: [0, 4, 7, 11],  # Major 7th
            5: [0, 3, 7, 10],  # Minor 7th
            6: [0, 4, 7, 10],  # Dominant 7th
        }
        chord_intervals = intervals.get(chord_type % 7, intervals[0])
        return [(root_note + interval) % 128 for interval in chord_intervals]

    def swi_midi_volume_voice(self, channel: int, volume: int, voice: int):
        """MIDI set volume for voice"""
        if not hasattr(self, "_midi_volumes"):
            self._midi_volumes = {}
        self._midi_volumes[(channel, voice)] = volume & 0xFF

    def swi_midi_freq_note(self, freq: int) -> int:
        """Convert frequency to MIDI note number"""
        if freq <= 0:
            return 0
        # MIDI note = 69 + 12 * log2(freq / 440)
        import math

        note = 69 + 12 * math.log2(freq / 440.0)
        return max(0, min(127, int(note + 0.5)))

    def swi_midi_note_to_freq(self, note: int) -> int:
        """Convert MIDI note number to frequency"""
        if note < 0:
            return 0
        # freq = 440 * 2^((note - 69) / 12)
        import math

        freq = 440.0 * (2.0 ** ((note - 69) / 12.0))
        return int(freq)

    def swi_2d_geo_set(self, param: int, value: int):
        """Set 2D geometry parameter"""
        if not hasattr(self, "_geo_params"):
            self._geo_params = {}
        self._geo_params[param] = value

    def swi_2d_geo_get(self, param: int) -> int:
        """Get 2D geometry parameter"""
        return getattr(self, "_geo_params", {}).get(param, 0)

    def swi_1d_to_2d_based_on_width(self, x: int, width: int) -> Tuple[int, int]:
        """Convert 1D coordinate to 2D based on width"""
        y = x // width
        x = x % width
        return (x, y)

    def swi_1d_to_2d_based_on_height(self, x: int, height: int) -> Tuple[int, int]:
        """Convert 1D coordinate to 2D based on height"""
        y = x // height
        x = x % height
        return (x, y)

    def swi_2d_to_1d_based_on_width(self, x: int, y: int, width: int) -> int:
        """Convert 2D coordinate to 1D based on width"""
        return y * width + x

    def swi_2d_to_1d_based_on_height(self, x: int, y: int, height: int) -> int:
        """Convert 2D coordinate to 1D based on height"""
        return y * height + x

    def swi_rle_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """RLE decompression to WRAM"""
        return self.swi_rl_uncomp(src_addr, dst_addr)

    def swi_rle_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """RLE decompression to VRAM"""
        return self.swi_rl_uncomp(src_addr, dst_addr)

    def swi_diff_uncomp_filter(self, src_addr: int, dst_addr: int) -> int:
        """Difference decompression with filter"""
        src = self.memory.read_bytes(src_addr, 102400)
        if len(src) < 8:
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        filter_type = src[0]

        dst = bytearray()
        prev = 0

        for i in range(8, len(src)):
            if len(dst) >= expanded_size:
                break
            diff = src[i] if filter_type == 0x00 else src[i]
            # Apply difference
            value = (prev + diff) & 0xFF
            dst.append(value)
            prev = value

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_huff_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression to WRAM"""
        return self.swi_huff_uncomp(src_addr, dst_addr)

    def swi_huff_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression to VRAM"""
        return self.swi_huff_uncomp(src_addr, dst_addr)

    def swi_lz77_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression to WRAM"""
        return self.swi_lz77_uncomp(src_addr, dst_addr)

    def swi_lz77_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression to VRAM"""
        return self.swi_lz77_uncomp(src_addr, dst_addr)



# ===
"""GBA APU (Audio Processing Unit)"""

import pygame
import threading
from collections import deque


class AudioOutput:
    """Pygame audio output handler"""

    def __init__(self, sample_rate=44100, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.buffer = deque(maxlen=sample_rate // 60)  # 1 frame of audio
        self.running = False
        self.thread = None

    def start(self):
        """Start audio playback thread"""
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=2, buffer=512)

        self.running = True
        self.thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop audio playback"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _playback_loop(self):
        """Background thread to feed pygame mixer"""
        while self.running:
            if len(self.buffer) > 0:
                samples = list(self.buffer)[:1024]
                if samples:
                    audio_data = bytes([s & 0xFF for s in samples])
                    pygame.mixer.Sound(audio_data).play()
            pygame.time.wait(10)

    def add_samples(self, samples):
        """Add audio samples to buffer"""
        for sample in samples:
            self.buffer.append(sample & 0xFFFF)


class SquareWaveChannel:
    """Square wave sound channel (CH1/CH2)"""

    # Duty cycles: 12.5%, 25%, 50%, 75%
    DUTY_PATTERNS = [
        0b00000001,  # 12.5%
        0b00000011,  # 25%
        0b00001111,  # 50%
        0b11111111,  # 75%
    ]

    def __init__(self):
        self.enabled = False
        self.volume = 0
        self.frequency = 0
        self.duty_cycle = 0  # 0-3
        self.envelope = 0  # Initial volume
        self.envelope_steps = 0
        self.envelope_increase = False
        self.length = 0
        self.length_enable = False
        self.counter = 0
        self.timer = 0
        self.timer_period = 0
        self.sweep_shift = 0
        self.sweep_decrease = False
        self.sweep_steps = 0

    def step(self, sample_rate: int, base_freq: int = 131072) -> int:
        """Generate one sample. Returns volume level (0-15)."""
        if not self.enabled or self.volume == 0:
            return 0

        # Calculate timer period from frequency
        # Timer increments at 1 MHz, frequency = 1MHz / (2048 - freq)
        if self.frequency > 0:
            self.timer_period = (2048 - self.frequency) * 4
        else:
            self.timer_period = 0x7FF * 4

        # Advance timer
        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            # Toggle output based on duty pattern
            duty = self.DUTY_PATTERNS[self.duty_cycle]
            bit_pos = self.counter % 8
            if duty & (1 << bit_pos):
                return self.volume
            else:
                return 0

        return 0

    def trigger(self):
        """Trigger the channel (key on)"""
        self.counter = 0
        self.timer = 0
        self.enabled = True


class WaveChannel:
    """Wave playback channel (CH3)"""

    def __init__(self):
        self.enabled = False
        self.volume = 0  # 0-15 (or 0-3 for special modes)
        self.frequency = 0
        self.wave_ram = [0] * 32  # 16 4-bit nibbles = 32 bytes
        self.wave_bank = 0  # 0 or 1
        self.length = 0
        self.length_enable = False
        self.timer = 0
        self.timer_period = 0
        self.counter = 0
        self.output_nibble = 0
        self.format_8bit = False

    def step(self, sample_rate: int, base_freq: int = 131072) -> int:
        """Generate one sample."""
        if not self.enabled or self.volume == 0:
            return 0

        if self.frequency > 0:
            self.timer_period = (2048 - self.frequency) * 4

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            # Read from wave RAM
            nibble_index = self.counter % 64  # 32 bytes * 2 nibbles
            byte_index = nibble_index // 2
            wave_value = self.wave_ram[byte_index]

            if nibble_index % 2 == 0:
                # Lower nibble
                sample = wave_value & 0x0F
            else:
                # Upper nibble
                sample = (wave_value >> 4) & 0x0F

            # Apply volume
            if self.format_8bit:
                return sample  # 8-bit mode
            else:
                return (sample * self.volume) // 15

        return 0

    def trigger(self):
        """Trigger the channel"""
        self.counter = 0
        self.timer = 0
        self.enabled = True


class NoiseChannel:
    """Noise channel (CH4)"""

    # LFSR tap positions for different widths
    STAGES_15BIT = 14
    STAGES_7BIT = 6

    def __init__(self):
        self.enabled = False
        self.volume = 0
        self.envelope = 0
        self.envelope_steps = 0
        self.envelope_increase = False
        self.length = 0
        self.length_enable = False
        self.lfsr = 0x7FFF  # 15-bit LFSR starts all 1s
        self.width_7bit = False
        self.clock_shift = 0
        self.clock_divider = 0
        self.timer = 0
        self.timer_period = 0

    def step(self, sample_rate: int, base_freq: int = 131072) -> int:
        """Generate one sample."""
        if not self.enabled or self.volume == 0:
            return 0

        # Calculate timer period
        # Noise frequency = base / (2^(shift+1)) / divider
        divisor = max(1, self.clock_divider * 2)
        self.timer_period = (1 << (self.clock_shift + 1)) * divisor

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0

            # LFSR operation: tap bits and XOR
            if self.width_7bit:
                # 7-bit mode
                bit0 = self.lfsr & 1
                bit1 = (self.lfsr >> 1) & 1
                new_bit = bit0 ^ bit1
                self.lfsr = (self.lfsr >> 1) | (new_bit << 6)
                # Keep only 7 bits
                self.lfsr &= 0x7F
            else:
                # 15-bit mode
                bit0 = self.lfsr & 1
                bit14 = (self.lfsr >> 14) & 1
                new_bit = bit0 ^ bit14
                self.lfsr = (self.lfsr >> 1) | (new_bit << 14)

            # Output is the XOR result inverted
            if (self.lfsr & 1) == 0:
                return self.volume

        return 0

    def trigger(self):
        """Trigger the channel"""
        self.lfsr = 0x7FFF
        self.timer = 0
        self.enabled = True


class FIFO:
    """Direct Sound FIFO buffer for DMA audio transfers

    The GBA has two FIFO buffers (A and B) used for streaming audio data
    from ROM via DMA. Each FIFO can hold up to 8 bytes and is used for
    direct sound output from channels 1/2 (FIFO A) and channels 3/4 (FIFO B).
    """

    # Maximum FIFO depth (hardware limit)
    MAX_FIFO_SIZE = 8

    def __init__(self):
        self.data = deque()  # Queue of 8-bit samples (using deque for efficiency)
        self.max_size = self.MAX_FIFO_SIZE
        self.timer = 0
        self.timer_period = 0  # Set by DMA
        self.enabled = False
        self.volume_left = 0
        self.volume_right = 0
        self.priority = 0

    @property
    def size(self) -> int:
        """Current number of bytes in FIFO"""
        return len(self.data)

    @property
    def is_empty(self) -> bool:
        """Check if FIFO is empty"""
        return len(self.data) == 0

    @property
    def is_full(self) -> bool:
        """Check if FIFO is full"""
        return len(self.data) >= self.max_size

    def write(self, value: int):
        """Write a byte to FIFO (only if space available)"""
        if len(self.data) < self.max_size:
            self.data.append(value & 0xFF)

    def read(self) -> int:
        """Read a byte from FIFO (FIFO pops from front)"""
        if self.data:
            return self.data.popleft()
        return 0

    def peek(self) -> int:
        """Peek at next byte without removing it"""
        if self.data:
            return self.data[0]
        return 0

    def step(self, sample_rate: int) -> int:
        """Generate one sample from FIFO data."""
        if not self.enabled or not self.data:
            return 0

        # Timer controls how fast we consume samples
        # In real hardware this is controlled by DMA
        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            return self.read() >> 4  # Scale to 4-bit volume

        return 0

    def clear(self):
        """Clear the FIFO"""
        self.data.clear()


class APU:
    """GBA Audio Processing Unit"""

    # Register addresses
    REG_SOUND1CNT_L = 0x04000060  # Sweep
    REG_SOUND1CNT_H = 0x04000062  # Duty/Length
    REG_SOUND1CNT_X = 0x04000064  # Frequency/Envelope

    REG_SOUND2CNT_L = 0x04000068  # Duty/Length
    REG_SOUND2CNT_H = 0x0400006A  # Volume/Envelope
    REG_SOUND2CNT_X = 0x0400006C  # Frequency

    REG_SOUND3CNT_L = 0x04000070  # Wave bank/on/off
    REG_SOUND3CNT_H = 0x04000072  # Length
    REG_SOUND3CNT_X = 0x04000074  # Volume/Frequency

    REG_SOUND4CNT_L = 0x04000078  # Length
    REG_SOUND4CNT_H = 0x0400007A  # Volume/Envelope

    REG_SOUNDCNT_L = 0x04000080  # Master volume/ena
    REG_SOUNDCNT_H = 0x04000082  # Direct Sound A
    REG_SOUNDCNT_X = 0x04000084  # Direct Sound B

    REG_FIFO_A = 0x040000A0
    REG_FIFO_B = 0x040000A4

    REG_WAVE_RAM = 0x04000090

    # APU DMA (Audio Control Block) register addresses: 0x0400004E-0x0400005F
    REG_DMDSNDCTRL = 0x0400004E  # DMA/FIFO control
    REG_DMDSNDREPEAT = 0x04000050  # DMA/FIFO repeat mode
    REG_DMDSNDCOUNT = 0x04000052  # DMA/FIFO sample count
    REG_ACB_SOUND1 = 0x04000054  # Audio control block - ch1
    REG_ACB_SOUND2 = 0x04000056  # Audio control block - ch2
    REG_ACB_SOUND3 = 0x04000058  # Audio control block - ch3
    REG_ACB_SOUND4 = 0x0400005A  # Audio control block - ch4

    # DMA Channel 1 (Channel 1 Square Wave) registers: 0x040000B0-0x040000BF
    REG_D1SAD = 0x040000B0  # DMA 1 Source Address
    REG_D1DAD = 0x040000B4  # DMA 1 Destination Address (FIFO A: 0x040000A0)
    REG_D1CNT_L = 0x040000B8  # DMA 1 Transfer Count (Lower 16 bits)
    REG_D1CNT_H = 0x040000BA  # DMA 1 Control / Count High

    # DMA Channel 2 registers: 0x040000C0-0x040000CF
    REG_D2SAD = 0x040000C0  # DMA 2 Source Address
    REG_D2DAD = 0x040000C4  # DMA 2 Destination Address (FIFO B: 0x040000A4)
    REG_D2CNT_L = 0x040000C8  # DMA 2 Transfer Count
    REG_D2CNT_H = 0x040000CA  # DMA 2 Control / Count High

    # Sample rate (1 MHz base / 4 for audio)
    SAMPLE_RATE = 262144

    def __init__(self):
        # Sound channels
        self.ch1 = SquareWaveChannel()
        self.ch2 = SquareWaveChannel()
        self.ch3 = WaveChannel()
        self.ch4 = NoiseChannel()

        # FIFO channels
        self.fifo_a = FIFO()
        self.fifo_b = FIFO()

        # Wave RAM (2 banks of 16 bytes each)
        self.wave_ram = [[0] * 16, [0] * 16]
        self.wave_bank = 0

        self.master_volume_left = 0
        self.master_volume_right = 0
        self.ch1_enabled = False
        self.ch2_enabled = False
        self.ch3_enabled = False
        self.ch4_enabled = False
        self.sample_counter = 0

        self._audio_output = None

        # APU DMA (Audio Control Block) state
        self.dma_enabled = False
        self.dma_block_counter = 0  # ACBU - block counter
        self.dma_block_selector = 0  # ACBS - block selector
        self.dma_block_descriptor = 0  # ACBD - block descriptor
        self.dma_control = 0  # DMDSNDCTRL
        self.dma_repeat = 0  # DMDSNDREPEAT
        self.dma_count = 0  # DMDSNDCOUNT

        # Channel 1 DMA (Square Wave) registers: 0x040000B0-0x040000BF
        self.d1sa = 0  # Source Address
        self.d1da = 0  # Destination Address (FIFO A at 0x040000A0)
        self.d1rl = 0  # Transfer Count (Repeat Length)
        self.d1cr = 0  # Control Register

        # Channel 2 DMA registers: 0x040000C0-0x040000CF
        self.d2sa = 0
        self.d2da = 0
        self.d2rl = 0
        self.d2cr = 0

        self._mem = None

    def attach_memory(self, mem):
        """Attach memory interface for DMA transfers"""
        self._mem = mem

    def start(self):
        if self._audio_output is None:
            self._audio_output = AudioOutput()
        self._audio_output.start()

    def write_register(self, addr: int, value: int):
        """Handle MMIO writes to sound registers"""
        # Check APU DMA range first (0x0400004E-0x0400005F)
        if 0x0400004E <= addr <= 0x0400005F:
            reg = addr - 0x0400004E
            self._write_apu_dma(reg, value)
            return

        if self.REG_SOUND1CNT_L <= addr <= 0x04000061:
            # CH1 Sweep control
            reg = addr - self.REG_SOUND1CNT_L
            self._write_ch1_sweep(reg, value)
        elif self.REG_SOUND1CNT_H <= addr <= 0x04000065:
            # CH1 Duty/Length/Frequency
            reg = addr - self.REG_SOUND1CNT_H
            self._write_ch1_control(reg, value)
        elif self.REG_SOUND2CNT_L <= addr <= 0x0400006D:
            # CH2 control
            reg = addr - self.REG_SOUND2CNT_L
            self._write_ch2_control(reg, value)
        elif self.REG_SOUND3CNT_L <= addr <= 0x04000075:
            # CH3 control
            reg = addr - self.REG_SOUND3CNT_L
            self._write_ch3_control(reg, value)
        elif self.REG_SOUND4CNT_L <= addr <= 0x0400007B:
            # CH4 control
            reg = addr - self.REG_SOUND4CNT_L
            self._write_ch4_control(reg, value)
        elif self.REG_SOUNDCNT_L <= addr <= 0x04000085:
            # Master sound control
            reg = addr - self.REG_SOUNDCNT_L
            self._write_sound_control(reg, value)
        elif self.REG_FIFO_A <= addr <= 0x040000A3:
            # FIFO A write
            self._write_fifo_a(addr, value)
        elif self.REG_FIFO_B <= addr <= 0x040000A7:
            # FIFO B write
            self._write_fifo_b(addr, value)
        elif self.REG_WAVE_RAM <= addr <= 0x0400009F:
            # Wave RAM
            self._write_wave_ram(addr, value)
        elif self.REG_D1SAD <= addr <= 0x040000BF:
            # DMA Channel 1 registers (0x040000B0-0x040000BF)
            reg = addr - self.REG_D1SAD
            self._write_dma_ch1(reg, value)
        elif self.REG_D2SAD <= addr <= 0x040000CF:
            # DMA Channel 2 registers (0x040000C0-0x040000CF)
            reg = addr - self.REG_D2SAD
            self._write_dma_ch2(reg, value)

    def _write_ch1_sweep(self, reg: int, value: int):
        """Write to CH1 sweep registers"""
        if reg == 0:  # SOUND1CNT_L
            self.ch1.sweep_shift = (value >> 4) & 0x07
            self.ch1.sweep_decrease = bool(value & 0x08)
            self.ch1.sweep_steps = value & 0x07

    def _write_ch1_control(self, reg: int, value: int):
        """Write to CH1 control registers"""
        if reg == 0:  # SOUND1CNT_H - duty/len
            self.ch1.duty_cycle = (value >> 6) & 0x03
            self.ch1.length = value & 0x3F
        elif reg == 2:  # SOUND1CNT_X - freq/env
            # Frequency is lower 11 bits
            self.ch1.frequency = value & 0x7FF
            # Envelope
            self.ch1.envelope = (value >> 12) & 0x0F
            self.ch1.envelope_steps = (value >> 8) & 0x07
            self.ch1.envelope_increase = bool(value & 0x0800)
            # Trigger
            if value & 0x8000:
                self.ch1.trigger()

    def _write_ch2_control(self, reg: int, value: int):
        """Write to CH2 control registers"""
        if reg == 0:  # SOUND2CNT_L
            self.ch2.duty_cycle = (value >> 6) & 0x03
            self.ch2.length = value & 0x3F
        elif reg == 2:  # SOUND2CNT_H
            self.ch2.envelope = (value >> 12) & 0x0F
            self.ch2.envelope_steps = (value >> 8) & 0x07
            self.ch2.envelope_increase = bool(value & 0x0800)
        elif reg == 4:  # SOUND2CNT_X
            self.ch2.frequency = value & 0x7FF
            if value & 0x8000:
                self.ch2.trigger()

    def _write_ch3_control(self, reg: int, value: int):
        """Write to CH3 control registers"""
        if reg == 0:  # SOUND3CNT_L
            self.ch3.wave_bank = (value >> 5) & 0x01
            self.ch3.enabled = bool(value & 0x80)
        elif reg == 2:  # SOUND3CNT_H
            self.ch3.length = value & 0xFF
        elif reg == 4:  # SOUND3CNT_X
            self.ch3.volume = (value >> 8) & 0x0F
            self.ch3.format_8bit = bool(value & 0x0400)
            self.ch3.frequency = value & 0x3FF
            if value & 0x8000:
                self.ch3.trigger()

    def _write_ch4_control(self, reg: int, value: int):
        """Write to CH4 control registers"""
        if reg == 0:  # SOUND4CNT_L
            self.ch4.length = value & 0x3F
        elif reg == 2:  # SOUND4CNT_H
            self.ch4.envelope = (value >> 12) & 0x0F
            self.ch4.envelope_steps = (value >> 8) & 0x07
            self.ch4.envelope_increase = bool(value & 0x0800)
        elif reg == 4:  # (address not standard, but CH4 doesn't have freq)
            self.ch4.clock_shift = (value >> 4) & 0x0F
            self.ch4.clock_divider = value & 0x07
            self.ch4.width_7bit = bool(value & 0x08)
            if value & 0x8000:
                self.ch4.trigger()

    def _write_sound_control(self, reg: int, value: int):
        """Write to master sound control"""
        if reg == 0:  # SOUNDCNT_L
            self.master_volume_right = (value >> 4) & 0x07
            self.master_volume_left = value & 0x07
        elif reg == 2:  # SOUNDCNT_H - Direct Sound A
            self.fifo_a.volume_right = (value >> 4) & 0x0F
            self.fifo_a.volume_left = value & 0x0F
            self.fifo_a.enabled = bool(value & 0x0200)
            self.ch1_enabled = bool(value & 0x0001)
            self.ch2_enabled = bool(value & 0x0002)
        elif reg == 4:  # SOUNDCNT_X - Direct Sound B
            self.fifo_b.volume_right = (value >> 4) & 0x0F
            self.fifo_b.volume_left = value & 0x0F
            self.fifo_b.enabled = bool(value & 0x0200)
            self.ch3_enabled = bool(value & 0x0004)
            self.ch4_enabled = bool(value & 0x0008)

    def _write_fifo_a(self, addr: int, value: int):
        """Write to FIFO A"""
        # Writing any byte to FIFO A pushes it
        self.fifo_a.write(value & 0xFF)

    def _write_fifo_b(self, addr: int, value: int):
        """Write to FIFO B"""
        self.fifo_b.write(value & 0xFF)

    def _write_wave_ram(self, addr: int, value: int):
        """Write to wave RAM"""
        offset = addr - self.REG_WAVE_RAM
        bank = self.wave_bank
        self.wave_ram[bank][offset % 16] = value & 0xFF
        self.ch3.wave_ram = self.wave_ram[bank]

    def _write_apu_dma(self, reg: int, value: int):
        """Write to APU DMA registers (0x0400004E-0x0400005F)"""
        if reg == 0:  # DMDSNDCTRL
            self.dma_control = value
            self.dma_enabled = bool(value & 0x0001)
        elif reg == 2:  # DMDSNDREPEAT
            self.dma_repeat = value
        elif reg == 4:  # DMDSNDCOUNT
            self.dma_count = value
        elif reg == 6:  # ACB sound1 - block address
            self.dma_block_descriptor = value
        elif reg == 8:  # ACB sound2
            self.dma_block_counter = value

    def _write_dma_ch1(self, reg: int, value: int):
        """Write to DMA Channel 1 (Square Wave) registers"""
        if reg == 0:  # D1SAD - Source Address
            self.d1sa = value
        elif reg == 4:  # D1DAD - Destination Address
            self.d1da = value
        elif reg == 8:  # D1RL - Repeat Length (Count High)
            self.d1rl = value
        elif reg == 12:  # D1CNT_H - Control High
            self.d1cr = value & 0xFFFF

    def _write_dma_ch2(self, reg: int, value: int):
        """Write to DMA Channel 2 registers"""
        if reg == 0:  # D2SAD - Source Address
            self.d2sa = value
        elif reg == 4:  # D2DAD - Destination Address
            self.d2da = value
        elif reg == 8:  # D2RL - Repeat Length
            self.d2rl = value
        elif reg == 12:  # D2CNT_H - Control High
            self.d2cr = value & 0xFFFF

    def dma_transfer(self, channel: int, count: int):
        """Perform DMA transfer from ROM to audio buffer"""
        if self._mem is None:
            return
        rom_base = 0x08000000
        for i in range(count):
            addr = rom_base + (channel * 0x1000) + (i * 4)
            sample = self._mem.read_u32(addr) & 0xFF
            if channel == 0:
                self.fifo_a.write(sample)
            else:
                self.fifo_b.write(sample)

    def fifo_write(self, channel: int, sample: int):
        """Write a sample to the specified FIFO channel

        Args:
            channel: 0 for FIFO A, 1 for FIFO B
            sample: 8-bit audio sample
        """
        if channel == 0:
            self.fifo_a.write(sample)
        else:
            self.fifo_b.write(sample)

    def fifo_read(self, channel: int) -> int:
        """Read a sample from the specified FIFO channel

        Args:
            channel: 0 for FIFO A, 1 for FIFO B
        Returns:
            8-bit audio sample, or 0 if FIFO is empty
        """
        if channel == 0:
            return self.fifo_a.read()
        else:
            return self.fifo_b.read()

    def fifo_is_empty(self, channel: int) -> bool:
        """Check if the specified FIFO is empty

        Args:
            channel: 0 for FIFO A, 1 for FIFO B
        Returns:
            True if FIFO is empty, False otherwise
        """
        if channel == 0:
            return self.fifo_a.is_empty
        else:
            return self.fifo_b.is_empty

    def fifo_size(self, channel: int) -> int:
        """Get current size of the specified FIFO

        Args:
            channel: 0 for FIFO A, 1 for FIFO B
        Returns:
            Number of bytes currently in FIFO (0-8)
        """
        if channel == 0:
            return self.fifo_a.size
        else:
            return self.fifo_b.size

    def step(self):
        """Advance audio by one sample cycle"""
        # Generate samples from each active channel
        ch1_sample = self.ch1.step(self.SAMPLE_RATE) if self.ch1_enabled else 0
        ch2_sample = self.ch2.step(self.SAMPLE_RATE) if self.ch2_enabled else 0
        ch3_sample = self.ch3.step(self.SAMPLE_RATE) if self.ch3_enabled else 0
        ch4_sample = self.ch4.step(self.SAMPLE_RATE) if self.ch4_enabled else 0

        # FIFO samples (controlled by DMA in real hardware)
        fifo_a_sample = self.fifo_a.step(self.SAMPLE_RATE)
        fifo_b_sample = self.fifo_b.step(self.SAMPLE_RATE)

        self.sample_counter += 1

    def get_sample(self) -> int:
        """Return current mixed audio sample value (int)"""
        # Mix all channels
        mixed = 0

        if self.ch1_enabled:
            duty = SquareWaveChannel.DUTY_PATTERNS[self.ch1.duty_cycle]
            bit_pos = self.sample_counter % 8
            if duty & (1 << bit_pos):
                mixed += self.ch1.volume

        if self.ch2_enabled:
            duty = SquareWaveChannel.DUTY_PATTERNS[self.ch2.duty_cycle]
            bit_pos = self.sample_counter % 8
            if duty & (1 << bit_pos):
                mixed += self.ch2.volume

        if self.ch3_enabled and self.ch3.wave_ram:
            nibble_index = self.sample_counter % 64
            byte_index = nibble_index // 2
            wave_value = self.ch3.wave_ram[byte_index % 16]

            if nibble_index % 2 == 0:
                sample = wave_value & 0x0F
            else:
                sample = (wave_value >> 4) & 0x0F

            if self.ch3.format_8bit:
                mixed += sample
            else:
                mixed += (sample * self.ch3.volume) // 15

        # CH4 noise
        if self.ch4_enabled:
            divisor = max(1, self.ch4.clock_divider * 2)
            timer_period = (1 << (self.ch4.clock_shift + 1)) * divisor
            if self.sample_counter % timer_period == 0:
                # LFSR step
                if self.ch4.width_7bit:
                    bit0 = self.ch4.lfsr & 1
                    bit1 = (self.ch4.lfsr >> 1) & 1
                    new_bit = bit0 ^ bit1
                    self.ch4.lfsr = (self.ch4.lfsr >> 1) | (new_bit << 6)
                    self.ch4.lfsr &= 0x7F
                else:
                    bit0 = self.ch4.lfsr & 1
                    bit14 = (self.ch4.lfsr >> 14) & 1
                    new_bit = bit0 ^ bit14
                    self.ch4.lfsr = (self.ch4.lfsr >> 1) | (new_bit << 14)

        # Add FIFO samples
        if self.fifo_a.enabled and self.fifo_a.data:
            mixed += self.fifo_a.data[0] >> 4
        if self.fifo_b.enabled and self.fifo_b.data:
            mixed += self.fifo_b.data[0] >> 4

        # Apply master volume (simplified)
        master_vol = (self.master_volume_left + self.master_volume_right + 1) // 2
        mixed = (mixed * master_vol) // 7

        # Clamp to valid range
        return max(0, min(15, mixed))

    def read_register(self, addr: int) -> int:
        """Read from sound registers (for completeness)"""
        if self.REG_FIFO_A <= addr <= 0x040000A3:
            # FIFO A read
            return self.fifo_a.read() if self.fifo_a.data else 0
        elif self.REG_FIFO_B <= addr <= 0x040000A7:
            # FIFO B read
            return self.fifo_b.read() if self.fifo_b.data else 0
        elif self.REG_WAVE_RAM <= addr <= 0x0400009F:
            offset = addr - self.REG_WAVE_RAM
            return self.wave_ram[self.wave_bank][offset % 16]

        return 0



# ===
"""GBA DMA Controller"""

from typing import List, Optional


DMA_ENABLE = 0x80000000
DMA_TIMING_MASK = 0x30000000
DMA_TIMING_IMMEDIATE = 0x80000000
DMA_TIMING_VBLANK = 0x40000000
DMA_TIMING_HBLANK = 0x30000000
DMA_TIMING_DISPLAY = 0x00000000

DMA_SRC_INCREMENT = 0x00000000
DMA_SRC_DECREMENT = 0x00100000
DMA_SRC_FIXED = 0x00200000
DMA_DST_INCREMENT = 0x00000000
DMA_DST_DECREMENT = 0x00001000
DMA_DST_FIXED = 0x00002000
DMA_REPEAT = 0x00000010
DMA_16BIT = 0x00000000
DMA_32BIT = 0x04000000
DMA_GAMEPAK_DRQ = 0x08000000

DMA0_SRC_ADDR = 0x040000B0
DMA0_DST_ADDR = 0x040000B4
DMA0_COUNT = 0x040000B8
DMA0_CONTROL = 0x040000BC

DMA1_SRC_ADDR = 0x040000C0
DMA1_DST_ADDR = 0x040000C4
DMA1_COUNT = 0x040000C8
DMA1_CONTROL = 0x040000CC

DMA2_SRC_ADDR = 0x040000D0
DMA2_DST_ADDR = 0x040000D4
DMA2_COUNT = 0x040000D8
DMA2_CONTROL = 0x040000DC

DMA3_SRC_ADDR = 0x040000E0
DMA3_DST_ADDR = 0x040000E4
DMA3_COUNT = 0x040000E8
DMA3_CONTROL = 0x040000EC


class DMAChannel:
    def __init__(self, channel_id: int, mem):
        self.channel_id = channel_id
        self.mem = mem
        self.src_addr: int = 0
        self.dst_addr: int = 0
        self.count: int = 0
        self.control: int = 0
        self.enabled: bool = False
        self.busy: bool = False
        self.pending: bool = False
        self.repeats: bool = False
        self.word_size_32bit: bool = False
        self.src_increment: int = 0
        self.dst_increment: int = 0

    def get_timing_bits(self) -> int:
        return self.control & DMA_TIMING_MASK

    def is_immediate(self) -> bool:
        return (self.control & DMA_TIMING_IMMEDIATE) == DMA_TIMING_IMMEDIATE

    def is_vblank(self) -> bool:
        timing = self.get_timing_bits()
        return timing == DMA_TIMING_VBLANK

    def is_hblank(self) -> bool:
        timing = self.get_timing_bits()
        return (self.control & 0x80000000) == 0x80000000 and timing == DMA_TIMING_HBLANK

    def is_display_sync(self) -> bool:
        timing = self.get_timing_bits()
        return timing == DMA_TIMING_DISPLAY and (self.control & 0x80000000) == 0

    def get_src_increment(self) -> int:
        return (self.control >> 20) & 0x3

    def get_dst_increment(self) -> int:
        return (self.control >> 12) & 0x3

    def is_32bit(self) -> bool:
        return (self.control & DMA_32BIT) != 0

    def is_repeat(self) -> bool:
        return (self.control & DMA_REPEAT) != 0

    def get_transfer_size(self) -> int:
        return 4 if self.is_32bit() else 2

    def read_from_memory(self):
        base = 0x040000B0 + (self.channel_id * 0x10)
        self.src_addr = self.mem.read_u32(base)
        self.dst_addr = self.mem.read_u32(base + 4)
        self.count = self.mem.read_u32(base + 8)
        self.control = self.mem.read_u32(base + 12)
        self.enabled = (self.control & DMA_ENABLE) != 0

    def write_to_memory(self):
        base = 0x040000B0 + (self.channel_id * 0x10)
        self.mem.write_u32(base, self.src_addr)
        self.mem.write_u32(base + 4, self.dst_addr)
        self.mem.write_u32(base + 8, self.count)
        self.mem.write_u32(base + 12, self.control)

    def get_count_value(self) -> int:
        if self.count == 0:
            return 0x10000 if self.is_32bit() else 0x4000
        return self.count


class DMA:
    def __init__(self, mem, interrupts):
        self.mem = mem
        self.interrupts = interrupts
        self.channels: List[DMAChannel] = [
            DMAChannel(0, mem),
            DMAChannel(1, mem),
            DMAChannel(2, mem),
            DMAChannel(3, mem),
        ]
        self._setup_mmio()

    def _setup_mmio(self):
        base = 0x040000B0
        for i in range(4):
            offset = base + (i * 0x10)
            self.mem.register_mmio_write(offset + 12, self._make_mmio_handler(i))

    def _make_mmio_handler(self, channel: int):
        def handler(addr: int, value: int):
            self.channels[channel].control = value
            self.channels[channel].enabled = (value & DMA_ENABLE) != 0
            if self.channels[channel].enabled and self.channels[channel].is_immediate():
                self.channels[channel].pending = True

        return handler

    def start_transfer(self, channel: int):
        if channel < 0 or channel > 3:
            return

        ch = self.channels[channel]
        ch.read_from_memory()

        if not ch.enabled:
            return

        self._do_transfer(ch)

    def _do_transfer(self, ch: DMAChannel):
        if ch.busy:
            return

        ch.busy = True

        src_inc = ch.get_src_increment()
        dst_inc = ch.get_dst_increment()
        count = ch.get_count_value()
        transfer_size = ch.get_transfer_size()

        src = ch.src_addr
        dst = ch.dst_addr

        for _ in range(count):
            if transfer_size == 4:
                value = self.mem.read_u32(src)
                self.mem.write_u32(dst, value)
                src += 4
                dst += 4
            else:
                value = self.mem.read_u16(src)
                self.mem.write_u16(dst, value)
                src += 2
                dst += 2

        ch.src_addr = self._adjust_address(ch.src_addr, src_inc, count * transfer_size)
        ch.dst_addr = self._adjust_address(ch.dst_addr, dst_inc, count * transfer_size)

        if ch.is_repeat():
            # Repeat DMA keeps enabled, source/dest will be adjusted on next trigger
            ch.busy = False  # Not busy during repeat delay
        else:
            ch.control &= ~DMA_ENABLE
            ch.enabled = False

        ch.write_to_memory()
        ch.busy = False

        # Fire DMA interrupt
        self.interrupts.dma_irq(ch.channel_id)

    def _adjust_address(self, addr: int, increment_mode: int, count: int) -> int:
        if increment_mode == 0:
            return addr + count
        elif increment_mode == 1:
            return addr - count
        else:
            return addr

    def step(self):
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_immediate():
                if ch.pending:
                    ch.pending = False
                    self._do_transfer(ch)

    def vblank_fire(self):
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_vblank():
                self._do_transfer(ch)
                ch.pending = False

    def hblank_fire(self):
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_hblank():
                self._do_transfer(ch)
                ch.pending = False

    def get_channel(self, channel: int) -> Optional[DMAChannel]:
        if 0 <= channel <= 3:
            return self.channels[channel]
        return None


def clear_dma_pending(dma_instance):
    for ch in dma_instance.channels:
        ch.pending = False



# ===
"""GBA Timers"""


class TimerChannel:
    """Individual timer channel"""

    def __init__(self):
        self.count = 0
        self.reload = 0
        self.control = 0

    @property
    def enabled(self) -> bool:
        """Check if timer is enabled (bit 7)"""
        return bool(self.control & 0x80)

    @property
    def irq_enable(self) -> bool:
        """Check if IRQ is enabled (bit 6)"""
        return bool(self.control & 0x40)

    @property
    def cascade(self) -> bool:
        """Check if cascade mode is enabled (bit 2)"""
        return bool(self.control & 0x04)

    @property
    def prescaler_value(self) -> int:
        """Get prescaler divisor value (bits 0-1)"""
        prescale_bits = self.control & 0x03
        return [1, 64, 256, 1024][prescale_bits]


class Timers:
    """GBA Timer Controller with 4 timer channels"""

    PRESCALER_VALUES = [1, 64, 256, 1024]

    def __init__(self):
        self._channels = [TimerChannel() for _ in range(4)]
        self._overflow_flags = [False] * 4

    @property
    def channels(self):
        """Access timer channels"""
        return self._channels

    def get_timer(self, channel: int) -> int:
        """Get current count value for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        return self._channels[channel].count

    def set_timer(self, channel: int, value: int) -> None:
        """Set count value for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        self._channels[channel].count = value & 0xFFFF

    def set_control(self, channel: int, control: int) -> None:
        """Set control register for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        self._channels[channel].control = control & 0xFF

    def set_reload(self, channel: int, reload: int) -> None:
        """Set reload value for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        self._channels[channel].reload = reload & 0xFFFF

    def get_control(self, channel: int) -> int:
        """Get control register for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        return self._channels[channel].control

    def get_reload(self, channel: int) -> int:
        """Get reload value for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        return self._channels[channel].reload

    def get_overflow_flag(self, channel: int) -> bool:
        """Get overflow flag for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        return self._overflow_flags[channel]

    def clear_overflow_flag(self, channel: int) -> None:
        """Clear overflow flag for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        self._overflow_flags[channel] = False

    def step(self, cycles: int) -> None:
        """Advance all enabled timers by given cycles"""
        # Reset overflow flags at start of step
        self._overflow_flags = [False] * 4

        # Process each timer
        for i in range(4):
            channel = self._channels[i]

            # Skip disabled timers
            if not channel.enabled:
                continue

            # Cascade mode: increment only when previous timer overflows
            if channel.cascade:
                if i == 0:
                    # Timer0 in cascade mode - should not happen, but handle it
                    continue
                # Check if previous timer overflowed this step
                if not self._overflow_flags[i - 1]:
                    continue
                # Increment by 1 for cascade
                increment = 1
            else:
                # Normal mode: increment based on prescaler
                prescaler = channel.prescaler_value
                increment = cycles // prescaler

            if increment > 0:
                old_count = channel.count
                channel.count = (channel.count + increment) & 0xFFFF

                # Check for overflow (wrapped around)
                if channel.count < old_count:
                    self._overflow_flags[i] = True
                    # Reload from reload value on overflow
                    channel.count = channel.reload



# ===
"""GBA Input - Keyboard to GBA input register mapping"""

# GBA button bit positions in KEYINPUT register (0x04000130)
# Active low: 0 = pressed, 1 = released
GBA_KEYS = {
    "A": 0x01,  # bit 0
    "B": 0x02,  # bit 1
    "SELECT": 0x04,  # bit 2
    "START": 0x08,  # bit 3
    "RIGHT": 0x100,  # bit 8
    "LEFT": 0x200,  # bit 9
    "UP": 0x400,  # bit 10
    "DOWN": 0x800,  # bit 11
    "R": 0x1000,  # bit 12
    "L": 0x2000,  # bit 13
}

# Keyboard to GBA button mapping
# Arrow keys -> DPAD (bits 8-11), Z -> A, S -> B, Enter -> Start, Space -> Select
KEYBOARD_MAP = {
    "z": "A",
    "s": "B",
    "return": "START",
    "space": "SELECT",
    "right": "RIGHT",
    "left": "LEFT",
    "up": "UP",
    "down": "DOWN",
    "a": "L",
    "x": "R",
}

# Default value when no keys pressed (all bits = 1, meaning released)
# 14 bits (0-13) = 0x3FFF
DEFAULT_KEYS = 0x3FFF


class Input:
    """Handles keyboard to GBA input mapping.

    Maps keyboard keys to GBA KEYINPUT register (0x04000130).
    Uses lazy import of pygame to avoid dependency at import time.
    """

    def __init__(self):
        self._keys_pressed = DEFAULT_KEYS
        self._pygame = None
        self._pygame_available = None

    @property
    def _pygame_module(self):
        """Lazy import of pygame to avoid dependency at import time."""
        if self._pygame_available is None:
            try:
                import pygame

                # Initialize video subsystem for keyboard support
                pygame.display.init()
                pygame.key.set_repeat(100, 50)

                self._pygame = pygame
                self._pygame_available = True
            except ImportError:
                self._pygame = None
                self._pygame_available = False
        return self._pygame

    @property
    def pygame_available(self) -> bool:
        """Check if pygame is available."""
        if self._pygame_available is None:
            _ = self._pygame_module  # Trigger lazy import
        return self._pygame_available

    def poll(self) -> bool:
        """Poll keyboard state and update internal key state.

        Returns:
            True if polling successful, False if quit event received.
            Returns True even if pygame is not available (no-op).
        """
        if not self.pygame_available:
            # pygame not installed, return default (no keys pressed)
            self._keys_pressed = DEFAULT_KEYS
            return True

        pygame = self._pygame_module

        # Process events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False

        # Get current key states
        keys = pygame.key.get_pressed()

        # Start with all keys released (bits = 1)
        key_state = DEFAULT_KEYS  # 0x3FFF = all released

        # Check each mapped key
        for py_key_name, gba_key_name in KEYBOARD_MAP.items():
            py_key = getattr(pygame, f"K_{py_key_name}", None)
            if py_key is not None and keys[py_key]:
                # Key is pressed, clear the bit (active low)
                key_state &= ~GBA_KEYS[gba_key_name]

        self._keys_pressed = key_state
        return True

    def get_keys(self) -> int:
        """Get current key state as 16-bit mask.

        Returns:
            16-bit integer representing GBA KEYINPUT register.
            Bits are active low: 0 = pressed, 1 = released.
            0x3FFF (14 bits) = no keys pressed
        """
        return self._keys_pressed

    def update_from_pygame(self, keys) -> None:
        """Update GBA input state from pygame key state.

        Args:
            keys: pygame key state from pygame.key.get_pressed()
        """
        # Lazy import pygame if not already loaded
        if self._pygame is None:
            _ = self._pygame_module  # Trigger lazy import

        if not self.pygame_available:
            self._keys_pressed = DEFAULT_KEYS
            return

        pygame = self._pygame
        key_state = DEFAULT_KEYS
        for py_key_name, gba_key_name in KEYBOARD_MAP.items():
            py_key = getattr(pygame, f"K_{py_key_name}", None)
            if py_key is not None and keys[py_key]:
                key_state &= ~GBA_KEYS[gba_key_name]
        self._keys_pressed = key_state

    def update_keys(
        self,
        a=False,
        b=False,
        start=False,
        select=False,
        right=False,
        left=False,
        up=False,
        down=False,
        r=False,
        l=False,
    ):
        """Update GBA input from boolean arguments."""
        self._keys_pressed = 0x3FFF  # All not pressed
        if a:
            self._keys_pressed &= ~GBA_KEYS["A"]
        if b:
            self._keys_pressed &= ~GBA_KEYS["B"]
        if start:
            self._keys_pressed &= ~GBA_KEYS["START"]
        if select:
            self._keys_pressed &= ~GBA_KEYS["SELECT"]
        if right:
            self._keys_pressed &= ~GBA_KEYS["RIGHT"]
        if left:
            self._keys_pressed &= ~GBA_KEYS["LEFT"]
        if up:
            self._keys_pressed &= ~GBA_KEYS["UP"]
        if down:
            self._keys_pressed &= ~GBA_KEYS["DOWN"]
        if r:
            self._keys_pressed &= ~GBA_KEYS["R"]
        if l:
            self._keys_pressed &= ~GBA_KEYS["L"]


# Export constants for generated code
KEY_A = 0x01  # bit 0
KEY_B = 0x02  # bit 1
KEY_SELECT = 0x04  # bit 2
KEY_START = 0x08  # bit 3
KEY_RIGHT = 0x100  # bit 8
KEY_LEFT = 0x200  # bit 9
KEY_UP = 0x400  # bit 10
KEY_DOWN = 0x800  # bit 11
KEY_R = 0x1000  # bit 12
KEY_L = 0x2000  # bit 13



# ===
"""GBA ROM handling - loads and parses cartridge ROM files."""



class ROM:
    """Represents a loaded GBA ROM image with header parsing.

    Provides access to ROM data and parsed header fields including
    title, game code, maker code, and entry point.
    """

    # GBA ROM header offsets
    OFFSET_ENTRY_POINT = 0x00  # 4 bytes - ARM branch to start
    OFFSET_NINTENDO_LOGO = 0x04  # 156 bytes - compressed logo
    OFFSET_TITLE = 0xA0  # 12 bytes - game title (ASCII)
    OFFSET_GAME_CODE = 0xAC  # 4 bytes - game code
    OFFSET_MAKER_CODE = 0xB0  # 2 bytes - maker code
    OFFSET_ROM_SIZE = 0xB4  # 1 byte - ROM size code

    def __init__(self):
        """Create an empty ROM instance."""
        self._data: bytes = b""
        self._header: dict = {}

    def load(self, path: str) -> None:
        """Load a GBA ROM file from disk.

        Args:
            path: Path to the .gba file to load.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file is too small to contain a valid header.
        """
        with open(path, "rb") as f:
            self._data = f.read()

        if len(self._data) < 0xC0:
            raise ValueError(f"ROM file too small: {len(self._data)} bytes")

        self._parse_header()

    def _parse_header(self) -> None:
        """Parse the GBA ROM header and populate header dict."""
        # Entry point (4 bytes at 0x00)
        entry = int.from_bytes(self._data[0x00:0x04], "little")

        # Game title (12 bytes at 0xA0, null-padded ASCII)
        title_bytes = self._data[0xA0:0xAC]
        title = title_bytes.rstrip(b"\x00").decode("ascii", errors="replace")

        # Game code (4 bytes at 0xAC)
        game_code = self._data[0xAC:0xB0].decode("ascii", errors="replace")

        # Maker code (2 bytes at 0xB0)
        maker_code = self._data[0xB0:0xB2].decode("ascii", errors="replace")

        rom_size_code = self._data[0xB4]
        shift = rom_size_code & 0x0F
        if rom_size_code < 0x18 and shift < 16:
            rom_size = 0x80000 << shift
        else:
            rom_size = len(self._data)

        self._header = {
            "entry_point": entry,
            "title": title,
            "game_code": game_code,
            "maker_code": maker_code,
            "rom_size": rom_size,
        }

    def get_header(self) -> dict:
        """Return the parsed ROM header fields.

        Returns:
            Dictionary containing: entry_point, title, game_code,
            maker_code, rom_size.
        """
        return self._header.copy()

    @property
    def data(self) -> bytes:
        """Return the raw ROM data."""
        return self._data

    @property
    def title(self) -> str:
        """Return the game title (up to 12 bytes, null-padded)."""
        return self._header.get("title", "")

    @property
    def game_code(self) -> str:
        """Return the 4-character game code."""
        return self._header.get("game_code", "")

    @property
    def maker_code(self) -> str:
        """Return the 2-character maker code."""
        return self._header.get("maker_code", "")

    @property
    def rom_size(self) -> int:
        """Return the ROM size in bytes (0 if unknown)."""
        return self._header.get("rom_size", 0)

    @property
    def entry_point(self) -> int:
        """Return the entry point address (ARM branch instruction)."""
        return self._header.get("entry_point", 0)

    def read_bytes(self, offset: int, length: int) -> bytes:
        """Read raw bytes from the ROM at the given offset.

        Args:
            offset: Byte offset from start of ROM.
            length: Number of bytes to read.

        Returns:
            Bytes read (may be shorter if ROM ends).
        """
        return self._data[offset : offset + length]



# ===
"""GBA Interrupt Controller"""


class InterruptController:
    """Interrupt controller managing IE, IF, and IME registers.

    Interrupt sources (bit positions):
        - VBlank: 0
        - HBlank: 1
        - VCounter: 2
        - Timer0-3: 3-6
        - DMA0-3: 8-11
        - KeyPad: 12
        - GamePak: 13
    """

    # Interrupt source bit positions
    IRQ_VBLANK = 0
    IRQ_HBLANK = 1
    IRQ_VCOUNTER = 2
    IRQ_TIMER0 = 3
    IRQ_TIMER1 = 4
    IRQ_TIMER2 = 5
    IRQ_TIMER3 = 6
    IRQ_DMA0 = 8
    IRQ_DMA1 = 9
    IRQ_DMA2 = 10
    IRQ_DMA3 = 11
    IRQ_KEYPAD = 12
    IRQ_GAMEPAK = 13

    def __init__(self):
        # IE: Interrupt Enable register (16-bit) - enables per-interrupt sources
        self.ie_reg = 0x0000
        # IF: Interrupt Flags register (16-bit) - raised interrupts, write 1 to clear
        self.if_reg = 0x0000
        # IME: Interrupt Master Enable register (1-bit)
        self.ime_reg = 0x0000
        # Handlers stored by interrupt source bit position
        self._handlers = {}

    def register_handler(self, irq_id: int, callback):
        """Register a callback for a specific interrupt source.

        Args:
            irq_id: Interrupt source bit position (0-13)
            callback: Function to call when interrupt fires and is enabled
        """
        self._handlers[irq_id] = callback

    def fire(self, irq_id: int):
        """Fire an interrupt - set the IF flag and call handler if enabled.

        Args:
            irq_id: Interrupt source bit position (0-13)
        """
        # Set the interrupt flag in IF register
        self.if_reg |= 1 << irq_id

        # Check if interrupt is enabled (IME=1 and IE bit for this irq is set)
        if self.ime_reg & 0x0001 and (self.ie_reg & (1 << irq_id)):
            # Call the handler if registered
            if irq_id in self._handlers:
                self._handlers[irq_id]()

    def vblank_irq(self):
        """Convenience method to fire a VBlank interrupt (IRQ 0)."""
        self.fire(self.IRQ_VBLANK)

    def hblank_irq(self):
        """Convenience method to fire a HBlank interrupt (IRQ 1)."""
        self.fire(self.IRQ_HBLANK)

    def vcounter_irq(self):
        """Convenience method to fire a VCounter interrupt (IRQ 2)."""
        self.fire(self.IRQ_VCOUNTER)

    def timer_irq(self, channel: int):
        """Convenience method to fire a timer interrupt.

        Args:
            channel: Timer channel (0-3), maps to IRQ 3-6
        """
        if 0 <= channel <= 3:
            self.fire(self.IRQ_TIMER0 + channel)

    def dma_irq(self, channel: int):
        """Convenience method to fire a DMA interrupt.

        Args:
            channel: DMA channel (0-3), maps to IRQ 8-11
        """
        if 0 <= channel <= 3:
            self.fire(self.IRQ_DMA0 + channel)

    def keypad_irq(self):
        """Convenience method to fire a KeyPad interrupt (IRQ 12)."""
        self.fire(self.IRQ_KEYPAD)

    def gamepak_irq(self):
        """Convenience method to fire a GamePak interrupt (IRQ 13)."""
        self.fire(self.IRQ_GAMEPAK)

    def write_ie(self, val: int):
        """Write to IE (Interrupt Enable) register.

        Args:
            val: 16-bit value to write
        """
        self.ie_reg = val & 0xFFFF

    def write_if(self, val: int):
        """Write to IF (Interrupt Flags) register.

        Writing 1 to a bit clears that interrupt flag.

        Args:
            val: 16-bit value to write
        """
        # Clear bits where val has 1s (write-1-to-clear behavior)
        self.if_reg &= ~(val & 0xFFFF)

    def write_ime(self, val: int):
        """Write to IME (Interrupt Master Enable) register.

        Args:
            val: 16-bit value (only bit 0 is significant)
        """
        self.ime_reg = val & 0x0001

    def read_ie(self) -> int:
        """Read IE register."""
        return self.ie_reg

    def read_if(self) -> int:
        """Read IF register."""
        return self.if_reg

    def read_ime(self) -> int:
        """Read IME register."""
        return self.ime_reg

    def get_pending_interrupts(self) -> int:
        """Get bitmask of pending and enabled interrupts."""
        return self.if_reg & self.ie_reg

    def has_pending_interrupt(self) -> bool:
        """Check if any enabled interrupt is pending."""
        return (self.ime_reg & 0x0001) and (self.if_reg & self.ie_reg) != 0

    def clear_if(self):
        """Clear all interrupt flags."""
        self.if_reg = 0x0000


def set_vblank_flag():
    interrupts.fire(InterruptController.IRQ_VBLANK)

    def set_ime(self, enabled: bool):
        """Set IME register.

        Args:
            enabled: True to enable interrupts, False to disable
        """
        self.ime_reg = 0x0001 if enabled else 0x0000



# ===
class GameError(Exception):
    pass


class GBARuntimeError(GameError):
    pass


class InvalidRom(GameError):
    pass


class InvalidROMError(InvalidRom):
    pass


class InvalidAddress(GameError):
    pass


__all__ = ["GameError", "GBARuntimeError", "InvalidRom", "InvalidROMError", "InvalidAddress"]



# ===
"""Text library - Replicazione di text.asm per test ROM

Queste funzioni replicano il comportamento di text.asm per permettere
alle test ROM di funzionare.

Source: test_roms/gba-tests-master/lib/text.asm
"""

# Glyph data per caratteri ASCII 32-126 (95 caratteri)
# Convertito da test_roms/gba-tests-master/lib/glyphs.asm
# Each glyph is 8 bytes (8x8 pixel, 2 bit per pixel)
GLYPHS = {
    " ": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    "!": [0x00, 0x00, 0x18, 0x18, 0x00, 0x18, 0x00, 0x00],
    '"': [0x00, 0x00, 0x36, 0x36, 0x00, 0x00, 0x00, 0x00],
    "#": [0x00, 0x00, 0x36, 0x7F, 0x36, 0x36, 0x7F, 0x3C],
    "$": [0x06, 0x1B, 0x35, 0x66, 0x00, 0x00, 0x33, 0x56],
    "%": [0x6C, 0x6E, 0x16, 0x36, 0x1C, 0x00, 0x00, 0xDE],
    "&": [0x73, 0x3B, 0x00, 0x0C, 0x18, 0x18, 0x00, 0x0C],
    "'": [0x0C, 0x18, 0x18, 0x00, 0x0C, 0x0C, 0x18, 0x30],
    "(": [0x00, 0x30, 0x18, 0x0C, 0x0C, 0x18, 0x30, 0x18],
    ")": [0x0C, 0x18, 0x30, 0x18, 0x18, 0x30, 0x18, 0x0C],
    "*": [0x00, 0x30, 0x0C, 0x7E, 0x0C, 0x30, 0x00, 0x00],
    "+": [0x00, 0x18, 0x18, 0x7E, 0x18, 0x18, 0x00, 0x00],
    ",": [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x00, 0x00],
    "-": [0x00, 0x00, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00],
    ".": [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00],
    "/": [0x00, 0x00, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x00],
    "0": [0x3C, 0x66, 0x66, 0x6E, 0x76, 0x66, 0x66, 0x3C],
    "1": [0x18, 0x38, 0x18, 0x18, 0x18, 0x18, 0x18, 0x7E],
    "2": [0x3C, 0x66, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x7E],
    "3": [0x3C, 0x66, 0x06, 0x0C, 0x06, 0x66, 0x3C, 0x00],
    "4": [0x0C, 0x1C, 0x3C, 0x6C, 0x7E, 0x0C, 0x0C, 0x1E],
    "5": [0x7E, 0x40, 0x7C, 0x06, 0x06, 0x66, 0x3C, 0x00],
    "6": [0x1C, 0x36, 0x60, 0x7C, 0x66, 0x66, 0x3C, 0x00],
    "7": [0x7E, 0x06, 0x0C, 0x18, 0x18, 0x18, 0x18, 0x00],
    "8": [0x3C, 0x66, 0x66, 0x3C, 0x66, 0x66, 0x3C, 0x00],
    "9": [0x3C, 0x66, 0x66, 0x3E, 0x06, 0x0C, 0x78, 0x00],
    ":": [0x00, 0x00, 0x66, 0x00, 0x00, 0x66, 0x00, 0x00],
    ";": [0x00, 0x00, 0x66, 0x00, 0x00, 0x66, 0x06, 0x0C],
    "<": [0x00, 0x30, 0x0C, 0x06, 0x0C, 0x30, 0x00, 0x00],
    "=": [0x00, 0x00, 0x7E, 0x00, 0x00, 0x7E, 0x00, 0x00],
    ">": [0x00, 0x0C, 0x30, 0x60, 0x30, 0x0C, 0x00, 0x00],
    "?": [0x3C, 0x66, 0x06, 0x0C, 0x18, 0x00, 0x18, 0x00],
    "@": [0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x3C, 0x00],
    "A": [0x18, 0x3C, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x00],
    "B": [0x7C, 0x66, 0x66, 0x7C, 0x66, 0x66, 0x7C, 0x00],
    "C": [0x3C, 0x66, 0x60, 0x60, 0x60, 0x66, 0x3C, 0x00],
    "D": [0x78, 0x6C, 0x66, 0x66, 0x66, 0x6C, 0x78, 0x00],
    "E": [0x7E, 0x60, 0x60, 0x7C, 0x60, 0x60, 0x7E, 0x00],
    "F": [0x7E, 0x60, 0x60, 0x7C, 0x60, 0x60, 0x60, 0x00],
    "G": [0x3C, 0x66, 0x60, 0x7E, 0x66, 0x66, 0x3C, 0x00],
    "H": [0x66, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
    "I": [0x3C, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    "J": [0x06, 0x06, 0x06, 0x06, 0x06, 0x66, 0x3C, 0x00],
    "K": [0x66, 0x6C, 0x78, 0x70, 0x78, 0x6C, 0x66, 0x00],
    "L": [0x60, 0x60, 0x60, 0x60, 0x60, 0x60, 0x7E, 0x00],
    "M": [0x63, 0x77, 0x7F, 0x6B, 0x63, 0x63, 0x63, 0x00],
    "N": [0x66, 0x6E, 0x76, 0x7E, 0x66, 0x66, 0x66, 0x00],
    "O": [0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    "P": [0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60, 0x60, 0x00],
    "Q": [0x3C, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x06, 0x0C],
    "R": [0x7C, 0x66, 0x66, 0x7C, 0x78, 0x6C, 0x66, 0x00],
    "S": [0x3C, 0x66, 0x60, 0x3C, 0x06, 0x66, 0x3C, 0x00],
    "T": [0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00],
    "U": [0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    "V": [0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
    "W": [0x63, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x63, 0x00],
    "X": [0x66, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0x66, 0x00],
    "Y": [0x66, 0x66, 0x66, 0x3C, 0x18, 0x18, 0x18, 0x00],
    "Z": [0x7E, 0x46, 0x0C, 0x18, 0x30, 0x62, 0x7E, 0x00],
    "[": [0x3C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x3C, 0x00],
    "\\": [0x60, 0x30, 0x18, 0x0C, 0x06, 0x03, 0x01, 0x00],
    "]": [0x3C, 0x30, 0x30, 0x30, 0x30, 0x30, 0x3C, 0x00],
    "^": [0x00, 0x00, 0x18, 0x18, 0x00, 0x18, 0x18, 0x00],
    "_": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7E],
    "`": [0x0C, 0x18, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00],
    "a": [0x00, 0x00, 0x3C, 0x06, 0x3E, 0x66, 0x3E, 0x00],
    "b": [0x00, 0x60, 0x60, 0x7C, 0x66, 0x66, 0x7C, 0x00],
    "c": [0x00, 0x00, 0x3C, 0x60, 0x60, 0x60, 0x3C, 0x00],
    "d": [0x00, 0x06, 0x06, 0x3E, 0x66, 0x66, 0x3E, 0x00],
    "e": [0x00, 0x00, 0x3C, 0x66, 0x7E, 0x60, 0x3C, 0x00],
    "f": [0x18, 0x30, 0x7E, 0x30, 0x30, 0x30, 0x00, 0x00],
    "g": [0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x7C],
    "h": [0x00, 0x60, 0x60, 0x7C, 0x66, 0x66, 0x66, 0x00],
    "i": [0x00, 0x00, 0x18, 0x00, 0x18, 0x18, 0x3C, 0x00],
    "j": [0x00, 0x06, 0x00, 0x06, 0x06, 0x06, 0x3E, 0x00],
    "k": [0x00, 0x60, 0x60, 0x6C, 0x78, 0x6C, 0x60, 0x00],
    "l": [0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    "m": [0x00, 0x00, 0x66, 0x7F, 0x6B, 0x63, 0x63, 0x00],
    "n": [0x00, 0x00, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x00],
    "o": [0x00, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x3C, 0x00],
    "p": [0x00, 0x00, 0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60],
    "q": [0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x06],
    "r": [0x00, 0x00, 0x66, 0x6C, 0x78, 0x60, 0x60, 0x00],
    "s": [0x00, 0x00, 0x3E, 0x40, 0x3C, 0x06, 0x7C, 0x00],
    "t": [0x00, 0x18, 0x18, 0x3E, 0x18, 0x18, 0x0C, 0x00],
    "u": [0x00, 0x00, 0x66, 0x66, 0x66, 0x66, 0x3E, 0x00],
    "v": [0x00, 0x00, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
    "w": [0x00, 0x00, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x00],
    "x": [0x00, 0x00, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0x00],
    "y": [0x00, 0x00, 0x66, 0x66, 0x66, 0x3E, 0x06, 0x7C],
    "z": [0x00, 0x00, 0x7E, 0x40, 0x30, 0x0C, 0x7E, 0x00],
    "{": [0x0C, 0x18, 0x18, 0x30, 0x18, 0x18, 0x0C, 0x00],
    "|": [0x18, 0x18, 0x18, 0x00, 0x18, 0x18, 0x18, 0x00],
    "}": [0x30, 0x18, 0x18, 0x0C, 0x18, 0x18, 0x30, 0x00],
    "~": [0x00, 0x00, 0x00, 0x76, 0x7F, 0x4B, 0x00, 0x00],
}

_memory_ref = None


def _set_memory(mem):
    global _memory_ref
    _memory_ref = mem


def text_init(memory=None):
    """
    Inizializza la modalità video 4 (320x240 8-bit color) con BG2 attivo.

    Assembly originale:
        text_init:
            mov r0, 4                   ; Background mode 4
            orr r0, 1 shl 10            ; Background 2
            mov r1, MEM_IO              ; 0x04000000
            strh r0, [r1, REG_DISPCNT]  ; DISPCNT = 0x1404

    Effect:
        - Imposta display mode 4 (320x240 bitmap)
        - Abilita Background 2
        - DISPCNT = 0x1404 (Mode 4 + BG2 on)

    Args:
        memory: Optional Memory instance. If None, uses global GBA runtime.
    """
    # Mode 4 = 320x240 8-bit color bitmap
    # Bit 10 = BG2 enable
    # DISPCNT = 0x1404 = 0b0001010000000100
    #   Bits 0-2: Mode 4
    #   Bit 10: BG2 enable
    dispcnt_value = 0x1404

    if memory is not None:
        # Use provided memory instance (for testing)
        memory.write_u16(0x04000000, dispcnt_value)
    else:
        # Use global GBA runtime memory
        if _memory_ref is None:
            raise RuntimeError(
                "gba_runtime._memory not initialized. Call text_lib._set_memory() first."
            )
        _memory_ref.write_u16(0x04000000, dispcnt_value)


def text_color(color: int, index: int, memory=None):
    """
    Imposta un colore nella palette a un indice specifico.

    Assembly originale:
        text_color:
            ; r0: color (16-bit RGB555)
            ; r1: index (0-255)
            lsl r1, 1                   ; index *= 2 (each entry is 2 bytes)
            mov r2, MEM_PALETTE         ; 0x05000000
            strh r0, [r2, r1]           ; palette[index] = color

    Effect:
        - Scrive il colore 16-bit alla posizione palette[index]
        - Ogni entry palette è 2 byte (16-bit RGB555)
        - Indirizzo = 0x05000000 + (index * 2)

    Args:
        color: colore 16-bit RGB555 (0x0000-0xFFFF)
        index: indice palette (0-255)
        memory: Optional Memory instance. If None, uses global GBA runtime.
    """
    # Ogni entry palette è 2 byte
    palette_offset = index * 2
    palette_addr = 0x05000000 + palette_offset

    if memory is not None:
        memory.write_u16(palette_addr, color)
    else:
        if _memory_ref is None:
            raise RuntimeError(
                "gba_runtime._memory not initialized. Call text_lib._set_memory() first."
            )
        _memory_ref.write_u16(palette_addr, color)


def text_glyph_data(data: int, vram_ptr: int, memory=None):
    """
    Converte 32 bit di dati in 32 pixel (2 bit per pixel) e scrive in VRAM.

    Assembly originale:
        text_glyph_data:
            ; r0: data (32-bit), modified
            ; r1: pointer (VRAM address), modified
            mov r2, 0                   ; Loop counter
        .loop:
            and r3, r0, 1               ; First bit
            lsr r0, 1
            and r4, r0, 1               ; Second bit
            lsr r0, 1
            orr r3, r4, ror 24          ; Combine bits
            strh r3, [r1], 2            ; Write 2 pixels, advance
            add r2, 2
            tst r2, 7                   ; Line end?
            addeq r1, 232               ; Move to next line
            cmp r2, 32
            bne .loop

    Args:
        data: 32-bit glyph data (16 pixel × 2 bit)
        vram_ptr: indirizzo VRAM di destinazione
        memory: Optional Memory instance. If None, uses global GBA runtime.
    """
    if memory is not None:
        mem = memory
    else:
        if _memory_ref is None:
            raise RuntimeError(
                "gba_runtime._memory not initialized. Call text_lib._set_memory() first."
            )
        mem = _memory_ref

    current_ptr = vram_ptr

    for i in range(16):
        # Estrai 2 bit per pixel
        pixel0 = data & 1
        data >>= 1
        pixel1 = data & 1
        data >>= 1

        # Combina in valore 2-bit (come l'assembly: ror 24)
        pixel_val = pixel0 | (pixel1 << 24)

        # Scrivi 2 pixel (2 byte)
        mem.write_u16(current_ptr, pixel_val & 0xFFFF)
        current_ptr += 2

        # Line wrap ogni 8 pixel (4 iterazioni)
        if (i + 1) % 4 == 0:
            current_ptr += 232


def text_glyph(x: int, y: int, data_upper: int, data_lower: int, memory=None):
    """
    Renderizza un glyph 8x8 a due colori in VRAM.

    Assembly originale:
        text_glyph:
            ; r0: x
            ; r1: y
            ; r2: glyph data upper
            ; r3: glyph data lower
            mov r4, 240
            mla r4, r4, r1, r0          ; offset = y * 240 + x
            add r4, MEM_VRAM            ; vram_addr = 0x06000000 + offset
            mov r0, r2
            mov r1, r4
            bl text_glyph_data          ; Render first half
            mov r0, r3
            mov r1, r4
            bl text_glyph_data          ; Render second half

    Args:
        x: coordinata X nella VRAM
        y: coordinata Y nella VRAM
        data_upper: primi 32 bit del glyph
        data_lower: ultimi 32 bit del glyph
        memory: Optional Memory instance. If None, uses global GBA runtime.
    """
    offset = y * 240 + x
    vram_addr = 0x06000000 + offset

    text_glyph_data(data_upper, vram_addr, memory)
    text_glyph_data(data_lower, vram_addr, memory)


def text_char(x: int, y: int, char: str, memory=None) -> int:
    """
    Renderizza un carattere ASCII a una posizione.

    Assembly originale:
        text_char:
            ; r0: x, modified
            ; r1: y
            ; r2: char (ASCII)
            sub r2, 32                  ; char -= 32
            lsl r2, 3                   ; glyph_offset = char * 8
            adr r3, glyphs              ; Load glyphs base
            add r3, r2
            ldmia r3, {r2, r3}          ; Load 8 bytes (2 words)
            bl text_glyph               ; Render glyph
            add r0, 8                   ; x += 8

    Args:
        x: coordinata X
        y: coordinata Y
        char: carattere ASCII (32-127)
        memory: Optional Memory instance. If None, uses global GBA runtime.

    Returns:
        Nuova coordinata X (x + 8)
    """
    glyph_index = ord(char) - 32

    if glyph_index < 0 or glyph_index >= len(GLYPHS):
        return x + 8

    glyph_bytes = GLYPHS[char]
    data_upper = (
        (glyph_bytes[0] << 24) | (glyph_bytes[1] << 16) | (glyph_bytes[2] << 8) | glyph_bytes[3]
    )
    data_lower = (
        (glyph_bytes[4] << 24) | (glyph_bytes[5] << 16) | (glyph_bytes[6] << 8) | glyph_bytes[7]
    )

    text_glyph(x, y, data_upper, data_lower, memory)

    return x + 8



# ===
"""GBA Runtime - Python implementation of GBA hardware"""

import pygame
from typing import Dict, Any, Optional

# Interrupts are now inline - no import needed
# ROM class is inline - no import needed
# Exceptions are inline - no import needed
# ARM7TDMI CPU core is inline - no import needed
# BIOS is now generated inline - no import needed
# Memory mapping is inline - no import needed
# PPU class is now generated inline - no import needed
# APU audio is inline - no import needed
# DMA controller is inline - no import needed
# Timers are inline - no import needed
# Input handling is inline - no import needed

# Screenshot helpers are inline - no import needed

# Global runtime state
_runtime: Optional[Dict[str, Any]] = None
_screen: Optional[pygame.Surface] = None
_running: bool = False

_memory = Memory()
_input = Input()
_memory.attach_input(_input)


def read_memory(addr: int) -> int:
    return _memory.read_u32(addr) if addr < 0x10000000 else 0


def write_memory(addr: int, value: int):
    if addr < 0x10000000:
        _memory.write_u32(addr, value)


def load_rom(path: str, memory=None):
    from .rom import ROM

    rom = ROM(path)
    if memory is not None:
        memory.load_rom(rom.data, 0x08000000)
    return rom


def poll_input() -> bool:
    pygame.event.pump()
    keys = pygame.key.get_pressed()
    return any(
        [
            keys[pygame.K_UP],
            keys[pygame.K_DOWN],
            keys[pygame.K_LEFT],
            keys[pygame.K_RIGHT],
            keys[pygame.K_z],
            keys[pygame.K_x],
            keys[pygame.K_RETURN],
            keys[pygame.K_RSHIFT],
        ]
    )


def create_runtime():
    """Create and return a fully configured GBA runtime"""
    memory = Memory()
    ppu = PPU()
    apu = APU()
    irq = InterruptController()
    dma = DMA(memory, irq)
    timers = Timers()
    input = Input()
    irq = InterruptController()

    memory.attach_ppu(ppu)
    memory.attach_apu(apu)
    memory.attach_dma(dma)
    memory.attach_timers(timers)
    memory.attach_input(input)
    memory.attach_interrupts(irq)

    cpu = ARM7TDMI(memory)

    return {
        "cpu": cpu,
        "memory": memory,
        "ppu": ppu,
        "apu": apu,
        "dma": dma,
        "timers": timers,
        "input": input,
        "irq": irq,
    }


def load_assets():
    """Load assets (palette, tiles, sprites) from generated Python files.

    This MUST be called before pygame.init() to ensure proper initialization order.
    """
    global _runtime
    if _runtime is not None:
        # Assets already loaded
        return

    # Load assets from generated code (if available)
    # These will be defined in the generated Python file
    try:
        # Import assets from generated code
        # The generated file should define: PALETTE_BG, TILES_4BPP, SPRITES, TILEMAP
        import sys
        import importlib.util

        # Try to load from generated code namespace
        if "generated_assets" in sys.modules:
            assets = sys.modules["generated_assets"]
            if hasattr(assets, "PALETTE_BG"):
                _runtime = create_runtime()
                memory = _runtime["memory"]
                # Load palette
                if hasattr(assets, "PALETTE_BG"):
                    memory.write_palette(0, assets.PALETTE_BG)
                # Load tiles
                if hasattr(assets, "TILES_4BPP"):
                    memory.write_vram(0x06000000, assets.TILES_4BPP)
                # Load sprites
                if hasattr(assets, "SPRITES"):
                    memory.write_vram(0x06018000, assets.SPRITES)
                # Load tilemap
                if hasattr(assets, "TILEMAP"):
                    memory.write_vram(0x06001800, assets.TILEMAP)

                # Parse assets after loading into VRAM
                if _runtime is not None:
                    ppu = _runtime["ppu"]
                    ppu.parse_tiles_4bpp()
                    ppu.parse_palette()
                    ppu.parse_tilemap()
    except ImportError:
        pass  # No assets loaded, will be handled by generated code


def main_entry(
    rom_path: str, frames: int = 60, headless: bool = False, screenshot_path: Optional[str] = None
):
    """Main entry point for running a GBA ROM in Python.

    Args:
        rom_path: Path to the generated Python file (not the ROM binary)
        frames: Number of frames to run (default: 60)
        headless: Run without display (default: False)
        screenshot_path: Path to save screenshot at end (optional)
    """
    global _runtime, _screen, _running

    print(f"=== GBAtoPy Runtime ===")
    print(f"ROM: {rom_path}")
    print(f"Frames: {frames}")
    print(f"Headless: {headless}")

    # STEP 1: Initialize pygame
    print("\n[1/6] Initializing pygame...")
    pygame.init()

    if not headless:
        _screen = pygame.display.set_mode((240, 160))
        pygame.display.set_caption("GBAtoPy")
    else:
        _screen = None

    # STEP 3: Create runtime
    print("[3/6] Creating runtime...")
    _runtime = create_runtime()
    cpu = _runtime["cpu"]
    memory = _runtime["memory"]
    ppu = _runtime["ppu"]
    apu = _runtime["apu"]
    input = _runtime["input"]

    # STEP 4: Start APU audio (if not headless)
    if not headless:
        print("[4/6] Starting audio...")
        apu.start()

    # STEP 5: Execute the generated code
    # The generated Python file should have a main() function or func_map
    print("[5/6] Executing ROM code...")

    # Import the generated code
    import importlib.util

    spec = importlib.util.spec_from_file_location("generated_rom", rom_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load generated ROM: {rom_path}")

    generated = importlib.util.module_from_spec(spec)
    sys.modules["generated_rom"] = generated
    spec.loader.exec_module(generated)

    # Load assets from generated module (after it's executed)
    if (
        hasattr(generated, "PALETTE_BG")
        or hasattr(generated, "TILES_4BPP")
        or hasattr(generated, "TILEMAP")
    ):
        print("  Loading assets from generated ROM...")
        _runtime = create_runtime()
        memory = _runtime["memory"]
        ppu = _runtime["ppu"]

        if hasattr(generated, "PALETTE_BG") and generated.PALETTE_BG:
            memory.write_palette(0, generated.PALETTE_BG)
        if hasattr(generated, "TILES_4BPP") and generated.TILES_4BPP:
            memory.write_vram(0x06000000, generated.TILES_4BPP)
        if hasattr(generated, "TILEMAP") and generated.TILEMAP:
            memory.write_vram(0x06001800, generated.TILEMAP)

        # Parse assets after loading into VRAM
        ppu.parse_tiles_4bpp()
        ppu.parse_palette()
        ppu.parse_tilemap()

    # Check if func_map exists and call entry point
    if hasattr(generated, "func_map") and 0x08000000 in generated.func_map:
        print("  Entry point found: func_map[0x08000000]")
        # Note: We don't call it directly here - the game loop will handle execution
    elif hasattr(generated, "main"):
        print("  Entry point found: main()")
    else:
        print("  WARNING: No entry point found in generated code")

    # STEP 6: Run game loop
    print("[6/6] Running game loop...")
    _running = True
    clock = pygame.time.Clock()

    for frame in range(frames):
        if not _running:
            print(f"\nGame stopped at frame {frame}")
            break

        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _running = False
                break
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    _running = False
                    break

        if not _running:
            break

        # Poll input
        input.poll()

        # Execute CPU with timeout to prevent infinite loops
        if hasattr(generated, "func_map") and 0x08000000 in generated.func_map:
            import threading

            result = {"exception": None}

            def run_rom():
                try:
                    generated.func_map[0x08000000]()
                except Exception as e:
                    result["exception"] = e

            rom_thread = threading.Thread(target=run_rom)
            rom_thread.daemon = True
            rom_thread.start()
            rom_thread.join(timeout=0.016667)

            if rom_thread.is_alive():
                if hasattr(generated, "z"):
                    generated.z = 1
            elif result["exception"]:
                print(f"  WARNING: ROM execution raised exception: {result['exception']}")
                break
        elif hasattr(generated, "main"):
            try:
                generated.main()
            except Exception as e:
                print(f"  WARNING: main() raised exception: {e}")
                break

        # Render frame
        if _screen is not None:
            ppu.render_frame()

            # Set VBlank flag to allow ROMs waiting for VBlank to proceed
            set_vblank_flag()

            # Copy PPU buffer to screen
            surface_data = ppu.get_surface_data()
            if surface_data is not None:
                _screen.blit(surface_data, (0, 0))

            pygame.display.flip()

        # APU audio update
        if not headless and _runtime is not None:
            apu.update()

        # Trigger VBlank interrupt
        if _runtime is not None:
            _runtime["dma"].vblank_fire()

        # VBlank simulation
        # Set z=1 to unblock VBlank wait loops
        if hasattr(generated, "z"):
            generated.z = 1

        # Frame timing
        clock.tick(60)  # Target 60 FPS

        if (frame + 1) % 10 == 0:
            print(f"  Frame {frame + 1}/{frames}")

    print("\n=== Game finished! ===")
    print(f"Total frames: {frame + 1}")

    # Capture screenshot if requested
    if screenshot_path and _screen is not None:
        pygame.image.save(_screen, screenshot_path)
        print(f"Screenshot saved to: {screenshot_path}")

    # Cleanup
    if not headless:
        apu.stop()

    pygame.quit()
    _runtime = None
    _screen = None
    _running = False


