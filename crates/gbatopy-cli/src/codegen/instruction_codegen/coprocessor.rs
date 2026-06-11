use gbatopy_disasm::{DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;

    if opcode == "MRC" || opcode == "MCR" {
        return Some(format!("# {} coprocessor register transfer", opcode));
    }
    if opcode == "LDC" || opcode == "STC" {
        return Some(format!("# {} coprocessor data transfer", opcode));
    }
    if opcode == "CDP" {
        return Some("# CDP coprocessor data operation".to_string());
    }
    if opcode == "SWI" || opcode == "SVC" {
        return Some(format!("# {} software interrupt", opcode));
    }
    if opcode == "MSR" {
        return Some("# MSR move to status register".to_string());
    }
    if opcode == "MRS" {
        return Some("# MRS move from status register".to_string());
    }
    if opcode == "NOP" {
        return Some("pass  # NOP".to_string());
    }
    if opcode == "MUL" || opcode == "MLA" {
        if ops.len() >= 3 {
            if let Operand::Register(rd) = ops[0] {
                let rm = if let Operand::Register(r) = ops[1] {
                    format!("r[{}]", r)
                } else { "0".to_string() };
                let rs = if let Operand::Register(r) = ops[2] {
                    format!("r[{}]", r)
                } else { "0".to_string() };
                let acc = if opcode == "MLA" && ops.len() >= 4 {
                    if let Operand::Register(a) = ops[3] {
                        format!(" + r[{}]", a)
                    } else { String::new() }
                } else { String::new() };
                return Some(format!("r[{}] = ({} * {} {}) & 0xFFFFFFFF", rd, rm, rs, acc));
            }
        }
    }
    if opcode == "UMULL" || opcode == "SMULL" {
        if ops.len() >= 4 {
            if let Operand::Register(rlo) = ops[0] {
                if let Operand::Register(rhi) = ops[1] {
                    let rm = if let Operand::Register(r) = ops[2] {
                        format!("r[{}]", r)
                    } else { "0".to_string() };
                    let rs = if let Operand::Register(r) = ops[3] {
                        format!("r[{}]", r)
                    } else { "0".to_string() };
                    return Some(format!(
                        "result = {} * {}; r[{}] = result & 0xFFFFFFFF; r[{}] = (result >> 32) & 0xFFFFFFFF",
                        rm, rs, rlo, rhi
                    ));
                }
            }
        }
    }
    None
}
