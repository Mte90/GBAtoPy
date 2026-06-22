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
            return Some(format!("if cpsr_check('{}'): registers[15] = 0x{:08X}", cond, target));
        }
    }
    None
}
