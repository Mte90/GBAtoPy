use serde::{Deserialize, Serialize};

/// All arithmetic, logical, and comparison operations
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub enum IrOp {
    // Arithmetic
    Add,
    Sub,
    Mul,
    Div,
    Rem,
    Neg,

    // Logical
    And,
    Or,
    Xor,
    Not,

    // Shifts
    Shl,
    Shr, // Logical shift right
    Asr, // Arithmetic shift right
    Ror,

    // Comparisons
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,

    // Type conversions
    ZeroExtend,
    SignExtend,
    Truncate,
}

impl std::fmt::Display for IrOp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            IrOp::Add => "add",
            IrOp::Sub => "sub",
            IrOp::Mul => "mul",
            IrOp::Div => "div",
            IrOp::Rem => "rem",
            IrOp::Neg => "neg",
            IrOp::And => "and",
            IrOp::Or => "or",
            IrOp::Xor => "xor",
            IrOp::Not => "not",
            IrOp::Shl => "shl",
            IrOp::Shr => "shr",
            IrOp::Asr => "asr",
            IrOp::Ror => "ror",
            IrOp::Eq => "eq",
            IrOp::Ne => "ne",
            IrOp::Lt => "lt",
            IrOp::Le => "le",
            IrOp::Gt => "gt",
            IrOp::Ge => "ge",
            IrOp::ZeroExtend => "zext",
            IrOp::SignExtend => "sext",
            IrOp::Truncate => "trunc",
        };
        write!(f, "{}", s)
    }
}
