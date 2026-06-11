use gbatopy_disasm::{DecodedInstruction, Operand};

pub fn generate_multiply(inst: &DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode;
    let ops = &inst.operands;

    match opcode {
        "MUL" | "MLA" => {
            if ops.len() >= 3 {
                if let Operand::Register(rd) = ops[0] {
                    let rm = match &ops[1] {
                        Operand::Register(r) => format!("r[{}]", r),
                        _ => "0".to_string(),
                    };
                    let rs = match &ops[2] {
                        Operand::Register(r) => format!("r[{}]", r),
                        _ => "0".to_string(),
                    };
                    let acc = if opcode == "MLA" && ops.len() >= 4 {
                        if let Operand::Register(a) = ops[3] {
                            format!(" + r[{}]", a)
                        } else {
                            String::new()
                        }
                    } else {
                        String::new()
                    };
                    return Some(format!("r[{}] = ({} * {} {}) & 0xFFFFFFFF", rd, rm, rs, acc));
                }
            }
            None
        }
        "UMULL" | "SMULL" => {
            if ops.len() >= 4 {
                if let Operand::Register(rlo) = ops[0] {
                    if let Operand::Register(rhi) = ops[1] {
                        let rm = match &ops[2] {
                            Operand::Register(r) => format!("r[{}]", r),
                            _ => "0".to_string(),
                        };
                        let rs = match &ops[3] {
                            Operand::Register(r) => format!("r[{}]", r),
                            _ => "0".to_string(),
                        };
                        let sign = if opcode == "SMULL" { "(x >> 63) & 1" } else { "0" };
                        return Some(format!(
                            "result = {} * {}; r[{}] = result & 0xFFFFFFFF; r[{}] = (result >> 32) & 0xFFFFFFFF",
                            rm, rs, rlo, rhi
                        ));
                    }
                }
            }
            None
        }
        "UMLAL" | "SMLAL" => {
            if ops.len() >= 4 {
                if let Operand::Register(rlo) = ops[0] {
                    if let Operand::Register(rhi) = ops[1] {
                        let rm = match &ops[2] {
                            Operand::Register(r) => format!("r[{}]", r),
                            _ => "0".to_string(),
                        };
                        let rs = match &ops[3] {
                            Operand::Register(r) => format!("r[{}]", r),
                            _ => "0".to_string(),
                        };
                        return Some(format!(
                            "result = (r[{}] | (r[{}] << 32)) + {} * {}; r[{}] = result & 0xFFFFFFFF; r[{}] = (result >> 32) & 0xFFFFFFFF",
                            rlo, rhi, rm, rs, rlo, rhi
                        ));
                    }
                }
            }
            None
        }
        _ => None,
    }
}