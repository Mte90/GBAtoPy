use serde::{Deserialize, Serialize};

use crate::{ArmMode, Condition, Operand};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Function {
    pub name: String,
    pub address: u32,
    pub size: u32,
    pub is_thumb: bool,
    pub mode_switches: Vec<(u32, ArmMode)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DisassemblyOutput {
    pub rom_path: String,
    pub base_address: u32,
    pub instructions: Vec<DecodedInstruction>,
    pub functions: Vec<Function>,
    pub mode_switches: Vec<(u32, ArmMode)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecodedInstruction {
    pub address: u32,
    pub opcode: String,
    pub operands: Vec<Operand>,
    pub condition: Option<Condition>,
    pub mode: ArmMode,
    pub raw: u32,
    pub sets_flags: bool,
    pub width: u8,
    /// Indicates this region is likely data rather than code
    pub is_data: bool,
}
