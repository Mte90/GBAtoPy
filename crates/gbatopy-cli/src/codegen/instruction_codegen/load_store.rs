use gbatopy_disasm::{DecodedInstruction, Operand};

fn base_address_expr(base: u8, inst: &DecodedInstruction) -> String {
    if base == 15 {
        let pc = if inst.mode == gbatopy_disasm::ArmMode::Thumb {
            inst.address + 4
        } else {
            inst.address + 8
        };
        format!("0x{:08X}", pc)
    } else {
        format!("registers[{}]", base)
    }
}

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;
    let base_opcode = opcode.trim_end_matches(|c: char| c.is_ascii_lowercase());

    if base_opcode == "LDR" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, writeback } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 { format!(" + {}", offset) } else { format!(" - {}", -offset) }
                    }
                    _ => String::new(),
                };
                
                let base_expr = base_address_expr(*base, inst);
                let mut code = format!("registers[{}] = memory.read_u32({}{})", rd, base_expr, offset_expr);
                
                // Handle post-increment writeback for LDR
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For LDR with writeback, assume post-increment by word size (4 bytes)
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + 4) & 0xFFFFFFFF", base, base));
                        }
                        _ => {}
                    }
                }
                
                return Some(code);
            }
        }
    }
    if base_opcode == "STR" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, writeback } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 { format!(" + {}", offset) } else { format!(" - {}", -offset) }
                    }
                    _ => String::new(),
                };
                
                let base_expr = base_address_expr(*base, inst);
                let mut code = format!("memory.write_u32({}{}, registers[{}])", base_expr, offset_expr, rd);
                
                // Handle post-increment writeback for STR
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For STR with writeback, assume post-increment by word size (4 bytes)
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + 4) & 0xFFFFFFFF", base, base));
                        }
                        _ => {}
                    }
                }
                
                return Some(code);
            }
        }
    }
    if base_opcode == "LDRB" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, writeback } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 { format!(" + {}", offset) } else { format!(" - {}", -offset) }
                    }
                    _ => String::new(),
                };
                
                let base_expr = base_address_expr(*base, inst);
                let mut code = format!("registers[{}] = memory.read_u8({}{}) & 0xFF", rd, base_expr, offset_expr);
                
                // Handle post-increment writeback for LDRB
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For LDRB with writeback, assume post-increment by byte size (1 byte)
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + 1) & 0xFFFFFFFF", base, base));
                        }
                        _ => {}
                    }
                }
                
                return Some(code);
            }
        }
    }
    if base_opcode == "STRB" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, writeback } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 { format!(" + {}", offset) } else { format!(" - {}", -offset) }
                    }
                    _ => String::new(),
                };
                
                let base_expr = base_address_expr(*base, inst);
                let mut code = format!("memory.write_u8({}{}, registers[{}] & 0xFF)", base_expr, offset_expr, rd);
                
                // Handle post-increment writeback for STRB
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For STRB with writeback, assume post-increment by byte size (1 byte)
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + 1) & 0xFFFFFFFF", base, base));
                        }
                        _ => {}
                    }
                }
                
                return Some(code);
            }
        }
    }
    if base_opcode == "LDRH" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, writeback } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PostIndexedRegister { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 { format!(" + {}", offset) } else { format!(" - {}", -offset) }
                    }
                    _ => String::new(),
                };
                
                let base_expr = base_address_expr(*base, inst);
                let mut code = format!("registers[{}] = memory.read_u16({}{}) & 0xFFFF", rd, base_expr, offset_expr);
                
                // Handle post-increment writeback for LDRH
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::PostIndexedRegister { reg, .. } => {
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF", base, base, reg));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For LDRH with writeback, assume post-increment by halfword size (2 bytes)
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + 2) & 0xFFFFFFFF", base, base));
                        }
                        _ => {}
                    }
                }
                
                return Some(code);
            }
        }
    }
    if base_opcode == "STRH" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, writeback } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PostIndexedRegister { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 { format!(" + {}", offset) } else { format!(" - {}", -offset) }
                    }
                    _ => String::new(),
                };
                
                let base_expr = base_address_expr(*base, inst);
                let mut code = format!("memory.write_u16({}{}, registers[{}] & 0xFFFF)", base_expr, offset_expr, rd);
                
                // Handle post-increment writeback for STRH
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            // Post-increment: add the offset after the store
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::PostIndexedRegister { reg, .. } => {
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF", base, base, reg));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            // Pre-increment writeback: the address was already adjusted before the store
                            // For STRH with pre-indexed writeback, we still need to update the base register
                            let increment = *offset;
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF", base, base, increment));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For STRH with writeback but ImmediateOffset, assume post-increment by halfword size (2 bytes)
                            // This handles cases where the disassembler doesn't distinguish pre/post indexed
                            code.push_str(&format!("\nregisters[{}] = (registers[{}] + 2) & 0xFFFFFFFF", base, base));
                        }
                        _ => {}
                    }
                }
                
                return Some(code);
            }
        }
    }

    if (base_opcode.starts_with("LDM") || base_opcode.starts_with("STM")) && ops.len() >= 1 {
        if let Operand::MemoryAddress { base, offset, writeback } = &ops[0] {
            if let gbatopy_disasm::operand::AddressingMode::Multi { registers, increment, pre_index, writeback: wb, .. } = offset {
                let is_load = base_opcode.starts_with("LDM");
                let base_reg = *base;
                let reg_list = registers;
                let do_writeback = *writeback || *wb;
                let is_increment = *increment;
                let is_pre_index = *pre_index;

                let mut code = String::new();
                let num_regs = reg_list.len();

                // ARM LDM/STM rule: registers are always accessed in ascending register-number
                // order mapped to ascending addresses. For increment modes (IA/IB) the lowest
                // register goes to the lowest address; for decrement modes (DA/DB) the lowest
                // register goes to the lowest address as well, which means the access starts at
                // the bottom of the range and walks upward.
                //
                // Address ranges per mode (n = num_regs):
                //   IA (post,inc): [base,     base + 4n)   final SP = base + 4n
                //   IB (pre,inc):  [base + 4, base + 4n + 4) final SP = base + 4n
                //   DA (post,dec): [base - 4n + 4, base + 4) final SP = base - 4n
                //   DB (pre,dec):  [base - 4n, base)       final SP = base - 4n
                let lowest_addr_expr = if is_increment {
                    if is_pre_index {
                        format!("registers[{}] + 4", base_reg)
                    } else {
                        format!("registers[{}]", base_reg)
                    }
                } else {
                    if is_pre_index {
                        format!("registers[{}] - {}", base_reg, num_regs * 4)
                    } else {
                        format!("registers[{}] - {} + 4", base_reg, num_regs * 4)
                    }
                };
                code.push_str(&format!("addr = {}\n", lowest_addr_expr));

                // Walk the register list in order, incrementing address by 4 each time.
                for (i, &reg) in reg_list.iter().enumerate() {
                    if is_load {
                        code.push_str(&format!("registers[{}] = memory.read_u32(addr)\n", reg));
                    } else {
                        code.push_str(&format!("memory.write_u32(addr, registers[{}])\n", reg));
                    }
                    if i < num_regs - 1 {
                        code.push_str("addr += 4\n");
                    }
                }

                // Writeback: IA/IB → base + n*4; DA/DB → base - n*4
                if do_writeback {
                    let final_addr = if is_increment {
                        format!("registers[{}] + {}", base_reg, num_regs * 4)
                    } else {
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
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    _ => String::new(),
                };
                return Some(format!(
                    "temp = memory.read_u16({}{})\nregisters[{}] = (temp << 16) >> 16",
                    base_address_expr(*base, inst), offset_expr, rd
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
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    _ => String::new(),
                };
                return Some(format!(
                    "temp = memory.read_u8({}{})\nregisters[{}] = (temp << 24) >> 24",
                    base_address_expr(*base, inst), offset_expr, rd
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
