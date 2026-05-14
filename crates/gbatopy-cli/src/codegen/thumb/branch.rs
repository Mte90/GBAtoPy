pub fn generate_thumb_branch_instruction(_ops: &[String]) -> String {
    format!("// branch instruction")
}

pub fn generate_thumb_blx_instruction(ops: &[String]) -> String {
    format!("// bx r{}", ops[0])
}
