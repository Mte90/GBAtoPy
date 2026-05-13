pub fn generate_b_instruction_thumb(ops: &[arg], _cfg: &arg) -> String {
    let target = 0x08000000; // placeholder
    format!("r15 = r15 + ({target - 4})")
}

pub fn generate_bx_instruction_thumb(ops: &[arg], _cfg: &arg) -> String {
    format!("r15 = r{}", ops[0])
}
