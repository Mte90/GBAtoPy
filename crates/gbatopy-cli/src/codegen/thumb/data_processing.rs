pub fn generate_thumb_and(ops: &[String]) -> String {
    // Thumb AND Rd, Rs - 2 operands only (Rd is both source and destination)
    format!("r{} = (r{} & r{}) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

pub fn generate_thumb_eor(ops: &[String]) -> String {
    // Thumb EOR Rd, Rs - 2 operands only
    format!("r{} = (r{} ^ r{}) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

pub fn generate_thumb_orr(ops: &[String]) -> String {
    // Thumb ORR Rd, Rs - 2 operands only
    format!("r{} = (r{} | r{}) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

pub fn generate_thumb_bic(ops: &[String]) -> String {
    // Thumb BIC Rd, Rs - 2 operands only
    format!("r{} = (r{} & ~r{}) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}

pub fn generate_thumb_adc(ops: &[String]) -> String {
    // Thumb ADC Rd, Rs - 2 operands only
    format!(
        "r{} = (r{} + r{} + (1 if cpsr_c else 0)) & 0xFFFFFFFF",
        ops[0], ops[0], ops[1]
    )
}

pub fn generate_thumb_sbc(ops: &[String]) -> String {
    // Thumb SBC Rd, Rs - 2 operands only
    format!(
        "r{} = (r{} - r{} - (0 if cpsr_c else 1)) & 0xFFFFFFFF",
        ops[0], ops[0], ops[1]
    )
}

pub fn generate_thumb_neg(ops: &[String]) -> String {
    format!("r{} = (0 - r{}) & 0xFFFFFFFF", ops[0], ops[1])
}

pub fn generate_thumb_mul_thumb(ops: &[String]) -> String {
    format!("r{} = (r{} * r{}) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
}
