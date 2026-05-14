pub fn generate_b_instruction(_ops: &[String]) -> String {
    format!("r15 = r15 + {}", _ops[0])
}

pub fn generate_bl_instruction(_ops: &[String]) -> String {
    format!("r15 = r15 + {}; func_{}()", _ops[0], _ops[1])
}

pub fn generate_bx_instruction(ops: &[String]) -> String {
    format!("r15 = r{}", ops[0])
}

pub fn generate_cbz_instruction(_ops: &[String]) -> String {
    format!("if r{} == 0: r15 = {}", _ops[0], _ops[1])
}

pub fn generate_cbnz_instruction(_ops: &[String]) -> String {
    format!("if r{} != 0: r15 = {}", _ops[0], _ops[1])
}
