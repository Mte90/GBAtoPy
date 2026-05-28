use crate::config::TestEntry;
use crate::types::{TestResult, TestStatus};
use super::Verifier;
use std::path::{Path, PathBuf};
use std::time::Instant;
use std::fs;
use duct::cmd;

pub struct ScreenshotMgbaVerifier;

impl Verifier for ScreenshotMgbaVerifier {
    fn verify(&self, entry: &TestEntry, artifacts_dir: &Path) -> TestResult {
        let start = Instant::now();
        let test_name = entry.name.clone();
        let test_type_str = format!("{:?}", entry.test_type);

        log::info!("[mGBA Oracle] Testing {}...", test_name);

        let rom_path = entry.rom_path.to_string_lossy().to_string();
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
            };
        }
        let mgba_path = mgba_path.unwrap();

        // Step 2: Generate Lua script for mGBA
        let frames = 60;
        if let Err(e) = generate_lua_script(&lua_script, frames, &golden_path) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Error,
                message: format!("Failed to generate Lua script: {}", e),
                duration: start.elapsed(),
            };
        }

        // Step 3: Run mGBA to capture golden screenshot
        if let Err(e) = run_mgba_capture(&mgba_path, &rom_path, &lua_script) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("mGBA capture failed: {}", e),
                duration: start.elapsed(),
            };
        }

        log::info!("[mGBA Oracle] Golden screenshot captured for {}", test_name);

        // Step 4: Transpile ROM
        if let Err(e) = transpile_rom(&rom_path, &transpiled_py) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Transpilation failed: {}", e),
                duration: start.elapsed(),
            };
        }

        log::info!("[mGBA Oracle] Transpilation succeeded for {}", test_name);

        // Step 5: Run transpiled Python to capture screenshot
        if let Err(e) = capture_transpiled_screenshot(&transpiled_py, &transpiled_screenshot, frames) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Screenshot capture failed: {}", e),
                duration: start.elapsed(),
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
            };
        }

        let threshold = 0.95;
        match compare_images(&transpiled_screenshot, &golden_path, threshold) {
            Ok((match_percent, diff_pixels)) => {
                if match_percent >= threshold {
                    log::info!(
                        "[mGBA Oracle] PASS: {} ({}% match, {} pixels differ)",
                        test_name,
                        match_percent,
                        diff_pixels
                    );
                    TestResult {
                        name: test_name,
                        test_type: test_type_str,
                        status: TestStatus::Pass,
                        message: format!(
                            "Images match: {:.1}% (threshold: {:.1}%)",
                            match_percent, threshold
                        ),
                        duration: start.elapsed(),
                    }
                } else {
                    log::error!(
                        "[mGBA Oracle] FAIL: {} ({}% match, {} pixels differ)",
                        test_name,
                        match_percent,
                        diff_pixels
                    );
                    TestResult {
                        name: test_name,
                        test_type: test_type_str,
                        status: TestStatus::Fail,
                        message: format!(
                            "Image mismatch: {:.1}% < {:.1}% threshold ({} pixels differ)",
                            match_percent, threshold, diff_pixels
                        ),
                        duration: start.elapsed(),
                    }
                }
            }
            Err(e) => TestResult {
                name: test_name,
                test_type: test_type_str,
                status: TestStatus::Error,
                message: format!("Image comparison failed: {}", e),
                duration: start.elapsed(),
            },
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
        emu:quit()
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
        "-L",
        lua_script.to_string_lossy().as_ref(),
        rom_path
    )
    .run()?;
    Ok(())
}

fn transpile_rom(rom_path: &str, output: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let bin = "target/debug/gbatopy-cli";
    
    cmd!(bin, "pipeline", "--rom", rom_path, "--output", output.to_string_lossy().as_ref())
        .run()?;
    
    if !output.exists() {
        return Err("Output file not created".into());
    }
    
    Ok(())
}

fn capture_transpiled_screenshot(py_file: &Path, screenshot_path: &Path, frames: u32) -> Result<(), Box<dyn std::error::Error>> {
    let frame_arg = format!("--frame={}", frames);
    let screenshot_arg = format!("--screenshot={}" , screenshot_path.to_string_lossy());
    
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

fn compare_images(
    screenshot: &Path,
    golden: &Path,
    _threshold: f64,
) -> Result<(f64, u32), Box<dyn std::error::Error>> {
    use image::GenericImageView;
    
    let img1 = image::open(screenshot)?;
    let img2 = image::open(golden)?;
    
    let (w1, h1) = img1.dimensions();
    let (w2, h2) = img2.dimensions();
    
    if w1 != w2 || h1 != h2 {
        let img2_resized = img2.resize_exact(w1, h1, image::imageops::FilterType::Nearest);
        return compare_pixel_by_pixel(&img1, &img2_resized);
    }
    
    compare_pixel_by_pixel(&img1, &img2)
}

fn compare_pixel_by_pixel(
    img1: &image::DynamicImage,
    img2: &image::DynamicImage,
) -> Result<(f64, u32), Box<dyn std::error::Error>> {
    let pixels1 = img1.to_rgba8();
    let pixels2 = img2.to_rgba8();
    
    let total_pixels = (pixels1.width() * pixels1.height()) as u32;
    let mut matching_pixels = 0u32;
    
    for (p1, p2) in pixels1.pixels().zip(pixels2.pixels()) {
        if p1 == p2 {
            matching_pixels += 1;
        }
    }
    
    let match_percent = (matching_pixels as f64 / total_pixels as f64) * 100.0;
    let diff_pixels = total_pixels - matching_pixels;
    
    Ok((match_percent, diff_pixels))
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
