use std::fs;
use std::path::Path;

// Import PPU code generator
use crate::ppu::generate_ppu_code;

// Disassembler module
use gbatopy_disasm::{AddressingMode, Disassembler, Operand};

pub fn run_pipeline(
    rom_path: &str,
    output_path: &str,
    assets_dir: &Path,
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

    // Generate Python directly from disassembled instructions
    let mut code = String::new();

    // Add imports
    code.push_str("import pygame\n");
    code.push_str("import argparse\n");
    code.push_str("import sys\n");
    code.push_str("import os\n\n");

    code.push_str("# Global ARM registers (r0-r15, cpsr, spsr)\n");
    code.push_str("r0 = r1 = r2 = r3 = r4 = r5 = r6 = r7 = 0\n");
    code.push_str("r8 = r9 = r10 = r11 = r12 = r13 = r14 = r15 = 0\n");
    code.push_str("cpsr = 0  # Current Program Status Register\n");
    code.push_str("spsr = 0  # Saved Program Status Register\n\n");

    // Embed PPU code
    code.push_str("# PPU (Picture Processing Unit) - Graphics rendering\n");
    code.push_str(&format!("{}\n\n", generate_ppu_code()));

    // Generate SINGLE function from ALL disassembled instructions
    let mut func_map_entries = Vec::new();
    let mut func_body = Vec::new();
    let base_addr = if let Some(first) = instructions.first() {
        first.address
    } else {
        0x08000000
    };

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
                        }
                    }
                }
            }
            // MOV Rd, Rm
            "MOV" if ops.len() == 2 => {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::Register(rm) = ops[1] {
                        return format!("r{} = r{}", rd, rm);
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
                    if let Operand::Immediate(offset) = ops[0] {
                        if base_opcode == "BL" {
                            // BL: Link register to return address (PC + 4)
                            return format!(
                                "r14, r15 = r15 + 4, r15 + {}\n# Branch with link",
                                offset
                            );
                        } else {
                            // B: Unconditional branch
                            return format!("r15 = r15 + {}\n# Branch", offset);
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
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::MemoryAddress {
                            base,
                            offset,
                            writeback,
                        } = &ops[1]
                        {
                            // Generate address expression based on addressing mode
                            let addr_expr = match offset {
                                AddressingMode::ImmediateOffset(off) => {
                                    if *off == 0 {
                                        format!("r{}", base)
                                    } else if *off >= 0 {
                                        format!("r{} + {}", base, off)
                                    } else {
                                        format!("r{} + ({})", base, off)
                                    }
                                }
                                AddressingMode::RegisterOffset(reg) => {
                                    format!("r{} + r{}", base, reg)
                                }
                                AddressingMode::ScaledRegisterOffset {
                                    reg,
                                    shift: _,
                                    amount,
                                } => {
                                    format!("r{} + (r{} << {})", base, reg, amount)
                                }
                                AddressingMode::PreIndexed { offset: off, .. } => {
                                    if *off == 0 {
                                        format!("r{}", base)
                                    } else if *off >= 0 {
                                        format!("r{} + {}", base, off)
                                    } else {
                                        format!("r{} + ({})", base, off)
                                    }
                                }
                                AddressingMode::PostIndexed { .. } => {
                                    format!("r{}", base)
                                }
                                AddressingMode::Multi { .. } => {
                                    return format!("# LDR (multi-register not applicable)");
                                }
                            };

                            let mut code = format!("r{} = memory.read_32({})", rd, addr_expr);

                            // Handle writeback
                            if *writeback {
                                let new_addr = match offset {
                                    AddressingMode::PreIndexed { offset: off, .. }
                                    | AddressingMode::PostIndexed { offset: off, .. } => {
                                        if *off == 0 {
                                            format!("r{}", base)
                                        } else if *off >= 0 {
                                            format!("r{} + {}", base, off)
                                        } else {
                                            format!("r{} + ({})", base, off)
                                        }
                                    }
                                    _ => format!("r{}", base),
                                };
                                code = format!("{}; r{} = {}", code, base, new_addr);
                            }

                            return code;
                        }
                    }
                }
                return format!("# LDR (parsing failed)");
            }
            // STR Rd, [Rn, #offset] - Store word to memory
            "STR" => {
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::MemoryAddress {
                            base,
                            offset,
                            writeback,
                        } = &ops[1]
                        {
                            // Generate address expression based on addressing mode
                            let addr_expr = match offset {
                                AddressingMode::ImmediateOffset(off) => {
                                    if *off == 0 {
                                        format!("r{}", base)
                                    } else if *off >= 0 {
                                        format!("r{} + {}", base, off)
                                    } else {
                                        format!("r{} + ({})", base, off)
                                    }
                                }
                                AddressingMode::RegisterOffset(reg) => {
                                    format!("r{} + r{}", base, reg)
                                }
                                AddressingMode::ScaledRegisterOffset {
                                    reg,
                                    shift: _,
                                    amount,
                                } => {
                                    format!("r{} + (r{} << {})", base, reg, amount)
                                }
                                AddressingMode::PreIndexed { offset: off, .. } => {
                                    if *off == 0 {
                                        format!("r{}", base)
                                    } else if *off >= 0 {
                                        format!("r{} + {}", base, off)
                                    } else {
                                        format!("r{} + ({})", base, off)
                                    }
                                }
                                AddressingMode::PostIndexed { .. } => {
                                    format!("r{}", base)
                                }
                                AddressingMode::Multi { .. } => {
                                    return format!("# STR (multi-register not applicable)");
                                }
                            };

                            let mut code = format!("memory.write_32({}, r{})", addr_expr, rd);

                            // Handle writeback
                            if *writeback {
                                let new_addr = match offset {
                                    AddressingMode::PreIndexed { offset: off, .. }
                                    | AddressingMode::PostIndexed { offset: off, .. } => {
                                        if *off == 0 {
                                            format!("r{}", base)
                                        } else if *off >= 0 {
                                            format!("r{} + {}", base, off)
                                        } else {
                                            format!("r{} + ({})", base, off)
                                        }
                                    }
                                    _ => format!("r{}", base),
                                };
                                code = format!("{}; r{} = {}", code, base, new_addr);
                            }

                            return code;
                        }
                    }
                }
                return format!("# STR (parsing failed)");
            } // LDM/STM - Block transfer instructions
            "LDM" | "STM" => {
                if ops.len() >= 1 {
                    if let Operand::MemoryAddress {
                        base,
                        offset,
                        writeback: wb,
                    } = &ops[0]
                    {
                        if let AddressingMode::Multi {
                            base: _,
                            registers,
                            increment,
                            writeback: _,
                        } = offset
                        {
                            // Generate code for block transfer
                            let is_load = base_opcode == "LDM";

                            // Determine addressing mode from the full opcode (which includes suffix)
                            // The base_opcode was stripped of condition codes, but retains the mode suffix
                            let mode_suffix =
                                opcode.trim_start_matches("LDM").trim_start_matches("STM");

                            // Determine direction: IA/IB increment, DA/DB decrement
                            let (pre_increment, addr_start) =
                                if mode_suffix.contains("IB") || mode_suffix.contains("DB") {
                                    // Pre-indexed: start at base + 4
                                    (true, format!("r{} + 4", base))
                                } else {
                                    // Post-indexed or increment after: start at base
                                    (false, format!("r{}", base))
                                };

                            // Calculate address for each register based on mode
                            let mut addr_var = "addr".to_string();
                            let mut code_lines = Vec::new();

                            // For decrement modes, we need to calculate the start address
                            if !*increment {
                                let count = registers.len();
                                let offset = count * 4 - 4;
                                if offset > 0 {
                                    addr_var = format!("r{} - {}", base, offset);
                                } else {
                                    addr_var = format!("r{}", base);
                                }
                            }

                            // Generate load/store for each register
                            for (i, &reg) in registers.iter().enumerate() {
                                let current_addr = if *increment {
                                    if pre_increment {
                                        format!("{} + {}", addr_var, i * 4 + 4)
                                    } else {
                                        format!("{} + {}", addr_var, i * 4)
                                    }
                                } else {
                                    let idx = registers.len() - 1 - i;
                                    if mode_suffix.contains("DB") {
                                        format!("{} + {}", addr_var, idx * 4 + 4)
                                    } else {
                                        format!("{} + {}", addr_var, idx * 4)
                                    }
                                };

                                if is_load {
                                    code_lines.push(format!(
                                        "r{} = memory.read_32({})",
                                        reg, current_addr
                                    ));
                                } else {
                                    code_lines.push(format!(
                                        "memory.write_32({}, r{})",
                                        current_addr, reg
                                    ));
                                }
                            }

                            // Handle writeback
                            if *wb {
                                let new_base = if *increment {
                                    let offset = registers.len() * 4;
                                    format!("r{} + {}", base, offset)
                                } else {
                                    let offset = registers.len() * 4;
                                    format!("r{} - {}", base, offset)
                                };
                                code_lines.push(format!("r{} = {}", base, new_base));
                            }

                            return code_lines.join("; ");
                        }
                    }
                }
                return format!("# {} (parsing failed)", base_opcode);
            }
            // LDRB/STRB - Byte transfer
            "LDRB" | "STRB" => {
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::MemoryAddress {
                            base,
                            offset,
                            writeback,
                        } = &ops[1]
                        {
                            // Generate address expression based on addressing mode
                            let addr_expr = match offset {
                                AddressingMode::ImmediateOffset(off) => {
                                    if *off == 0 {
                                        format!("r{}", base)
                                    } else if *off >= 0 {
                                        format!("r{} + {}", base, off)
                                    } else {
                                        format!("r{} + ({})", base, off)
                                    }
                                }
                                AddressingMode::RegisterOffset(reg) => {
                                    format!("r{} + r{}", base, reg)
                                }
                                AddressingMode::ScaledRegisterOffset {
                                    reg,
                                    shift: _,
                                    amount,
                                } => {
                                    format!("r{} + (r{} << {})", base, reg, amount)
                                }
                                AddressingMode::PreIndexed { offset: off, .. } => {
                                    if *off == 0 {
                                        format!("r{}", base)
                                    } else if *off >= 0 {
                                        format!("r{} + {}", base, off)
                                    } else {
                                        format!("r{} + ({})", base, off)
                                    }
                                }
                                AddressingMode::PostIndexed { .. } => {
                                    format!("r{}", base)
                                }
                                AddressingMode::Multi { .. } => {
                                    return format!(
                                        "# {} (multi-register not applicable)",
                                        base_opcode
                                    );
                                }
                            };

                            let mut code = if base_opcode == "LDRB" {
                                format!("r{} = memory.read_8({})", rd, addr_expr)
                            } else {
                                format!("memory.write_8({}, r{})", addr_expr, rd)
                            };

                            // Handle writeback
                            if *writeback {
                                let new_addr = match offset {
                                    AddressingMode::PreIndexed { offset: off, .. }
                                    | AddressingMode::PostIndexed { offset: off, .. } => {
                                        if *off == 0 {
                                            format!("r{}", base)
                                        } else if *off >= 0 {
                                            format!("r{} + {}", base, off)
                                        } else {
                                            format!("r{} + ({})", base, off)
                                        }
                                    }
                                    _ => format!("r{}", base),
                                };
                                code = format!("{}; r{} = {}", code, base, new_addr);
                            }

                            return code;
                        }
                    }
                }
                return format!("# {} (parsing failed)", base_opcode);
            }
            // LDRH/STRH - Halfword transfer
            "LDRH" | "STRH" => {
                if ops.len() >= 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::MemoryAddress {
                            base,
                            offset,
                            writeback,
                        } = &ops[1]
                        {
                            // Generate address expression based on addressing mode
                            let addr_expr = match offset {
                                AddressingMode::ImmediateOffset(off) => {
                                    if *off == 0 {
                                        format!("r{}", base)
                                    } else if *off >= 0 {
                                        format!("r{} + {}", base, off)
                                    } else {
                                        format!("r{} + ({})", base, off)
                                    }
                                }
                                AddressingMode::RegisterOffset(reg) => {
                                    format!("r{} + r{}", base, reg)
                                }
                                AddressingMode::PreIndexed { offset: off, .. } => {
                                    if *off == 0 {
                                        format!("r{}", base)
                                    } else if *off >= 0 {
                                        format!("r{} + {}", base, off)
                                    } else {
                                        format!("r{} + ({})", base, off)
                                    }
                                }
                                AddressingMode::PostIndexed { .. } => {
                                    format!("r{}", base)
                                }
                                _ => {
                                    return format!(
                                        "# {} (addressing mode not supported)",
                                        base_opcode
                                    );
                                }
                            };

                            let mut code = if base_opcode == "LDRH" {
                                format!("r{} = memory.read_16({})", rd, addr_expr)
                            } else {
                                format!("memory.write_16({}, r{})", addr_expr, rd)
                            };

                            // Handle writeback
                            if *writeback {
                                let new_addr = match offset {
                                    AddressingMode::PreIndexed { offset: off, .. }
                                    | AddressingMode::PostIndexed { offset: off, .. } => {
                                        if *off == 0 {
                                            format!("r{}", base)
                                        } else if *off >= 0 {
                                            format!("r{} + {}", base, off)
                                        } else {
                                            format!("r{} + ({})", base, off)
                                        }
                                    }
                                    _ => format!("r{}", base),
                                };
                                code = format!("{}; r{} = {}", code, base, new_addr);
                            }

                            return code;
                        }
                    }
                }
                return format!("# {} (parsing failed)", base_opcode);
            }
            // Branch instructions
            "B" | "BL" => {
                return format!("# {} branch (not implemented)", base_opcode);
            }
            "BX" => {
                return format!("# BX (branch exchange not implemented)");
            }
            // CMP, CMN, TST, TEQ (condition tests - set CPSR flags only)
            "CMP" => {
                // CMP Rd, Rn: sets flags based on Rd - Rn
                if ops.len() >= 2 {
                    let rd = &ops[0];
                    let rn = &ops[1];
                    return format!(
                        "cpsr = _update_flags_nzcv({} - {})",
                        rd.to_python(),
                        rn.to_python()
                    );
                }
                return format!("# {} (parsing failed)", base_opcode);
            }
            "CMN" => {
                // CMN Rd, Rn: sets flags based on Rd + Rn
                if ops.len() >= 2 {
                    let rd = &ops[0];
                    let rn = &ops[1];
                    return format!(
                        "cpsr = _update_flags_nzcv({} + {})",
                        rd.to_python(),
                        rn.to_python()
                    );
                }
                return format!("# {} (parsing failed)", base_opcode);
            }
            "TST" => {
                // TST Rd, Rn: sets flags based on Rd AND Rn
                if ops.len() >= 2 {
                    let rd = &ops[0];
                    let rn = &ops[1];
                    return format!(
                        "cpsr = _update_flags_nzcv({} & {})",
                        rd.to_python(),
                        rn.to_python()
                    );
                }
                return format!("# {} (parsing failed)", base_opcode);
            }
            "TEQ" => {
                // TEQ Rd, Rn: sets flags based on Rd XOR Rn
                if ops.len() >= 2 {
                    let rd = &ops[0];
                    let rn = &ops[1];
                    return format!(
                        "cpsr = _update_flags_nzcv({} ^ {})",
                        rd.to_python(),
                        rn.to_python()
                    );
                }
                return format!("# {} (parsing failed)", base_opcode);
            }
            // MUL/MLA - Multiply instructions
            "MUL" => {
                // MUL Rd, Rm, Rs: Rd = Rm * Rs
                if ops.len() >= 3 {
                    let rd = &ops[0];
                    let rm = &ops[1];
                    let rs = &ops[2];
                    return format!(
                        "r{} = (r{} * r{}) & 0xFFFFFFFF",
                        rd.to_python(),
                        rm.to_python(),
                        rs.to_python()
                    );
                }
                return format!("# MUL (parsing failed)");
            }
            "MLA" => {
                // MLA Rd, Rm, Rs, Ra: Rd = (Rm * Rs) + Ra
                if ops.len() >= 4 {
                    let rd = &ops[0];
                    let rm = &ops[1];
                    let rs = &ops[2];
                    let ra = &ops[3];
                    return format!(
                        "r{} = ((r{} * r{}) + r{}) & 0xFFFFFFFF",
                        rd.to_python(),
                        rm.to_python(),
                        rs.to_python(),
                        ra.to_python()
                    );
                }
                return format!("# MLA (parsing failed)");
            }
            "UMULL" => {
                // UMULL RdLo, RdHi, Rm, Rs: 64-bit unsigned multiply
                if ops.len() >= 4 {
                    let rd_lo = &ops[0];
                    let rd_hi = &ops[1];
                    let rm = &ops[2];
                    let rs = &ops[3];
                    return format!(
                        "result_64 = r{} * r{}; r{} = result_64 & 0xFFFFFFFF; r{} = (result_64 >> 32) & 0xFFFFFFFF",
                        rm.to_python(), rs.to_python(), rd_lo.to_python(), rd_hi.to_python()
                    );
                }
                return format!("# UMULL (parsing failed)");
            }
            "SMULL" => {
                // SMULL RdLo, RdHi, Rm, Rs: 64-bit signed multiply
                if ops.len() >= 4 {
                    let rd_lo = &ops[0];
                    let rd_hi = &ops[1];
                    let rm = &ops[2];
                    let rs = &ops[3];
                    return format!(
                        "result_64 = (r{} if r{} < 0x80000000 else r{} - 0x100000000) * (r{} if r{} < 0x80000000 else r{} - 0x100000000); r{} = result_64 & 0xFFFFFFFF; r{} = (result_64 >> 32) & 0xFFFFFFFF",
                        rm.to_python(), rm.to_python(), rm.to_python(), rs.to_python(), rs.to_python(), rs.to_python(), rd_lo.to_python(), rd_hi.to_python()
                    );
                }
                return format!("# SMULL (parsing failed)");
            }
            "MRS" => {
                if ops.len() == 2 {
                    if let Operand::Register(rd) = ops[0] {
                        if let Operand::Immediate(reg_type) = ops[1] {
                            let source = if reg_type == 0 { "cpsr" } else { "spsr" };
                            return format!("r{} = {}", rd, source);
                        } else {
                            return format!("r{} = cpsr", rd);
                        }
                    }
                }
                return format!("# MRS (parsing failed)");
            }
            "MSR" => {
                if ops.len() >= 2 {
                    let flags_operand = &ops[0];
                    let src_operand = &ops[1];

                    let is_flags_immediate = matches!(flags_operand, Operand::Immediate(_));

                    let flags_field = if is_flags_immediate {
                        if let Operand::Immediate(f) = flags_operand {
                            *f
                        } else {
                            0
                        }
                    } else {
                        0xF
                    };

                    let mut flag_mask = String::new();
                    if flags_field & 0x1 != 0 {
                        flag_mask.push_str("0x00010000 | ");
                    }
                    if flags_field & 0x2 != 0 {
                        flag_mask.push_str("0x00020000 | ");
                    }
                    if flags_field & 0x4 != 0 {
                        flag_mask.push_str("0x00040000 | ");
                    }
                    if flags_field & 0x8 != 0 {
                        flag_mask.push_str("0x00080000 | ");
                    }

                    let mask = if flag_mask.is_empty() {
                        "0xFFFF_FFFF".to_string()
                    } else {
                        flag_mask.trim_end_matches(" | ").to_string()
                    };

                    let src_val = match src_operand {
                        Operand::Register(rn) => format!("r{}", rn),
                        Operand::Immediate(imm) => format!("{}", imm),
                        _ => "0".to_string(),
                    };

                    if flags_field & 0x1 != 0 || flags_field & 0x8 != 0 || flags_field == 0xF {
                        return format!("cpsr = (cpsr & ~0x0F000000) | ({} & {})", src_val, mask);
                    }

                    if flags_field & 0x4 != 0 {
                        return format!("spsr = (spsr & ~{}) | {}", mask, src_val);
                    }

                    let full_mask = if flag_mask.is_empty() {
                        "0xFFFF_FFFF".to_string()
                    } else {
                        "0xFFFF_FFFF".to_string()
                    };
                    return format!("spsr = (spsr & ~{}) | {}", full_mask, src_val);
                }
                return format!("# MSR (parsing failed)");
            }
            "SWP" => {
                // SWP Rd, [Rn], Rm: Rd = memory[Rn]; memory[Rn] = Rm (32-bit atomic swap)
                // Format: SWP Rd, [Rn], Rm
                if ops.len() >= 3 {
                    let rd = &ops[0];
                    let rn = &ops[1];
                    let rm = &ops[2];
                    return format!(
                        "r{} = memory.read_32(r{}); memory.write_32(r{}, r{})",
                        rd.to_python(),
                        rn.to_python(),
                        rn.to_python(),
                        rm.to_python()
                    );
                }
                return format!("# SWP (parsing failed)");
            }
            "SWPB" => {
                // SWPB Rd, [Rn], Rm: Rd = memory[Rn]; memory[Rn] = Rm & 0xFF (8-bit atomic swap)
                // Format: SWPB Rd, [Rn], Rm
                if ops.len() >= 3 {
                    let rd = &ops[0];
                    let rn = &ops[1];
                    let rm = &ops[2];
                    return format!(
                        "r{} = memory.read_8(r{}); memory.write_8(r{}, r{} & 0xFF)",
                        rd.to_python(),
                        rn.to_python(),
                        rn.to_python(),
                        rm.to_python()
                    );
                }
                return format!("# SWPB (parsing failed)");
            }
            "SWI" => {
                if let Operand::Immediate(swi_num) = ops[0] {
                    return format!("bios_swi(0x{:06X})", swi_num);
                }
                return format!("# SWI (parsing failed)");
            }
            "COPROCESSOR" => {
                // Coprocessor instructions (MCR, MRC, LDC, STC) - not used on GBA
                return format!("# COPROCESSOR (not used on GBA)");
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

    for inst in &instructions {
        // Generate REAL Python code from instruction (not just comments)
        let py_stmt = generate_python_from_instruction(inst);
        func_body.push(py_stmt);
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

    // Generate single function for entire ROM
    if !func_body.is_empty() {
        let func_name = format!("func_{:08X}", base_addr);

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

    def write_16(self, addr, value):
        # Write 16-bit value (little-endian)
        self.write_8(addr, value & 0xFF)
        self.write_8(addr + 1, (value >> 8) & 0xFF)

    def write_32(self, addr, value):
        self.write_8(addr, value & 0xFF)
        self.write_8(addr + 1, (value >> 8) & 0xFF)
        self.write_8(addr + 2, (value >> 16) & 0xFF)
        self.write_8(addr + 3, (value >> 24) & 0xFF)

"#,
        );

        code.push_str("# Initialize GBA memory with ROM data\n");
        code.push_str("memory = GBA(ROM_DATA)\n\n");
        code.push_str(&format!("def {}():\n", func_name));
        code.push_str(
            "    global r0, r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11, r12, r13, r14, r15\n",
        );
        code.push_str("    global cpsr, spsr\n");
        for stmt in &func_body {
            code.push_str(&format!("    {}\n", stmt));
        }
        code.push_str("\n");
        func_map_entries.push(format!("    0x{:08X}: {},", base_addr, func_name));
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
import os

def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1, 
                   dump_memory=False, compare_with_mgba=False):
    """Execute transpiled GBA code using func_map dispatch"""
    
    # Set dump directory if needed
    dump_dir = os.environ.get("GBATOPY_DUMP_DIR", ".")
    
    frame_count = 0
    max_instructions = 1000000  # Safety limit
    instruction_count = 0
    
    print(f"Starting transpiled execution at PC=0x{r15:08X}")
    
    # Import dump utilities
    from memory import MemoryDump
    from cpu import RegisterDump
    
    memory_dump = MemoryDump(memory) if 'memory' in globals() else None
    register_dump = RegisterDump(cpu) if 'cpu' in globals() else None
    
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
        screen = pygame.Surface((240 * scale, 160 * scale))
    
    clock = pygame.time.Clock()
    frame_count = 0
    running = True
    instruction_count = 0
    max_instructions_per_frame = 2000  # ~120K instructions/sec for 60fps
    
    # Input state
    keys_down = {}
    
    # Execute initial code to reach game loop
    # (some ROMs need setup before entering main loop)
    
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

        # Execute transpiled GBA code for this frame
        pc = r15
        instructions_this_frame = 0

        while instructions_this_frame < max_instructions_per_frame:
            # Look up function by address
            if pc not in func_map:
                print(f"Unknown PC: 0x{pc:08X} - execution halted")
                running = False
                break

            # Get the function and call it
            func = func_map[pc]
            func()  # This updates r15 (PC) for next instruction

            pc = r15
            instructions_this_frame += 1
            instruction_count += 1

            # If PC didn't change, we're in an infinite loop - break to prevent hang
            if r15 == pc and instructions_this_frame > 100:
                print(f"PC unchanged at 0x{pc:08X} - possible infinite loop, breaking")
                break

        # Render PPU output to screen (always, even in headless mode for screenshots)
        if screen:
            ppu = get_ppu(memory)
            # Clear screen first
            screen.fill((0, 0, 0))
            # Render to framebuffer and get screen surface
            framebuffer_screen = ppu.render_frame()
            # Copy framebuffer to pygame screen
            for y in range(160):
                for x in range(240):
                    color = framebuffer_screen.get_at((x, y))
                    screen.set_at((x, y), (color[0], color[1], color[2]))
            if not headless:
                pygame.display.flip()
        
        frame_count += 1
        clock.tick(60)
        
        if frame_limit and frame_count >= frame_limit:
            break
    
    # Save screenshot if requested
    if screenshot_path and screen is not None:
        pygame.image.save(screen, screenshot_path)
        print(f"Screenshot saved to: {screenshot_path}")
    
    pygame.quit()
    return frame_count

if __name__ == "__main__":
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
