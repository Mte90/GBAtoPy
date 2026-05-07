//! Thumb instruction lifter
//!
//! Lifts decoded Thumb instructions to IR statements.
//! Thumb mode: 16-bit instructions, subset of ARM functionality,
//! CPSR.T flag determines execution mode.

use gbatopy_disasm::{ArmMode, DecodedInstruction, Operand};

use crate::lifter::LifterContext;
use crate::{IrExpr, IrOp, IrStatement};

/// Lift a Thumb data processing instruction
///
/// Common Thumb ALU operations: ADD, SUB, MOV, CMP, AND, etc.
pub fn lift_thumb_alu(ctx: &mut LifterContext, instr: &DecodedInstruction) -> Vec<IrStatement> {
    let mut statements = Vec::new();

    // Get destination register from first operand
    let rd = instr.operands.first().and_then(|op| {
        if let Operand::Register(r) = op {
            Some(*r)
        } else {
            None
        }
    });

    // Get source operands
    let rs = if instr.operands.len() > 1 {
        create_thumb_expr(ctx, &instr.operands[1])
    } else {
        IrExpr::constant(0)
    };

    // Map Thumb opcode to IR operation
    let ir_op = match instr.opcode.as_str() {
        "ADD" => IrOp::Add,
        "SUB" => IrOp::Sub,
        "AND" => IrOp::And,
        "EOR" => IrOp::Xor,
        "ORR" => IrOp::Or,
        "LSL" => IrOp::Shl,
        "LSR" => IrOp::Shr,
        "ASR" => IrOp::Asr,
        "ROR" => IrOp::Ror,
        "NEG" => IrOp::Sub,
        "MVN" => IrOp::Not,
        "MOV" => IrOp::Add,
        "CMP" | "CMN" | "TST" => return statements,
        _ => return statements,
    };

    // Handle MOV specially (single operand)
    if instr.opcode == "MOV" {
        if let Some(rd) = rd {
            if rd < 16 {
                statements.push(IrStatement::assign(ctx.reg_expr(rd), rs));
            }
        }
        return statements;
    }

    // For NEG, compute 0 - rs
    let result = if instr.opcode == "NEG" {
        IrExpr::Op(IrOp::Sub, vec![IrExpr::constant(0), rs])
    } else {
        // Two-operand instructions: rd = rd op rs
        let lhs = ctx.reg_expr(rd.unwrap_or(0));
        IrExpr::Op(ir_op, vec![lhs, rs])
    };

    // Assign result to destination
    if let Some(rd) = rd {
        if rd < 16 {
            statements.push(IrStatement::assign(ctx.reg_expr(rd), result));
        }
    }

    // Handle S bit for flag setting
    if instr.sets_flags {
        // Generate flag computation using CPSR
        // For now, emit a Nop to preserve the semantic that flags were set
        // Full implementation would update CPSR based on result
    }

    statements
}

/// Lift a Thumb load/store instruction (LDR, STR, LDRH, STRH, etc.)
pub fn lift_thumb_load_store(
    ctx: &mut LifterContext,
    instr: &DecodedInstruction,
) -> Vec<IrStatement> {
    let mut statements = Vec::new();

    // Thumb load/store format: OP rd, [rb, #offset]
    // Operands: [Register(rt), MemoryAddress{base, offset, ...}]

    if instr.operands.len() < 2 {
        return statements;
    }

    // Get the register to load/store
    let rt = if let Operand::Register(r) = &instr.operands[0] {
        Some(*r)
    } else {
        None
    };

    // Create memory address expression
    let mem_addr = create_thumb_mem_expr(ctx, &instr.operands[1]);

    // Create the IR statement based on opcode
    match instr.opcode.as_str() {
        "LDR" => {
            if let Some(rt) = rt {
                statements.push(IrStatement::Load {
                    target: ctx.reg_expr(rt),
                    address: mem_addr,
                    size: 4,
                });
            }
        }
        "STR" => {
            if let Some(rt) = rt {
                statements.push(IrStatement::Store {
                    value: ctx.reg_expr(rt),
                    address: mem_addr,
                    size: 4,
                });
            }
        }
        "LDRH" => {
            if let Some(rt) = rt {
                statements.push(IrStatement::Load {
                    target: ctx.reg_expr(rt),
                    address: mem_addr,
                    size: 2,
                });
            }
        }
        "STRH" => {
            if let Some(rt) = rt {
                statements.push(IrStatement::Store {
                    value: ctx.reg_expr(rt),
                    address: mem_addr,
                    size: 2,
                });
            }
        }
        "LDRB" => {
            if let Some(rt) = rt {
                statements.push(IrStatement::Load {
                    target: ctx.reg_expr(rt),
                    address: mem_addr,
                    size: 1,
                });
            }
        }
        "STRB" => {
            if let Some(rt) = rt {
                statements.push(IrStatement::Store {
                    value: ctx.reg_expr(rt),
                    address: mem_addr,
                    size: 1,
                });
            }
        }
        _ => {}
    }

    statements
}

/// Lift a Thumb branch instruction (B, BL, BX)
///
/// BX causes mode switching between ARM and Thumb
pub fn lift_thumb_branch(_ctx: &mut LifterContext, instr: &DecodedInstruction) -> Vec<IrStatement> {
    let mut statements = Vec::new();

    match instr.opcode.as_str() {
        "B" => {
            if let Some(Operand::Immediate(target)) = instr.operands.first() {
                statements.push(IrStatement::Branch {
                    target: format!("0x{:08X}", target),
                    condition: None,
                });
            }
        }
        "BL" => {
            if let Some(Operand::Immediate(target)) = instr.operands.first() {
                statements.push(IrStatement::Call {
                    target: format!("0x{:08X}", target),
                    args: vec![],
                });
            }
        }
        "BX" => {
            if let Some(Operand::Register(r)) = instr.operands.first() {
                statements.push(IrStatement::ModeSwitch {
                    new_mode: ArmMode::Thumb,
                    address: *r as u32,
                });
            }
        }
        "BEQ" | "BNE" | "BGT" | "BLT" | "BGE" | "BLE" | "BCC" | "BHS" | "BLO" | "BMI" | "BPL"
        | "BVS" | "BVC" | "BHI" => {
            if let Some(Operand::Immediate(target)) = instr.operands.first() {
                let condition = decode_thumb_cond(&instr.opcode);
                statements.push(IrStatement::Branch {
                    target: format!("0x{:08X}", target),
                    condition,
                });
            }
        }
        _ => {}
    }

    statements
}

pub fn lift_thumb_stack(ctx: &mut LifterContext, instr: &DecodedInstruction) -> Vec<IrStatement> {
    let mut statements = Vec::new();

    let is_pop = instr.opcode == "POP";

    for (_idx, op) in instr.operands.iter().enumerate() {
        if let Operand::Register(reg) = op {
            if *reg < 13 {
                if is_pop {
                    let sp = ctx.reg_expr(13);
                    statements.push(IrStatement::Load {
                        target: ctx.reg_expr(*reg),
                        address: sp,
                        size: 4,
                    });
                } else {
                    let sp = ctx.reg_expr(13);
                    statements.push(IrStatement::Store {
                        value: ctx.reg_expr(*reg),
                        address: sp,
                        size: 4,
                    });
                }
            }
        }
    }

    statements
}

/// Decode Thumb condition code from opcode suffix
fn decode_thumb_cond(opcode: &str) -> Option<crate::Condition> {
    let cond = match opcode {
        "BEQ" => crate::Condition::Eq,
        "BNE" => crate::Condition::Ne,
        "BGT" => crate::Condition::Gt,
        "BLT" => crate::Condition::Lt,
        "BGE" => crate::Condition::Ge,
        "BLE" => crate::Condition::Le,
        "BCC" | "BHS" => crate::Condition::Cc,
        "BLO" => crate::Condition::Cs,
        "BLS" => crate::Condition::Ls,
        "BMI" => crate::Condition::Mi,
        "BPL" => crate::Condition::Pl,
        "BVS" => crate::Condition::Vs,
        "BVC" => crate::Condition::Vc,
        "BHI" => crate::Condition::Hi,
        _ => return None,
    };
    Some(cond)
}

/// Create IR expression from Thumb operand
fn create_thumb_expr(ctx: &mut LifterContext, op: &Operand) -> IrExpr {
    match op {
        Operand::Register(r) => ctx.reg_expr(*r),
        Operand::Immediate(val) => IrExpr::constant(*val),
        Operand::PcRelative(offset) => {
            // PC-relative: address = PC + offset
            IrExpr::Op(
                IrOp::Add,
                vec![ctx.reg_expr(15), IrExpr::constant(*offset as u32)],
            )
        }
        _ => IrExpr::constant(0),
    }
}

/// Create memory address expression for load/store
fn create_thumb_mem_expr(ctx: &mut LifterContext, op: &Operand) -> IrExpr {
    match op {
        Operand::MemoryAddress { base, offset, .. } => {
            let base_expr = ctx.reg_expr(*base);
            match offset {
                gbatopy_disasm::AddressingMode::ImmediateOffset(off) => {
                    IrExpr::Op(IrOp::Add, vec![base_expr, IrExpr::constant(*off as u32)])
                }
                _ => base_expr,
            }
        }
        _ => IrExpr::constant(0),
    }
}

/// Main entry point for lifting Thumb instructions
pub fn lift_thumb(ctx: &mut LifterContext, instr: &DecodedInstruction) -> Vec<IrStatement> {
    // Verify this is actually a Thumb instruction
    if instr.width != 2 {
        // Not a Thumb instruction (Thumb is 16-bit = 2 bytes)
        return vec![];
    }

    // Route to appropriate lifter based on opcode category
    let mut statements = Vec::new();
    match instr.opcode.as_str() {
        "NOP" => {
            statements.push(IrStatement::Nop);
            return statements;
        }
        // ALU operations
        "ADD" | "SUB" | "MOV" | "CMP" | "CMN" | "NEG" | "AND" | "EOR" | "ORR" | "LSL" | "LSR"
        | "ASR" | "ROR" | "MVN" | "TST" => lift_thumb_alu(ctx, instr),
        // Load/Store
        "LDR" | "STR" | "LDRH" | "STRH" | "LDRB" | "STRB" | "LDRSB" | "LDRSH" => {
            lift_thumb_load_store(ctx, instr)
        }
        // Branches
        "B" | "BL" | "BX" | "BEQ" | "BNE" | "BGT" | "BLT" | "BGE" | "BLE" | "BCC" | "BHS"
        | "BLO" | "BLS" | "BMI" | "BPL" | "BVS" | "BVC" | "BHI" => lift_thumb_branch(ctx, instr),
        // Push/Pop (thumb-specific stack operations)
        "PUSH" | "POP" => lift_thumb_stack(ctx, instr),
        // Unknown - return empty
        _ => vec![],
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::lifter::LifterContext;
    use crate::Condition;
    use gbatopy_disasm::{ArmMode, DecodedInstruction, Operand};

    #[test]
    fn test_lift_thumb_mov() {
        let mut ctx = LifterContext::new();

        // MOV r0, #42 in Thumb mode
        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "MOV".to_string(),
            operands: vec![Operand::Register(0), Operand::Immediate(42)],
            condition: Some(Condition::Al),
            mode: ArmMode::Thumb,
            raw: 0x2000, // MOV r0, #42 encoding
            sets_flags: false,
            width: 2, // Thumb is 16-bit
            is_data: false,
        };

        let statements = lift_thumb(&mut ctx, &instr);

        // Should generate one assignment
        assert_eq!(statements.len(), 1);

        if let IrStatement::Assign { target: _, value } = &statements[0] {
            // r0 = 42
            assert!(matches!(value, IrExpr::Value(crate::IrValue::Constant(42))));
        } else {
            panic!("Expected Assign statement");
        }
    }

    #[test]
    fn test_lift_thumb_add() {
        let mut ctx = LifterContext::new();

        // ADD r0, r1, r2 in Thumb mode
        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "ADD".to_string(),
            operands: vec![
                Operand::Register(0),
                Operand::Register(1),
                Operand::Register(2),
            ],
            condition: Some(Condition::Al),
            mode: ArmMode::Thumb,
            raw: 0x1880, // ADD r0, r1, r2 encoding
            sets_flags: false,
            width: 2,
            is_data: false,
        };

        let statements = lift_thumb(&mut ctx, &instr);

        assert_eq!(statements.len(), 1);
    }

    #[test]
    fn test_lift_thumb_ldr() {
        let mut ctx = LifterContext::new();

        // LDR r0, [r1, #4]
        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "LDR".to_string(),
            operands: vec![
                Operand::Register(0),
                Operand::MemoryAddress {
                    base: 1,
                    offset: gbatopy_disasm::AddressingMode::ImmediateOffset(4),
                    writeback: false,
                },
            ],
            condition: Some(Condition::Al),
            mode: ArmMode::Thumb,
            raw: 0x6801, // LDR r0, [r1, #4] encoding
            sets_flags: false,
            width: 2,
            is_data: false,
        };

        let statements = lift_thumb(&mut ctx, &instr);

        // Should generate Load statement
        assert!(!statements.is_empty());
    }

    #[test]
    fn test_lift_thumb_bx() {
        let mut ctx = LifterContext::new();

        // BX lr - switch mode based on LR bit 0
        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "BX".to_string(),
            operands: vec![Operand::Register(14)], // LR
            condition: Some(Condition::Al),
            mode: ArmMode::Thumb,
            raw: 0x4770, // BX lr encoding
            sets_flags: false,
            width: 2,
            is_data: false,
        };

        let statements = lift_thumb(&mut ctx, &instr);

        // Should generate ModeSwitch statement
        assert!(!statements.is_empty());
    }
}
