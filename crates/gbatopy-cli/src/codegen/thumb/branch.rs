pub fn generate_thumb_branch_instruction(ops: &[String]) -> String {
    // ops[0] should be the absolute target address
    format!("registers[15] = {}", ops[0])
}

pub fn generate_thumb_blx_instruction(ops: &[String]) -> String {
    // BLX Rm - Branch and link exchange. Bit 0 of Rm selects Thumb/ARM mode.
    // When Rm is R15 (PC), the Thumb pipeline makes PC read as current + 4.
    if ops[0] == "15" {
        format!("_bx_pc = (registers[15] + 4) & 0xFFFFFFFF; registers[14] = ((registers[15] + 4) & 0xFFFFFFFF) | 1; cpsr['t'] = _bx_pc & 1; registers[15] = _bx_pc & 0xFFFFFFFE")
    } else if ops[0].starts_with("0x") || ops[0].parse::<u32>().map(|v| v > 0x08000000).unwrap_or(false) {
        // BLX immediate - target is an absolute address (either hex like 0x0800xxxx or decimal > 0x08000000)
        // Set LR to return address (PC + 4), set mode to Thumb (bit 0 = 1), branch to target
        let target = if ops[0].starts_with("0x") {
            ops[0].clone()
        } else {
            format!("0x{:08X}", ops[0].parse::<u32>().unwrap_or(0))
        };
        format!("registers[14] = ((registers[15] + 4) & 0xFFFFFFFF) | 1; cpsr['t'] = 1; registers[15] = {}", target)
    } else {
        // BLX Rm - register form
        format!("registers[14] = ((registers[15] + 4) & 0xFFFFFFFF) | 1; cpsr['t'] = registers[{}] & 1; registers[15] = registers[{}] & 0xFFFFFFFE", ops[0], ops[0])
    }
}

pub fn generate_thumb_bx_instruction(ops: &[String]) -> String {
    // BX Rm - Branch and exchange. Bit 0 of Rm selects Thumb/ARM mode.
    // When Rm is R15 (PC), the Thumb pipeline makes PC read as current + 4.
    if ops[0] == "15" {
        format!("_bx_pc = (registers[15] + 4) & 0xFFFFFFFF; cpsr['t'] = _bx_pc & 1; registers[15] = _bx_pc & 0xFFFFFFFE")
    } else {
        format!("cpsr['t'] = registers[{}] & 1; registers[15] = registers[{}] & 0xFFFFFFFE", ops[0], ops[0])
    }
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

pub fn generate_thumb_bl_instruction(ops: &[String]) -> String {
    // BL - Branch and Link. 32-bit Thumb instruction.
    // Target is already computed as absolute address during decode.
    // LR = return address (PC + 4, with Thumb bit set)
    // PC = target address
    format!("registers[14] = (registers[15] + 4) | 1; registers[15] = {}", ops[0])
}

pub fn generate(inst: &gbatopy_disasm::DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode.to_uppercase();
    let ops: Vec<String> = inst.operands.iter().map(|op| op.to_codegen()).collect();
    
    match opcode.as_str() {
        "B" => Some(generate_thumb_branch_instruction(&ops)),
        "BLX" => Some(generate_thumb_blx_instruction(&ops)),
        "BX" => Some(generate_thumb_bx_instruction(&ops)),
        "BL" => Some(generate_thumb_bl_instruction(&ops)),
        "BL_PREFIX" => Some(generate_thumb_bl_prefix_instruction(&ops)),
        "BL_SUFFIX" => Some(generate_thumb_bl_suffix_instruction(&ops)),
        _ => None,
    }
}
