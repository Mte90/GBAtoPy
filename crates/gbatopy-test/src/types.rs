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
    pub fn pass(name: &str, test_type: &str, message: &str, duration: Duration) -> Self {
        Self {
            name: name.to_string(),
            test_type: test_type.to_string(),
            status: TestStatus::Pass,
            message: message.to_string(),
            duration,
        }
    }

    pub fn fail(name: &str, test_type: &str, message: &str, duration: Duration) -> Self {
        Self {
            name: name.to_string(),
            test_type: test_type.to_string(),
            status: TestStatus::Fail,
            message: message.to_string(),
            duration,
        }
    }

    pub fn skip(name: &str, test_type: &str, message: &str, duration: Duration) -> Self {
        Self {
            name: name.to_string(),
            test_type: test_type.to_string(),
            status: TestStatus::Skipped,
            message: message.to_string(),
            duration,
        }
    }

    pub fn error(name: &str, test_type: &str, message: &str, duration: Duration) -> Self {
        Self {
            name: name.to_string(),
            test_type: test_type.to_string(),
            status: TestStatus::Error,
            message: message.to_string(),
            duration,
        }
    }

    pub fn is_pass(&self) -> bool {
        self.status == TestStatus::Pass
    }

    pub fn is_fail(&self) -> bool {
        matches!(self.status, TestStatus::Fail | TestStatus::Error)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestSuiteResult {
    pub tests: Vec<TestResult>,
}
