pub fn generate_thumb_branch_instruction(ops: &[String]) -> String {
    // ops[0] should be the absolute target address
    format!("registers[15] = {}", ops[0])
}

pub fn generate_thumb_blx_instruction(ops: &[String]) -> String {
    // BX Rm - Branch and exchange to Thumb mode
    format!("registers[15] = registers[{}] & 0xFFFFFFFE; arm_mode = False;", ops[0])
}
