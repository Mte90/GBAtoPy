//! GBAtoPy test harness crate.
//!
//! This crate provides infrastructure for running and verifying GBA transpilation tests.
//! Modules:
//! - `config`: Test configuration and entry points
//! - `types`: Test result types and status enums
//! - `runner`: Test execution logic
//! - `report`: Test reporting and output formatting
//! - `verifiers`: Verification strategies for different test types

pub mod config;
pub mod types;
pub mod runner;
pub mod report;
pub mod verifiers;

pub use config::TestConfig;
pub use types::{TestResult, TestStatus, TestSuiteResult};
pub use verifiers::get_verifier;
pub use report::Reporter;

