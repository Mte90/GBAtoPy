use gbatopy_disasm::{DecodedInstruction, Operand};

use crate::lifter::LifterContext;
use crate::{Condition as IrCondition, IrExpr, IrOp, IrStatement};

/// Lift ARM data processing instructions (AND, EOR, SUB, ADD, etc.)
pub fn lift_data_processing(
    ctx: &mut LifterContext,
    instr: &DecodedInstruction,
) -> Vec<IrStatement> {
    let mut statements = Vec::new();

    // Handle special opcodes first that don't follow standard 3-operand format
    match instr.opcode.as_str() {
        "NOP" => {
            statements.push(IrStatement::Nop);
            return statements;
        }
        "SWI" => {
            let number = instr
                .operands
                .first()
                .and_then(|op| {
                    if let Operand::Immediate(n) = op {
                        Some(*n)
                    } else {
                        None
                    }
                })
                .unwrap_or(0);
            statements.push(IrStatement::Swi { number });
            return statements;
        }
        "BX" | "BLX" => {
            let target = instr.operands.first().and_then(|op| {
                if let Operand::Register(r) = op {
                    Some(*r)
                } else {
                    None
                }
            });
            let is_blx = instr.opcode == "BLX";
            if is_blx || instr.opcode == "BX" {
                statements.push(IrStatement::ModeSwitch {
                    new_mode: if is_blx {
                        gbatopy_disasm::ArmMode::Thumb
                    } else {
                        gbatopy_disasm::ArmMode::Arm
                    },
                    address: target.unwrap_or(0) as u32,
                });
            }
            return statements;
        }
        "MRS" => {
            if let Some(rd) = instr.operands.first().and_then(|op| {
                if let Operand::Register(r) = op {
                    Some(*r)
                } else {
                    None
                }
            }) {
                statements.push(IrStatement::Assign {
                    target: ctx.reg_expr(rd),
                    value: IrExpr::Value(crate::values::IrValue::Flags {
                        n: false,
                        z: false,
                        c: false,
                        v: false,
                    }),
                });
            }
            return statements;
        }
        "MSR" => {
            return statements;
        }
        "LDM" | "STM" => {
            let base_reg = instr.operands.first().and_then(|op| {
                if let Operand::Register(r) = op {
                    Some(*r)
                } else {
                    None
                }
            });
            if let Some(base) = base_reg {
                let is_load = instr.opcode == "LDM";
                let addr_expr = ctx.reg_expr(base);
                let mut offset: u32 = 0;
                for i in 1..instr.operands.len() {
                    if let Operand::Register(reg) = &instr.operands[i] {
                        let reg_addr = IrExpr::Op(
                            IrOp::Add,
                            vec![addr_expr.clone(), IrExpr::constant(offset)],
                        );
                        if is_load {
                            statements.push(IrStatement::Load {
                                target: ctx.reg_expr(*reg),
                                address: reg_addr,
                                size: 4,
                            });
                        } else {
                            statements.push(IrStatement::Store {
                                address: reg_addr,
                                value: ctx.reg_expr(*reg),
                                size: 4,
                            });
                        }
                        offset += 4;
                    }
                }
            }
            return statements;
        }
        "SWP" | "SWPB" => {
            let rd = instr.operands.first().and_then(|op| {
                if let Operand::Register(r) = op {
                    Some(*r)
                } else {
                    None
                }
            });
            let rn = if instr.operands.len() > 1 {
                instr.operands[1].clone()
            } else {
                Operand::Immediate(0)
            };
            let rm = if instr.operands.len() > 2 {
                Some(instr.operands[2].clone())
            } else {
                None
            };
            if let Some(dest) = rd {
                let addr = create_expr(ctx, &rn);
                statements.push(IrStatement::Load {
                    target: ctx.reg_expr(dest),
                    address: addr.clone(),
                    size: if instr.opcode == "SWPB" { 1 } else { 4 },
                });
                if let Some(src_op) = rm {
                    let src = create_expr(ctx, &src_op);
                    statements.push(IrStatement::Store {
                        address: addr,
                        value: src,
                        size: if instr.opcode == "SWPB" { 1 } else { 4 },
                    });
                }
            }
            return statements;
        }
        _ => {}
    }

    // Get destination register
    let rd = instr.operands.first().and_then(|op| {
        if let Operand::Register(r) = op {
            Some(*r)
        } else {
            None
        }
    });

    // Get source operands
    let rs = if instr.operands.len() > 1 {
        instr.operands[1].clone()
    } else {
        Operand::Immediate(0)
    };

    let rt = if instr.operands.len() > 2 {
        Some(instr.operands[2].clone())
    } else {
        None
    };

    // Create RHS expression based on second operand
    let rhs = create_expr(ctx, &rs);

    // Create LHS expression (third operand if present, otherwise 0)
    let lhs = if let Some(rt) = rt {
        create_expr(ctx, &rt)
    } else {
        IrExpr::constant(0)
    };

    // Get carry flag expression for ADC/SBC/RSC
    let carry = IrExpr::Value(crate::values::IrValue::Flags {
        n: false,
        z: false,
        c: true,
        v: false,
    });

    // Map opcode to IrOp
    let (ir_op, lhs_expr, rhs_expr) = match instr.opcode.as_str() {
        "AND" => (Some(IrOp::And), lhs.clone(), rhs.clone()),
        "EOR" => (Some(IrOp::Xor), lhs.clone(), rhs.clone()),
        "SUB" => (Some(IrOp::Sub), lhs.clone(), rhs.clone()),
        "RSB" => (Some(IrOp::Sub), rhs.clone(), lhs.clone()),
        "ADD" => (Some(IrOp::Add), lhs.clone(), rhs.clone()),
        "ADC" => (
            Some(IrOp::Add),
            IrExpr::Op(IrOp::Add, vec![lhs.clone(), rhs.clone()]),
            carry,
        ),
        "SBC" => (
            Some(IrOp::Sub),
            IrExpr::Op(IrOp::Sub, vec![lhs.clone(), rhs.clone()]),
            IrExpr::Op(IrOp::Not, vec![carry]),
        ),
        "RSC" => (
            Some(IrOp::Sub),
            IrExpr::Op(IrOp::Sub, vec![rhs.clone(), lhs.clone()]),
            IrExpr::Op(IrOp::Not, vec![carry]),
        ),
        "ORR" => (Some(IrOp::Or), lhs.clone(), rhs.clone()),
        "BIC" => (
            Some(IrOp::And),
            lhs.clone(),
            IrExpr::Op(IrOp::Not, vec![rhs.clone()]),
        ),
        "MVN" => (Some(IrOp::Not), rhs.clone(), IrExpr::constant(0)),
        "MOV" => (None, IrExpr::constant(0), rhs.clone()),
        "CMP" => return statements,
        "CMN" => return statements,
        "TST" => return statements,
        "TEQ" => return statements,
        "LSL" => (Some(IrOp::Shl), rhs.clone(), lhs.clone()),
        "LSR" => (Some(IrOp::Shr), rhs.clone(), lhs.clone()),
        "ASR" => (Some(IrOp::Asr), rhs.clone(), lhs.clone()),
        "ROR" => (Some(IrOp::Ror), rhs.clone(), lhs.clone()),
        "MUL" => (Some(IrOp::Mul), lhs.clone(), rhs.clone()),
        "MLA" => (
            Some(IrOp::Add),
            IrExpr::Op(IrOp::Mul, vec![lhs.clone(), rhs.clone()]),
            lhs.clone(),
        ),
        _ => match instr.opcode.as_str() {
            "STR" | "STRB" | "STRH" => {
                if let Some(dest_reg) = rd {
                    let size = match instr.opcode.as_str() {
                        "STRB" => 1,
                        "STRH" => 2,
                        _ => 4,
                    };
                    statements.push(IrStatement::Store {
                        address: rhs.clone(),
                        value: ctx.reg_expr(dest_reg),
                        size,
                    });
                }
                return statements;
            }
            "LDR" | "LDRB" | "LDRH" | "LDRSB" | "LDRSH" => {
                if let Some(dest_reg) = rd {
                    let size = match instr.opcode.as_str() {
                        "LDRB" | "LDRSB" => 1,
                        "LDRH" | "LDRSH" => 2,
                        _ => 4,
                    };
                    statements.push(IrStatement::Load {
                        target: ctx.reg_expr(dest_reg),
                        address: rhs.clone(),
                        size,
                    });
                }
                return statements;
            }
            "BL" => {
                // BL (Branch with Link) - generate a function call
                let target = instr
                    .operands
                    .first()
                    .and_then(|op| {
                        if let Operand::Immediate(addr) = op {
                            Some(*addr)
                        } else {
                            None
                        }
                    })
                    .unwrap_or(0);
                statements.push(IrStatement::Call {
                    target: format!("0x{:08X}", target),
                    args: vec![],
                });
                return statements;
            }
            "B" => {
                // Plain B (Branch without link)
                let target = instr
                    .operands
                    .first()
                    .and_then(|op| {
                        if let Operand::Immediate(addr) = op {
                            Some(*addr)
                        } else {
                            None
                        }
                    })
                    .unwrap_or(0);
                statements.push(IrStatement::Branch {
                    condition: instr.condition,
                    target: format!("0x{:08X}", target),
                });
                return statements;
            }
            "UMULL" | "SMULL" => {
                let (rd_lo, rd_hi) = if instr.operands.len() >= 4 {
                    let lo = if let Operand::Register(r) = &instr.operands[0] {
                        Some(*r)
                    } else {
                        None
                    };
                    let hi = if let Operand::Register(r) = &instr.operands[1] {
                        Some(*r)
                    } else {
                        None
                    };
                    (lo, hi)
                } else {
                    (None, None)
                };
                let mul_result = IrExpr::Op(IrOp::Mul, vec![lhs, rhs]);
                if let Some(lo) = rd_lo {
                    statements.push(IrStatement::assign(ctx.reg_expr(lo), mul_result.clone()));
                }
                if let Some(hi) = rd_hi {
                    statements.push(IrStatement::assign(ctx.reg_expr(hi), IrExpr::constant(0)));
                }
                return statements;
            }
            "UMLAL" | "SMLAL" => {
                return statements;
            }
            _ => return vec![],
        },
    };

    if instr.opcode == "MOV" {
        if let Some(dest) = rd {
            if dest < 16 {
                statements.push(IrStatement::assign(ctx.reg_expr(dest), rhs));
            }
        }
        return statements;
    }

    let Some(op) = ir_op else {
        return statements;
    };

    let result = IrExpr::Op(op, vec![lhs_expr, rhs_expr]);

    let final_result = if let Some(cond) = instr.condition {
        if cond != IrCondition::Al {
            IrExpr::Conditional {
                condition: cond,
                true_val: Box::new(result.clone()),
                false_val: Box::new(ctx.reg_expr(rd.unwrap_or(0))),
            }
        } else {
            result
        }
    } else {
        result
    };

    if let Some(dest) = rd {
        if dest < 16 {
            statements.push(IrStatement::assign(ctx.reg_expr(dest), final_result));
        }
    }

    statements
}

/// Create an IrExpr from an Operand
fn create_expr(ctx: &mut LifterContext, op: &Operand) -> IrExpr {
    match op {
        Operand::Register(r) => {
            if *r < 16 {
                ctx.reg_expr(*r)
            } else {
                IrExpr::constant(0)
            }
        }
        Operand::Immediate(val) => IrExpr::constant(*val),
        Operand::ShiftedRegister { reg, shift, amount } => {
            let reg_expr = if *reg < 16 {
                ctx.reg_expr(*reg)
            } else {
                IrExpr::constant(0)
            };
            // Convert ShiftAmount to u32
            let shift_val = amount.value();
            let shift_expr = IrExpr::constant(shift_val);

            let ir_shift = match shift.name() {
                "lsl" => IrOp::Shl,
                "lsr" => IrOp::Shr,
                "asr" => IrOp::Asr,
                "ror" => IrOp::Ror,
                _ => IrOp::Shl,
            };

            IrExpr::Op(ir_shift, vec![reg_expr, shift_expr])
        }
        Operand::MemoryAddress { .. } => IrExpr::constant(0),
        Operand::PcRelative(_) => IrExpr::constant(0),
        Operand::Label(_) => IrExpr::constant(0),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::values::IrValue;
    use gbatopy_disasm::ArmMode;

    #[test]
    fn test_lift_add() {
        let mut ctx = LifterContext::new();

        let instr = DecodedInstruction {
            address: 0x08000000,
            opcode: "ADD".to_string(),
            operands: vec![
                Operand::Register(0), // rd = r0
                Operand::Register(1), // rs = r1
                Operand::Register(2), // rt = r2
            ],
            condition: Some(IrCondition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };

        let statements = lift_data_processing(&mut ctx, &instr);
        assert_eq!(statements.len(), 1);

        // ADD r0, r1, r2 -> r0 = r1 + r2
        if let IrStatement::Assign { target, value } = &statements[0] {
            assert!(matches!(target, IrExpr::Value(_)));
            assert!(matches!(value, IrExpr::Op(IrOp::Add, _)));
        } else {
            panic!("Expected Assign statement");
        }
    }

    #[test]
    fn test_lift_mov() {
        let mut ctx = LifterContext::new();

        let instr = DecodedInstruction {
            address: 0x08000004,
            opcode: "MOV".to_string(),
            operands: vec![
                Operand::Register(0),   // rd = r0
                Operand::Immediate(42), // immediate = 42
            ],
            condition: Some(IrCondition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };

        let statements = lift_data_processing(&mut ctx, &instr);
        assert_eq!(statements.len(), 1);

        // MOV r0, #42 -> r0 = 42
        if let IrStatement::Assign { target: _, value } = &statements[0] {
            assert!(matches!(value, IrExpr::Value(IrValue::Constant(42))));
        } else {
            panic!("Expected Assign statement");
        }
    }

    #[test]
    fn test_lift_and() {
        let mut ctx = LifterContext::new();

        let instr = DecodedInstruction {
            address: 0x08000008,
            opcode: "AND".to_string(),
            operands: vec![
                Operand::Register(3),     // rd = r3
                Operand::Register(4),     // rs = r4
                Operand::Immediate(0xFF), // immediate = 0xFF
            ],
            condition: Some(IrCondition::Al),
            mode: ArmMode::Arm,
            raw: 0,
            sets_flags: false,
            width: 4,
            is_data: false,
        };

        let statements = lift_data_processing(&mut ctx, &instr);
        assert_eq!(statements.len(), 1);

        // AND r3, r4, #0xFF -> r3 = r4 & 0xFF
        if let IrStatement::Assign { value, .. } = &statements[0] {
            assert!(matches!(value, IrExpr::Op(IrOp::And, _)));
        } else {
            panic!("Expected Assign statement");
        }
    }
}
