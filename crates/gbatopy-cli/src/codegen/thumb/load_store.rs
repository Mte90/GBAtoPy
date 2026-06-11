pub fn generate_ldrh_instruction(ops: &[String]) -> String {
    // LDRH Rd, [Rn, #imm] or LDRH Rd, [Rn, Rm]
    format!("r[{}] = memory.read_u16({}) & 0xFFFF", ops[0], ops[1])
}

pub fn generate_strh_instruction(ops: &[String]) -> String {
    // STRH Rd, [Rn, #imm] or STRH Rd, [Rn, Rm]
    format!("memory.write_16({}, r[{}] & 0xFFFF)", ops[0], ops[1])
}

pub fn generate_ldrhb_instruction(ops: &[String]) -> String {
    format!("r[{}] = memory.read_u16({}) & 0xFFFF", ops[0], ops[1])
}

pub fn generate_strhb_instruction(ops: &[String]) -> String {
    format!("memory.write_16({}, r[{}] & 0xFFFF)", ops[0], ops[1])
}

pub fn generate_ldrd_instruction(ops: &[String]) -> String {
    format!("r[{}] = r[{}]", ops[0], ops[1])
}

pub fn generate_strd_instruction(ops: &[String]) -> String {
    // STRD Rd, [Rn, #imm]
    format!("memory.write_u32({}, r[{}] & 0xFFFFFFFF)", ops[0], ops[1])
}

pub fn generate_thumb_ldmia_instruction(ops: &[String]) -> String {
    // LDMIA Rn!, {reglist} - Load Multiple Increment After
    // ops[0] = register number (base)
    // ops[1] = register list string (e.g., "{r0,r1,r2}")
    let base_reg = &ops[0];
    let reg_list = &ops[1].trim_matches(|c| c == '{' || c == '}');
    let regs: Vec<&str> = reg_list.split(',').map(|s| s.trim()).collect();

    let mut code = format!("addr = r[{}]
", base_reg);
    for (i, reg) in regs.iter().enumerate() {
        let reg_num = reg.trim_start_matches('r');
        code.push_str(&format!(
            "r[{}] = memory.read_u32(addr) & 0xFFFFFFFF
",
            reg_num
        ));
        if i < regs.len() - 1 {
            code.push_str(&format!("addr += 4\n"));
        }
    }
    code.push_str(&format!("r[{}] = addr\n", base_reg)); // Writeback
    code
}

pub fn generate_thumb_stmia_instruction(ops: &[String]) -> String {
    // STMIA Rn!, {reglist} - Store Multiple Increment After
    // ops[0] = register number (base)
    // ops[1] = register list string (e.g., "{r0,r1,r2}")
    let base_reg = &ops[0];
    let reg_list = &ops[1].trim_matches(|c| c == '{' || c == '}');
    let regs: Vec<&str> = reg_list.split(',').map(|s| s.trim()).collect();

    let mut code = format!("addr = r[{}]
", base_reg);
    for (i, reg) in regs.iter().enumerate() {
        let reg_num = reg.trim_start_matches('r');
        code.push_str(&format!(
            "memory.write_u32(addr, r[{}] & 0xFFFFFFFF)
",
            reg_num
        ));
        if i < regs.len() - 1 {
            code.push_str(&format!("addr += 4\n"));
        }
    }
    code.push_str(&format!("r[{}] = addr\n", base_reg)); // Writeback
    code
}

pub fn generate_thumb_pop_instruction(ops: &[String]) -> String {
    // POP {reglist} - Load from stack (LDMIA SP!, {reglist})
    // ops[0] = register list string (e.g., "{r0,r1,r2}")
    let reg_list = &ops[0].trim_matches(|c| c == '{' || c == '}');
    let regs: Vec<&str> = reg_list.split(',').map(|s| s.trim()).collect();

    let mut code = String::new();
    code.push_str("addr = r13\n"); // SP
    for (i, reg) in regs.iter().enumerate() {
        let reg_num = reg.trim_start_matches('r');
        code.push_str(&format!(
            "r[{}] = memory.read_u32(addr) & 0xFFFFFFFF
",
            reg_num
        ));
        if i < regs.len() - 1 {
            code.push_str("addr += 4\n");
        }
    }
    code.push_str("r[13] = addr
"); // Update SP
    code
}

pub fn generate_thumb_push_instruction(ops: &[String]) -> String {
    // PUSH {reglist} - Store to stack (STMIA SP!, {reglist})
    // ops[0] = register list string (e.g., "{r0,r1,r2}")
    let reg_list = &ops[0].trim_matches(|c| c == '{' || c == '}');
    let regs: Vec<&str> = reg_list.split(',').map(|s| s.trim()).collect();

    let mut code = String::new();
    code.push_str("addr = r13\n"); // SP
    for (i, reg) in regs.iter().enumerate() {
        let reg_num = reg.trim_start_matches('r');
        code.push_str(&format!(
            "memory.write_u32(addr, r[{}] & 0xFFFFFFFF)
",
            reg_num
        ));
        if i < regs.len() - 1 {
            code.push_str("addr += 4\n");
        }
    }
    code.push_str("r[13] = addr
"); // Update SP
    code
}
