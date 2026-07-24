use gbatopy_disasm::{Condition, DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;
    let base_opcode = opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());

    if base_opcode == "B" || base_opcode == "BL" {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let target = if *target > 0x08000000 && *target < 0x0A000000 {
                *target
            } else {
                return Some(format!("# Invalid branch target: 0x{:08X}", target));
            };
            if base_opcode == "BL" {
                // BL (Branch with Link): set LR = return address (next instruction),
                // then branch to target. LR holds the address the callee should
                // return to via LDMFD SP!, {..., PC} or BX LR.
                return Some(format!(
                    "registers[14] = (registers[15] + 4) & 0xFFFFFFFF\nregisters[15] = 0x{:08X}",
                    target
                ));
            }
            return Some(format!("registers[15] = 0x{:08X}", target));
        }
        return Some(format!("# {} branch (target unknown)", base_opcode));
    }
    if base_opcode == "BX" || base_opcode == "BLX" {
        if let Some(Operand::Register(rn)) = ops.first() {
            // BX/BLX Rm: bit 0 of Rm selects Thumb (1) or ARM (0) mode.
            // The disassembler stores the condition in inst.condition (not in
            // the opcode string), so we must read it separately for conditional
            // variants like BXEQ, BXNE, etc.
            let cond_str = match inst.condition {
                Some(c) if c != Condition::Al => c.name().to_uppercase(),
                _ => String::new(),
            };
            let blx_link = if base_opcode == "BLX" {
                "registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n"
            } else {
                ""
            };
            if !cond_str.is_empty() {
                return Some(format!(
                    "if cpsr_check('{}'):\n    {}cpsr['t'] = registers[{}] & 1\n    registers[15] = registers[{}] & 0xFFFFFFFE\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF",
                    cond_str, blx_link, rn, rn
                ));
            }
            return Some(format!(
                "{}cpsr['t'] = registers[{}] & 1\nregisters[15] = registers[{}] & 0xFFFFFFFE",
                blx_link, rn, rn
            ));
        }
        return Some(format!("# {} branch exchange", base_opcode));
    }
    // Conditional branches: BEQ, BNE, BCS, BCC, BMI, BPL, BVS, BVC, BHI, BLS, BGE, BLT, BGT, BLE
    if opcode.len() == 3 && opcode.starts_with('B') && opcode != "BX" && opcode != "BLX" {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let target = if *target > 0x08000000 && *target < 0x0A000000 {
                *target
            } else {
                return None;
            };
            let cond = &opcode[1..];
            // When condition is false, PC must still advance by 4 bytes (ARM instruction size)
            return Some(format!("if cpsr_check('{}'):\n    registers[15] = 0x{:08X}\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF", cond, target));
        }
    }
    // Conditional BL: BLEQ, BLNE, etc. (4 chars, starts with "BL", not "BLX")
    if opcode.len() >= 4 && opcode.starts_with("BL") && !opcode.starts_with("BLX") {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let target = if *target > 0x08000000 && *target < 0x0A000000 {
                *target
            } else {
                return None;
            };
            let cond = &opcode[2..];
            return Some(format!(
                "if cpsr_check('{}'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x{:08X}\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF",
                cond, target
            ));
        }
    }
    None
}
