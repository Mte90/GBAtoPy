pub fn generate_mul_instruction(ops: &[String]) -> String {
    format!("r{} = r{} * r{}", ops[0], ops[1], ops[2])
}

pub fn generate_mla_instruction(ops: &[String]) -> String {
    format!("r{} = r{} * r{} + r{}", ops[0], ops[1], ops[2], ops[3])
}
