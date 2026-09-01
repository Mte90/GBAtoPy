use gbatopy_disasm::{DecodedInstruction, Operand};

fn wrap_conditional(code: String, opcode: &str) -> String {
    let full_opcode = opcode.split_whitespace().next().unwrap_or(opcode);
    let base_opcode = full_opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());
    let cond_suffix = &full_opcode[base_opcode.len()..];
    if cond_suffix.is_empty() || cond_suffix.eq_ignore_ascii_case("al") {
        return code;
    }
    let cond = cond_suffix.to_uppercase();
    let indented = code
        .lines()
        .map(|line| {
            if line.is_empty() {
                String::new()
            } else {
                format!("    {}", line)
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    format!("if cpsr_check('{}'):\n{}", cond, indented)
}

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let code = generate_inner(inst)?;
    Some(wrap_conditional(code, &inst.opcode))
}

fn generate_inner(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;
    let base_opcode = opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());
    let opcode_upper = base_opcode.to_uppercase();

    // Handle conditional variants like COPROCESSORge, COPROCESSORne, etc.
    // ARM7TDMI has no system coprocessor; coprocessor instructions indicate
    // either data-decoded-as-code (CFG bug) or an undefined instruction trap.
    if opcode_upper.starts_with("COPROCESSOR") {
        return Some("raise NotImplementedError('COPROCESSOR instruction - no coprocessor on ARM7TDMI')".to_string());
    }

    if base_opcode == "MRC" || base_opcode == "MCR" {
        return Some(format!("raise NotImplementedError('{} - no coprocessor on ARM7TDMI')", base_opcode));
    }
    if base_opcode == "LDC" || base_opcode == "STC" {
        return Some(format!("raise NotImplementedError('{} - no coprocessor on ARM7TDMI')", base_opcode));
    }
    if base_opcode == "CDP" {
        return Some("raise NotImplementedError('CDP - no coprocessor on ARM7TDMI')".to_string());
    }
    if base_opcode == "SWI" || base_opcode == "SVC" {
        // SWI/SVC: software interrupt - call the global swi_handler(swi_num)
        // GBA BIOS extracts the SWI number from bits 23:16 of the 24-bit
        // comment field (mGBA: immediate >> 16).
        let swi_num = match ops.first() {
            Some(Operand::Immediate(n)) => (*n >> 16) & 0xFF,
            _ => 0,
        };
        return Some(format!("swi_handler({:#X})\nif _cpu_halted:\n    return", swi_num));
    }
    if base_opcode == "MSR" {
        if ops.len() >= 2 {
            if let Operand::Immediate(flags) = ops[0] {
                // flags bits map to ARM CPSR fields:
                //   bit 0 (ARM bit 16) = f field → flags (N/Z/C/V) → cpsr dict
                //   bit 3 (ARM bit 19) = c field → control (mode/T bit) → not tracked by runtime
                let has_flags = (flags & 1) != 0;
                let has_control = (flags & 8) != 0;
                if !has_flags && !has_control {
                    return Some("pass  # MSR with no fields".to_string());
                }
                let source = match &ops[1] {
                    Operand::Register(rd) => format!("registers[{}]", rd),
                    Operand::Immediate(val) => format!("{:#010x}", val),
                    _ => return None,
                };
                let mut code = String::new();
                if has_control {
                    code.push_str(&format!("_new_mode = {} & 0x1F\n", source));
                    code.push_str("if _new_mode != cpsr.get('mode', 0x1F):\n");
                    code.push_str("    _switch_mode(_new_mode)\n");
                    code.push_str("    cpsr['mode'] = _new_mode\n");
                    code.push_str(&format!("cpsr['t'] = ({} >> 5) & 1\n", source));
                    code.push_str(&format!("cpsr['i'] = ({} >> 7) & 1", source));
                }
                if has_flags {
                    if has_control {
                        code.push_str("\n");
                    }
                    code.push_str(&format!("cpsr['n'] = ({} >> 31) & 1\n", source));
                    code.push_str(&format!("cpsr['z'] = ({} >> 30) & 1\n", source));
                    code.push_str(&format!("cpsr['c'] = ({} >> 29) & 1\n", source));
                    code.push_str(&format!("cpsr['v'] = ({} >> 28) & 1", source));
                }
                if code.is_empty() {
                    code.push_str("raise NotImplementedError('MSR with no effect')");
                }
                return Some(code);
            }
        }
        return Some("raise NotImplementedError('MSR unhandled operand form')".to_string());
    }
    if base_opcode == "MRS" {
        if let Some(Operand::Register(rd)) = ops.get(0) {
            return Some(format!("registers[{}] = (cpsr['n'] << 31) | (cpsr['z'] << 30) | (cpsr['c'] << 29) | (cpsr['v'] << 28)", rd));
        }
        return Some("raise NotImplementedError('MRS unhandled operand form')".to_string());
    }
    if base_opcode == "NOP" {
        return Some("pass  # NOP".to_string());
    }
    if base_opcode == "MUL" || base_opcode == "MLA" {
        if ops.len() >= 3 {
            if let Operand::Register(rd) = ops[0] {
                let rm = if let Operand::Register(r) = ops[1] {
                    format!("registers[{}]", r)
                } else { "0".to_string() };
                let rs = if let Operand::Register(r) = ops[2] {
                    format!("registers[{}]", r)
                } else { "0".to_string() };
                let acc = if base_opcode == "MLA" && ops.len() >= 4 {
                    if let Operand::Register(a) = ops[3] {
                        format!(" + registers[{}]", a)
                    } else { String::new() }
                } else { String::new() };
                return Some(format!("registers[{}] = ({} * {} {}) & 0xFFFFFFFF", rd, rm, rs, acc));
            }
        }
    }
    if base_opcode == "UMULL" || base_opcode == "SMULL" {
        if ops.len() >= 4 {
            if let Operand::Register(rlo) = ops[0] {
                if let Operand::Register(rhi) = ops[1] {
                    let rm = if let Operand::Register(r) = ops[2] {
                        format!("registers[{}]", r)
                    } else { "0".to_string() };
                    let rs = if let Operand::Register(r) = ops[3] {
                        format!("registers[{}]", r)
                    } else { "0".to_string() };
                    return Some(format!(
                        "result = {} * {}; registers[{}] = result & 0xFFFFFFFF; registers[{}] = (result >> 32) & 0xFFFFFFFF",
                        rm, rs, rlo, rhi
                    ));
                }
            }
        }
    }
    None
}
