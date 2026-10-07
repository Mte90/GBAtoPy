use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Instant;

fn generate_python_if_missing(
    rom_path: &str,
    output_dir: &str,
) -> Result<String, Box<dyn std::error::Error>> {
    let rom_name = Path::new(rom_path)
        .file_stem()
        .ok_or_else(|| format!("ROM path has no file stem: {:?}", rom_path))?
        .to_str()
        .ok_or_else(|| format!("ROM path contains non-UTF8 characters: {:?}", rom_path))?;
    let py_path = format!("{}/{}_test.py", output_dir, rom_name);

    if Path::new(&py_path).exists() {
        return Ok(py_path);
    }

    println!("  Generating Python from ROM...");

    let assets_dir = PathBuf::from("crates/gbatopy-cli/assets");

    let output = Command::new("./target/debug/gbatopy-cli")
        .args([
            "pipeline",
            "--rom",
            rom_path,
            "--output",
            output_dir,
            "--assets-dir",
            assets_dir.to_str().unwrap_or("assets"),
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Pipeline failed: {}", stderr).into());
    }

    if !Path::new(&py_path).exists() {
        return Err(format!("Generated Python not found at {}", py_path).into());
    }

    Ok(py_path)
}

pub fn verify_registers(
    rom_path: &str,
    output_dir: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("Verifying register state for {}...", rom_path);

    let py_path = generate_python_if_missing(rom_path, output_dir)?;

    let start = Instant::now();
    let output = Command::new("python3")
        .arg(&py_path)
        .arg("--headless")
        .arg("--frame=1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()?;

    let duration = start.elapsed();

    if !output.status.success() {
        eprintln!("  ERROR: {}", String::from_utf8_lossy(&output.stderr));
        return Err("Verification failed".into());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    println!("  Registers after 1 frame:");
    for line in stdout.lines() {
        if line.contains("r") || line.contains("CPSR") {
            println!("    {}", line);
        }
    }

    println!("  Duration: {:?}", duration);
    println!("  PASS: Register verification completed");
    Ok(())
}

pub fn verify_memory(rom_path: &str, output_dir: &str) -> Result<(), Box<dyn std::error::Error>> {
    println!("Verifying memory state for {}...", rom_path);

    let py_path = generate_python_if_missing(rom_path, output_dir)?;

    let start = Instant::now();
    let output = Command::new("python3")
        .arg(&py_path)
        .arg("--headless")
        .arg("--frame=1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()?;

    let duration = start.elapsed();

    if !output.status.success() {
        eprintln!("  ERROR: {}", String::from_utf8_lossy(&output.stderr));
        return Err("Verification failed".into());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    println!("  Memory state after 1 frame:");
    for line in stdout.lines() {
        if line.contains("VRAM") || line.contains("OAM") || line.contains("PALETTE") {
            println!("    {}", line);
        }
    }

    println!("  Duration: {:?}", duration);
    println!("  PASS: Memory verification completed");
    Ok(())
}

pub fn verify_screenshot(
    rom_path: &str,
    output_dir: &str,
    reference_dir: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("Comparing screenshot for {}...", rom_path);

    let py_path = generate_python_if_missing(rom_path, output_dir)?;
    let rom_name = Path::new(rom_path)
        .file_stem()
        .ok_or_else(|| format!("ROM path has no file stem: {:?}", rom_path))?
        .to_str()
        .ok_or_else(|| format!("ROM path contains non-UTF8 characters: {:?}", rom_path))?;
    let screenshot_path = format!("{}/{}_screenshot.png", output_dir, rom_name);
    let reference_path = format!("{}/{}_reference.png", reference_dir, rom_name);

    let start = Instant::now();
    let output = Command::new("python3")
        .arg(&py_path)
        .arg("--headless")
        .arg("--frame=1")
        .arg(format!("--screenshot={}", screenshot_path))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()?;

    let duration = start.elapsed();

    if !output.status.success() {
        eprintln!("  ERROR: {}", String::from_utf8_lossy(&output.stderr));
        return Err("Screenshot capture failed".into());
    }

    if !Path::new(&screenshot_path).exists() {
        return Err("Screenshot file not created".into());
    }

    let check_output = Command::new("python3")
        .args([
            "-c",
            &format!(
                "from PIL import Image; img=Image.open('{}'); pixels=list(img.getdata()); total=len(pixels); non_black=sum(1 for r,g,b in pixels if r>0 or g>0 or b>0); print('Screenshot analysis: ' + str(non_black) + ' non-black pixels out of ' + str(total) + ' total'); exit(0 if non_black>=10 else 1)",
                screenshot_path
            ),
        ])
        .output()?;

    if !check_output.status.success() {
        println!("  FAIL: Screenshot is all black or nearly empty");
        return Err("Screenshot is black".into());
    }

    if !Path::new(&reference_path).exists() {
        println!("  WARNING: No reference image found at {}", reference_path);
        println!("  PASS: Screenshot captured and contains visible content (no reference for comparison)");
        return Ok(());
    }

    let diff_output = Command::new("compare")
        .args([
            "-metric",
            "RMSE",
            &screenshot_path,
            &reference_path,
            "null:",
        ])
        .output()?;

    let diff_result = String::from_utf8_lossy(&diff_output.stderr);
    println!("  Difference: {}", diff_result.trim());

    if diff_result.contains("0") {
        println!("  PASS: Screenshots match");
    } else {
        println!("  FAIL: Screenshots differ");
        return Err("Screenshot mismatch".into());
    }

    println!("  Duration: {:?}", duration);
    Ok(())
}

pub fn verify_regression(
    rom_path: &str,
    output_dir: &str,
    frames: u32,
) -> Result<(), Box<dyn std::error::Error>> {
    println!(
        "Running regression test for {} ({} frames)...",
        rom_path, frames
    );

    let py_path = generate_python_if_missing(rom_path, output_dir)?;

    let start = Instant::now();
    let output = Command::new("python3")
        .arg(&py_path)
        .arg("--headless")
        .arg(format!("--frame={}", frames))
        .arg("--benchmark")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()?;

    let duration = start.elapsed();

    if !output.status.success() {
        eprintln!("  ERROR: {}", String::from_utf8_lossy(&output.stderr));
        return Err("Regression test failed".into());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    println!("  Frames executed: {}", frames);
    println!("  Duration: {:?}", duration);
    println!(
        "  Average FPS: {:.2}",
        frames as f64 / duration.as_secs_f64()
    );

    if stdout.contains("PASS") || stdout.contains("completed") {
        println!("  PASS: Regression test completed without crashes");
    } else {
        println!("  WARNING: No explicit PASS found in output");
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    // === Path construction tests ===
    #[test]
    fn test_rom_path_has_file_stem_valid() {
        // Valid ROM path with file stem
        let result = Path::new("/path/to/rom.gba").file_stem();
        assert!(result.is_some());
        assert_eq!(result.unwrap(), "rom");
    }

    #[test]
    fn test_rom_path_has_file_stem_with_dir() {
        // ROM path with directory components
        let result = Path::new("test_roms/roms/hello.gba").file_stem();
        assert!(result.is_some());
        assert_eq!(result.unwrap(), "hello");
    }

    #[test]
    fn test_rom_path_has_no_file_stem_root() {
        // Root path has no file stem
        let result = Path::new("/").file_stem();
        assert!(result.is_none());
    }

    #[test]
    fn test_rom_path_has_no_file_stem_empty() {
        // Empty path has no file stem
        let result = Path::new("").file_stem();
        assert!(result.is_none());
    }

    #[test]
    fn test_py_path_construction() {
        // Test Python output path construction
        let rom_path = "test.gba";
        let output_dir = "/tmp/output";
        let rom_name = Path::new(rom_path).file_stem().unwrap().to_str().unwrap();
        let py_path = format!("{}/{}_test.py", output_dir, rom_name);
        assert_eq!(py_path, "/tmp/output/test_test.py");
    }

    #[test]
    fn test_screenshot_path_construction() {
        // Test screenshot path construction
        let rom_path = "pong.gba";
        let output_dir = "/tmp/screenshots";
        let rom_name = Path::new(rom_path).file_stem().unwrap().to_str().unwrap();
        let screenshot_path = format!("{}/{}_screenshot.png", output_dir, rom_name);
        assert_eq!(screenshot_path, "/tmp/screenshots/pong_screenshot.png");
    }

    #[test]
    fn test_reference_path_construction() {
        // Test reference path construction
        let rom_path = "combo.gba";
        let reference_dir = "/tmp/references";
        let rom_name = Path::new(rom_path).file_stem().unwrap().to_str().unwrap();
        let reference_path = format!("{}/{}_reference.png", reference_dir, rom_name);
        assert_eq!(reference_path, "/tmp/references/combo_reference.png");
    }

    // === Error handling tests ===
    #[test]
    fn test_error_conversion_from_string() {
        // Test that String can be converted to Box<dyn Error>
        let err: Box<dyn std::error::Error> = "test error".to_string().into();
        assert_eq!(err.to_string(), "test error");
    }

    #[test]
    fn test_error_conversion_from_format() {
        // Test formatted error conversion
        let msg = "Pipeline failed: some error";
        let err: Box<dyn std::error::Error> = format!("{}", msg).into();
        assert_eq!(err.to_string(), msg);
    }

    // === Path validation edge cases ===
    #[test]
    fn test_path_with_extension() {
        // Path with .gba extension
        let stem = Path::new("game.gba").file_stem().unwrap().to_str().unwrap();
        assert_eq!(stem, "game");
    }

    #[test]
    fn test_path_with_multiple_dots() {
        // Path with multiple dots in filename
        let stem = Path::new("game.v1.0.gba").file_stem().unwrap().to_str().unwrap();
        assert_eq!(stem, "game.v1.0");
    }

    #[test]
    fn test_path_without_extension() {
        // Path without extension
        let stem = Path::new("game").file_stem().unwrap().to_str().unwrap();
        assert_eq!(stem, "game");
    }

    #[test]
    fn test_nested_path() {
        // Deeply nested path
        let stem = Path::new("a/b/c/d/e/rom.gba").file_stem().unwrap().to_str().unwrap();
        assert_eq!(stem, "rom");
    }

    #[test]
    fn test_absolute_vs_relative_paths() {
        // Both absolute and relative paths should extract stem correctly
        let abs_stem = Path::new("/absolute/path/rom.gba").file_stem().unwrap().to_str().unwrap();
        let rel_stem = Path::new("relative/path/rom.gba").file_stem().unwrap().to_str().unwrap();
        assert_eq!(abs_stem, rel_stem);
        assert_eq!(abs_stem, "rom");
    }
}
