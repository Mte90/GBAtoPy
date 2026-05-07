use std::fs;
use std::path::Path;
use std::process::{Command, Stdio};

pub fn verify_all(
    rom_dir: &str,
    output_dir: &str,
    frames: u32,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Verifying all ROMs in {} ===", rom_dir);

    let mut passed = 0;
    let mut failed = 0;

    for entry in fs::read_dir(rom_dir)? {
        let entry = entry?;
        let path = entry.path();

        if path.extension().map_or(false, |ext| ext == "gba") {
            let rom_path = path.to_str().unwrap_or("");
            println!(
                "\n--- Testing: {} ---",
                path.file_name().unwrap().to_str().unwrap()
            );

            match verify_single_rom(rom_path, output_dir, frames) {
                Ok(_) => {
                    passed += 1;
                    println!("RESULT: PASS");
                }
                Err(e) => {
                    failed += 1;
                    println!("RESULT: FAIL - {}", e);
                }
            }
        }
    }

    println!("\n=== Verification Summary ===");
    println!("Passed: {}", passed);
    println!("Failed: {}", failed);
    println!("Total: {}", passed + failed);

    if failed > 0 {
        return Err(format!("{} ROMs failed verification", failed).into());
    }

    Ok(())
}

fn verify_single_rom(
    rom_path: &str,
    output_dir: &str,
    frames: u32,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("  Generating Python from ROM...");

    let rom_name = Path::new(rom_path).file_stem().unwrap().to_str().unwrap();
    let py_path = format!("{}/{}_test.py", output_dir, rom_name);

    let status = Command::new("cargo")
        .args([
            "run",
            "--bin",
            "gbatopy-cli",
            "--",
            "pipeline",
            "--rom",
            rom_path,
            "--output",
            &py_path,
            "--assets-dir",
            "crates/gbatopy-cli/assets",
        ])
        .status()?;

    if !status.success() {
        return Err("Transpilation failed".into());
    }

    println!("  Running {} frames...", frames);

    let output = Command::new("python3")
        .arg(&py_path)
        .arg("--headless")
        .arg(format!("--frame={}", frames))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        eprintln!("  ERROR: {}", stderr);
        return Err("Execution failed".into());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);

    if stdout.contains("Game finished") || stdout.contains("PASS") || stdout.contains("completed") {
        println!("  Execution successful");
        Ok(())
    } else {
        Err("No success indicator found in output".into())
    }
}
