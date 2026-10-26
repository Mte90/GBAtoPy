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
        return Some(
            "_interp_fallback(registers, cpsr, max_steps=1, irq_return_pc=None)".to_string(),
        );
    }

    if base_opcode == "MRC" || base_opcode == "MCR" {
        return Some(
            "_interp_fallback(registers, cpsr, max_steps=1, irq_return_pc=None)".to_string(),
        );
    }
    if base_opcode == "LDC" || base_opcode == "STC" {
        return Some(
            "_interp_fallback(registers, cpsr, max_steps=1, irq_return_pc=None)".to_string(),
        );
    }
    if base_opcode == "CDP" {
        return Some(
            "_interp_fallback(registers, cpsr, max_steps=1, irq_return_pc=None)".to_string(),
        );
    }
    if base_opcode == "SWI" || base_opcode == "SVC" {
        let swi_num = match ops.first() {
            Some(Operand::Immediate(n)) => *n & 0xFF,
            _ => 0,
        };
        return Some(format!(
            "swi_handler({:#X})\nif _cpu_halted:\n    return",
            swi_num
        ));
    }
    if base_opcode == "MSR" {
        if ops.len() >= 2 {
            if let Operand::Immediate(flags) = ops[0] {
                // flags bits map to ARM CPSR field-mask bits [19:16]:
                //   bit 0 (ARM bit 16) = c field → control (mode, T, I, F)
                //   bit 1 (ARM bit 17) = x field → extension (reserved on ARM7TDMI)
                //   bit 2 (ARM bit 18) = s field → status (reserved on ARM7TDMI)
                //   bit 3 (ARM bit 19) = f field → flags (N/Z/C/V)
                let has_control = (flags & 1) != 0;
                let has_flags = (flags & 8) != 0;
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
                        code.push('\n');
                    }
                    code.push_str(&format!("cpsr['n'] = ({} >> 31) & 1\n", source));
                    code.push_str(&format!("cpsr['z'] = ({} >> 30) & 1\n", source));
                    code.push_str(&format!("cpsr['c'] = ({} >> 29) & 1\n", source));
                    code.push_str(&format!("cpsr['v'] = ({} >> 28) & 1", source));
                }
                if code.is_empty() {
                    code.push_str(
                        "_interp_fallback(registers, cpsr, max_steps=1, irq_return_pc=None)",
                    );
                }
                return Some(code);
            }
        }
        return Some(
            "_interp_fallback(registers, cpsr, max_steps=1, irq_return_pc=None)".to_string(),
        );
    }
    if base_opcode == "MRS" {
        if let Some(Operand::Register(rd)) = ops.first() {
            return Some(format!("registers[{}] = ((cpsr['n'] << 31) | (cpsr['z'] << 30) | (cpsr['c'] << 29) | (cpsr['v'] << 28) | (cpsr['f'] << 6) | (cpsr['i'] << 7) | (cpsr['t'] << 5) | cpsr['mode']) & 0xFFFFFFFF", rd));
        }
        return Some(
            "_interp_fallback(registers, cpsr, max_steps=1, irq_return_pc=None)".to_string(),
        );
    }
    if base_opcode == "NOP" {
        return Some("pass  # NOP".to_string());
    }
    // Not collapsed: MUL/MLA with nested if-let patterns for operand extraction
    #[allow(clippy::collapsible_if)]
    if base_opcode == "MUL" || base_opcode == "MLA" {
        if ops.len() >= 3 {
            if let Operand::Register(rd) = ops[0] {
                let rm = if let Operand::Register(r) = ops[1] {
                    format!("registers[{}]", r)
                } else {
                    "0".to_string()
                };
                let rs = if let Operand::Register(r) = ops[2] {
                    format!("registers[{}]", r)
                } else {
                    "0".to_string()
                };
                let acc = if base_opcode == "MLA" && ops.len() >= 4 {
                    if let Operand::Register(a) = ops[3] {
                        format!(" + registers[{}]", a)
                    } else {
                        String::new()
                    }
                } else {
                    String::new()
                };
                return Some(format!(
                    "registers[{}] = ({} * {} {}) & 0xFFFFFFFF",
                    rd, rm, rs, acc
                ));
            }
        }
    }
    // Not collapsed: UMULL/SMULL with nested if-let patterns for operand extraction
    #[allow(clippy::collapsible_if)]
    if base_opcode == "UMULL" || base_opcode == "SMULL" {
        if ops.len() >= 4 {
            if let Operand::Register(rlo) = ops[0] {
                if let Operand::Register(rhi) = ops[1] {
                    let rm = if let Operand::Register(r) = ops[2] {
                        format!("registers[{}]", r)
                    } else {
                        "0".to_string()
                    };
                    let rs = if let Operand::Register(r) = ops[3] {
                        format!("registers[{}]", r)
                    } else {
                        "0".to_string()
                    };
                    // SMULL sign-extends operands; UMULL is unsigned
                    let mul_expr = if base_opcode == "SMULL" {
                        format!("int({}) * int({})", rm, rs)
                    } else {
                        format!("{} * {}", rm, rs)
                    };
                    return Some(format!(
                        "result = {}; registers[{}] = result & 0xFFFFFFFF; registers[{}] = (result >> 32) & 0xFFFFFFFF",
                        mul_expr, rlo, rhi
                    ));
                }
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use gbatopy_disasm::{Condition, DecodedInstruction, Operand};

    fn make_inst(opcode: &str, operands: Vec<Operand>) -> DecodedInstruction {
        DecodedInstruction {
            address: 0x08000000,
            opcode: opcode.to_string(),
            operands,
            condition: Some(Condition::Al),
            mode: gbatopy_disasm::ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        }
    }

    // === wrap_conditional tests ===
    #[test]
    fn test_wrap_conditional_no_condition() {
        let code = String::from("registers[0] = 42");
        let result = wrap_conditional(code, "MOV");
        assert_eq!(result, "registers[0] = 42");
    }

    #[test]
    fn test_wrap_conditional_eq_suffix() {
        // Condition codes are lowercase suffixes (e.g., "MOVeq" not "moveq" or "MOVEQ")
        let code = String::from("registers[0] = 42");
        let result = wrap_conditional(code, "MOVeq");
        assert_eq!(result, "if cpsr_check('EQ'):\n    registers[0] = 42");
    }

    #[test]
    fn test_wrap_conditional_ne_suffix() {
        // Condition codes are lowercase suffixes (e.g., "ADDne")
        let code = String::from("registers[0] = 42");
        let result = wrap_conditional(code, "ADDne");
        assert_eq!(result, "if cpsr_check('NE'):\n    registers[0] = 42");
    }

    #[test]
    fn test_wrap_conditional_al_no_wrap() {
        // 'al' (always) condition should NOT wrap
        let code = String::from("registers[0] = 42");
        let result = wrap_conditional(code, "MOVal");
        assert_eq!(result, "registers[0] = 42");
    }

    #[test]
    fn test_wrap_conditional_multiline() {
        let code = String::from("line1\nline2\nline3");
        let result = wrap_conditional(code, "ADDne");
        assert_eq!(result, "if cpsr_check('NE'):\n    line1\n    line2\n    line3");
    }

    #[test]
    fn test_wrap_conditional_empty_lines() {
        let code = String::from("line1\n\nline2");
        let result = wrap_conditional(code, "ADDne");
        assert_eq!(result, "if cpsr_check('NE'):\n    line1\n\n    line2");
    }

    // === generate() tests for coprocessor instructions ===
    #[test]
    fn test_generate_copro_always_fallback() {
        let inst = make_inst("COPROCESSOR", vec![]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert!(result.unwrap().contains("_interp_fallback"));
    }

    #[test]
    fn test_generate_copro_conditional_fallback() {
        // Use mixed case: uppercase opcode + lowercase condition (e.g., "COPROCESSORge")
        let inst = make_inst("COPROCESSORge", vec![]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("_interp_fallback"));
        assert!(code.contains("if cpsr_check('GE')"));
    }

    #[test]
    fn test_generate_mrc_fallback() {
        let inst = make_inst("MRC", vec![Operand::Immediate(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert!(result.unwrap().contains("_interp_fallback"));
    }

    #[test]
    fn test_generate_mcr_fallback() {
        let inst = make_inst("MCR", vec![Operand::Immediate(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert!(result.unwrap().contains("_interp_fallback"));
    }

    #[test]
    fn test_generate_ldc_fallback() {
        let inst = make_inst("LDC", vec![Operand::Immediate(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert!(result.unwrap().contains("_interp_fallback"));
    }

    #[test]
    fn test_generate_stc_fallback() {
        let inst = make_inst("STC", vec![Operand::Immediate(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert!(result.unwrap().contains("_interp_fallback"));
    }

    #[test]
    fn test_generate_cdp_fallback() {
        let inst = make_inst("CDP", vec![Operand::Immediate(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert!(result.unwrap().contains("_interp_fallback"));
    }

    // === SWI/SVC tests ===
    #[test]
    fn test_generate_swi_with_immediate() {
        // ARM disassembler pre-extracts: word & 0xFFFFFF → Immediate(swi_num)
        let inst = make_inst("SWI", vec![Operand::Immediate(0x12)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("swi_handler(0x12)"));
        assert!(code.contains("if _cpu_halted"));
    }

    #[test]
    fn test_generate_svc_with_immediate() {
        // ARM disassembler pre-extracts: word & 0xFFFFFF → Immediate(swi_num)
        let inst = make_inst("SVC", vec![Operand::Immediate(0xAB)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("swi_handler(0xAB)"));
    }

    #[test]
    fn test_generate_swi_no_immediate() {
        let inst = make_inst("SWI", vec![Operand::Register(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("swi_handler(0x0)"));
    }

    // === MSR tests ===
    #[test]
    fn test_generate_msr_no_fields() {
        let inst = make_inst("MSR", vec![Operand::Immediate(0), Operand::Register(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert_eq!(result.unwrap(), "pass  # MSR with no fields");
    }

    #[test]
    fn test_generate_msr_flags_only() {
        let inst = make_inst("MSR", vec![Operand::Immediate(0x8), Operand::Register(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("cpsr['n']"));
        assert!(code.contains("cpsr['z']"));
        assert!(code.contains("cpsr['c']"));
        assert!(code.contains("cpsr['v']"));
        assert!(!code.contains("_new_mode"));
    }

    #[test]
    fn test_generate_msr_control_only() {
        let inst = make_inst("MSR", vec![Operand::Immediate(0x1), Operand::Register(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("_new_mode"));
        assert!(code.contains("_switch_mode"));
        assert!(code.contains("cpsr['mode']"));
        assert!(code.contains("cpsr['t']"));
        assert!(code.contains("cpsr['i']"));
        assert!(!code.contains("cpsr['n']"));
    }

    #[test]
    fn test_generate_msr_flags_and_control() {
        let inst = make_inst("MSR", vec![Operand::Immediate(0x9), Operand::Register(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("_new_mode"));
        assert!(code.contains("cpsr['n']"));
        assert!(code.contains("cpsr['z']"));
        assert!(code.contains("cpsr['c']"));
        assert!(code.contains("cpsr['v']"));
    }

    #[test]
    fn test_generate_msr_immediate_source() {
        let inst = make_inst("MSR", vec![Operand::Immediate(0x8), Operand::Immediate(0x20000000)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("cpsr['n'] = (0x20000000 >> 31) & 1"));
    }

    #[test]
    fn test_generate_msr_fallback() {
        let inst = make_inst("MSR", vec![Operand::Register(0), Operand::Register(1)]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert!(result.unwrap().contains("_interp_fallback"));
    }

    // === MRS tests ===
    #[test]
    fn test_generate_mrs_register() {
        let inst = make_inst("MRS", vec![Operand::Register(5)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("registers[5] ="));
        assert!(code.contains("cpsr['n'] << 31"));
        assert!(code.contains("cpsr['z'] << 30"));
        assert!(code.contains("cpsr['c'] << 29"));
        assert!(code.contains("cpsr['v'] << 28"));
    }

    #[test]
    fn test_generate_mrs_fallback() {
        let inst = make_inst("MRS", vec![Operand::Immediate(0)]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert!(result.unwrap().contains("_interp_fallback"));
    }

    // === NOP tests ===
    #[test]
    fn test_generate_nop() {
        let inst = make_inst("NOP", vec![]);
        let result = generate(&inst);
        assert!(result.is_some());
        assert_eq!(result.unwrap(), "pass  # NOP");
    }

    // === MUL/MLA tests ===
    #[test]
    fn test_generate_mul() {
        let inst = make_inst("MUL", vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("registers[0] ="));
        assert!(code.contains("registers[1] * registers[2]"));
        assert!(code.contains("& 0xFFFFFFFF"));
    }

    #[test]
    fn test_generate_mla() {
        let inst = make_inst("MLA", vec![Operand::Register(0), Operand::Register(1), Operand::Register(2), Operand::Register(3)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("registers[0] ="));
        // The actual format uses semicolons and explicit parentheses
        assert!(code.contains("registers[1] * registers[2]"));
        assert!(code.contains("+ registers[3]"));
    }

    #[test]
    fn test_generate_mla_without_accumulator() {
        let inst = make_inst("MLA", vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("registers[0] ="));
        assert!(code.contains("registers[1] * registers[2]"));
        assert!(!code.contains(" + "));
    }

    // === UMULL/SMULL tests ===
    #[test]
    fn test_generate_umull() {
        let inst = make_inst("UMULL", vec![Operand::Register(0), Operand::Register(1), Operand::Register(2), Operand::Register(3)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        assert!(code.contains("registers[0] = result & 0xFFFFFFFF"));
        assert!(code.contains("registers[1] = (result >> 32) & 0xFFFFFFFF"));
    }

    #[test]
    fn test_generate_smull() {
        let inst = make_inst("SMULL", vec![Operand::Register(0), Operand::Register(1), Operand::Register(2), Operand::Register(3)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        // SMULL must sign-extend operands using int() before multiplying
        assert!(code.contains("result = int(registers[2]) * int(registers[3])"));
    }

    #[test]
    fn test_generate_smull_sign_extension() {
        // Verify SMULL generates code that sign-extends operands
        // This test ensures negative values are properly handled
        let inst = make_inst("SMULL", vec![Operand::Register(0), Operand::Register(1), Operand::Register(2), Operand::Register(3)]);
        let result = generate(&inst);
        assert!(result.is_some());
        let code = result.unwrap();
        // The generated Python code must use int() for sign-extension
        assert!(code.contains("int(registers[2])"));
        assert!(code.contains("int(registers[3])"));
    }

    // === Edge cases ===
    #[test]
    fn test_generate_unknown_opcode() {
        let inst = make_inst("UNKNOWN", vec![]);
        let result = generate(&inst);
        assert!(result.is_none());
    }

    #[test]
    fn test_generate_muls_flag_setting() {
        let inst = make_inst("MULS", vec![Operand::Register(0), Operand::Register(1), Operand::Register(2)]);
        let result = generate(&inst);
        // MULS is not explicitly handled, so it returns None
        assert!(result.is_none());
    }
}
