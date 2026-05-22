use gbatopy_disasm::{operand::ShiftAmount, DecodedInstruction, Operand};

/// Convert ARM shift operator to Python operator
fn shift_to_python(
    reg: u8,
    shift_type: &gbatopy_disasm::operand::ShiftType,
    amount: &ShiftAmount,
) -> String {
    let amt = match amount {
        ShiftAmount::Immediate(n) => *n,
        _ => 0,
    };

    match shift_type {
        gbatopy_disasm::operand::ShiftType::Lsl => format!("r{} << {}", reg, amt),
        gbatopy_disasm::operand::ShiftType::Lsr => format!("r{} >> {}", reg, amt),
        gbatopy_disasm::operand::ShiftType::Asr => format!("r{} >> {}", reg, amt),
        gbatopy_disasm::operand::ShiftType::Ror => {
            format!(
                "(r{} >> {}) | (r{} << (32 - {})) & 0xFFFFFFFF",
                reg, amt, reg, amt
            )
        }
    }
}

/// Generate Python code from a decoded ARM/Thumb instruction
pub fn generate_instruction_python(inst: &DecodedInstruction) -> String {
    let opcode = &inst.opcode;
    let ops = &inst.operands;

    // Remove condition suffix from opcode (eq, ne, cs, cc, etc.)
    let base_opcode = opcode.split_whitespace().next().unwrap_or(opcode);
    let base_opcode = base_opcode
        .trim_end_matches("eq")
        .trim_end_matches("ne")
        .trim_end_matches("cs")
        .trim_end_matches("cc")
        .trim_end_matches("hs")
        .trim_end_matches("lo")
        .trim_end_matches("mi")
        .trim_end_matches("pl")
        .trim_end_matches("vs")
        .trim_end_matches("vc")
        .trim_end_matches("hi")
        .trim_end_matches("ls")
        .trim_end_matches("ge")
        .trim_end_matches("lt")
        .trim_end_matches("gt")
        .trim_end_matches("le")
        .trim_end_matches("al");

    eprintln!(
        "DEBUG: addr=0x{:08X} opcode=\"{}\" ops={:?} len={}",
        inst.address,
        base_opcode,
        ops,
        ops.len()
    );

    // Generate Python based on opcode type
    match base_opcode {
        // MOV Rd, #imm
        "MOV" => {
            eprintln!("DEBUG MOV: ops.len()={}, ops={:?}", ops.len(), ops);
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Immediate(imm) = ops[1] {
                        return format!("r{} = {}", rd, imm);
                    } else if let Operand::Register(rm) = ops[1] {
                        return format!("r{} = r{}", rd, rm);
                    }
                }
            }
        }
        // ADD Rd, Rn, #imm or Rm
        "ADD" => {
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Immediate(imm) = ops[1] {
                        return format!("r{} = (r{} + {}) & 0xFFFFFFFF", rd, rd, imm);
                    }
                }
            }
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Immediate(imm) = ops[2] {
                            return format!("r{} = (r{} + {}) & 0xFFFFFFFF", rd, rn, imm);
                        } else if let Operand::Register(rm) = ops[2] {
                            return format!("r{} = (r{} + r{}) & 0xFFFFFFFF", rd, rn, rm);
                        } else if let Operand::ShiftedRegister { reg, shift, amount } = &ops[2] {
                            let shift_expr = match (shift, amount) {
                                (
                                    gbatopy_disasm::operand::ShiftType::Lsl,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} << {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Lsr,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} >> {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Asr,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} >> {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Ror,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!(
                                        "(r{} >> {}) | (r{} << (32 - {})) & 0xFFFFFFFF",
                                        reg, n, reg, n
                                    )
                                }
                                _ => format!("r{}", reg),
                            };
                            return format!("r{} = (r{} + {}) & 0xFFFFFFFF", rd, rn, shift_expr);
                        }
                    }
                }
            }
        }
        // SUB Rd, Rn, #imm or Rm
        "SUB" => {
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Immediate(imm) = ops[1] {
                        return format!("r{} = (r{} - {}) & 0xFFFFFFFF", rd, rd, imm);
                    }
                }
            }
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Immediate(imm) = ops[2] {
                            return format!("r{} = (r{} - {}) & 0xFFFFFFFF", rd, rn, imm);
                        } else if let Operand::Register(rm) = ops[2] {
                            return format!("r{} = (r{} - r{}) & 0xFFFFFFFF", rd, rn, rm);
                        } else if let Operand::ShiftedRegister { reg, shift, amount } = &ops[2] {
                            let shift_expr = match (shift, amount) {
                                (
                                    gbatopy_disasm::operand::ShiftType::Lsl,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} << {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Lsr,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} >> {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Asr,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} >> {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Ror,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!(
                                        "(r{} >> {}) | (r{} << (32 - {})) & 0xFFFFFFFF",
                                        reg, n, reg, n
                                    )
                                }
                                _ => format!("r{}", reg),
                            };
                            return format!("r{} = (r{} - {}) & 0xFFFFFFFF", rd, rn, shift_expr);
                        }
                    }
                }
            }
        }
        // ADC Rd, Rn, Rm - Add with Carry
        "ADC" => {
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Register(rm) = ops[2] {
                            return format!("r{} = (r{} + r{} + cpsr_c) & 0xFFFFFFFF", rd, rn, rm);
                        }
                    }
                }
            }
        }
        // SBC Rd, Rn, Rm - Subtract with Carry
        "SBC" => {
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Register(rm) = ops[2] {
                            return format!(
                                "r{} = (r{} - r{} + cpsr_c - 1) & 0xFFFFFFFF",
                                rd, rn, rm
                            );
                        }
                    }
                }
            }
        }
        // RSC Rd, Rn, Rm - Reverse Subtract with Carry
        "RSC" => {
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Register(rm) = ops[2] {
                            return format!(
                                "r{} = (r{} - r{} - cpsr_c + 1) & 0xFFFFFFFF",
                                rd, rn, rm
                            );
                        }
                    }
                }
            }
        }
        // RSB Rd, Rn, #imm or Rm - Reverse Subtract (operand2 - operand1)
        "RSB" => {
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Immediate(imm) = ops[1] {
                        return format!("r{} = ({imm} - r{}) & 0xFFFFFFFF", rd, rd);
                    }
                }
            }
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Immediate(imm) = ops[2] {
                            return format!("r{} = ({imm} - r{}) & 0xFFFFFFFF", rd, rn);
                        } else if let Operand::Register(rm) = ops[2] {
                            return format!("r{} = (r{} - r{}) & 0xFFFFFFFF", rd, rm, rn);
                        }
                    }
                }
            }
        }
        // AND, EOR, ORR, BIC
        "AND" | "EOR" | "ORR" | "BIC" => {
            // Case 1: 2 operands - Rd, #imm
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Immediate(val) = ops[1] {
                        let op = match base_opcode {
                            "AND" => "&",
                            "EOR" => "^",
                            "ORR" => "|",
                            "BIC" => "& ~",
                            _ => "&",
                        };
                        return format!("r{} = (r{} {} {}) & 0xFFFFFFFF", rd, rd, op, val);
                    }
                }
            }
            // Case 2: 3 operands - Rd, Rn, Rm or Rd, Rn, #imm
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        let rm_expr = match &ops[2] {
                            Operand::Register(rm) => format!("r{}", rm),
                            Operand::Immediate(val) => val.to_string(),
                            Operand::ShiftedRegister { reg, shift, amount } => {
                                let shift_expr = match (shift, amount) {
                                    (
                                        gbatopy_disasm::operand::ShiftType::Lsl,
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                    ) => {
                                        format!("r{} << {}", reg, n)
                                    }
                                    (
                                        gbatopy_disasm::operand::ShiftType::Lsr,
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                    ) => {
                                        format!("r{} >> {}", reg, n)
                                    }
                                    (
                                        gbatopy_disasm::operand::ShiftType::Asr,
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                    ) => {
                                        format!("r{} >> {}", reg, n)
                                    }
                                    (
                                        gbatopy_disasm::operand::ShiftType::Ror,
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                    ) => {
                                        format!(
                                            "(r{} >> {}) | (r{} << (32 - {})) & 0xFFFFFFFF",
                                            reg, n, reg, n
                                        )
                                    }
                                    _ => format!("r{}", reg),
                                };
                                shift_expr
                            }
                            _ => "0".to_string(),
                        };
                        let op = match base_opcode {
                            "AND" => "&",
                            "EOR" => "^",
                            "ORR" => "|",
                            "BIC" => "& ~",
                            _ => "&",
                        };
                        return format!("r{} = (r{} {} {}) & 0xFFFFFFFF", rd, rn, op, rm_expr);
                    }
                }
            }
        }
        // MVN Rd, Rm
        "MVN" if ops.len() == 2 => {
            if let Operand::Register(rd) = ops[0] {
                if let Operand::Register(rm) = ops[1] {
                    return format!("r{} = (~r{}) & 0xFFFFFFFF", rd, rm);
                }
            }
        }
        // ADD Rd, Rn, #imm - Add immediate
        "B" | "BL" => {
            if ops.len() == 1 {
                if let Operand::Immediate(target) = ops[0] {
                    // The disassembler already returns the ABSOLUTE target address
                    // (PC + 4) + (sign_extend(offset) * 4) - no need to recalculate!
                    if base_opcode == "BL" {
                        // BL: Link register to return address (PC + 4)
                        let pc_next = inst.address + 4;
                        return format!("r14, r15 = {}, {}", pc_next, target);
                    } else {
                        // B: Unconditional branch
                        return format!("r15 = {}", target);
                    }
                }
            }
            return format!("# {} (parsing failed)", base_opcode);
        }
        "BX" => {
            // BX: Branch exchange (branch to address in register)
            if ops.len() == 1 {
                if let Operand::Register(rn) = ops[0] {
                    return format!("r15 = {}\n# Branch exchange", rn);
                }
            }
            return format!("# BX (parsing failed)");
        }
        // LDR Rd, [Rn, #offset] - Load word from memory
        "LDR" => {
            // Case 1: 2 operands - LDR Rd, [Rn, offset]
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    // Case 1a: LDR Rd, #imm (pseudo-instruction - load immediate value)
                    if let Operand::Immediate(val) = ops[1] {
                        return format!("r{} = {}", rd, val);
                    }
                    // Case 1b: LDR Rd, [Rn, offset]
                    if let Operand::MemoryAddress {
                        base: rn, offset, ..
                    } = &ops[1]
                    {
                        let offset_expr = match offset {
                            gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => {
                                if *val == 0 {
                                    String::new()
                                } else {
                                    format!(" + {}", val)
                                }
                            }
                            gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                                format!(" + r{}", reg)
                            }
                            gbatopy_disasm::operand::AddressingMode::ScaledRegisterOffset {
                                reg,
                                shift,
                                amount: _,
                            } => {
                                let shift_op = match shift {
                                    gbatopy_disasm::operand::ShiftType::Lsl => " << 1",
                                    gbatopy_disasm::operand::ShiftType::Lsr => " >> 1",
                                    gbatopy_disasm::operand::ShiftType::Asr => " >> 1",
                                    gbatopy_disasm::operand::ShiftType::Ror => " >> 1",
                                };
                                format!(" + (r{}{})", reg, shift_op)
                            }
                            gbatopy_disasm::operand::AddressingMode::PreIndexed {
                                base,
                                offset: _,
                                writeback: _,
                            } => {
                                format!(" + r{} /* PreIndexed */", base)
                            }
                            gbatopy_disasm::operand::AddressingMode::PostIndexed {
                                base,
                                offset: _,
                                writeback: _,
                            } => {
                                format!(" + r{} /* PostIndexed */", base)
                            }
                            gbatopy_disasm::operand::AddressingMode::Multi { .. } => {
                                " /* Multi-addressing */".to_string()
                            }
                        };
                        return format!("r{} = memory.read_32(r{}{})", rd, rn, offset_expr);
                    }
                }
            }
            // Case 2: 3 operands - LDR Rd, [Rn, Rm] or LDR Rd, [Rn, Rm, LSL #n]
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        let op2_expr = match &ops[2] {
                            Operand::Register(rm) => format!("r{}", rm),
                            Operand::ShiftedRegister { reg, shift, amount } => {
                                shift_to_python(*reg, shift, amount)
                            }
                            _ => "0".to_string(),
                        };
                        return format!("r{} = memory.read_32(r{} + {})", rd, rn, op2_expr);
                    }
                }
            }
            eprintln!(
                "WARNING: LDR failed - ops.len={}, ops[0]={:?}, ops[1]={:?}",
                ops.len(),
                ops.get(0),
                ops.get(1)
            );
            return format!("# LDR (parsing failed)");
        }
        // STR Rd, [Rn, #offset] - Store word to memory
        "STR" => {
            // Case 1: 2 operands - STR Rd, [Rn, offset]
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress {
                        base: rn, offset, ..
                    } = &ops[1]
                    {
                        let offset_expr = match offset {
                            gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => {
                                if *val == 0 {
                                    String::new()
                                } else {
                                    format!(" + {}", val)
                                }
                            }
                            gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                                format!(" + r{}", reg)
                            }
                            gbatopy_disasm::operand::AddressingMode::ScaledRegisterOffset {
                                reg,
                                shift,
                                amount: _,
                            } => {
                                let shift_op = match shift {
                                    gbatopy_disasm::operand::ShiftType::Lsl => " << 1",
                                    gbatopy_disasm::operand::ShiftType::Lsr => " >> 1",
                                    gbatopy_disasm::operand::ShiftType::Asr => " >> 1",
                                    gbatopy_disasm::operand::ShiftType::Ror => " >> 1",
                                };
                                format!(" + (r{}{})", reg, shift_op)
                            }
                            gbatopy_disasm::operand::AddressingMode::PreIndexed {
                                base,
                                offset: _,
                                writeback: _,
                            } => {
                                format!(" + r{} /* PreIndexed */", base)
                            }
                            gbatopy_disasm::operand::AddressingMode::PostIndexed {
                                base,
                                offset: _,
                                writeback: _,
                            } => {
                                format!(" + r{} /* PostIndexed */", base)
                            }
                            gbatopy_disasm::operand::AddressingMode::Multi { .. } => {
                                " /* Multi-addressing */".to_string()
                            }
                        };
                        return format!("memory.write_u32(r{}{}, r{})", rn, offset_expr, rd);
                    }
                }
            }
            // Case 2: 3 operands - STR Rd, [Rn, Rm] or STR Rd, [Rn, Rm, LSL #n]
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        // Third operand could be Register or ShiftedRegister
                        let op2_expr = match &ops[2] {
                            Operand::Register(rm) => format!("r{}", rm),
                            Operand::ShiftedRegister { reg, shift, amount } => {
                                shift_to_python(*reg, shift, amount)
                            }
                            _ => "0".to_string(),
                        };
                        return format!("memory.write_u32(r{} + {}, r{})", rn, op2_expr, rd);
                    }
                }
            }
            eprintln!(
                "WARNING: STR failed - ops.len={}, ops[0]={:?}, ops[1]={:?}, ops[2]={:?}",
                ops.len(),
                ops.get(0),
                ops.get(1),
                ops.get(2)
            );
            return format!("# STR (parsing failed)");
        }
        // LDM/STM - Block transfer (not implemented yet)
        "LDM" | "STM" => {
            // LDM/STM: Load/Store Multiple registers
            // Format: LDM{mode}{!} Rn, {reglist} or STM{mode}{!} Rn, {reglist}
            // Modes: IA (Increment After), DB (Decrement Before), IB (Increment Before), DA (Decrement After)

            if ops.len() != 1 {
                return format!("# {} (parsing failed: expected 1 operand)", base_opcode);
            }

            let is_load = base_opcode == "LDM";

            // Extract memory address info
            if let Operand::MemoryAddress {
                base: rn,
                offset: addr_mode,
                writeback,
            } = &ops[0]
            {
                // Check if this is a Multi addressing mode (LDM/STM)
                if let gbatopy_disasm::operand::AddressingMode::Multi {
                    base,
                    registers,
                    increment,
                    writeback: wb,
                } = addr_mode
                {
                    if registers.is_empty() {
                        return format!("# {} (parsing failed: empty register list)", base_opcode);
                    }

                    let base_reg = format!("r{}", base);
                    let mut code = String::new();
                    let mut addr_expr = base_reg.clone();

                    // Determine addressing mode behavior
                    let is_increment = *increment;
                    let do_writeback = *wb;

                    // Calculate starting address based on mode
                    if !is_increment && registers.len() > 0 {
                        // DB or DA: decrement before loading/storing
                        let decrement = (registers.len() - 1) * 4;
                        addr_expr = format!("({} - {})", base_reg, decrement);
                    }

                    // Generate load/store operations for each register
                    let mut current_addr = addr_expr.clone();
                    for (i, reg) in registers.iter().enumerate() {
                        if is_load {
                            // LDM: load from memory to register
                            if i > 0 && is_increment {
                                current_addr = format!("addr + {}", i * 4);
                            } else if i > 0 && !is_increment {
                                // For DB/DA, we already calculated starting address
                                current_addr = format!("addr + {}", i * 4);
                            }
                            code.push_str(&format!(
                                "r{} = memory.read_u32({}); ",
                                reg, current_addr
                            ));
                        } else {
                            // STM: store from register to memory
                            if i > 0 && is_increment {
                                current_addr = format!("addr + {}", i * 4);
                            } else if i > 0 && !is_increment {
                                current_addr = format!("addr + {}", i * 4);
                            }
                            code.push_str(&format!(
                                "memory.write_u32({}, r{}); ",
                                current_addr, reg
                            ));
                        }
                    }

                    // Handle writeback
                    if do_writeback {
                        let final_offset = if is_increment {
                            registers.len() * 4
                        } else {
                            registers.len() * 4
                        };
                        let final_addr = if is_increment {
                            format!("addr + {}", final_offset)
                        } else {
                            format!("addr + {}", final_offset)
                        };
                        code.push_str(&format!("{} = {};", base_reg, final_addr));
                    }

                    // Add address initialization
                    let init_addr = if !is_increment && registers.len() > 0 {
                        let decrement = (registers.len() - 1) * 4;
                        format!("addr = ({} - {}); ", base_reg, decrement)
                    } else {
                        format!("addr = {}; ", base_reg)
                    };

                    return format!("{}{}", init_addr, code);
                }
            }

            return format!("# {} (parsing failed)", base_opcode);
        }
        "STRB" => {
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress {
                        base: rn, offset, ..
                    } = &ops[1]
                    {
                        let offset_val = match offset {
                            gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => *val,
                            _ => 0,
                        };
                        return format!(
                            "memory.write_u8(r{} + {}, r{} & 0xFF)",
                            rn, offset_val, rd
                        );
                    }
                }
            }
            // Case 2: 3 operands - STRB Rt, [Rn, Rm] or STRB Rt, [Rn, #imm]
            if ops.len() == 3 {
                if let Operand::Register(rt) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        let offset_expr = match &ops[2] {
                            Operand::Register(rm) => format!("r{}", rm),
                            Operand::Immediate(val) => val.to_string(),
                            _ => "0".to_string(),
                        };
                        return format!(
                            "memory.write_u8(r{} + {}, r{} & 0xFF)",
                            rn, offset_expr, rt
                        );
                    }
                }
            }
            return format!("# STRB (parsing failed)");
        }
        "LDRB" => {
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress {
                        base: rn, offset, ..
                    } = &ops[1]
                    {
                        let offset_val = match offset {
                            gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => *val,
                            _ => 0,
                        };
                        return format!(
                            "r{} = memory.read_u8(r{} + {}) & 0xFF",
                            rd, rn, offset_val
                        );
                    }
                }
            }
            // Case 2: 3 operands - LDRB Rt, [Rn, Rm] or LDRB Rt, [Rn, #imm]
            if ops.len() == 3 {
                if let Operand::Register(rt) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        let offset_expr = match &ops[2] {
                            Operand::Register(rm) => format!("r{}", rm),
                            Operand::Immediate(val) => val.to_string(),
                            _ => "0".to_string(),
                        };
                        return format!(
                            "r{} = memory.read_u8(r{} + {}) & 0xFF",
                            rt, rn, offset_expr
                        );
                    }
                }
            }
            return format!("# LDRB (parsing failed)");
        }
        "STRH" => {
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress {
                        base: rn, offset, ..
                    } = &ops[1]
                    {
                        let offset_val = match offset {
                            gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => *val,
                            _ => 0,
                        };
                        return format!(
                            "memory.write_u16(r{} + {}, r{} & 0xFFFF)",
                            rn, offset_val, rd
                        );
                    }
                }
            }
            return format!("# STRH (parsing failed)");
        }
        "LDRH" => {
            // Case 1: 2 operands - LDRH Rd, [Rn, offset]
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress {
                        base: rn, offset, ..
                    } = &ops[1]
                    {
                        let offset_expr = match offset {
                            gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => {
                                if *val == 0 {
                                    String::new()
                                } else {
                                    format!(" + {}", val)
                                }
                            }
                            gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                                format!(" + r{}", reg)
                            }
                            gbatopy_disasm::operand::AddressingMode::ScaledRegisterOffset {
                                reg,
                                shift,
                                amount: _,
                            } => {
                                let shift_op = match shift {
                                    gbatopy_disasm::operand::ShiftType::Lsl => " << 1",
                                    gbatopy_disasm::operand::ShiftType::Lsr => " >> 1",
                                    gbatopy_disasm::operand::ShiftType::Asr => " >> 1",
                                    gbatopy_disasm::operand::ShiftType::Ror => " >> 1",
                                };
                                format!(" + (r{}{})", reg, shift_op)
                            }
                            gbatopy_disasm::operand::AddressingMode::PreIndexed {
                                base,
                                offset: _,
                                writeback: _,
                            } => {
                                format!(" + r{} /* PreIndexed */", base)
                            }
                            gbatopy_disasm::operand::AddressingMode::PostIndexed {
                                base,
                                offset: _,
                                writeback: _,
                            } => {
                                format!(" + r{} /* PostIndexed */", base)
                            }
                            _ => {
                                eprintln!("WARNING: LDRH unhandled offset type: {:?}", offset);
                                String::new()
                            }
                        };
                        return format!(
                            "r{} = memory.read_16(r{}{}) & 0xFFFF",
                            rd, rn, offset_expr
                        );
                    }
                }
            }
            // Case 2: 3 operands - LDRH Rd, [Rn, Rm]
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        let op2_expr = match &ops[2] {
                            Operand::Register(rm) => format!("r{}", rm),
                            Operand::ShiftedRegister { reg, shift, amount } => {
                                shift_to_python(*reg, shift, amount)
                            }
                            _ => "0".to_string(),
                        };
                        return format!(
                            "r{} = memory.read_16(r{} + {}) & 0xFFFF",
                            rd, rn, op2_expr
                        );
                    }
                }
            }
            eprintln!(
                "WARNING: LDRH failed - ops.len={}, ops[0]={:?}, ops[1]={:?}",
                ops.len(),
                ops.get(0),
                ops.get(1)
            );
            return format!("# LDRH (parsing failed)");
        }
        // LDRSB Rd, [Rn, offset] - Load Signed Byte
        "LDRSB" => {
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress {
                        base: rn, offset, ..
                    } = &ops[1]
                    {
                        let offset_expr = match offset {
                            gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => {
                                if *val == 0 {
                                    String::new()
                                } else {
                                    format!(" + {}", val)
                                }
                            }
                            gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                                format!(" + r{}", reg)
                            }
                            _ => String::new(),
                        };
                        return format!("r{} = memory.read_s8(r{}{}) & 0xFF", rd, rn, offset_expr);
                    }
                }
            }
            return format!("# LDRSB (parsing failed)");
        }
        // LDRSH Rd, [Rn, offset] - Load Signed Halfword
        "LDRSH" => {
            if ops.len() == 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress {
                        base: rn, offset, ..
                    } = &ops[1]
                    {
                        let offset_expr = match offset {
                            gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => {
                                if *val == 0 {
                                    String::new()
                                } else {
                                    format!(" + {}", val)
                                }
                            }
                            gbatopy_disasm::operand::AddressingMode::RegisterOffset(reg) => {
                                format!(" + r{}", reg)
                            }
                            _ => String::new(),
                        };
                        return format!(
                            "r{} = memory.read_s16(r{}{}) & 0xFFFF",
                            rd, rn, offset_expr
                        );
                    }
                }
            }
            return format!("# LDRSH (parsing failed)");
        }
        // Multiply instructions
        "MUL" | "MLA" | "UMULL" | "SMULL" | "UMLAL" | "SMLAL" => {
            // MUL Rd, Rm, Rs - Rd = Rm * Rs
            if base_opcode == "MUL" || base_opcode == "MLA" {
                if ops.len() >= 3 {
                    if let Operand::Register(rd) = ops[0] {
                        let rm = if let Operand::Register(rm) = ops[1] {
                            format!("r{}", rm)
                        } else {
                            "0".to_string()
                        };
                        let rs = if let Operand::Register(rs) = ops[2] {
                            format!("r{}", rs)
                        } else {
                            "0".to_string()
                        };
                        let acc = if base_opcode == "MLA" && ops.len() >= 4 {
                            if let Operand::Register(acc) = ops[3] {
                                format!("r{}", acc)
                            } else {
                                "0".to_string()
                            }
                        } else {
                            "0".to_string()
                        };
                        return format!("r{} = ({} * {} + {}) & 0xFFFFFFFF", rd, rm, rs, acc);
                    }
                }
            }
            // UMULL/SMULL/UMLAL/SMLAL - 64-bit multiply
            // Store low 32 bits in RLo, high 32 bits in RHi
            if (base_opcode == "UMULL" || base_opcode == "SMULL") && ops.len() >= 4 {
                if let Operand::Register(rlo) = ops[0] {
                    if let Operand::Register(rhi) = ops[1] {
                        let rm = if let Operand::Register(rm) = ops[2] {
                            format!("r{}", rm)
                        } else {
                            "0".to_string()
                        };
                        let rs = if let Operand::Register(rs) = ops[3] {
                            format!("r{}", rs)
                        } else {
                            "0".to_string()
                        };
                        let signed = base_opcode == "SMULL";
                        return format!(
                            "result = ({}) * ({}); r{} = result & 0xFFFFFFFF; r{} = (result >> 32) & 0xFFFFFFFF",
                            rm, rs, rlo, rhi
                        );
                    }
                }
            }
            // Fallback for UMLAL/SMLAL or parsing failures
            return format!(
                "# {} (64-bit multiply accumulate not fully implemented)",
                base_opcode
            );
        }
        "SWP" | "SWPB" => {
            if ops.len() == 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rm) = ops[1] {
                        if let Operand::Register(rn) = ops[2] {
                            let byte = base_opcode == "SWPB";
                            return format!(
                                    "temp = memory.read_u8(r{}) if {} else memory.read_u32(r{}); r{} = temp; memory.write_u8(r{}, r{}) if {} else memory.write_u32(r{}, r{})",
                                    rn, byte, rn, rd, rn, rm, byte, rn, rm
                                );
                        }
                    }
                }
            }
            return format!("# SWP parsing failed");
        }
        "MRS" => {
            // MRS Rd, CPSR/SPSR
            if ops.len() >= 2 {
                if let Operand::Register(rd) = ops[0] {
                    return format!("r{} = cpsr", rd);
                }
            }
            return format!("# MRS parsing failed");
        }
        "MSR" => {
            // MSR CPSR/SPSR, Operand
            if ops.len() >= 2 {
                let operand = match &ops[1] {
                    Operand::Immediate(val) => val.to_string(),
                    Operand::Register(rm) => format!("r{}", rm),
                    _ => "0".to_string(),
                };
                return format!("cpsr = {}", operand);
            }
            return format!("# MSR parsing failed");
        }
        "CLZ" => {
            // CLZ Rd, Rm - Count Leading Zeros
            if ops.len() >= 3 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rm) = ops[1] {
                        return format!(
                            "r{} = (32 - (r{}).bit_length()) if r{} != 0 else 32",
                            rd, rm, rm
                        );
                    }
                }
            }
            return format!("# CLZ parsing failed");
        }
        "CMP" => {
            // CMP Rn, Operand2 - Compare Rn with Operand2, set flags
            // Can have 2 or 3 operands depending on encoding
            if ops.len() >= 2 {
                let (rn, op2) = if ops.len() >= 3 {
                    // 3 operands: CMP Rd, Rn, Operand2 (Rd is unused, Rn is ops[1])
                    if let Operand::Register(rn) = ops[1] {
                        let op2 = match &ops[2] {
                            Operand::Immediate(val) => val.to_string(),
                            Operand::Register(rm) => format!("r{}", rm),
                            Operand::ShiftedRegister { reg, shift, amount } => {
                                shift_to_python(*reg, shift, amount)
                            }
                            _ => "0".to_string(),
                        };
                        (format!("r{}", rn), op2)
                    } else {
                        ("0".to_string(), "0".to_string())
                    }
                } else {
                    // 2 operands: CMP Rn, Operand2 (Thumb or simplified ARM)
                    // ops[0] = Rn, ops[1] = Operand2
                    let rn = if let Operand::Register(rn) = ops[0] {
                        format!("r{}", rn)
                    } else {
                        "0".to_string()
                    };
                    let op2 = if let Operand::Immediate(val) = ops[1] {
                        val.to_string()
                    } else if let Operand::Register(rm) = ops[1] {
                        format!("r{}", rm)
                    } else {
                        "0".to_string()
                    };
                    (rn, op2)
                };
                if rn != "0" || op2 != "0" {
                    return format!(
                        "result = {} - {}; flags = compute_flags(result, 32)",
                        rn, op2
                    );
                }
            }
            eprintln!("WARNING: CMP failed - ops.len={}, ops={:?}", ops.len(), ops);
            return format!("# CMP (parsing failed)");
        }
        "CMN" => {
            if ops.len() >= 3 {
                if let Operand::Register(rn) = ops[1] {
                    let op2_expr = match &ops[2] {
                        Operand::Immediate(val) => val.to_string(),
                        Operand::Register(rm) => format!("r{}", rm),
                        Operand::ShiftedRegister { reg, shift, amount } => {
                            shift_to_python(*reg, shift, amount)
                        }
                        _ => "0".to_string(),
                    };
                    return format!(
                        "result = r{} + {}; flags = compute_flags(result, 32)",
                        rn, op2_expr
                    );
                }
            }
            // Case 2: 2 operands - CMN Rn, #imm or CMN Rn, Rm
            if ops.len() == 2 {
                if let Operand::Register(rn) = ops[0] {
                    let op2_expr = match &ops[1] {
                        Operand::Immediate(val) => val.to_string(),
                        Operand::Register(rm) => format!("r{}", rm),
                        Operand::ShiftedRegister { reg, shift, amount } => {
                            let shift_expr = match (shift, amount) {
                                (
                                    gbatopy_disasm::operand::ShiftType::Lsl,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} << {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Lsr,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} >> {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Asr,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} >> {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Ror,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!(
                                        "(r{} >> {}) | (r{} << (32 - {})) & 0xFFFFFFFF",
                                        reg, n, reg, n
                                    )
                                }
                                _ => format!("r{}", reg),
                            };
                            shift_expr
                        }
                        _ => "0".to_string(),
                    };
                    return format!(
                        "result = r{} + {}; flags = compute_flags(result, 32)",
                        rn, op2_expr
                    );
                }
            }
            return format!("# CMN (parsing failed)");
        }
        "TST" => {
            if ops.len() >= 3 {
                if let Operand::Register(rn) = ops[1] {
                    let op2_expr = match &ops[2] {
                        Operand::Immediate(val) => val.to_string(),
                        Operand::Register(rm) => format!("r{}", rm),
                        Operand::ShiftedRegister { reg, shift, amount } => {
                            let shift_expr = match (shift, amount) {
                                (
                                    gbatopy_disasm::operand::ShiftType::Lsl,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} << {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Lsr,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} >> {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Asr,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!("r{} >> {}", reg, n)
                                }
                                (
                                    gbatopy_disasm::operand::ShiftType::Ror,
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n),
                                ) => {
                                    format!(
                                        "(r{} >> {}) | (r{} << (32 - {})) & 0xFFFFFFFF",
                                        reg, n, reg, n
                                    )
                                }
                                _ => format!("r{}", reg),
                            };
                            shift_expr
                        }
                        _ => "0".to_string(),
                    };
                    return format!(
                        "result = r{} & {}; flags = compute_flags(result, 32)",
                        rn, op2_expr
                    );
                }
            }
            // Case 2: 2 operands - TST Rn, #imm or TST Rn, Rm
            if ops.len() == 2 {
                if let Operand::Register(rn) = ops[0] {
                    let op2_expr = match &ops[1] {
                        Operand::Immediate(val) => val.to_string(),
                        Operand::Register(rm) => format!("r{}", rm),
                        Operand::ShiftedRegister { reg, shift, amount } => {
                            shift_to_python(*reg, shift, amount)
                        }
                        _ => "0".to_string(),
                    };
                    return format!(
                        "result = r{} & {}; flags = compute_flags(result, 32)",
                        rn, op2_expr
                    );
                }
            }
            return format!("# TST (parsing failed)");
        }
        "TEQ" => {
            if ops.len() >= 3 {
                if let Operand::Register(rn) = ops[1] {
                    let op2_expr = match &ops[2] {
                        Operand::Immediate(val) => val.to_string(),
                        Operand::Register(rm) => format!("r{}", rm),
                        Operand::ShiftedRegister { reg, shift, amount } => {
                            shift_to_python(*reg, shift, amount)
                        }
                        _ => "0".to_string(),
                    };
                    return format!(
                        "result = r{} ^ {}; flags = compute_flags(result, 32)",
                        rn, op2_expr
                    );
                }
            }
            // Case 2: 2 operands - TEQ Rn, #imm or TEQ Rn, Rm
            if ops.len() == 2 {
                if let Operand::Register(rn) = ops[0] {
                    let op2_expr = match &ops[1] {
                        Operand::Immediate(val) => val.to_string(),
                        Operand::Register(rm) => format!("r{}", rm),
                        Operand::ShiftedRegister { reg, shift, amount } => {
                            shift_to_python(*reg, shift, amount)
                        }
                        _ => "0".to_string(),
                    };
                    return format!(
                        "result = r{} ^ {}; flags = compute_flags(result, 32)",
                        rn, op2_expr
                    );
                }
            }
            return format!("# TEQ (parsing failed)");
        }
        _ => {
            // Fallback to comment for unimplemented opcodes
            let ops_str = ops
                .iter()
                .map(|op| format!("{:?}", op))
                .collect::<Vec<_>>()
                .join(", ");
            return format!("# {} {}", base_opcode, ops_str);
        }
    }

    // Default fallback
    let ops_str = ops
        .iter()
        .map(|op| format!("{:?}", op))
        .collect::<Vec<_>>()
        .join(", ");
    format!("# {} {}", base_opcode, ops_str)
}
