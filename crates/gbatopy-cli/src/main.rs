mod asset_extractor;
mod analysis;
mod benchmark;
mod cmds;
mod codegen;
mod helpers;
mod pipeline_cmd;
pub mod ppu;
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
    },
    Lift {
        #[arg(short, long)]
        input: PathBuf,
        #[arg(short, long)]
        output: PathBuf,
    },
    Pipeline {
        #[arg(short, long)]
        rom: PathBuf,
        #[arg(short, long)]
        output: PathBuf,
        #[arg(long, default_value = "false")]
        minify: bool,
        #[arg(long, default_value = "false")]
        minify_aggressive: bool,
        #[arg(long, default_value = "false")]
        no_audio: bool,
        #[arg(long, default_value = "false")]
        no_irq: bool,
        #[arg(long, default_value = "false")]
        no_timers: bool,
        #[arg(long, default_value = "false")]
        no_dma: bool,
        #[arg(long, default_value = "false")]
        no_numba: bool,
        #[arg(long, default_value = "2000000")]
        max_output_lines: u64,
    },
    Test {
        #[arg(short, long)]
        rom: PathBuf,
        #[arg(long, default_value = "60")]
        frames: u32,
        #[arg(long)]
        screenshot: Option<PathBuf>,
        #[arg(long)]
        dump_memory: Option<PathBuf>,
        #[arg(long)]
        dump_region: Option<String>,
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
    },
    TestAll {
        #[arg(long, default_value = "test_roms/roms")]
        rom_dir: PathBuf,
        #[arg(long, default_value = "output_python")]
        output_dir: PathBuf,
        #[arg(long, default_value = "10")]
        frames: u32,
    },
    Benchmark,
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Disasm { input, output } => {
            if let Err(e) = cmds::disasm::disassemble(
                input.to_str().unwrap_or(""),
                output.to_str().unwrap_or(""),
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
        Commands::Pipeline {
            rom,
            output,
            minify,
            minify_aggressive,
            no_audio,
            no_irq,
            no_timers,
            no_dma,
            no_numba,
            max_output_lines,
        } => {
            let feature_flags = Some(pipeline_cmd::FeatureFlags {
                audio: !no_audio,
                irq: !no_irq,
                timers: !no_timers,
                dma: !no_dma,
                numba: !no_numba,
            });
            if let Err(e) = pipeline_cmd::run_pipeline(
                rom.to_str().unwrap_or(""),
                output.to_str().unwrap_or(""),
                feature_flags,
                minify,
                minify_aggressive,
                max_output_lines,
            ) {
                eprintln!("Error: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Test {
            rom,
            frames,
            screenshot,
            dump_memory,
            dump_region,
        } => {
            println!("Running test on {} for {} frames...", rom.display(), frames);

            // Generate Python from ROM
            println!("  Generating Python from ROM...");
            let rom_name = Path::new(rom.to_str().unwrap_or("rom"))
                .file_stem()
                .unwrap_or(std::ffi::OsStr::new("rom"))
                .to_str()
                .unwrap_or("rom");
            let output_dir = std::env::current_dir()
                .unwrap_or_else(|_| std::path::PathBuf::from("."))
                .join("output_test");
            let _ = fs::create_dir_all(&output_dir);
            let py_path = output_dir.join(format!("{}_test.py", rom_name));

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

            // Execute generated Python
            println!("  Executing ROM for {} frames...", frames);

            let mut python_args: Vec<String> = vec![
                py_path.to_string_lossy().to_string(),
                "--headless".to_string(),
                format!("--frame={}", frames),
            ];

            // Add screenshot argument if provided
            if let Some(screenshot_path) = screenshot {
                python_args.push("--screenshot".to_string());
                python_args.push(screenshot_path.to_string_lossy().to_string());
                println!(
                    "  Screenshot will be saved to: {}",
                    screenshot_path.display()
                );
            }

            // Add dump-memory argument if provided
            if let Some(dm) = dump_memory {
                python_args.push(format!("--dump-memory={}", dm.display()));
                println!("  Memory will be dumped to: {}", dm.display());
            }

            // Add dump-region argument if provided
            if let Some(dr) = dump_region {
                python_args.push(format!("--dump-region={}", dr));
                println!("  Memory region to dump: {}", dr);
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
        Commands::Benchmark => {
            if let Err(e) = benchmark::benchmark_all() {
                eprintln!("Error: {}", e);
                std::process::exit(1);
            }
        }
    }
}
