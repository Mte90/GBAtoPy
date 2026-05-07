pub mod error;
pub mod mgba;
pub mod types;

pub use error::{Error, Result};
pub use mgba::{MgbaConfig, MgbaOracle};
pub use types::{
    consume_traces, AccessKind, MemoryAccess, OracleMode, OracleTrace, RegisterState, TraceEntry,
    TraceInsights, TraceMetadata,
};
