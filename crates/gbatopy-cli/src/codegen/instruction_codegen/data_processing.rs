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
                        format!(
                            "((({} - 0x100000000) if {} & 0x80000000 else {}) >> {}) & 0xFFFFFFFF",
                            r, r, r, a
                        )
                    }
                }
                ShiftType::Ror => {
                    if amt == 0 {
                        format!(
                            "(({} >> 1) | ((1 if cpsr.get('c', 0) else 0) << 31)) & 0xFFFFFFFF",
                            r
                        )
                    } else {
                        format!(
                            "(({} >> {}) | ({} << (32 - {}))) & 0xFFFFFFFF",
                            r, amt, r, amt
                        )
                    }
                }
            }
        }
        ShiftAmount::Register(rs) => {
            let amt_expr = format!("(registers[{}] & 0xFF)", rs);
            match shift {
                ShiftType::Lsl => {
                    // LSL #0 → Rm; LSL #1-31 → Rm << n; LSL #32+ → 0
                    format!(
                        "(0 if {a} >= 32 else (({r} << {a}) & 0xFFFFFFFF if {a} != 0 else {r}))",
                        r = r,
                        a = amt_expr
                    )
                }
                ShiftType::Lsr => {
                    // LSR #0 → Rm; LSR #1-31 → Rm >> n; LSR #32+ → 0
                    format!(
                        "(0 if {a} >= 32 else (({r} >> {a}) & 0xFFFFFFFF if {a} != 0 else {r}))",
                        r = r,
                        a = amt_expr
                    )
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

/// Check if operand is RRX (ROR #0 with immediate shift amount).
fn is_rrx(op: &Operand) -> bool {
    matches!(op, Operand::ShiftedRegister { shift: ShiftType::Ror, amount: ShiftAmount::Immediate(0), .. })
}

/// Extract the source register from a ShiftedRegister operand.
fn shift_reg(op: &Operand) -> Option<u8> {
    match op {
        Operand::ShiftedRegister { reg, .. } => Some(*reg),
        _ => None,
    }
}

/// Return Python code to update cpsr['c'] with the shifter carry-out.
/// Returns None when carry is unchanged (LSL #0, bare register, immediate,
/// register-specified shift). RRX (ROR #0) also returns None because it
/// requires special handling: the old carry must be saved before updating.
fn shifter_carry_code(op: &Operand) -> Option<String> {
    match op {
        Operand::ShiftedRegister { reg, shift, amount } => {
            let r = format!("registers[{}]", reg);
            match amount {
                ShiftAmount::Immediate(amt) => {
                    let amt = *amt as u32;
                    match (shift, amt) {
                        (ShiftType::Lsl, 0) => None,
                        (ShiftType::Lsl, n) => Some(format!("cpsr['c'] = (({} >> (32 - {})) & 1)", r, n)),
                        (ShiftType::Lsr, 0) => Some(format!("cpsr['c'] = (({} >> 31) & 1)", r)),
                        (ShiftType::Lsr, n) => Some(format!("cpsr['c'] = (({} >> ({} - 1)) & 1)", r, n)),
                        (ShiftType::Asr, 0) => Some(format!("cpsr['c'] = (({} >> 31) & 1)", r)),
                        (ShiftType::Asr, n) => Some(format!("cpsr['c'] = (({} >> ({} - 1)) & 1)", r, n)),
                        (ShiftType::Ror, 0) => None,
                        (ShiftType::Ror, n) => Some(format!("cpsr['c'] = (({} >> ({} - 1)) & 1)", r, n)),
                    }
                }
                ShiftAmount::Register(_) => None,
            }
        }
        _ => None,
    }
}

/// Generate Python expression for an RRX-shifted value using _old_c
/// instead of cpsr['c']. Used when sets_flags=true to avoid reading
/// the already-updated carry.
fn rrx_value_expr(reg: u8) -> String {
    format!("((registers[{}] >> 1) | (_old_c << 31)) & 0xFFFFFFFF", reg)
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
/// ARM: PC = instruction_address + 8. Thumb: PC = (instruction_address + 4) & !3.
/// The destination register (ops[0] for instructions with Rd) is never replaced.
fn resolve_pc_operands(ops: &[Operand], inst: &DecodedInstruction, base_opcode: &str) -> Vec<Operand> {
    let pc_val = if inst.mode == gbatopy_disasm::ArmMode::Thumb {
        (inst.address + 4) & !3
    } else {
        inst.address + ARM_PC_OFFSET
    };
    let has_rd = !matches!(base_opcode, "CMP" | "CMN" | "TST" | "TEQ");
    ops.iter()
        .enumerate()
        .map(|(i, op)| {
            if has_rd && i == 0 {
                return op.clone();
            }
            match op {
                Operand::Register(15) => Operand::Immediate(pc_val),
                other => other.clone(),
            }
        })
        .collect()
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

    let ops = resolve_pc_operands(&inst.operands, inst, base_opcode);

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
        "NEG" => generate_neg(&ops, inst.sets_flags),
        "MUL" => generate_mul(&ops, inst.sets_flags),
        "SXTH" | "SXTB" | "UXTH" | "UXTB" => generate_extend(&ops, base_opcode),
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
    if !ops.is_empty() {
        if let Operand::Register(rd) = ops[0] {
            if rd == 15 {
                // MOVS PC, LR: exception return — restore CPSR from SPSR, then set PC.
                if sets_flags && ops.len() >= 2 {
                    let src_expr = operand_to_expr(&ops[1]);
                    return Some(format!(
                        "_new_cpsr = _spsr_for_mode(cpsr['mode'])\nregisters[15] = ({src}) & 0xFFFFFFFE\n_cpsr_from_int(cpsr, _new_cpsr)\n_switch_mode(cpsr['mode'])",
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

            let src = if ops.len() >= 2 {
                operand_to_expr(&ops[1])
            } else {
                "0".to_string()
            };
            if sets_flags {
                if ops.len() >= 2 {
                    if let Some(rm) = shift_reg(&ops[1]) {
                        if is_rrx(&ops[1]) {
                            return Some(format!(
                                "_old_c = cpsr.get('c', 0)\ncpsr['c'] = registers[{}] & 1\nregisters[{}] = {}\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                                rm, rd, rrx_value_expr(rm), rd
                            ));
                        }
                    }
                    let carry_line = shifter_carry_code(&ops[1])
                        .map(|c| format!("{}\n", c))
                        .unwrap_or_default();
                    return Some(format!(
                        "{}registers[{}] = {}\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                        carry_line, rd, src, rd
                    ));
                }
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
    if !ops.is_empty() {
        if let Operand::Register(rd) = ops[0] {
            let src = if ops.len() >= 2 {
                operand_to_expr(&ops[1])
            } else {
                "0".to_string()
            };
            if sets_flags {
                if ops.len() >= 2 {
                    if let Some(rm) = shift_reg(&ops[1]) {
                        if is_rrx(&ops[1]) {
                            return Some(format!(
                                "_old_c = cpsr.get('c', 0)\ncpsr['c'] = registers[{}] & 1\nregisters[{}] = ({} ^ 0xFFFFFFFF) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                                rm, rd, rrx_value_expr(rm), rd
                            ));
                        }
                    }
                    let carry_line = shifter_carry_code(&ops[1])
                        .map(|c| format!("{}\n", c))
                        .unwrap_or_default();
                    return Some(format!(
                        "{}registers[{}] = ({} ^ 0xFFFFFFFF) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                        carry_line, rd, src, rd
                    ));
                }
                return Some(format!(
                    "registers[{}] = ({} ^ 0xFFFFFFFF) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                    rd, src, rd
                ));
            }
            return Some(format!("registers[{}] = ({} ^ 0xFFFFFFFF) & 0xFFFFFFFF", rd, src));
        }
    }
    None
}

fn generate_add(ops: &[Operand], op: &str, sets_flags: bool) -> Option<String> {
    if !ops.is_empty() {
        if let Operand::Register(rd) = ops[0] {
            let is_adc = op == "ADC";
            if ops.len() == 2 {
                let rd_str = format!("registers[{}]", rd);
                let op2 = operand_to_expr(&ops[1]);
                if sets_flags {
                    let carry = if is_adc {
                        " + (1 if cpsr.get('c', 0) else 0)"
                    } else {
                        ""
                    };
                    return Some(format!(
                        "_rn_val = {}\n_op2_val = {}\n_full = _rn_val + _op2_val{}\nregisters[{}] = _full & 0xFFFFFFFF\n_result = _full & 0xFFFFFFFF\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0\ncpsr['c'] = 1 if _full >= 0x100000000 else 0\n_rn_s = _rn_val if _rn_val < 0x80000000 else _rn_val - 0x100000000\n_op2_s = _op2_val if _op2_val < 0x80000000 else _op2_val - 0x100000000\n_result_s = _result if _result < 0x80000000 else _result - 0x100000000\ncpsr['v'] = 1 if (_rn_s >= 0 and _op2_s >= 0 and _result_s < 0) or (_rn_s < 0 and _op2_s < 0 and _result_s >= 0) else 0",
                        rd_str, op2, carry, rd
                    ));
                }
                if is_adc {
                    return Some(format!(
                        "{} = ({} + (({})) + (1 if cpsr['c'] else 0)) & 0xFFFFFFFF",
                        rd_str, rd_str, op2
                    ));
                }
                return Some(format!("{} = ({} + {}) & 0xFFFFFFFF", rd_str, rd_str, op2));
            }
            if ops.len() >= 3 {
                let rn = operand_to_expr(&ops[1]);
                let op2 = operand_to_expr(&ops[2]);
                if sets_flags {
                    let carry = if is_adc {
                        " + (1 if cpsr.get('c', 0) else 0)"
                    } else {
                        ""
                    };
                    return Some(format!(
                        "_rn_val = {}\n_op2_val = {}\n_full = _rn_val + _op2_val{}\nregisters[{}] = _full & 0xFFFFFFFF\n_result = _full & 0xFFFFFFFF\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0\ncpsr['c'] = 1 if _full >= 0x100000000 else 0\n_rn_s = _rn_val if _rn_val < 0x80000000 else _rn_val - 0x100000000\n_op2_s = _op2_val if _op2_val < 0x80000000 else _op2_val - 0x100000000\n_result_s = _result if _result < 0x80000000 else _result - 0x100000000\ncpsr['v'] = 1 if (_rn_s >= 0 and _op2_s >= 0 and _result_s < 0) or (_rn_s < 0 and _op2_s < 0 and _result_s >= 0) else 0",
                        rn, op2, carry, rd
                    ));
                }
                if is_adc {
                    return Some(format!(
                        "registers[{}] = ({} + (({})) + (1 if cpsr['c'] else 0)) & 0xFFFFFFFF",
                        rd, rn, op2
                    ));
                }
                return Some(format!(
                    "registers[{}] = ({} + {}) & 0xFFFFFFFF",
                    rd, rn, op2
                ));
            }
        }
    }
    None
}

fn generate_sub(ops: &[Operand], op: &str, sets_flags: bool) -> Option<String> {
    if !ops.is_empty() {
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
                    if is_reversed {
                        (op2, rd_str)
                    } else {
                        (rd_str, op2)
                    }
                } else {
                    ("0".to_string(), "0".to_string())
                };
                let borrow = if with_borrow {
                    " - (0 if cpsr.get('c', 0) else 1)"
                } else {
                    ""
                };
                return Some(format!(
                    "_a_val = {a}\n_b_val = {b}\n_full = (_a_val - _b_val{borrow}) & 0xFFFFFFFF\n_new_cpsr = _spsr_for_mode(cpsr['mode'])\nregisters[15] = _full & 0xFFFFFFFE\n_cpsr_from_int(cpsr, _new_cpsr)\n_switch_mode(cpsr['mode'])",
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
                    let borrow = if with_borrow {
                        " - (0 if cpsr.get('c', 0) else 1)"
                    } else {
                        ""
                    };
                    return Some(format!(
                        "_a_val = {}\n_b_val = {}\n_full = _a_val - _b_val{}\nregisters[{}] = _full & 0xFFFFFFFF\n_result = _full & 0xFFFFFFFF\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0\ncpsr['c'] = 1 if _a_val >= _b_val else 0\n_a_s = _a_val if _a_val < 0x80000000 else _a_val - 0x100000000\n_b_s = _b_val if _b_val < 0x80000000 else _b_val - 0x100000000\n_result_s = _result if _result < 0x80000000 else _result - 0x100000000\ncpsr['v'] = 1 if (_a_s >= 0 and _b_s < 0 and _result_s < 0) or (_a_s < 0 and _b_s >= 0 and _result_s >= 0) else 0",
                        a, b, borrow, rd
                    ));
                }
                if with_borrow {
                    return Some(format!("registers[{}] = ({} - (({})) - (0 if cpsr.get('c', 0) else 1)) & 0xFFFFFFFF", rd, a, b));
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
                    let borrow = if with_borrow {
                        " - (0 if cpsr.get('c', 0) else 1)"
                    } else {
                        ""
                    };
                    return Some(format!(
                        "_a_val = {}\n_b_val = {}\n_full = _a_val - _b_val{}\nregisters[{}] = _full & 0xFFFFFFFF\n_result = _full & 0xFFFFFFFF\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0\ncpsr['c'] = 1 if _a_val >= _b_val else 0\n_a_s = _a_val if _a_val < 0x80000000 else _a_val - 0x100000000\n_b_s = _b_val if _b_val < 0x80000000 else _b_val - 0x100000000\n_result_s = _result if _result < 0x80000000 else _result - 0x100000000\ncpsr['v'] = 1 if (_a_s >= 0 and _b_s < 0 and _result_s < 0) or (_a_s < 0 and _b_s >= 0 and _result_s >= 0) else 0",
                        a, b, borrow, rd
                    ));
                }
                if with_borrow {
                    return Some(format!("registers[{}] = ({} - (({})) - (0 if cpsr.get('c', 0) else 1)) & 0xFFFFFFFF", rd, a, b));
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
                    "_full = ({a} {py_op} {b}) & 0xFFFFFFFF\n_new_cpsr = _spsr_for_mode(cpsr['mode'])\nregisters[15] = _full & 0xFFFFFFFE\n_cpsr_from_int(cpsr, _new_cpsr)\n_switch_mode(cpsr['mode'])",
                    a = a, py_op = py_op, b = b
                ));
            }
            // Not collapsed: nested R15 handling with specific operand checks
            #[allow(clippy::collapsible_if)]
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
                    if let Some(rm) = shift_reg(&ops[1]) {
                        if is_rrx(&ops[1]) {
                            return Some(format!(
                                "_old_c = cpsr.get('c', 0)\ncpsr['c'] = registers[{}] & 1\nregisters[{}] = (registers[{}] {} {}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                                rm, rd, rd, py_op, rrx_value_expr(rm), rd
                            ));
                        }
                    }
                    let carry_line = shifter_carry_code(&ops[1])
                        .map(|c| format!("{}\n", c))
                        .unwrap_or_default();
                    return Some(format!(
                        "{}registers[{}] = (registers[{}] {} {}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                        carry_line, rd, rd, py_op, src, rd
                    ));
                }
                return Some(format!(
                    "registers[{}] = (registers[{}] {} {}) & 0xFFFFFFFF",
                    rd, rd, py_op, src
                ));
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
                    if let Some(rm) = shift_reg(&ops[2]) {
                        if is_rrx(&ops[2]) {
                            return Some(format!(
                                "_old_c = cpsr.get('c', 0)\ncpsr['c'] = registers[{}] & 1\nregisters[{}] = ({} {} {}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                                rm, rd, rn, py_op, rrx_value_expr(rm), rd
                            ));
                        }
                    }
                    let carry_line = shifter_carry_code(&ops[2])
                        .map(|c| format!("{}\n", c))
                        .unwrap_or_default();
                    return Some(format!(
                        "{}registers[{}] = ({} {} {}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                        carry_line, rd, rn, py_op, op2, rd
                    ));
                }
                return Some(format!(
                    "registers[{}] = ({} {} {}) & 0xFFFFFFFF",
                    rd, rn, py_op, op2
                ));
            }
        }
    }
    None
}

/// Generate Python code to update cpsr['c'] for shift instructions
/// (LSL/LSR/ASR/ROR). Must be emitted BEFORE the destination register is
/// updated so the source value is still original. Returns empty string when
/// carry is unchanged (LSL #0 only).
fn shift_carry_code(op: &str, src_expr: &str, shift_operand: &Operand) -> String {
    match shift_operand {
        Operand::Immediate(amt) => {
            let amt = *amt as u32;
            match (op, amt) {
                ("LSL", 0) => String::new(),
                ("LSL", n) if n < 32 => format!("cpsr['c'] = ({} >> (32 - {})) & 1", src_expr, n),
                ("LSL", _) => format!("cpsr['c'] = {} & 1", src_expr),
                ("LSR", 0) => format!("cpsr['c'] = ({} >> 31) & 1", src_expr),
                ("LSR", n) if n < 32 => format!("cpsr['c'] = ({} >> ({} - 1)) & 1", src_expr, n),
                ("LSR", _) => format!("cpsr['c'] = ({} >> 31) & 1", src_expr),
                ("ASR", 0) => format!("cpsr['c'] = ({} >> 31) & 1", src_expr),
                ("ASR", n) if n < 32 => format!("cpsr['c'] = ({} >> ({} - 1)) & 1", src_expr, n),
                ("ASR", _) => format!("cpsr['c'] = ({} >> 31) & 1", src_expr),
                ("ROR", 0) => format!("cpsr['c'] = {} & 1", src_expr),
                ("ROR", n) => format!("cpsr['c'] = ({} >> ({} - 1)) & 1", src_expr, n),
                _ => String::new(),
            }
        }
        Operand::Register(rs) => {
            let rs_expr = format!("registers[{}]", rs);
            match op {
                "LSL" => format!(
                    "_sh = ({}) & 0xFF\ncpsr['c'] = (0 if _sh > 32 else ({} & 1 if _sh == 32 else (({} >> (32 - _sh)) & 1 if 0 < _sh < 32 else cpsr.get('c', 0))))",
                    rs_expr, src_expr, src_expr
                ),
                "LSR" => format!(
                    "_sh = ({}) & 0xFF\ncpsr['c'] = (({} >> 31) & 1 if _sh >= 32 else (({} >> (_sh - 1)) & 1 if 0 < _sh < 32 else cpsr.get('c', 0)))",
                    rs_expr, src_expr, src_expr
                ),
                "ASR" => format!(
                    "_sh = ({}) & 0xFF\ncpsr['c'] = (({} >> 31) & 1 if _sh >= 32 else (({} >> (_sh - 1)) & 1 if 0 < _sh < 32 else cpsr.get('c', 0)))",
                    rs_expr, src_expr, src_expr
                ),
                "ROR" => format!(
                    "_sh = ({}) & 0xFF\n_n = _sh & 31\ncpsr['c'] = (({} >> 31) & 1 if _sh > 0 and _n == 0 else (({} >> (_n - 1)) & 1 if _n > 0 else cpsr.get('c', 0)))",
                    rs_expr, src_expr, src_expr
                ),
                _ => String::new(),
            }
        }
        _ => String::new(),
    }
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
            let expr = match op {
                "LSL" => format!("({} << {})", rn, shift),
                "LSR" => {
                    match &ops[2] {
                        Operand::Immediate(0) => format!("({} >> 32)", rn),
                        _ => format!("({} >> {})", rn, shift),
                    }
                }
                "ASR" => {
                    match &ops[2] {
                        Operand::Immediate(0) => format!("((({} - 0x100000000) if ({} & 0x80000000) else ({})) >> 32)", rn, rn, rn),
                        _ => format!(
                            "((({} - 0x100000000) if ({} & 0x80000000) else ({})) >> {})",
                            rn, rn, rn, shift
                        ),
                    }
                }
                "ROR" => format!(
                    "(({} >> ({} & 31)) | ({} << (32 - ({} & 31))))",
                    rn, shift, rn, shift
                ),
                _ => return None,
            };
            if sets_flags {
                let carry_line = shift_carry_code(op, &rn, &ops[2]);
                let carry_prefix = if carry_line.is_empty() { String::new() } else { format!("{}\n", carry_line) };
                return Some(format!(
                    "{}registers[{}] = ({}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                    carry_prefix, rd, expr, rd
                ));
            }
            return Some(format!("registers[{}] = ({}) & 0xFFFFFFFF", rd, expr));
        }
    } else if ops.len() == 2 {
        if let Operand::Register(rd) = ops[0] {
            let rn = format!("registers[{}]", rd);
            let shift = match &ops[1] {
                Operand::Immediate(i) => format!("{}", i),
                Operand::Register(r) => format!("registers[{}]", r),
                _ => "0".to_string(),
            };
            let expr = match op {
                "LSL" => format!("({} << {})", rn, shift),
                "LSR" => {
                    match &ops[1] {
                        Operand::Immediate(0) => format!("({} >> 32)", rn),
                        _ => format!("({} >> {})", rn, shift),
                    }
                }
                "ASR" => {
                    match &ops[1] {
                        Operand::Immediate(0) => format!("((({} - 0x100000000) if ({} & 0x80000000) else ({})) >> 32)", rn, rn, rn),
                        _ => format!(
                            "((({} - 0x100000000) if ({} & 0x80000000) else ({})) >> {})",
                            rn, rn, rn, shift
                        ),
                    }
                }
                "ROR" => format!(
                    "(({} >> ({} & 31)) | ({} << (32 - ({} & 31))))",
                    rn, shift, rn, shift
                ),
                _ => return None,
            };
            if sets_flags {
                let carry_line = shift_carry_code(op, &rn, &ops[1]);
                let carry_prefix = if carry_line.is_empty() { String::new() } else { format!("{}\n", carry_line) };
                return Some(format!(
                    "{}registers[{}] = ({}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                    carry_prefix, rd, expr, rd
                ));
            }
            return Some(format!("registers[{}] = ({}) & 0xFFFFFFFF", rd, expr));
        }
    }
    None
}

fn generate_neg(ops: &[Operand], sets_flags: bool) -> Option<String> {
    if ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            let rs = operand_to_expr(&ops[1]);
            if sets_flags {
                return Some(format!(
                    "_a_val = 0\n_b_val = {}\n_full = _a_val - _b_val\nregisters[{}] = _full & 0xFFFFFFFF\n_result = _full & 0xFFFFFFFF\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0\ncpsr['c'] = 1 if _a_val >= _b_val else 0\n_a_s = 0\n_b_s = _b_val if _b_val < 0x80000000 else _b_val - 0x100000000\n_result_s = _result if _result < 0x80000000 else _result - 0x100000000\ncpsr['v'] = 1 if (_a_s >= 0 and _b_s < 0 and _result_s < 0) or (_a_s < 0 and _b_s >= 0 and _result_s >= 0) else 0",
                    rs, rd
                ));
            }
            return Some(format!("registers[{}] = (0 - {}) & 0xFFFFFFFF", rd, rs));
        }
    }
    None
}

fn generate_mul(ops: &[Operand], sets_flags: bool) -> Option<String> {
    if ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            let rm = format!("registers[{}]", rd);
            let rs = match &ops[1] {
                Operand::Register(r) => format!("registers[{}]", r),
                _ => return None,
            };
            if sets_flags {
                return Some(format!(
                    "registers[{}] = ({} * {}) & 0xFFFFFFFF\n_result = registers[{}]\ncpsr['n'] = (_result >> 31) & 1\ncpsr['z'] = 1 if _result == 0 else 0",
                    rd, rm, rs, rd
                ));
            }
            return Some(format!("registers[{}] = ({} * {}) & 0xFFFFFFFF", rd, rm, rs));
        }
    }
    None
}

fn generate_extend(ops: &[Operand], op: &str) -> Option<String> {
    if ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            let rm = match &ops[1] {
                Operand::Register(r) => format!("registers[{}]", r),
                _ => return None,
            };
            let code = match op {
                "SXTH" => format!(
                    "_v = {rm} & 0xFFFF
registers[{rd}] = _v | (0xFFFF0000 if _v & 0x8000 else 0)"
                ),
                "SXTB" => format!(
                    "_v = {rm} & 0xFF
registers[{rd}] = _v | (0xFFFFFF00 if _v & 0x80 else 0)"
                ),
                "UXTH" => format!("registers[{rd}] = {rm} & 0xFFFF"),
                "UXTB" => format!("registers[{rd}] = {rm} & 0xFF"),
                _ => return None,
            };
            return Some(code);
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
_rn_s = {rn} if {rn} < 0x80000000 else {rn} - 0x100000000
_rm_s = {rm} if {rm} < 0x80000000 else {rm} - 0x100000000
_result_s = result_cmp if result_cmp < 0x80000000 else result_cmp - 0x100000000
if (_rn_s >= 0 and _rm_s < 0 and _result_s < 0) or (_rn_s < 0 and _rm_s >= 0 and _result_s >= 0):
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
        if let Some(rm) = shift_reg(&ops[1]) {
            if is_rrx(&ops[1]) {
                return Some(format!(
                    "_old_c = cpsr.get('c', 0)\ncpsr['c'] = registers[{}] & 1\nresult_tst = {rn} & {}\ncpsr['n'] = (result_tst >> 31) & 1\ncpsr['z'] = 1 if result_tst == 0 else 0",
                    rm, rrx_value_expr(rm)
                ));
            }
        }
        let carry_line = shifter_carry_code(&ops[1])
            .map(|c| format!("{}\n", c))
            .unwrap_or_default();
        let rm = operand_to_expr(&ops[1]);
        return Some(format!(
            "{}result_tst = {rn} & {rm}\ncpsr['n'] = (result_tst >> 31) & 1\ncpsr['z'] = 1 if result_tst == 0 else 0",
            carry_line
        ));
    }
    None
}

fn generate_teq(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 2 {
        let rn = operand_to_expr(&ops[0]);
        if let Some(rm) = shift_reg(&ops[1]) {
            if is_rrx(&ops[1]) {
                return Some(format!(
                    "_old_c = cpsr.get('c', 0)\ncpsr['c'] = registers[{}] & 1\nresult_teq = {rn} ^ {}\ncpsr['n'] = (result_teq >> 31) & 1\ncpsr['z'] = 1 if result_teq == 0 else 0",
                    rm, rrx_value_expr(rm)
                ));
            }
        }
        let carry_line = shifter_carry_code(&ops[1])
            .map(|c| format!("{}\n", c))
            .unwrap_or_default();
        let rm = operand_to_expr(&ops[1]);
        return Some(format!(
            "{}result_teq = {rn} ^ {rm}\ncpsr['n'] = (result_teq >> 31) & 1\ncpsr['z'] = 1 if result_teq == 0 else 0",
            carry_line
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
                        let mul_type = if is_signed {
                            "int(rm_val) * int(rs_val)"
                        } else {
                            "rm_val * rs_val"
                        };
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

#[cfg(test)]
mod tests {
    use super::*;
    use gbatopy_disasm::{operand::ShiftAmount, operand::ShiftType, ArmMode, Condition, DecodedInstruction, Operand};

    fn make_inst(
        opcode: &str,
        operands: Vec<Operand>,
        sets_flags: bool,
        mode: ArmMode,
        addr: u32,
    ) -> DecodedInstruction {
        DecodedInstruction {
            address: addr,
            opcode: opcode.to_string(),
            operands,
            condition: Some(Condition::Al),
            mode,
            raw: 0,
            sets_flags,
            width: if mode == ArmMode::Arm { 4 } else { 2 },
            is_data: false,
        }
    }

    // === MOV tests ===
    #[test]
    fn test_generate_mov_register() {
        let inst = make_inst(
            "MOV",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[0] = registers[1]");
    }

    #[test]
    fn test_generate_mov_immediate() {
        let inst = make_inst(
            "MOV",
            vec![Operand::Register(0), Operand::Immediate(42)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[0] = 42");
    }

    #[test]
    fn test_generate_mov_pc_immediate() {
        let inst = make_inst(
            "MOV",
            vec![Operand::Register(15), Operand::Immediate(0x08000100)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[15] = 0x08000100");
    }

    #[test]
    fn test_generate_mov_sets_flags() {
        let inst = make_inst(
            "MOV",  // Use "MOV" not "MOVS" - the S suffix is handled via sets_flags field
            vec![Operand::Register(0), Operand::Immediate(42)],
            true,  // sets_flags = true
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[0] = 42"));
        assert!(code.contains("cpsr['n']"));
        assert!(code.contains("cpsr['z']"));
    }

    #[test]
    fn test_generate_mov_pc_register() {
        let inst = make_inst(
            "MOV",
            vec![Operand::Register(15), Operand::Register(14)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[15] = registers[14] & 0xFFFFFFFC"));
    }

    // === MVN tests ===
    #[test]
    fn test_generate_mvn_immediate() {
        let inst = make_inst(
            "MVN",
            vec![Operand::Register(0), Operand::Immediate(0)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[0] = (0 ^ 0xFFFFFFFF) & 0xFFFFFFFF");
    }

    #[test]
    fn test_generate_mvn_register() {
        let inst = make_inst(
            "MVN",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[0] = (registers[1] ^ 0xFFFFFFFF) & 0xFFFFFFFF");
    }

    // === ADD tests ===
    #[test]
    fn test_generate_add_register_register() {
        let inst = make_inst(
            "ADD",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = (registers[1] + registers[2]) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_add_register_immediate() {
        let inst = make_inst(
            "ADD",
            vec![Operand::Register(0), Operand::Register(1), Operand::Immediate(5)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = (registers[1] + 5) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_add_sets_flags() {
        let inst = make_inst(
            "ADD",  // Use "ADD" not "ADDS" - the S suffix is handled via sets_flags field
            vec![Operand::Register(0), Operand::Register(1), Operand::Immediate(100)],
            true,  // sets_flags = true
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("_rn_val = registers[1]"));
        assert!(code.contains("_op2_val = 100"));
        assert!(code.contains("cpsr['n']"));
        assert!(code.contains("cpsr['z']"));
        assert!(code.contains("cpsr['c']"));
        assert!(code.contains("cpsr['v']"));
    }

    #[test]
    fn test_generate_adc() {
        let inst = make_inst(
            "ADC",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("+ (1 if cpsr['c'] else 0)"));
    }

    // === SUB tests ===
    #[test]
    fn test_generate_sub_register_register() {
        let inst = make_inst(
            "SUB",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = (registers[1] - registers[2]) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_sub_register_immediate() {
        let inst = make_inst(
            "SUB",
            vec![Operand::Register(0), Operand::Register(1), Operand::Immediate(10)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = (registers[1] - 10) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_rsb() {
        let inst = make_inst(
            "RSB",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[0] = (registers[2] - registers[1])"));
    }

    #[test]
    fn test_generate_sbc() {
        let inst = make_inst(
            "SBC",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("- (0 if cpsr.get('c', 0) else 1)"));
    }

    // === Logic operations tests ===
    #[test]
    fn test_generate_and() {
        let inst = make_inst(
            "AND",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = (registers[1] & registers[2]) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_eor() {
        let inst = make_inst(
            "EOR",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = (registers[1] ^ registers[2]) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_orr() {
        let inst = make_inst(
            "ORR",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = (registers[1] | registers[2]) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bic() {
        let inst = make_inst(
            "BIC",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("& ~"));
    }

    // === Shift operations tests ===
    #[test]
    fn test_generate_lsl() {
        let inst = make_inst(
            "LSL",
            vec![Operand::Register(0), Operand::Register(1), Operand::Immediate(5)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[1] << 5"));
        assert!(code.contains("& 0xFFFFFFFF"));
    }

    #[test]
    fn test_generate_lsr() {
        let inst = make_inst(
            "LSR",
            vec![Operand::Register(0), Operand::Register(1), Operand::Immediate(10)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[1] >> 10"));
        assert!(code.contains("& 0xFFFFFFFF"));
    }

    #[test]
    fn test_generate_asr() {
        let inst = make_inst(
            "ASR",
            vec![Operand::Register(0), Operand::Register(1), Operand::Immediate(3)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("0x80000000"));
        assert!(code.contains("0x100000000"));
        assert!(code.contains("& 0xFFFFFFFF"));
    }

    #[test]
    fn test_generate_ror() {
        let inst = make_inst(
            "ROR",
            vec![Operand::Register(0), Operand::Register(1), Operand::Immediate(7)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("32 - (7 & 31)"));
        assert!(!code.contains("registers[1] | 7"));
        assert!(code.contains("& 0xFFFFFFFF"));
    }

    // === Comparison tests ===
    #[test]
    fn test_generate_cmp() {
        let inst = make_inst(
            "CMP",
            vec![Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("result_cmp = (registers[1] - registers[2])"));
        assert!(code.contains("cpsr['n']"));
        assert!(code.contains("cpsr['z']"));
        assert!(code.contains("cpsr['c']"));
        assert!(code.contains("cpsr['v']"));
    }

    #[test]
    fn test_generate_cmn() {
        let inst = make_inst(
            "CMN",
            vec![Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("result_cmn = (registers[1] + registers[2])"));
        assert!(code.contains("cpsr['n']"));
        assert!(code.contains("cpsr['z']"));
    }

    #[test]
    fn test_generate_tst() {
        let inst = make_inst(
            "TST",
            vec![Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("result_tst = registers[1] & registers[2]"));
        assert!(code.contains("cpsr['n']"));
        assert!(code.contains("cpsr['z']"));
    }

    #[test]
    fn test_generate_teq() {
        let inst = make_inst(
            "TEQ",
            vec![Operand::Register(1), Operand::Register(2)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("result_teq = registers[1] ^ registers[2]"));
        assert!(code.contains("cpsr['n']"));
        assert!(code.contains("cpsr['z']"));
    }

    // === CLZ test ===
    #[test]
    fn test_generate_clz() {
        let inst = make_inst(
            "CLZ",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[0] = 32 - len(bin"));
        assert!(code.contains("registers[1]"));
    }

    // === UMLAL test ===
    #[test]
    fn test_generate_umlal() {
        let inst = make_inst(
            "UMLAL",
            vec![
                Operand::Register(0),  // RdLo
                Operand::Register(1),  // RdHi
                Operand::Register(2),  // Rm
                Operand::Register(3),  // Rs
            ],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("rm_val = registers[2]"));
        assert!(code.contains("rs_val = registers[3]"));
        assert!(code.contains("product = rm_val * rs_val"));
        assert!(code.contains("registers[0] = acc_lo & 0xFFFFFFFF"));
        assert!(code.contains("registers[1] = acc_hi & 0xFFFFFFFF"));
    }

    // === Extend tests ===
    #[test]
    fn test_generate_sxth() {
        let inst = make_inst(
            "SXTH",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Thumb,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("0xFFFF"));
        assert!(code.contains("0x8000"));
        assert!(code.contains("registers[0]"));
    }

    #[test]
    fn test_generate_sxtb() {
        let inst = make_inst(
            "SXTB",
            vec![Operand::Register(2), Operand::Register(3)],
            false,
            ArmMode::Thumb,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("0xFF"));
        assert!(code.contains("0x80"));
        assert!(code.contains("registers[2]"));
    }

    #[test]
    fn test_generate_uxth() {
        let inst = make_inst(
            "UXTH",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Thumb,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("& 0xFFFF"));
        assert!(!code.contains("0x8000"));
    }

    #[test]
    fn test_generate_uxtb() {
        let inst = make_inst(
            "UXTB",
            vec![Operand::Register(4), Operand::Register(5)],
            false,
            ArmMode::Thumb,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("& 0xFF"));
        assert!(!code.contains("0x80"));
    }

    // === Shifted register tests ===
    #[test]
    fn test_generate_mov_shifted_register_lsl() {
        let inst = DecodedInstruction {
            address: 0x08000000,
            opcode: "MOV".to_string(),
            operands: vec![
                Operand::Register(0),
                Operand::ShiftedRegister {
                    reg: 1,
                    shift: ShiftType::Lsl,
                    amount: ShiftAmount::Immediate(4),
                },
            ],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };
        let code = generate(&inst).unwrap();
        assert!(code.contains("(registers[1] << 4) & 0xFFFFFFFF"));
    }

    #[test]
    fn test_generate_mov_shifted_register_lsr() {
        let inst = DecodedInstruction {
            address: 0x08000000,
            opcode: "MOV".to_string(),
            operands: vec![
                Operand::Register(0),
                Operand::ShiftedRegister {
                    reg: 1,
                    shift: ShiftType::Lsr,
                    amount: ShiftAmount::Immediate(0),
                },
            ],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };
        let code = generate(&inst).unwrap();
        // LSR #0 is shift by 32
        assert!(code.contains("registers[1] >> 32"));
    }

    #[test]
    fn test_generate_mov_shifted_register_ror_rrx() {
        let inst = DecodedInstruction {
            address: 0x08000000,
            opcode: "MOV".to_string(),
            operands: vec![
                Operand::Register(0),
                Operand::ShiftedRegister {
                    reg: 1,
                    shift: ShiftType::Ror,
                    amount: ShiftAmount::Immediate(0),
                },
            ],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };
        let code = generate(&inst).unwrap();
        // RRX uses cpsr.get('c', 0)
        assert!(code.contains("cpsr.get('c', 0)"));
    }

    // === PC resolution tests ===
    #[test]
    fn test_generate_add_pc_source() {
        let inst = make_inst(
            "ADD",
            vec![Operand::Register(0), Operand::Register(1), Operand::Register(15)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        // PC should be resolved to address + 8 = 0x08000008 = 134217736 (decimal)
        // The operand_to_expr function formats immediates as decimal
        assert!(code.contains("134217736"), "Expected PC value 134217736 (0x08000008) in: {}", code);
    }

    // === Conditional execution tests ===
    #[test]
    fn test_generate_mov_conditional_eq() {
        let inst = make_inst(
            "MOVeq",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "if cpsr_check('EQ'):\n    registers[0] = registers[1]");
    }

    #[test]
    fn test_generate_add_conditional_ne() {
        let inst = make_inst(
            "ADDne",
            vec![Operand::Register(0), Operand::Register(1), Operand::Immediate(42)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "if cpsr_check('NE'):\n    registers[0] = (registers[1] + 42) & 0xFFFFFFFF");
    }

    // === Exception return tests ===
    #[test]
    fn test_generate_movs_pc_lr_exception_return() {
        let inst = make_inst(
            "MOV",  // Use "MOV" not "MOVS" - the S suffix is handled via sets_flags field
            vec![Operand::Register(15), Operand::Register(14)],
            true,  // sets_flags = true
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("_new_cpsr = _spsr_for_mode(cpsr['mode'])"));
        assert!(code.contains("registers[15] = (registers[14]) & 0xFFFFFFFE"));
        assert!(code.contains("_cpsr_from_int"));
        assert!(code.contains("_switch_mode"));
    }

    #[test]
    fn test_generate_subs_pc_lr_exception_return() {
        let inst = make_inst(
            "SUB",  // Use "SUB" not "SUBS" - the S suffix is handled via sets_flags field
            vec![Operand::Register(15), Operand::Register(14), Operand::Immediate(0)],
            true,  // sets_flags = true
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("_new_cpsr = _spsr_for_mode(cpsr['mode'])"));
        assert!(code.contains("registers[15] = _full & 0xFFFFFFFE"));
    }

    // === Edge cases ===
    #[test]
    fn test_generate_add_two_operands_immediate() {
        let inst = make_inst(
            "ADD",
            vec![Operand::Register(0), Operand::Immediate(100)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[0] = (registers[0] + 100)"));
    }

    #[test]
    fn test_generate_sub_two_operands_register() {
        let inst = make_inst(
            "SUB",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[0] = (registers[0] - registers[1])"));
    }

    // === Register-specified shift tests ===
    #[test]
    fn test_generate_mov_register_specified_shift_lsl() {
        let inst = DecodedInstruction {
            address: 0x08000000,
            opcode: "MOV".to_string(),
            operands: vec![
                Operand::Register(0),
                Operand::ShiftedRegister {
                    reg: 1,
                    shift: ShiftType::Lsl,
                    amount: ShiftAmount::Register(2),
                },
            ],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[2] & 0xFF"));
        assert!(code.contains("0 if"));
        assert!(code.contains(">= 32"));
    }

    // === SMLAL test ===
    #[test]
    fn test_generate_smlal_signed() {
        let inst = make_inst(
            "SMLAL",
            vec![
                Operand::Register(0),
                Operand::Register(1),
                Operand::Register(2),
                Operand::Register(3),
            ],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("int(rm_val) * int(rs_val)"));
    }
}
