use gbatopy_disasm::{DecodedInstruction, Disassembler};
use std::fs;

use crate::apu;

/// Generate Python code for a single ARM/Thumb instruction
fn generate_instruction_python(instr: &DecodedInstruction) -> String {
    let mut code = String::new();

    // Add comment with original instruction
    code.push_str(&format!(
        "# 0x{:08X}: {} {}\n",
        instr.address,
        instr.opcode,
        instr
            .operands
            .iter()
            .map(|o| o.display())
            .collect::<Vec<_>>()
            .join(", ")
    ));

    // Generate code based on opcode
    match instr.opcode.to_uppercase().as_str() {
        "MOV" => code.push_str(&generate_mov_python(instr)),
        "ADD" => code.push_str(&generate_add_python(instr)),
        "SUB" => code.push_str(&generate_sub_python(instr)),
        "LDR" => code.push_str(&generate_ldr_python(instr)),
        "STR" => code.push_str(&generate_str_python(instr)),
        "LDM" | "LDMIA" | "LDMIB" | "LDMDA" | "LDMDB" | "LDM!" | "LDMIA!" | "LDMIB!" | "LDMDA!"
        | "LDMDB!" => code.push_str(&generate_ldm_python(instr)),
        "STM" | "STMIA" | "STMIB" | "STMDA" | "STMDB" | "STM!" | "STMIA!" | "STMIB!" | "STMDA!"
        | "STMDB!" => code.push_str(&generate_stm_python(instr)),
        "STRH" => code.push_str(&generate_strh_python(instr)),
        "B" | "BL" => code.push_str(&generate_branch_python(instr)),
        "BX" => code.push_str(&generate_bx_python(instr)),
        "AND" | "EOR" | "ORR" | "BIC" | "MVN" => {
            code.push_str(&generate_logic_python(instr));
        }
        "NOP" => code.push_str("pass  # NOP\n"),
        _ => {
            // Unimplemented instruction
            code.push_str(&format!("pass  # TODO: {} not implemented\n", instr.opcode));
        }
    }

    code
}

/// Generate Python for MOV Rd, #imm or MOV Rd, Rm
fn generate_mov_python(instr: &DecodedInstruction) -> String {
    if instr.operands.len() >= 2 {
        let rd = instr.operands[0].display();
        let rm_or_imm = instr.operands[1].display();

        // Check if second operand is immediate or register
        if rm_or_imm.starts_with("#") {
            // MOV Rd, #imm
            let imm = rm_or_imm.trim_start_matches("#");
            format!("{} = {}  # MOV Rd, #imm\n", rd, imm)
        } else {
            // MOV Rd, Rm
            format!("{} = {}  # MOV Rd, Rm\n", rd, rm_or_imm)
        }
    } else {
        format!("pass  # MOV: insufficient operands\n")
    }
}

/// Generate Python for ADD Rd, Rm, #imm or ADD Rd, Rm, Rn
fn generate_add_python(instr: &DecodedInstruction) -> String {
    if instr.operands.len() >= 2 {
        let rd = instr.operands[0].display();
        if instr.operands.len() == 2 {
            // ADD Rd, Rm (Rd = Rd + Rm)
            format!(
                "{} = {} + {}  # ADD Rd, Rm\n",
                rd,
                rd,
                instr.operands[1].display()
            )
        } else {
            // ADD Rd, Rn, #imm or ADD Rd, Rn, Rm
            let op2_raw = instr.operands[2].display();
            let op2 = op2_raw.trim_start_matches('#');
            format!(
                "{} = {} + {}  # ADD\n",
                rd,
                instr.operands[1].display(),
                op2
            )
        }
    } else {
        format!("pass  # ADD: insufficient operands\n")
    }
}

/// Generate Python for SUB
fn generate_sub_python(instr: &DecodedInstruction) -> String {
    if instr.operands.len() >= 2 {
        let rd = instr.operands[0].display();
        let op1_raw = instr.operands[1].display();
        let op1 = op1_raw.trim_start_matches('#');
        format!("{} = {} - {}  # SUB\n", rd, rd, op1)
    } else {
        format!("pass  # SUB: insufficient operands\n")
    }
}

/// Generate Python for LDR
fn generate_ldr_python(instr: &DecodedInstruction) -> String {
    if instr.operands.len() < 2 {
        return format!("pass  # LDR: insufficient operands\n");
    }

    let rd = instr.operands[0].display();
    let base = instr.operands[1].display();

    // Handle PC-relative LDR Rd, =addr
    if base.starts_with("=") {
        let addr_str = base.trim_start_matches("=");
        if let Ok(addr) = addr_str.parse::<u32>() {
            format!(
                "{} = ROM_DATA[0x{:X} - 0x08000000]  # LDR Rd, =addr (PC-relative)\n",
                rd, addr
            )
        } else {
            format!("{} = 0  # LDR Rd, ={} (unresolved)\n", rd, addr_str)
        }
    } else if base.starts_with("#") {
        // LDR Rd, #addr (load from absolute address - treat as ROM_DATA access)
        let addr_str = base.trim_start_matches("#");
        if let Ok(addr) = addr_str.parse::<u32>() {
            if addr >= 0x08000000 && addr < 0x0C000000 {
                let offset = addr - 0x08000000;
                format!("{} = ROM_DATA[{}]  # LDR Rd, #addr\n", rd, offset)
            } else {
                format!("{} = memory.read_32({})  # LDR Rd, #addr\n", rd, addr)
            }
        } else {
            format!("{} = 0  # LDR Rd, #{} (unresolved)\n", rd, addr_str)
        }
    } else {
        // LDR Rd, [Rn] or LDR Rd, [Rn, #offset] or LDR Rd, [Rn, Rm]
        let addr = if instr.operands.len() >= 3 {
            let offset_raw = instr.operands[2].display();
            let offset = offset_raw.trim_start_matches('#');
            format!("{} + {}", base, offset)
        } else {
            base.clone()
        };
        format!("{} = memory.read_32({})  # LDR\n", rd, addr)
    }
}

/// Generate Python for STR
fn generate_str_python(instr: &DecodedInstruction) -> String {
    if instr.operands.len() < 2 {
        return format!("pass  # STR: insufficient operands\n");
    }

    let rm = instr.operands[0].display();
    let base = instr.operands[1].display();

    // Calculate address: base + offset (if present)
    let addr = if instr.operands.len() >= 3 {
        let offset_raw = instr.operands[2].display();
        let offset = offset_raw.trim_start_matches('#');
        if offset_raw.starts_with('#') {
            format!("{} + {}", base, offset) // No extra parens - write_32 adds them
        } else {
            format!("{} + {}", base, offset)
        }
    } else {
        base.clone()
    };

    // STR Rm, [Rn] or STR Rm, [Rn, #offset]
    format!("memory.write_32({}, {})  # STR\n", addr, rm)
}

/// Generate Python for STRH (store halfword)
fn generate_strh_python(instr: &DecodedInstruction) -> String {
    if instr.operands.len() < 2 {
        return format!("pass  # STRH: insufficient operands\n");
    }

    let rm = instr.operands[0].display();
    let base = instr.operands[1].display();

    let addr = if instr.operands.len() >= 3 {
        let offset_raw = instr.operands[2].display();
        let offset = offset_raw.trim_start_matches('#');
        format!("{} + {}", base, offset)
    } else {
        base.clone()
    };

    // Check if this is a VRAM write (0x06000000-0x06017FFF)
    // Generate ppu.vram_write(offset, value) for VRAM addresses
    format!(
        "if 0x06000000 <= {} < 0x06018000: ppu.vram_write({} - 0x06000000, {})  # STRH to VRAM\nelse: memory.write_u16({}, {})  # STRH\n",
        addr, addr, rm, addr, rm
    )
}

/// Generate Python for branch instructions
fn generate_branch_python(instr: &DecodedInstruction) -> String {
    // Branch handling - update PC (r15)
    // For now, just comment - actual branching needs more complex logic
    format!(
        "pass  # Branch instruction {} at 0x{:08X} - TODO: implement branching\n",
        instr.opcode, instr.address
    )
}

/// Generate Python for BX (branch exchange)
fn generate_bx_python(instr: &DecodedInstruction) -> String {
    // BX Rn - switch mode and branch
    format!(
        "pass  # BX instruction at 0x{:08X} - TODO: implement mode switch\n",
        instr.address
    )
}

/// Generate Python for logical instructions
fn generate_logic_python(instr: &DecodedInstruction) -> String {
    if instr.operands.len() >= 2 {
        let opcode = instr.opcode.to_uppercase();
        let rd = instr.operands[0].display();
        let rm = instr.operands[1].display();

        // Map opcode to Python operator
        let op = match opcode.as_str() {
            "AND" => "&",
            "EOR" => "^",
            "ORR" => "|",
            "BIC" => "& ~",
            "MVN" => "~",
            _ => "&",
        };

        if opcode == "MVN" {
            // MVN Rd, Rm: Rd = NOT Rm (unary)
            format!("{} = {} {}  # {}\n", rd, op, rm, opcode)
        } else {
            // Binary operations: Rd = Rd op Rm
            format!("{} = {} {} {}  # {}\n", rd, rd, op, rm, opcode)
        }
    } else {
        format!("pass  # {}: insufficient operands\n", instr.opcode)
    }
}

pub fn run_pipeline(
    rom_path: &str,
    output_path: &str,
    _assets_dir: &std::path::Path,
    _use_ir: bool,
) -> Result<(), String> {
    let rom = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    eprintln!("Step 1: Disassembly");
    let mut disasm = Disassembler::new();
    let instructions = disasm.disassemble(&rom, 0x08000000);
    eprintln!("  Disassembled {} instructions", instructions.len());

    eprintln!("Step 2: Asset Extraction");
    let assets = extract_assets(&rom);

    eprintln!("Step 3: Python Code Generation");

    // Generate ARM instruction codegen - collect instructions first
    eprintln!(
        "  Generating code for {} instructions...",
        instructions.len()
    );
    let mut instruction_count = 0;
    let max_instructions = 100000; // Safety limit
    let mut instruction_code = String::new();

    for instr in &instructions {
        if instruction_count >= max_instructions {
            eprintln!("  Warning: Reached max instructions ({})", max_instructions);
            break;
        }

        // Skip data regions
        if instr.is_data {
            continue;
        }

        // Generate Python for this instruction
        let python_code = generate_instruction_python(instr);
        instruction_code.push_str(&python_code);
        instruction_count += 1;
    }
    eprintln!("  Generated Python for {} instructions", instruction_count);

    // Now build the complete output in correct order:
    // 1. Classes (Memory, GBA)
    // 2. Global variables (registers)
    // 3. Instructions
    // 4. Assets and ROM data
    // 5. Game loop

    let mut code = String::new();

    // 1. Classes first
    code.push_str("# Memory object for backward compatibility\n");
    code.push_str("class Memory:\n");
    code.push_str("    def __init__(self, gba):\n");
    code.push_str("        self.gba = gba\n");
    code.push_str("    \n");
    code.push_str("    def read_32(self, addr):\n");
    code.push_str("        if isinstance(addr, int):\n");
    code.push_str("            if 0x08000000 <= addr < 0x0C000000:  # ROM\n");
    code.push_str("                idx = addr - 0x08000000\n");
    code.push_str("                if idx + 3 < len(ROM_DATA):\n");
    code.push_str("                    return ROM_DATA[idx] | (ROM_DATA[idx+1] << 8) | (ROM_DATA[idx+2] << 16) | (ROM_DATA[idx+3] << 24)\n");
    code.push_str("            elif 0x06000000 <= addr < 0x06020000:  # VRAM\n");
    code.push_str("                idx = addr - 0x06000000\n");
    code.push_str("                if idx + 3 < len(self.gba.vram):\n");
    code.push_str("                    return self.gba.vram[idx] | (self.gba.vram[idx+1] << 8) | (self.gba.vram[idx+2] << 16) | (self.gba.vram[idx+3] << 24)\n");
    code.push_str("            elif 0x04000000 <= addr < 0x04000400:  # MMIO\n");
    code.push_str("                return self.gba.read_io(addr - 0x04000000)\n");
    code.push_str("            elif 0x02000000 <= addr < 0x02040000:  # EWRAM\n");
    code.push_str("                idx = addr - 0x02000000\n");
    code.push_str("                if idx + 3 < len(self.gba.ewram):\n");
    code.push_str("                    return self.gba.ewram[idx] | (self.gba.ewram[idx+1] << 8) | (self.gba.ewram[idx+2] << 16) | (self.gba.ewram[idx+3] << 24)\n");
    code.push_str("        return 0\n");
    code.push_str("    \n");
    code.push_str("    def write_32(self, addr, value):\n");
    code.push_str("        if isinstance(addr, int):\n");
    code.push_str("            if 0x06000000 <= addr < 0x06020000:  # VRAM\n");
    code.push_str("                idx = addr - 0x06000000\n");
    code.push_str("                if idx + 3 < len(self.gba.vram):\n");
    code.push_str("                    self.gba.vram[idx] = value & 0xFF\n");
    code.push_str("                    self.gba.vram[idx+1] = (value >> 8) & 0xFF\n");
    code.push_str("                    self.gba.vram[idx+2] = (value >> 16) & 0xFF\n");
    code.push_str("                    self.gba.vram[idx+3] = (value >> 24) & 0xFF\n");
    code.push_str("            elif 0x04000000 <= addr < 0x04000400:  # MMIO\n");
    code.push_str("                self.gba.write_io(addr - 0x04000000, value)\n");
    code.push_str("            elif 0x02000000 <= addr < 0x02040000:  # EWRAM\n");
    code.push_str("                idx = addr - 0x02000000\n");
    code.push_str("                if idx + 3 < len(self.gba.ewram):\n");
    code.push_str("                    self.gba.ewram[idx] = value & 0xFF\n");
    code.push_str("                    self.gba.ewram[idx+1] = (value >> 8) & 0xFF\n");
    code.push_str("                    self.gba.ewram[idx+2] = (value >> 16) & 0xFF\n");
    code.push_str("                    self.gba.ewram[idx+3] = (value >> 24) & 0xFF\n");
    code.push_str("    \n");
    code.push_str("    def write_u16(self, addr, value):\n");
    code.push_str("        if isinstance(addr, int):\n");
    code.push_str("            if 0x06000000 <= addr < 0x06020000:  # VRAM\n");
    code.push_str("                idx = addr - 0x06000000\n");
    code.push_str("                if idx + 1 < len(self.gba.vram):\n");
    code.push_str("                    self.gba.vram[idx] = value & 0xFF\n");
    code.push_str("                    self.gba.vram[idx+1] = (value >> 8) & 0xFF\n");
    code.push_str("            elif 0x04000000 <= addr < 0x04000400:  # MMIO\n");
    code.push_str("                self.gba.write_io(addr - 0x04000000, value)\n");
    code.push_str("            elif 0x02000000 <= addr < 0x02040000:  # EWRAM\n");
    code.push_str("                idx = addr - 0x02000000\n");
    code.push_str("                if idx + 1 < len(self.gba.ewram):\n");
    code.push_str("                    self.gba.ewram[idx] = value & 0xFF\n");
    code.push_str("                    self.gba.ewram[idx+1] = (value >> 8) & 0xFF\n");
    code.push_str("\n");
    code.push_str("memory = None  # Will be initialized in run_transpiled\n\n");

    // 2. Global variables (registers)
    code.push_str("# Global ARM registers\n");
    code.push_str("r0 = r1 = r2 = r3 = r4 = r5 = r6 = r7 = 0\n");
    code.push_str("r8 = r9 = r10 = r11 = r12 = r13 = r14 = r15 = 0\n");
    code.push_str("cpsr = 0\nspsr = 0\n\n");

    // 3. Instructions wrapped in main function
    code.push_str("def main():\n");
    code.push_str("    # Load assets into GBA memory before executing ROM code\n");
    code.push_str("    _load_assets(gba)\n");
    for line in instruction_code.lines() {
        code.push_str("    ");
        code.push_str(line);
        code.push('\n');
    }
    code.push_str("\n");

    // 4. Assets and ROM data

    code.push_str("# Extracted Assets from ROM\n");

    // Write TILES_4BPP (runtime expects this name)
    code.push_str("TILES_4BPP = bytearray([\n");
    for (_i, byte) in assets.tile_data.iter().enumerate() {
        code.push_str(format!("    0x{:02X},\n", byte).as_str());
    }
    code.push_str("])\n\n");

    // Write PALETTE_BG (runtime expects this name)
    code.push_str("PALETTE_BG = bytearray([\n");
    for (_i, byte) in assets.palette_data.iter().enumerate() {
        code.push_str(format!("    0x{:02X},\n", byte).as_str());
    }
    code.push_str("])\n\n");

    // Write TILEMAP (runtime expects this name)
    if !assets.tilemap_data.is_empty() {
        code.push_str("TILEMAP = bytearray([\n");
        for (_i, byte) in assets.tilemap_data.iter().enumerate() {
            code.push_str(format!("    0x{:02X},\n", byte).as_str());
        }
        code.push_str("])\n\n");
    }

    // Add asset loading code after assets are defined
    code.push_str("# Load assets into GBA memory at startup\n");
    code.push_str("def _load_assets(gba):\n");
    code.push_str("    \"\"\"Load extracted assets into GBA memory\"\"\"\n");
    code.push_str("    if 'TILES_4BPP' in globals() and TILES_4BPP:\n");
    code.push_str("        for i, byte in enumerate(TILES_4BPP):\n");
    code.push_str("            gba.vram[i] = byte\n");
    code.push_str("    if 'PALETTE_BG' in globals() and PALETTE_BG:\n");
    code.push_str("        for i in range(0, len(PALETTE_BG), 2):\n");
    code.push_str("            color = (PALETTE_BG[i] << 8) | PALETTE_BG[i + 1]\n");
    code.push_str("            gba.palette[i // 2] = color\n");
    code.push_str("    if 'TILEMAP' in globals() and TILEMAP:\n");
    code.push_str("        for i, byte in enumerate(TILEMAP):\n");
    code.push_str("            gba.vram[0x1800 + i] = byte\n");
    code.push_str("\n");

    // Write full ROM
    code.push_str("ROM_DATA = bytearray([");
    let mut first = true;
    for byte in rom.iter() {
        if !first {
            code.push_str(", ");
        }
        code.push_str(&format!("0x{:02X}", byte));
        first = false;
    }
    code.push_str("])\n\n");

    code.push_str("func_map = {}\n\n");
    code.push_str("# Memory object for backward compatibility\n");
    code.push_str("class Memory:\n");
    code.push_str("    def __init__(self, gba):\n");
    code.push_str("        self.gba = gba\n");
    code.push_str("    \n");
    code.push_str("    def read_32(self, addr):\n");
    code.push_str("        if isinstance(addr, int):\n");
    code.push_str("            if 0x08000000 <= addr < 0x0C000000:  # ROM\n");
    code.push_str("                idx = addr - 0x08000000\n");
    code.push_str("                if idx + 3 < len(ROM_DATA):\n");
    code.push_str("                    return ROM_DATA[idx] | (ROM_DATA[idx+1] << 8) | (ROM_DATA[idx+2] << 16) | (ROM_DATA[idx+3] << 24)\n");
    code.push_str("            elif 0x06000000 <= addr < 0x06020000:  # VRAM\n");
    code.push_str("                idx = addr - 0x06000000\n");
    code.push_str("                if idx + 3 < len(self.gba.vram):\n");
    code.push_str("                    return self.gba.vram[idx] | (self.gba.vram[idx+1] << 8) | (self.gba.vram[idx+2] << 16) | (self.gba.vram[idx+3] << 24)\n");
    code.push_str("            elif 0x04000000 <= addr < 0x04000400:  # MMIO\n");
    code.push_str("                return self.gba.read_io(addr - 0x04000000)\n");
    code.push_str("            elif 0x02000000 <= addr < 0x02040000:  # EWRAM\n");
    code.push_str("                idx = addr - 0x02000000\n");
    code.push_str("                if idx + 3 < len(self.gba.ewram):\n");
    code.push_str("                    return self.gba.ewram[idx] | (self.gba.ewram[idx+1] << 8) | (self.gba.ewram[idx+2] << 16) | (self.gba.ewram[idx+3] << 24)\n");
    code.push_str("        return 0\n");
    code.push_str("    \n");
    code.push_str("    def write_32(self, addr, value):\n");
    code.push_str("        if isinstance(addr, int):\n");
    code.push_str("            if 0x06000000 <= addr < 0x06020000:  # VRAM\n");
    code.push_str("                idx = addr - 0x06000000\n");
    code.push_str("                if idx + 3 < len(self.gba.vram):\n");
    code.push_str("                    self.gba.vram[idx] = value & 0xFF\n");
    code.push_str("                    self.gba.vram[idx+1] = (value >> 8) & 0xFF\n");
    code.push_str("                    self.gba.vram[idx+2] = (value >> 16) & 0xFF\n");
    code.push_str("                    self.gba.vram[idx+3] = (value >> 24) & 0xFF\n");
    code.push_str("            elif 0x04000000 <= addr < 0x04000400:  # MMIO\n");
    code.push_str("                self.gba.write_io(addr - 0x04000000, value)\n");
    code.push_str("            elif 0x02000000 <= addr < 0x02040000:  # EWRAM\n");
    code.push_str("                idx = addr - 0x02000000\n");
    code.push_str("                if idx + 3 < len(self.gba.ewram):\n");
    code.push_str("                    self.gba.ewram[idx] = value & 0xFF\n");
    code.push_str("                    self.gba.ewram[idx+1] = (value >> 8) & 0xFF\n");
    code.push_str("                    self.gba.ewram[idx+2] = (value >> 16) & 0xFF\n");
    code.push_str("                    self.gba.ewram[idx+3] = (value >> 24) & 0xFF\n");
    code.push_str("    \n");
    code.push_str("    def write_u16(self, addr, value):\n");
    code.push_str("        if isinstance(addr, int):\n");
    code.push_str("            if 0x06000000 <= addr < 0x06020000:  # VRAM\n");
    code.push_str("                idx = addr - 0x06000000\n");
    code.push_str("                if idx + 1 < len(self.gba.vram):\n");
    code.push_str("                    self.gba.vram[idx] = value & 0xFF\n");
    code.push_str("                    self.gba.vram[idx+1] = (value >> 8) & 0xFF\n");
    code.push_str("            elif 0x04000000 <= addr < 0x04000400:  # MMIO\n");
    code.push_str("                self.gba.write_io(addr - 0x04000000, value)\n");
    code.push_str("            elif 0x02000000 <= addr < 0x02040000:  # EWRAM\n");
    code.push_str("                idx = addr - 0x02000000\n");
    code.push_str("                if idx + 1 < len(self.gba.ewram):\n");
    code.push_str("                    self.gba.ewram[idx] = value & 0xFF\n");
    code.push_str("                    self.gba.ewram[idx+1] = (value >> 8) & 0xFF\n");
    code.push_str("\n");
    code.push_str("memory = None  # Will be initialized in run_transpiled\n\n");
    code.push_str(&apu::generate_apu_code());
    code.push_str("\n\n");
    code.push_str(
        r#"
# Game Loop - Minimal GBA Emulator
import pygame
import sys

class GBA:
    def __init__(self, rom_data):
        self.vram = bytearray(0x18000)  # 96KB VRAM
        self.palette = bytearray(0x400)  # 1KB palette
        self.oam = bytearray(0x400)  # 1KB OAM
        self.io = bytearray(0x400)  # MMIO
        self.ewram = bytearray(0x40000)  # 256KB EWRAM
        
        # Load embedded assets if available
        if 'VRAM_DATA' in dir() and VRAM_DATA:
            self.vram[:len(VRAM_DATA)] = VRAM_DATA
        if 'PALETTE_DATA' in dir() and PALETTE_DATA:
            self.palette[:len(PALETTE_DATA)] = PALETTE_DATA
        if 'TILEMAP_DATA' in dir() and TILEMAP_DATA:
            # Copy tilemap to appropriate VRAM location
            pass
        
        # Initialize APU for audio
        self.apu = APU(self)
        
    def write_io(self, addr, value):
        """Write to MMIO register, routing to appropriate subsystem"""
        if 0x60 <= addr < 0x90:
            self.apu.write_register(0x04000000 + addr, value)
        elif addr < 0x400:
            self.io[addr] = value & 0xFF
            self.io[addr + 1] = (value >> 8) & 0xFF
        
    def read_io(self, addr):
        """Read from MMIO register"""
        if addr < 0x400 and addr + 1 < len(self.io):
            return self.io[addr] | (self.io[addr + 1] << 8)
        return 0
            
    def render_frame(self, headless=False):
        # Minimal Mode 3 rendering (direct bitmap)
        pygame.init()
        
        # Always create surface from VRAM (Mode 3 = 16-bit RGB555)
        pixels = pygame.Surface((240, 160), depth=16)
        
        for y in range(160):
            for x in range(240):
                vram_idx = (y * 240 + x) * 2
                if vram_idx + 1 < len(self.vram):
                    color = self.vram[vram_idx] | (self.vram[vram_idx + 1] << 8)
                    r = (color & 0x1F) * 8
                    g = ((color >> 5) & 0x1F) * 8
                    b = ((color >> 10) & 0x1F) * 8
                    pixels.set_at((x, y), (r, g, b))
        
        if headless:
            return pixels
        
        screen = pygame.display.set_mode((240, 160))
        screen.blit(pixels, (0, 0))
        pygame.display.flip()
        return screen

def run_transpiled(headless=False, frame_limit=None, screenshot_path=None):
    # Initialize pygame regardless of headless mode
    pygame.init()
    
    gba = GBA(ROM_DATA)
    
    # Initialize memory object with gba reference
    global memory
    memory = Memory(gba)
    
    # Load extracted assets into VRAM and palette RAM if available
    if 'VRAM_DATA' in globals() and len(VRAM_DATA) > 0:
        # Copy tile data to VRAM (0x06000000) using write_u16 for efficiency
        for i in range(0, len(VRAM_DATA) - 1, 2):
            if (i // 2) < 49152:  # 96KB VRAM limit / 2
                value = (VRAM_DATA[i] & 0xFF) | ((VRAM_DATA[i + 1] & 0xFF) << 8)
                memory.write_u16(0x06000000 + i, value)
        print(f"Loaded {len(VRAM_DATA)} bytes of VRAM data")
    
    if 'PALETTE_DATA' in globals() and len(PALETTE_DATA) > 0:
        # Copy palette data to palette RAM (0x05000000) using write_u16
        for i in range(0, len(PALETTE_DATA) - 1, 2):
            if (i // 2) < 256:  # 256 colors max
                value = (PALETTE_DATA[i] & 0xFF) | ((PALETTE_DATA[i + 1] & 0xFF) << 8)
                memory.write_u16(0x05000000 + i, value)
        print(f"Loaded {len(PALETTE_DATA)} bytes of palette data")
    
    if 'TILEMAP_DATA' in globals() and len(TILEMAP_DATA) > 0:
        # Copy tilemap to video memory (0x06001800 for BG0 map) using write_u16
        for i in range(0, len(TILEMAP_DATA) - 1, 2):
            if (i // 2) < 1024:  # Max tilemap size / 2
                value = (TILEMAP_DATA[i] & 0xFF) | ((TILEMAP_DATA[i + 1] & 0xFF) << 8)
                memory.write_u16(0x06001800 + i, value)
        print(f"Loaded {len(TILEMAP_DATA)} bytes of tilemap data")
    
    # Execute transpiled code via func_map dispatch
    if 0x08000000 in func_map:
        func_map[0x08000000](gba)
    
    if headless:
        # Headless mode: just execute and exit
        if screenshot_path:
            # Save screenshot before exiting
            screen = gba.render_frame(headless=True)
            if screen:
                pygame.image.save(screen, screenshot_path)
                print(f"Screenshot saved to: {screenshot_path}")
        return
    
    # Render frames with display
    frames_rendered = 0
    while frame_limit is None or frames_rendered < frame_limit:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
        gba.render_frame(headless)
        frames_rendered += 1
        pygame.time.delay(16)  # ~60fps
    
    # Save screenshot if requested
    if screenshot_path:
        screen = gba.render_frame(headless=True)
        if screen:
            pygame.image.save(screen, screenshot_path)
            print(f"Screenshot saved to: {screenshot_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frame", type=int, default=None)
    parser.add_argument("--screenshot", type=str, default=None)
    args = parser.parse_args()
    run_transpiled(headless=args.headless, frame_limit=args.frame, screenshot_path=args.screenshot)
"#,
    );

    fs::write(output_path, &code).map_err(|e| format!("Failed to write output: {}", e))?;

    println!(
        "Generated {} lines of Python to {}",
        code.lines().count(),
        output_path
    );
    Ok(())
}

#[derive(Default)]
pub struct ExtractedAssets {
    pub palette_data: Vec<u8>,
    pub tile_data: Vec<u8>,
    pub tilemap_data: Vec<u8>,
}

fn is_valid_rgb555(color: u16) -> bool {
    let r = color & 0x1F;
    let g = (color >> 5) & 0x1F;
    let b = (color >> 10) & 0x1F;
    r <= 0x1F && g <= 0x1F && b <= 0x1F && (color & 0x8000) == 0
}

fn is_valid_4bpp_tile(data: &[u8]) -> bool {
    if data.len() < 32 {
        return false;
    }
    let mut unique_nibbles = [false; 16];
    for &byte in &data[..32] {
        unique_nibbles[(byte & 0x0F) as usize] = true;
        unique_nibbles[((byte >> 4) & 0x0F) as usize] = true;
    }
    unique_nibbles.iter().filter(|&&x| x).count() >= 3
}

fn is_likely_tilemap(data: &[u8]) -> bool {
    if data.len() < 4 || data.len() % 2 != 0 {
        return false;
    }
    let valid_entries = data
        .chunks_exact(2)
        .filter(|pair| {
            let entry = u16::from_le_bytes([pair[0], pair[1]]);
            (entry & 0x3FF) <= 1023
        })
        .count();
    valid_entries * 4 >= data.len() / 2
}

pub fn extract_assets(rom_data: &[u8]) -> ExtractedAssets {
    let mut assets = ExtractedAssets::default();
    let start_offset = 0x100;

    let mut palette_candidates: std::collections::HashMap<usize, usize> =
        std::collections::HashMap::new();
    for offset in (start_offset..rom_data.len().saturating_sub(64)).step_by(2) {
        let mut consecutive_valid = 0;
        for i in 0..32 {
            let pos = offset + i * 2;
            if pos + 1 >= rom_data.len() {
                break;
            }
            let color = u16::from_le_bytes([rom_data[pos], rom_data[pos + 1]]);
            if is_valid_rgb555(color) {
                consecutive_valid += 1;
            } else {
                break;
            }
        }
        if consecutive_valid >= 8 {
            let count = palette_candidates.entry(offset).or_insert(0);
            *count = consecutive_valid;
        }
    }

    if let Some((best_offset, _)) = palette_candidates.iter().max_by_key(|(_, count)| *count) {
        let offset = *best_offset;
        let max_colors = 256;
        for i in 0..max_colors {
            let pos = offset + i * 2;
            if pos + 1 >= rom_data.len() {
                break;
            }
            assets.palette_data.push(rom_data[pos]);
            assets.palette_data.push(rom_data[pos + 1]);
        }
        eprintln!(
            "  Found palette at offset 0x{:X}, {} colors",
            offset,
            assets.palette_data.len() / 2
        );
    } else {
        eprintln!("  No palette data found");
    }

    let mut best_tile_offset = 0;
    let mut best_tile_count = 0;
    for offset in (start_offset..rom_data.len().saturating_sub(128)).step_by(32) {
        let mut tile_count = 0;
        for tile_idx in 0..64 {
            let tile_start = offset + tile_idx * 32;
            if tile_start + 32 > rom_data.len() {
                break;
            }
            if is_valid_4bpp_tile(&rom_data[tile_start..tile_start + 32]) {
                tile_count += 1;
            } else {
                break;
            }
        }
        if tile_count > best_tile_count {
            best_tile_count = tile_count;
            best_tile_offset = offset;
        }
    }

    if best_tile_count > 0 {
        for i in 0..best_tile_count {
            let tile_start = best_tile_offset + i * 32;
            if tile_start + 32 <= rom_data.len() {
                assets
                    .tile_data
                    .extend_from_slice(&rom_data[tile_start..tile_start + 32]);
            }
        }
        eprintln!(
            "  Found {} tiles at offset 0x{:X}",
            best_tile_count, best_tile_offset
        );
    } else {
        eprintln!("  No tile data found");
    }

    let mut best_tilemap_offset = 0;
    let mut best_tilemap_count = 0;
    for offset in (start_offset..rom_data.len().saturating_sub(64)).step_by(2) {
        let sample = &rom_data[offset..std::cmp::min(offset + 128, rom_data.len())];
        if is_likely_tilemap(sample) {
            let mut count = 0;
            for i in (0..sample.len()).step_by(2) {
                let entry = u16::from_le_bytes([sample[i], sample[i + 1]]);
                if (entry & 0x3FF) <= 1023 {
                    count += 1;
                }
            }
            if count > best_tilemap_count {
                best_tilemap_count = count;
                best_tilemap_offset = offset;
            }
        }
    }

    if best_tilemap_count > 16 {
        for i in 0..std::cmp::min(best_tilemap_count, 1024) {
            let pos = best_tilemap_offset + i * 2;
            if pos + 1 < rom_data.len() {
                assets.tilemap_data.push(rom_data[pos]);
                assets.tilemap_data.push(rom_data[pos + 1]);
            }
        }
        eprintln!(
            "  Found {} tilemap entries at offset 0x{:X}",
            best_tilemap_count, best_tilemap_offset
        );
    }
    assets
}

/// Generate Python for LDM (Load Multiple)
/// Generate Python for LDM (Load Multiple)
fn generate_ldm_python(instr: &DecodedInstruction) -> String {
    if instr.operands.is_empty() {
        return format!("pass  # LDM: insufficient operands\n");
    }

    let multi_str = instr.operands[0].display();

    // Extract base register
    let base = multi_str
        .split("base:")
        .nth(1)
        .and_then(|s| s.split(',').next())
        .and_then(|s| s.trim().parse::<u8>().ok())
        .unwrap_or(0);

    // Extract the "Multi {...}" part
    let multi_part = if let Some(start) = multi_str.find("Multi {") {
        if let Some(end) = multi_str.rfind('}') {
            &multi_str[start..=end]
        } else {
            ""
        }
    } else {
        ""
    };

    // Extract register list from [0, 1, 2, ...]
    let regs: Vec<u8> = match (multi_part.find('['), multi_part.find(']')) {
        (Some(start), Some(end)) => multi_part[start + 1..end]
            .split(',')
            .filter_map(|s| s.trim().parse::<u8>().ok())
            .collect(),
        _ => vec![],
    };

    let increment = multi_part.contains("increment: true");
    let writeback = multi_part.contains("writeback: true");

    let addr_var = format!("ldm_addr_{}", base);
    let mut code = format!("{} = r{}\n", addr_var, base);

    // Adjust address for DB (Decrement Before) mode
    if !increment && !regs.is_empty() {
        code.push_str(&format!("{} -= {}\n", addr_var, (regs.len() - 1) * 4));
    }

    // Load each register
    for reg in &regs {
        if *reg < 16 {
            code.push_str(&format!("r{} = memory.read_32({})\n", reg, addr_var));
            code.push_str(&format!("{} += 4\n", addr_var));
        }
    }

    // Writeback base register if needed
    if writeback {
        code.push_str(&format!("r{} = {}\n", base, addr_var));
    }

    code
}
/// Generate Python for STM (Store Multiple)
fn generate_stm_python(instr: &DecodedInstruction) -> String {
    if instr.operands.is_empty() {
        return format!("pass  # STM: insufficient operands\n");
    }

    let multi_str = instr.operands[0].display();

    // Extract base register
    let base = multi_str
        .split("base:")
        .nth(1)
        .and_then(|s| s.split(',').next())
        .and_then(|s| s.trim().parse::<u8>().ok())
        .unwrap_or(0);

    // Extract the "Multi {...}" part from "[r11, Multi { base: 11, registers: [0, 1], ... }]"
    let multi_part = if let Some(start) = multi_str.find("Multi {") {
        if let Some(end) = multi_str.rfind('}') {
            &multi_str[start..=end]
        } else {
            ""
        }
    } else {
        ""
    };

    // Extract register list from [0, 1, 2, ...]
    let regs: Vec<u8> = match (multi_part.find('['), multi_part.find(']')) {
        (Some(start), Some(end)) => multi_part[start + 1..end]
            .split(',')
            .filter_map(|s| s.trim().parse::<u8>().ok())
            .collect(),
        _ => vec![],
    };

    let increment = multi_part.contains("increment: true");
    let writeback = multi_part.contains("writeback: true");

    let addr_var = format!("stm_addr_{}", base);
    let mut code = format!("{} = r{}\n", addr_var, base);

    // Adjust address for DB (Decrement Before) mode
    if !increment && !regs.is_empty() {
        code.push_str(&format!("{} -= {}\n", addr_var, (regs.len() - 1) * 4));
    }

    // Store each register
    for reg in &regs {
        if *reg < 16 {
            code.push_str(&format!("memory.write_32({}, r{})\n", addr_var, reg));
            code.push_str(&format!("{} += 4\n", addr_var));
        }
    }

    // Writeback base register if needed
    if writeback {
        code.push_str(&format!("r{} = {}\n", base, addr_var));
    }

    code
}
