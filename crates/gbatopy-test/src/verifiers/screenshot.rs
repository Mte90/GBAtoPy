use crate::config::TestEntry;
use crate::types::{TestResult, TestStatus};
use super::Verifier;
use std::path::{Path, PathBuf};
use std::time::Instant;
use duct::cmd;

pub struct ScreenshotGoldenVerifier;

impl Verifier for ScreenshotGoldenVerifier {
    fn verify(&self, entry: &TestEntry, artifacts_dir: &Path) -> TestResult {
        let start = Instant::now();
        let test_name = entry.name.clone();
        let test_type_str = format!("{:?}", entry.test_type);

        log::info!("[ScreenshotGolden] Testing {}...", test_name);

        let rom_path = entry.rom_path.to_string_lossy().to_string();
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

        if let Err(e) = self.transpile(&rom_path, &transpiled_py) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Transpilation failed: {}", e),
                duration: start.elapsed(),
            };
        }

        log::info!("[ScreenshotGolden] Transpilation succeeded for {}", test_name);

        let frames = 60;
        if let Err(e) = self.capture_screenshot(&transpiled_py, &screenshot_path, frames) {
            return TestResult {
                name: test_name.clone(),
                test_type: test_type_str.clone(),
                status: TestStatus::Fail,
                message: format!("Screenshot capture failed: {}", e),
                duration: start.elapsed(),
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
            };
        }

        let threshold = 0.95;
        match self.compare_images(&screenshot_path, &golden_path, threshold) {
            Ok((match_percent, diff_pixels)) => {
                if match_percent >= threshold {
                    log::info!(
                        "[ScreenshotGolden] PASS: {} ({}% match, {} pixels differ)",
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
                        "[ScreenshotGolden] FAIL: {} ({}% match, {} pixels differ)",
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
        "screenshot_golden"
    }
}

impl ScreenshotGoldenVerifier {
    fn transpile(&self, rom_path: &str, output: &Path) -> Result<(), Box<dyn std::error::Error>> {
        let bin = "target/debug/gbatopy-cli";
        
        cmd!(bin, "pipeline", "--rom", rom_path, "--output", output.to_string_lossy().as_ref())
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

    fn compare_images(
        &self,
        screenshot: &Path,
        golden: &Path,
        threshold: f64,
    ) -> Result<(f64, u32), Box<dyn std::error::Error>> {
        use image::GenericImageView;
        
        let img1 = image::open(screenshot)?;
        let img2 = image::open(golden)?;
        
        let (w1, h1) = img1.dimensions();
        let (w2, h2) = img2.dimensions();
        
        if w1 != w2 || h1 != h2 {
            let img2_resized = img2.resize_exact(w1, h1, image::imageops::FilterType::Nearest);
            return self.compare_pixel_by_pixel(&img1, &img2_resized, threshold);
        }
        
        self.compare_pixel_by_pixel(&img1, &img2, threshold)
    }

    fn compare_pixel_by_pixel(
        &self,
        img1: &image::DynamicImage,
        img2: &image::DynamicImage,
        _threshold: f64,
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
