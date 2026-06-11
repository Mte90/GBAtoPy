use gbatopy_disasm::{DecodedInstruction, Operand};

pub fn generate(inst: &DecodedInstruction) -> Option<String> {
    let opcode = inst.opcode.as_str();
    let ops = &inst.operands;

    if opcode == "LDR" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("r[{}] = memory.read_u32(r[{}]{})", rd, base, offset_expr));
            }
        }
    }
    if opcode == "STR" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("memory.write_u32(r[{}]{}, r[{}])", base, offset_expr, rd));
            }
        }
    }
    if opcode == "LDRB" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("r[{}] = memory.read_u8(r[{}]{}) & 0xFF", rd, base, offset_expr));
            }
        }
    }
    if opcode == "STRB" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("memory.write_u8(r[{}]{}, r[{}] & 0xFF)", base, offset_expr, rd));
            }
        }
    }
    if opcode == "LDRH" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("r[{}] = memory.read_u16(r[{}]{}) & 0xFFFF", rd, base, offset_expr));
            }
        }
    }
    if opcode == "STRH" && ops.len() >= 2 {
        if let Operand::Register(rd) = ops[0] {
            if let Operand::MemoryAddress { base, offset, .. } = &ops[1] {
                let offset_expr = match offset {
                    gbatopy_disasm::operand::AddressingMode::ImmediateOffset(n) => {
                        if *n >= 0 { format!(" + {}", n) } else { format!(" - {}", -n) }
                    }
                    _ => String::new(),
                };
                return Some(format!("memory.write_u16(r[{}]{}, r[{}] & 0xFFFF)", base, offset_expr, rd));
            }
        }
    }
    None
}
