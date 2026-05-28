use rayon::prelude::*;
use std::path::PathBuf;

use crate::config::{TestConfig, TestEntry, TestType};
use crate::types::{TestResult, TestStatus, TestSuiteResult};
use crate::verifiers::get_verifier;

/// Test runner that orchestrates parallel test execution
pub struct TestRunner {
    config: TestConfig,
}

impl TestRunner {
    /// Create a new test runner from configuration
    pub fn from_config(config: TestConfig) -> Self {
        Self { config }
    }

    /// Run all tests, return summary
    pub fn run_all(&self, entries: &[TestEntry]) -> TestSuiteResult {
        let results: Vec<TestResult> = entries
            .par_iter()
            .map(|entry| self.run_single(entry))
            .collect();
        TestSuiteResult { tests: results }
    }

    /// Run a single test entry through its verifier
    fn run_single(&self, entry: &TestEntry) -> TestResult {
        let verifier = get_verifier(&entry.test_type);
        let artifacts_dir = self.config.output_dir.join(&entry.name);

        // Create artifacts dir for this test
        std::fs::create_dir_all(&artifacts_dir).ok();

        let result = verifier.verify(entry, &artifacts_dir);
        log::info!(
            "[{}] {} - {:?}",
            match result.status {
                TestStatus::Pass => "PASS",
                TestStatus::Fail => "FAIL",
                TestStatus::Error => "ERROR",
                TestStatus::Skipped => "SKIP",
            },
            entry.name,
            result.status
        );
        result
    }

    /// Filter and run only specific test types
    pub fn run_by_type(&self, entries: &[TestEntry], test_type: &TestType) -> TestSuiteResult {
        let filtered: Vec<&TestEntry> = entries.iter()
            .filter(|e| &e.test_type == test_type)
            .collect();
        let results: Vec<TestResult> = filtered
            .par_iter()
            .map(|e| self.run_single(e))
            .collect();
        TestSuiteResult { tests: results }
    }

    /// Run a single test by name
    pub fn run_test(&self, entries: &[TestEntry], test_name: &str) -> Option<TestResult> {
        entries.iter()
            .find(|e| e.name == test_name)
            .map(|e| self.run_single(e))
    }

    /// Resolve the full path to a ROM file
    pub fn resolve_rom_path(entry: &TestEntry, config: &TestConfig) -> PathBuf {
        config.roms_dir.join(&entry.rom_path)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_rom_path() {
        let config = TestConfig {
            roms_dir: PathBuf::from("test_roms/roms"),
            output_dir: PathBuf::from("artifacts"),
            parallel: 4,
        };
        let entry = TestEntry {
            name: "stripes".to_string(),
            rom_path: PathBuf::from("stripes.gba"),
            test_type: TestType::Smoke,
        };

        let path = TestRunner::resolve_rom_path(&entry, &config);
        assert_eq!(path, PathBuf::from("test_roms/roms/stripes.gba"));
    }

    #[test]
    fn test_run_all_creates_results() {
        let config = TestConfig {
            roms_dir: PathBuf::from("test_roms/roms"),
            output_dir: PathBuf::from("artifacts"),
            parallel: 4,
        };
        let runner = TestRunner::from_config(config);
        let entries = vec![
            TestEntry {
                name: "test1".to_string(),
                rom_path: PathBuf::from("test1.gba"),
                test_type: TestType::Smoke,
            },
            TestEntry {
                name: "test2".to_string(),
                rom_path: PathBuf::from("test2.gba"),
                test_type: TestType::ScreenshotGolden,
            },
        ];

        let result = runner.run_all(&entries);
        assert_eq!(result.tests.len(), 2);
    }
}
