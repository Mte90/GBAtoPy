pub fn generate_mul_instruction(ops: &[String]) -> String {
    format!("registers[{}] = registers[{}] * registers[{}]", ops[0], ops[1], ops[2])
}

pub fn generate_mla_instruction(ops: &[String]) -> String {
    format!("registers[{}] = registers[{}] * registers[{}] + registers[{}]", ops[0], ops[1], ops[2], ops[3])
}
