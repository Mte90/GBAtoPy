use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Default)]
pub enum GbaType {
    I8,
    I16,
    I32,
    U8,
    U16,
    U32,
    Bool,
    Ptr,
    Array {
        size: usize,
    },
    Struct,
    Function,
    Void,
    #[default]
    Unknown,
}
