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
    let base_opcode = opcode.split_whitespace().next().unwrap_or(opcode);
    let base_opcode = base_opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());

    let ops = resolve_pc_operands(&inst.operands, inst.address, base_opcode);

    match base_opcode {
        "MOV" => generate_mov(&ops),
        "MVN" => generate_mvn(&ops),
        "ADD" | "ADC" => generate_add(&ops, base_opcode),
        "SUB" | "SBC" | "RSB" | "RSC" => generate_sub(&ops, base_opcode, inst.sets_flags),
        "AND" | "EOR" | "ORR" | "BIC" => generate_logic(&ops, base_opcode),
        "LSL" | "LSR" | "ASR" | "ROR" => generate_shift(&ops, base_opcode),
        "CLZ" => generate_clz(&ops),
        "CMP" => generate_cmp(&ops),
        "CMN" => generate_cmn(&ops),
        "TST" => generate_tst(&ops),
        "TEQ" => generate_teq(&ops),
        "UMLAL" | "SMLAL" => generate_umlal(&ops, base_opcode),
        _ => None,
    }
}

fn generate_mov(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 1 {
        if let Operand::Register(rd) = ops[0] {
            // CRITICAL: MOV to PC (R15) is a branch!
            if rd == 15 {
                // MOV PC, #imm - direct jump to immediate address
                if ops.len() >= 2 {
                    if let Operand::Immediate(imm) = &ops[1] {
                        return Some(format!("registers[15] = 0x{:08X}", imm));
                    }
                }
                // MOV PC, Rn - indirect jump via register
                if ops.len() >= 2 {
                    if let Operand::Register(rn) = &ops[1] {
                        return Some(format!("registers[15] = registers[{}] & 0xFFFFFFFC", rn));
                    }
                }
            }
            
            let src = if ops.len() >= 2 { operand_to_expr(&ops[1]) } else { "0".to_string() };
            return Some(format!("registers[{}] = {}", rd, src));
        }
    }
    None
}

fn generate_mvn(ops: &[Operand]) -> Option<String> {
    if ops.len() >= 1 {
        if let Operand::Register(rd) = ops[0] {
            let src = if ops.len() >= 2 { operand_to_expr(&ops[1]) } else { "0".to_string() };
            return Some(format!("registers[{}] = {} ^ 0xFFFFFFFF", rd, src));
        }
    }
    None
}

fn generate_add(ops: &[Operand], op: &str) -> Option<String> {
    if ops.len() >= 1 {
        if let Operand::Register(rd) = ops[0] {
            // Handle 2-operand form: ADD Rd, op2 (same as ADD Rd, Rd, op2)
            if ops.len() == 2 {
                let rd_str = format!("registers[{}]", rd);
                let op2 = operand_to_expr(&ops[1]);
                if op == "ADC" {
                    return Some(format!("{} = ({} + {} + (1 if cpsr['c'] else 0)) & 0xFFFFFFFF", rd_str, rd_str, op2));
                }
                return Some(format!("{} = ({} + {}) & 0xFFFFFFFF", rd_str, rd_str, op2));
            }
            // Handle 3-operand form: ADD Rd, Rn, op2
            if ops.len() >= 3 {
                let rn = operand_to_expr(&ops[1]);
                let op2 = operand_to_expr(&ops[2]);
                if op == "ADC" {
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
            if ops.len() == 2 {
                let rd_str = format!("registers[{}]", rd);
                let op2 = operand_to_expr(&ops[1]);
                let result_var = format!("result_sub_{}", rd);
                let sub_code = match op {
                    "RSB" => format!("{} = ({} - {}) & 0xFFFFFFFF", result_var, op2, rd_str),
                    "RSC" => format!("{} = ({} - {} - (0 if cpsr['c'] else 1)) & 0xFFFFFFFF", result_var, op2, rd_str),
                    "SBC" => format!("{} = ({} - {} - (0 if cpsr['c'] else 1)) & 0xFFFFFFFF", result_var, rd_str, op2),
                    _ => format!("{} = ({} - {}) & 0xFFFFFFFF", result_var, rd_str, op2),
                };
                if sets_flags {
                    let flag_code = format!(
                        "{}\n{} = {}\nresult_sub_cmp = {} & 0xFFFFFFFF\ncpsr['z'] = 1 if result_sub_cmp == 0 else 0\ncpsr['n'] = 1 if result_sub_cmp >= 0x80000000 else 0",
                        sub_code, rd_str, result_var, result_var
                    );
                    return Some(flag_code);
                } else {
                    return Some(format!("{}\n{} = {}", sub_code, rd_str, result_var));
                }
            }
            if ops.len() >= 3 {
                let rn = operand_to_expr(&ops[1]);
                let op2 = operand_to_expr(&ops[2]);
                let result_var = format!("result_sub_{}", rd);
                let sub_code = match op {
                    "RSB" => format!("{} = ({} - {}) & 0xFFFFFFFF", result_var, op2, rn),
                    "RSC" => format!("{} = ({} - {} - (0 if cpsr['c'] else 1)) & 0xFFFFFFFF", result_var, op2, rn),
                    "SBC" => format!("{} = ({} - {} - (0 if cpsr['c'] else 1)) & 0xFFFFFFFF", result_var, rn, op2),
                    _ => format!("{} = ({} - {}) & 0xFFFFFFFF", result_var, rn, op2),
                };
                if sets_flags {
                    let flag_code = format!(
                        "{}\nregisters[{}] = {}\nresult_sub_cmp = {} & 0xFFFFFFFF\ncpsr['z'] = 1 if result_sub_cmp == 0 else 0\ncpsr['n'] = 1 if result_sub_cmp >= 0x80000000 else 0",
                        sub_code, rd, result_var, result_var
                    );
                    return Some(flag_code);
                } else {
                    return Some(format!("{}\nregisters[{}] = {}", sub_code, rd, result_var));
                }
            }
        }
    }
    None
}

fn generate_logic(ops: &[Operand], op: &str) -> Option<String> {
    if ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            // CRITICAL: Writing to PC (R15) is a branch!
            if rd == 15 {
                // ORR PC, Rn, #imm - this is a branch to computed address
                if ops.len() == 3 {
                    if let Operand::Register(rn_reg) = &ops[1] {
                        // ORR PC, Rn, #imm - jump to Rn | imm
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
            
            // Handle 2-operand form: ORR Rd, #imm or ORR Rd, Rm
            if ops.len() == 2 {
                let src = operand_to_expr(&ops[1]);
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
                let op2 = operand_to_expr(&ops[2]);
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
