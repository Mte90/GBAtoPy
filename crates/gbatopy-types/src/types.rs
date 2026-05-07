use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GbaType {
    I8,
    I16,
    I32,
    U8,
    U16,
    U32,
    Bool,
    Ptr(Box<GbaType>),
    Array {
        element: Box<GbaType>,
        size: usize,
    },
    Struct {
        fields: Vec<(String, GbaType)>,
    },
    Function {
        params: Vec<GbaType>,
        ret: Box<GbaType>,
    },
    Void,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum TypeSource {
    Static,
    Oracle,
    Heuristic,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypeInfo {
    pub name: String,
    pub gba_type: GbaType,
    pub confidence: f32,
    pub source: TypeSource,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TypedIr {
    pub module: IrModule,
    pub type_map: HashMap<String, TypeInfo>,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ArmMode {
    Arm,
    Thumb,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum IrValue {
    Constant(u32),
    Variable { name: String, version: u32 },
    Register(u8),
    Flags { n: bool, z: bool, c: bool, v: bool },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum IrStatement {
    Assign {
        target: IrValue,
        value: IrValue,
    },
    Store {
        address: IrValue,
        value: IrValue,
        size: u8,
    },
    Load {
        target: IrValue,
        address: IrValue,
        size: u8,
    },
    Branch {
        condition: Option<Condition>,
        target: String,
    },
    Call {
        target: String,
        args: Vec<IrValue>,
    },
    Return {
        value: Option<IrValue>,
    },
    Phi {
        target: IrValue,
        sources: Vec<(String, IrValue)>,
    },
    Nop,
    ModeSwitch {
        new_mode: ArmMode,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IrBlock {
    pub label: String,
    pub statements: Vec<IrStatement>,
    pub predecessors: Vec<String>,
    pub successors: Vec<String>,
    pub mode: ArmMode,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IrFunction {
    pub name: String,
    pub address: u32,
    pub params: Vec<IrValue>,
    pub blocks: Vec<IrBlock>,
    pub mode: ArmMode,
    pub mode_switches: Vec<(u32, ArmMode)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IrGlobal {
    pub name: String,
    pub address: u32,
    pub size: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IrModule {
    pub functions: Vec<IrFunction>,
    pub globals: Vec<IrGlobal>,
}

pub type Result<T> = std::result::Result<T, super::Error>;
