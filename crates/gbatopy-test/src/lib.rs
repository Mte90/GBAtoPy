pub mod config;
pub mod types;
pub mod runner;
pub mod report;
pub mod coverage;
pub mod verifiers;

pub use config::TestConfig;
pub use types::{TestResult, TestStatus, TestSuiteResult};
pub use verifiers::get_verifier;
pub use report::Reporter;

pub fn placeholder() -> &'static str {
    "gbatopy-test"
}
