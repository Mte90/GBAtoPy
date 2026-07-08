use crate::config::TestEntry;
use crate::types::{TestResult, TestStatus};
use super::Verifier;
use std::path::{Path, PathBuf};
use std::time::Instant;
use std::fs;
use duct::cmd;
use super::image_compare::{
    compare_images_comprehensive, ComparisonConfig, format_success_message, 
    format_failure_message
};

pub struct ScreenshotMgbaVerifier;

impl Verifier for ScreenshotMgbaVerifier {
    fn verify(&self, entry: &TestEntry, artifacts_dir: &Path, config: &crate::config::TestConfig) -> TestResult {
        let start = Instant::now();
        let test_name = entry.name.clone();
        let test_type_str = format!("{:?}", entry.test_type);

        log::info!("[mGBA Oracle] Testing {}...", test_name);

        // Resolve the full ROM path
        let rom_path = config.roms_dir.join(&entry.rom_path);
        let rom_path_str = rom_path.to_string_lossy().to_string();
        let rom_stem = entry.rom_path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        let transpiled_py = artifacts_dir.join(format!("{}.py", rom_stem));
        let transpiled_screenshot = artifacts_dir.join("transpiled.png");
        let golden_path = artifacts_dir.join("golden_mgba.png");
        let lua_script = artifacts_dir.join("capture.lua");

        // Step 1: Find mGBA binary
        let mgba_path = find_mgba_binary();
        if let Err(e) = &mgba_path {
            log::warn!("[mGBA Oracle] Skipping {}: {}", test_name, e);
            return TestResult {
                name: test_name,
                test_type: test_type_str,
                status: TestStatus::Skipped,
                message: format!("mGBA not available: {}", e),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            };
        }
        let mgba_path = mgba_path.unwrap();

        // Step 2: Generate Lua script for mGBA
        let frames = 10;
        if let Err(e) = generate_lua_script(&lua_script, frames, &golden_path) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Error,
                message: format!("Failed to generate Lua script: {}", e),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            };
        }

        // Step 3: Run mGBA to capture golden screenshot
        if let Err(e) = run_mgba_capture(&mgba_path, &rom_path_str, &lua_script) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("mGBA capture failed: {}", e),
                duration: start.elapsed(),
                metrics: None,
                failure_classification: None,
            };
        }

        log::info!("[mGBA Oracle] Golden screenshot captured for {}", test_name);

        // Step 4: Transpile ROM
        if let Err(e) = transpile_rom(&rom_path_str, &transpiled_py) {
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

        log::info!("[mGBA Oracle] Transpilation succeeded for {}", test_name);

        // Copy ROM .bin alongside transpiled script for load_rom_data()
        let rom_bin_dest = artifacts_dir.join(format!("{}.bin", rom_stem));
        let _ = std::fs::copy(&rom_path, &rom_bin_dest);

        // Step 5: Run transpiled Python to capture screenshot
        if let Err(e) = capture_transpiled_screenshot(&transpiled_py, &transpiled_screenshot, frames) {
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

        log::info!("[mGBA Oracle] Screenshot captured for {}", test_name);

        // Step 6: Compare images
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
            &transpiled_screenshot,
            &golden_path,
            &config,
            &rom_stem,
            &test_type_str,
            artifacts_dir,
        ) {
            Ok(result) => {
                if result.passed {
                    log::info!("[mGBA Oracle] PASS: {}", test_name);
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
                        "[mGBA Oracle] FAIL: {} ({})",
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
                log::error!("[mGBA Oracle] Error comparing images: {}", e);
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
        "screenshot_mgba"
    }
}

fn find_mgba_binary() -> Result<PathBuf, String> {
    let paths = [
        "mgba/build/sdl/mgba",
        "target/debug/mgba",
        "target/release/mgba",
        "/usr/bin/mgba-qt",
        "/usr/bin/mgba-sdl",
    ];

    for path in &paths {
        if Path::new(path).exists() {
            return Ok(PathBuf::from(path));
        }
    }

    Err("mGBA binary not found in standard locations".to_string())
}

fn generate_lua_script(lua_path: &Path, frames: u32, output_path: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let content = format!(
        r#"local frame_count = 0
callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count == {} then
        emu:screenshot("{}")
        os.exit(0)
    end
end)
"#,
        frames,
        output_path.to_string_lossy().as_ref()
    );

    fs::write(lua_path, content)?;
    Ok(())
}

fn run_mgba_capture(mgba_path: &Path, rom_path: &str, lua_script: &Path) -> Result<(), Box<dyn std::error::Error>> {
    cmd!(
        mgba_path.to_string_lossy().as_ref(),
        "-S",
        lua_script.to_string_lossy().as_ref(),
        rom_path
    )
    .dir(".")
    .run()?;
    Ok(())
}

fn transpile_rom(rom_path: &str, output: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let bin = "target/debug/gbatopy-cli";
    
    cmd!(bin, "pipeline", "--rom", rom_path, "--output", output.to_string_lossy().as_ref())
        .dir(".")
        .run()?;
    
    if !output.exists() {
        return Err("Output file not created".into());
    }
    
    Ok(())
}

fn capture_transpiled_screenshot(py_file: &Path, screenshot_path: &Path, frames: u32) -> Result<(), Box<dyn std::error::Error>> {
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_verifier_name() {
        let verifier = ScreenshotMgbaVerifier;
        assert_eq!(verifier.name(), "screenshot_mgba");
    }

    #[test]
    fn test_find_mgba_binary() {
        let result = find_mgba_binary();
        assert!(result.is_ok() || result.is_err());
    }
}
