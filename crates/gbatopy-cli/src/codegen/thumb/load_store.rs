pub fn generate_ldrh_instruction(ops: &[String]) -> String {
    // LDRH Rd, [Rn, #imm] or LDRH Rd, [Rn, Rm]
    format!("registers[{}] = memory.read_u16({}) & 0xFFFF", ops[0], ops[1])
}

pub fn generate_strh_instruction(ops: &[String]) -> String {
    // STRH Rd, [Rn, #imm] or STRH Rd, [Rn, Rm]
    // ops[0] = Rd (register number)
    // ops[1] = Rn (register number)  
    // ops[2] = offset (immediate or register)
    let rd = &ops[0];
    let rn = &ops[1];
    let offset = if ops.len() > 2 { &ops[2] } else { "0" };
    
    // Calculate effective address: registers[Rn] + offset
    format!("memory.write_u16(registers[{}] + {}, registers[{}] & 0xFFFF)", rn, offset, rd)
}

pub fn generate_ldrhb_instruction(ops: &[String]) -> String {
    format!("registers[{}] = memory.read_u16({}) & 0xFFFF", ops[0], ops[1])
}

pub fn generate_strhb_instruction(ops: &[String]) -> String {
    format!("memory.write_16({}, registers[{}] & 0xFFFF)", ops[0], ops[1])
}

pub fn generate_ldrd_instruction(ops: &[String]) -> String {
    format!("registers[{}] = registers[{}]", ops[0], ops[1])
}

pub fn generate_strd_instruction(ops: &[String]) -> String {
    // STRD Rd, [Rn, #imm]
    format!("memory.write_u32({}, registers[{}] & 0xFFFFFFFF)", ops[0], ops[1])
}

pub fn generate_thumb_ldmia_instruction(ops: &[String]) -> String {
    // LDMIA Rn!, {reglist} - Load Multiple Increment After
    // ops[0] = register number (base)
    // ops[1..] = individual register names (e.g., "r0", "r1", "r2")
    let base_reg = &ops[0];

    let mut code = format!("addr = registers[{}]
", base_reg);
    if ops.len() > 1 {
        for (i, reg) in ops[1..].iter().enumerate() {
            let reg_num = reg.trim_start_matches('r');
            code.push_str(&format!(
                "registers[{}] = memory.read_u32(addr) & 0xFFFFFFFF
",
                reg_num
            ));
            if i < ops.len() - 2 {
                code.push_str("addr += 4\n");
            }
        }
    }
    code.push_str(&format!("registers[{}] = addr\n", base_reg)); // Writeback
    code
}

pub fn generate_thumb_stmia_instruction(ops: &[String]) -> String {
    // STMIA Rn!, {reglist} - Store Multiple Increment After
    // ops[0] = register number (base)
    // ops[1..] = individual register names (e.g., "r0", "r1", "r2")
    let base_reg = &ops[0];

    let mut code = format!("addr = registers[{}]
", base_reg);
    if ops.len() > 1 {
        for (i, reg) in ops[1..].iter().enumerate() {
            let reg_num = reg.trim_start_matches('r');
            code.push_str(&format!(
                "memory.write_u32(addr, registers[{}] & 0xFFFFFFFF)
",
                reg_num
            ));
            if i < ops.len() - 2 {
                code.push_str("addr += 4\n");
            }
        }
    }
    code.push_str(&format!("registers[{}] = addr\n", base_reg)); // Writeback
    code
}

pub fn generate_thumb_pop_instruction(ops: &[String]) -> String {
    // POP {reglist} - Load from stack (LDMIA SP!, {reglist})
    // ops[0..] = individual register names (e.g., "r0", "r1", "r2")
    let mut code = String::new();
    code.push_str("addr = r13\n"); // SP
    for (i, reg) in ops.iter().enumerate() {
        let reg_num = reg.trim_start_matches('r');
        code.push_str(&format!(
            "registers[{}] = memory.read_u32(addr) & 0xFFFFFFFF
",
            reg_num
        ));
        if i < ops.len() - 1 {
            code.push_str("addr += 4\n");
        }
    }
    code.push_str("registers[13] = addr
"); // Update SP
    code
}

pub fn generate_thumb_push_instruction(ops: &[String]) -> String {
    // PUSH {reglist} - Store to stack (STMIA SP!, {reglist})
    // ops[0..] = individual register names (e.g., "r0", "r1", "r2")
    let mut code = String::new();
    code.push_str("addr = r13\n"); // SP
    for (i, reg) in ops.iter().enumerate() {
        let reg_num = reg.trim_start_matches('r');
        code.push_str(&format!(
            "memory.write_u32(addr, registers[{}] & 0xFFFFFFFF)
",
            reg_num
        ));
            if i < ops.len() - 1 {
            code.push_str("addr += 4\n");
        }
    }
    code.push_str("registers[13] = addr
"); // Update SP
    code
}

pub fn generate_ldr_instruction(ops: &[String]) -> String {
    // LDR Rd, [Rn, Rm] or LDR Rd, [Rn, #imm]
    format!("registers[{}] = memory.read_u32({}) & 0xFFFFFFFF", ops[0], ops[1])
}

pub fn generate_str_instruction(ops: &[String]) -> String {
    // STR Rd, [Rn, Rm] or STR Rd, [Rn, #imm]
    format!("memory.write_u32({}, registers[{}] & 0xFFFFFFFF)", ops[1], ops[0])
}

pub fn generate_ldr_imm_offset_instruction(ops: &[String]) -> String {
    // LDR Rd, [Rn, #imm] - immediate offset form
    format!("registers[{}] = memory.read_u32({}) & 0xFFFFFFFF", ops[0], ops[1])
}

pub fn generate_str_imm_offset_instruction(ops: &[String]) -> String {
    // STR Rd, [Rn, #imm] - immediate offset form
    format!("memory.write_u32({}, registers[{}] & 0xFFFFFFFF)", ops[1], ops[0])
}

pub fn generate_ldrb_instruction(ops: &[String]) -> String {
    // LDRB Rd, [Rn, Rm] or LDRB Rd, [Rn, #imm]
    format!("registers[{}] = memory.read_u8({}) & 0xFF", ops[0], ops[1])
}

pub fn generate_strb_instruction(ops: &[String]) -> String {
    // STRB Rd, [Rn, Rm] or STRB Rd, [Rn, #imm]
    format!("memory.write_u8({}, registers[{}] & 0xFF)", ops[1], ops[0])
}

pub fn generate_ldr_pc_instruction(ops: &[String]) -> String {
    // LDR Rd, [PC, #imm] - PC-relative load
    format!("registers[{}] = memory.read_u32({}) & 0xFFFFFFFF", ops[0], ops[1])
}

pub fn generate(inst: &gbatopy_disasm::DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode.to_uppercase();
    let ops: Vec<String> = inst.operands.iter().map(|op| op.to_codegen()).collect();
    
    match opcode.as_str() {
        "LDR" => Some(generate_ldr_instruction(&ops)),
        "STR" => Some(generate_str_instruction(&ops)),
        "LDRB" => Some(generate_ldrb_instruction(&ops)),
        "STRB" => Some(generate_strb_instruction(&ops)),
        "LDRH" => Some(generate_ldrh_instruction(&ops)),
        "STRH" => Some(generate_strh_instruction(&ops)),
        "LDRHB" => Some(generate_ldrhb_instruction(&ops)),
        "STRHB" => Some(generate_strhb_instruction(&ops)),
        "LDRD" => Some(generate_ldrd_instruction(&ops)),
        "STRD" => Some(generate_strd_instruction(&ops)),
        "LDMIA" => Some(generate_thumb_ldmia_instruction(&ops)),
        "STMIA" => Some(generate_thumb_stmia_instruction(&ops)),
        "POP" => Some(generate_thumb_pop_instruction(&ops)),
        "PUSH" => Some(generate_thumb_push_instruction(&ops)),
        _ => None,
    }
}
