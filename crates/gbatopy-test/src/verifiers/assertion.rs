use crate::config::TestEntry;
use crate::types::{TestResult, TestStatus};
use super::Verifier;
use std::path::Path;
use std::time::Instant;

// Reuse analyze_screenshot from pass_fail module
use super::pass_fail::{analyze_screenshot, ScreenAnalysis};

pub struct AssertionTextVerifier;

impl Verifier for AssertionTextVerifier {
    fn verify(&self, entry: &TestEntry, artifacts_dir: &Path) -> TestResult {
        let start = Instant::now();
        let test_name = entry.name.clone();
        let test_type_str = format!("{:?}", entry.test_type);

        log::info!("[Assertion Text] Testing {}...", test_name);

        let rom_path = entry.rom_path.to_string_lossy().to_string();
        let rom_stem = entry.rom_path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        let transpiled_py = artifacts_dir.join(format!("{}.py", rom_stem));
        let screenshot_path = artifacts_dir.join("transpiled.png");

        // Step 1: Transpile ROM
        if let Err(e) = transpile_rom(&rom_path, &transpiled_py) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Transpilation failed: {}", e),
                duration: start.elapsed(),
            };
        }

        log::info!("[Assertion Text] Transpilation succeeded for {}", test_name);

        // Step 2: Capture screenshot
        let frames = 60;
        if let Err(e) = capture_screenshot(&transpiled_py, &screenshot_path, frames) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Screenshot capture failed: {}", e),
                duration: start.elapsed(),
            };
        }

        log::info!("[Assertion Text] Screenshot captured for {}", test_name);

        // Step 3: Analyze screenshot (reuse from pass_fail)
        let analysis = match analyze_screenshot(&screenshot_path) {
            Ok(analysis) => analysis,
            Err(e) => {
                return TestResult {
                    name: test_name.clone(),
                    test_type: test_type_str.clone(),
                    status: TestStatus::Error,
                    message: format!("Screenshot analysis failed: {}", e),
                    duration: start.elapsed(),
                };
            }
        };

        // Step 4: Report results
        match analysis {
            ScreenAnalysis::BlankOrGreen => {
                log::info!("[Assertion Text] PASS: {} (blank/green screen)", test_name);
                TestResult {
                    name: test_name,
                    test_type: test_type_str,
                    status: TestStatus::Pass,
                    message: "Pass screen detected (blank or green)".to_string(),
                    duration: start.elapsed(),
                }
            }
            ScreenAnalysis::HasContent(ratio) => {
                log::error!(
                    "[Assertion Text] FAIL: {} ({}% visible content)",
                    test_name,
                    ratio * 100.0
                );
                TestResult {
                    name: test_name,
                    test_type: test_type_str,
                    status: TestStatus::Fail,
                    message: format!("Assertion failure screen: {:.1}% visible content", ratio * 100.0),
                    duration: start.elapsed(),
                }
            }
        }
    }

    fn name(&self) -> &'static str {
        "assertion_text"
    }
}

fn transpile_rom(rom_path: &str, output: &Path) -> Result<(), Box<dyn std::error::Error>> {
    use duct::cmd;
    let bin = "target/debug/gbatopy-cli";
    
    cmd!(bin, "pipeline", "--rom", rom_path, "--output", output.to_string_lossy().as_ref())
        .run()?;
    
    if !output.exists() {
        return Err("Output file not created".into());
    }
    
    Ok(())
}

fn capture_screenshot(py_file: &Path, screenshot_path: &Path, frames: u32) -> Result<(), Box<dyn std::error::Error>> {
    use duct::cmd;
    let frame_arg = format!("--frame={}", frames);
    let screenshot_arg = format!("--screenshot={}", screenshot_path.to_string_lossy());
    
    cmd!(
        "python3",
        py_file.to_string_lossy().as_ref(),
        "--headless",
        &frame_arg,
        &screenshot_arg
    )
    .env("SDL_VIDEODRIVER", "dummy")
    .run()?;
    
    if !screenshot_path.exists() {
        return Err("Screenshot file not created".into());
    }
    
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_verifier_name() {
        let verifier = AssertionTextVerifier;
        assert_eq!(verifier.name(), "assertion_text");
    }
}
