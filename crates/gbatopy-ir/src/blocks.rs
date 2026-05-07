use serde::{Deserialize, Serialize};

use crate::types::GbaType;
use crate::values::IrExpr;
use crate::ArmMode;

/// A basic block in the control flow graph
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IrBlock {
    /// Unique label for this block
    pub label: String,

    /// Statements in this block (last one is usually Branch or Return)
    pub statements: Vec<IrExpr>,

    /// Predecessor blocks (blocks that can jump here)
    pub predecessors: Vec<String>,

    /// Successor blocks (blocks this block can jump to)
    pub successors: Vec<String>,

    /// CPU mode at block entry (ARM or Thumb)
    pub mode: ArmMode,
}

/// A function in the IR
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IrFunction {
    /// Function name (may be mangled or demangled)
    pub name: String,

    /// Starting address in ROM
    pub address: u32,

    /// Function parameters (SSA variables)
    pub params: Vec<IrExpr>,

    /// Basic blocks in this function
    pub blocks: Vec<IrBlock>,

    /// Return type (None for void)
    pub return_type: Option<GbaType>,

    /// Function entry mode (ARM or Thumb)
    pub mode: ArmMode,

    /// All mode switches in this function (address -> new_mode)
    pub mode_switches: Vec<(u32, ArmMode)>,
}

impl IrFunction {
    /// Find all mode switches before a given address
    pub fn mode_before(&self, address: u32) -> Option<ArmMode> {
        self.mode_switches
            .iter()
            .filter(|(addr, _)| *addr < address)
            .map(|(_, mode)| *mode)
            .last()
            .or(Some(self.mode))
    }
}
