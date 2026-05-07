use crate::blocks::IrBlock;
use crate::ops::IrOp;
use crate::values::IrValue;
use crate::IrExpr;

pub struct Optimizer;

impl Optimizer {
    pub fn new() -> Self {
        Self
    }

    pub fn run(&self, blocks: &mut [IrBlock]) {
        self.constant_folding(blocks);
    }

    fn constant_folding(&self, blocks: &mut [IrBlock]) {
        for block in blocks.iter_mut() {
            for stmt in block.statements.iter_mut() {
                self.fold_expr(stmt);
            }
        }
    }

    fn fold_expr(&self, expr: &mut IrExpr) {
        if let IrExpr::Op(op, args) = expr {
            if let Some(c) = self.fold_op(op, args) {
                *expr = IrExpr::Value(IrValue::Constant(c));
            }
        }
    }

    fn fold_op(&self, op: &IrOp, args: &[IrExpr]) -> Option<u32> {
        if args.len() != 2 {
            return None;
        }
        let IrExpr::Value(IrValue::Constant(a)) = &args[0] else {
            return None;
        };
        let IrExpr::Value(IrValue::Constant(b)) = &args[1] else {
            return None;
        };
        Some(match op {
            IrOp::Add => a.wrapping_add(*b),
            IrOp::Sub => a.wrapping_sub(*b),
            IrOp::And => a & b,
            IrOp::Or => a | b,
            IrOp::Xor => a ^ b,
            IrOp::Shl => a << b,
            IrOp::Shr => a >> b,
            _ => return None,
        })
    }
}

impl Default for Optimizer {
    fn default() -> Self {
        Self::new()
    }
}
