use gbatopy_disasm::Operand;

/// Compute the effective address expression for a Thumb load/store with 3 operands.
/// ops[0] = Rd, ops[1] = Rb (base), ops[2] = offset (Register or Immediate)
fn addr_expr_3op(ops: &[Operand]) -> Option<String> {
    let (_, Operand::Register(rb), offset_op) = (&ops[0], &ops[1], &ops[2]) else {
        return None;
    };
    let offset_expr = match offset_op {
        Operand::Register(r) => format!("registers[{}]", r),
        Operand::Immediate(v) => v.to_string(),
        _ => "0".to_string(),
    };
    Some(format!("registers[{}] + {}", rb, offset_expr))
}

pub fn generate_ldrh_instruction(ops: &[String]) -> String {
    // LDRH Rd, [Rn, #imm] or LDRH Rd, [Rn, Rm]
    format!("registers[{}] = memory.read_u16({}) & 0xFFFF", ops[0], ops[1])
}

pub fn generate_strh_instruction(ops: &[String]) -> String {
    // STRH Rd, [Rn, #imm] or STRH Rd, [Rn, Rm]
    let rd = &ops[0];
    let rn = &ops[1];
    let offset = if ops.len() > 2 { &ops[2] } else { "0" };
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
    format!("memory.write_u32({}, registers[{}] & 0xFFFFFFFF)", ops[0], ops[1])
}

pub fn generate_thumb_ldmia_instruction(ops: &[String]) -> String {
    let base_reg = &ops[0];
    let mut code = format!("addr = registers[{}]\n", base_reg);
    if ops.len() > 1 {
        for reg in ops[1..].iter() {
            let reg_num = reg.trim_start_matches('r');
            code.push_str(&format!(
                "registers[{}] = memory.read_u32(addr) & 0xFFFFFFFF\naddr += 4\n",
                reg_num
            ));
        }
    }
    code.push_str(&format!("registers[{}] = addr\n", base_reg));
    code
}

pub fn generate_thumb_stmia_instruction(ops: &[String]) -> String {
    let base_reg = &ops[0];
    let mut code = format!("addr = registers[{}]\n", base_reg);
    if ops.len() > 1 {
        for reg in ops[1..].iter() {
            let reg_num = reg.trim_start_matches('r');
            code.push_str(&format!(
                "memory.write_u32(addr, registers[{}] & 0xFFFFFFFF)\naddr += 4\n",
                reg_num
            ));
        }
    }
    code.push_str(&format!("registers[{}] = addr\n", base_reg));
    code
}

pub fn generate_thumb_pop_instruction(ops: &[String]) -> String {
    let mut code = String::new();
    code.push_str("addr = registers[13]\n");
    for reg in ops.iter() {
        let reg_num = reg.trim_start_matches('r');
        code.push_str(&format!(
            "registers[{}] = memory.read_u32(addr) & 0xFFFFFFFF\naddr += 4\n",
            reg_num
        ));
    }
    code.push_str("registers[13] = addr\n");
    code
}

pub fn generate_thumb_push_instruction(ops: &[String]) -> String {
    let count = ops.len();
    let mut code = format!("addr = registers[13] - {}\n", count * 4);
    for reg in ops.iter() {
        let reg_num = reg.trim_start_matches('r');
        code.push_str(&format!(
            "memory.write_u32(addr, registers[{}] & 0xFFFFFFFF)\naddr += 4\n",
            reg_num
        ));
    }
    code.push_str(&format!("registers[13] = registers[13] - {}\n", count * 4));
    code
}

pub fn generate(inst: &gbatopy_disasm::DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.to_uppercase();
    let ops = &inst.operands;

    match opcode.as_str() {
        "STR" => {
            if ops.len() >= 3 {
                let addr = addr_expr_3op(ops)?;
                let Operand::Register(rd) = &ops[0] else { return None };
                Some(format!("memory.write_u32({}, registers[{}] & 0xFFFFFFFF)", addr, rd))
            } else {
                let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
                Some(generate_str_instruction(&ops_s))
            }
        }
        "LDR" => {
            if ops.len() >= 3 {
                let addr = addr_expr_3op(ops)?;
                let Operand::Register(rd) = &ops[0] else { return None };
                Some(format!("registers[{}] = memory.read_u32({}) & 0xFFFFFFFF", rd, addr))
            } else {
                let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
                Some(generate_ldr_instruction(&ops_s))
            }
        }
        "STRB" => {
            if ops.len() >= 3 {
                let addr = addr_expr_3op(ops)?;
                let Operand::Register(rd) = &ops[0] else { return None };
                Some(format!("memory.write_u8({}, registers[{}] & 0xFF)", addr, rd))
            } else {
                let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
                Some(generate_strb_instruction(&ops_s))
            }
        }
        "LDRB" => {
            if ops.len() >= 3 {
                let addr = addr_expr_3op(ops)?;
                let Operand::Register(rd) = &ops[0] else { return None };
                Some(format!("registers[{}] = memory.read_u8({}) & 0xFF", rd, addr))
            } else {
                let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
                Some(generate_ldrb_instruction(&ops_s))
            }
        }
        "LDRH" => {
            if ops.len() >= 3 {
                let addr = addr_expr_3op(ops)?;
                let Operand::Register(rd) = &ops[0] else { return None };
                Some(format!("registers[{}] = memory.read_u16({}) & 0xFFFF", rd, addr))
            } else {
                let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
                Some(generate_ldrh_instruction(&ops_s))
            }
        }
        "STRH" => {
            let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
            Some(generate_strh_instruction(&ops_s))
        }
        "LDRSB" => {
            if ops.len() >= 3 {
                let addr = addr_expr_3op(ops)?;
                let Operand::Register(rd) = &ops[0] else { return None };
                Some(format!("temp = memory.read_u8({}); registers[{}] = (temp << 24) >> 24", addr, rd))
            } else {
                None
            }
        }
        "LDRSH" => {
            if ops.len() >= 3 {
                let addr = addr_expr_3op(ops)?;
                let Operand::Register(rd) = &ops[0] else { return None };
                Some(format!("temp = memory.read_u16({}); registers[{}] = (temp << 16) >> 16", addr, rd))
            } else {
                None
            }
        }
        "LDRHB" => {
            let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
            Some(generate_ldrhb_instruction(&ops_s))
        }
        "STRHB" => {
            let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
            Some(generate_strhb_instruction(&ops_s))
        }
        "LDRD" => {
            let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
            Some(generate_ldrd_instruction(&ops_s))
        }
        "STRD" => {
            let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
            Some(generate_strd_instruction(&ops_s))
        }
        "LDMIA" => {
            let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
            Some(generate_thumb_ldmia_instruction(&ops_s))
        }
        "STMIA" => {
            let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
            Some(generate_thumb_stmia_instruction(&ops_s))
        }
        "POP" => {
            let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
            Some(generate_thumb_pop_instruction(&ops_s))
        }
        "PUSH" => {
            let ops_s: Vec<String> = ops.iter().map(|op| op.to_codegen()).collect();
            Some(generate_thumb_push_instruction(&ops_s))
        }
        _ => None,
    }
}

// Legacy functions retained for callers that pass string operands.
fn generate_ldr_instruction(ops: &[String]) -> String {
    format!("registers[{}] = memory.read_u32({}) & 0xFFFFFFFF", ops[0], ops[1])
}

fn generate_str_instruction(ops: &[String]) -> String {
    format!("memory.write_u32({}, registers[{}] & 0xFFFFFFFF)", ops[1], ops[0])
}

fn generate_ldrb_instruction(ops: &[String]) -> String {
    format!("registers[{}] = memory.read_u8({}) & 0xFF", ops[0], ops[1])
}

fn generate_strb_instruction(ops: &[String]) -> String {
    format!("memory.write_u8({}, registers[{}] & 0xFF)", ops[1], ops[0])
}
