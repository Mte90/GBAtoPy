use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("Invalid ROM: {0}")]
    InvalidRom(String),

    #[error("Unknown opcode at address {address}: 0x{opcode:08X}")]
    UnknownOpcode { address: u32, opcode: u32 },

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, Error>;
