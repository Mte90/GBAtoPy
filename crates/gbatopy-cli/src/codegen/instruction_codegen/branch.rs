use gbatopy_disasm::{DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;

    if opcode == "B" || opcode == "BL" {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let target = if *target > 0x08000000 && *target < 0x0A000000 {
                *target
            } else {
                return Some(format!("# Invalid branch target: 0x{:08X}", target));
            };
            return Some(format!("return 0x{:08X}", target));
        }
        return Some(format!("# {} branch (target unknown)", opcode));
    }
    if opcode == "BX" || opcode == "BLX" {
        if let Some(Operand::Register(rn)) = ops.first() {
            return Some(format!("return r[{}]", rn));
        }
        return Some(format!("# {} branch exchange", opcode));
    }
    if opcode.starts_with('B') && opcode.len() == 3 {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let target = if *target > 0x08000000 && *target < 0x0A000000 {
                *target
            } else {
                return None;
            };
            let cond = &opcode[1..];
            return Some(format!("if cpsr_check('{}'): return 0x{:08X}", cond, target));
        }
    }
    None
}
