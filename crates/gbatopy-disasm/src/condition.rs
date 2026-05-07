use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Condition {
    Eq,
    Ne,
    Cs,
    Cc,
    Mi,
    Pl,
    Vs,
    Vc,
    Hi,
    Ls,
    Ge,
    Lt,
    Gt,
    Le,
    Al,
    Nv,
}

impl Condition {
    pub fn from_bits(bits: u8) -> Option<Condition> {
        match bits & 0xF {
            0b0000 => Some(Condition::Eq),
            0b0001 => Some(Condition::Ne),
            0b0010 => Some(Condition::Cs),
            0b0011 => Some(Condition::Cc),
            0b0100 => Some(Condition::Mi),
            0b0101 => Some(Condition::Pl),
            0b0110 => Some(Condition::Vs),
            0b0111 => Some(Condition::Vc),
            0b1000 => Some(Condition::Hi),
            0b1001 => Some(Condition::Ls),
            0b1010 => Some(Condition::Ge),
            0b1011 => Some(Condition::Lt),
            0b1100 => Some(Condition::Gt),
            0b1101 => Some(Condition::Le),
            0b1110 => Some(Condition::Al),
            0b1111 => Some(Condition::Nv),
            _ => None,
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            Condition::Eq => "eq",
            Condition::Ne => "ne",
            Condition::Cs => "cs",
            Condition::Cc => "cc",
            Condition::Mi => "mi",
            Condition::Pl => "pl",
            Condition::Vs => "vs",
            Condition::Vc => "vc",
            Condition::Hi => "hi",
            Condition::Ls => "ls",
            Condition::Ge => "ge",
            Condition::Lt => "lt",
            Condition::Gt => "gt",
            Condition::Le => "le",
            Condition::Al => "al",
            Condition::Nv => "nv",
        }
    }
}

pub fn decode_condition(bits: u8) -> Option<Condition> {
    Condition::from_bits(bits)
}
