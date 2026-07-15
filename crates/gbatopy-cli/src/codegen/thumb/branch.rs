pub fn generate_thumb_branch_instruction(ops: &[String]) -> String {
    // ops[0] should be the absolute target address
    format!("registers[15] = {}", ops[0])
}

pub fn generate_thumb_blx_instruction(ops: &[String]) -> String {
    // BLX Rm - Branch and link exchange to Thumb mode
    format!("registers[14] = (registers[15] + 4) & 0xFFFFFFFF; registers[15] = registers[{}] & 0xFFFFFFFE; arm_mode = False;", ops[0])
}

pub fn generate_thumb_bx_instruction(ops: &[String]) -> String {
    // BX Rm - Branch and exchange (Thumb/ARM mode switch)
    format!("registers[15] = registers[{}] & 0xFFFFFFFE; arm_mode = False;", ops[0])
}

pub fn generate_thumb_bl_prefix_instruction(ops: &[String]) -> String {
    // BL_PREFIX - stores upper bits of branch target in LR
    format!("registers[14] = {}", ops[0])
}

pub fn generate_thumb_bl_suffix_instruction(ops: &[String]) -> String {
    // BL_SUFFIX - combines with LR (from BL_PREFIX) to form full target and branches.
    // Must compute target from OLD LR before overwriting LR with return address.
    // Return address = current PC + 2 (Thumb: BL_SUFFIX is 2 bytes, next insn is +2).
    // LR gets Thumb bit (| 1) so BX LR returns to Thumb mode.
    format!("_bl_target = (registers[14] + {}) & 0xFFFFFFFF; registers[14] = (registers[15] + 2) | 1; registers[15] = _bl_target;", ops[0])
}

pub fn generate(inst: &gbatopy_disasm::DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode.to_uppercase();
    let ops: Vec<String> = inst.operands.iter().map(|op| op.to_codegen()).collect();
    
    match opcode.as_str() {
        "B" => Some(generate_thumb_branch_instruction(&ops)),
        "BLX" => Some(generate_thumb_blx_instruction(&ops)),
        "BX" => Some(generate_thumb_bx_instruction(&ops)),
        "BL_PREFIX" => Some(generate_thumb_bl_prefix_instruction(&ops)),
        "BL_SUFFIX" => Some(generate_thumb_bl_suffix_instruction(&ops)),
        _ => None,
    }
}
