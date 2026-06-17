pub fn generate_mul_instruction(ops: &[String]) -> String {
    // Thumb MUL has 2 operands: Rd, Rm (Rd = Rd * Rm)
    format!("registers[{}] = (registers[{}] * registers[{}]) & 0xFFFFFFFF", ops[0], ops[0], ops[1])
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

pub fn generate(inst: &gbatopy_disasm::DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode.to_uppercase();
    let ops: Vec<String> = inst.operands.iter().map(|op| op.to_codegen()).collect();
    
    match opcode.as_str() {
        "MUL" => Some(generate_mul_instruction(&ops)),
        "MLA" => Some(generate_mla_instruction(&ops)),
        "SMLA" => Some(generate_smla_instruction(&ops)),
        "SMLBB" => Some(generate_smlbb_instruction(&ops)),
        "SMLABT" => Some(generate_smlabt_instruction(&ops)),
        "SMLATB" => Some(generate_smlatb_instruction(&ops)),
        "SMLBBAT" => Some(generate_smlbbat_instruction(&ops)),
        _ => None,
    }
}
