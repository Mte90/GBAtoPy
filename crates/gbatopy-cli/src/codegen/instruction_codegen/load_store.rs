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
            if let gbatopy_disasm::operand::AddressingMode::Multi { registers, increment, writeback: wb, .. } = offset {
                let is_load = base_opcode.starts_with("LDM");
                let base_reg = *base;
                let reg_list = registers;
                let do_writeback = *writeback || *wb;
                let is_increment = *increment;

                // Determine addressing mode from opcode suffix
                // IA = Increment After (post-increment), DB = Decrement Before (pre-decrement)
                // IB = Increment Before (pre-increment), DA = Decrement After (post-decrement)
                let is_pre_index = base_opcode.contains("IB") || base_opcode.contains("DB");
                let is_decrement = base_opcode.contains("DA") || base_opcode.contains("DB");

                let mut code = String::new();

                // Calculate initial address based on addressing mode
                let num_regs = reg_list.len();
                if is_pre_index {
                    // Pre-index: adjust address before first access
                    if is_increment {
                        // IB: start at base + 4
                        code.push_str(&format!("addr = registers[{}] + 4\n", base_reg));
                    } else {
                        // DB: start at base - (num_regs * 4) + 4 = base - (num_regs - 1) * 4
                        code.push_str(&format!("addr = registers[{}] - {}\n", base_reg, (num_regs - 1) * 4));
                    }
                } else {
                    // Post-index: start at base
                    code.push_str(&format!("addr = registers[{}]\n", base_reg));
                }

                // Generate load/store for each register
                for (i, &reg) in reg_list.iter().enumerate() {
                    if is_load {
                        code.push_str(&format!("registers[{}] = memory.read_u32(addr)\n", reg));
                    } else {
                        code.push_str(&format!("memory.write_u32(addr, registers[{}])\n", reg));
                    }

                    // Update address after each access (except last)
                    if i < num_regs - 1 {
                        if is_increment {
                            code.push_str("addr += 4\n");
                        } else {
                            code.push_str("addr -= 4\n");
                        }
                    }
                }

                // Calculate final address for writeback
                if do_writeback {
                    let final_addr = if is_increment {
                        // IA and IB both write back to base + num_regs * 4
                        format!("registers[{}] + {}", base_reg, num_regs * 4)
                    } else {
                        // DA and DB both write back to base - num_regs * 4
                        format!("registers[{}] - {}", base_reg, num_regs * 4)
                    };
                    code.push_str(&format!("registers[{}] = {}\n", base_reg, final_addr));
                }

                return Some(code);
            }
        }
    }

    // LDRSH: Load Halfword Signed
    if base_opcode == "LDRSH" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!(
                    "temp = memory.read_u16(registers[{}]{})\nregisters[{}] = (temp << 16) >> 16",
                    base, offset_expr, rd
                ));
            }
        }
    }

    // LDRSB: Load Byte Signed
    if base_opcode == "LDRSB" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!(
                    "temp = memory.read_u8(registers[{}]{})\nregisters[{}] = (temp << 24) >> 24",
                    base, offset_expr, rd
                ));
            }
        }
    }

    // SWP/SWPB: swap register with memory
    if base_opcode == "SWP" || base_opcode == "SWPB" {
        if ops.len() >= 3 {
            if let Operand::Register(rd) = ops[0] {
                if let Operand::Register(rm) = ops[1] {
                    if let Operand::Register(rn) = ops[2] {
                        let is_byte = base_opcode == "SWPB";
                        let read = if is_byte { "memory.read_u8" } else { "memory.read_u32" };
                        let write = if is_byte { "memory.write_u8" } else { "memory.write_u32" };
                        let mask = if is_byte { " & 0xFF" } else { "" };
                        return Some(format!(
                            "temp = {}(registers[{}])\nregisters[{}] = temp\n{}(registers[{}], registers[{}]{})",
                            read, rn, rd, write, rn, rm, mask
                        ));
                    }
                }
            }
        }
    }

    None
}
