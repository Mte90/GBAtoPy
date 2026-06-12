use gbatopy_disasm::{operand::ShiftAmount, DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode;
    let ops = &inst.operands;
    let base_opcode = opcode.split_whitespace().next().unwrap_or(opcode);

    match base_opcode {
        "MOV" => generate_mov(ops),
        "MVN" => generate_mvn(ops),
        "ADD" | "ADC" => generate_add(ops, base_opcode),
        "SUB" | "SBC" | "RSB" | "RSC" => generate_sub(ops, base_opcode),
        "AND" | "EOR" | "ORR" | "BIC" => generate_logic(ops, base_opcode),
        "LSL" | "LSR" | "ASR" | "ROR" => generate_shift(ops, base_opcode),
        "CLZ" => generate_clz(ops),
        _ => None,
    }
}

fn generate_mov(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 1 {
        if let Operand::Register(rd) = ops[0] {
            let src = if ops.len() >= 2 {
                match &ops[1] {
                    Operand::Register(rn) => format!("registers[{}]", rn),
                    Operand::Immediate(imm) => format!("{}", imm),
                    Operand::ShiftedRegister { reg, shift, amount } => {
                        let amt = match amount {
                            ShiftAmount::Immediate(n) => *n,
                            _ => 0,
                        };
                        match shift {
                            gbatopy_disasm::operand::ShiftType::Lsl => format!("registers[{}] << {}", reg, amt),
                            gbatopy_disasm::operand::ShiftType::Lsr => format!("registers[{}] >> {}", reg, amt),
                            gbatopy_disasm::operand::ShiftType::Asr => format!("registers[{}] >> {}", reg, amt),
                            _ => format!("registers[{}]", reg),
                        }
                    }
                    _ => "0".to_string(),
                }
            } else {
                "0".to_string()
            };
            return Some(format!("registers[{}] = {}", rd, src));
        }
    }
    None
}

fn generate_mvn(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 1 {
        if let Operand::Register(rd) = ops[0] {
            let src = if ops.len() >= 2 {
                match &ops[1] {
                    Operand::Register(rn) => format!("registers[{}]", rn),
                    Operand::Immediate(imm) => format!("{}", imm),
                    _ => "0".to_string(),
                }
            } else {
                "0".to_string()
            };
            return Some(format!("registers[{}] = {} ^ 0xFFFFFFFF", rd, src));
        }
    }
    None
}

fn generate_add(ops: &[Operand], op: &str) -> Option<String> {
    if ops.len() >= 3 {
        if let Operand::Register(rd) = ops[0] {
            let rn = match &ops[1] {
                Operand::Register(r) => format!("registers[{}]", r),
                Operand::Immediate(i) => format!("{}", i),
                _ => "0".to_string(),
            };
            let op2 = match &ops[2] {
                Operand::Register(r) => format!("registers[{}]", r),
                Operand::Immediate(i) => format!("{}", i),
                Operand::ShiftedRegister { reg, shift, amount } => {
                    let amt = match amount {
                        ShiftAmount::Immediate(n) => *n,
                        _ => 0,
                    };
                    match shift {
                        gbatopy_disasm::operand::ShiftType::Lsl => format!("(registers[{}] << {})", reg, amt),
                        gbatopy_disasm::operand::ShiftType::Lsr => format!("(registers[{}] >> {})", reg, amt),
                        gbatopy_disasm::operand::ShiftType::Asr => format!("(registers[{}] >> {})", reg, amt),
                        gbatopy_disasm::operand::ShiftType::Ror => format!("(registers[{}] >> {}) | (registers[{}] << (32 - {})) & 0xFFFFFFFF", reg, amt, reg, amt),
                    }
                }
                _ => "0".to_string(),
            };
            return Some(format!("registers[{}] = ({})", rd, op2));
        }
    }
    None
}

fn generate_sub(ops: &[Operand], op: &str) -> Option<String> {
    if ops.len() >= 3 {
        if let Operand::Register(rd) = ops[0] {
            let rn = match &ops[1] {
                Operand::Register(r) => format!("registers[{}]", r),
                Operand::Immediate(i) => format!("{}", i),
                _ => "0".to_string(),
            };
            let op2 = match &ops[2] {
                Operand::Register(r) => format!("registers[{}]", r),
                Operand::Immediate(i) => format!("{}", i),
                Operand::ShiftedRegister { reg, shift, amount } => {
                    let amt = match amount {
                        ShiftAmount::Immediate(n) => *n,
                        _ => 0,
                    };
                    match shift {
                        gbatopy_disasm::operand::ShiftType::Lsl => format!("registers[{}] << {}", reg, amt),
                        gbatopy_disasm::operand::ShiftType::Lsr => format!("registers[{}] >> {}", reg, amt),
                        gbatopy_disasm::operand::ShiftType::Asr => format!("registers[{}] >> {}", reg, amt),
                        gbatopy_disasm::operand::ShiftType::Ror => format!("(registers[{}] >> {}) | (registers[{}] << (32 - {})) & 0xFFFFFFFF", reg, amt, reg, amt),
                    }
                }
                _ => "0".to_string(),
            };
            return Some(format!("registers[{}] = ({} - {})", rd, rn, op2));
        }
    }
    None
}

fn generate_logic(ops: &[Operand], op: &str) -> Option<String> {
    if ops.len() >= 3 {
        if let Operand::Register(rd) = ops[0] {
            let rn = match &ops[1] {
                Operand::Register(r) => format!("registers[{}]", r),
                Operand::Immediate(i) => format!("{}", i),
                _ => "registers[0]".to_string(),
            };
            let op2 = match &ops[2] {
                Operand::Register(r) => format!("registers[{}]", r),
                Operand::Immediate(i) => format!("{}", i),
                Operand::ShiftedRegister { reg, shift, amount } => {
                    let amt = match amount {
                        ShiftAmount::Immediate(n) => *n,
                        _ => 0,
                    };
                    match shift {
                        gbatopy_disasm::operand::ShiftType::Lsl => format!("registers[{}] << {}", reg, amt),
                        gbatopy_disasm::operand::ShiftType::Lsr => format!("registers[{}] >> {}", reg, amt),
                        gbatopy_disasm::operand::ShiftType::Asr => format!("registers[{}] >> {}", reg, amt),
                        gbatopy_disasm::operand::ShiftType::Ror => format!("(registers[{}] >> {}) | (registers[{}] << (32 - {})) & 0xFFFFFFFF", reg, amt, reg, amt),
                    }
                }
                _ => "0".to_string(),
            };
            let py_op = match op {
                "AND" => "&",
                "EOR" => "^",
                "ORR" => "|",
                "BIC" => "& ~",
                _ => "&",
            };
            return Some(format!("registers[{}] = ({} {} {}) & 0xFFFFFFFF", rd, rn, py_op, op2));
        }
    }
    None
}

fn generate_shift(ops: &[Operand], op: &str) -> Option<String> {
    if ops.len() >= 3 {
        if let Operand::Register(rd) = ops[0] {
            let rn = match &ops[1] {
                Operand::Register(r) => format!("registers[{}]", r),
                _ => "registers[0]".to_string(),
            };
            let shift = match &ops[2] {
                Operand::Immediate(i) => format!("{}", i),
                Operand::Register(r) => format!("registers[{}]", r),
                _ => "0".to_string(),
            };
            let py_op = match op {
                "LSL" => "<<",
                "LSR" => ">>",
                "ASR" => ">>",
                "ROR" => "|",
                _ => "<<",
            };
            return Some(format!("registers[{}] = ({} {} {})", rd, rn, py_op, shift));
        }
    }
    None
}

fn generate_clz(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            let rm = match &ops[1] {
                Operand::Register(r) => format!("registers[{}]", r),
                _ => "registers[0]".to_string(),
            };
            return Some(format!(
                "registers[{}] = 32 - len(bin({} | 0xFFFFFFFF)) + 1 if {} == 0 else 32 - len(bin({})) + 1",
                rd, rm, rm, rm
            ));
        }
    }
    None
}