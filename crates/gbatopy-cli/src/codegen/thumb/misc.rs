pub fn generate_thumb_movw_instruction(ops: &[String]) -> String {
    format!("r[{}] = {}", ops[0], ops[1])
}

pub fn generate_thumb_movt_instruction(ops: &[String]) -> String {
    format!("r[{}] = (r[{}] & 0xFFFF) | ({} << 16)", ops[0], ops[0], ops[1])
}
