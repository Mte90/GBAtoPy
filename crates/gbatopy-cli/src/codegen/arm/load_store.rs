use gbatopy_disasm::DecodedInstruction;

pub fn generate_load_store(inst: &DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode;
    let ops = &inst.operands;

    match opcode {
        "LDR" | "STR" => {
            if ops.len() >= 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress { base, offset, writeback } = &ops[1] {
                        let offset_expr = match offset {
                            ImmediateOffset(n) => {
                                if *n >= 0 {
                                    format!(" + {}", n)
                                } else {
                                    format!(" - {}", -n)
                                }
                            }
                            _ => String::new(),
                        };
                        let wb = if *writeback { " + offset" } else { "" };
                        let rw = if opcode == "LDR" { "read_u32" } else { "write_u32" };
                        return Some(format!(
                            "memory.{}(r[{}]{}{}, r[{}]{})",
                            rw, rd, offset_expr, wb, base
                        ));
                    }
                }
            }
            None
        }
        "LDRB" | "STRB" => {
            if ops.len() >= 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress { base, offset, writeback } = &ops[1] {
                        let offset_expr = match offset {
                            ImmediateOffset(n) => {
                                if *n >= 0 {
                                    format!(" + {}", n)
                                } else {
                                    format!(" - {}", -n)
                                }
                            }
                            _ => String::new(),
                        };
                        let rw = if opcode == "LDRB" { "read_u8" } else { "write_u8" };
                        return Some(format!(
                            "r[{}] = memory.{}(r[{}]{}) & 0xFF",
                            rd, rw, base, offset_expr
                        ));
                    }
                }
            }
            None
        }
        "LDRH" | "STRH" => {
            if ops.len() >= 2 {
                if let Operand::Register(rd) = ops[0] {
                    if let Operand::MemoryAddress { base, offset, writeback } = &ops[1] {
                        let offset_expr = match offset {
                            ImmediateOffset(n) => {
                                if *n >= 0 {
                                    format!(" + {}", n)
                                } else {
                                    format!(" - {}", -n)
                                }
                            }
                            _ => String::new(),
                        };
                        let rw = if opcode == "LDRH" { "read_u16" } else { "write_u16" };
                        return Some(format!(
                            "r[{}] = memory.{}(r[{}]{}) & 0xFFFF",
                            rd, rw, base, offset_expr
                        ));
                    }
                }
            }
            None
        }
        _ => None,
    }
}