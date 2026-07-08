use gbatopy_disasm::{DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;
    let base_opcode = opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());
    let opcode_upper = base_opcode.to_uppercase();

    // Handle conditional variants like COPROCESSORge, COPROCESSORne, etc.
    if opcode_upper.starts_with("COPROCESSOR") {
        return Some("pass  # COPROCESSOR conditional variant".to_string());
    }

    if base_opcode == "MRC" || base_opcode == "MCR" {
        return Some(format!("pass  # {} coprocessor register transfer", base_opcode));
    }
    if base_opcode == "LDC" || base_opcode == "STC" {
        return Some(format!("pass  # {} coprocessor data transfer", base_opcode));
    }
    if base_opcode == "CDP" {
        return Some("pass  # CDP coprocessor data operation".to_string());
    }
    if base_opcode == "SWI" || base_opcode == "SVC" {
        // SWI/SVC: software interrupt - increment PC and continue
        // The actual SWI handler is called by the runtime at the appropriate time
        return Some("pass  # SWI/SVC software interrupt (handled by runtime)".to_string());
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
                if has_flags {
                    code.push_str(&format!("cpsr['n'] = ({} >> 31) & 1\n", source));
                    code.push_str(&format!("cpsr['z'] = ({} >> 30) & 1\n", source));
                    code.push_str(&format!("cpsr['c'] = ({} >> 29) & 1\n", source));
                    code.push_str(&format!("cpsr['v'] = ({} >> 28) & 1", source));
                }
                if has_control && !has_flags {
                    code.push_str("pass  # MSR control field (mode/T bit) not tracked by runtime");
                }
                if code.is_empty() {
                    code.push_str("pass  # MSR no-op");
                }
                return Some(code);
            }
        }
        return Some("pass  # MSR unhandled form".to_string());
    }
    if base_opcode == "MRS" {
        if let Some(Operand::Register(rd)) = ops.get(0) {
            return Some(format!("registers[{}] = (cpsr['n'] << 31) | (cpsr['z'] << 30) | (cpsr['c'] << 29) | (cpsr['v'] << 28)", rd));
        }
        return Some("pass  # MRS unhandled form".to_string());
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
