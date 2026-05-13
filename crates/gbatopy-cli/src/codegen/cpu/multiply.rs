pub fn generate_mul_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{}, r14 = r{} * r{}", ops[0], ops[1], ops[2])
}

pub fn generate_mla_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!(
        "r{}, r14 = r{} + (r{} * r{})",
        ops[0], ops[1], ops[2], ops[3]
    )
}
