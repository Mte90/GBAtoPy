pub fn generate_ldm_instruction(ops: &[String]) -> String {
    let base_reg = ops.get(0).map(|s| s.as_str()).unwrap_or("r0");
    let reg_list = ops.get(1).map(|s| s.as_str()).unwrap_or("");

    let regs: Vec<&str> = reg_list
        .trim_matches(|c| c == '{' || c == '}')
        .split(',')
        .filter(|s| !s.trim().is_empty())
        .map(|s| s.trim())
        .collect();

    if regs.is_empty() {
        return "pass".to_string();
    }

    let mut code = format!("addr = {}\n", base_reg);
    for reg in &regs {
        code.push_str(&format!("{} = memory.read_32(addr)\n", reg));
        code.push_str("addr += 4\n");
    }
    code.push_str(&format!("{} = addr\n", base_reg));
    code
}

pub fn generate_stm_instruction(ops: &[String]) -> String {
    let base_reg = ops.get(0).map(|s| s.as_str()).unwrap_or("r0");
    let reg_list = ops.get(1).map(|s| s.as_str()).unwrap_or("");

    let regs: Vec<&str> = reg_list
        .trim_matches(|c| c == '{' || c == '}')
        .split(',')
        .filter(|s| !s.trim().is_empty())
        .map(|s| s.trim())
        .collect();

    if regs.is_empty() {
        return "pass".to_string();
    }

    let mut code = format!("addr = {}\n", base_reg);
    for reg in &regs {
        code.push_str(&format!("memory.write_32(addr, {})\n", reg));
        code.push_str("addr += 4\n");
    }
    code.push_str(&format!("{} = addr\n", base_reg));
    code
}

pub fn generate_prefetch_instruction(_ops: &[String]) -> String {
    "pass".to_string()
}