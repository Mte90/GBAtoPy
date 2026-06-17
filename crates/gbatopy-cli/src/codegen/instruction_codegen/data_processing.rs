use gbatopy_disasm::{operand::ShiftAmount, DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode;
    let ops = &inst.operands;
    let base_opcode = opcode.split_whitespace().next().unwrap_or(opcode);
    let base_opcode = base_opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());

    match base_opcode {
        "MOV" => generate_mov(ops),
        "MVN" => generate_mvn(ops),
        "ADD" | "ADC" => generate_add(ops, base_opcode),
        "SUB" | "SBC" | "RSB" | "RSC" => generate_sub(ops, base_opcode),
        "AND" | "EOR" | "ORR" | "BIC" => generate_logic(ops, base_opcode),
        "LSL" | "LSR" | "ASR" | "ROR" => generate_shift(ops, base_opcode),
        "CLZ" => generate_clz(ops),
        "CMP" => generate_cmp(ops),
        "CMN" => generate_cmn(ops),
        "TST" => generate_tst(ops),
        "TEQ" => generate_teq(ops),
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
    if ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            // Handle 2-operand form: ORR Rd, #imm or ORR Rd, Rm
            if ops.len() == 2 {
                let src = match &ops[1] {
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
                return Some(format!("registers[{}] = (registers[{}] {} {}) & 0xFFFFFFFF", rd, rd, py_op, src));
            }
            
            // Handle 3-operand form: ORR Rd, Rn, #imm/Rm/shifted
            if let Operand::Register(rn_reg) = ops[1] {
                let rn = format!("registers[{}]", rn_reg);
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

fn generate_cmp(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 2 {
        let rn = match &ops[0] {
            Operand::Register(r) => format!("registers[{}]", r),
            Operand::Immediate(i) => format!("{}", i),
            _ => "0".to_string(),
        };
        let rm = match &ops[1] {
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
        
        return Some(format!(
            r#"result_cmp = ({rn} - {rm}) & 0xFFFFFFFF
cpsr['n'] = (result_cmp >> 31) & 1
cpsr['z'] = 1 if result_cmp == 0 else 0
cpsr['c'] = 1 if ({rn} >= {rm}) else 0
if ({rn} >= 0 and {rm} < 0 and result_cmp < 0) or ({rn} < 0 and {rm} >= 0 and result_cmp >= 0):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
        ));
    }
    None
}

fn generate_cmn(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 2 {
        let rn = match &ops[0] {
            Operand::Register(r) => format!("registers[{}]", r),
            Operand::Immediate(i) => format!("{}", i),
            _ => "0".to_string(),
        };
        let rm = match &ops[1] {
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
        
        return Some(format!(
            r#"result_cmn = ({rn} + {rm}) & 0xFFFFFFFF
cpsr['n'] = (result_cmn >> 31) & 1
cpsr['z'] = 1 if result_cmn == 0 else 0
cpsr['c'] = 1 if ({rn} + {rm}) >= 0x100000000 else 0
rn_s = {rn} if {rn} < 0x80000000 else {rn} - 0x100000000
rm_s = {rm} if {rm} < 0x80000000 else {rm} - 0x100000000
if (rn_s > 0 and rm_s > 0 and result_cmn >= 0x80000000) or (rn_s < 0 and rm_s < 0 and result_cmn < 0x80000000):
    cpsr['v'] = 1
else:
    cpsr['v'] = 0"#
        ));
    }
    None
}

fn generate_tst(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 2 {
        let rn = match &ops[0] {
            Operand::Register(r) => format!("registers[{}]", r),
            Operand::Immediate(i) => format!("{}", i),
            _ => "0".to_string(),
        };
        let rm = match &ops[1] {
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
        
        return Some(format!(
            r#"result_tst = {rn} & {rm}
cpsr['n'] = (result_tst >> 31) & 1
cpsr['z'] = 1 if result_tst == 0 else 0
cpsr['c'] = 0
cpsr['v'] = 0"#
        ));
    }
    None
}

fn generate_teq(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 2 {
        let rn = match &ops[0] {
            Operand::Register(r) => format!("registers[{}]", r),
            Operand::Immediate(i) => format!("{}", i),
            _ => "0".to_string(),
        };
        let rm = match &ops[1] {
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
        
        return Some(format!(
            r#"result_teq = {rn} ^ {rm}
cpsr['n'] = (result_teq >> 31) & 1
cpsr['z'] = 1 if result_teq == 0 else 0
cpsr['c'] = 0
cpsr['v'] = 0"#
        ));
    }
    None
}