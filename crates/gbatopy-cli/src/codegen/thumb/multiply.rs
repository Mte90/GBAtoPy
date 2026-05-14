pub fn generate_mul_instruction(ops: &[String]) -> String {
    format!("r{} = r{} * r{}", ops[0], ops[1], ops[2])
}

pub fn generate_mla_instruction(ops: &[String]) -> String {
    format!("r{} = r{} * r{} + r{}", ops[0], ops[1], ops[2], ops[3])
}

pub fn generate_smla_instruction(ops: &[String]) -> String {
    format!("r{} = smla r{}, r{}, r{}", ops[0], ops[1], ops[2], ops[3])
}

pub fn generate_smlbb_instruction(ops: &[String]) -> String {
    format!("r{} = smlbb r{}, r{}, r{}", ops[0], ops[1], ops[2], ops[3])
}

pub fn generate_smlabt_instruction(ops: &[String]) -> String {
    format!("r{} = smlabt r{}, r{}, r{}", ops[0], ops[1], ops[2], ops[3])
}

pub fn generate_smlatb_instruction(ops: &[String]) -> String {
    format!("r{} = smlatb r{}, r{}, r{}", ops[0], ops[1], ops[2], ops[3])
}

pub fn generate_smlbbat_instruction(ops: &[String]) -> String {
    format!(
        "r{} = smlbbat r{}, r{}, r{}",
        ops[0], ops[1], ops[2], ops[3]
    )
}
