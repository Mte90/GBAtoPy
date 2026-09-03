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
            let cond_str = match inst.condition {
                Some(c) if c != Condition::Al => c.name().to_uppercase(),
                _ => String::new(),
            };
            let is_blx = base_opcode == "BLX";
            if !cond_str.is_empty() {
                let lr_set = if is_blx {
                    format!("    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n")
                } else {
                    String::new()
                };
                return Some(format!(
                    "if cpsr_check('{}'):\n{}    cpsr['t'] = registers[{}] & 1\n    registers[15] = registers[{}] & 0xFFFFFFFE\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF",
                    cond_str, lr_set, rn, rn
                ));
            }
            let lr_set = if is_blx {
                format!("registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n")
            } else {
                String::new()
            };
            return Some(format!(
                "{}cpsr['t'] = registers[{}] & 1\nregisters[15] = registers[{}] & 0xFFFFFFFE",
                lr_set, rn, rn
            ));
        }
        return Some(format!("# {} branch exchange", base_opcode));
    }
    // Conditional branches: BEQ, BNE, BCS, BCC, BMI, BPL, BVS, BVC, BHI, BLS, BGE, BLT, BGT, BLE
    if opcode.len() == 3 && opcode.starts_with('B') && opcode != "BX" && opcode != "BLX" {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let cond = &opcode[1..];
            if *target > 0x08000000 && *target < 0x0A000000 {
                return Some(format!("if cpsr_check('{}'):\n    registers[15] = 0x{:08X}\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF", cond, target));
            }
            return Some("registers[15] = (registers[15] + 4) & 0xFFFFFFFF".to_string());
        }
    }
    // Conditional BL: BLEQ, BLNE, etc. (4 chars, starts with "BL", not "BLX")
    if opcode.len() >= 4 && opcode.starts_with("BL") && !opcode.starts_with("BLX") {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let cond = &opcode[2..];
            if *target > 0x08000000 && *target < 0x0A000000 {
                return Some(format!(
                    "if cpsr_check('{}'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x{:08X}\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF",
                    cond, target
                ));
            }
            return Some("registers[15] = (registers[15] + 4) & 0xFFFFFFFF".to_string());
        }
    }
    None
}
