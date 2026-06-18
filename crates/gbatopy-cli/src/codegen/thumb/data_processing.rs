pub fn generate_thumb_and(ops: &[String]) -> String {
    // Thumb AND Rd, Rs - 2 operands only (Rd is both source and destination)
    format!("registers[{}] = (registers[{}] & registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

pub fn generate_thumb_eor(ops: &[String]) -> String {
    // Thumb EOR Rd, Rs - 2 operands only
    format!("registers[{}] = (registers[{}] ^ registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

pub fn generate_thumb_orr(ops: &[String]) -> String {
    // Thumb ORR Rd, Rs - 2 operands only
    format!("registers[{}] = (registers[{}] | registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

pub fn generate_thumb_bic(ops: &[String]) -> String {
    // Thumb BIC Rd, Rs - 2 operands only
    format!("registers[{}] = (registers[{}] & ~registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

pub fn generate_thumb_adc(ops: &[String]) -> String {
    // Thumb ADC Rd, Rs - 2 operands only
    format!(
        "registers[{}] = (registers[{}] + registers[{}] + (1 if registers[18] else 0)) & 0xFFFFFFFF",
        ops[0], ops[0], ops[1]
    )
}

pub fn generate_thumb_sbc(ops: &[String]) -> String {
    // Thumb SBC Rd, Rs - 2 operands only
    format!(
        "registers[{}] = (registers[{}] - registers[{}] - (0 if registers[18] else 1)) & 0xFFFFFFFF",
        ops[0], ops[0], ops[1]
    )
}

pub fn generate_thumb_neg(ops: &[String]) -> String {
    format!("registers[{}] = (0 - registers[{}]) & 0xFFFFFFFF", ops[0], ops[1])
}

pub fn generate_thumb_mul_thumb(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] * registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

// MOV Rd, #imm8 - Move immediate to low register
pub fn generate_thumb_mov_imm(ops: &[String]) -> String {
    format!("registers[{}] = {}", ops[0], ops[1])
}

// MOV Rd, Rm - Move register (format_5_hi_reg)
pub fn generate_thumb_mov_reg(ops: &[String]) -> String {
    format!("registers[{}] = registers[{}]", ops[0], ops[1])
}

// CMP Rn, #imm8 - Compare immediate
pub fn generate_thumb_cmp_imm(ops: &[String]) -> String {
    let rd = &ops[0];
    let imm = &ops[1];
    format!(
        "result = (registers[{}] - {}) & 0xFFFFFFFF\n\
         registers[16] = 1 if (result & 0x80000000) else 0\n\
         registers[17] = 1 if result == 0 else 0\n\
         registers[18] = 1 if registers[{}] >= {} else 0\n\
         registers[19] = 0",
        rd, imm, rd, imm
    )
}

// CMP Rn, Rm - Compare register
pub fn generate_thumb_cmp_reg(ops: &[String]) -> String {
    format!(
        "result = (registers[{}] - registers[{}]) & 0xFFFFFFFF\n\
         registers[16] = 1 if (result & 0x80000000) else 0\n\
         registers[17] = 1 if result == 0 else 0\n\
         registers[18] = 1 if registers[{}] >= registers[{}] else 0\n\
         registers[19] = 0",
        ops[0], ops[1], ops[0], ops[1]
    )
}

// ADD Rd, Rn, #imm3 - Add immediate to register
pub fn generate_thumb_add_imm3(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] + {}) & 0xFFFFFFFF", ops[0], ops[1], ops[2])
}

// ADD Rd, Rn, Rm - Add register to register
pub fn generate_thumb_add_reg(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF", ops[0], ops[1], ops[2])
}

// ADD Rd, #imm8 - Add immediate to low register
pub fn generate_thumb_add_imm8(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] + {}) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

// ADD Rd, Rm - Add high registers (format_5_hi_reg)
pub fn generate_thumb_add_hi(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

// SUB Rd, Rn, #imm3 - Subtract immediate from register
pub fn generate_thumb_sub_imm3(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] - {}) & 0xFFFFFFFF", ops[0], ops[1], ops[2])
}

// SUB Rd, Rn, Rm - Subtract register from register
pub fn generate_thumb_sub_reg(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] - registers[{}]) & 0xFFFFFFFF", ops[0], ops[1], ops[2])
}

// SUB Rd, #imm8 - Subtract immediate from low register
pub fn generate_thumb_sub_imm8(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] - {}) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

// LSL Rd, Rs, #imm5 - Logical shift left by immediate
pub fn generate_thumb_lsl_imm(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] << {}) & 0xFFFFFFFF", ops[0], ops[1], ops[2])
}

// LSR Rd, Rs, #imm5 - Logical shift right by immediate
pub fn generate_thumb_lsr_imm(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] >> {}) & 0xFFFFFFFF", ops[0], ops[1], ops[2])
}

// ASR Rd, Rs, #imm5 - Arithmetic shift right by immediate
pub fn generate_thumb_asr_imm(ops: &[String]) -> String {
    // Arithmetic shift preserves sign bit
    format!(
        "registers[{}] = (registers[{}] >> {}) | ((registers[{}] >> 31) * 0xFFFFFFFF << (32 - {})) & 0xFFFFFFFF",
        ops[0], ops[1], ops[2], ops[1], ops[2]
    )
}

// ROR Rd, Rs, #imm5 - Rotate right by immediate
pub fn generate_thumb_ror_imm(ops: &[String]) -> String {
    format!(
        "registers[{}] = ((registers[{}] >> {}) | (registers[{}] << (32 - {}))) & 0xFFFFFFFF",
        ops[0], ops[1], ops[2], ops[1], ops[2]
    )
}

// MVN Rd, Rs - Move not (bitwise complement)
pub fn generate_thumb_mvn(ops: &[String]) -> String {
    format!("registers[{}] = (~registers[{}]) & 0xFFFFFFFF", ops[0], ops[1])
}

// CMN Rn, Rm - Compare negative (add and set flags)
pub fn generate_thumb_cmn(ops: &[String]) -> String {
    format!(
        "result = (registers[{}] + registers[{}]) & 0xFFFFFFFF\n\
         registers[16] = 1 if (result & 0x80000000) else 0\n\
         registers[17] = 1 if result == 0 else 0\n\
         registers[18] = 1 if (registers[{}] + registers[{}]) >= 0x100000000 else 0\n\
         registers[19] = 1 if ((registers[{}] ^ registers[{}]) & 0x80000000) == 0 else 0",
        ops[0], ops[1], ops[0], ops[1], ops[0], ops[1]
    )
}

// TST Rn, Rm - Test (AND and set flags)
pub fn generate_thumb_tst(ops: &[String]) -> String {
    format!(
        "result = registers[{}] & registers[{}]\n\
         registers[16] = 1 if (result & 0x80000000) else 0\n\
         registers[17] = 1 if result == 0 else 0\n\
         registers[18] = 1\n\
         registers[19] = 0",
        ops[0], ops[1]
    )
}

// LSL Rd, Rs - Logical shift left by register (format_4_alu)
pub fn generate_thumb_lsl_reg(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] << (registers[{}] & 0xFF)) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

// LSR Rd, Rs - Logical shift right by register
pub fn generate_thumb_lsr_reg(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] >> (registers[{}] & 0xFF)) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

// ASR Rd, Rs - Arithmetic shift right by register
pub fn generate_thumb_asr_reg(ops: &[String]) -> String {
    format!(
        "registers[{}] = (registers[{}] >> (registers[{}] & 0xFF)) | ((registers[{}] >> 31) * 0xFFFFFFFF << (32 - (registers[{}] & 0xFF))) & 0xFFFFFFFF",
        ops[0], ops[0], ops[1], ops[0], ops[1]
    )
}

// ROR Rd, Rs - Rotate right by register
pub fn generate_thumb_ror_reg(ops: &[String]) -> String {
    format!(
        "shift = registers[{}] & 0xFF\n\
         registers[{}] = ((registers[{}] >> shift) | (registers[{}] << (32 - shift))) & 0xFFFFFFFF",
        ops[1], ops[0], ops[0], ops[0]
    )
}

pub fn generate(inst: &gbatopy_disasm::DecodedInstruction) -> Option<String> {
    let opcode_raw = &inst.opcode.to_uppercase();
    let ops: Vec<String> = inst.operands.iter().map(|op| op.to_codegen()).collect();
    
    // Strip condition codes from opcode (e.g., "ADDMI" -> "ADD", "ADCVC" -> "ADC", "ADDmi" -> "ADD")
    let valid_conditions = ["EQ", "NE", "CS", "CC", "MI", "PL", "VS", "VC", "HI", "LS", "GE", "LT", "GT", "LE"];
    let opcode = if opcode_raw.len() > 2 {
        let maybe_cond = &opcode_raw[opcode_raw.len()-2..];
        if valid_conditions.contains(&maybe_cond) {
            opcode_raw[..opcode_raw.len()-2].to_string()
        } else {
            opcode_raw.clone()
        }
    } else {
        opcode_raw.clone()
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
        "MOV" => {
            if ops.len() == 2 {
                Some(generate_thumb_mov_imm(&ops))
            } else {
                Some(generate_thumb_mov_reg(&ops))
            }
        }
        "CMP" => {
            if ops.len() == 2 {
                Some(generate_thumb_cmp_imm(&ops))
            } else {
                Some(generate_thumb_cmp_reg(&ops))
            }
        }
        "ADD" => {
            if ops.len() == 3 {
                Some(generate_thumb_add_imm3(&ops))
            } else if ops.len() == 2 {
                // Could be ADD Rd, Rm (hi reg) or ADD Rd, #imm8
                // Check if ops[1] is a register or immediate
                if ops[1].starts_with('r') || ops[1].starts_with('R') {
                    Some(generate_thumb_add_hi(&ops))
                } else {
                    Some(generate_thumb_add_imm8(&ops))
                }
            } else {
                Some(generate_thumb_add_imm8(&ops))
            }
        }
        "SUB" => {
            if ops.len() == 3 {
                Some(generate_thumb_sub_imm3(&ops))
            } else {
                Some(generate_thumb_sub_imm8(&ops))
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
        "MVN" => Some(generate_thumb_mvn(&ops)),
        "CMN" => Some(generate_thumb_cmn(&ops)),
        "TST" => Some(generate_thumb_tst(&ops)),
        _ => None,
    }
}
