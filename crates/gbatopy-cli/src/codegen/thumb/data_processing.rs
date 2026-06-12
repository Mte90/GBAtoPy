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
