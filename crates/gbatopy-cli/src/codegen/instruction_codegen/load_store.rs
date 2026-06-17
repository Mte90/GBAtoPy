use gbatopy_disasm::{DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;
    let base_opcode = opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());

    if base_opcode == "LDR" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("registers[{}] = memory.read_u32(registers[{}]{})", rd, base, offset_expr));
            }
        }
    }
    if base_opcode == "STR" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("memory.write_u32(registers[{}]{}, registers[{}])", base, offset_expr, rd));
            }
        }
    }
    if base_opcode == "LDRB" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("registers[{}] = memory.read_u8(registers[{}]{}) & 0xFF", rd, base, offset_expr));
            }
        }
    }
    if base_opcode == "STRB" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("memory.write_u8(registers[{}]{}, registers[{}] & 0xFF)", base, offset_expr, rd));
            }
        }
    }
    if base_opcode == "LDRH" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("registers[{}] = memory.read_u16(registers[{}]{}) & 0xFFFF", rd, base, offset_expr));
            }
        }
    }
    if base_opcode == "STRH" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("memory.write_u16(registers[{}]{}, registers[{}] & 0xFFFF)", base, offset_expr, rd));
            }
        }
    }

    if (base_opcode.starts_with("LDM") || base_opcode.starts_with("STM")) && ops.len() >= 1 {
        if let Operand::MemoryAddress { base, offset, writeback } = &ops[0] {
            if let gbatopy_disasm::operand::AddressingMode::Multi { registers, increment, .. } = offset {
                let is_load = base_opcode.starts_with("LDM");
                let base_reg = *base;
                let reg_list = registers;
                let do_writeback = *writeback;
                let is_increment = *increment;

                let pre_index = base_opcode.contains("IB") || base_opcode.contains("DB");
                let post_index = base_opcode.contains("IA") || base_opcode.contains("DA") || !pre_index;

                let mut code = String::new();

                if pre_index {
                    if is_increment {
                        code.push_str(&format!("addr = registers[{}] + {}\n", base_reg, reg_list.len() * 4));
                    } else {
                        code.push_str(&format!("addr = registers[{}] - {}\n", base_reg, reg_list.len() * 4));
                    }
                } else {
                    code.push_str(&format!("addr = registers[{}]\n", base_reg));
                }

                for (i, &reg) in reg_list.iter().enumerate() {
                    if is_load {
                        code.push_str(&format!("registers[{}] = memory.read_u32(addr)\n", reg));
                    } else {
                        code.push_str(&format!("memory.write_u32(addr, registers[{}])\n", reg));
                    }

                    if post_index && i < reg_list.len() - 1 {
                        if is_increment {
                            code.push_str("addr += 4\n");
                        } else {
                            code.push_str("addr -= 4\n");
                        }
                    }
                }

                if pre_index {
                    if is_increment {
                        code.push_str(&format!("addr = registers[{}] + {}\n", base_reg, reg_list.len() * 4));
                    } else {
                        code.push_str(&format!("addr = registers[{}] - {}\n", base_reg, reg_list.len() * 4));
                    }
                }

                if do_writeback {
                    code.push_str(&format!("registers[{}] = addr\n", base_reg));
                }

                return Some(code);
            }
        }
    }

    None
}
