pub fn generate_b_instruction(_ops: &[arg], _cfg: &arg) -> String {
    format!("r15 = r15 + OFFSET")
}

pub fn generate_bl_instruction(_ops: &[arg], _cfg: &arg) -> String {
    format!("r15 = r15 + OFFSET; func_{}_()", target)
}

pub fn generate_bx_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r15 = r{}", ops[0])
}

pub fn generate_cbz_instruction(_ops: &[arg], _cfg: &arg) -> String {
    format!("if r{} == 0: r15 = r15 + OFFSET")
}

pub fn generate_cbnz_instruction(_ops: &[arg], _cfg: &arg) -> String {
    format!("if r{} != 0: r15 = r15 + OFFSET")
}
