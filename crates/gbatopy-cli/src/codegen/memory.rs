use gbatopy_disasm::{AddressingMode, Operand};

#[allow(dead_code)]
pub fn generate_store_instruction(
    rd: u8,
    mem_op: &Operand,
    is_halfword: bool,
    is_byte: bool,
) -> String {
    match mem_op {
        Operand::MemoryAddress {
            base,
            offset,
            writeback,
        } => {
            let base_reg = format!("r{}", base);
            let offset_expr = match offset {
                AddressingMode::ImmediateOffset(val) => {
                    if *val >= 0 {
                        format!(" + {}", val)
                    } else {
                        format!(" - {}", -val)
                    }
                }
                AddressingMode::RegisterOffset(reg) => {
                    format!(" + r{}", reg)
                }
                AddressingMode::ScaledRegisterOffset { reg, shift, amount } => {
                    let shift_str = match shift {
                        gbatopy_disasm::ShiftType::Lsl => " << ",
                        gbatopy_disasm::ShiftType::Lsr => " >> ",
                        gbatopy_disasm::ShiftType::Asr => " >> ",
                        _ => " << ",
                    };
                    format!(" + (r{}{}{})", reg, shift_str, amount)
                }
                _ => " + 0".to_string(),
            };

            let addr_expr = format!("{}{}", base_reg, offset_expr);
            let value_expr = format!("r{}", rd);
            let (size_check, write_method) = if is_byte {
                ("& 0xFF", "write_u8")
            } else if is_halfword {
                ("& 0xFFFF", "write_u16")
            } else {
                ("& 0xFFFFFFFF", "write_u32")
            };

            let mut code = format!(
                "self.memory.{}({}, ({} & {}))",
                write_method, addr_expr, value_expr, size_check
            );

            if *writeback {
                code.push_str(&format!(
                    "\n    {} = {}{}",
                    base_reg, addr_expr, offset_expr
                ));
            }
            code
        }
        _ => "# Unsupported memory addressing mode for STR".to_string(),
    }
}

#[allow(dead_code)]
pub fn generate_load_instruction(
    rd: u8,
    mem_op: &Operand,
    is_halfword: bool,
    is_byte: bool,
) -> String {
    match mem_op {
        Operand::MemoryAddress {
            base,
            offset,
            writeback,
        } => {
            let base_reg = format!("r{}", base);
            let offset_expr = match offset {
                AddressingMode::ImmediateOffset(val) => {
                    if *val >= 0 {
                        format!(" + {}", val)
                    } else {
                        format!(" - {}", -val)
                    }
                }
                AddressingMode::RegisterOffset(reg) => {
                    format!(" + r{}", reg)
                }
                AddressingMode::ScaledRegisterOffset { reg, shift, amount } => {
                    let shift_str = match shift {
                        gbatopy_disasm::ShiftType::Lsl => " << ",
                        gbatopy_disasm::ShiftType::Lsr => " >> ",
                        gbatopy_disasm::ShiftType::Asr => " >> ",
                        _ => " << ",
                    };
                    format!(" + (r{}{}{})", reg, shift_str, amount)
                }
                _ => " + 0".to_string(),
            };

            let addr_expr = format!("{}{}", base_reg, offset_expr);
            let (read_method, mask) = if is_byte {
                ("read_u8", "& 0xFF")
            } else if is_halfword {
                ("read_u16", "& 0xFFFF")
            } else {
                ("read_u32", "& 0xFFFFFFFF")
            };

            let mut code = format!(
                "r{} = self.memory.{}({}, {})",
                rd, read_method, addr_expr, mask
            );

            if *writeback {
                code.push_str(&format!(
                    "\n    {} = {}{}",
                    base_reg, addr_expr, offset_expr
                ));
            }
            code
        }
        _ => "# Unsupported memory addressing mode for LDR".to_string(),
    }
}
