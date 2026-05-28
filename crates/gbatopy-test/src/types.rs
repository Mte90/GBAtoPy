use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub enum TestStatus {
    Pass,
    Fail,
    Error,
    Skipped,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestResult {
    pub name: String,
    pub test_type: String,
    pub status: TestStatus,
    pub message: String,
    pub duration: Duration,
}

impl TestResult {
    pub fn error(name: &str, test_type: &str, message: &str, duration: Duration) -> Self {
        Self {
            name: name.to_string(),
            test_type: test_type.to_string(),
            status: TestStatus::Error,
            message: message.to_string(),
            duration,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestSuiteResult {
    pub tests: Vec<TestResult>,
}
