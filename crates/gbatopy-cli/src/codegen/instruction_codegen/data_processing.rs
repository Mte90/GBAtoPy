use gbatopy_disasm::{operand::ShiftAmount, operand::ShiftType, DecodedInstruction, Operand};

/// ARM: PC = instruction_address + 8 (pipeline offset)
const ARM_PC_OFFSET: u32 = 8;

/// Generate a Python expression for a shifted register operand.
/// Handles both immediate and register-specified shift amounts,
/// masks results to 32 bits, and handles GBA edge cases
/// (LSR/ASR #0 → shift by 32, ROR #0 → RRX).
fn shifted_reg_expr(reg: u8, shift: &ShiftType, amount: &ShiftAmount) -> String {
    let r = format!("registers[{}]", reg);
    match amount {
        ShiftAmount::Immediate(amt) => {
            let amt = *amt as u32;
            match shift {
                ShiftType::Lsl => {
                    if amt == 0 {
                        r
                    } else {
                        format!("({} << {}) & 0xFFFFFFFF", r, amt)
                    }
                }
                ShiftType::Lsr => {
                    let a = if amt == 0 { 32 } else { amt };
                    format!("({} >> {}) & 0xFFFFFFFF", r, a)
                }
                ShiftType::Asr => {
                    let a = if amt == 0 { 32 } else { amt };
                    if a >= 32 {
                        format!("(0xFFFFFFFF if {} & 0x80000000 else 0)", r)
                    } else {
                        format!("((({} - 0x100000000) if {} & 0x80000000 else {}) >> {}) & 0xFFFFFFFF", r, r, r, a)
                    }
                }
                ShiftType::Ror => {
                    if amt == 0 {
                        format!("(({} >> 1) | ((1 if cpsr.get('c', 0) else 0) << 31)) & 0xFFFFFFFF", r)
                    } else {
                        format!("(({} >> {}) | ({} << (32 - {}))) & 0xFFFFFFFF", r, amt, r, amt)
                    }
                }
            }
        }
        ShiftAmount::Register(rs) => {
            let amt_expr = format!("(registers[{}] & 0xFF)", rs);
            match shift {
                ShiftType::Lsl => {
                    // LSL #0 → Rm; LSL #1-31 → Rm << n; LSL #32+ → 0
                    format!("(0 if {a} >= 32 else (({r} << {a}) & 0xFFFFFFFF if {a} != 0 else {r}))", r = r, a = amt_expr)
                }
                ShiftType::Lsr => {
                    // LSR #0 → Rm; LSR #1-31 → Rm >> n; LSR #32+ → 0
                    format!("(0 if {a} >= 32 else (({r} >> {a}) & 0xFFFFFFFF if {a} != 0 else {r}))", r = r, a = amt_expr)
                }
                ShiftType::Asr => {
                    // ASR #0 → Rm; ASR #1-31 → arithmetic; ASR #32+ → sign-extend
                    format!("((0xFFFFFFFF if {r} & 0x80000000 else 0) if {a} >= 32 else ((((({r}) - 0x100000000) if {r} & 0x80000000 else {r}) >> {a}) & 0xFFFFFFFF) if {a} != 0 else {r})", r = r, a = amt_expr)
                }
                ShiftType::Ror => {
                    // ROR #0 → Rm; ROR #32 → Rm; ROR >32 → rotate by n & 0x1F
                    format!("(({r}) if {a} == 0 else ({r}) if ({a} & 0x1F) == 0 else (({r} >> ({a} & 0x1F)) | ({r} << (32 - ({a} & 0x1F)))) & 0xFFFFFFFF)", r = r, a = amt_expr)
                }
            }
        }
    }
}

/// Resolve an operand to a Python expression string.
fn operand_to_expr(op: &Operand) -> String {
    match op {
        Operand::Register(r) => format!("registers[{}]", r),
        Operand::Immediate(i) => format!("{}", i),
        Operand::ShiftedRegister { reg, shift, amount } => shifted_reg_expr(*reg, shift, amount),
        _ => "0".to_string(),
    }
}

/// Replace R15 (PC) **source** operands with the computed PC value as an Immediate.
/// In ARM mode, PC = instruction_address + 8.
/// The destination register (ops[0] for instructions with Rd) is never replaced.
fn resolve_pc_operands(ops: &[Operand], inst_addr: u32, base_opcode: &str) -> Vec<Operand> {
    let pc_val = inst_addr.wrapping_add(ARM_PC_OFFSET);
    let has_rd = !matches!(base_opcode, "CMP" | "CMN" | "TST" | "TEQ");
    ops.iter().enumerate().map(|(i, op)| {
        if has_rd && i == 0 {
            return op.clone();
        }
        match op {
            Operand::Register(15) => Operand::Immediate(pc_val),
            other => other.clone(),
        }
    }).collect()
}

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode;
    let full_opcode = opcode.split_whitespace().next().unwrap_or(opcode);
    let base_opcode = full_opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());

    // Extract condition code from the stripped suffix.
    // The disassembler appends lowercase condition codes (e.g., "ADDeq").
    // cpsr_check expects uppercase, so we convert.
    let cond_suffix = &full_opcode[base_opcode.len()..];
    let cond = if cond_suffix.is_empty() || cond_suffix.eq_ignore_ascii_case("al") {
        None
    } else {
        Some(cond_suffix.to_uppercase())
    };

    let ops = resolve_pc_operands(&inst.operands, inst.address, base_opcode);

    let code = match base_opcode {
        "MOV" => generate_mov(&ops, inst.sets_flags),
        "MVN" => generate_mvn(&ops, inst.sets_flags),
        "ADD" | "ADC" => generate_add(&ops, base_opcode, inst.sets_flags),
        "SUB" | "SBC" | "RSB" | "RSC" => generate_sub(&ops, base_opcode, inst.sets_flags),
        "AND" | "EOR" | "ORR" | "BIC" => generate_logic(&ops, base_opcode, inst.sets_flags),
        "LSL" | "LSR" | "ASR" | "ROR" => generate_shift(&ops, base_opcode, inst.sets_flags),
        "CLZ" => generate_clz(&ops),
        "CMP" => generate_cmp(&ops),
        "CMN" => generate_cmn(&ops),
        "TST" => generate_tst(&ops),
        "TEQ" => generate_teq(&ops),
        "UMLAL" | "SMLAL" => generate_umlal(&ops, base_opcode),
        _ => None,
    }?;

    // Wrap in conditional check if the instruction has a condition code
    if let Some(c) = cond {
        let indented = code
            .lines()
            .map(|line| {
                if line.is_empty() {
                    String::new()
                } else {
                    format!("    {}", line)
                }
            })
            .collect::<Vec<_>>()
            .join("\n");
        return Some(format!("if cpsr_check('{}'):\n{}", c, indented));
    }

    Some(code)
}

fn generate_mov(ops: &[Operand], sets_flags: bool) -> Option<String> {
    if ops.len() >= 1 {
        if let Operand::Register(rd) = ops[0] {
            if rd == 15 {
                // MOVS PC, LR: exception return — restore CPSR from SPSR, then set PC.
                if sets_flags && ops.len() >= 2 {
                    let src_expr = operand_to_expr(&ops[1]);
                    return Some(format!(
                        "_new_cpsr = _spsr_for_mode(cpsr['mode'])\nregisters[15] = ({src}) & 0xFFFFFFFE\ncpsr.clear()\ncpsr.update(_cpsr_from_int(_new_cpsr))\n_switch_mode(cpsr['mode'])\ncpsr['t'] = 1 if (({src}) & 1) else 0",
                        src = src_expr
                    ));
                }
                if ops.len() >= 2 {
                    if let Operand::Immediate(imm) = &ops[1] {
                        return Some(format!("registers[15] = 0x{:08X}", imm));
                    }
                }
                if ops.len() >= 2 {
                    if let Operand::Register(rn) = &ops[1] {
                        return Some(format!("registers[15] = registers[{}] & 0xFFFFFFFC", rn));
                    }
                }
            }

            let src = if ops.len() >= 2 { operand_to_expr(&ops[1]) } else { "0".to_string() };
            if sets_flags {
                return Some(format!(
                    "registers[{}] = {}\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                    rd, src, rd
                ));
            }
            return Some(format!("registers[{}] = {}", rd, src));
        }
    }
    None
}

fn generate_mvn(ops: &[Operand], sets_flags: bool) -> Option<String> {
    if ops.len() >= 1 {
        if let Operand::Register(rd) = ops[0] {
            let src = if ops.len() >= 2 { operand_to_expr(&ops[1]) } else { "0".to_string() };
            if sets_flags {
                return Some(format!(
                    "registers[{}] = {} ^ 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                    rd, src, rd
                ));
            }
            return Some(format!("registers[{}] = {} ^ 0xFFFFFFFF", rd, src));
        }
    }
    None
}

fn generate_add(ops: &[Operand], op: &str, sets_flags: bool) -> Option<String> {
    if ops.len() >= 1 {
        if let Operand::Register(rd) = ops[0] {
            let is_adc = op == "ADC";
            if ops.len() == 2 {
                let rd_str = format!("registers[{}]", rd);
                let op2 = operand_to_expr(&ops[1]);
                if sets_flags {
                    let carry = if is_adc { " + (1 if cpsr.get('c', 0) else 0)" } else { "" };
                    return Some(format!(
                        "_rn_val = {}\n_op2_val = {}\n_full = _rn_val + _op2_val{}\nregisters[{}] = _full & 0xFFFFFFFF\n_result = _full & 0xFFFFFFFF\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0\ncpsr['c'] = 1 if _full >= 0x100000000 else 0\n_rn_s = _rn_val if _rn_val < 0x80000000 else _rn_val - 0x100000000\n_op2_s = _op2_val if _op2_val < 0x80000000 else _op2_val - 0x100000000\n_result_s = _result if _result < 0x80000000 else _result - 0x100000000\ncpsr['v'] = 1 if (_rn_s >= 0 and _op2_s >= 0 and _result_s < 0) or (_rn_s < 0 and _op2_s < 0 and _result_s >= 0) else 0",
                        rd_str, op2, carry, rd
                    ));
                }
                if is_adc {
                    return Some(format!("{} = ({} + {} + (1 if cpsr['c'] else 0)) & 0xFFFFFFFF", rd_str, rd_str, op2));
                }
                return Some(format!("{} = ({} + {}) & 0xFFFFFFFF", rd_str, rd_str, op2));
            }
            if ops.len() >= 3 {
                let rn = operand_to_expr(&ops[1]);
                let op2 = operand_to_expr(&ops[2]);
                if sets_flags {
                    let carry = if is_adc { " + (1 if cpsr.get('c', 0) else 0)" } else { "" };
                    return Some(format!(
                        "_rn_val = {}\n_op2_val = {}\n_full = _rn_val + _op2_val{}\nregisters[{}] = _full & 0xFFFFFFFF\n_result = _full & 0xFFFFFFFF\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0\ncpsr['c'] = 1 if _full >= 0x100000000 else 0\n_rn_s = _rn_val if _rn_val < 0x80000000 else _rn_val - 0x100000000\n_op2_s = _op2_val if _op2_val < 0x80000000 else _op2_val - 0x100000000\n_result_s = _result if _result < 0x80000000 else _result - 0x100000000\ncpsr['v'] = 1 if (_rn_s >= 0 and _op2_s >= 0 and _result_s < 0) or (_rn_s < 0 and _op2_s < 0 and _result_s >= 0) else 0",
                        rn, op2, carry, rd
                    ));
                }
                if is_adc {
                    return Some(format!("registers[{}] = ({} + {} + (1 if cpsr['c'] else 0)) & 0xFFFFFFFF", rd, rn, op2));
                }
                return Some(format!("registers[{}] = ({} + {}) & 0xFFFFFFFF", rd, rn, op2));
            }
        }
    }
    None
}

fn generate_sub(ops: &[Operand], op: &str, sets_flags: bool) -> Option<String> {
    if ops.len() >= 1 {
        if let Operand::Register(rd) = ops[0] {
            let with_borrow = op == "SBC" || op == "RSC";
            let is_reversed = op == "RSB" || op == "RSC";

            // SUBS PC, LR: exception return — restore CPSR from SPSR, then set PC.
            if rd == 15 && sets_flags {
                let (a, b) = if ops.len() >= 3 {
                    (operand_to_expr(&ops[1]), operand_to_expr(&ops[2]))
                } else if ops.len() == 2 {
                    let rd_str = format!("registers[{}]", rd);
                    let op2 = operand_to_expr(&ops[1]);
                    if is_reversed { (op2, rd_str) } else { (rd_str, op2) }
                } else {
                    ("0".to_string(), "0".to_string())
                };
                let borrow = if with_borrow { " - (0 if cpsr.get('c', 0) else 1)" } else { "" };
                return Some(format!(
                    "_a_val = {a}\n_b_val = {b}\n_full = (_a_val - _b_val{borrow}) & 0xFFFFFFFF\n_new_cpsr = _spsr_for_mode(cpsr['mode'])\nregisters[15] = _full & 0xFFFFFFFE\ncpsr.clear()\ncpsr.update(_cpsr_from_int(_new_cpsr))\n_switch_mode(cpsr['mode'])\ncpsr['t'] = 1 if (_full & 1) else 0",
                    a = a, b = b, borrow = borrow
                ));
            }

            if ops.len() == 2 {
                let rd_str = format!("registers[{}]", rd);
                let op2 = operand_to_expr(&ops[1]);
                let (a, b) = if is_reversed {
                    (op2.as_str(), rd_str.as_str())
                } else {
                    (rd_str.as_str(), op2.as_str())
                };
                if sets_flags {
                    let borrow = if with_borrow { " - (0 if cpsr.get('c', 0) else 1)" } else { "" };
                    return Some(format!(
                        "_a_val = {}\n_b_val = {}\n_full = _a_val - _b_val{}\nregisters[{}] = _full & 0xFFFFFFFF\n_result = _full & 0xFFFFFFFF\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0\ncpsr['c'] = 1 if _full >= 0 else 0\n_a_s = _a_val if _a_val < 0x80000000 else _a_val - 0x100000000\n_b_s = _b_val if _b_val < 0x80000000 else _b_val - 0x100000000\n_result_s = _result if _result < 0x80000000 else _result - 0x100000000\ncpsr['v'] = 1 if (_a_s >= 0 and _b_s < 0 and _result_s < 0) or (_a_s < 0 and _b_s >= 0 and _result_s >= 0) else 0",
                        a, b, borrow, rd
                    ));
                }
                if with_borrow {
                    return Some(format!("registers[{}] = ({} - {} - (0 if cpsr.get('c', 0) else 1)) & 0xFFFFFFFF", rd, a, b));
                }
                return Some(format!("registers[{}] = ({} - {}) & 0xFFFFFFFF", rd, a, b));
            }
            if ops.len() >= 3 {
                let rn = operand_to_expr(&ops[1]);
                let op2 = operand_to_expr(&ops[2]);
                let (a, b) = if is_reversed {
                    (op2.as_str(), rn.as_str())
                } else {
                    (rn.as_str(), op2.as_str())
                };
                if sets_flags {
                    let borrow = if with_borrow { " - (0 if cpsr.get('c', 0) else 1)" } else { "" };
                    return Some(format!(
                        "_a_val = {}\n_b_val = {}\n_full = _a_val - _b_val{}\nregisters[{}] = _full & 0xFFFFFFFF\n_result = _full & 0xFFFFFFFF\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0\ncpsr['c'] = 1 if _full >= 0 else 0\n_a_s = _a_val if _a_val < 0x80000000 else _a_val - 0x100000000\n_b_s = _b_val if _b_val < 0x80000000 else _b_val - 0x100000000\n_result_s = _result if _result < 0x80000000 else _result - 0x100000000\ncpsr['v'] = 1 if (_a_s >= 0 and _b_s < 0 and _result_s < 0) or (_a_s < 0 and _b_s >= 0 and _result_s >= 0) else 0",
                        a, b, borrow, rd
                    ));
                }
                if with_borrow {
                    return Some(format!("registers[{}] = ({} - {} - (0 if cpsr.get('c', 0) else 1)) & 0xFFFFFFFF", rd, a, b));
                }
                return Some(format!("registers[{}] = ({} - {}) & 0xFFFFFFFF", rd, a, b));
            }
        }
    }
    None
}

fn generate_logic(ops: &[Operand], op: &str, sets_flags: bool) -> Option<String> {
    if ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if rd == 15 && sets_flags {
                // ANDS/EORS/ORRS/BICS PC, ...: exception return.
                let py_op = match op {
                    "AND" => "&",
                    "EOR" => "^",
                    "ORR" => "|",
                    "BIC" => "& ~",
                    _ => "&",
                };
                let (a, b) = if ops.len() >= 3 {
                    (operand_to_expr(&ops[1]), operand_to_expr(&ops[2]))
                } else {
                    (format!("registers[{}]", rd), operand_to_expr(&ops[1]))
                };
                return Some(format!(
                    "_full = ({a} {py_op} {b}) & 0xFFFFFFFF\n_new_cpsr = _spsr_for_mode(cpsr['mode'])\nregisters[15] = _full & 0xFFFFFFFE\ncpsr.clear()\ncpsr.update(_cpsr_from_int(_new_cpsr))\n_switch_mode(cpsr['mode'])\ncpsr['t'] = 1 if (_full & 1) else 0",
                    a = a, py_op = py_op, b = b
                ));
            }
            if rd == 15 {
                if ops.len() == 3 {
                    if let Operand::Register(rn_reg) = &ops[1] {
                        let imm = match &ops[2] {
                            Operand::Immediate(i) => *i,
                            _ => 0,
                        };
                        return Some(format!(
                            "registers[15] = (registers[{}] | {}) & 0xFFFFFFFC",
                            rn_reg, imm
                        ));
                    }
                }
            }

            if ops.len() == 2 {
                let src = operand_to_expr(&ops[1]);
                let py_op = match op {
                    "AND" => "&",
                    "EOR" => "^",
                    "ORR" => "|",
                    "BIC" => "& ~",
                    _ => "&",
                };
                if sets_flags {
                    return Some(format!(
                        "registers[{}] = (registers[{}] {} {}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                        rd, rd, py_op, src, rd
                    ));
                }
                return Some(format!("registers[{}] = (registers[{}] {} {}) & 0xFFFFFFFF", rd, rd, py_op, src));
            }

            if ops.len() >= 3 {
                let rn = operand_to_expr(&ops[1]);
                let op2 = operand_to_expr(&ops[2]);
                let py_op = match op {
                    "AND" => "&",
                    "EOR" => "^",
                    "ORR" => "|",
                    "BIC" => "& ~",
                    _ => "&",
                };
                if sets_flags {
                    return Some(format!(
                        "registers[{}] = ({} {} {}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                        rd, rn, py_op, op2, rd
                    ));
                }
                return Some(format!("registers[{}] = ({} {} {}) & 0xFFFFFFFF", rd, rn, py_op, op2));
            }
        }
    }
    None
}

fn generate_shift(ops: &[Operand], op: &str, sets_flags: bool) -> Option<String> {
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
            if sets_flags {
                return Some(format!(
                    "registers[{}] = ({} {} {}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                    rd, rn, py_op, shift, rd
                ));
            }
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
        let rn = operand_to_expr(&ops[0]);
        let rm = operand_to_expr(&ops[1]);
        
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
        let rn = operand_to_expr(&ops[0]);
        let rm = operand_to_expr(&ops[1]);
        
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
        let rn = operand_to_expr(&ops[0]);
        let rm = operand_to_expr(&ops[1]);
        
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
        let rn = operand_to_expr(&ops[0]);
        let rm = operand_to_expr(&ops[1]);
        
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
fn generate_umlal(ops: &[Operand], op: &str) -> Option<String> {
    if ops.len() >= 4 {
        if let Operand::Register(rdlo) = ops[0] {
            if let Operand::Register(rdhi) = ops[1] {
                if let Operand::Register(rm) = ops[2] {
                    if let Operand::Register(rs) = ops[3] {
                        let is_signed = op == "SMLAL";
                        let mul_type = if is_signed { "int(rm_val) * int(rs_val)" } else { "rm_val * rs_val" };
                        return Some(format!(
                            r#"rm_val = registers[{}]
rs_val = registers[{}]
product = {}
acc_lo = registers[{}] + (product & 0xFFFFFFFF)
acc_hi = registers[{}] + ((product >> 32) & 0xFFFFFFFF) + (1 if acc_lo < (product & 0xFFFFFFFF) else 0)
registers[{}] = acc_lo & 0xFFFFFFFF
registers[{}] = acc_hi & 0xFFFFFFFF"#,
                            rm, rs, mul_type, rdlo, rdhi, rdlo, rdhi
                        ));
                    }
                }
            }
        }
    }
    None
}
