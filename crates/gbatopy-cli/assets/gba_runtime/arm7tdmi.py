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

    def _update_flags_nzcv(self, result: int, carry: int = 0, overflow: int = 0) -> int:
        """Update CPSR N, Z, C, V flags based on result.
        
        Args:
            result: The computation result (32-bit value)
            carry: Carry flag value (optional, defaults to 0)
            overflow: Overflow flag value (optional, defaults to 0)
            
        Returns:
            New CPSR value with updated flags
        """
        # N: Negative flag (bit 31)
        n = (result >> 31) & 1
        # Z: Zero flag (bit 30)
        z = 1 if result == 0 else 0
        # C: Carry flag (use provided value or 0)
        c = carry & 1
        # V: Overflow flag (use provided value or 0)
        v = overflow & 1
        
        # Clear old flags and set new ones
        self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        return self.cpsr

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
                    operand2 = (operand2 >> shift_imm) | ((operand2 & 0x80000000) * shift_imm)
                elif shift_type == 3:  # ROR
                    operand2 = (
                        (operand2 >> shift_imm) | (operand2 << (32 - shift_imm))
                    ) & 0xFFFFFFFF

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
        """Handle BIOS SWI calls.
        
        GBA SWI numbers (from bios.h):
        0x00: SoftReset
        0x01: RegisterRamReset
        0x02: Halt
        0x03: Stop
        0x04: IntrWait
        0x05: VBlankIntrWait
        0x06: Div
        0x07: DivArm
        0x08: Sqrt
        0x09: ArcTan
        0x0A: ArcTan2
        0x0B: CpuSet
        0x0C: CpuFastSet
        0x0E: BgAffineSet
        0x0F: ObjAffineSet
        0x11: LZ77UnCompWram
        0x12: LZ77UnCompVram
        """
        if num == 0x00:  # SoftReset
            for i in range(13):
                self.registers[i] = 0
            self.registers[13] = 0x03007F00
            self.registers[15] = 0x08000000
        elif num == 0x01:  # RegisterRamReset
            flags = self.registers[0]
            # Reset EWRAM
            if flags & 0x01:
                for addr in range(0x02000000, 0x02040000, 4):
                    self.memory.write_u32(addr, 0)
            # Reset IWRAM
            if flags & 0x02:
                for addr in range(0x03000000, 0x03008000, 4):
                    self.memory.write_u32(addr, 0)
            # Reset Palette
            if flags & 0x04:
                for addr in range(0x05000000, 0x05000400, 2):
                    self.memory.write_u16(addr, 0)
            # Reset VRAM
            if flags & 0x08:
                for addr in range(0x06000000, 0x06018000, 2):
                    self.memory.write_u16(addr, 0)
            # Reset OAM
            if flags & 0x10:
                for addr in range(0x07000000, 0x07000400, 2):
                    self.memory.write_u16(addr, 0)
        elif num == 0x02:  # Halt
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_halt()
        elif num == 0x03:  # Stop
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_stop(self.registers[0])
        elif num == 0x04:  # IntrWait
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_intr_wait(self.registers[0], self.registers[1])
        elif num == 0x05:  # VBlankIntrWait
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_vblank_intr_wait()
        elif num == 0x06:  # Div
            if hasattr(self, 'bios') and self.bios is not None:
                result = self.bios.swi_div(self.registers[0], self.registers[1])
                remainder = self.registers[0] % self.registers[1] if self.registers[1] != 0 else 0
                self.registers[0] = result & 0xFFFFFFFF
                self.registers[1] = remainder & 0xFFFFFFFF
        elif num == 0x07:  # DivArm (unsigned division)
            if hasattr(self, 'bios') and self.bios is not None:
                dividend = self.registers[0] & 0xFFFFFFFF
                divisor = self.registers[1] & 0xFFFFFFFF
                if divisor == 0:
                    self.registers[0] = 0
                else:
                    result = dividend // divisor
                    self.registers[0] = result & 0xFFFFFFFF
        elif num == 0x08:  # Sqrt
            if hasattr(self, 'bios') and self.bios is not None:
                result = self.bios.swi_sqrt(self.registers[0])
                self.registers[0] = result & 0xFFFFFFFF
        elif num == 0x09:  # ArcTan
            if hasattr(self, 'bios') and self.bios is not None:
                result = self.bios.swi_arctan(self.registers[0])
                self.registers[0] = result & 0xFFFF
        elif num == 0x0A:  # ArcTan2
            if hasattr(self, 'bios') and self.bios is not None:
                result = self.bios.swi_arctan2(self.registers[0], self.registers[1])
                self.registers[0] = result & 0xFFFF
        elif num == 0x0B:  # CpuSet
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_cpuset(self.registers[0], self.registers[1], self.registers[2], self.registers[2])
        elif num == 0x0C:  # CpuFastSet
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_cpufastset(self.registers[0], self.registers[1], self.registers[2], self.registers[3])
        elif num == 0x0E:  # BgAffineSet
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_bg_affine_set(self.registers[0], self.registers[1], self.registers[2], self.registers[3])
        elif num == 0x0F:  # ObjAffineSet
            if hasattr(self, 'bios') and self.bios is not None:
                data = self.registers[0]
                param_table = self.registers[1]
                num_objects = self.registers[2]
                increment = self.registers[3]
                for i in range(num_objects):
                    offset = i * increment
                    self.bios.swi_obj_affine_set(
                        param_table + offset,
                        self.memory.read_u16(data + offset * 2),
                        self.memory.read_u16(data + offset * 2 + 2),
                        self.memory.read_u16(data + offset * 2 + 4)
                    )
        elif num == 0x11:  # LZ77UnCompWram
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_lz77_uncomp(self.registers[0], self.registers[1])
        elif num == 0x12:  # LZ77UnCompVram
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_lz77_uncomp(self.registers[0], self.registers[1])

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


class ISRHandler:
    """Default ISR handler placed at 0x03007FFC in IWRAM."""

    def __init__(self, memory, interrupts):
        self.memory = memory
        self.interrupts = interrupts
        self._handlers = {}
    
    def register_handler(self, irq_id: int, callback):
        self._handlers[irq_id] = callback
    
    def handle_irq(self):
        if_reg = self.interrupts.if_reg
        ie_reg = self.interrupts.ie_reg
        pending = if_reg & ie_reg & 0xFFFF
        
        if pending == 0:
            return
        
        current_cpsr = self.cpsr
        thumb_mode_before = self.thumb_mode
        
        irq_bit = 0
        while irq_bit < 14:
            if pending & (1 << irq_bit):
                if irq_bit in self._handlers:
                    try:
                        self._handlers[irq_bit]()
                    except Exception as e:
                        print(f"  WARNING: ISR handler {irq_bit} raised exception: {e}")
                self.interrupts.if_reg &= ~(1 << irq_bit)
                
                if 8 <= irq_bit <= 11:
                    ch = irq_bit - 8
                    if hasattr(self.memory, 'dma') and self.memory.dma:
                        self.memory.dma.channels[ch].pending = False
                
                self.cpsr = current_cpsr
                self.thumb_mode = thumb_mode_before
                break
            irq_bit += 1
    
    def handle_vblank(self):
        if InterruptController.IRQ_VBLANK in self._handlers:
            self._handlers[InterruptController.IRQ_VBLANK]()
    
    def handle_hblank(self):
        if InterruptController.IRQ_HBLANK in self._handlers:
            self._handlers[InterruptController.IRQ_HBLANK]()
    
    def handle_vcounter(self):
        if InterruptController.IRQ_VCOUNTER in self._handlers:
            self._handlers[InterruptController.IRQ_VCOUNTER]()
    
    def handle_timer(self, channel: int):
        irq_id = InterruptController.IRQ_TIMER0 + channel
        if irq_id in self._handlers:
            self._handlers[irq_id]()
    
    def handle_dma(self, channel: int):
        irq_id = InterruptController.IRQ_DMA0 + channel
        if irq_id in self._handlers:
            self._handlers[irq_id]()
    
    def handle_keypad(self):
        if InterruptController.IRQ_KEYPAD in self._handlers:
            self._handlers[InterruptController.IRQ_KEYPAD]()
    
    def handle_gamepak(self):
        if InterruptController.IRQ_GAMEPAK in self._handlers:
            self._handlers[InterruptController.IRQ_GAMEPAK]()


from gba_runtime.interrupts import InterruptController
