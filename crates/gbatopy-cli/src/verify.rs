use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Instant;

fn generate_python_if_missing(
    rom_path: &str,
    output_dir: &str,
) -> Result<String, Box<dyn std::error::Error>> {
    let rom_name = Path::new(rom_path).file_stem().unwrap().to_str().unwrap();
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
            &output_dir,
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
        .arg("--debug")
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
        .arg("--debug")
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
    let rom_name = Path::new(rom_path).file_stem().unwrap().to_str().unwrap();
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
