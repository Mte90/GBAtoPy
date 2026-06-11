use gbatopy_disasm::DecodedInstruction;

pub fn generate_branch(inst: &DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode;
    let ops = &inst.operands;

    match opcode {
        "B" | "BL" | "BX" | "BLX" => {
            if let Some(gbatopy_disasm::Operand::Immediate(target)) = ops.first() {
                let target = if *target > 0x08000000 && *target < 0x0A000000 {
                    *target
                } else {
                    return Some(format!("# Invalid branch target: 0x{:08X}", target));
                };
                return Some(format!("return 0x{:08X}", target));
            }
            if opcode == "BX" || opcode == "BLX" {
                if let Some(gbatopy_disasm::Operand::Register(rn)) = ops.first() {
                    return Some(format!("return r[{}]", rn));
                }
            }
            Some(format!("# {} branch (target unknown)", opcode))
        }
        "BEQ" | "BNE" | "BGT" | "BLT" | "BGE" | "BLE" | "BCC" | "BCS" | "BVS" | "BVC" | "BMI" | "BPL" {
            if let Some(gbatopy_disasm::Operand::Immediate(target)) = ops.first() {
                let target = if *target > 0x08000000 && *target < 0x0A000000 {
                    *target
                } else {
                    return None;
                };
                let cond = opcode.trim_start_matches('B');
                return Some(format!(
                    "if cpsr_check('{}'): return 0x{:08X}",
                    cond, target
                ));
            }
            None
        }
        "CBZ" | "CBNZ" => {
            if ops.len() >= 2 {
                if let gbatopy_disasm::Operand::Register(rn) = ops[0] {
                    if let gbatopy_disasm::Operand::Immediate(target) = ops[1] {
                        let check = if opcode == "CBZ" { "==" } else { "!=" };
                        return Some(format!(
                            "if r[{}] {} 0: return 0x{:08X}",
                            rn, check, target
                        ));
                    }
                }
            }
            None
        }
        _ => None,
    }
}