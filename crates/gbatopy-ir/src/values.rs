use serde::{Deserialize, Serialize};

use crate::types::GbaType;
use crate::{Condition, IrOp};

/// Represents a value in the IR (registers, constants, variables, flags)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum IrValue {
    /// Immediate constant value
    Constant(u32),

    /// SSA variable with type information
    Variable {
        name: String,
        version: u32,
        ty: GbaType,
    },

    /// CPU register (r0-r15)
    Register(u8),

    /// CPSR flags state
    Flags { n: bool, z: bool, c: bool, v: bool },
}

/// Represents an expression (computation) in the IR
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum IrExpr {
    /// Operation applied to sub-expressions
    Op(IrOp, Vec<IrExpr>),

    /// Value reference
    Value(IrValue),

    /// Conditional expression: condition ? true_val : false_val
    Conditional {
        condition: Condition,
        true_val: Box<IrExpr>,
        false_val: Box<IrExpr>,
    },

    /// Phi function for SSA (selection from multiple sources)
    Phi {
        sources: Vec<(String, IrExpr)>, // (block_label, value)
    },
}

impl IrExpr {
    /// Create a constant expression
    pub fn constant(val: u32) -> Self {
        IrExpr::Value(IrValue::Constant(val))
    }

    /// Create a register expression
    pub fn register(r: u8) -> Self {
        IrExpr::Value(IrValue::Register(r))
    }

    /// Create a variable expression
    pub fn variable(name: String, version: u32, ty: GbaType) -> Self {
        IrExpr::Value(IrValue::Variable { name, version, ty })
    }
}
