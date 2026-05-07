use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("Type inference error: {0}")]
    InferenceError(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, Error>;
