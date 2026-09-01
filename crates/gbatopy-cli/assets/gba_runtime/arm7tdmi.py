"""ARM7TDMI CPU Interpreter for GBA"""

from typing import Optional, Callable, List, Tuple
from bios import BIOS

try:
    import numba
    from numba import njit
    _HAS_NUMBA = True
except ImportError:
    numba = None
    # Create a no-op decorator when numba is not available
    def njit(*args, **kwargs):
        """No-op decorator when numba is not available."""
        def decorator(func):
            return func
        # Handle @njit() with no arguments
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator
    _HAS_NUMBA = False

_NUMBA_ENABLED = False

_MODE_TO_SPSR_IDX = {0x10: 0, 0x1F: 1, 0x13: 2, 0x17: 3, 0x1B: 4, 0x11: 5, 0x12: 6}
_MODES_WITH_SPSR = frozenset({0x11, 0x12, 0x13, 0x17, 0x1B})


def jit_compile(func):
    """Decorator to optionally compile functions with numba for 10x speedup."""
    if not _HAS_NUMBA or not _NUMBA_ENABLED:
        return func
    try:
        return njit(func)
    except Exception as e:
        print(f"  Warning: JIT compilation failed for {func.__name__}: {e}")
        return func


def set_numba_enabled(enabled: bool):
    global _NUMBA_ENABLED
    if not _HAS_NUMBA and enabled:
        print("  Warning: numba not installed, JIT compilation unavailable")
    _NUMBA_ENABLED = enabled and _HAS_NUMBA


def is_numba_available() -> bool:
    return _HAS_NUMBA


@jit_compile
def _check_condition_fast(cond: int, n: int, z: int, c: int, v: int) -> bool:
    if cond == 0xE or cond == 0xF:
        return True
    if cond == 0x0:
        return z == 1
    if cond == 1:
        return z == 0
    if cond == 0x2:
        return c == 1
    if cond == 0x3:
        return c == 0
    if cond == 0x4:
        return n == 1
    if cond == 0x5:
        return n == 0
    if cond == 0x6:
        return v == 1
    if cond == 0x7:
        return v == 0
    if cond == 0x8:
        return c == 1 and z == 0
    if cond == 0x9:
        return c == 0 or z == 1
    if cond == 0xA:
        return n == v
    if cond == 0xB:
        return n != v
    if cond == 0xC:
        return z == 0 and n == v
    if cond == 0xD:
        return z == 1 or n != v
    return True


@jit_compile
def _update_flags_fast(result: int, carry: int, overflow: int) -> int:
    n = (result >> 31) & 1
    z = 1 if result == 0 else 0
    c = carry & 1
    v = overflow & 1
    return (n << 31) | (z << 30) | (c << 29) | (v << 28)


class ARM7TDMI:
    """ARM7TDMI CPU interpreter with full instruction execution."""

    def __init__(self, memory):
        self.memory = memory
        self.registers = [0] * 16  # r0-r15
        self.cpsr = 0  # Current Program Status Register
        self.spsr = [0] * 7  # Saved PSR for each mode (USR, SYS, SVC, ABT, UND, FIQ, IRQ)

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
        self.running = True
        self.cycles = 0
        self._halted = False
        self._halt_reason = None
        self._swi_lr = None
        self._swi_caller_pc = None

        # Banked SP/LR per mode (FIQ also banks r8-r12)
        # User (0x10) and System (0x1F) share the same register bank
        _user_sys_bank = {'sp': 0, 'lr': 0}
        self.banked_sp_lr = {
            0x10: _user_sys_bank,  # User
            0x1F: _user_sys_bank,  # System
            0x11: {'sp': 0, 'lr': 0, 'r8': 0, 'r9': 0, 'r10': 0, 'r11': 0, 'r12': 0},  # FIQ
            0x12: {'sp': 0, 'lr': 0},  # IRQ
            0x13: {'sp': 0, 'lr': 0},  # SVC
            0x17: {'sp': 0, 'lr': 0},  # ABT
            0x1B: {'sp': 0, 'lr': 0},  # UND
        }

        # Initialize BIOS for SWI handlers
        self.bios = BIOS(self.memory)

    def _switch_mode(self, new_mode: int):
        """Swap banked SP/LR (and r8-r12 for FIQ) on mode change."""
        old_mode = self.mode
        if new_mode == old_mode:
            return

        # Save outgoing mode's banked registers
        if old_mode in self.banked_sp_lr:
            bank = self.banked_sp_lr[old_mode]
            bank['sp'] = self.registers[13]
            bank['lr'] = self.registers[14]
            if old_mode == 0x11:  # FIQ banks r8-r12
                bank['r8'] = self.registers[8]
                bank['r9'] = self.registers[9]
                bank['r10'] = self.registers[10]
                bank['r11'] = self.registers[11]
                bank['r12'] = self.registers[12]

        # Load incoming mode's banked registers
        if new_mode in self.banked_sp_lr:
            bank = self.banked_sp_lr[new_mode]
            self.registers[13] = bank['sp']
            self.registers[14] = bank['lr']
            if new_mode == 0x11:  # FIQ banks r8-r12
                self.registers[8] = bank['r8']
                self.registers[9] = bank['r9']
                self.registers[10] = bank['r10']
                self.registers[11] = bank['r11']
                self.registers[12] = bank['r12']

        self.mode = new_mode

    @property
    def r(self):
        return self.registers

    @property
    def thumb_mode(self) -> bool:
        return bool((self.cpsr >> 5) & 1)

    @thumb_mode.setter
    def thumb_mode(self, value: bool):
        if value:
            self.cpsr |= (1 << 5)
        else:
            self.cpsr &= ~(1 << 5)

    @property
    def pc(self) -> int:
        return self.registers[15]

    @pc.setter
    def pc(self, value: int):
        if value & 1:
            self.thumb_mode = True
            self.registers[15] = value & 0xFFFFFFFE
        else:
            self.registers[15] = value & (0xFFFFFFFE if self.thumb_mode else 0xFFFFFFFC)

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

    @jit_compile
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

    @jit_compile
    def read_register(self, reg: int) -> int:
        return self.registers[reg & 0xF]

    @jit_compile
    def write_register(self, reg: int, value: int):
        value &= 0xFFFFFFFF
        self.registers[reg & 0xF] = value
        if (reg & 0xF) == 15:
            if value & 1:
                self.thumb_mode = True
                self.registers[15] = value & 0xFFFFFFFE
            else:
                self.registers[15] = value & (0xFFFFFFFE if self.thumb_mode else 0xFFFFFFFC)

    def _operand(self, reg: int) -> int:
        """Read a register as an instruction operand.

        R15 has a visible value of PC+8 in ARM mode and PC+4 in Thumb mode
        because of the 3-stage pipeline: when the current instruction at PC
        is executing, the fetch for PC+8 (ARM) is already in flight. Reading
        R15 directly returns the fetch address, so operand reads must add the
        pipeline offset.
        """
        if (reg & 0xF) == 15:
            offset = 4 if self.thumb_mode else 8
            return (self.registers[15] + offset) & 0xFFFFFFFF
        return self.registers[reg & 0xF]

    @jit_compile
    def step(self) -> int:
        if self.thumb_mode:
            return self.step_thumb()
        return self.step_arm()

    @jit_compile
    def step_arm(self) -> int:
        pc = self.pc
        instr = self.memory.read_u32(pc)
        cond = (instr >> 28) & 0xF

        if not self.check_condition(cond):
            self.registers[15] += 4
            return 1

        return self.execute_arm(instr)

    @jit_compile
    def step_thumb(self) -> int:
        pc = self.registers[15] & 0xFFFFFFFE
        instr = self.memory.read_u16(pc)
        return self.execute_thumb(instr)

    def execute_arm(self, instr: int) -> int:
        opcode = (instr >> 21) & 0xF
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        rm = instr & 0xF

        if (instr & 0x0FFFFFF0) == 0x012FFF10:
            rm = instr & 0xF
            target = self._operand(rm)
            self.thumb_mode = (target & 1) != 0
            self.registers[15] = target & 0xFFFFFFFE
            return 3

        if (instr & 0x0FFFFFF0) == 0x012FFF30:
            rm = instr & 0xF
            target = self._operand(rm)
            self.registers[14] = (self.registers[15] + 4) & 0xFFFFFFFF
            self.thumb_mode = (target & 1) != 0
            self.registers[15] = target & 0xFFFFFFFE
            return 3

        if (instr & 0x0C000000) == 0:
            is_immediate = (instr >> 25) & 1
            if not is_immediate:
                op_lo = instr & 0xF0
                if op_lo == 0x90:
                    if (instr >> 24) & 1:
                        return self.exec_swp(instr)
                    return self.exec_mul(instr)
                if op_lo == 0xB0 or op_lo == 0xD0 or op_lo == 0xF0:
                    return self.exec_extra_load_store(instr)
            op2 = (instr >> 20) & 0xFF
            if (op2 in (0x10, 0x14) and rn == 15) or (op2 in (0x12, 0x16, 0x32, 0x36) and rd == 15):
                return self._exec_status_transfer(instr, rd)
            return self.exec_data_processing(instr)

        if (instr & 0xC000000) == 0x4000000:
            return self.exec_load_store(instr)

        if (instr & 0xE000000) == 0xA000000:
            return self.exec_branch(instr)

        if (instr & 0xE000000) == 0x8000000:
            return self.exec_block_transfer(instr)

        if (instr & 0xF000000) == 0xF000000:
            return self.exec_swi(instr)

        raise NotImplementedError(
            'Unhandled ARM instruction at PC={:#010x}: {:#010x}'.format(
                self.registers[15] & 0xFFFFFFFC, instr
            )
        )


    def _exec_status_transfer(self, instr: int, rd: int) -> int:
        """Execute MSR (write PSR) or MRS (read PSR).

        Encoding overlaps with TST/TEQ/CMP/CMN when S=0:
          - Rd == 15 (Rn field == 15 in disassembly) -> MSR: write masked fields
          - Rn == 15 (rd field == 15)                  -> MRS: read PSR to Rd

        Field mask (bits 19:16 of instr):
          bit 19 = f -> update N,Z,C,V (bits 31:28)
          bit 18 = s -> reserved (bits 23:16)
          bit 17 = x -> reserved (bits 15:8)
          bit 16 = c -> update mode,I,F,T (bits 7:0)
        """
        is_mrs = (rd == 15)  # Rn field holds the mask for MSR; Rd field == 15 means MRS
        # In our encoding MSR has Rd==15 (Rn in standard form), MRS has Rn==15.
        # Re-derive cleanly: MSR is selected when bit 21 (opcode bit) is 0x2 AND Rn != 15.
        rn = (instr >> 16) & 0xF
        rd_field = (instr >> 12) & 0xF
        # MRS: 00010?001111???????1111????????
        #   - Rn field = 1111? No: MRS has Rn=1111 (15) and Rd != 15.
        # MSR (reg): 00010?10?1111????1111????????
        #   - Rd field = 1111 (15), Rn field = mask.
        # MSR (imm): 00110010?1111????1111????????
        #   - Rd field = 1111 (15), Rn field = mask.
        is_msr = (rd_field == 15)

        if not is_msr and rn == 15:
            # MRS: Rd <- CPSR (or SPSR if bit 22 set)
            psr_sel = (instr >> 22) & 1
            if psr_sel:
                mode_idx = _MODE_TO_SPSR_IDX.get(self.mode, 0)
                psr = self.spsr[mode_idx] if 0 <= mode_idx < len(self.spsr) else 0
            else:
                psr = self.cpsr
            self.registers[rd_field] = psr & 0xFFFFFFFF
            self.registers[15] = (self.registers[15] + 4) & 0xFFFFFFFF
            return 1

        # MSR: compute operand
        imm = (instr >> 25) & 1
        if imm:
            imm_val = instr & 0xFF
            rot = ((instr >> 8) & 0xF) * 2
            if rot:
                imm_val = ((imm_val >> rot) | (imm_val << (32 - rot))) & 0xFFFFFFFF
            operand = imm_val
        else:
            rm = instr & 0xF
            operand = self.registers[rm & 0xF] & 0xFFFFFFFF

        # Field mask from bits 19:16
        mask_f = (rn >> 3) & 1  # bit 19
        mask_s = (rn >> 2) & 1  # bit 18
        mask_x = (rn >> 1) & 1  # bit 17
        mask_c = (rn >> 0) & 1  # bit 16

        psr_sel = (instr >> 22) & 1
        if psr_sel:
            mode_idx = {0x10: 0, 0x1F: 1, 0x13: 2, 0x17: 3, 0x1A: 4, 0x11: 5}.get(self.mode, 0)
            target = self.spsr[mode_idx] if 0 <= mode_idx < 6 else 0
            write_back_spsr = True
        else:
            target = self.cpsr
            write_back_spsr = False

        new_psr = target
        if mask_f:
            new_psr = (new_psr & 0x0FFFFFFF) | (operand & 0xF0000000)
        if mask_s:
            new_psr = (new_psr & 0xFF00FFFF) | (operand & 0x00FF0000)
        if mask_x:
            new_psr = (new_psr & 0xFFFF00FF) | (operand & 0x0000FF00)
        if mask_c:
            new_psr = (new_psr & 0xFFFFFF00) | (operand & 0x000000FF)

        if write_back_spsr:
            self.spsr[mode_idx] = new_psr & 0xFFFFFFFF
        else:
            self.cpsr = new_psr & 0xFFFFFFFF
            self._switch_mode(new_psr & 0x1F)
            self.thumb_mode = bool((new_psr >> 5) & 1)

        self.registers[15] = (self.registers[15] + 4) & 0xFFFFFFFF
        return 1

    @jit_compile
    def exec_data_processing(self, instr: int) -> int:
        """Execute ARM data processing instruction."""
        opcode = (instr >> 21) & 0xF
        s_bit = (instr >> 20) & 1
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        rm = instr & 0xF

        # MSR/MRS: test opcodes (TST=8, TEQ=9, CMP=A, CMN=B) with S=0
        # are status register transfers, not arithmetic tests.
        # Rd=15 → MSR (write PSR), Rn=15 → MRS (read PSR).
        if opcode in (8, 9, 0xA, 0xB) and s_bit == 0:
            return self._exec_status_transfer(instr, rd)

        shifter_carry = (self.cpsr >> 29) & 1

        # Check for immediate
        imm = (instr >> 25) & 1
        if imm:
            imm_val = instr & 0xFF
            rot = ((instr >> 8) & 0xF) * 2
            if rot:
                imm_val = ((imm_val >> rot) | (imm_val << (32 - rot))) & 0xFFFFFFFF
                shifter_carry = (imm_val >> 31) & 1
            operand2 = imm_val
        else:
            shift_type = (instr >> 5) & 3
            operand2 = self._operand(rm)
            if (instr >> 4) & 1:  # register-specified shift
                rs = (instr >> 8) & 0xF
                shift_amount = self._operand(rs) & 0xFF
                if shift_amount == 0:
                    pass
                elif shift_amount < 32:
                    if shift_type == 0:  # LSL
                        shifter_carry = (operand2 >> (32 - shift_amount)) & 1
                        operand2 = (operand2 << shift_amount) & 0xFFFFFFFF
                    elif shift_type == 1:  # LSR
                        shifter_carry = (operand2 >> (shift_amount - 1)) & 1
                        operand2 = operand2 >> shift_amount
                    elif shift_type == 2:  # ASR
                        shifter_carry = (operand2 >> (shift_amount - 1)) & 1
                        operand2 = (operand2 >> shift_amount) | (
                            (operand2 & 0x80000000) * (0xFFFFFFFF >> (32 - shift_amount))
                        )
                    else:  # ROR
                        shifter_carry = (operand2 >> (shift_amount - 1)) & 1
                        operand2 = (
                            (operand2 >> shift_amount) | (operand2 << (32 - shift_amount))
                        ) & 0xFFFFFFFF
                elif shift_amount == 32:
                    if shift_type == 0:  # LSL
                        shifter_carry = operand2 & 1
                        operand2 = 0
                    elif shift_type == 1:  # LSR
                        shifter_carry = (operand2 >> 31) & 1
                        operand2 = 0
                    elif shift_type == 2:  # ASR
                        shifter_carry = (operand2 >> 31) & 1
                        operand2 = 0xFFFFFFFF if (operand2 & 0x80000000) else 0
                    else:  # ROR by 32 = no change, carry = bit 31
                        shifter_carry = (operand2 >> 31) & 1
                else:  # shift_amount > 32
                    if shift_type == 0:  # LSL
                        shifter_carry = 0
                        operand2 = 0
                    elif shift_type == 1:  # LSR
                        shifter_carry = 0
                        operand2 = 0
                    elif shift_type == 2:  # ASR
                        shifter_carry = (operand2 >> 31) & 1
                        operand2 = 0xFFFFFFFF if (operand2 & 0x80000000) else 0
                    else:  # ROR
                        eff = shift_amount % 32
                        if eff == 0:
                            shifter_carry = (operand2 >> 31) & 1
                        else:
                            shifter_carry = (operand2 >> (eff - 1)) & 1
                            operand2 = (
                                (operand2 >> eff) | (operand2 << (32 - eff))
                            ) & 0xFFFFFFFF
            else:
                shift_imm = (instr >> 7) & 0x1F
                if shift_imm:
                    if shift_type == 0:  # LSL
                        shifter_carry = (operand2 >> (32 - shift_imm)) & 1
                        operand2 = (operand2 << shift_imm) & 0xFFFFFFFF
                    elif shift_type == 1:  # LSR
                        shifter_carry = (operand2 >> (shift_imm - 1)) & 1
                        operand2 = operand2 >> shift_imm
                    elif shift_type == 2:  # ASR
                        shifter_carry = (operand2 >> (shift_imm - 1)) & 1
                        operand2 = (operand2 >> shift_imm) | (
                            (operand2 & 0x80000000) * (0xFFFFFFFF >> (32 - shift_imm))
                        )
                    elif shift_type == 3:  # ROR
                        shifter_carry = (operand2 >> (shift_imm - 1)) & 1
                        operand2 = (
                            (operand2 >> shift_imm) | (operand2 << (32 - shift_imm))
                        ) & 0xFFFFFFFF
                else:
                    if shift_type == 1:  # LSR #0 means LSR #32
                        shifter_carry = (operand2 >> 31) & 1
                        operand2 = 0
                    elif shift_type == 2:  # ASR #0 means ASR #32
                        shifter_carry = (operand2 >> 31) & 1
                        operand2 = 0xFFFFFFFF if (operand2 & 0x80000000) else 0
                    elif shift_type == 3:  # ROR #0 means RRX
                        carry = (self.cpsr >> 29) & 1
                        shifter_carry = operand2 & 1
                        operand2 = ((carry << 31) | (operand2 >> 1)) & 0xFFFFFFFF

        operand1 = self._operand(rn)

        is_test = opcode in (8, 9, 0xA, 0xB)
        is_arithmetic = opcode in (2, 3, 4, 5, 6, 7, 0xA, 0xB)
        update_flags = s_bit or is_test
        alu_carry = shifter_carry
        alu_overflow = (self.cpsr >> 28) & 1

        if opcode == 0:  # AND
            result = operand1 & operand2
            self.write_register(rd, result)
        elif opcode == 1:  # EOR
            result = operand1 ^ operand2
            self.write_register(rd, result)
        elif opcode == 2:  # SUB
            result = (operand1 - operand2) & 0xFFFFFFFF
            alu_carry = 1 if operand1 >= operand2 else 0
            alu_overflow = 1 if ((operand1 ^ operand2) & (operand1 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 3:  # RSB
            result = (operand2 - operand1) & 0xFFFFFFFF
            alu_carry = 1 if operand2 >= operand1 else 0
            alu_overflow = 1 if ((operand2 ^ operand1) & (operand2 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 4:  # ADD
            raw = operand1 + operand2
            result = raw & 0xFFFFFFFF
            alu_carry = 1 if raw > 0xFFFFFFFF else 0
            alu_overflow = 1 if ((operand1 ^ result) & (operand2 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 5:  # ADC
            c = (self.cpsr >> 29) & 1
            raw = operand1 + operand2 + c
            result = raw & 0xFFFFFFFF
            alu_carry = 1 if raw > 0xFFFFFFFF else 0
            alu_overflow = 1 if ((operand1 ^ result) & (operand2 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 6:  # SBC
            c = (self.cpsr >> 29) & 1
            result = (operand1 - operand2 - (1 - c)) & 0xFFFFFFFF
            alu_carry = 1 if (operand1 >= operand2 + (1 - c)) else 0
            alu_overflow = 1 if ((operand1 ^ operand2) & (operand1 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 7:  # RSC
            c = (self.cpsr >> 29) & 1
            result = (operand2 - operand1 - (1 - c)) & 0xFFFFFFFF
            alu_carry = 1 if (operand2 >= operand1 + (1 - c)) else 0
            alu_overflow = 1 if ((operand2 ^ operand1) & (operand2 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 8:  # TST
            result = operand1 & operand2
        elif opcode == 9:  # TEQ
            result = operand1 ^ operand2
        elif opcode == 0xA:  # CMP
            result = (operand1 - operand2) & 0xFFFFFFFF
            alu_carry = 1 if operand1 >= operand2 else 0
            alu_overflow = 1 if ((operand1 ^ operand2) & (operand1 ^ result) & 0x80000000) else 0
        elif opcode == 0xB:  # CMN
            raw = operand1 + operand2
            result = raw & 0xFFFFFFFF
            alu_carry = 1 if raw > 0xFFFFFFFF else 0
            alu_overflow = 1 if ((operand1 ^ result) & (operand2 ^ result) & 0x80000000) else 0
        elif opcode == 0xC:  # ORR
            result = operand1 | operand2
            self.write_register(rd, result)
        elif opcode == 0xD:  # MOV
            result = operand2
            self.write_register(rd, result)
        elif opcode == 0xE:  # BIC
            result = operand1 & (~operand2 & 0xFFFFFFFF)
            self.write_register(rd, result)
        elif opcode == 0xF:  # MVN
            result = (~operand2) & 0xFFFFFFFF
            self.write_register(rd, result)

        if update_flags:
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            if is_arithmetic:
                c = alu_carry
                v = alu_overflow
            else:
                c = shifter_carry
                v = (self.cpsr >> 28) & 1
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)

        if rd != 15:
            self.registers[15] += 4
        elif update_flags:
            # SUBS/MOVS PC, Rm — exception return: restore CPSR from SPSR.
            # Only privileged modes have an SPSR; User/System mode leaves CPSR unchanged.
            import sys as _sys
            _fc = getattr(_sys.modules.get('__main__', None), 'fc', -1)
            _mode_before = self.mode
            _sp_before = self.registers[13]
            if self.mode in _MODES_WITH_SPSR:
                _idx = _MODE_TO_SPSR_IDX.get(self.mode, -1)
                if 0 <= _idx < len(self.spsr):
                    new_cpsr = self.spsr[_idx] & 0xFFFFFFFF
                    new_mode = new_cpsr & 0x1F
                    self._switch_mode(new_mode)
                    self.cpsr = new_cpsr
                    self.mode = new_mode
                    self.thumb_mode = (new_cpsr >> 5) & 1

        return 1

    @jit_compile
    def exec_load_store(self, instr: int) -> int:
        is_load = (instr >> 20) & 1
        is_byte = (instr >> 22) & 1
        is_up = (instr >> 23) & 1
        p_bit = (instr >> 24) & 1
        w_bit = (instr >> 21) & 1
        is_imm = not ((instr >> 25) & 1)
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF

        base = self._operand(rn)

        if is_imm:
            offset = instr & 0xFFF
        else:
            rm = instr & 0xF
            shift_type = (instr >> 5) & 3
            shift_imm = (instr >> 7) & 0x1F
            offset = self._operand(rm)
            if shift_imm:
                if shift_type == 0:
                    offset = (offset << shift_imm) & 0xFFFFFFFF
                elif shift_type == 1:
                    offset = offset >> shift_imm
                elif shift_type == 2:
                    offset = (offset >> shift_imm) | ((offset & 0x80000000) * (0xFFFFFFFF >> (32 - shift_imm)))
                elif shift_type == 3:
                    offset = ((offset >> shift_imm) | (offset << (32 - shift_imm))) & 0xFFFFFFFF

        eff_offset = offset if is_up else -offset

        if p_bit:
            addr = (base + eff_offset) & 0xFFFFFFFF
        else:
            addr = base

        if is_load:
            if is_byte:
                val = self.memory.read_u8(addr)
            else:
                val = self.memory.read_u32(addr)
            self.write_register(rd, val)
        else:
            val = self._operand(rd)
            if is_byte:
                self.memory.write_u8(addr, val & 0xFF)
            else:
                self.memory.write_u32(addr, val)

        if w_bit or not p_bit:
            if rn != 15:
                self.registers[rn] = (base + eff_offset) & 0xFFFFFFFF

        if rd != 15:
            self.registers[15] += 4
        return 2

    @jit_compile
    def exec_extra_load_store(self, instr: int) -> int:
        p_bit = (instr >> 24) & 1
        is_up = (instr >> 23) & 1
        is_imm = (instr >> 22) & 1
        w_bit = (instr >> 21) & 1
        is_load = (instr >> 20) & 1
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        sh = (instr >> 5) & 0x3

        base = self._operand(rn)

        if is_imm:
            imm_hi = (instr >> 8) & 0xF
            imm_lo = instr & 0xF
            offset = (imm_hi << 4) | imm_lo
        else:
            rm = instr & 0xF
            offset = self._operand(rm)

        eff_offset = offset if is_up else -offset

        if p_bit:
            addr = (base + eff_offset) & 0xFFFFFFFF
        else:
            addr = base

        if not is_load:
            val = self._operand(rd)
            self.memory.write_u16(addr, val & 0xFFFF)
        else:
            if sh == 1:
                val = self.memory.read_u16(addr)
            elif sh == 2:
                val = self.memory.read_u8(addr)
                if val & 0x80:
                    val |= 0xFFFFFF00
            elif sh == 3:
                val = self.memory.read_u16(addr)
                if val & 0x8000:
                    val |= 0xFFFF0000
            else:
                val = 0
            self.write_register(rd, val)

        if w_bit or not p_bit:
            if rn != 15:
                self.registers[rn] = (base + eff_offset) & 0xFFFFFFFF

        if rd != 15:
            self.registers[15] = (self.registers[15] + 4) & 0xFFFFFFFF
        return 2

    @jit_compile
    def exec_branch(self, instr: int) -> int:
        """Execute B/BL instruction."""
        is_link = (instr >> 24) & 1
        offset = instr & 0xFFFFFF
        if offset & 0x800000:
            offset |= 0xFF000000
        offset <<= 2

        if is_link:
            self.registers[14] = self.registers[15] + 4
        self.registers[15] = ((self.registers[15] + 8) + offset) & 0xFFFFFFFF
        return 3

    def exec_bx(self, instr: int) -> int:
        """Execute BX instruction."""
        rm = instr & 0xF
        target = self._operand(rm)
        self.thumb_mode = (target & 1) != 0
        self.registers[15] = target & 0xFFFFFFFE
        return 3

    def exec_block_transfer(self, instr: int) -> int:
        """Execute LDM/STM instruction.
        ARM encoding:
          bits 24: P (pre/post index)
          bit  23: U (up/down)
          bit  22: S (force user mode, or restore CPSR on LDM PC^)
          bit  21: W (writeback)
          bit  20: L (load/store)
          bits 19-16: Rn (base)
          bits 15-0:  register list
        """
        p_bit = (instr >> 24) & 1
        is_up = (instr >> 23) & 1
        s_bit = (instr >> 22) & 1
        is_load = (instr >> 20) & 1
        w_bit = (instr >> 21) & 1
        rn = (instr >> 16) & 0xF
        reg_list = instr & 0xFFFF

        if reg_list == 0:
            return 2

        base = self._operand(rn)
        n_regs = bin(reg_list).count('1')

        # Compute start address honoring pre/post index
        # ARM addressing modes (P=pre/post, U=up/down):
        #   IA (P=0,U=1): start at base, increment after each access
        #   IB (P=1,U=1): start at base+4, increment after each access
        #   DA (P=0,U=0): start at base-4*(n-1), increment after each access
        #   DB (P=1,U=0): start at base-4*n, increment after each access
        if p_bit:
            if is_up:
                addr = base + 4
            else:
                addr = base - 4 * n_regs
        else:
            if is_up:
                addr = base
            else:
                addr = base - 4 * (n_regs - 1)

        if is_load:
            for i in range(16):
                if reg_list & (1 << i):
                    val = self.memory.read_u32(addr)
                    self.write_register(i, val)
                    addr += 4
        else:
            for i in range(16):
                if reg_list & (1 << i):
                    val = self._operand(i)
                    self.memory.write_u32(addr, val & 0xFFFFFFFF)
                    addr += 4

        if w_bit:
            if is_up:
                self.registers[rn] = (base + n_regs * 4) & 0xFFFFFFFF
            else:
                self.registers[rn] = (base - n_regs * 4) & 0xFFFFFFFF

        if not (is_load and (reg_list & (1 << 15))):
            self.registers[15] += 4
        elif s_bit and self.mode in _MODES_WITH_SPSR:
            # LDM ... PC^: exception return — restore CPSR from SPSR.
            import sys as _sys
            _fc = getattr(_sys.modules.get('__main__', None), 'fc', -1)
            _mode_before = self.mode
            _sp_before = self.registers[13]
            _idx = _MODE_TO_SPSR_IDX.get(self.mode, -1)
            if 0 <= _idx < len(self.spsr):
                new_cpsr = self.spsr[_idx] & 0xFFFFFFFF
                new_mode = new_cpsr & 0x1F
                self._switch_mode(new_mode)
                self.cpsr = new_cpsr
                self.mode = new_mode
                self.thumb_mode = (new_cpsr >> 5) & 1
        return 2 + (n_regs * 2)

    @jit_compile
    def exec_mul(self, instr: int) -> int:
        rm = instr & 0xF
        rs = (instr >> 8) & 0xF
        rd = (instr >> 16) & 0xF
        rn = (instr >> 12) & 0xF
        is_long = (instr >> 23) & 1
        accumulate = (instr >> 21) & 1
        s_bit = (instr >> 20) & 1
        a = self._operand(rm)
        b = self._operand(rs)

        if is_long:
            rd_lo = (instr >> 12) & 0xF
            rd_hi = (instr >> 16) & 0xF
            is_signed = (instr >> 22) & 1
            if is_signed:
                sa = a if a < 0x80000000 else a - 0x100000000
                sb = b if b < 0x80000000 else b - 0x100000000
                result = sa * sb
            else:
                result = a * b
            result &= 0xFFFFFFFFFFFFFFFF
            if accumulate:
                acc = (self._operand(rd_hi) << 32) | self._operand(rd_lo)
                result = (result + acc) & 0xFFFFFFFFFFFFFFFF
            self.write_register(rd_lo, result & 0xFFFFFFFF)
            self.write_register(rd_hi, (result >> 32) & 0xFFFFFFFF)
            if s_bit:
                n = (result >> 63) & 1
                z = 1 if result == 0 else 0
                self.cpsr = (self.cpsr & 0x3FFFFFFF) | (n << 31) | (z << 30)
        else:
            result = (a * b) & 0xFFFFFFFF
            if accumulate:
                result = (result + self._operand(rn)) & 0xFFFFFFFF
            self.write_register(rd, result)
            if s_bit:
                n = (result >> 31) & 1
                z = 1 if result == 0 else 0
                self.cpsr = (self.cpsr & 0x3FFFFFFF) | (n << 31) | (z << 30)

        self.registers[15] += 4
        return 2

    @jit_compile
    def exec_swp(self, instr: int) -> int:
        is_byte = (instr >> 22) & 1
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        rm = instr & 0xF
        base = self._operand(rn)
        rm_val = self._operand(rm)
        if is_byte:
            old = self.memory.read_u8(base)
            self.memory.write_u8(base, rm_val & 0xFF)
        else:
            old = self.memory.read_u32(base)
            self.memory.write_u32(base, rm_val)
        self.write_register(rd, old)
        self.registers[15] += 4
        return 2

    def exec_swi(self, instr: int) -> int:
        """Execute SWI (software interrupt).
        GBA BIOS extracts the SWI number from bits 23:16 of the 24-bit
        comment field (mGBA: immediate >> 16)."""
        swi_num = (instr >> 16) & 0xFF
        print(f"PROBE swi num=0x{swi_num:02X} instr=0x{instr:08X} pc=0x{self.registers[15]:08X}", flush=True)
        self.swi_handler(swi_num)
        self.registers[15] += 4
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
        
        SWI exception entry (ARM hardware behavior):
        - Save CPSR to SPSR_svc
        - Save PC+4 to LR_svc (return address after SWI)
        - Switch to SVC mode (0x13) with IRQ disabled (I bit set)
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
        elif num == 0x02:  # Halt — wake on ANY enabled IRQ
            self._swi_lr = self.registers[14]
            self._swi_caller_pc = (self.registers[15] + (2 if self.thumb_mode else 4)) & 0xFFFFFFFF
            self._halted = True
            self._halt_reason = 'any'
        elif num == 0x03:  # Stop
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_stop(self.registers[0])
        elif num == 0x04:  # IntrWait — check IF first, then halt
            self._swi_lr = self.registers[14]
            self._swi_caller_pc = (self.registers[15] + (2 if self.thumb_mode else 4)) & 0xFFFFFFFF
            _wait_flag = self.registers[0] & 0xFF
            _ic = getattr(getattr(self, 'memory', None), '_interrupts', None)
            if _wait_flag & 0x01 and _ic is not None:
                _flag_mask = self.registers[1] & 0xFFFF
                _pending = _ic.if_reg & _flag_mask
                if _pending:
                    _ic.if_reg &= ~_pending
                    self.registers[0] = 1
                    self.cpsr |= (1 << 30)
                    return
            self._halted = True
            self._halt_reason = 'any'
        elif num == 0x05:  # VBlankIntrWait — wake on VBlank IRQ only
            self._swi_lr = self.registers[14]
            self._swi_caller_pc = (self.registers[15] + (2 if self.thumb_mode else 4)) & 0xFFFFFFFF
            # Per GBATEK: set IME=1, IE.0=1, clear IF.0, then halt until VBlank
            if hasattr(self, 'memory') and hasattr(self.memory, '_interrupts') and self.memory._interrupts is not None:
                ic = self.memory._interrupts
                ic.ime_reg |= 0x0001
                ic.ie_reg |= 0x0001
                ic.if_reg &= ~0x0001
                ic._enabled_mask = ic.ie_reg
                # Set DISPSTAT.3 so step_scanline fires vblank_irq()
                _ds = self.memory.read_u16(0x04000004)
                self.memory.write_u16(0x04000004, _ds | 0x0008)
            self._halted = True
            self._halt_reason = 'vblank'
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
                self.bios.swi_cpufastset(self.registers[0], self.registers[1], self.registers[2], self.registers[2])
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
        elif num == 0x10:  # BitUnPack
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_bit_unpack(self.registers[0], self.registers[1], self.registers[2])
        elif num == 0x13:  # HuffmanUnComp
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_huff_uncomp(self.registers[0], self.registers[1])
        elif num == 0x14:  # RLUnCompWram
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_rl_uncomp(self.registers[0], self.registers[1])
        elif num == 0x15:  # RLUnCompVram
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_rl_uncomp(self.registers[0], self.registers[1])
        elif num == 0x16:  # BitUnPackVram
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_bit_unpack(self.registers[0], self.registers[1], self.registers[2])
        elif num == 0x18:  # DiffUnCompFilterWrite
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_diff_uncomp_filter(self.registers[0], self.registers[1])

    def _swi_exception_entry(self):
        """Model ARM SWI exception entry.
        
        On SWI execution, real ARM hardware:
        1. Saves current CPSR to SPSR_svc
        2. Saves PC+4 to LR_svc (return address)
        3. Switches to SVC mode (0x13) with IRQ disabled (I bit set)
        
        This ensures that when an IRQ fires during SWI (e.g., during halt),
        the CPU has proper SVC-mode state, and IRQ entry can correctly
        save to IRQ banked registers without corrupting the SWI return address.
        
        Note: PC at this point is still the SWI instruction address. The caller
        (exec_swi) will increment PC by 4 after the handler returns.
        """
        # Save current CPSR to SPSR_svc (index 2 for mode 0x13)
        svc_spsr_idx = 2  # _MODE_TO_SPSR_IDX[0x13]
        self.spsr[svc_spsr_idx] = self.cpsr
        
        # Save return address to LR_svc
        # In ARM mode: return = PC + 4 (pipeline offset)
        # In Thumb mode: return = PC + 4 (SWI is 2 bytes, but return is PC+4)
        # At this point, PC is the SWI instruction address
        if self.thumb_mode:
            # Thumb SWI is 2 bytes, but exception return is PC+4
            return_addr = (self.registers[15] + 4) & 0xFFFFFFFF
        else:
            # ARM SWI is 4 bytes, return is PC+4
            return_addr = (self.registers[15] + 4) & 0xFFFFFFFF
        self.banked_sp_lr[0x13]['lr'] = return_addr
        
        # Switch to SVC mode (0x13)
        # The I bit (bit 7) should be set to disable IRQs, but we keep it simple
        self.cpsr = (self.cpsr & ~0x1F) | 0x13  # Set mode bits to 0x13 (SVC)
        
        # Perform mode switch to load SVC banked registers
        self._switch_mode(0x13)

    def execute_thumb(self, instr: int) -> int:
        """Execute Thumb instruction.

        Dispatch matches the ThumbDecoder format table in
        crates/gbatopy-disasm/src/thumb/mod.rs (instr >> 8 → format ranges).
        """
        op = instr >> 8  # bits 15-8

        if op <= 0x17:  # format 1: LSL/LSR/ASR Rd, Rs, #Offset5
            return self.exec_thumb_move_shift(instr)
        elif op <= 0x1F:  # format 2: ADD/SUB Rd, Rs, Rn/#Imm3
            return self.exec_thumb_add_sub(instr)
        elif op <= 0x3F:  # format 3: MOV/CMP/ADD/SUB Rd, #Imm8
            return self.exec_thumb_imm3(instr)
        elif op <= 0x43:  # format 4: ALU operations
            return self.exec_thumb_alu(instr)
        elif op <= 0x47:  # format 5: Hi register operations / BX
            return self.exec_thumb_hi(instr)
        elif op <= 0x4F:  # format 6: LDR Rd, [PC, #Imm8*4]
            return self.exec_thumb_pc_rel(instr)
        elif op <= 0x5F:  # format 7: Load/store with register offset
            return self.exec_thumb_load_store(instr)
        elif op <= 0x77:  # format 9: Load/store with immediate offset (word/byte)
            return self.exec_thumb_load_store_imm(instr)
        elif op <= 0x7F:  # format 10: Load/store halfword with immediate offset
            return self.exec_thumb_load_store_imm(instr)
        elif op <= 0x8F:  # format 9: Load/store with immediate offset (cont.)
            return self.exec_thumb_load_store_imm(instr)
        elif op <= 0x9F:  # format 11: Load/store SP-relative
            return self.exec_thumb_sp_rel(instr)
        elif op <= 0xAF:  # format 12: Load address (PC or SP + Imm8*4)
            return self.exec_thumb_load_addr(instr)
        elif op == 0xB0:  # format 13: ADD SP, #Imm7*4
            return self.exec_thumb_add_sp(instr)
        elif op <= 0xB5:  # format 14: PUSH {reglist, LR}
            return self.exec_thumb_push_pop(instr)
        elif op <= 0xBD:  # format 14: POP {reglist, PC}
            return self.exec_thumb_push_pop(instr)
        elif op <= 0xCF:  # format 15: LDM/STM
            return self.exec_thumb_ldm_stm(instr)
        elif op <= 0xDF:  # format 16: Conditional branch (cond 0xE) or SWI (cond 0xF)
            if (instr >> 8) == 0xDF:
                return self.exec_thumb_swi(instr)
            return self.exec_thumb_cond_branch(instr)
        elif op <= 0xEF:  # format 18: Unconditional branch
            return self.exec_thumb_branch(instr)
        elif op <= 0xF7:  # format 19: BL prefix
            return self.exec_thumb_bl_prefix(instr)
        else:  # 0xF8-0xFF: format 19: BL suffix
            return self.exec_thumb_bl_suffix(instr)

    def exec_thumb_move_shift(self, instr: int) -> int:
        """Thumb move shifted register (format 1: LSL/LSR/ASR Rd, Rs, #Offset5). Sets N, Z, C."""
        op = (instr >> 11) & 3
        offset = (instr >> 6) & 0x1F
        rs = (instr >> 3) & 7
        rd = instr & 7
        val = self.registers[rs]
        c = (self.cpsr >> 29) & 1
        if op == 0:  # LSL
            if offset == 0:
                result = val
            else:
                c = (val >> (32 - offset)) & 1
                result = (val << offset) & 0xFFFFFFFF
        elif op == 1:  # LSR
            if offset == 0:
                offset = 32
            c = (val >> (offset - 1)) & 1
            result = val >> offset
        elif op == 2:  # ASR
            if offset == 0:
                offset = 32
            c = (val >> (offset - 1)) & 1
            if val & 0x80000000:
                result = (val >> offset) | ((0xFFFFFFFF << (32 - offset)) & 0xFFFFFFFF)
            else:
                result = val >> offset
        self.write_register(rd, result)
        n = (result >> 31) & 1
        z = 1 if result == 0 else 0
        v = (self.cpsr >> 28) & 1
        self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        self.registers[15] += 2
        return 1

    def exec_thumb_add_sub(self, instr: int) -> int:
        """Thumb ADD/SUB (format 2). Sets N, Z, C, V."""
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
            c = 1 if op1 >= offset else 0
            v = 1 if ((op1 ^ offset) & (op1 ^ result) & 0x80000000) else 0
        else:
            result = (op1 + offset) & 0xFFFFFFFF
            c = 1 if result < op1 else 0
            v = 1 if ((~(op1 ^ offset) & 0xFFFFFFFF) & (op1 ^ result) & 0x80000000) else 0

        self.write_register(rd, result)
        n = (result >> 31) & 1
        z = 1 if result == 0 else 0
        self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        self.registers[15] += 2
        return 1

    def exec_thumb_imm3(self, instr: int) -> int:
        """Thumb MOV/CMP/ADD/SUB Rd, #Imm8 (format 3). All set N, Z; ADD/SUB/CMP also set C, V."""
        op = (instr >> 11) & 3  # bits 12-11
        rd = (instr >> 8) & 7   # bits 10-8
        imm8 = instr & 0xFF     # bits 7-0

        if op == 0:  # MOV Rd, #Imm8
            result = imm8 & 0xFFFFFFFF
            self.write_register(rd, result)
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            c = (self.cpsr >> 29) & 1
            v = (self.cpsr >> 28) & 1
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        elif op == 1:  # CMP Rd, #Imm8
            op1 = self.registers[rd]
            result = (op1 - imm8) & 0xFFFFFFFF
            c = 1 if op1 >= imm8 else 0
            v = 1 if ((op1 ^ imm8) & (op1 ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        elif op == 2:  # ADD Rd, #Imm8
            op1 = self.registers[rd]
            result = (op1 + imm8) & 0xFFFFFFFF
            self.write_register(rd, result)
            c = 1 if result < op1 else 0
            v = 1 if ((~(op1 ^ imm8) & 0xFFFFFFFF) & (op1 ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        elif op == 3:  # SUB Rd, #Imm8
            op1 = self.registers[rd]
            result = (op1 - imm8) & 0xFFFFFFFF
            self.write_register(rd, result)
            c = 1 if op1 >= imm8 else 0
            v = 1 if ((op1 ^ imm8) & (op1 ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)

        self.registers[15] += 2
        return 1

    def exec_thumb_alu(self, instr: int) -> int:
        """Thumb ALU operations. All set N and Z; arithmetic/shift ops also set C and V."""
        op = (instr >> 6) & 0xF
        rs = (instr >> 3) & 7
        rd = instr & 7

        val = self.registers[rs]
        rd_val = self.registers[rd]

        c = (self.cpsr >> 29) & 1
        v = (self.cpsr >> 28) & 1

        if op == 0:  # AND
            result = rd_val & val
        elif op == 1:  # EOR
            result = rd_val ^ val
        elif op == 2:  # LSL
            shift = val & 0xFF
            if shift == 0:
                result = rd_val
            elif shift < 32:
                c = (rd_val >> (32 - shift)) & 1
                result = (rd_val << shift) & 0xFFFFFFFF
            elif shift == 32:
                c = rd_val & 1
                result = 0
            else:
                c = 0
                result = 0
        elif op == 3:  # LSR
            shift = val & 0xFF
            if shift == 0:
                result = rd_val
            elif shift < 32:
                c = (rd_val >> (shift - 1)) & 1
                result = rd_val >> shift
            elif shift == 32:
                c = (rd_val >> 31) & 1
                result = 0
            else:
                c = 0
                result = 0
        elif op == 4:  # ASR
            shift = val & 0xFF
            if shift == 0:
                result = rd_val
            elif shift < 32:
                c = (rd_val >> (shift - 1)) & 1
                if rd_val & 0x80000000:
                    result = (rd_val >> shift) | ((0xFFFFFFFF << (32 - shift)) & 0xFFFFFFFF)
                else:
                    result = rd_val >> shift
            else:
                c = (rd_val >> 31) & 1
                result = 0xFFFFFFFF if rd_val & 0x80000000 else 0
        elif op == 5:  # ADC
            carry_in = (self.cpsr >> 29) & 1
            raw = rd_val + val + carry_in
            result = raw & 0xFFFFFFFF
            c = 1 if raw > 0xFFFFFFFF else 0
            v = 1 if ((rd_val ^ result) & (val ^ result) & 0x80000000) else 0
        elif op == 6:  # SBC
            carry_in = (self.cpsr >> 29) & 1
            not_c = 1 - carry_in
            result = (rd_val - val - not_c) & 0xFFFFFFFF
            c = 1 if rd_val >= (val + not_c) else 0
            v = 1 if ((rd_val ^ val) & (rd_val ^ result) & 0x80000000) else 0
        elif op == 7:  # ROR
            shift = val & 0x1F
            if shift == 0:
                c = (rd_val >> 31) & 1
                result = rd_val
            else:
                result = ((rd_val >> shift) | (rd_val << (32 - shift))) & 0xFFFFFFFF
                c = (rd_val >> (shift - 1)) & 1
        elif op == 8:  # TST
            result = rd_val & val
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
            self.registers[15] += 2
            return 1
        elif op == 9:  # NEG (RSB Rd, Rs, #0)
            result = (0 - val) & 0xFFFFFFFF
            c = 1 if val == 0 else 0
            v = 1 if (val & result & 0x80000000) else 0
        elif op == 0xA:  # CMP
            result = (rd_val - val) & 0xFFFFFFFF
            c = 1 if rd_val >= val else 0
            v = 1 if ((rd_val ^ val) & (rd_val ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
            self.registers[15] += 2
            return 1
        elif op == 0xB:  # CMN
            raw = rd_val + val
            result = raw & 0xFFFFFFFF
            c = 1 if raw > 0xFFFFFFFF else 0
            v = 1 if ((rd_val ^ result) & (val ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
            self.registers[15] += 2
            return 1
        elif op == 0xC:  # ORR
            result = rd_val | val
        elif op == 0xD:  # MUL
            result = (rd_val * val) & 0xFFFFFFFF
        elif op == 0xE:  # BIC
            result = rd_val & (~val & 0xFFFFFFFF)
        else:  # 0xF: MVN
            result = (~val) & 0xFFFFFFFF

        self.write_register(rd, result)
        n = (result >> 31) & 1
        z = 1 if result == 0 else 0
        self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        self.registers[15] += 2
        return 1

    def exec_thumb_hi(self, instr: int) -> int:
        """Thumb hi register operations/BX."""
        op = (instr >> 8) & 3
        rs = (instr >> 3) & 7
        rd = (instr >> 0) & 7
        h1 = (instr >> 7) & 1
        h2 = (instr >> 6) & 1

        if op == 3 and h1 == 0:  # BX
            rm_reg = rs + (h2 << 3)
            target = self._operand(rm_reg)
            self.thumb_mode = (target & 1) != 0
            self.registers[15] = target & 0xFFFFFFFE
            return 1

        if op == 3 and h1 == 1:  # BLX Rm
            rm_reg = rs + (h2 << 3)
            target = self._operand(rm_reg)
            self.registers[14] = (self.registers[15] + 2) | 1
            self.thumb_mode = (target & 1) != 0
            self.registers[15] = target & 0xFFFFFFFE
            return 1

        rdn = rd + (h1 << 3)
        rm = rs + (h2 << 3)

        if op == 0:  # ADD
            result = (self._operand(rdn) + self._operand(rm)) & 0xFFFFFFFF
            self.write_register(rdn, result)
        elif op == 1:  # CMP
            op1 = self._operand(rdn)
            op2 = self._operand(rm)
            result = (op1 - op2) & 0xFFFFFFFF
            
            # Set N flag (bit 31)
            n = (result >> 31) & 1
            # Set Z flag (bit 30)
            z = 1 if result == 0 else 0
            # Set C flag (bit 29): C=1 if op1 >= op2 (unsigned comparison)
            c = 1 if op1 >= op2 else 0
            # Set V flag (bit 28): overflow in signed subtraction
            v = 1 if ((op1 ^ op2) & (op1 ^ result) & 0x80000000) else 0
            
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        elif op == 2:  # MOV
            self.write_register(rdn, self._operand(rm))

        if rdn != 15:
            self.registers[15] += 2
        return 1

    def exec_thumb_pc_rel(self, instr: int) -> int:
        """Thumb PC-relative load."""
        rd = (instr >> 8) & 7
        offset = (instr & 0xFF) * 4
        addr = ((self.registers[15] + 4) & 0xFFFFFFFC) + offset
        val = self.memory.read_u32(addr)
        self.write_register(rd, val)
        self.registers[15] += 2
        return 2

    def exec_thumb_load_store(self, instr: int) -> int:
        """Thumb load/store with register offset (formats 7+8).

        Opcode bits 11-9 select the access type:
        000=STR, 001=STRH, 010=STRB, 011=LDSB, 100=LDR, 101=LDSH, 110=LDRB, 111=LDRH
        """
        op = (instr >> 9) & 7   # bits 11-9
        ro = (instr >> 6) & 7   # bits 8-6
        rb = (instr >> 3) & 7   # bits 5-3
        rd = instr & 7          # bits 2-0

        addr = (self.registers[rb] + self.registers[ro]) & 0xFFFFFFFF

        if op == 0:    # STR Rd, [Rb, Ro]
            self.memory.write_u32(addr, self.registers[rd])
        elif op == 1:  # STRH Rd, [Rb, Ro]
            self.memory.write_u16(addr, self.registers[rd] & 0xFFFF)
        elif op == 2:  # STRB Rd, [Rb, Ro]
            self.memory.write_u8(addr, self.registers[rd] & 0xFF)
        elif op == 3:  # LDSB Rd, [Rb, Ro] (sign-extended byte)
            val = self.memory.read_u8(addr)
            if val & 0x80:
                val |= 0xFFFFFF00
            self.write_register(rd, val)
        elif op == 4:  # LDR Rd, [Rb, Ro]
            self.write_register(rd, self.memory.read_u32(addr))
        elif op == 5:  # LDSH Rd, [Rb, Ro] (sign-extended halfword)
            val = self.memory.read_u16(addr)
            if val & 0x8000:
                val |= 0xFFFF0000
            self.write_register(rd, val)
        elif op == 6:  # LDRB Rd, [Rb, Ro]
            self.write_register(rd, self.memory.read_u8(addr))
        elif op == 7:  # LDRH Rd, [Rb, Ro]
            self.write_register(rd, self.memory.read_u16(addr))

        self.registers[15] += 2
        return 2

    def exec_thumb_load_store_imm(self, instr: int) -> int:
        """Thumb load/store with immediate offset (formats 9+10).

        Bits 15-11 select the access type:
        01100=STR word, 01101=LDR word, 01110=STRB, 01111=LDRB,
        10000=STRH, 10001=LDRH
        """
        op = (instr >> 11) & 0x1F  # bits 15-11
        imm5 = (instr >> 6) & 0x1F  # bits 10-6
        rb = (instr >> 3) & 7       # bits 5-3
        rd = instr & 7              # bits 2-0

        if op == 0b01100:  # STR Rd, [Rb, #Imm5*4]
            addr = self.registers[rb] + imm5 * 4
            self.memory.write_u32(addr, self.registers[rd])
        elif op == 0b01101:  # LDR Rd, [Rb, #Imm5*4]
            addr = self.registers[rb] + imm5 * 4
            self.write_register(rd, self.memory.read_u32(addr))
        elif op == 0b01110:  # STRB Rd, [Rb, #Imm5]
            addr = self.registers[rb] + imm5
            self.memory.write_u8(addr, self.registers[rd] & 0xFF)
        elif op == 0b01111:  # LDRB Rd, [Rb, #Imm5]
            addr = self.registers[rb] + imm5
            self.write_register(rd, self.memory.read_u8(addr))
        elif op == 0b10000:  # STRH Rd, [Rb, #Imm5*2]
            addr = self.registers[rb] + imm5 * 2
            self.memory.write_u16(addr, self.registers[rd] & 0xFFFF)
        elif op == 0b10001:  # LDRH Rd, [Rb, #Imm5*2]
            addr = self.registers[rb] + imm5 * 2
            self.write_register(rd, self.memory.read_u16(addr))

        self.registers[15] += 2
        return 2

    def exec_thumb_sp_rel(self, instr: int) -> int:
        """Thumb load/store SP-relative (format 11)."""
        is_load = (instr >> 11) & 1  # bit 11: 0=STR, 1=LDR
        rd = (instr >> 8) & 7        # bits 10-8
        imm8 = instr & 0xFF          # bits 7-0
        addr = (self.registers[13] + imm8 * 4) & 0xFFFFFFFF

        if is_load:
            self.write_register(rd, self.memory.read_u32(addr))
        else:
            self.memory.write_u32(addr, self.registers[rd])

        self.registers[15] += 2
        return 2

    def exec_thumb_load_addr(self, instr: int) -> int:
        """Thumb load address (format 12): ADD Rd, PC/SP, #Imm8*4."""
        use_sp = (instr >> 11) & 1  # bit 11: 0=PC, 1=SP
        rd = (instr >> 8) & 7       # bits 10-8
        imm8 = instr & 0xFF         # bits 7-0

        if use_sp:
            addr = (self.registers[13] + imm8 * 4) & 0xFFFFFFFF
        else:
            # Thumb PC reads as current instruction + 4
            pc = (self.registers[15] + 4) & 0xFFFFFFFF
            addr = ((pc & 0xFFFFFFFC) + imm8 * 4) & 0xFFFFFFFF
        self.write_register(rd, addr)
        self.registers[15] += 2
        return 1

    def exec_thumb_add_sp(self, instr: int) -> int:
        """Thumb add/sub offset to SP (format 13)."""
        sign = (instr >> 7) & 1  # bit 7: 0=ADD, 1=SUB
        imm7 = instr & 0x7F       # bits 6-0
        if sign:
            self.registers[13] = (self.registers[13] - imm7 * 4) & 0xFFFFFFFF
        else:
            self.registers[13] = (self.registers[13] + imm7 * 4) & 0xFFFFFFFF
        self.registers[15] += 2
        return 1

    def exec_thumb_push_pop(self, instr: int) -> int:
        """Thumb push/pop registers (format 14)."""
        op8 = (instr >> 8) & 0xFF
        is_pop = op8 in (0xBC, 0xBD)
        with_extra = op8 in (0xB5, 0xBD)  # LR for push, PC for pop
        reg_list = instr & 0xFF  # bits 7-0

        if is_pop:
            addr = self.registers[13]
            for i in range(8):
                if reg_list & (1 << i):
                    self.write_register(i, self.memory.read_u32(addr))
                    addr += 4
            if with_extra:
                val = self.memory.read_u32(addr)
                addr += 4
                self.thumb_mode = (val & 1) != 0
                self.registers[15] = val & 0xFFFFFFFE
                if self.mode in _MODES_WITH_SPSR:
                    # Write back SP before the mode switch so the banked SP
                    # (e.g. IRQ SP) is saved with its post-pop value.
                    self.registers[13] = addr
                    _idx = _MODE_TO_SPSR_IDX.get(self.mode, -1)
                    if 0 <= _idx < len(self.spsr):
                        new_cpsr = self.spsr[_idx] & 0xFFFFFFFF
                        new_mode = new_cpsr & 0x1F
                        self._switch_mode(new_mode)
                        self.cpsr = new_cpsr
                        self.mode = new_mode
                        self.thumb_mode = (new_cpsr >> 5) & 1
                    return 2
            else:
                self.registers[15] += 2
            self.registers[13] = addr
            return 2
        else:
            count = bin(reg_list).count('1') + (1 if with_extra else 0)
            addr = (self.registers[13] - count * 4) & 0xFFFFFFFF
            self.registers[13] = addr
            for i in range(8):
                if reg_list & (1 << i):
                    self.memory.write_u32(addr, self.registers[i])
                    addr += 4
            if with_extra:
                self.memory.write_u32(addr, self.registers[14])  # LR
            self.registers[15] += 2
            return 2

    def exec_thumb_ldm_stm(self, instr: int) -> int:
        """Thumb LDM/STM (format 15)."""
        is_load = (instr >> 11) & 1  # bit 11: 0=STM, 1=LDM
        rb = (instr >> 8) & 7        # bits 10-8
        reg_list = instr & 0xFF      # bits 7-0

        if reg_list == 0:
            self.registers[15] += 2
            return 1

        addr = self.registers[rb]
        base_in_list = (reg_list & (1 << rb)) != 0
        for i in range(8):
            if reg_list & (1 << i):
                if is_load:
                    self.write_register(i, self.memory.read_u32(addr))
                else:
                    self.memory.write_u32(addr, self.registers[i])
                addr += 4
        if not (is_load and base_in_list):
            self.registers[rb] = addr

        self.registers[15] += 2
        return 2

    def _check_condition(self, cond: int) -> bool:
        """Check ARM condition code."""
        n = (self.cpsr >> 31) & 1
        z = (self.cpsr >> 30) & 1
        c = (self.cpsr >> 29) & 1
        v = (self.cpsr >> 28) & 1

        if cond == 0x0:   # EQ
            return z == 1
        elif cond == 0x1: # NE
            return z == 0
        elif cond == 0x2: # CS/HS
            return c == 1
        elif cond == 0x3: # CC/LO
            return c == 0
        elif cond == 0x4: # MI
            return n == 1
        elif cond == 0x5: # PL
            return n == 0
        elif cond == 0x6: # VS
            return v == 1
        elif cond == 0x7: # VC
            return v == 0
        elif cond == 0x8: # HI
            return c == 1 and z == 0
        elif cond == 0x9: # LS
            return c == 0 or z == 1
        elif cond == 0xA: # GE
            return n == v
        elif cond == 0xB: # LT
            return n != v
        elif cond == 0xC: # GT
            return n == v and z == 0
        elif cond == 0xD: # LE
            return n != v or z == 1
        elif cond == 0xE: # AL
            return True
        return False       # NV

    def exec_thumb_cond_branch(self, instr: int) -> int:
        """Thumb conditional branch (format 16).
        
        Thumb conditional branch: bits 15-12 = cond (4 bits), bits 11-8 = unused/reversed,
        bits 7-0 = signed_offset8.
        
        Branch target = (PC + 4) + (sign_extend(offset8) << 1)
        Where PC = current instruction address (Thumb mode means PC is even)
        """
        cond = (instr >> 8) & 0xF  # bits 11-8 (condition code)
        offset = instr & 0xFF      # bits 7-0 (signed 8-bit offset)
        
        # Sign extend offset8 (8-bit to 32-bit signed)
        if offset & 0x80:
            offset -= 0x100
        
        # Branch target = (PC + 4) + (offset << 1) - offset is already sign-extended
        target = ((self.registers[15] + 4) + (offset << 1)) & 0xFFFFFFFE

        if self._check_condition(cond):
            self.registers[15] = target
        else:
            self.registers[15] += 2
        return 2

    def exec_thumb_branch(self, instr: int) -> int:
        """Thumb unconditional branch (format 18)."""
        offset = instr & 0x7FF  # bits 10-0
        if offset & 0x400:
            offset -= 0x800
        offset *= 2
        self.registers[15] = ((self.registers[15] + 4) + offset) & 0xFFFFFFFE
        return 2

    def exec_thumb_bl_prefix(self, instr: int) -> int:
        """Thumb BL prefix (format 19)."""
        offset_high = instr & 0x7FF  # bits 10-0
        if offset_high & 0x400:
            offset_high -= 0x800
        offset_high <<= 12
        # Thumb PC reads as current instruction + 4
        pc = (self.registers[15] + 4) & 0xFFFFFFFE
        self.registers[14] = (pc + offset_high) | 1
        self.registers[15] += 2
        return 1

    def exec_thumb_bl_suffix(self, instr: int) -> int:
        """Thumb BL suffix (format 19)."""
        offset_low = (instr & 0x7FF) << 1  # bits 10-0, *2
        target = (self.registers[14] & 0xFFFFFFFE) + offset_low
        # Return address = next instruction with Thumb bit set
        self.registers[14] = (self.registers[15] + 2) | 1
        self.registers[15] = target & 0xFFFFFFFE
        return 2

    def exec_thumb_swi(self, instr: int) -> int:
        """Thumb SWI (format 17)."""
        swi_num = instr & 0xFF
        if hasattr(self, 'swi_handler'):
            self.swi_handler(swi_num)
        self.registers[15] += 2
        return 1


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



