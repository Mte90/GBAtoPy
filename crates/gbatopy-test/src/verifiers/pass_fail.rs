use crate::config::TestEntry;
use crate::types::{TestResult, TestStatus};
use super::Verifier;
use std::path::Path;
use std::time::Instant;

pub struct PassFailScreenVerifier;

impl Verifier for PassFailScreenVerifier {
    fn verify(&self, entry: &TestEntry, artifacts_dir: &Path, config: &crate::config::TestConfig) -> TestResult {
        let start = Instant::now();
        let test_name = entry.name.clone();
        let test_type_str = format!("{:?}", entry.test_type);

        log::info!("[Pass/Fail Screen] Testing {}...", test_name);

        let rom_path = config.roms_dir.join(&entry.rom_path).to_string_lossy().to_string();
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
                metrics: None,
                failure_classification: None,
            };
        }

        // Copy ROM .bin alongside transpiled script for load_rom_data()
        let rom_bin_dest = artifacts_dir.join(format!("{}.bin", rom_stem));
        let _ = std::fs::copy(&rom_path, &rom_bin_dest);

        log::info!("[Pass/Fail Screen] Transpilation succeeded for {}", test_name);

        // Step 2: Capture screenshot
        let frames = 60;
        if let Err(e) = capture_screenshot(&transpiled_py, &screenshot_path, frames) {
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

        log::info!("[Pass/Fail Screen] Screenshot captured for {}", test_name);

        // Step 3: Analyze screenshot
        let analysis = match analyze_screenshot(&screenshot_path) {
            Ok(analysis) => analysis,
            Err(e) => {
                return TestResult {
                    name: test_name.clone(),
                    test_type: test_type_str.clone(),
                    status: TestStatus::Error,
                    message: format!("Screenshot analysis failed: {}", e),
                    duration: start.elapsed(),
                    metrics: None,
                    failure_classification: None,
                };
            }
        };

        // Step 4: Report results
        match analysis {
            ScreenAnalysis::BlankOrGreen => {
                log::info!("[Pass/Fail Screen] PASS: {} (blank/green screen)", test_name);
                TestResult {
                    name: test_name,
                    test_type: test_type_str,
                    status: TestStatus::Pass,
                    message: "Pass screen detected (blank or green)".to_string(),
                    duration: start.elapsed(),
                    metrics: None,
                    failure_classification: None,
                }
            }
            ScreenAnalysis::HasContent(ratio) => {
                log::error!(
                    "[Pass/Fail Screen] FAIL: {} ({}% visible content)",
                    test_name,
                    ratio * 100.0
                );
                TestResult {
                    name: test_name,
                    test_type: test_type_str,
                    status: TestStatus::Fail,
                    message: format!("Fail screen detected: {:.1}% visible content", ratio * 100.0),
                    duration: start.elapsed(),
                    metrics: None,
                    failure_classification: None,
                }
            }
        }
    }

    fn name(&self) -> &'static str {
        "pass_fail_screen"
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum ScreenAnalysis {
    BlankOrGreen,
    HasContent(f64), // Ratio of non-blank pixels
}

fn transpile_rom(rom_path: &str, output: &Path) -> Result<(), Box<dyn std::error::Error>> {
    use duct::cmd;
    let bin = "target/debug/gbatopy-cli";
    
    cmd!(bin, "pipeline", "--rom", rom_path, "--output", output.to_string_lossy().as_ref())
        .dir(".")
        .run()?;
    
    if !output.exists() {
        return Err("Output file not created".into());
    }
    
    Ok(())
}

fn capture_screenshot(py_file: &Path, screenshot_path: &Path, frames: u32) -> Result<(), Box<dyn std::error::Error>> {
    use duct::cmd;
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

/// Analyze screenshot to detect pass/fail screen
/// - Blank screen (any RGB > 30) < 1% → PASS
/// - Green screen (G > 200, R < 50, B < 50) > 95% → PASS  
/// - Otherwise → FAIL
pub fn analyze_screenshot(path: &Path) -> Result<ScreenAnalysis, Box<dyn std::error::Error>> {
    let img = image::open(path)?;
    let pixels = img.to_rgba8();
    
    let total_pixels = (pixels.width() * pixels.height()) as u32;
    let mut non_blank_pixels = 0u32;
    let mut green_pixels = 0u32;
    
    for pixel in pixels.pixels() {
        let r = pixel[0];
        let g = pixel[1];
        let b = pixel[2];
        
        // Check if pixel is "non-blank" (any channel > 30)
        if r > 30 || g > 30 || b > 30 {
            non_blank_pixels += 1;
        }
        
        // Check if pixel is "green" (G > 200, R < 50, B < 50)
        if g > 200 && r < 50 && b < 50 {
            green_pixels += 1;
        }
    }
    
    let non_blank_ratio = non_blank_pixels as f64 / total_pixels as f64;
    let green_ratio = green_pixels as f64 / total_pixels as f64;
    
    // Green screen detection: > 95% green pixels = PASS
    if green_ratio > 0.95 {
        return Ok(ScreenAnalysis::BlankOrGreen);
    }
    
    // Blank screen: < 1% non-blank pixels = PASS
    if non_blank_ratio < 0.01 {
        return Ok(ScreenAnalysis::BlankOrGreen);
    }
    
    // Otherwise, there's visible content = FAIL
    Ok(ScreenAnalysis::HasContent(non_blank_ratio))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_verifier_name() {
        let verifier = PassFailScreenVerifier;
        assert_eq!(verifier.name(), "pass_fail_screen");
    }

    #[test]
    fn test_analyze_blank_screen() {
        // Create a temporary all-black image
        let img = image::RgbaImage::from_fn(240, 160, |_, _| image::Rgba([0u8, 0u8, 0u8, 255u8]));
        let tmp_path = std::env::temp_dir().join("test_blank.png");
        img.save(&tmp_path).unwrap();
        
        let analysis = analyze_screenshot(&tmp_path).unwrap();
        assert_eq!(analysis, ScreenAnalysis::BlankOrGreen);
        
        let _ = fs::remove_file(tmp_path);
    }

    #[test]
    fn test_analyze_green_screen() {
        // Create a temporary all-green image
        let img = image::RgbaImage::from_fn(240, 160, |_, _| image::Rgba([30u8, 220u8, 30u8, 255u8]));
        let tmp_path = std::env::temp_dir().join("test_green.png");
        img.save(&tmp_path).unwrap();
        
        let analysis = analyze_screenshot(&tmp_path).unwrap();
        assert_eq!(analysis, ScreenAnalysis::BlankOrGreen);
        
        let _ = fs::remove_file(tmp_path);
    }

    #[test]
    fn test_analyze_content_screen() {
        // Create a temporary image with visible text-like content
        let mut img = image::RgbaImage::from_fn(240, 160, |_, _| image::Rgba([0u8, 0u8, 0u8, 255u8]));
        // Draw some white pixels in the center (5% of screen)
        for x in 100..140 {
            for y in 60..100 {
                img.put_pixel(x, y, image::Rgba([255u8, 255u8, 255u8, 255u8]));
            }
        }
        let tmp_path = std::env::temp_dir().join("test_content.png");
        img.save(&tmp_path).unwrap();
        
        let analysis = analyze_screenshot(&tmp_path).unwrap();
        match analysis {
            ScreenAnalysis::HasContent(ratio) => {
                assert!(ratio > 0.01, "Expected > 1% content, got {}%", ratio * 100.0);
            }
            ScreenAnalysis::BlankOrGreen => panic!("Expected HasContent, got BlankOrGreen"),
        }
        
        let _ = fs::remove_file(tmp_path);
    }
}
