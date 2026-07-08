use image::{GenericImageView, Rgba, ImageBuffer};
use serde::Serialize;
use std::path::Path;
use std::fs;

/// Configuration for image comparison thresholds
#[derive(Debug, Clone)]
pub struct ComparisonConfig {
    pub max_diff_percent: f64,      // Default: 0.5%
    pub min_ssim: f64,              // Default: 0.98
    pub min_content_ratio: f64,     // Default: 0.1 (10%)
    pub pixel_tolerance: u8,        // Default: ±2 per channel
}

impl Default for ComparisonConfig {
    fn default() -> Self {
        Self {
            max_diff_percent: 0.5,
            min_ssim: 0.98,
            min_content_ratio: 0.1,
            pixel_tolerance: 2,
        }
    }
}

/// Diagnostic metrics for image comparison
#[derive(Debug, Clone, Serialize)]
pub struct ComparisonMetrics {
    pub match_percent: f64,
    pub diff_percent: f64,
    pub diff_pixels: u32,
    pub total_pixels: u32,
    pub ssim: f64,
    pub golden_nonblack_pixels: u32,
    pub transpiled_nonblack_pixels: u32,
    pub content_loss_percent: f64,
}

/// Failure classification for diagnostic reports
#[derive(Debug, Clone, Serialize, PartialEq)]
pub enum FailureClassification {
    SizeMismatch,
    EmptyOutput,
    NearBlackOutput,
    Offset,
    ColorShift,
    StructuralMismatch,
}

/// Diagnostic report for failed comparisons
#[derive(Debug, Clone, Serialize)]
pub struct DiagnosticReport {
    pub rom_name: String,
    pub test_type: String,
    pub verdict: String,
    pub metrics: ComparisonMetrics,
    pub thresholds: ComparisonThresholds,
    pub failure_reasons: Vec<String>,
    pub failure_classification: Option<String>,
    pub golden_image: String,
    pub transpiled_image: String,
    pub diff_image: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ComparisonThresholds {
    pub max_diff_percent: f64,
    pub min_ssim: f64,
    pub min_content_ratio: f64,
}

/// Result of image comparison
pub struct ComparisonResult {
    pub passed: bool,
    pub metrics: ComparisonMetrics,
    pub failure_reasons: Vec<String>,
    pub failure_classification: Option<FailureClassification>,
}

/// Compare two images with comprehensive checks
pub fn compare_images_comprehensive(
    transpiled_path: &Path,
    golden_path: &Path,
    config: &ComparisonConfig,
    rom_name: &str,
    test_type: &str,
    artifacts_dir: &Path,
) -> Result<ComparisonResult, Box<dyn std::error::Error>> {
    let img_transpiled = image::open(transpiled_path)?;
    let img_golden = image::open(golden_path)?;

    let (w1, h1) = img_transpiled.dimensions();
    let (w2, h2) = img_golden.dimensions();

    // Check for size mismatch
    if w1 != w2 || h1 != h2 {
        let metrics = ComparisonMetrics {
            match_percent: 0.0,
            diff_percent: 100.0,
            diff_pixels: w1 * h1,
            total_pixels: w1 * h1,
            ssim: 0.0,
            golden_nonblack_pixels: 0,
            transpiled_nonblack_pixels: 0,
            content_loss_percent: 100.0,
        };
        return Ok(ComparisonResult {
            passed: false,
            metrics,
            failure_reasons: vec!["size_mismatch".to_string()],
            failure_classification: Some(FailureClassification::SizeMismatch),
        });
    }

    // Convert to RGBA
    let pixels_transpiled = img_transpiled.to_rgba8();
    let pixels_golden = img_golden.to_rgba8();

    let total_pixels = (pixels_transpiled.width() * pixels_transpiled.height()) as u32;

    // Count non-black pixels
    let golden_nonblack = count_nonblack_pixels(&pixels_golden);
    let transpiled_nonblack = count_nonblack_pixels(&pixels_transpiled);

    // Content-awareness check
    let mut failure_reasons = Vec::new();
    let mut failure_classification = None;

    if golden_nonblack > 0 && transpiled_nonblack == 0 {
        failure_reasons.push("empty_output".to_string());
        failure_classification = Some(FailureClassification::EmptyOutput);
    } else if golden_nonblack > 0 && transpiled_nonblack < (golden_nonblack as f64 * config.min_content_ratio) as u32 {
        failure_reasons.push("near_black_output".to_string());
        failure_classification = Some(FailureClassification::NearBlackOutput);
    }

    // Calculate content loss percent
    let content_loss_percent = if golden_nonblack > 0 {
        ((golden_nonblack - transpiled_nonblack) as f64 / golden_nonblack as f64) * 100.0
    } else {
        0.0
    };

    // Compare pixels with tolerance
    let mut matching_pixels = 0u32;

    for (p1, p2) in pixels_transpiled.pixels().zip(pixels_golden.pixels()) {
        if pixels_match_tolerance(p1, p2, config.pixel_tolerance) {
            matching_pixels += 1;
        }
    }

    let diff_pixels = total_pixels - matching_pixels;
    let match_percent = (matching_pixels as f64 / total_pixels as f64) * 100.0;
    let diff_percent = (diff_pixels as f64 / total_pixels as f64) * 100.0;

    // Calculate SSIM
    let ssim = calculate_ssim(&pixels_transpiled, &pixels_golden);

    // Determine additional failure reasons
    if ssim < config.min_ssim
        && !failure_reasons.contains(&"empty_output".to_string())
        && !failure_reasons.contains(&"near_black_output".to_string())
    {
        failure_reasons.push("ssim_below_threshold".to_string());

        // Classify the type of mismatch
        if failure_classification.is_none() {
            if diff_percent > 40.0 {
                failure_classification = Some(FailureClassification::Offset);
            } else if match_percent > 80.0 {
                failure_classification = Some(FailureClassification::ColorShift);
            } else {
                failure_classification = Some(FailureClassification::StructuralMismatch);
            }
        }
    }

    if diff_percent > config.max_diff_percent
        && !failure_reasons.contains(&"diff_percent_above_threshold".to_string())
    {
        failure_reasons.push("diff_percent_above_threshold".to_string());
    }

    let passed = failure_reasons.is_empty();

    let metrics = ComparisonMetrics {
        match_percent,
        diff_percent,
        diff_pixels,
        total_pixels,
        ssim,
        golden_nonblack_pixels: golden_nonblack,
        transpiled_nonblack_pixels: transpiled_nonblack,
        content_loss_percent,
    };

    // Generate diagnostic artifacts if test failed
    if !passed {
        generate_diff_image(&pixels_transpiled, &pixels_golden, artifacts_dir, rom_name)?;
        generate_diagnostic_report(
            rom_name,
            test_type,
            &metrics,
            config,
            &failure_reasons,
            failure_classification.as_ref(),
            golden_path,
            transpiled_path,
            artifacts_dir,
        )?;
    }

    Ok(ComparisonResult {
        passed,
        metrics,
        failure_reasons,
        failure_classification,
    })
}

/// Count pixels that are not completely black
fn count_nonblack_pixels(pixels: &image::RgbaImage) -> u32 {
    pixels.pixels().filter(|p| {
        p[0] > 0 || p[1] > 0 || p[2] > 0
    }).count() as u32
}

/// Check if two pixels match within tolerance
fn pixels_match_tolerance(p1: &Rgba<u8>, p2: &Rgba<u8>, tolerance: u8) -> bool {
    let dr = p1[0].abs_diff(p2[0]);
    let dg = p1[1].abs_diff(p2[1]);
    let db = p1[2].abs_diff(p2[2]);
    let da = p1[3].abs_diff(p2[3]);

    dr <= tolerance && dg <= tolerance && db <= tolerance && da <= tolerance
}

/// Calculate SSIM (Structural Similarity Index) using 8x8 sliding window
fn calculate_ssim(img1: &image::RgbaImage, img2: &image::RgbaImage) -> f64 {
    // Convert to luminance
    let lum1: Vec<f64> = img1.pixels().map(rgba_to_luminance).collect();
    let lum2: Vec<f64> = img2.pixels().map(rgba_to_luminance).collect();

    let width = img1.width() as usize;
    let height = img1.height() as usize;
    let window_size = 8;
    let window_pixels = window_size * window_size;

    let mut ssim_sum = 0.0;
    let mut window_count = 0;

    // Sliding window
    for y in 0..=height.saturating_sub(window_size) {
        for x in 0..=width.saturating_sub(window_size) {
            let mut win1 = Vec::with_capacity(window_pixels);
            let mut win2 = Vec::with_capacity(window_pixels);

            for wy in 0..window_size {
                for wx in 0..window_size {
                    let idx = (y + wy) * width + (x + wx);
                    win1.push(lum1[idx]);
                    win2.push(lum2[idx]);
                }
            }

            let ssim_window = calculate_ssim_window(&win1, &win2);
            ssim_sum += ssim_window;
            window_count += 1;
        }
    }

    if window_count == 0 {
        return 1.0; // No windows to compare (tiny image)
    }

    ssim_sum / window_count as f64
}

/// Convert RGBA to luminance
fn rgba_to_luminance(p: &Rgba<u8>) -> f64 {
    0.299 * p[0] as f64 + 0.587 * p[1] as f64 + 0.114 * p[2] as f64
}

/// Calculate SSIM for a single window
fn calculate_ssim_window(win1: &[f64], win2: &[f64]) -> f64 {
    let n = win1.len() as f64;
    let c1 = (0.01 * 255.0_f64).powi(2);
    let c2 = (0.03 * 255.0_f64).powi(2);

    // Calculate means
    let mu_x: f64 = win1.iter().sum::<f64>() / n;
    let mu_y: f64 = win2.iter().sum::<f64>() / n;

    // Calculate variances and covariance
    let mut var_x = 0.0;
    let mut var_y = 0.0;
    let mut cov_xy = 0.0;

    for (a, b) in win1.iter().zip(win2.iter()) {
        let diff_x = a - mu_x;
        let diff_y = b - mu_y;
        var_x += diff_x * diff_x;
        var_y += diff_y * diff_y;
        cov_xy += diff_x * diff_y;
    }

    var_x /= n;
    var_y /= n;
    cov_xy /= n;

    let numerator = (2.0 * mu_x * mu_y + c1) * (2.0 * cov_xy + c2);
    let denominator = (mu_x * mu_x + mu_y * mu_y + c1) * (var_x + var_y + c2);

    if denominator == 0.0 {
        return 1.0;
    }

    numerator / denominator
}

/// Generate a visual diff image
fn generate_diff_image(
    img1: &image::RgbaImage,
    img2: &image::RgbaImage,
    artifacts_dir: &Path,
    rom_name: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let width = img1.width();
    let height = img1.height();
    let mut diff_img = ImageBuffer::new(width, height);

    for (idx, (p1, p2)) in img1.pixels().zip(img2.pixels()).enumerate() {
        let px = (idx as u32) % width;
        let py = (idx as u32) / width;

        if !pixels_match_tolerance(p1, p2, 2) {
            // Red for differences
            diff_img.put_pixel(px, py, Rgba([255u8, 0, 0, 255]));
        } else {
            // Black for matches
            diff_img.put_pixel(px, py, Rgba([0u8, 0, 0, 255]));
        }
    }

    let diff_path = artifacts_dir.join(format!("{}_diff.png", rom_name));
    diff_img.save(&diff_path)?;

    Ok(())
}

/// Generate diagnostic JSON report
#[allow(clippy::too_many_arguments)]
fn generate_diagnostic_report(
    rom_name: &str,
    test_type: &str,
    metrics: &ComparisonMetrics,
    config: &ComparisonConfig,
    failure_reasons: &[String],
    classification: Option<&FailureClassification>,
    golden_path: &Path,
    transpiled_path: &Path,
    artifacts_dir: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let classification_str = classification.map(|c| {
        match c {
            FailureClassification::SizeMismatch => "size_mismatch",
            FailureClassification::EmptyOutput => "empty_output",
            FailureClassification::NearBlackOutput => "near_black_output",
            FailureClassification::Offset => "offset",
            FailureClassification::ColorShift => "color_shift",
            FailureClassification::StructuralMismatch => "structural_mismatch",
        }.to_string()
    });

    let report = DiagnosticReport {
        rom_name: rom_name.to_string(),
        test_type: test_type.to_string(),
        verdict: "FAIL".to_string(),
        metrics: metrics.clone(),
        thresholds: ComparisonThresholds {
            max_diff_percent: config.max_diff_percent,
            min_ssim: config.min_ssim,
            min_content_ratio: config.min_content_ratio,
        },
        failure_reasons: failure_reasons.to_vec(),
        failure_classification: classification_str,
        golden_image: golden_path.file_name().unwrap_or_default().to_string_lossy().to_string(),
        transpiled_image: transpiled_path.file_name().unwrap_or_default().to_string_lossy().to_string(),
        diff_image: Some(format!("{}_diff.png", rom_name)),
    };

    let report_path = artifacts_dir.join(format!("{}_diagnostic.json", rom_name));
    let json = serde_json::to_string_pretty(&report)?;
    fs::write(report_path, json)?;

    Ok(())
}

/// Format a success message
pub fn format_success_message(metrics: &ComparisonMetrics, tolerance: u8) -> String {
    format!(
        "PASS: {:.1}% match, SSIM={:.2}, {} pixels differ (±{} tolerance)",
        metrics.match_percent,
        metrics.ssim,
        metrics.diff_pixels,
        tolerance
    )
}

/// Format a failure message
pub fn format_failure_message(
    metrics: &ComparisonMetrics,
    classification: Option<&FailureClassification>,
) -> String {
    let classification_str = classification.map(|c| {
        match c {
            FailureClassification::SizeMismatch => "size_mismatch",
            FailureClassification::EmptyOutput => "empty_output",
            FailureClassification::NearBlackOutput => "near_black_output",
            FailureClassification::Offset => "offset",
            FailureClassification::ColorShift => "color_shift",
            FailureClassification::StructuralMismatch => "structural_mismatch",
        }
    }).unwrap_or("unknown");

    format!(
        "FAIL [{}]: {:.1}% match, SSIM={:.2}, {}/{} non-black pixels — see diff_image.png and diagnostic_report.json",
        classification_str,
        metrics.match_percent,
        metrics.ssim,
        metrics.transpiled_nonblack_pixels,
        metrics.golden_nonblack_pixels
    )
}
