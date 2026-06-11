use gbatopy_disasm::{operand::ShiftAmount, DecodedInstruction, Operand};

pub fn generate_data_processing(inst: &DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode;
    let ops = &inst.operands;
    let base_opcode = opcode.split_whitespace().next().unwrap_or(opcode);

    match base_opcode {
        "MOV" | "MVN" => {
            if ops.len() >= 1 {
                if let Operand::Register(rd) = ops[0] {
                    let src = if ops.len() >= 2 {
                        match &ops[1] {
                            Operand::Register(rn) => format!("r[{}]", rn),
                            Operand::Immediate(imm) => format!("{}", imm),
                            Operand::ShiftedRegister { reg, shift, amount } => {
                                let amt = match amount {
                                    ShiftAmount::Immediate(n) => *n,
                                    _ => 0,
                                };
                                match shift {
                                    gbatopy_disasm::operand::ShiftType::Lsl => {
                                        format!("r[{}] << {}", reg, amt)
                                    }
                                    gbatopy_disasm::operand::ShiftType::Lsr => {
                                        format!("r[{}] >> {}", reg, amt)
                                    }
                                    gbatopy_disasm::operand::ShiftType::Asr => {
                                        format!("r[{}] >> {}", reg, amt)
                                    }
                                    _ => format!("r[{}]", reg),
                                }
                            }
                            _ => "0".to_string(),
                        }
                    } else {
                        "0".to_string()
                    };

                    let neg = if base_opcode == "MVN" { " ^ 0xFFFFFFFF" } else { "" };
                    return Some(format!("r[{}] = {}{}", rd, src, neg));
                }
            }
            None
        }
        "ADD" | "ADC" | "SUB" | "SBC" | "RSB" | "RSC" => {
            if ops.len() >= 3 {
                if let Operand::Register(rd) = ops[0] {
                    let rn = match &ops[1] {
                        Operand::Register(r) => format!("r[{}]", r),
                        Operand::Immediate(i) => format!("{}", i),
                        _ => "0".to_string(),
                    };
                    let op2 = match &ops[2] {
                        Operand::Register(r) => format!("r[{}]", r),
                        Operand::Immediate(i) => format!("{}", i),
                        Operand::ShiftedRegister { reg, shift, amount } => {
                            let amt = match amount {
                                ShiftAmount::Immediate(n) => *n,
                                _ => 0,
                            };
                            format!("(r[{}] {} {})", reg, format!("{:?}", shift).to_lowercase(), amt)
                        }
                        _ => "0".to_string(),
                    };

                    let op = match base_opcode {
                        "ADD" => "+",
                        "ADC" => "+",
                        "SUB" => "-",
                        "SBC" => "-",
                        "RSB" => "-",
                        "RSC" => "-",
                        _ => "+",
                    };
                    return Some(format!("r[{}] = ({} {})", rd, rn, op2));
                }
            }
            None
        }
        "AND" | "EOR" | "ORR" | "BIC" | "LSL" | "LSR" | "ASR" | "ROR" => {
            if ops.len() >= 3 {
                if let Operand::Register(rd) = ops[0] {
                    let rn = match &ops[1] {
                        Operand::Register(r) => format!("r[{}]", r),
                        Operand::Immediate(i) => format!("{}", i),
                        _ => "r[0]".to_string(),
                    };
                    let op2 = match &ops[2] {
                        Operand::Register(r) => format!("r[{}]", r),
                        Operand::Immediate(i) => format!("{}", i),
                        _ => "0".to_string(),
                    };

                    let py_op = match base_opcode {
                        "AND" => "&",
                        "EOR" => "^",
                        "ORR" => "|",
                        "BIC" => "& ~",
                        _ => "&",
                    };
                    return Some(format!("r[{}] = ({} {} {}) & 0xFFFFFFFF", rd, rn, py_op, op2));
                }
            }
            None
        }
        "CMP" | "CMN" | "TST" | "TEQ" => {
            None
        }
        "CLZ" => {
            if ops.len() >= 2 {
                if let Operand::Register(rd) = ops[0] {
                    let rm = match &ops[1] {
                        Operand::Register(r) => format!("r[{}]", r),
                        _ => "r[0]".to_string(),
                    };
                    return Some(format!(
                        "r[{}] = 32 - len(bin({} | 0xFFFFFFFF)) + 1 if {} == 0 else 32 - len(bin({})) + 1",
                        rd, rm, rm, rm
                    ));
                }
            }
            None
        }
        _ => None,
    }
}