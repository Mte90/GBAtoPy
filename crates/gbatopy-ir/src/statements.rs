use serde::{Deserialize, Serialize};

use crate::values::IrExpr;
use crate::{ArmMode, Condition};

/// All statement types in the IR
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum IrStatement {
    /// Assignment: target = value
    Assign { target: IrExpr, value: IrExpr },

    /// Memory store: [address] = value (size in bytes)
    Store {
        address: IrExpr,
        value: IrExpr,
        size: u8,
    },

    /// Memory load: target = [address] (size in bytes)
    Load {
        target: IrExpr,
        address: IrExpr,
        size: u8,
    },

    /// Conditional or unconditional branch
    Branch {
        condition: Option<Condition>,
        target: String,
    },

    /// Function call
    Call { target: String, args: Vec<IrExpr> },

    /// Return from function
    Return { value: Option<IrExpr> },

    /// Phi node for SSA (selects value from predecessor block)
    Phi {
        target: IrExpr,
        sources: Vec<(String, IrExpr)>, // (block_label, value)
    },

    /// No operation
    Nop,

    /// Mode switch (ARM <-> Thumb) at given address
    ModeSwitch { new_mode: ArmMode, address: u32 },

    /// Software interrupt
    Swi { number: u32 },

    /// Signed memory load (LDRSB, LDRSH)
    SignedLoad {
        target: IrExpr,
        address: IrExpr,
        size: u8,
    },
}

impl IrStatement {
    /// Create an assignment statement
    pub fn assign(target: IrExpr, value: IrExpr) -> Self {
        IrStatement::Assign { target, value }
    }

    /// Create a load statement
    pub fn load(target: IrExpr, address: IrExpr, size: u8) -> Self {
        IrStatement::Load {
            target,
            address,
            size,
        }
    }

    /// Create a store statement
    pub fn store(address: IrExpr, value: IrExpr, size: u8) -> Self {
        IrStatement::Store {
            address,
            value,
            size,
        }
    }
}
