use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("Failed to launch mGBA: {0}")]
    MgbaLaunch(String),

    #[error("Lua script failure: {0}")]
    ScriptFailure(String),

    #[error("Failed to parse trace: {0}")]
    ParseError(String),

    #[error("Trace collection timed out")]
    Timeout,

    #[error("Failed to load ROM: {0}")]
    RomLoad(String),

    #[error("Falling back to static-only mode: {0}")]
    Fallback(String),

    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    JsonError(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, Error>;
