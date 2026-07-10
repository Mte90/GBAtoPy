use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ShiftType {
    Lsl,
    Lsr,
    Asr,
    Ror,
}

impl ShiftType {
    pub fn from_bits(bits: u8) -> Option<ShiftType> {
        match bits {
            0b00 => Some(ShiftType::Lsl),
            0b01 => Some(ShiftType::Lsr),
            0b10 => Some(ShiftType::Asr),
            0b11 => Some(ShiftType::Ror),
            _ => None,
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            ShiftType::Lsl => "lsl",
            ShiftType::Lsr => "lsr",
            ShiftType::Asr => "asr",
            ShiftType::Ror => "ror",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ShiftAmount {
    Immediate(u8),
    Register(u8),
}

impl ShiftAmount {
    pub fn value(&self) -> u32 {
        match self {
            ShiftAmount::Immediate(v) => *v as u32,
            ShiftAmount::Register(r) => *r as u32,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum AddressingMode {
    ImmediateOffset(i32),
    RegisterOffset(u8),
    ScaledRegisterOffset {
        reg: u8,
        shift: ShiftType,
        amount: u8,
    },
    PreIndexed {
        base: u8,
        offset: i32,
        writeback: bool,
    },
    PostIndexed {
        base: u8,
        offset: i32,
        writeback: bool,
    },
    PostIndexedRegister {
        base: u8,
        reg: u8,
    },
    Multi {
        base: u8,
        registers: Vec<u8>,
        increment: bool,
        pre_index: bool,
        writeback: bool,
    },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Operand {
    Register(u8),
    Immediate(u32),
    ShiftedRegister {
        reg: u8,
        shift: ShiftType,
        amount: ShiftAmount,
    },
    MemoryAddress {
        base: u8,
        offset: AddressingMode,
        writeback: bool,
    },
    PcRelative(i32),
    Label(String),
}

impl Operand {
    pub fn display(&self) -> String {
        match self {
            Operand::Register(r) => format!("r{}", r),
            Operand::Immediate(i) => format!("#{}", i),
            Operand::ShiftedRegister { reg, shift, amount } => {
                let amount_str = match amount {
                    ShiftAmount::Immediate(v) => format!(", {}", v),
                    ShiftAmount::Register(r) => format!(", r{}", r),
                };
                format!("r{}{}{}", reg, shift.name(), amount_str)
            }
            Operand::MemoryAddress { base, offset, .. } => {
                format!("[r{}, {:?}]", base, offset)
            }
            Operand::PcRelative(offset) => format!("pc, #{}", offset),
            Operand::Label(s) => s.clone(),
        }
    }

    pub fn to_python(&self) -> String {
        match self {
            Operand::Register(r) => format!("r{}", r),
            Operand::Immediate(i) => i.to_string(),
            Operand::ShiftedRegister { reg, shift, amount } => {
                let amount_str = match amount {
                    ShiftAmount::Immediate(v) => format!(", {}", v),
                    ShiftAmount::Register(r) => format!(", r{}", r),
                };
                format!("r{}{}{}", reg, shift.name(), amount_str)
            }
            Operand::MemoryAddress { base, offset, .. } => {
                format!("[r{}, {:?}]", base, offset)
            }
            Operand::PcRelative(offset) => format!("pc + {}", offset),
            Operand::Label(s) => s.clone(),
        }
    }

    /// Format operand for Python codegen output.
    /// - Register: returns just the number (e.g. "0", "15") for use in registers[]
    /// - Immediate: returns just the number without '#' prefix
    pub fn to_codegen(&self) -> String {
        match self {
            Operand::Register(r) => r.to_string(),
            Operand::Immediate(i) => i.to_string(),
            Operand::ShiftedRegister { reg, shift, amount } => {
                let amount_str = match amount {
                    ShiftAmount::Immediate(v) => format!(", {}", v),
                    ShiftAmount::Register(r) => format!(", r{}", r),
                };
                format!("reg|{}|{}r{}", reg, shift.name(), amount_str)
            }
            Operand::MemoryAddress { base, offset, .. } => {
                format!("[r{}, {:?}]", base, offset)
            }
            Operand::PcRelative(offset) => format!("pc + {}", offset),
            Operand::Label(s) => s.clone(),
        }
    }
}
