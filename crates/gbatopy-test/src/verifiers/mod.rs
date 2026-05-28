use crate::config::{TestEntry, TestType};
use crate::types::TestResult;
use std::path::Path;

pub trait Verifier: Send + Sync {
    fn verify(&self, entry: &TestEntry, artifacts_dir: &Path) -> TestResult;
    fn name(&self) -> &'static str;
}

pub fn get_verifier(test_type: &TestType) -> Box<dyn Verifier> {
    match test_type {
        TestType::Smoke => Box::new(smoke::SmokeVerifier),
        TestType::ScreenshotGolden => Box::new(screenshot::ScreenshotGoldenVerifier),
        TestType::ScreenshotMgba => Box::new(mgba_oracle::ScreenshotMgbaVerifier),
        TestType::EwramDump => Box::new(ewram::EwramDumpVerifier),
        TestType::PassFailScreen => Box::new(pass_fail::PassFailScreenVerifier),
        TestType::AssertionText => Box::new(assertion::AssertionTextVerifier),
    }
}

mod smoke;
mod screenshot;
mod mgba_oracle;
mod ewram;
mod pass_fail;
mod assertion;
