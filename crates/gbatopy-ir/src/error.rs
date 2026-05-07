use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("Invalid function at address {0}")]
    InvalidFunction(u32),

    #[error("Invalid block: {0}")]
    InvalidBlock(String),

    #[error("SSA error: {0}")]
    SsaError(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, Error>;