use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestConfig {
    pub roms_dir: PathBuf,
    pub output_dir: PathBuf,
    pub parallel: usize,
    #[serde(default, alias = "test")]
    pub tests: Vec<TestEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TestEntry {
    pub name: String,
    pub rom_path: PathBuf,
    pub test_type: TestType,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub enum TestType {
    Smoke,
    ScreenshotGolden,
    ScreenshotMgba,
    EwramDump,
    PassFailScreen,
    AssertionText,
}
