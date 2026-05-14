pub fn generate_ldm_instruction(ops: &[String]) -> String {
    format!("LDM {}, {}", ops[0], ops[1])
}

pub fn generate_stm_instruction(ops: &[String]) -> String {
    format!("STM {}, {}", ops[0], ops[1])
}

pub fn generate_prefetch_instruction(ops: &[String]) -> String {
    format!("PREFETCH {}", ops[0])
}
