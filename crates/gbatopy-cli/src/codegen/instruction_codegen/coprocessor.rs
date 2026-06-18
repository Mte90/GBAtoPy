use gbatopy_disasm::{DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;
    let base_opcode = opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());
    let opcode_upper = base_opcode.to_uppercase();

    // Handle conditional variants like COPROCESSORge, COPROCESSORne, etc.
    if opcode_upper.starts_with("COPROCESSOR") {
        return Some("pass  # COPROCESSOR conditional variant".to_string());
    }

    if base_opcode == "MRC" || base_opcode == "MCR" {
        return Some(format!("pass  # {} coprocessor register transfer", base_opcode));
    }
    if base_opcode == "LDC" || base_opcode == "STC" {
        return Some(format!("pass  # {} coprocessor data transfer", base_opcode));
    }
    if base_opcode == "CDP" {
        return Some("pass  # CDP coprocessor data operation".to_string());
    }
    if base_opcode == "SWI" || base_opcode == "SVC" {
        // SWI/SVC: software interrupt - increment PC and continue
        // The actual SWI handler is called by the runtime at the appropriate time
        return Some("pass  # SWI/SVC software interrupt (handled by runtime)".to_string());
    }
    if base_opcode == "MSR" {
        return Some("pass  # MSR move to status register".to_string());
    }
    if base_opcode == "MRS" {
        return Some("pass  # MRS move from status register".to_string());
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
