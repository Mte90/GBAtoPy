pub fn generate_b_instruction(ops: &[String]) -> String {
    // ops[0] should be the absolute target address (e.g., "0x08000100")
    format!("r[15] = {}", ops[0])
}

pub fn generate_bl_instruction(ops: &[String]) -> String {
    // ops[0] should be the absolute target address, ops[1] should be function name
    format!("r[15] = {}; func_{}()", ops[0], ops[1])
}

pub fn generate_bx_instruction(ops: &[String]) -> String {
    format!("r[15] = r[{}]", ops[0])
}

pub fn generate_cbz_instruction(_ops: &[String]) -> String {
    format!("if r[{}] == 0: r[15] = {}", _ops[0], _ops[1])
}

pub fn generate_cbnz_instruction(_ops: &[String]) -> String {
    format!("if r[{}] != 0: r[15] = {}", _ops[0], _ops[1])
}
