"""
Minimal ARM7TDMI Interpreter for GBAtoPy
Implements common ARM instructions that are not codegen-ready
"""

class ARMInterpreter:
    def __init__(self, memory, rom_data):
        self.memory = memory  # bytearray or dict for memory
        self.rom_data = rom_data
        self.regs = [0] * 16  # R0-R15 (PC)
        self.cpsr = 0
        self.pc = 0x08000000  # Start at ROM base
        self.thumb = False
        
    def read_memory(self, addr):
        """Read 32-bit word from memory"""
        if addr >= 0x08000000 and addr < 0x08000000 + len(self.rom_data):
            offset = addr - 0x08000000
            return (self.rom_data[offset] | 
                   (self.rom_data[offset+1] << 8) | 
                   (self.rom_data[offset+2] << 16) | 
                   (self.rom_data[offset+3] << 24)) & 0xFFFFFFFF
        # Fallback to memory object if available
        if hasattr(self.memory, 'read_32'):
            return self.memory.read_32(addr)
        return 0
    
    def write_memory(self, addr, value):
        """Write 32-bit word to memory"""
        if addr >= 0x08000000 and addr < 0x08000000 + len(self.rom_data):
            offset = addr - 0x08000000
            if offset + 3 < len(self.rom_data):
                self.rom_data[offset] = value & 0xFF
                self.rom_data[offset+1] = (value >> 8) & 0xFF
                self.rom_data[offset+2] = (value >> 16) & 0xFF
                self.rom_data[offset+3] = (value >> 24) & 0xFF
    
    def execute_instruction(self, opcode):
        """Execute a single ARM instruction"""
        # Simple instruction decoder - handles common cases
        cond = (opcode >> 28) & 0xF
        # Check condition (simplified - always execute for now)
        if cond != 0xE and not self.check_condition(cond):
            self.pc += 4
            return
        
        op = (opcode >> 21) & 0xF
        rd = (opcode >> 12) & 0xF
        rn = (opcode >> 16) & 0xF
        rm = opcode & 0xF
        imm = opcode & 0xFF
        
        if op == 0x4 or op == 0x5:  # LDR/STR
            imm_flag = (opcode >> 25) & 1
            wback = (opcode >> 21) & 1
            if op == 0x4:  # LDR
                if imm_flag:
                    # LDR Rd, [Rn, #imm]
                    offset = opcode & 0xFFF
                    if not (opcode & 0x08000000):  # Not U flag
                        offset = -offset
                    addr = self.regs[rn] + offset
                    self.regs[rd] = self.read_memory(addr)
                else:
                    # LDR Rd, [Rn, Rm]
                    addr = self.regs[rn] + self.regs[rm]
                    self.regs[rd] = self.read_memory(addr)
            else:  # STR
                if imm_flag:
                    offset = opcode & 0xFFF
                    if not (opcode & 0x08000000):
                        offset = -offset
                    addr = self.regs[rn] + offset
                    self.write_memory(addr, self.regs[rd])
                else:
                    addr = self.regs[rn] + self.regs[rm]
                    self.write_memory(addr, self.regs[rd])
            
            if wback and rd != 13:
                self.regs[rn] = addr
                
        elif op == 0x0 and (opcode & 0x0FB00F00) == 0x00000900:  # LDM/STM
            # Simplified LDMIA/STMIA
            base = self.regs[rn]
            regs = (opcode & 0xFFFF)
            for i in range(16):
                if regs & (1 << i):
                    if op == 0x0:  # LDM
                        self.regs[i] = self.read_memory(base)
                    else:  # STM
                        self.write_memory(base, self.regs[i])
                    base += 4
            self.regs[rn] = base
            
        elif (opcode & 0x0E000000) == 0x0A000000:  # B/BL
            link = (opcode >> 24) & 1
            offset = opcode & 0xFFFFFF
            if offset & 0x00800000:
                offset |= 0xFF000000  # Sign extend
            offset <<= 2
            target = self.pc + offset + 4
            if link:
                self.regs[14] = self.pc + 4
            self.pc = target - 4  # Will be incremented after
            return  # Skip pc += 4
            
        elif (opcode & 0x0E000000) == 0x00000000:  # Data processing
            # Handle common data processing instructions
            pass
            
        self.pc += 4
        
    def check_condition(self, cond):
        """Check ARM condition code"""
        N = (self.cpsr >> 31) & 1
        Z = (self.cpsr >> 30) & 1
        C = (self.cpsr >> 29) & 1
        V = (self.cpsr >> 28) & 1
        
        if cond == 0x0: return Z == 1  # EQ
        if cond == 0x1: return Z == 0  # NE
        if cond == 0x2: return C == 1  # CS
        if cond == 0x3: return C == 0  # CC
        if cond == 0x4: return N == 1  # MI
        if cond == 0x5: return N == 0  # PL
        if cond == 0x6: return V == 1  # VS
        if cond == 0x7: return V == 0  # VC
        if cond == 0x8: return C == 1 and Z == 0  # HI
        if cond == 0x9: return C == 0 or Z == 1  # LS
        if cond == 0xA: return N == V  # GE
        if cond == 0xB: return N != V  # LT
        if cond == 0xC: return Z == 0 and N == V  # GT
        if cond == 0xD: return Z == 1 or N != V  # LE
        return True  # AL
        
    def run(self, max_instructions=10000):
        """Execute ROM until max_instructions or halt"""
        for _ in range(max_instructions):
            # Fetch instruction from ROM
            if self.pc >= 0x08000000 and self.pc < 0x08000000 + len(self.rom_data):
                offset = self.pc - 0x08000000
                if offset + 3 < len(self.rom_data):
                    opcode = (self.rom_data[offset] | 
                             (self.rom_data[offset+1] << 8) | 
                             (self.rom_data[offset+2] << 16) | 
                             (self.rom_data[offset+3] << 24))
                    self.execute_instruction(opcode)
                else:
                    break
            else:
                break

# Template usage:
# interpreter = ARMInterpreter(memory, ROM_DATA)
# interpreter.run(60000)  # Run for ~60 frames
