use gbatopy_disasm::Disassembler;
use std::fs;
use std::path::Path;

pub fn run_pipeline(
    rom_path: &str,
    output_path: &str,
    _assets_dir: &Path,
    _use_ir: bool,
) -> Result<(), String> {
    let rom = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    eprintln!("Step 1: Disassembly");
    let mut disasm = Disassembler::new();
    let instructions = disasm.disassemble(&rom, 0x08000000);
    eprintln!("  Disassembled {} instructions", instructions.len());

    eprintln!("Step 2: Asset Extraction");
    eprintln!("  (Asset extraction skipped - not implemented yet)");

    eprintln!("Step 3: Python Code Generation (direct from disassembly)");

    // TWO-PASS ALGORITHM for func_map generation:
    // Pass 1: Collect all branch targets
    // Pass 2: Group instructions by function start address and generate code

    use gbatopy_disasm::Operand;

    // Generate Python directly from disassembled instructions
    let mut code = String::new();

    // Required imports
    code.push_str("import pygame\n");
    code.push_str("\n");

    code.push_str("# Global ARM registers (r0-r15, cpsr, spsr)\n");
    code.push_str("r0 = r1 = r2 = r3 = r4 = r5 = r6 = r7 = 0\n");
    code.push_str("r8 = r9 = r10 = r11 = r12 = r13 = r14 = r15 = 0\n");
    code.push_str("cpsr = 0  # Current Program Status Register\n");
    code.push_str("spsr = 0  # Saved Program Status Register\n\n");

    // PASS 1: Collect all branch targets (function start addresses)
    let mut branch_targets: std::collections::HashSet<u64> = std::collections::HashSet::new();
    for inst in &instructions {
        let opcode = &inst.opcode;
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

        match base_opcode {
            "B" | "BL" => {
                if inst.operands.len() == 1 {
                    if let Operand::Immediate(target) = inst.operands[0] {
                        branch_targets.insert(target as u64);
                    }
                }
            }
            "BX" => {
                // BX targets are dynamic (register-based), can't determine statically
                // Add current instruction + 4 as a potential target
                branch_targets.insert((inst.address + 4) as u64);
            }
            _ => {}
        }
    }

    // Add the first instruction address as the entry point
    if let Some(first) = instructions.first() {
        branch_targets.insert(first.address as u64);
    }

    eprintln!("  Found {} branch targets", branch_targets.len());

    // PASS 2: Group instructions by function start address
    let mut func_map_entries = Vec::new();
    let mut func_groups: std::collections::BTreeMap<u64, Vec<&gbatopy_disasm::DecodedInstruction>> =
        std::collections::BTreeMap::new();

    for inst in &instructions {
        // Find the nearest branch target <= this instruction's address
        let mut func_start = inst.address as u64;
        for &target in &branch_targets {
            if target <= inst.address as u64 {
                if target > func_start || func_start == inst.address as u64 {
                    func_start = target;
                }
            }
        }

        func_groups
            .entry(func_start)
            .or_insert_with(Vec::new)
            .push(inst);
    }

    eprintln!("  Generated {} functions", func_groups.len());

    // Helper function to generate Python from ARM instruction
    fn generate_python_from_instruction(inst: &gbatopy_disasm::DecodedInstruction) -> String {
        use gbatopy_disasm::Operand;

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

        // Generate Python based on opcode type
        match base_opcode {
            // MOV Rd, #imm
            "MOV" => {
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
            // ADD Rd, Rn, #imm
            "ADD" => {
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Register(rn) = ops[1] {
                            if ops.len() == 3 {
                                if let Operand::Immediate(imm) = ops[2] {
                                    return format!("r{} = (r{} + {}) & 0xFFFFFFFF", rd, rn, imm);
                                }
                            } else if let Operand::Register(rm) = ops[2] {
                                return format!("r{} = (r{} + r{}) & 0xFFFFFFFF", rd, rn, rm);
                            }
                        }
                    }
                }
            }
            // ADD Rd, Rn, Rm
            "ADD" if ops.len() == 3 => {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Register(rm) = ops[2] {
                            return format!("r{} = (r{} + r{}) & 0xFFFFFFFF", rd, rn, rm);
                        }
                    }
                }
            }
            // SUB Rd, Rn, #imm
            "SUB" => {
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Register(rn) = ops[1] {
                            if ops.len() == 3 {
                                if let Operand::Immediate(imm) = ops[2] {
                                    return format!("r{} = (r{} - {}) & 0xFFFFFFFF", rd, rn, imm);
                                }
                            }
                        }
                    }
                }
            }
            // SUB Rd, Rn, Rm
            "SUB" if ops.len() == 3 => {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rn) = ops[1] {
                        if let Operand::Register(rm) = ops[2] {
                            return format!("r{} = (r{} - r{}) & 0xFFFFFFFF", rd, rn, rm);
                        }
                    }
                }
            }
            // AND, EOR, ORR, BIC
            "AND" | "EOR" | "ORR" | "BIC" => {
                if ops.len() == 3 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Register(rn) = ops[1] {
                            if let Operand::Register(rm) = ops[2] {
                                let op = match base_opcode {
                                    "AND" => "&",
                                    "EOR" => "^",
                                    "ORR" => "|",
                                    "BIC" => "& ~",
                                    _ => "&",
                                };
                                return format!("r{} = (r{} {} r{}) & 0xFFFFFFFF", rd, rn, op, rm);
                            }
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
            // B, BL - Branch instructions
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
                                    let shift_str = match shift {
                                        gbatopy_disasm::operand::ShiftType::Lsl => "lsl",
                                        gbatopy_disasm::operand::ShiftType::Lsr => "lsr",
                                        gbatopy_disasm::operand::ShiftType::Asr => "asr",
                                        gbatopy_disasm::operand::ShiftType::Ror => "ror",
                                    };
                                    let amount_str = match amount {
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(0) => {
                                            "0".to_string()
                                        }
                                        gbatopy_disasm::operand::ShiftAmount::Register(_) => {
                                            "0".to_string()
                                        }
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(n) => {
                                            n.to_string()
                                        }
                                    };
                                    format!("r{} {} {}", reg, shift_str, amount_str)
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
                                _ => {
                                    eprintln!("WARNING: STR unhandled offset type: {:?}", offset);
                                    String::new()
                                }
                            };
                            return format!("memory.write_32(r{}{}, r{})", rn, offset_expr, rd);
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
                                    let shift_str = match shift {
                                        gbatopy_disasm::operand::ShiftType::Lsl => "lsl",
                                        gbatopy_disasm::operand::ShiftType::Lsr => "lsr",
                                        gbatopy_disasm::operand::ShiftType::Asr => "asr",
                                        gbatopy_disasm::operand::ShiftType::Ror => "ror",
                                    };
                                    let amount_str = match amount {
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(0) => {
                                            "0".to_string()
                                        }
                                        gbatopy_disasm::operand::ShiftAmount::Register(_) => {
                                            "0".to_string()
                                        }
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(n) => {
                                            n.to_string()
                                        }
                                    };
                                    format!("r{} {} {}", reg, shift_str, amount_str)
                                }
                                _ => "0".to_string(),
                            };
                            return format!("memory.write_32(r{} + {}, r{})", rn, op2_expr, rd);
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
                return format!("# {} (block transfer not implemented)", base_opcode);
            }
            "STRB" => {
                if ops.len() == 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::MemoryAddress {
                            base: rn, offset, ..
                        } = &ops[1]
                        {
                            let offset_val = match offset {
                                gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => {
                                    *val
                                }
                                _ => 0,
                            };
                            return format!(
                                "memory.write_u8(r{} + {}, r{} & 0xFF)",
                                rn, offset_val, rd
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
                                gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => {
                                    *val
                                }
                                _ => 0,
                            };
                            return format!(
                                "r{} = memory.read_u8(r{} + {}) & 0xFF",
                                rd, rn, offset_val
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
                                gbatopy_disasm::operand::AddressingMode::ImmediateOffset(val) => {
                                    *val
                                }
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
                                    let shift_str = match shift {
                                        gbatopy_disasm::operand::ShiftType::Lsl => "lsl",
                                        gbatopy_disasm::operand::ShiftType::Lsr => "lsr",
                                        gbatopy_disasm::operand::ShiftType::Asr => "asr",
                                        gbatopy_disasm::operand::ShiftType::Ror => "ror",
                                    };
                                    let amount_str = match amount {
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(0) => {
                                            "0".to_string()
                                        }
                                        gbatopy_disasm::operand::ShiftAmount::Register(_) => {
                                            "0".to_string()
                                        }
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(n) => {
                                            n.to_string()
                                        }
                                    };
                                    format!("r{} {} {}", reg, shift_str, amount_str)
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
            // Multiply instructions
            "MUL" | "MLA" | "UMULL" | "SMULL" | "UMLAL" | "SMLAL" => {
                // MUL/MLA - Multiply (operand parsing issue in disassembler, skip for now)
                return format!(
                    "# {} (multiply - needs disassembler operand fix)",
                    base_opcode
                );
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
                                    let shift_str = match shift {
                                        gbatopy_disasm::operand::ShiftType::Lsl => "lsl",
                                        gbatopy_disasm::operand::ShiftType::Lsr => "lsr",
                                        gbatopy_disasm::operand::ShiftType::Asr => "asr",
                                        gbatopy_disasm::operand::ShiftType::Ror => "ror",
                                    };
                                    let amount_str = match amount {
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(0) => {
                                            "0".to_string()
                                        }
                                        gbatopy_disasm::operand::ShiftAmount::Register(_) => {
                                            "0".to_string()
                                        }
                                        gbatopy_disasm::operand::ShiftAmount::Immediate(n) => {
                                            n.to_string()
                                        }
                                    };
                                    format!("r{} {} {}", reg, shift_str, amount_str)
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
                                let shift_str = match shift {
                                    gbatopy_disasm::operand::ShiftType::Lsl => "lsl",
                                    gbatopy_disasm::operand::ShiftType::Lsr => "lsr",
                                    gbatopy_disasm::operand::ShiftType::Asr => "asr",
                                    gbatopy_disasm::operand::ShiftType::Ror => "ror",
                                };
                                let amount_str = match amount {
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(0) => {
                                        "0".to_string()
                                    }
                                    gbatopy_disasm::operand::ShiftAmount::Register(_) => {
                                        "0".to_string()
                                    }
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n) => {
                                        n.to_string()
                                    }
                                };
                                format!("r{} {} {}", reg, shift_str, amount_str)
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
                                let shift_str = match shift {
                                    gbatopy_disasm::operand::ShiftType::Lsl => "lsl",
                                    gbatopy_disasm::operand::ShiftType::Lsr => "lsr",
                                    gbatopy_disasm::operand::ShiftType::Asr => "asr",
                                    gbatopy_disasm::operand::ShiftType::Ror => "ror",
                                };
                                let amount_str = match amount {
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(0) => {
                                        "0".to_string()
                                    }
                                    gbatopy_disasm::operand::ShiftAmount::Register(_) => {
                                        "0".to_string()
                                    }
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n) => {
                                        n.to_string()
                                    }
                                };
                                format!("r{} {} {}", reg, shift_str, amount_str)
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
                                let shift_str = match shift {
                                    gbatopy_disasm::operand::ShiftType::Lsl => "lsl",
                                    gbatopy_disasm::operand::ShiftType::Lsr => "lsr",
                                    gbatopy_disasm::operand::ShiftType::Asr => "asr",
                                    gbatopy_disasm::operand::ShiftType::Ror => "ror",
                                };
                                let amount_str = match amount {
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(0) => {
                                        "0".to_string()
                                    }
                                    gbatopy_disasm::operand::ShiftAmount::Register(_) => {
                                        "0".to_string()
                                    }
                                    gbatopy_disasm::operand::ShiftAmount::Immediate(n) => {
                                        n.to_string()
                                    }
                                };
                                format!("r{} {} {}", reg, shift_str, amount_str)
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

    // Embed ROM data FIRST (before GBA class needs it)
    code.push_str("# Full ROM data\n");
    code.push_str("ROM_DATA = bytearray([\n");
    for (i, byte) in rom.iter().enumerate() {
        if i > 0 {
            code.push_str(", ");
        }
        if i % 16 == 0 {
            code.push_str("\n    ");
        }
        code.push_str(&format!("0x{:02X}", byte));
    }
    code.push_str("\n])\n\n");

    // Embed GBA memory class (Python version)
    code.push_str(
        r#"# GBA Memory Map Implementation
# Memory layout:
# - 0x00000000-0x00003FFF: BIOS ROM (16KB)
# - 0x02000000-0x0203FFFF: EWRAM (256KB)
# - 0x03000000-0x03007FFF: IWRAM (32KB)
# - 0x04000000-0x040003FF: MMIO registers
# - 0x05000000-0x050003FF: Palette RAM (1KB)
# - 0x06000000-0x06017FFF: VRAM (96KB)
# - 0x07000000-0x070003FF: OAM (1KB)
# - 0x08000000-0x09FFFFFF: ROM (up to 32MB)

class GBA:
    def __init__(self, rom_data):
        self.bios = bytearray(0x4000)       # 16KB
        self.ewram = bytearray(0x40000)     # 256KB
        self.iwram = bytearray(0x8000)      # 32KB
        self.mmio = {}                      # MMIO registers
        self.palette = bytearray(0x400)     # 1KB
        self.vram = bytearray(0x18000)      # 96KB
        self.oam = bytearray(0x400)         # 1KB
        self.rom = rom_data                 # up to 32MB

    def read_8(self, addr):
        if 0x00000000 <= addr <= 0x00003FFF:
            offset = addr - 0x00000000
            return self.bios[offset] if offset < len(self.bios) else 0
        elif 0x02000000 <= addr <= 0x0203FFFF:
            offset = addr - 0x02000000
            return self.ewram[offset] if offset < len(self.ewram) else 0
        elif 0x03000000 <= addr <= 0x03007FFF:
            offset = addr - 0x03000000
            return self.iwram[offset] if offset < len(self.iwram) else 0
        elif 0x04000000 <= addr <= 0x040003FF:
            offset = addr - 0x04000000
            return self.mmio.get(offset, 0)
        elif 0x05000000 <= addr <= 0x050003FF:
            offset = addr - 0x05000000
            return self.palette[offset] if offset < len(self.palette) else 0
        elif 0x06000000 <= addr <= 0x06017FFF:
            offset = addr - 0x06000000
            return self.vram[offset] if offset < len(self.vram) else 0
        elif 0x07000000 <= addr <= 0x070003FF:
            offset = addr - 0x07000000
            return self.oam[offset] if offset < len(self.oam) else 0
        elif 0x08000000 <= addr <= 0x09FFFFFF:
            offset = addr - 0x08000000
            return self.rom[offset] if offset < len(self.rom) else 0
        return 0

    def read_32(self, addr):
        b0 = self.read_8(addr)
        b1 = self.read_8(addr + 1)
        b2 = self.read_8(addr + 2)
        b3 = self.read_8(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)

    def write_8(self, addr, value):
        if 0x02000000 <= addr <= 0x0203FFFF:
            offset = addr - 0x02000000
            if offset < len(self.ewram): self.ewram[offset] = value
        elif 0x03000000 <= addr <= 0x03007FFF:
            offset = addr - 0x03000000
            if offset < len(self.iwram): self.iwram[offset] = value
        elif 0x04000000 <= addr <= 0x040003FF:
            offset = addr - 0x04000000
            self.mmio[offset] = value  # MMIO side effects would be handled here
        elif 0x05000000 <= addr <= 0x050003FF:
            offset = addr - 0x05000000
            if offset < len(self.palette): self.palette[offset] = value
        elif 0x06000000 <= addr <= 0x06017FFF:
            offset = addr - 0x06000000
            if offset < len(self.vram): self.vram[offset] = value
        elif 0x07000000 <= addr <= 0x070003FF:
            offset = addr - 0x07000000
            if offset < len(self.oam): self.oam[offset] = value

    def write_32(self, addr, value):
        self.write_8(addr, value & 0xFF)
        self.write_8(addr + 1, (value >> 8) & 0xFF)
        self.write_8(addr + 2, (value >> 16) & 0xFF)
        self.write_8(addr + 3, (value >> 24) & 0xFF)

"#,
    );

    code.push_str("# Initialize GBA memory with ROM data\n");
    code.push_str("memory = GBA(ROM_DATA)\n\n");

    // Generate functions for each branch target
    for (&func_start, func_instructions) in &func_groups {
        let func_name = format!("func_{:08X}", func_start);

        code.push_str(&format!("def {}():\n", func_name));
        code.push_str(
            "    global r0, r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12, r13, r14, r15\n",
        );
        code.push_str("    global cpsr, spsr\n");

        for inst in func_instructions {
            let py_stmt = generate_python_from_instruction(inst);
            code.push_str(&format!("    {}\n", py_stmt));
        }

        code.push_str("\n");
        func_map_entries.push(format!("    0x{:08X}: {},", func_start, func_name));
    }

    // Generate func_map
    code.push_str("# Function map for dynamic dispatch\n");
    code.push_str("func_map = {\n");
    code.push_str(&func_map_entries.join("\n"));
    code.push_str("\n}\n\n");

    // Add game loop (from generate_game_loop in pipeline.rs)
    code.push_str(&generate_game_loop());

    fs::write(output_path, &code).map_err(|e| format!("Failed to write output: {}", e))?;

    println!(
        "Generated {} lines of Python to {}",
        code.lines().count(),
        output_path
    );
    Ok(())
}

// Helper function to generate game loop (copied from cmds/pipeline.rs)
fn generate_game_loop() -> String {
    r#"
def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    """Execute transpiled GBA code using func_map dispatch"""
    
    frame_count = 0
    max_instructions = 1000000  # Safety limit
    instruction_count = 0
    
    print(f"Starting transpiled execution at PC=0x{r15:08X}")
    
    # Main execution loop
    while instruction_count < max_instructions:
        pc = r15
        
        # Look up function by address
        if pc not in func_map:
            print(f"Unknown PC: 0x{pc:08X} - execution halted")
            break
        
        # Get the function and call it
        func = func_map[pc]
        func()  # This updates r15 (PC) for next instruction
        
        instruction_count += 1
        
        # If PC didn't change, we're in an infinite loop
        if r15 == pc:
            print(f"PC unchanged at 0x{pc:08X} - infinite loop detected")
            break
        
        # Progress reporting every 10000 instructions
        if instruction_count % 10000 == 0:
            print(f"Executed {instruction_count} instructions, PC=0x{r15:08X}")
        
        # Frame limit check
        if frame_limit and frame_count >= frame_limit:
            break
        
        # For now, each instruction counts as ~1 frame
        # Real implementation would count actual frame cycles
        if instruction_count % 1000 == 0:
            frame_count += 1
    
    print(f"Execution stopped after {instruction_count} instructions")
    print(f"Final PC: 0x{r15:08X}")
    
    return frame_count

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    """Run transpiled GBA code with pygame display and input"""
    
    pygame.init()
    
    if not headless:
        screen = pygame.display.set_mode((240 * scale, 160 * scale))
        pygame.display.set_caption("GBAtoPy - Transpiled GBA")
    else:
        # Create dummy surface for screenshot saving in headless mode
        screen = pygame.Surface((240 * scale, 160 * scale))
    
    clock = pygame.time.Clock()
    frame_count = 0
    running = True
    
    # Input state
    keys_down = {}
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_UP:
                    keys_down['UP'] = True
                elif event.key == pygame.K_DOWN:
                    keys_down['DOWN'] = True
                elif event.key == pygame.K_LEFT:
                    keys_down['LEFT'] = True
                elif event.key == pygame.K_RIGHT:
                    keys_down['RIGHT'] = True
                elif event.key == pygame.K_z:
                    keys_down['A'] = True
                elif event.key == pygame.K_x:
                    keys_down['B'] = True
                elif event.key == pygame.K_RETURN:
                    keys_down['START'] = True
                elif event.key == pygame.K_BACKSPACE:
                    keys_down['SELECT'] = True
                elif event.key == pygame.K_a:
                    keys_down['L'] = True
                elif event.key == pygame.K_s:
                    keys_down['R'] = True
            elif event.type == pygame.KEYUP:
                if event.key == pygame.K_UP:
                    keys_down.pop('UP', None)
                elif event.key == pygame.K_DOWN:
                    keys_down.pop('DOWN', None)
                elif event.key == pygame.K_LEFT:
                    keys_down.pop('LEFT', None)
                elif event.key == pygame.K_RIGHT:
                    keys_down.pop('RIGHT', None)
                elif event.key == pygame.K_z:
                    keys_down.pop('A', None)
                elif event.key == pygame.K_x:
                    keys_down.pop('B', None)
                elif event.key == pygame.K_RETURN:
                    keys_down.pop('START', None)
                elif event.key == pygame.K_BACKSPACE:
                    keys_down.pop('SELECT', None)
                elif event.key == pygame.K_a:
                    keys_down.pop('L', None)
                elif event.key == pygame.K_s:
                    keys_down.pop('R', None)
        
        # TODO: Render PPU framebuffer to screen
        # For now, show a placeholder
        if not headless and screen:
            screen.fill((0, 0, 0))  # Black background
            # TODO: Render actual PPU output
            pygame.display.flip()
        
        frame_count += 1
        clock.tick(60)
        
        if frame_limit and frame_count >= frame_limit:
            break
    
    # Save screenshot if requested
    if screenshot_path:
        pygame.image.save(screen, screenshot_path)
        print(f"Screenshot saved to: {screenshot_path}")
    
    pygame.quit()
    return frame_count

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GBAtoPy Transpiled GBA")
    parser.add_argument("--headless", action="store_true", help="Run without display")
    parser.add_argument("--frame", type=int, default=None, help="Number of frames to run")
    parser.add_argument("--screenshot", type=str, default=None, help="Screenshot output path")
    parser.add_argument("--scale", type=int, default=1, help="Display scale factor")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark (1000 instructions)")
    
    args = parser.parse_args()
    
    if args.benchmark:
        import time
        start = time.time()
        frames = run_transpiled(headless=True, frame_limit=1000)
        elapsed = time.time() - start
        print(f"Benchmark: {frames} frames in {elapsed:.3f}s")
    else:
        # Use pygame version for interactive display
        frames = run_with_pygame(
            headless=args.headless,
            frame_limit=args.frame,
            screenshot_path=args.screenshot,
            scale=args.scale
        )
        print(f"Ran {frames} frames")
"#
    .to_string()
}
// Force rebuild ven 1 mag 2026, 13:30:36, CEST
