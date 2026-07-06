use gbatopy_disasm::{DecodedInstruction, Operand};

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
            return Some(format!("registers[15] = registers[{}]", rn));
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
    None
}
