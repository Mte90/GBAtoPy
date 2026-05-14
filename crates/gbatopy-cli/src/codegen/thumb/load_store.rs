pub fn generate_ldrh_instruction(ops: &[String]) -> String {
    format!("r{} = read_word({})", ops[0], ops[1])
}

pub fn generate_strh_instruction(ops: &[String]) -> String {
    format!("write_word({}, {})", ops[0], ops[1])
}

pub fn generate_ldrhb_instruction(ops: &[String]) -> String {
    format!("r{} = read_hword({})", ops[0], ops[1])
}

pub fn generate_strhb_instruction(ops: &[String]) -> String {
    format!("write_hword({}, {})", ops[0], ops[1])
}

pub fn generate_ldrd_instruction(ops: &[String]) -> String {
    format!("r{} = r{}", ops[0], ops[1])
}

pub fn generate_strd_instruction(ops: &[String]) -> String {
    format!("write_dword({}, {})", ops[0], ops[1])
}
