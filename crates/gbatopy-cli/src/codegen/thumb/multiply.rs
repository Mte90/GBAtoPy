pub fn generate_mul_instruction(ops: &[String]) -> String {
    format!("registers[{}] = registers[{}] * registers[{}]", ops[0], ops[1], ops[2])
}

pub fn generate_mla_instruction(ops: &[String]) -> String {
    format!("registers[{}] = registers[{}] * registers[{}] + registers[{}]", ops[0], ops[1], ops[2], ops[3])
}

pub fn generate_smla_instruction(ops: &[String]) -> String {
    // SMLA: Rd = Rd + (Rn * Rm) - signed multiply-accumulate
    format!("registers[{}] = (registers[{}] + registers[{}] * registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1], ops[2])
}

pub fn generate_smlbb_instruction(ops: &[String]) -> String {
    // SMLBB: Signed Multiply Long Bottom x Bottom
    // RdHi:RdLo = RdLo + (Rn(bottom) * Rm(bottom))
    format!("registers[{}] = (registers[{}] + registers[{}] * registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1], ops[2])
}

pub fn generate_smlabt_instruction(ops: &[String]) -> String {
    // SMLABT: Signed Multiply Long Alternate Bottom x Top
    format!("registers[{}] = (registers[{}] + registers[{}] * registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1], ops[2])
}

pub fn generate_smlatb_instruction(ops: &[String]) -> String {
    // SMLATB: Signed Multiply Long Alternate Top x Bottom
    format!("registers[{}] = (registers[{}] + registers[{}] * registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1], ops[2])
}

pub fn generate_smlbbat_instruction(ops: &[String]) -> String {
    // SMLBBAT: Signed Multiply Long Bottom x Bottom x Top
    format!("registers[{}] = (registers[{}] + registers[{}] * registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1], ops[2])
}
