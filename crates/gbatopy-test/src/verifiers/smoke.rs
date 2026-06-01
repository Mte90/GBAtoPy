use crate::config::TestEntry;
use crate::types::{TestResult, TestStatus};
use super::Verifier;
use std::path::Path;
use std::time::Instant;

pub struct SmokeVerifier;

impl Verifier for SmokeVerifier {
    fn verify(&self, entry: &TestEntry, artifacts_dir: &Path, config: &crate::config::TestConfig) -> TestResult {
        let start = Instant::now();
        let test_name = entry.name.clone();
        let test_type_str = format!("{:?}", entry.test_type);

        log::info!("[Smoke] Transpiling {}...", entry.rom_path.display());

        // Resolve the full ROM path
        let rom_path = config.roms_dir.join(&entry.rom_path);
        log::debug!("[Smoke] ROM path resolved to: {}", rom_path.display());

        // Step 1: Run transpiler
        let output_path = artifacts_dir.join("output.py");
        let rom_path_str = rom_path.to_string_lossy().to_string();
        let output_path_str = output_path.to_string_lossy().to_string();
        
        let transpile_result = duct::cmd!(
            "cargo",
            "run",
            "-p",
            "gbatopy-cli",
            "--",
            "pipeline",
            "--rom",
            &rom_path_str,
            "--output",
            &output_path_str
        )
        .dir(".") // Run from project root
        .run();

        if let Err(e) = transpile_result {
            log::error!("[Smoke] Transpilation failed for {}: {}", test_name, e);
            return TestResult {
                name: test_name,
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Transpilation failed: {}", e),
                duration: start.elapsed(),
            };
        }

        log::info!("[Smoke] Transpilation succeeded for {}", test_name);

        // Step 2: Check Python syntax
        let syntax_result = duct::cmd!(
            "python3",
            "-m",
            "py_compile",
            output_path.to_string_lossy().as_ref()
        )
        .stdout_null()
        .stderr_null()
        .run();

        if let Err(e) = syntax_result {
            log::error!("[Smoke] Python syntax check failed for {}: {}", test_name, e);
            return TestResult {
                name: test_name,
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Python syntax error: {}", e),
                duration: start.elapsed(),
            };
        }

        log::info!("[Smoke] Python syntax OK for {}", test_name);

        TestResult {
            name: test_name,
            test_type: test_type_str,
            status: TestStatus::Pass,
            message: "Transpilation and syntax check passed".to_string(),
            duration: start.elapsed(),
        }
    }

    fn name(&self) -> &'static str {
        "smoke"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_smoke_verifier_name() {
        let verifier = SmokeVerifier;
        assert_eq!(verifier.name(), "smoke");
    }
}
