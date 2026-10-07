use gbatopy_disasm::{DecodedInstruction, Operand};

fn base_address_expr(base: u8, inst: &DecodedInstruction) -> String {
    if base == 15 {
        let pc = if inst.mode == gbatopy_disasm::ArmMode::Thumb {
            (inst.address + 4) & !3
        } else {
            inst.address + 8
        };
        format!("0x{:08X}", pc)
    } else {
        format!("registers[{}]", base)
    }
}

fn scaled_reg_offset_expr(
    reg: u8,
    shift: gbatopy_disasm::operand::ShiftType,
    amount: u8,
) -> String {
    use gbatopy_disasm::operand::ShiftType;
    match shift {
        ShiftType::Lsl if amount == 0 => format!(" + registers[{}]", reg),
        ShiftType::Lsl => format!(" + ((registers[{}] << {}) & 0xFFFFFFFF)", reg, amount),
        ShiftType::Lsr if amount == 0 => format!(" + (0 if registers[{}] == 0 else 0)", reg),
        ShiftType::Lsr => format!(" + (registers[{}] >> {})", reg, amount),
        ShiftType::Asr if amount == 0 => {
            format!(" + (0xFFFFFFFF if registers[{}] & 0x80000000 else 0)", reg)
        }
        ShiftType::Asr => format!(
            " + ((registers[{}] >> {}) | (0xFFFFFFFF if registers[{}] & 0x80000000 else 0))",
            reg, amount, reg
        ),
        ShiftType::Ror if amount == 0 => format!(" + ((registers[{}] >> 1) & 0x7FFFFFFF)", reg),
        ShiftType::Ror => format!(
            " + (((registers[{}] >> {}) | (registers[{}] << (32 - {}))) & 0xFFFFFFFF)",
            reg, amount, reg, amount
        ),
    }
}

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

    if base_opcode == "LDR" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress {
                base,
                offset,
                writeback,
            } = &ops[1]
            {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 {
                            format!(" + {}", n)
                        } else {
                            format!(" - {}", -n)
                        }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::ScaledRegisterOffset {
                        reg,
                        shift,
                        amount,
                    } => scaled_reg_offset_expr(*reg, *shift, *amount),
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => String::new(),
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 {
                            format!(" + {}", offset)
                        } else {
                            format!(" - {}", -offset)
                        }
                    }
                    _ => String::new(),
                };

                let base_expr = base_address_expr(*base, inst);
                let mut code = format!(
                    "registers[{}] = memory.read_u32({}{})",
                    rd, base_expr, offset_expr
                );

                // Handle post-increment writeback for LDR
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PostIndexedRegister {
                            reg,
                            ..
                        } => {
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF",
                                base, base, reg
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For LDR with writeback, assume post-increment by word size (4 bytes)
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + 4) & 0xFFFFFFFF",
                                base, base
                            ));
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
            if let Operand::MemoryAddress {
                base,
                offset,
                writeback,
            } = &ops[1]
            {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 {
                            format!(" + {}", n)
                        } else {
                            format!(" - {}", -n)
                        }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::ScaledRegisterOffset {
                        reg,
                        shift,
                        amount,
                    } => scaled_reg_offset_expr(*reg, *shift, *amount),
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => String::new(),
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 {
                            format!(" + {}", offset)
                        } else {
                            format!(" - {}", -offset)
                        }
                    }
                    _ => String::new(),
                };

                let base_expr = base_address_expr(*base, inst);
                let mut code = format!(
                    "memory.write_u32({}{}, registers[{}])",
                    base_expr, offset_expr, rd
                );

                // Handle post-increment writeback for STR
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PostIndexedRegister {
                            reg,
                            ..
                        } => {
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF",
                                base, base, reg
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For STR with writeback, assume post-increment by word size (4 bytes)
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + 4) & 0xFFFFFFFF",
                                base, base
                            ));
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
            if let Operand::MemoryAddress {
                base,
                offset,
                writeback,
            } = &ops[1]
            {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 {
                            format!(" + {}", n)
                        } else {
                            format!(" - {}", -n)
                        }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::ScaledRegisterOffset {
                        reg,
                        shift,
                        amount,
                    } => scaled_reg_offset_expr(*reg, *shift, *amount),
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => String::new(),
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 {
                            format!(" + {}", offset)
                        } else {
                            format!(" - {}", -offset)
                        }
                    }
                    _ => String::new(),
                };

                let base_expr = base_address_expr(*base, inst);
                let mut code = format!(
                    "registers[{}] = memory.read_u8({}{}) & 0xFF",
                    rd, base_expr, offset_expr
                );

                // Handle post-increment writeback for LDRB
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PostIndexedRegister {
                            reg,
                            ..
                        } => {
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF",
                                base, base, reg
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For LDRB with writeback, assume post-increment by byte size (1 byte)
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + 1) & 0xFFFFFFFF",
                                base, base
                            ));
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
            if let Operand::MemoryAddress {
                base,
                offset,
                writeback,
            } = &ops[1]
            {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 {
                            format!(" + {}", n)
                        } else {
                            format!(" - {}", -n)
                        }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::ScaledRegisterOffset {
                        reg,
                        shift,
                        amount,
                    } => scaled_reg_offset_expr(*reg, *shift, *amount),
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => String::new(),
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 {
                            format!(" + {}", offset)
                        } else {
                            format!(" - {}", -offset)
                        }
                    }
                    _ => String::new(),
                };

                let base_expr = base_address_expr(*base, inst);
                let mut code = format!(
                    "memory.write_u8({}{}, registers[{}] & 0xFF)",
                    base_expr, offset_expr, rd
                );

                // Handle post-increment writeback for STRB
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PostIndexedRegister {
                            reg,
                            ..
                        } => {
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF",
                                base, base, reg
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For STRB with writeback, assume post-increment by byte size (1 byte)
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + 1) & 0xFFFFFFFF",
                                base, base
                            ));
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
            if let Operand::MemoryAddress {
                base,
                offset,
                writeback,
            } = &ops[1]
            {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 {
                            format!(" + {}", n)
                        } else {
                            format!(" - {}", -n)
                        }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::ScaledRegisterOffset {
                        reg,
                        shift,
                        amount,
                    } => scaled_reg_offset_expr(*reg, *shift, *amount),
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => String::new(),
                    gbatopy_disasm::operand::AddressingMode::PostIndexedRegister { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 {
                            format!(" + {}", offset)
                        } else {
                            format!(" - {}", -offset)
                        }
                    }
                    _ => String::new(),
                };

                let base_expr = base_address_expr(*base, inst);
                let mut code = format!(
                    "registers[{}] = memory.read_u16({}{}) & 0xFFFF",
                    rd, base_expr, offset_expr
                );

                // Handle post-increment writeback for LDRH
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PostIndexedRegister {
                            reg,
                            ..
                        } => {
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF",
                                base, base, reg
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For LDRH with writeback, assume post-increment by halfword size (2 bytes)
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + 2) & 0xFFFFFFFF",
                                base, base
                            ));
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
            if let Operand::MemoryAddress {
                base,
                offset,
                writeback,
            } = &ops[1]
            {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 {
                            format!(" + {}", n)
                        } else {
                            format!(" - {}", -n)
                        }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    gbatopy_disasm::operand::AddressingMode::ScaledRegisterOffset {
                        reg,
                        shift,
                        amount,
                    } => scaled_reg_offset_expr(*reg, *shift, *amount),
                    gbatopy_disasm::operand::AddressingMode::PostIndexed { .. } => String::new(),
                    gbatopy_disasm::operand::AddressingMode::PostIndexedRegister { .. } => {
                        String::new()
                    }
                    gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                        if *offset >= 0 {
                            format!(" + {}", offset)
                        } else {
                            format!(" - {}", -offset)
                        }
                    }
                    _ => String::new(),
                };

                let base_expr = base_address_expr(*base, inst);
                let mut code = format!(
                    "memory.write_u16({}{}, registers[{}] & 0xFFFF)",
                    base_expr, offset_expr, rd
                );

                // Handle post-increment writeback for STRH
                if *writeback {
                    match offset {
                        gbatopy_disasm::operand::AddressingMode::PostIndexed { offset, .. } => {
                            // Post-increment: add the offset after the store
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PostIndexedRegister {
                            reg,
                            ..
                        } => {
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + registers[{}]) & 0xFFFFFFFF",
                                base, base, reg
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::PreIndexed { offset, .. } => {
                            // Pre-increment writeback: the address was already adjusted before the store
                            // For STRH with pre-indexed writeback, we still need to update the base register
                            let increment = *offset;
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + {}) & 0xFFFFFFFF",
                                base, base, increment
                            ));
                        }
                        gbatopy_disasm::operand::AddressingMode::ImmediateOffset(_) => {
                            // For STRH with writeback but ImmediateOffset, assume post-increment by halfword size (2 bytes)
                            // This handles cases where the disassembler doesn't distinguish pre/post indexed
                            code.push_str(&format!(
                                "\nregisters[{}] = (registers[{}] + 2) & 0xFFFFFFFF",
                                base, base
                            ));
                        }
                        _ => {}
                    }
                }

                return Some(code);
            }
        }
    }

    if (base_opcode.starts_with("LDM") || base_opcode.starts_with("STM")) && !ops.is_empty() {
        if let Operand::MemoryAddress {
            base,
            offset,
            writeback,
        } = &ops[0]
        {
            // Not collapsible: outer if let destructures ops[0], inner destructures offset
            #[allow(clippy::collapsible_match)]
            if let gbatopy_disasm::operand::AddressingMode::Multi {
                registers,
                increment,
                pre_index,
                writeback: wb,
                s_bit,
                ..
            } = offset
            {
                let is_load = base_opcode.starts_with("LDM");
                let base_reg = *base;
                let reg_list = registers;
                let do_writeback = *writeback || *wb;
                let is_increment = *increment;
                let is_pre_index = *pre_index;
                let has_s_bit = *s_bit;

                // S-bit (bit 22) handling:
                // - LDM with PC in list + S=1: exception return — load PC, restore CPSR from SPSR.
                // - LDM without PC + S=1: load into user-bank registers via _write_user_reg().
                // - STM + S=1: store from user-bank registers via _read_user_reg().

                let mut code = String::new();
                let num_regs = reg_list.len();
                let base_in_list = reg_list.contains(&base_reg);

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

                // Walk the register list in order, always incrementing address by 4 each time.
                // Lowest register maps to lowest address in all four addressing modes (IA/IB/DA/DB).
                let _has_pc = reg_list.contains(&15);
                for (i, &reg) in reg_list.iter().enumerate() {
                    if is_load {
                        if reg == 15 && has_s_bit {
                            // LDM ... {PC}^ : exception return — load PC and restore CPSR from SPSR.
                            code.push_str("registers[15] = memory.read_u32(addr)\n");
                            code.push_str("_new_cpsr = _spsr_for_mode(cpsr['mode'])\n");
                            code.push_str("_old_mode = cpsr['mode']\n");
                            code.push_str("_cpsr_from_int(cpsr, _new_cpsr)\n");
                            code.push_str("_switch_mode(cpsr['mode'])\n");
                        } else if has_s_bit {
                            code.push_str(&format!("_write_user_reg({}, memory.read_u32(addr))\n", reg));
                        } else {
                            code.push_str(&format!("registers[{}] = memory.read_u32(addr)\n", reg));
                        }
                    } else {
                        if has_s_bit {
                            code.push_str(&format!("memory.write_u32(addr, _read_user_reg({}))\n", reg));
                        } else {
                            code.push_str(&format!("memory.write_u32(addr, registers[{}])\n", reg));
                        }
                    }
                    if i < num_regs - 1 {
                        code.push_str("addr += 4\n");
                    }
                }

                // Writeback: save original base if it's in the register list
                if do_writeback && base_in_list {
                    code.push_str(&format!("_orig_base = registers[{}]\n", base_reg));
                }
                // IA/IB → base + n*4; DA/DB → base - n*4
                if do_writeback {
                    let base_expr = if base_in_list {
                        "_orig_base"
                    } else {
                        &format!("registers[{}]", base_reg)
                    };
                    let final_addr = if is_increment {
                        format!("{} + {}", base_expr, num_regs * 4)
                    } else {
                        format!("{} - {}", base_expr, num_regs * 4)
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
                        if *n >= 0 {
                            format!(" + {}", n)
                        } else {
                            format!(" - {}", -n)
                        }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    _ => String::new(),
                };
                return Some(format!(
                    "temp = memory.read_u16({}{})\nregisters[{}] = (temp << 16) >> 16",
                    base_address_expr(*base, inst),
                    offset_expr,
                    rd
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
                        if *n >= 0 {
                            format!(" + {}", n)
                        } else {
                            format!(" - {}", -n)
                        }
                    }
                    gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                        format!(" + registers[{}]", reg)
                    }
                    _ => String::new(),
                };
                return Some(format!(
                    "temp = memory.read_u8({}{})\nregisters[{}] = (temp << 24) >> 24",
                    base_address_expr(*base, inst),
                    offset_expr,
                    rd
                ));
            }
        }
    }

    // SWP/SWPB: swap register with memory
    // Not collapsed: 5-level nesting with specific guard conditions at each level
    #[allow(clippy::collapsible_if)]
    if base_opcode == "SWP" || base_opcode == "SWPB" {
        if ops.len() >= 3 {
            if let Operand::Register(rd) = ops[0] {
                if let Operand::Register(rm) = ops[1] {
                    if let Operand::Register(rn) = ops[2] {
                        let is_byte = base_opcode == "SWPB";
                        let read = if is_byte {
                            "memory.read_u8"
                        } else {
                            "memory.read_u32"
                        };
                        let write = if is_byte {
                            "memory.write_u8"
                        } else {
                            "memory.write_u32"
                        };
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

#[cfg(test)]
mod tests {
    use super::*;
    use gbatopy_disasm::{operand::AddressingMode, ArmMode, Condition, DecodedInstruction, Operand};

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

    // === LDR tests ===
    #[test]
    fn test_generate_ldr_immediate_offset_positive() {
        let inst = make_inst(
            "LDR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(16),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = memory.read_u32(registers[1] + 16)"
        );
    }

    #[test]
    fn test_generate_ldr_immediate_offset_negative() {
        let inst = make_inst(
            "LDR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(-8),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = memory.read_u32(registers[1] - 8)"
        );
    }

    #[test]
    fn test_generate_ldr_pc_relative() {
        let inst = make_inst(
            "LDR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 15,
                    offset: AddressingMode::ImmediateOffset(20),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        // PC = address + 8 = 0x08000008
        assert!(code.contains("0x08000008"));
        assert!(code.contains(" + 20"));
        assert!(code.contains("registers[0] = memory.read_u32"));
    }

    #[test]
    fn test_generate_ldr_register_offset() {
        let inst = make_inst(
            "LDR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::RegisterOffset(2),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = memory.read_u32(registers[1] + registers[2])"
        );
    }

    #[test]
    fn test_generate_ldr_scaled_register_offset_lsl() {
        let inst = make_inst(
            "LDR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ScaledRegisterOffset {
                        reg: 2,
                        shift: gbatopy_disasm::operand::ShiftType::Lsl,
                        amount: 2,
                    },
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[1]"));
        assert!(code.contains("(registers[2] << 2)"));
        assert!(code.contains("memory.read_u32"));
    }

    #[test]
    fn test_generate_ldr_with_writeback() {
        let inst = make_inst(
            "LDR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(16),
                    writeback: true,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[0] = memory.read_u32(registers[1] + 16)"));
        assert!(code.contains("registers[1] = (registers[1] + 4) & 0xFFFFFFFF"));
    }

    // === STR tests ===
    #[test]
    fn test_generate_str_immediate_offset() {
        let inst = make_inst(
            "STR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(24),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "memory.write_u32(registers[1] + 24, registers[0])"
        );
    }

    #[test]
    fn test_generate_str_with_writeback() {
        let inst = make_inst(
            "STR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(8),
                    writeback: true,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("memory.write_u32(registers[1] + 8, registers[0])"));
        assert!(code.contains("registers[1] = (registers[1] + 4) & 0xFFFFFFFF"));
    }

    // === LDRB tests ===
    #[test]
    fn test_generate_ldrb_immediate_offset() {
        let inst = make_inst(
            "LDRB",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(12),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = memory.read_u8(registers[1] + 12) & 0xFF"
        );
    }

    #[test]
    fn test_generate_ldrb_with_writeback() {
        let inst = make_inst(
            "LDRB",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(4),
                    writeback: true,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[0] = memory.read_u8(registers[1] + 4) & 0xFF"));
        assert!(code.contains("registers[1] = (registers[1] + 1) & 0xFFFFFFFF"));
    }

    // === STRB tests ===
    #[test]
    fn test_generate_strb_immediate_offset() {
        let inst = make_inst(
            "STRB",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(8),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "memory.write_u8(registers[1] + 8, registers[0] & 0xFF)"
        );
    }

    // === LDRH tests ===
    #[test]
    fn test_generate_ldrh_immediate_offset() {
        let inst = make_inst(
            "LDRH",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(22),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = memory.read_u16(registers[1] + 22) & 0xFFFF"
        );
    }

    #[test]
    fn test_generate_ldrh_with_writeback() {
        let inst = make_inst(
            "LDRH",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(10),
                    writeback: true,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[0] = memory.read_u16(registers[1] + 10) & 0xFFFF"));
        assert!(code.contains("registers[1] = (registers[1] + 2) & 0xFFFFFFFF"));
    }

    // === STRH tests ===
    #[test]
    fn test_generate_strh_immediate_offset() {
        let inst = make_inst(
            "STRH",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(30),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "memory.write_u16(registers[1] + 30, registers[0] & 0xFFFF)"
        );
    }

    #[test]
    fn test_generate_strh_with_writeback() {
        let inst = make_inst(
            "STRH",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(6),
                    writeback: true,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("memory.write_u16(registers[1] + 6, registers[0] & 0xFFFF)"));
        assert!(code.contains("registers[1] = (registers[1] + 2) & 0xFFFFFFFF"));
    }

    // === LDM tests ===
    #[test]
    fn test_generate_ldmfd_increasing_addresses() {
        let inst = make_inst(
            "LDMFD",
            vec![Operand::MemoryAddress {
                base: 13,
                offset: AddressingMode::Multi {
                    base: 13,
                    registers: vec![4, 5, 6],
                    increment: true,
                    pre_index: false,
                    writeback: true,
                    s_bit: false,
                },
                writeback: true,
            }],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("addr = registers[13]"));
        assert!(code.contains("addr += 4"));
        assert!(code.contains("registers[4] = memory.read_u32(addr)"));
        assert!(code.contains("registers[5] = memory.read_u32(addr)"));
        assert!(code.contains("registers[6] = memory.read_u32(addr)"));
        assert!(code.contains("registers[13] = registers[13] + 12"));
    }

    #[test]
    fn test_generate_ldm_with_pc_in_list() {
        let inst = make_inst(
            "LDMFD",
            vec![Operand::MemoryAddress {
                base: 13,
                offset: AddressingMode::Multi {
                    base: 13,
                    registers: vec![4, 15],
                    increment: true,
                    pre_index: false,
                    writeback: false,
                    s_bit: false,
                },
                writeback: false,
            }],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[4] = memory.read_u32(addr)"));
        assert!(code.contains("registers[15] = memory.read_u32(addr)"));
    }

    // === STM tests ===
    #[test]
    fn test_generate_stmfd_decreasing_addresses() {
        let inst = make_inst(
            "STMFD",
            vec![Operand::MemoryAddress {
                base: 13,
                offset: AddressingMode::Multi {
                    base: 13,
                    registers: vec![4, 5, 14],
                    increment: false,
                    pre_index: true,
                    writeback: true,
                    s_bit: false,
                },
                writeback: true,
            }],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("addr = registers[13] - 12"));
        assert!(code.contains("addr += 4"));
        assert!(code.contains("memory.write_u32(addr, registers[4])"));
        assert!(code.contains("memory.write_u32(addr, registers[5])"));
        assert!(code.contains("memory.write_u32(addr, registers[14])"));
        assert!(code.contains("registers[13] = registers[13] - 12"));
    }

    #[test]
    fn test_generate_stmia_increasing_addresses() {
        let inst = make_inst(
            "STMIA",
            vec![Operand::MemoryAddress {
                base: 13,
                offset: AddressingMode::Multi {
                    base: 13,
                    registers: vec![4, 5, 6],
                    increment: true,
                    pre_index: false,
                    writeback: true,
                    s_bit: false,
                },
                writeback: true,
            }],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("addr = registers[13]"));
        assert!(code.contains("addr += 4"));
        assert!(code.contains("memory.write_u32(addr, registers[4])"));
        assert!(code.contains("registers[13] = registers[13] + 12"));
    }

    // === LDRSH tests ===
    #[test]
    fn test_generate_ldrsh_immediate_offset() {
        let inst = make_inst(
            "LDRSH",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(8),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("temp = memory.read_u16(registers[1] + 8)"));
        assert!(code.contains("registers[0] = (temp << 16) >> 16"));
    }

    // === LDRSB tests ===
    #[test]
    fn test_generate_ldrsb_immediate_offset() {
        let inst = make_inst(
            "LDRSB",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(4),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("temp = memory.read_u8(registers[1] + 4)"));
        assert!(code.contains("registers[0] = (temp << 24) >> 24"));
    }

    // === SWP tests ===
    #[test]
    fn test_generate_swp_word_swap() {
        let inst = make_inst(
            "SWP",
            vec![
                Operand::Register(0),
                Operand::Register(1),
                Operand::Register(2),
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("temp = memory.read_u32(registers[2])"));
        assert!(code.contains("registers[0] = temp"));
        assert!(code.contains("memory.write_u32(registers[2], registers[1])"));
    }

    #[test]
    fn test_generate_swpb_byte_swap() {
        let inst = make_inst(
            "SWPB",
            vec![
                Operand::Register(0),
                Operand::Register(1),
                Operand::Register(2),
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("temp = memory.read_u8(registers[2])"));
        assert!(code.contains("registers[0] = temp"));
        assert!(code.contains("memory.write_u8(registers[2], registers[1] & 0xFF)"));
    }

    // === Conditional execution tests ===
    #[test]
    fn test_generate_ldr_conditional_eq() {
        let inst = make_inst(
            "LDRge",
            vec![Operand::Register(0), Operand::MemoryAddress { base: 1, offset: AddressingMode::ImmediateOffset(4), writeback: false }],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("if cpsr_check('GE'):"));
        assert!(code.contains("registers[0] = memory.read_u32(registers[1] + 4)"));
    }

    #[test]
    fn test_generate_str_conditional_ne() {
        let inst = make_inst(
            "STRne",
            vec![Operand::Register(0), Operand::MemoryAddress { base: 1, offset: AddressingMode::ImmediateOffset(4), writeback: false }],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("if cpsr_check('NE'):"));
        assert!(code.contains("memory.write_u32(registers[1] + 4, registers[0])"));
    }

    // === Register offset tests ===
    #[test]
    fn test_generate_ldr_scaled_register_offset_lsr() {
        let inst = make_inst(
            "LDR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ScaledRegisterOffset {
                        reg: 2,
                        shift: gbatopy_disasm::operand::ShiftType::Lsr,
                        amount: 4,
                    },
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[1]"));
        assert!(code.contains("registers[2] >> 4"));
        assert!(code.contains("memory.read_u32"));
    }

    #[test]
    fn test_generate_ldr_scaled_register_offset_asr() {
        let inst = make_inst(
            "LDR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ScaledRegisterOffset {
                        reg: 2,
                        shift: gbatopy_disasm::operand::ShiftType::Asr,
                        amount: 3,
                    },
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("registers[1]"));
        assert!(code.contains("registers[2] >> 3"));
        assert!(code.contains("memory.read_u32"));
    }

    // === Edge cases ===
    #[test]
    fn test_generate_ldr_zero_offset() {
        let inst = make_inst(
            "LDR",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::ImmediateOffset(0),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = memory.read_u32(registers[1] + 0)"
        );
    }

    #[test]
    fn test_generate_ldrb_with_register_offset() {
        let inst = make_inst(
            "LDRB",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::RegisterOffset(3),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "registers[0] = memory.read_u8(registers[1] + registers[3]) & 0xFF"
        );
    }

    #[test]
    fn test_generate_strb_with_register_offset() {
        let inst = make_inst(
            "STRB",
            vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: AddressingMode::RegisterOffset(3),
                    writeback: false,
                },
            ],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert_eq!(
            code,
            "memory.write_u8(registers[1] + registers[3], registers[0] & 0xFF)"
        );
    }

    // === LDM writeback tests ===
    #[test]
    fn test_generate_ldmfd_writeback_base_in_list() {
        let inst = make_inst(
            "LDMFD",
            vec![Operand::MemoryAddress {
                base: 13,
                offset: AddressingMode::Multi {
                    base: 13,
                    registers: vec![13, 14, 15],
                    increment: true,
                    pre_index: false,
                    writeback: true,
                    s_bit: false,
                },
                writeback: true,
            }],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(code.contains("_orig_base = registers[13]"));
        assert!(code.contains("registers[13] = _orig_base + 12"));
    }

    #[test]
    fn test_generate_stmia_writeback_base_not_in_list() {
        let inst = make_inst(
            "STMIA",
            vec![Operand::MemoryAddress {
                base: 13,
                offset: AddressingMode::Multi {
                    base: 13,
                    registers: vec![4, 5, 6],
                    increment: true,
                    pre_index: false,
                    writeback: true,
                    s_bit: false,
                },
                writeback: true,
            }],
            ArmMode::Arm,
            0x08000000,
        );
        let code = generate(&inst).unwrap();
        assert!(!code.contains("_orig_base"));
        assert!(code.contains("registers[13] = registers[13] + 12"));
    }
}
