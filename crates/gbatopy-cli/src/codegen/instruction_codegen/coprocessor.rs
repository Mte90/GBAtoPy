use gbatopy_disasm::{DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;
    let base_opcode = opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());

    if base_opcode == "MRC" || base_opcode == "MCR" {
        return Some(format!("# {} coprocessor register transfer", base_opcode));
    }
    if base_opcode == "LDC" || base_opcode == "STC" {
        return Some(format!("# {} coprocessor data transfer", base_opcode));
    }
    if base_opcode == "CDP" {
        return Some("# CDP coprocessor data operation".to_string());
    }
    if base_opcode == "SWI" || base_opcode == "SVC" {
        return Some(format!("# {} software interrupt", base_opcode));
    }
    if base_opcode == "MSR" {
        return Some("# MSR move to status register".to_string());
    }
    if base_opcode == "MRS" {
        return Some("# MRS move from status register".to_string());
    }
    if base_opcode == "NOP" {
        return Some("pass  # NOP".to_string());
    }
    if base_opcode == "MUL" || base_opcode == "MLA" {
        if ops.len() >= 3 {
            if let Operand::Register(rd) = ops[0] {
                let rm = if let Operand::Register(r) = ops[1] {
                    format!("registers[{}]", r)
                } else { "0".to_string() };
                let rs = if let Operand::Register(r) = ops[2] {
                    format!("registers[{}]", r)
                } else { "0".to_string() };
                let acc = if base_opcode == "MLA" && ops.len() >= 4 {
                    if let Operand::Register(a) = ops[3] {
                        format!(" + registers[{}]", a)
                    } else { String::new() }
                } else { String::new() };
                return Some(format!("registers[{}] = ({} * {} {}) & 0xFFFFFFFF", rd, rm, rs, acc));
            }
        }
    }
    if base_opcode == "UMULL" || base_opcode == "SMULL" {
        if ops.len() >= 4 {
            if let Operand::Register(rlo) = ops[0] {
                if let Operand::Register(rhi) = ops[1] {
                    let rm = if let Operand::Register(r) = ops[2] {
                        format!("registers[{}]", r)
                    } else { "0".to_string() };
                    let rs = if let Operand::Register(r) = ops[3] {
                        format!("registers[{}]", r)
                    } else { "0".to_string() };
                    return Some(format!(
                        "result = {} * {}; registers[{}] = result & 0xFFFFFFFF; registers[{}] = (result >> 32) & 0xFFFFFFFF",
                        rm, rs, rlo, rhi
                    ));
                }
            }
        }
    }
    None
}
