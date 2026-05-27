"""GBA CPU (ARM7TDMI) implementation"""

from typing import Any, Literal


class CPU:
    """ARM7TDMI CPU emulator state"""

    # Register names
    SP = 13  # Stack Pointer
    LR = 14  # Link Register
    PC = 15  # Program Counter

    # CPSR flag positions
    FLAG_N = 31  # Negative/Less than
    FLAG_Z = 30  # Zero
    FLAG_C = 29  # Carry/Borrow
    FLAG_V = 28  # Overflow
    FLAG_T = 5  # Thumb mode

    def __init__(self, memory=None):
        """Initialize CPU state"""
        self.registers: list[int] = [0] * 16
        self.memory = memory

        # CPSR flags as individual booleans
        self.flag_n: bool = False  # Negative
        self.flag_z: bool = False  # Zero
        self.flag_c: bool = False  # Carry
        self.flag_v: bool = False  # Overflow
        self.thumb_mode: bool = False  # T bit - Thumb mode

        # Cycle counter for interrupt-driven execution
        self.cycle_count: int = 0
        self.instruction_cycles: int = 1  # Default: 1 cycle per instruction (simplified)

    def reset(self, entry_point: int) -> None:
        """
        Reset CPU to initial state

        Args:
            entry_point: Initial PC value (typically 0x08000000 for GBA)
        """
        # Clear all registers
        for i in range(16):
            self.registers[i] = 0

        # Set stack pointer to IWRAM top (GBA convention)
        self.registers[self.SP] = 0x03007F00

        # Set PC to entry point
        self.registers[self.PC] = entry_point & 0xFFFFFFFF

        # Clear all CPSR flags
        self.flag_n = False
        self.flag_z = False
        self.flag_c = False
        self.flag_v = False
        self.thumb_mode = False

    def get_register(self, index: int) -> int:
        """
        Get value of register

        Args:
            index: Register index (0-15)

        Returns:
            32-bit register value
        """
        if 0 <= index <= 15:
            return self.registers[index]
        raise ValueError(f"Invalid register index: {index}")

    def set_register(self, index: int, value: int) -> None:
        """
        Set value of register

        Args:
            index: Register index (0-15)
            value: Value to set (will be masked to 32 bits)
        """
        if 0 <= index <= 15:
            self.registers[index] = value & 0xFFFFFFFF
        else:
            raise ValueError(f"Invalid register index: {index}")

    def get_cpsr_flag(self, flag: Literal["N", "Z", "C", "V"]) -> bool:
        """
        Get CPSR flag value

        Args:
            flag: Flag name (N, Z, C, or V)

        Returns:
            Flag boolean value
        """
        flag = flag.upper()
        if flag == "N":
            return self.flag_n
        elif flag == "Z":
            return self.flag_z
        elif flag == "C":
            return self.flag_c
        elif flag == "V":
            return self.flag_v
        else:
            raise ValueError(f"Invalid CPSR flag: {flag}. Must be N, Z, C, or V")

    def set_cpsr_flag(self, flag: Literal["N", "Z", "C", "V"], value: bool) -> None:
        """
        Set CPSR flag value

        Args:
            flag: Flag name (N, Z, C, or V)
            value: Boolean value to set
        """
        flag = flag.upper()
        if flag == "N":
            self.flag_n = bool(value)
        elif flag == "Z":
            self.flag_z = bool(value)
        elif flag == "C":
            self.flag_c = bool(value)
        elif flag == "V":
            self.flag_v = bool(value)
        else:
            raise ValueError(f"Invalid CPSR flag: {flag}. Must be N, Z, C, or V")

    def check_condition(self, cond: int) -> bool:
        """Check if ARM condition is satisfied (cond: 0-15)"""
        if cond == 0:
            return self.flag_z
        elif cond == 1:
            return not self.flag_z
        elif cond == 2:
            return self.flag_c
        elif cond == 3:
            return not self.flag_c
        elif cond == 4:
            return self.flag_n
        elif cond == 5:
            return not self.flag_n
        elif cond == 6:
            return self.flag_v
        elif cond == 7:
            return not self.flag_v
        elif cond == 8:
            return self.flag_c and not self.flag_z
        elif cond == 9:
            return not self.flag_c or self.flag_z
        elif cond == 10:
            return self.flag_n == self.flag_v
        elif cond == 11:
            return self.flag_n != self.flag_v
        elif cond == 12:
            return not self.flag_z and (self.flag_n == self.flag_v)
        elif cond == 13:
            return self.flag_z or (self.flag_n != self.flag_v)
        elif cond == 14:
            return True
        elif cond == 15:
            return False
        else:
            raise ValueError(f"Invalid condition code: {cond}. Must be 0-15")

    def step(self) -> int:
        """Execute one ARM or Thumb instruction"""
        if not self.memory:
            return 1

        # Fetch instruction
        pc = self.registers[self.PC]
        if self.thumb_mode:
            # Thumb mode (16-bit)
            opcode = self.memory.read_u16(pc & 0xFFFFFFFE)
            self.registers[self.PC] = (pc + 2) & 0xFFFFFFFF
            self._execute_thumb(opcode)
            return 1
        else:
            # ARM mode (32-bit)
            opcode = self.memory.read_u32(pc & 0xFFFFFFFC)
            self.registers[self.PC] = (pc + 4) & 0xFFFFFFFF
            self._execute_arm(opcode)
            return 1

    def _execute_arm(self, opcode: int) -> bool:
        """Execute one ARM instruction. Returns False to halt."""
        if opcode == 0 or opcode == 0xE1200070:  # NOP / reserved
            return True

        cond = (opcode >> 28) & 0xF
        if not self.check_condition(cond):
            return True

        # Check for B/BL
        if (opcode & 0xE000000) == 0xA000000:
            offset = opcode & 0xFFFFFF
            if offset & 0x800000:
                offset = -((~offset + 1) & 0xFFFFFF)
            target = self.registers[self.PC] + 4 + (offset << 2)
            if opcode & 0x01000000:  # BL
                self.registers[self.LR] = self.registers[self.PC]
            self.registers[self.PC] = target & 0xFFFFFFFF
            return True

        # Check for BX
        if (opcode & 0xFFFFFFF) == 0xE12FFF10:
            target = self.registers[opcode & 0xF]
            self.thumb_mode = bool(target & 1)
            self.registers[self.PC] = target & 0xFFFFFFFE
            return True

        # Data processing: bits 27-26 = 00
        if (opcode >> 26) & 3 == 0:
            return self._arm_data_processing(opcode)

        # Load/Store
        if (opcode >> 26) & 0x3 == 1:
            return self._arm_load_store(opcode)

        # Multiply
        if (opcode & 0xFC000F0) == 0x0:
            return self._arm_multiply(opcode)

        return True

    def _arm_data_processing(self, opcode: int) -> bool:
        """Execute ARM data processing instruction"""
        rn = (opcode >> 16) & 0xF
        rd = (opcode >> 12) & 0xF
        imm = (opcode >> 25) & 1

        # Get operands
        # Handle register shift (bit 4 = 1 means register shift)
        if imm:
            operand2 = opcode & 0xFF
            rotate = ((opcode >> 8) & 0xF) * 2
            operand2 = ((operand2 >> rotate) | (operand2 << (32 - rotate))) & 0xFFFFFFFF
        elif (opcode >> 4) & 1:  # Register shift
            rm = opcode & 0xF
            rs = (opcode >> 8) & 0xF  # Shift amount register
            shift_imm = self.registers[rs] & 0xFF
            operand2 = self.registers[rm]
            shift_type = (opcode >> 5) & 3
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
            rm = opcode & 0xF
            operand2 = self.registers[rm]
            shift_type = (opcode >> 5) & 3
            shift_imm = (opcode >> 7) & 0x1F
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

        op = (opcode >> 21) & 0xF
        s = (opcode >> 20) & 1

        if rn == 15:
            operand1 = self.registers[self.PC] + 4
        else:
            operand1 = self.registers[rn]

        result = 0
        update_flags = s == 1 and rd != 15

        # Opcode mapping
        if op == 0:  # AND
            result = operand1 & operand2
            self.registers[rd] = result
        elif op == 1:  # EOR
            result = operand1 ^ operand2
            self.registers[rd] = result
        elif op == 2:  # SUB
            result = (operand1 - operand2) & 0xFFFFFFFF
            self.registers[rd] = result
            if update_flags:
                self.flag_c = operand1 >= operand2
        elif op == 3:  # RSB
            result = (operand2 - operand1) & 0xFFFFFFFF
            self.registers[rd] = result
        elif op == 4:  # ADD
            result = (operand1 + operand2) & 0xFFFFFFFF
            self.registers[rd] = result
            if update_flags:
                self.flag_c = result < operand1
        elif op == 5:  # ADC
            c = 1 if self.flag_c else 0
            result = (operand1 + operand2 + c) & 0xFFFFFFFF
            self.registers[rd] = result
        elif op == 6:  # SBC
            c = 1 if self.flag_c else 0
            result = (operand1 - operand2 - c + 0x100000000) & 0xFFFFFFFF
            self.registers[rd] = result
        elif op == 8:  # TST
            result = operand1 & operand2
            update_flags = True
        elif op == 9:  # TEQ
            result = operand1 ^ operand2
            update_flags = True
        elif op == 10:  # CMP
            result = (operand1 - operand2) & 0xFFFFFFFF
            update_flags = True
            if update_flags:
                self.flag_c = operand1 >= operand2
        elif op == 11:  # CMN
            result = (operand1 + operand2) & 0xFFFFFFFF
            update_flags = True
        elif op == 12:  # ORR
            result = operand1 | operand2
            self.registers[rd] = result
        elif op == 13:  # MOV
            result = operand2
            self.registers[rd] = result
        elif op == 14:  # BIC
            result = operand1 & ~operand2
            self.registers[rd] = result
        elif op == 15:  # MVN
            result = (~operand2) & 0xFFFFFFFF
            self.registers[rd] = result

        if update_flags:
            self.flag_n = bool(result & 0x80000000)
            self.flag_z = result == 0

        return True

    def _arm_load_store(self, opcode: int) -> bool:
        """Execute ARM load/store instruction"""
        rd = (opcode >> 12) & 0xF
        rn = (opcode >> 16) & 0xF
        imm = (opcode >> 25) & 1
        load = (opcode >> 20) & 1
        byte = (opcode >> 22) & 1

        # Calculate address
        if imm:
            offset = opcode & 0xFFF
        elif (opcode >> 4) & 1:  # Register shift (bit 4 = 1)
            rm = opcode & 0xF
            offset = self.registers[rm]
        elif (opcode & 0xF) == 0:  # No register specified = no offset
            offset = 0
        else:
            rm = opcode & 0xF
            offset = self.registers[rm]

        addr = self.registers[rn]

        # Pre/post indexing
        add = (opcode >> 23) & 1
        write_back = (opcode >> 21) & 1

        if add:
            addr = (addr + offset) & 0xFFFFFFFF
        else:
            addr = (addr - offset) & 0xFFFFFFFF

        if load:
            if byte:
                val = self.memory.read_u8(addr)
            else:
                val = self.memory.read_u32(addr)
            self.registers[rd] = val
        else:
            val = self.registers[rd]
            if byte:
                self.memory.write_u8(addr, val & 0xFF)
            else:
                self.memory.write_u32(addr, val)

        if write_back:
            if add:
                self.registers[rn] = (self.registers[rn] + offset) & 0xFFFFFFFF
            else:
                self.registers[rn] = (self.registers[rn] - offset) & 0xFFFFFFFF

        return True

    def _arm_multiply(self, opcode: int) -> bool:
        """Execute ARM multiply instruction"""
        rd = (opcode >> 16) & 0xF
        rn = (opcode >> 12) & 0xF
        rs = (opcode >> 8) & 0xF
        rm = opcode & 0xF
        s = (opcode >> 20) & 1

        result = (self.registers[rm] * self.registers[rs]) & 0xFFFFFFFF

        if rn != 0:
            result = (result + self.registers[rn]) & 0xFFFFFFFF
            self.registers[rn] = result

        self.registers[rd] = result

        if s:
            self.flag_n = bool(result & 0x80000000)
            self.flag_z = result == 0

        return True

    def _execute_thumb(self, opcode: int) -> bool:
        """Execute one Thumb instruction"""
        # Check condition for branch
        if (opcode & 0xF000) == 0xD000:
            cond = (opcode >> 8) & 0xF
            if not self.check_condition(cond):
                return True
            offset = opcode & 0xFF
            if offset & 0x80:
                offset = -((~offset + 1) & 0xFF)
            self.registers[self.PC] = (self.registers[self.PC] + (offset << 1)) & 0xFFFFFFFF
            return True

        # Unconditional branch
        if (opcode & 0xF800) == 0xE000:
            offset = opcode & 0x7FF
            if offset & 0x400:
                offset = -((~offset + 1) & 0x7FF)
            self.registers[self.PC] = (self.registers[self.PC] + (offset << 1)) & 0xFFFFFFFF
            return True

        # BL/BLX (high word)
        if (opcode & 0xF000) == 0xF000:
            return True  # Simplified: just return

        # MOV immediate
        if (opcode & 0xF800) == 0x2000:
            rd = (opcode >> 8) & 0x7
            imm = opcode & 0xFF
            self.registers[rd] = imm
            return True

        # ADD register
        if (opcode & 0xFC00) == 0x1800:
            rd = (opcode >> 6) & 0x7
            rn = (opcode >> 3) & 0x7
            rm = opcode & 0x7
            self.registers[rd] = (self.registers[rn] + self.registers[rm]) & 0xFFFFFFFF
            return True

        # SUB immediate
        if (opcode & 0xFC00) == 0x1C00:
            rd = (opcode >> 6) & 0x7
            rn = (opcode >> 3) & 0x7
            imm = opcode & 0x7
            self.registers[rd] = (self.registers[rn] - imm) & 0xFFFFFFFF
            return True

        # LDR
        if (opcode & 0xF800) == 0x6800:
            rd = (opcode >> 8) & 0x7
            rn = (opcode >> 3) & 0x7
            offset = (opcode & 0x7) * 4
            addr = (self.registers[rn] + offset) & 0xFFFFFFFF
            self.registers[rd] = self.memory.read_u32(addr)
            return True

        # STR
        if (opcode & 0xF800) == 0x6000:
            rd = (opcode >> 8) & 0x7
            rn = (opcode >> 3) & 0x7
            offset = (opcode & 0x7) * 4
            addr = (self.registers[rn] + offset) & 0xFFFFFFFF
            self.memory.write_u32(addr, self.registers[rd])
            return True

        # CMP
        if (opcode & 0xF800) == 0x2800:
            rd = (opcode >> 8) & 0x7
            imm = opcode & 0xFF
            result = (self.registers[rd] - imm) & 0xFFFFFFFF
            self.flag_z = result == 0
            self.flag_n = bool(result & 0x80000000)
            return True

        # BX
        if (opcode & 0xFF00) == 0x4700:
            rm = (opcode >> 3) & 0xF
            target = self.registers[rm]
            self.thumb_mode = bool(target & 1)
            self.registers[self.PC] = target & 0xFFFFFFFE
            return True

        return True

    # DEAD CODE: SWI handlers not used by runtime (runtime uses ARM7TDMI class from arm7tdmi.py)
    def dump_registers(self, frame: int = None) -> dict:
        """
        Dump CPU register state to a dictionary.

        Returns:
            dict containing register values
        """
        return {
            "timestamp": frame if frame is not None else "unknown",
            "registers": [self.registers[i] for i in range(16)],
            "cpsr_flags": {
                "N": self.flag_n,
                "Z": self.flag_z,
                "C": self.flag_c,
                "V": self.flag_v,
                "T": self.thumb_mode,
            },
        }

    def dump_state(self) -> dict:
        return {
            "registers": list(self.registers),
            "flag_n": self.flag_n,
            "flag_z": self.flag_z,
            "flag_c": self.flag_c,
            "flag_v": self.flag_v,
            "thumb_mode": self.thumb_mode,
            "cycle_count": self.cycle_count,
            "instruction_cycles": self.instruction_cycles,
        }

    def load_state(self, state: dict) -> None:
        regs = state.get("registers", [0] * 16)
        for i in range(16):
            if i < len(regs):
                self.registers[i] = regs[i]

        if "flag_n" in state:
            self.flag_n = bool(state["flag_n"])
        if "flag_z" in state:
            self.flag_z = bool(state["flag_z"])
        if "flag_c" in state:
            self.flag_c = bool(state["flag_c"])
        if "flag_v" in state:
            self.flag_v = bool(state["flag_v"])
        if "thumb_mode" in state:
            self.thumb_mode = bool(state["thumb_mode"])
        if "cycle_count" in state:
            self.cycle_count = int(state["cycle_count"])
        if "instruction_cycles" in state:
            self.instruction_cycles = int(state["instruction_cycles"])

    def save_register_dump(self, dump: dict, filename: str = None) -> str:
        """
        Save register dump to JSON file.

        Args:
            dump: Register dump dictionary
            filename: Optional filename (without extension)

        Returns:
            Path to saved file
        """
        import json
        import os

        dump_dir = os.environ.get("GBATOPY_DUMP_DIR", ".")
        os.makedirs(dump_dir, exist_ok=True)

        if filename is None:
            filename = f"registers_{dump.get('timestamp', 'unknown')}"

        filepath = os.path.join(dump_dir, f"{filename}.json")
        with open(filepath, "w") as f:
            json.dump(dump, f, indent=2)

        return filepath


class RegisterDump:
    """Utility for dumping and comparing CPU register state."""

    def __init__(self, cpu: "CPU"):
        self.cpu = cpu
        self.dump_dir = None

    def set_dump_directory(self, directory: str):
        """Set the output directory for dump files."""
        self.dump_dir = directory

    def dump_registers(self, frame: int = None) -> dict:
        """
        Dump CPU registers to a dictionary.

        Returns:
            dict containing register values
        """
        return self.cpu.dump_registers(frame)

    def save_register_dump(self, dump: dict, filename: str = None) -> str:
        """
        Save register dump to JSON file.

        Args:
            dump: Register dump dictionary
            filename: Optional filename (without extension)

        Returns:
            Path to saved file
        """
        import json
        import os

        if self.dump_dir is None:
            raise ValueError("No dump directory set.")

        if filename is None:
            filename = f"registers_{dump.get('timestamp', 'unknown')}"

        os.makedirs(self.dump_dir, exist_ok=True)

        filepath = os.path.join(self.dump_dir, f"{filename}.json")
        with open(filepath, "w") as f:
            json.dump(dump, f, indent=2)

        return filepath

    def compare_registers(self, regs1: dict, regs2: dict) -> dict:
        """
        Compare two register dumps.

        Args:
            regs1: First register dump
            regs2: Second register dump

        Returns:
            dict with comparison results
        """
        differences = []

        if "registers" in regs1 and "registers" in regs2:
            for i in range(len(regs1["registers"])):
                if regs1["registers"][i] != regs2["registers"][i]:
                    differences.append({
                        "register": f"R{i}",
                        "value1": regs1["registers"][i],
                        "value2": regs2["registers"][i],
                    })

        if "cpsr_flags" in regs1 and "cpsr_flags" in regs2:
            for flag in ["N", "Z", "C", "V", "T"]:
                val1 = regs1["cpsr_flags"].get(flag, False)
                val2 = regs2["cpsr_flags"].get(flag, False)
                if val1 != val2:
                    differences.append({
                        "register": f"CPSR.{flag}",
                        "value1": val1,
                        "value2": val2,
                    })

        return {
            "differences_found": len(differences),
            "differences": differences,
        }

    def save_diff_report(self, comparison: dict, filename: str = None) -> str:
        """
        Save register comparison report to text file.

        Args:
            comparison: Result of compare_registers()
            filename: Optional filename (without extension)
        """
        import os
        if self.dump_dir is None:
            raise ValueError("No dump directory set.")

        if filename is None:
            filename = "register_comparison"

        filepath = os.path.join(self.dump_dir, f"{filename}.txt")
        with open(filepath, "w") as f:
            f.write("Register Comparison Report\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Differences found: {comparison['differences_found']}\n\n")

            if comparison["differences"]:
                f.write("Differences:\n")
                f.write("-" * 60 + "\n")
                for diff in comparison["differences"]:
                    f.write(f"\n{diff['register']}:\n")
                    f.write(f"  - Value 1: {diff['value1']}\n")
                    f.write(f"  - Value 2: {diff['value2']}\n")
            else:
                f.write("\nNo differences found.\n")

        return filepath
