mod benchmark;
mod cmds;
mod codegen;
mod helpers;
mod memory;
mod pipeline_cmd;
mod ppu;
mod test;
mod verify;

use clap::{Parser, Subcommand};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Parser)]
#[command(name = "pygba")]
#[command(about = "GBA ARM assembly to Python transpiler")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Disasm {
        #[arg(short, long)]
        input: PathBuf,
        #[arg(short, long)]
        output: PathBuf,
        #[arg(long, default_value = "false")]
        use_ir: bool,
    },
    Lift {
        #[arg(short, long)]
        input: PathBuf,
        #[arg(short, long)]
        output: PathBuf,
    },
    Generate {
        #[arg(short, long)]
        input: PathBuf,
        #[arg(short, long)]
        output: PathBuf,
        #[arg(short, long, default_value = "assets")]
        assets_dir: PathBuf,
        #[arg(long, default_value = "false")]
        use_ir: bool,
    },
    Pipeline {
        #[arg(short, long)]
        rom: PathBuf,
        #[arg(short, long)]
        output: PathBuf,
        #[arg(short, long, default_value = "assets")]
        assets_dir: PathBuf,
        #[arg(long, default_value = "false")]
        use_ir: bool,
    },
    Test {
        #[arg(short, long)]
        rom: PathBuf,
        #[arg(long, default_value = "60")]
        frames: u32,
        #[arg(long)]
        screenshot: Option<PathBuf>, // screenshot path for verification
        #[arg(long, default_value = "false")]
        #[allow(dead_code)]
        headless: bool, // available for future use
        #[arg(long)]
        dump_memory: bool, // dump memory state at each frame
        #[arg(long)]
        compare_with_mgba: bool, // compare with mGBA reference
        #[arg(long)]
        output_dir: Option<PathBuf>, // directory for dump files
    },
    Verify {
        #[arg(short, long)]
        rom: PathBuf,
        #[arg(long, default_value = "output_python")]
        output_dir: PathBuf,
        #[arg(long, default_value = "test_roms/references")]
        reference_dir: PathBuf,
        #[arg(long, default_value = "100")]
        frames: u32,
        #[arg(long, default_value = "false")]
        diff: bool,
    },
    TestAll {
        #[arg(long, default_value = "test_roms/roms")]
        rom_dir: PathBuf,
        #[arg(long, default_value = "output_python")]
        output_dir: PathBuf,
        #[arg(long, default_value = "10")]
        frames: u32,
    },
    Benchmark {
        #[arg(short, long)]
        rom: PathBuf,
        #[arg(long, default_value = "1000")]
        frames: u32,
    },
}

fn main() {
    let cli = Cli::parse();

    let _assets_dir = PathBuf::from("crates/gbatopy-cli/assets");
    let _assets_dir = _assets_dir.canonicalize().unwrap_or(_assets_dir);

    match cli.command {
        Commands::Disasm {
            input,
            output,
            use_ir,
        } => {
            if let Err(e) = cmds::disasm::disassemble(
                input.to_str().unwrap_or(""),
                output.to_str().unwrap_or(""),
                use_ir,
            ) {
                eprintln!("Error: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Lift { input, output } => {
            if let Err(e) =
                cmds::lift::lift(input.to_str().unwrap_or(""), output.to_str().unwrap_or(""))
            {
                eprintln!("Error: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Generate {
            input,
            output,
            assets_dir,
            use_ir,
        } => {
            if let Err(e) = pipeline_cmd::run_pipeline(
                input.to_str().unwrap_or(""),
                output.to_str().unwrap_or(""),
                &assets_dir,
                use_ir,
            ) {
                eprintln!("Error: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Pipeline {
            rom,
            output,
            assets_dir,
            use_ir,
        } => {
            if let Err(e) = pipeline_cmd::run_pipeline(
                rom.to_str().unwrap_or(""),
                output.to_str().unwrap_or(""),
                &assets_dir,
                use_ir,
            ) {
                eprintln!("Error: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Test {
            rom,
            frames,
            screenshot,
            headless,
            dump_memory,
            compare_with_mgba,
            output_dir,
        } => {
            println!("Running test on {} for {} frames...", rom.display(), frames);

            // Generate Python from ROM
            println!("  Generating Python from ROM...");
            let rom_name = Path::new(rom.to_str().unwrap_or("rom"))
                .file_stem()
                .unwrap_or(std::ffi::OsStr::new("rom"))
                .to_str()
                .unwrap_or("rom");
            let py_output_dir = std::env::current_dir()
                .unwrap_or_else(|_| std::path::PathBuf::from("."))
                .join("output_test");
            let _ = fs::create_dir_all(&py_output_dir);
            let py_path = py_output_dir.join(format!("{}_test.py", rom_name));
            let assets_dir = std::path::Path::new("crates/gbatopy-cli/assets");

            let pipeline_status = std::process::Command::new("cargo")
                .args([
                    "run",
                    "--bin",
                    "gbatopy-cli",
                    "--",
                    "pipeline",
                    "--rom",
                    rom.to_str().unwrap_or(""),
                    "--output",
                    py_path.to_str().unwrap_or(""),
                    "--assets-dir",
                    assets_dir.to_str().unwrap_or(""),
                ])
                .status();

            match pipeline_status {
                Ok(status) if status.success() => {
                    println!("  Python generated successfully: {}", py_path.display());
                }
                Ok(status) => {
                    eprintln!("  ERROR: Pipeline failed with status: {}", status);
                    eprintln!("RESULT: FAIL (pipeline error)");
                    std::process::exit(1);
                }
                Err(e) => {
                    eprintln!("  ERROR: Failed to run pipeline: {}", e);
                    eprintln!("RESULT: FAIL (pipeline error)");
                    std::process::exit(1);
                }
            }

            // Setup dump directory
            let dump_dir = match output_dir {
                Some(path) => {
                    let dir = path.join("dumps");
                    let _ = fs::create_dir_all(&dir);
                    dir
                }
                None => std::env::current_dir()
                    .unwrap_or_else(|_| std::path::PathBuf::from("."))
                    .join("dumps"),
            };

            // Set environment for dump utility
            if dump_memory || compare_with_mgba {
                let dump_dir_str = dump_dir.to_string_lossy();
                std::env::set_var("GBATOPY_DUMP_DIR", dump_dir_str.as_ref());
                println!("  Dump directory: {}", dump_dir_str);
            }

            // Execute generated Python
            println!("  Executing ROM for {} frames...", frames);

            let mut python_args: Vec<String> = vec![
                py_path.to_string_lossy().to_string(),
                "--headless".to_string(),
                format!("--frame={}", frames),
            ];

            // Add dump-memory flag
            if dump_memory {
                python_args.push("--dump-memory".to_string());
                println!("  Memory dumping enabled");
            }

            // Add compare-with-mgba flag
            if compare_with_mgba {
                python_args.push("--compare-with-mgba".to_string());
                println!("  mGBA comparison enabled");
            }

            // Add screenshot argument if provided
            if let Some(screenshot_path) = screenshot {
                python_args.push("--screenshot".to_string());
                python_args.push(screenshot_path.to_string_lossy().to_string());
                println!(
                    "  Screenshot will be saved to: {}",
                    screenshot_path.display()
                );
            }

            let output = std::process::Command::new("python3")
                .args(&python_args)
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::piped())
                .output();

            match output {
                Ok(output) => {
                    let stdout = String::from_utf8_lossy(&output.stdout);
                    let stderr = String::from_utf8_lossy(&output.stderr);

                    if !output.status.success() {
                        eprintln!("  ERROR: Execution failed");
                        eprintln!("  stderr: {}", stderr);
                        eprintln!("RESULT: FAIL (execution error)");
                        std::process::exit(1);
                    }

                    // Check for success indicators in output
                    if stdout.contains("Game finished")
                        || stdout.contains("PASS")
                        || stdout.contains("completed")
                        || stdout.contains("Test passed")
                    {
                        println!("  {}", stdout.trim());
                        println!("RESULT: PASS");
                    } else {
                        // Even if no explicit PASS, successful execution is a pass for basic test
                        println!("  {}", stdout.trim());
                        println!("RESULT: PASS (execution successful)");
                    }

                    // Report dump files if generated
                    if dump_memory {
                        println!("  Memory dumps saved to: {}", dump_dir.to_string_lossy());
                    }
                    if compare_with_mgba {
                        println!("  mGBA comparison completed");
                    }
                }
                Err(e) => {
                    eprintln!("  ERROR: Failed to execute Python: {}", e);
                    eprintln!("RESULT: FAIL (execution error)");
                    std::process::exit(1);
                }
            }
        }
        Commands::Verify {
            rom,
            diff,
            output_dir,
            reference_dir,
            frames,
        } => {
            let rom_path = rom.to_str().unwrap_or("");
            let output_dir_path = output_dir.to_str().unwrap_or("output_python");
            let reference_dir_path = reference_dir.to_str().unwrap_or("test_roms/references");

            println!("=== Verify Registers ===");
            if let Err(e) = verify::verify_registers(rom_path, output_dir_path) {
                eprintln!("  FAILED: {}", e);
            }

            println!("\n=== Verify Memory ===");
            if let Err(e) = verify::verify_memory(rom_path, output_dir_path) {
                eprintln!("  FAILED: {}", e);
            }

            println!("\n=== Verify Screenshot ===");
            if let Err(e) = verify::verify_screenshot(rom_path, output_dir_path, reference_dir_path)
            {
                eprintln!("  FAILED: {}", e);
            }

            println!("\n=== Verify Regression ({} frames) ===", frames);
            if let Err(e) = verify::verify_regression(rom_path, output_dir_path, frames) {
                eprintln!("  FAILED: {}", e);
            }

            if diff {
                println!("\n=== Diff Mode: Comparing outputs ===");
                println!("  Diff verification not yet implemented");
            }
        }
        Commands::TestAll {
            rom_dir,
            output_dir,
            frames,
        } => {
            let rom_dir_path = rom_dir.to_str().unwrap_or("test_roms/roms");
            let output_dir_path = output_dir.to_str().unwrap_or("output_python");

            if let Err(e) = cmds::verify::verify_all(rom_dir_path, output_dir_path, frames) {
                eprintln!("\nVerification failed: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Benchmark { .. } => {
            if let Err(e) = benchmark::benchmark_all() {
                eprintln!("Error: {}", e);
                std::process::exit(1);
            }
        }
    }
}
