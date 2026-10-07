use gbatopy_disasm::{Condition, DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;
    let base_opcode = opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());

    if base_opcode == "B" || base_opcode == "BL" {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let target = if *target > 0x08000000 && *target < 0x0A000000 {
                *target
            } else {
                return Some(format!("# Invalid branch target: 0x{:08X}", target));
            };
            if base_opcode == "BL" {
                // BL (Branch with Link): set LR = return address (next instruction),
                // then branch to target. LR holds the address the callee should
                // return to via LDMFD SP!, {..., PC} or BX LR.
                return Some(format!(
                    "registers[14] = (registers[15] + 4) & 0xFFFFFFFF\nregisters[15] = 0x{:08X}",
                    target
                ));
            }
            return Some(format!("registers[15] = 0x{:08X}", target));
        }
        return Some(format!("# {} branch (target unknown)", base_opcode));
    }
    if base_opcode == "BX" || base_opcode == "BLX" {
        // BLX/BX with register operand
        if let Some(Operand::Register(rn)) = ops.first() {
            let cond_str = match inst.condition {
                Some(c) if c != Condition::Al => c.name().to_uppercase(),
                _ => String::new(),
            };
            let is_blx = base_opcode == "BLX";
            if !cond_str.is_empty() {
                let lr_set = if is_blx {
                    "    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n".to_string()
                } else {
                    String::new()
                };
                return Some(format!(
                    "if cpsr_check('{}'):\n{}    cpsr['t'] = registers[{}] & 1\n    registers[15] = registers[{}] & 0xFFFFFFFE\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF",
                    cond_str, lr_set, rn, rn
                ));
            }
            let lr_set = if is_blx {
                "registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n".to_string()
            } else {
                String::new()
            };
            return Some(format!(
                "{}cpsr['t'] = registers[{}] & 1\nregisters[15] = registers[{}] & 0xFFFFFFFE",
                lr_set, rn, rn
            ));
        }
        // BLX with immediate operand (ARM mode BLX imm)
        if base_opcode == "BLX" {
            if let Some(Operand::Immediate(target)) = ops.first() {
                if *target > 0x08000000 && *target < 0x0A000000 {
                    return Some(format!(
                        "registers[14] = (registers[15] + 4) & 0xFFFFFFFF\ncpsr['t'] = 1\nregisters[15] = 0x{:08X}",
                        target
                    ));
                }
                return Some(format!("# Invalid BLX target: 0x{:08X}", target));
            }
        }
        return Some(format!("# {} branch exchange", base_opcode));
    }
    // Conditional branches: BEQ, BNE, BCS, BCC, BMI, BPL, BVS, BVC, BHI, BLS, BGE, BLT, BGT, BLE
    if opcode.len() == 3 && opcode.starts_with('B') && opcode != "BX" && opcode != "BLX" {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let cond = &opcode[1..];
            if *target > 0x08000000 && *target < 0x0A000000 {
                return Some(format!("if cpsr_check('{}'):\n    registers[15] = 0x{:08X}\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF", cond, target));
            }
            return Some("registers[15] = (registers[15] + 4) & 0xFFFFFFFF".to_string());
        }
    }
    // Conditional BL: BLEQ, BLNE, etc. (4 chars, starts with "BL", not "BLX")
    if opcode.len() >= 4 && opcode.starts_with("BL") && !opcode.starts_with("BLX") {
        if let Some(Operand::Immediate(target)) = ops.first() {
            let cond = &opcode[2..];
            if *target > 0x08000000 && *target < 0x0A000000 {
                return Some(format!(
                    "if cpsr_check('{}'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x{:08X}\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF",
                    cond, target
                ));
            }
            return Some("registers[15] = (registers[15] + 4) & 0xFFFFFFFF".to_string());
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use gbatopy_disasm::{ArmMode, Condition, DecodedInstruction, Operand};

    fn make_inst(
        opcode: &str,
        operands: Vec<Operand>,
        mode: ArmMode,
        addr: u32,
    ) -> DecodedInstruction {
        DecodedInstruction {
            address: addr,
            opcode: opcode.to_string(),
            operands,
            condition: Some(Condition::Al),
            mode,
            raw: 0,
            sets_flags: false,
            width: if mode == ArmMode::Arm { 4 } else { 2 },
            is_data: false,
        }
    }

    // === B (unconditional branch) tests ===
    #[test]
    fn test_generate_b_valid_target() {
        let inst = make_inst(
            "B",
            vec![Operand::Immediate(0x08000100)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[15] = 0x08000100");
    }

    #[test]
    fn test_generate_b_invalid_target_low() {
        let inst = make_inst(
            "B",
            vec![Operand::Immediate(0x07FFFFFF)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "# Invalid branch target: 0x07FFFFFF");
    }

    #[test]
    fn test_generate_b_invalid_target_high() {
        let inst = make_inst(
            "B",
            vec![Operand::Immediate(0x0A000000)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "# Invalid branch target: 0x0A000000");
    }

    #[test]
    fn test_generate_b_no_operand() {
        let inst = make_inst("B", vec![], ArmMode::Arm, 0x08000000);
        let code = generate(&inst).unwrap();
        assert_eq!(code, "# B branch (target unknown)");
    }

    // === BL (branch with link) tests ===
    #[test]
    fn test_generate_bl_valid_target() {
        let inst = make_inst(
            "BL",
            vec![Operand::Immediate(0x08000200)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[14] = (registers[15] + 4) & 0xFFFFFFFF\nregisters[15] = 0x08000200"
        );
    }

    #[test]
    fn test_generate_bl_invalid_target() {
        let inst = make_inst(
            "BL",
            vec![Operand::Immediate(0x00000000)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "# Invalid branch target: 0x00000000");
    }

    #[test]
    fn test_generate_bl_no_operand() {
        let inst = make_inst("BL", vec![], ArmMode::Arm, 0x08000000);
        let code = generate(&inst).unwrap();
        assert_eq!(code, "# BL branch (target unknown)");
    }

    // === BX (branch and exchange) tests ===
    #[test]
    fn test_generate_bx_register() {
        let inst = make_inst(
            "BX",
            vec![Operand::Register(14)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "cpsr['t'] = registers[14] & 1\nregisters[15] = registers[14] & 0xFFFFFFFE"
        );
    }

    #[test]
    fn test_generate_bx_no_operand() {
        let inst = make_inst("BX", vec![], ArmMode::Arm, 0x08000000);
        let code = generate(&inst).unwrap();
        assert_eq!(code, "# BX branch exchange");
    }

    #[test]
    fn test_generate_bx_conditional() {
        let inst = DecodedInstruction {
            address: 0x08000000,
            opcode: "BX".to_string(),
            operands: vec![Operand::Register(14)],
            condition: Some(Condition::Ne),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };
        let code = generate(&inst).unwrap();
        assert!(code.contains("if cpsr_check('NE'):"));
        assert!(code.contains("cpsr['t'] = registers[14] & 1"));
        assert!(code.contains("registers[15] = registers[14] & 0xFFFFFFFE"));
        assert!(code.contains("else:"));
        assert!(code.contains("registers[15] = (registers[15] + 4) & 0xFFFFFFFF"));
    }

    // === BLX (branch with link and exchange) tests ===
    #[test]
    fn test_generate_blx_register() {
        let inst = make_inst(
            "BLX",
            vec![Operand::Register(14)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[14] = (registers[15] + 4) & 0xFFFFFFFF\ncpsr['t'] = registers[14] & 1\nregisters[15] = registers[14] & 0xFFFFFFFE"
        );
    }

    #[test]
    fn test_generate_blx_immediate_valid() {
        let inst = make_inst(
            "BLX",
            vec![Operand::Immediate(0x08000300)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[14] = (registers[15] + 4) & 0xFFFFFFFF\ncpsr['t'] = 1\nregisters[15] = 0x08000300"
        );
    }

    #[test]
    fn test_generate_blx_immediate_invalid() {
        let inst = make_inst(
            "BLX",
            vec![Operand::Immediate(0x00000000)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "# Invalid BLX target: 0x00000000");
    }

    #[test]
    fn test_generate_blx_no_operand() {
        let inst = make_inst("BLX", vec![], ArmMode::Arm, 0x08000000);
        let code = generate(&inst).unwrap();
        assert_eq!(code, "# BLX branch exchange");
    }

    #[test]
    fn test_generate_blx_conditional() {
        let inst = DecodedInstruction {
            address: 0x08000000,
            opcode: "BLXne".to_string(),
            operands: vec![Operand::Register(14)],
            condition: Some(Condition::Ne),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };
        let code = generate(&inst).unwrap_or("".to_string());
        assert!(code.contains("if cpsr_check('NE'):"));
        assert!(code.contains("registers[14] = (registers[15] + 4) & 0xFFFFFFFF"));
        assert!(code.contains("cpsr['t'] = registers[14] & 1"));
        assert!(code.contains("registers[15] = registers[14] & 0xFFFFFFFE"));
    }

    // === Conditional branch tests (BEQ, BNE, etc.) ===
    #[test]
    fn test_generate_beq() {
        let inst = make_inst(
            "BEQ",
            vec![Operand::Immediate(0x08000050)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('EQ'):\n    registers[15] = 0x08000050\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bne() {
        let inst = make_inst(
            "BNE",
            vec![Operand::Immediate(0x08000100)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('NE'):\n    registers[15] = 0x08000100\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bcs() {
        let inst = make_inst(
            "BCS",
            vec![Operand::Immediate(0x08000200)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('CS'):\n    registers[15] = 0x08000200\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bcc() {
        let inst = make_inst(
            "BCC",
            vec![Operand::Immediate(0x08000300)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('CC'):\n    registers[15] = 0x08000300\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bmi() {
        let inst = make_inst(
            "BMI",
            vec![Operand::Immediate(0x08000400)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('MI'):\n    registers[15] = 0x08000400\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bpl() {
        let inst = make_inst(
            "BPL",
            vec![Operand::Immediate(0x08000500)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('PL'):\n    registers[15] = 0x08000500\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bvs() {
        let inst = make_inst(
            "BVS",
            vec![Operand::Immediate(0x08000600)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('VS'):\n    registers[15] = 0x08000600\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bvc() {
        let inst = make_inst(
            "BVC",
            vec![Operand::Immediate(0x08000700)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('VC'):\n    registers[15] = 0x08000700\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bhi() {
        let inst = make_inst(
            "BHI",
            vec![Operand::Immediate(0x08000800)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('HI'):\n    registers[15] = 0x08000800\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bls() {
        let inst = make_inst(
            "BLS",
            vec![Operand::Immediate(0x08000900)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('LS'):\n    registers[15] = 0x08000900\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bge() {
        let inst = make_inst(
            "BGE",
            vec![Operand::Immediate(0x08000A00)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('GE'):\n    registers[15] = 0x08000A00\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blt() {
        let inst = make_inst(
            "BLT",
            vec![Operand::Immediate(0x08000B00)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('LT'):\n    registers[15] = 0x08000B00\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bgt() {
        let inst = make_inst(
            "BGT",
            vec![Operand::Immediate(0x08000C00)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('GT'):\n    registers[15] = 0x08000C00\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_ble() {
        let inst = make_inst(
            "BLE",
            vec![Operand::Immediate(0x08000D00)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('LE'):\n    registers[15] = 0x08000D00\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_conditional_branch_invalid_target() {
        let inst = make_inst(
            "BEQ",
            vec![Operand::Immediate(0x00000000)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[15] = (registers[15] + 4) & 0xFFFFFFFF");
    }



    // === Conditional BL tests (BLEQ, BLNE, etc.) ===
    #[test]
    fn test_generate_bleq() {
        let inst = make_inst(
            "BLEQ",
            vec![Operand::Immediate(0x08001000)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('EQ'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001000\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blne() {
        let inst = make_inst(
            "BLNE",
            vec![Operand::Immediate(0x08001100)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('NE'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001100\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blcs() {
        let inst = make_inst(
            "BLCS",
            vec![Operand::Immediate(0x08001200)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('CS'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001200\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blcc() {
        let inst = make_inst(
            "BLCC",
            vec![Operand::Immediate(0x08001300)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('CC'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001300\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blmi() {
        let inst = make_inst(
            "BLMI",
            vec![Operand::Immediate(0x08001400)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('MI'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001400\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blpl() {
        let inst = make_inst(
            "BLPL",
            vec![Operand::Immediate(0x08001500)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('PL'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001500\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blvs() {
        let inst = make_inst(
            "BLVS",
            vec![Operand::Immediate(0x08001600)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('VS'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001600\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blvc() {
        let inst = make_inst(
            "BLVC",
            vec![Operand::Immediate(0x08001700)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('VC'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001700\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blhi() {
        let inst = make_inst(
            "BLHI",
            vec![Operand::Immediate(0x08001800)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('HI'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001800\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blhs() {
        let inst = make_inst(
            "BLHS",
            vec![Operand::Immediate(0x08001900)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('HS'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001900\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blle() {
        let inst = make_inst(
            "BLLE",
            vec![Operand::Immediate(0x08001A00)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('LE'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001A00\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blge() {
        let inst = make_inst(
            "BLGE",
            vec![Operand::Immediate(0x08001B00)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('GE'):\n    registers[14] = (registers[15] + 4) & 0xFFFFFFFF\n    registers[15] = 0x08001B00\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_blgtr() {
        let inst = make_inst(
            "BGT",
            vec![Operand::Immediate(0x08001C00)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "if cpsr_check('GT'):\n    registers[15] = 0x08001C00\nelse:\n    registers[15] = (registers[15] + 4) & 0xFFFFFFFF"
        );
    }

    #[test]
    fn test_generate_bl_conditional_invalid_target() {
        let inst = make_inst(
            "BLEQ",
            vec![Operand::Immediate(0x00000000)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[15] = (registers[15] + 4) & 0xFFFFFFFF");
    }



    // === Edge cases ===
    #[test]
    fn test_generate_b_max_valid_target() {
        let inst = make_inst(
            "B",
            vec![Operand::Immediate(0x09FFFFFF)],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[15] = 0x09FFFFFF");
    }

    #[test]
    fn test_generate_b_thumb_region() {
        // Thumb region is 0x08000001 (odd address)
        let inst = make_inst(
            "B",
            vec![Operand::Immediate(0x08000001)],
            ArmMode::Thumb,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(code, "registers[15] = 0x08000001");
    }

    #[test]
    fn test_generate_blx_thumb_entry() {
        // BLX to Thumb entry point
        let inst = make_inst(
            "BLX",
            vec![Operand::Immediate(0x08000005)],
            ArmMode::Thumb,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[14] = (registers[15] + 4) & 0xFFFFFFFF\ncpsr['t'] = 1\nregisters[15] = 0x08000005"
        );
    }

    #[test]
    fn test_generate_unknown_opcode() {
        let inst = DecodedInstruction {
            address: 0x08000000,
            opcode: "UNK".to_string(),
            operands: vec![],
            condition: Some(Condition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };
        let code = generate(&inst);
        assert!(code.is_none());
    }
}
