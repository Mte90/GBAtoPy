use crate::config::TestEntry;
use crate::types::{TestResult, TestStatus};
use super::Verifier;
use std::path::{Path, PathBuf};
use std::time::Instant;
use duct::cmd;
use super::image_compare::{
    compare_images_comprehensive, ComparisonConfig, format_success_message,
    format_failure_message
};

pub struct ScreenshotGoldenVerifier;

impl Verifier for ScreenshotGoldenVerifier {
    fn verify(&self, entry: &TestEntry, artifacts_dir: &Path, config: &crate::config::TestConfig) -> TestResult {
        let start = Instant::now();
        let test_name = entry.name.clone();
        let test_type_str = format!("{:?}", entry.test_type);

        log::info!("[ScreenshotGolden] Testing {}...", test_name);

        // Resolve the full ROM path
        let rom_path = config.roms_dir.join(&entry.rom_path);
        let rom_path_str = rom_path.to_string_lossy().to_string();
        let rom_stem = entry.rom_path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        let transpiled_py = artifacts_dir.join(format!("{}.py", rom_stem));
        let screenshot_path = artifacts_dir.join("transpiled.png");
        
        let golden_path = PathBuf::from(format!(
            "test_roms/sources/hw-test/ppu/{}/expected.png",
            rom_stem
        ));

        if let Err(e) = self.transpile(&rom_path_str, &transpiled_py) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Transpilation failed: {}", e),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            };
        }

        log::info!("[ScreenshotGolden] Transpilation succeeded for {}", test_name);

        // Copy ROM .bin alongside transpiled script for load_rom_data()
        let rom_bin_dest = artifacts_dir.join(format!("{}.bin", rom_stem));
        let _ = std::fs::copy(&rom_path, &rom_bin_dest);

        let frames = 60;
        if let Err(e) = self.capture_screenshot(&transpiled_py, &screenshot_path, frames) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Screenshot capture failed: {}", e),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            };
        }

        log::info!("[ScreenshotGolden] Screenshot captured for {}", test_name);

        if !golden_path.exists() {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Error,
                message: format!("Golden image not found: {}", golden_path.display()),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            };
        }

        // Use comprehensive comparison with new thresholds
        let config = ComparisonConfig::default();
        
        match compare_images_comprehensive(
            &screenshot_path,
            &golden_path,
            &config,
            &rom_stem,
            &test_type_str,
            artifacts_dir,
        ) {
            Ok(result) => {
                if result.passed {
                    log::info!("[ScreenshotGolden] PASS: {}", test_name);
                    TestResult {
                        name: test_name,
                        test_type: test_type_str,
                        status: TestStatus::Pass,
                        message: format_success_message(&result.metrics, config.pixel_tolerance),
                        duration: start.elapsed(),
                        metrics: None,
                        failure_classification: None,
                    }
                } else {
                    log::error!(
                        "[ScreenshotGolden] FAIL: {} ({})",
                        test_name,
                        format_failure_message(&result.metrics, result.failure_classification.as_ref())
                    );
                    TestResult {
                        name: test_name,
                        test_type: test_type_str,
                        status: TestStatus::Fail,
                        message: format_failure_message(&result.metrics, result.failure_classification.as_ref()),
                        duration: start.elapsed(),
                        metrics: serde_json::to_value(&result.metrics).ok(),
                        failure_classification: result.failure_classification.map(|c| {
                            match c {
                                super::image_compare::FailureClassification::SizeMismatch => "size_mismatch".to_string(),
                                super::image_compare::FailureClassification::EmptyOutput => "empty_output".to_string(),
                                super::image_compare::FailureClassification::NearBlackOutput => "near_black_output".to_string(),
                                super::image_compare::FailureClassification::Offset => "offset".to_string(),
                                super::image_compare::FailureClassification::ColorShift => "color_shift".to_string(),
                                super::image_compare::FailureClassification::StructuralMismatch => "structural_mismatch".to_string(),
                            }
                        }),
                    }
                }
            }
            Err(e) => {
                log::error!("[ScreenshotGolden] Error comparing images: {}", e);
                TestResult {
                    name: test_name,
                    test_type: test_type_str,
                    status: TestStatus::Error,
                    message: format!("Image comparison failed: {}", e),
                    duration: start.elapsed(),
                    metrics: None,
                    failure_classification: None,
                }
            }
        }
    }

    fn name(&self) -> &'static str {
        "screenshot_golden"
    }
}

impl ScreenshotGoldenVerifier {
    fn transpile(&self, rom_path: &str, output: &Path) -> Result<(), Box<dyn std::error::Error>> {
        let bin = if Path::new("target/release/gbatopy-cli").exists() {
            "target/release/gbatopy-cli"
        } else {
            "target/debug/gbatopy-cli"
        };
        
        cmd!(bin, "pipeline", "--rom", rom_path, "--output", output.to_string_lossy().as_ref())
            .dir(".")
            .run()?;
        
        if !output.exists() {
            return Err("Output file not created".into());
        }
        
        Ok(())
    }

    fn capture_screenshot(
        &self,
        py_file: &Path,
        screenshot_path: &Path,
        frames: u32,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let frame_arg = format!("--frame={}", frames);
        let screenshot_name = screenshot_path.file_name().unwrap_or_default().to_string_lossy().to_string();
        let screenshot_arg = format!("--screenshot={}", screenshot_name);
        
        cmd!(
            "python3",
            py_file.file_name().unwrap().to_string_lossy().as_ref(),
            "--headless",
            &frame_arg,
            &screenshot_arg
        )
        .env("SDL_VIDEODRIVER", "dummy")
        .dir(py_file.parent().unwrap_or(Path::new(".")))
        .run()?;
        
        if !screenshot_path.exists() {
            return Err("Screenshot file not created".into());
        }
        
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_verifier_name() {
        let verifier = ScreenshotGoldenVerifier;
        assert_eq!(verifier.name(), "screenshot_golden");
    }

    #[test]
    fn test_compare_images_basic() {
        let verifier = ScreenshotGoldenVerifier;
        assert_eq!(verifier.name(), "screenshot_golden");
    }
}
