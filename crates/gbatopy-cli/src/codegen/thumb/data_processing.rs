use gbatopy_disasm::Operand;

// --- Logical operations (set N, Z; C preserved or from shifter; V preserved) ---

pub fn generate_thumb_and(ops: &[String]) -> String {
    format!(
        r#"result_and = (registers[{}] & registers[{}]) & 0xFFFFFFFF
registers[{}] = result_and
cpsr['n'] = (result_and >> 31) & 1
cpsr['z'] = 1 if result_and == 0 else 0"#,
        ops[0], ops[1], ops[0]
    )
}

pub fn generate_thumb_eor(ops: &[String]) -> String {
    format!(
        r#"result_eor = (registers[{}] ^ registers[{}]) & 0xFFFFFFFF
registers[{}] = result_eor
cpsr['n'] = (result_eor >> 31) & 1
cpsr['z'] = 1 if result_eor == 0 else 0"#,
        ops[0], ops[1], ops[0]
    )
}

pub fn generate_thumb_orr(ops: &[String]) -> String {
    format!(
        r#"result_orr = (registers[{}] | registers[{}]) & 0xFFFFFFFF
registers[{}] = result_orr
cpsr['n'] = (result_orr >> 31) & 1
cpsr['z'] = 1 if result_orr == 0 else 0"#,
        ops[0], ops[1], ops[0]
    )
}

pub fn generate_thumb_bic(ops: &[String]) -> String {
    format!(
        r#"result_bic = (registers[{}] & (~registers[{}] & 0xFFFFFFFF)) & 0xFFFFFFFF
registers[{}] = result_bic
cpsr['n'] = (result_bic >> 31) & 1
cpsr['z'] = 1 if result_bic == 0 else 0"#,
        ops[0], ops[1], ops[0]
    )
}

pub fn generate_thumb_mvn(ops: &[String]) -> String {
    format!(
        r#"result_mvn = (~registers[{}]) & 0xFFFFFFFF
registers[{}] = result_mvn
cpsr['n'] = (result_mvn >> 31) & 1
cpsr['z'] = 1 if result_mvn == 0 else 0"#,
        ops[1], ops[0]
    )
}

pub fn generate_thumb_tst(ops: &[String]) -> String {
    format!(
        r#"result_tst = registers[{}] & registers[{}]
cpsr['n'] = (result_tst >> 31) & 1
cpsr['z'] = 1 if result_tst == 0 else 0"#,
        ops[0], ops[1]
    )
}

// --- Arithmetic operations (set N, Z, C, V) ---

pub fn generate_thumb_adc(ops: &[String]) -> String {
    format!(
        r#"carry_in = 1 if cpsr.get('c', 0) else 0
result_adc = (registers[{}] + registers[{}] + carry_in) & 0xFFFFFFFF
cpsr['c'] = 1 if (registers[{}] + registers[{}] + carry_in) > 0xFFFFFFFF else 0
cpsr['v'] = 1 if ((registers[{}] ^ result_adc) & (registers[{}] ^ result_adc) & 0x80000000) else 0
registers[{}] = result_adc
cpsr['n'] = (result_adc >> 31) & 1
cpsr['z'] = 1 if result_adc == 0 else 0"#,
        ops[0], ops[1],
        ops[0], ops[1],
        ops[0], ops[1],
        ops[0]
    )
}

pub fn generate_thumb_sbc(ops: &[String]) -> String {
    format!(
        r#"not_c = 0 if cpsr.get('c', 0) else 1
result_sbc = (registers[{}] - registers[{}] - not_c) & 0xFFFFFFFF
cpsr['c'] = 1 if registers[{}] >= (registers[{}] + not_c) else 0
cpsr['v'] = 1 if ((registers[{}] ^ registers[{}]) & (registers[{}] ^ result_sbc) & 0x80000000) else 0
registers[{}] = result_sbc
cpsr['n'] = (result_sbc >> 31) & 1
cpsr['z'] = 1 if result_sbc == 0 else 0"#,
        ops[0], ops[1],
        ops[0], ops[1],
        ops[0], ops[1], ops[0],
        ops[0]
    )
}

pub fn generate_thumb_neg(ops: &[String]) -> String {
    format!(
        r#"result_neg = (0 - registers[{}]) & 0xFFFFFFFF
cpsr['c'] = 1 if 0 >= registers[{}] else 0
cpsr['v'] = 1 if (registers[{}] & result_neg & 0x80000000) else 0
registers[{}] = result_neg
cpsr['n'] = (result_neg >> 31) & 1
cpsr['z'] = 1 if result_neg == 0 else 0"#,
        ops[1], ops[1], ops[1], ops[0]
    )
}

pub fn generate_thumb_mul_thumb(ops: &[String]) -> String {
    format!(
        r#"result_mul = (registers[{}] * registers[{}]) & 0xFFFFFFFF
registers[{}] = result_mul
cpsr['n'] = (result_mul >> 31) & 1
cpsr['z'] = 1 if result_mul == 0 else 0"#,
        ops[0], ops[1], ops[0]
    )
}

// --- CMP / CMN (compare, result discarded) ---

pub fn generate_thumb_cmp_imm(ops: &[String]) -> String {
    let rd = &ops[0];
    let imm = &ops[1];
    format!(
        r#"result_cmp = (registers[{}] - {}) & 0xFFFFFFFF
cpsr['n'] = (result_cmp >> 31) & 1
cpsr['z'] = 1 if result_cmp == 0 else 0
cpsr['c'] = 1 if registers[{}] >= {} else 0
cpsr['v'] = 1 if ((registers[{}] ^ {}) & (registers[{}] ^ result_cmp) & 0x80000000) else 0"#,
        rd, imm, rd, imm, rd, imm, rd
    )
}

pub fn generate_thumb_cmp_reg(ops: &[String]) -> String {
    format!(
        r#"result_cmp = (registers[{}] - registers[{}]) & 0xFFFFFFFF
cpsr['n'] = (result_cmp >> 31) & 1
cpsr['z'] = 1 if result_cmp == 0 else 0
cpsr['c'] = 1 if registers[{}] >= registers[{}] else 0
cpsr['v'] = 1 if ((registers[{}] ^ registers[{}]) & (registers[{}] ^ result_cmp) & 0x80000000) else 0"#,
        ops[0], ops[1], ops[0], ops[1], ops[0], ops[1], ops[0]
    )
}

pub fn generate_thumb_cmn(ops: &[String]) -> String {
    format!(
        r#"result_cmn = (registers[{}] + registers[{}]) & 0xFFFFFFFF
cpsr['n'] = (result_cmn >> 31) & 1
cpsr['z'] = 1 if result_cmn == 0 else 0
cpsr['c'] = 1 if (registers[{}] + registers[{}]) > 0xFFFFFFFF else 0
cpsr['v'] = 1 if ((registers[{}] ^ result_cmn) & (registers[{}] ^ result_cmn) & 0x80000000) else 0"#,
        ops[0], ops[1], ops[0], ops[1], ops[0], ops[1]
    )
}

// --- ADD (all forms set N, Z, C, V except hi-reg which sets no flags) ---

pub fn generate_thumb_add_imm3(ops: &[String]) -> String {
    let rd = &ops[0];
    let rn = &ops[1];
    let imm = &ops[2];
    format!(
        r#"result_add = (registers[{}] + {}) & 0xFFFFFFFF
cpsr['c'] = 1 if (registers[{}] + {}) > 0xFFFFFFFF else 0
cpsr['v'] = 1 if ((registers[{}] ^ result_add) & ({} ^ result_add) & 0x80000000) else 0
registers[{}] = result_add
cpsr['n'] = (result_add >> 31) & 1
cpsr['z'] = 1 if result_add == 0 else 0"#,
        rn, imm, rn, imm, rn, imm, rd
    )
}

pub fn generate_thumb_add_reg(ops: &[String]) -> String {
    format!(
        r#"result_add = (registers[{}] + registers[{}]) & 0xFFFFFFFF
cpsr['c'] = 1 if (registers[{}] + registers[{}]) > 0xFFFFFFFF else 0
cpsr['v'] = 1 if ((registers[{}] ^ result_add) & (registers[{}] ^ result_add) & 0x80000000) else 0
registers[{}] = result_add
cpsr['n'] = (result_add >> 31) & 1
cpsr['z'] = 1 if result_add == 0 else 0"#,
        ops[1], ops[2], ops[1], ops[2], ops[1], ops[2], ops[0]
    )
}

pub fn generate_thumb_add_imm8(ops: &[String]) -> String {
    let rd = &ops[0];
    let imm = &ops[1];
    format!(
        r#"result_add = (registers[{}] + {}) & 0xFFFFFFFF
cpsr['c'] = 1 if (registers[{}] + {}) > 0xFFFFFFFF else 0
cpsr['v'] = 1 if ((registers[{}] ^ result_add) & ({} ^ result_add) & 0x80000000) else 0
registers[{}] = result_add
cpsr['n'] = (result_add >> 31) & 1
cpsr['z'] = 1 if result_add == 0 else 0"#,
        rd, imm, rd, imm, rd, imm, rd
    )
}

// ADD Rd, Rm (hi-register) — does NOT set flags
pub fn generate_thumb_add_hi(ops: &[String]) -> String {
    format!(
        "registers[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF",
        ops[0], ops[0], ops[1]
    )
}

// --- SUB (all forms set N, Z, C, V except hi-reg which doesn't exist for SUB) ---

pub fn generate_thumb_sub_imm3(ops: &[String]) -> String {
    let rd = &ops[0];
    let rn = &ops[1];
    let imm = &ops[2];
    format!(
        r#"result_sub = (registers[{}] - {}) & 0xFFFFFFFF
cpsr['c'] = 1 if registers[{}] >= {} else 0
cpsr['v'] = 1 if ((registers[{}] ^ {}) & (registers[{}] ^ result_sub) & 0x80000000) else 0
registers[{}] = result_sub
cpsr['n'] = (result_sub >> 31) & 1
cpsr['z'] = 1 if result_sub == 0 else 0"#,
        rn, imm, rn, imm, rn, imm, rn, rd
    )
}

pub fn generate_thumb_sub_reg(ops: &[String]) -> String {
    format!(
        r#"result_sub = (registers[{}] - registers[{}]) & 0xFFFFFFFF
cpsr['c'] = 1 if registers[{}] >= registers[{}] else 0
cpsr['v'] = 1 if ((registers[{}] ^ registers[{}]) & (registers[{}] ^ result_sub) & 0x80000000) else 0
registers[{}] = result_sub
cpsr['n'] = (result_sub >> 31) & 1
cpsr['z'] = 1 if result_sub == 0 else 0"#,
        ops[1], ops[2], ops[1], ops[2], ops[1], ops[2], ops[1], ops[0]
    )
}

pub fn generate_thumb_sub_imm8(ops: &[String]) -> String {
    let rd = &ops[0];
    let imm = &ops[1];
    format!(
        r#"result_sub = (registers[{}] - {}) & 0xFFFFFFFF
cpsr['c'] = 1 if registers[{}] >= {} else 0
cpsr['v'] = 1 if ((registers[{}] ^ {}) & (registers[{}] ^ result_sub) & 0x80000000) else 0
registers[{}] = result_sub
cpsr['n'] = (result_sub >> 31) & 1
cpsr['z'] = 1 if result_sub == 0 else 0"#,
        rd, imm, rd, imm, rd, imm, rd, rd
    )
}

// --- MOV ---

// MOV Rd, #imm8 — sets N, Z
pub fn generate_thumb_mov_imm(ops: &[String]) -> String {
    let rd = &ops[0];
    let imm = &ops[1];
    format!(
        r#"registers[{}] = {}
cpsr['n'] = (registers[{}] >> 31) & 1
cpsr['z'] = 1 if registers[{}] == 0 else 0"#,
        rd, imm, rd, rd
    )
}

// MOV Rd, Rm (hi-register) — does NOT set flags
pub fn generate_thumb_mov_reg(ops: &[String]) -> String {
    format!("registers[{}] = registers[{}]", ops[0], ops[1])
}

// --- Shifts by immediate (format 1: set N, Z, C; V preserved) ---

pub fn generate_thumb_lsl_imm(ops: &[String]) -> String {
    let rd = &ops[0];
    let rs = &ops[1];
    let imm: u32 = ops[2].parse().unwrap_or(0);
    if imm == 0 {
        // LSL #0 = MOV Rd, Rs; C preserved
        format!(
            r#"result_lsl = registers[{}]
registers[{}] = result_lsl
cpsr['n'] = (result_lsl >> 31) & 1
cpsr['z'] = 1 if result_lsl == 0 else 0"#,
            rs, rd
        )
    } else {
        format!(
            r#"result_lsl = (registers[{}] << {}) & 0xFFFFFFFF
cpsr['c'] = (registers[{}] >> {}) & 1
registers[{}] = result_lsl
cpsr['n'] = (result_lsl >> 31) & 1
cpsr['z'] = 1 if result_lsl == 0 else 0"#,
            rs, imm, rs, 32 - imm, rd
        )
    }
}

pub fn generate_thumb_lsr_imm(ops: &[String]) -> String {
    let rd = &ops[0];
    let rs = &ops[1];
    let imm: u32 = ops[2].parse().unwrap_or(0);
    if imm == 0 {
        // LSR #0 encodes LSR #32: result = 0, C = bit 31
        format!(
            r#"cpsr['c'] = (registers[{}] >> 31) & 1
result_lsr = 0
registers[{}] = result_lsr
cpsr['n'] = 0
cpsr['z'] = 1"#,
            rs, rd
        )
    } else {
        format!(
            r#"result_lsr = (registers[{}] >> {}) & 0xFFFFFFFF
cpsr['c'] = (registers[{}] >> {}) & 1
registers[{}] = result_lsr
cpsr['n'] = (result_lsr >> 31) & 1
cpsr['z'] = 1 if result_lsr == 0 else 0"#,
            rs, imm, rs, imm - 1, rd
        )
    }
}

pub fn generate_thumb_asr_imm(ops: &[String]) -> String {
    let rd = &ops[0];
    let rs = &ops[1];
    let imm: u32 = ops[2].parse().unwrap_or(0);
    if imm == 0 {
        // ASR #0 encodes ASR #32: sign-extend, C = bit 31
        format!(
            r#"cpsr['c'] = (registers[{}] >> 31) & 1
if registers[{}] & 0x80000000:
    result_asr = 0xFFFFFFFF
else:
    result_asr = 0
registers[{}] = result_asr
cpsr['n'] = (result_asr >> 31) & 1
cpsr['z'] = 1 if result_asr == 0 else 0"#,
            rs, rs, rd
        )
    } else {
        format!(
            r#"val_asr = registers[{}]
if val_asr & 0x80000000:
    val_asr -= 0x100000000
result_asr = (val_asr >> {}) & 0xFFFFFFFF
cpsr['c'] = (registers[{}] >> {}) & 1
registers[{}] = result_asr
cpsr['n'] = (result_asr >> 31) & 1
cpsr['z'] = 1 if result_asr == 0 else 0"#,
            rs, imm, rs, imm - 1, rd
        )
    }
}

// ROR by immediate — only exists in ARM, not Thumb format 1.
// Kept for completeness; Thumb ROR is format 4 (register form).
pub fn generate_thumb_ror_imm(ops: &[String]) -> String {
    let rd = &ops[0];
    let rs = &ops[1];
    let imm: u32 = ops[2].parse().unwrap_or(1);
    if imm == 0 {
        // ROR #0 = RRX (rotate right extended): C shifted in
        format!(
            r#"carry_in = 1 if cpsr.get('c', 0) else 0
result_ror = ((registers[{}] >> 1) | (carry_in << 31)) & 0xFFFFFFFF
cpsr['c'] = registers[{}] & 1
registers[{}] = result_ror
cpsr['n'] = (result_ror >> 31) & 1
cpsr['z'] = 1 if result_ror == 0 else 0"#,
            rs, rs, rd
        )
    } else {
        format!(
            r#"result_ror = ((registers[{}] >> {}) | (registers[{}] << {})) & 0xFFFFFFFF
cpsr['c'] = (registers[{}] >> {}) & 1
registers[{}] = result_ror
cpsr['n'] = (result_ror >> 31) & 1
cpsr['z'] = 1 if result_ror == 0 else 0"#,
            rs, imm, rs, 32 - imm, rs, imm - 1, rd
        )
    }
}

// --- Shifts by register (format 4: set N, Z, C; V preserved) ---

pub fn generate_thumb_lsl_reg(ops: &[String]) -> String {
    format!(
        r#"shift = registers[{}] & 0xFF
if shift == 0:
    result_lsl = registers[{}]
elif shift < 32:
    cpsr['c'] = (registers[{}] >> (32 - shift)) & 1
    result_lsl = (registers[{}] << shift) & 0xFFFFFFFF
elif shift == 32:
    cpsr['c'] = registers[{}] & 1
    result_lsl = 0
else:
    cpsr['c'] = 0
    result_lsl = 0
registers[{}] = result_lsl
cpsr['n'] = (result_lsl >> 31) & 1
cpsr['z'] = 1 if result_lsl == 0 else 0"#,
        ops[1], ops[0], ops[0], ops[0], ops[0], ops[0]
    )
}

pub fn generate_thumb_lsr_reg(ops: &[String]) -> String {
    format!(
        r#"shift = registers[{}] & 0xFF
if shift == 0:
    result_lsr = registers[{}]
elif shift < 32:
    cpsr['c'] = (registers[{}] >> (shift - 1)) & 1
    result_lsr = (registers[{}] >> shift) & 0xFFFFFFFF
elif shift == 32:
    cpsr['c'] = (registers[{}] >> 31) & 1
    result_lsr = 0
else:
    cpsr['c'] = 0
    result_lsr = 0
registers[{}] = result_lsr
cpsr['n'] = (result_lsr >> 31) & 1
cpsr['z'] = 1 if result_lsr == 0 else 0"#,
        ops[1], ops[0], ops[0], ops[0], ops[0], ops[0]
    )
}

pub fn generate_thumb_asr_reg(ops: &[String]) -> String {
    format!(
        r#"shift = registers[{}] & 0xFF
if shift == 0:
    result_asr = registers[{}]
elif shift < 32:
    val_asr = registers[{}]
    if val_asr & 0x80000000:
        val_asr -= 0x100000000
    result_asr = (val_asr >> shift) & 0xFFFFFFFF
    cpsr['c'] = (registers[{}] >> (shift - 1)) & 1
elif shift >= 32:
    cpsr['c'] = (registers[{}] >> 31) & 1
    if registers[{}] & 0x80000000:
        result_asr = 0xFFFFFFFF
    else:
        result_asr = 0
registers[{}] = result_asr
cpsr['n'] = (result_asr >> 31) & 1
cpsr['z'] = 1 if result_asr == 0 else 0"#,
        ops[1], ops[0], ops[0], ops[0], ops[0], ops[0], ops[0]
    )
}

pub fn generate_thumb_ror_reg(ops: &[String]) -> String {
    format!(
        r#"shift = registers[{}] & 0x1F
if shift == 0:
    result_ror = registers[{}]
    cpsr['c'] = (registers[{}] >> 31) & 1
else:
    result_ror = ((registers[{}] >> shift) | (registers[{}] << (32 - shift))) & 0xFFFFFFFF
    cpsr['c'] = (registers[{}] >> (shift - 1)) & 1
registers[{}] = result_ror
cpsr['n'] = (result_ror >> 31) & 1
cpsr['z'] = 1 if result_ror == 0 else 0"#,
        ops[1], ops[0], ops[0], ops[0], ops[0], ops[0], ops[0]
    )
}

pub fn generate(inst: &gbatopy_disasm::DecodedInstruction) -> Option<String> {
    let opcode_raw = &inst.opcode.to_uppercase();
    let ops: Vec<String> = inst.operands.iter().map(|op| op.to_codegen()).collect();

    // Strip condition codes from opcode (e.g. "ADDMI" -> "ADD", "ADCVC" -> "ADC")
    let valid_conditions = [
        "EQ", "NE", "CS", "CC", "MI", "PL", "VS", "VC", "HI", "LS", "GE", "LT", "GT", "LE",
    ];
    let opcode = if opcode_raw.len() > 2 {
        let maybe_cond = &opcode_raw[opcode_raw.len() - 2..];
        if valid_conditions.contains(&maybe_cond) {
            opcode_raw[..opcode_raw.len() - 2].to_string()
        } else {
            opcode_raw.clone()
        }
    } else {
        opcode_raw.clone()
    };

    // Helper: check if operand at index is an Immediate
    let is_imm = |idx: usize| -> bool {
        inst.operands
            .get(idx)
            .map(|op| matches!(op, Operand::Immediate(_)))
            .unwrap_or(false)
    };

    match opcode.as_str() {
        "AND" => Some(generate_thumb_and(&ops)),
        "EOR" => Some(generate_thumb_eor(&ops)),
        "ORR" => Some(generate_thumb_orr(&ops)),
        "BIC" => Some(generate_thumb_bic(&ops)),
        "ADC" => Some(generate_thumb_adc(&ops)),
        "SBC" => Some(generate_thumb_sbc(&ops)),
        "NEG" => Some(generate_thumb_neg(&ops)),
        "MUL" => Some(generate_thumb_mul_thumb(&ops)),
        "MVN" => Some(generate_thumb_mvn(&ops)),
        "TST" => Some(generate_thumb_tst(&ops)),
        "CMN" => Some(generate_thumb_cmn(&ops)),
        "MOV" => {
            if ops.len() >= 2 {
                if is_imm(1) {
                    Some(generate_thumb_mov_imm(&ops))
                } else {
                    Some(generate_thumb_mov_reg(&ops))
                }
            } else {
                None
            }
        }
        "CMP" => {
            if ops.len() >= 2 {
                if is_imm(1) {
                    Some(generate_thumb_cmp_imm(&ops))
                } else {
                    Some(generate_thumb_cmp_reg(&ops))
                }
            } else {
                None
            }
        }
        "ADD" => {
            if ops.len() == 3 {
                if is_imm(2) {
                    Some(generate_thumb_add_imm3(&ops))
                } else {
                    Some(generate_thumb_add_reg(&ops))
                }
            } else if ops.len() == 2 {
                if is_imm(1) {
                    Some(generate_thumb_add_imm8(&ops))
                } else {
                    Some(generate_thumb_add_hi(&ops))
                }
            } else {
                None
            }
        }
        "SUB" => {
            if ops.len() == 3 {
                if is_imm(2) {
                    Some(generate_thumb_sub_imm3(&ops))
                } else {
                    Some(generate_thumb_sub_reg(&ops))
                }
            } else if ops.len() == 2 {
                Some(generate_thumb_sub_imm8(&ops))
            } else {
                None
            }
        }
        "LSL" => {
            if ops.len() == 3 {
                Some(generate_thumb_lsl_imm(&ops))
            } else {
                Some(generate_thumb_lsl_reg(&ops))
            }
        }
        "LSR" => {
            if ops.len() == 3 {
                Some(generate_thumb_lsr_imm(&ops))
            } else {
                Some(generate_thumb_lsr_reg(&ops))
            }
        }
        "ASR" => {
            if ops.len() == 3 {
                Some(generate_thumb_asr_imm(&ops))
            } else {
                Some(generate_thumb_asr_reg(&ops))
            }
        }
        "ROR" => {
            if ops.len() == 3 {
                Some(generate_thumb_ror_imm(&ops))
            } else {
                Some(generate_thumb_ror_reg(&ops))
            }
        }
        _ => None,
    }
}
