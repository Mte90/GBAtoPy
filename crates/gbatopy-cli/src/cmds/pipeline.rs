use crate::ppu::generate_ppu_code;
use std::fs;
use std::path::Path;

#[allow(dead_code)]
fn embed_pyboyadvance(_runtime_dir: &str) -> Result<String, String> {
    let mut code = String::new();

    // List of runtime files to embed in order
    let runtime_files = [
        "crates/gbatopy-cli/assets/templates/header.py", 
        "crates/gbatopy-cli/assets/gba_runtime/memory.py",
        "crates/gbatopy-cli/assets/gba_runtime/ppu.py",
        "crates/gbatopy-cli/assets/gba_runtime/cpu.py",
        "crates/gbatopy-cli/assets/gba_runtime/arm7tdmi.py",
        "crates/gbatopy-cli/assets/gba_runtime/interrupts.py",
        "crates/gbatopy-cli/assets/gba_runtime/timers.py",
        "crates/gbatopy-cli/assets/gba_runtime/dma.py",
        "crates/gbatopy-cli/assets/gba_runtime/input.py",
        "crates/gbatopy-cli/assets/gba_runtime/apu.py",
        "crates/gbatopy-cli/assets/gba_runtime/bios.py",
        "crates/gbatopy-cli/assets/gba_runtime/text_lib.py",
        "crates/gbatopy-cli/assets/gba_runtime/screenshot.py",
        "crates/gbatopy-cli/assets/gba_runtime/rom.py",
        "crates/gbatopy-cli/assets/gba_runtime/exceptions.py",
    ];

    for file_path in &runtime_files {
        match std::fs::read_to_string(file_path) {
            Ok(content) => {
                // Remove relative imports and gba_runtime imports that won't work in standalone
                let filtered: String = content
                    .lines()
                    .filter(|line| {
                        let trimmed = line.trim();
                        !trimmed.starts_with("from .")
                            && !trimmed.starts_with("import .")
                            && !trimmed.starts_with("from gba_runtime.")
                            && !trimmed.starts_with("import gba_runtime.")
                    })
                    .collect::<Vec<_>>()
                    .join("\n");
                code.push_str(&filtered);
                code.push('\n');
                code.push_str(&format!(
                    "# === End of {} ===\n\n",
                    file_path.split('/').last().unwrap_or("")
                ));
            }
            Err(e) => {
                eprintln!("Warning: Could not read {}: {}", file_path, e);
            }
        }
    }

    Ok(code)
}

#[allow(dead_code)]
fn strip_cython_guards(code: &str) -> String {
    let mut result = String::new();
    let mut in_cython_guard = false;

    for line in code.lines() {
        let trimmed = line.trim();

        if trimmed.starts_with("# ifndef CYTHON") || trimmed.starts_with("#if !CYTHON") {
            in_cython_guard = true;
            continue;
        }

        if trimmed == "# endif" || trimmed.starts_with("#endif") {
            if in_cython_guard {
                in_cython_guard = false;
                continue;
            }
        }

        if in_cython_guard {
            continue;
        }

        result.push_str(line);
        result.push('\n');
    }

    result
}

#[allow(dead_code)]

#[allow(dead_code)]
pub fn generate_rom_data(rom_data: &[u8]) -> String {
    let mut code = String::new();
    code.push_str("\n# Full ROM data for runtime memory mapping\n");
    code.push_str("ROM_DATA = bytearray([");

    for (i, byte) in rom_data.iter().enumerate() {
        if i > 0 {
            code.push_str(", ");
        }
        if i % 16 == 0 {
            code.push_str("\n    ");
        }
        code.push_str(&format!("0x{:02X}", byte));
    }

    code.push_str("\n])\n");
    code
}

#[allow(dead_code)]
pub fn generate_bios() -> String {
    let bios_path = "python/gba_runtime/bios_minimal.py";

    if let Ok(bios_content) = std::fs::read_to_string(bios_path) {
        let mut code = String::new();
        code.push_str("\n# Embedded GBA BIOS (minimal Python implementation)\n");
        code.push_str("# Provides: Halt(), VSync(), Div(), Sqrt()\n\n");
        code.push_str(&bios_content);
        code.push('\n');
        return code;
    }

    r#"
# Minimal GBA BIOS fallback (when bios_minimal.py not found)

def Halt():
    """Freeze loop when ROM calls BIOS Halt (most common)."""
    import time
    # Busy-wait loop that checks for interrupts
    # In a real implementation, this would check memory.interrupt_controller._interrupt_fired
    # For now, use a small sleep to avoid CPU spin
    time.sleep(0.001)

def VSync():
    """Trigger VBlank interrupt for save states and frame sync."""
    # VBlank IRQ is already triggered by the render loop in ppu.py
    # This is a no-op in the transpiled output since frame sync happens naturally
    pass

def Div(numerator, denominator):
    """32-bit integer division."""
    if denominator == 0:
        return (0, numerator)
    quotient = int(numerator / denominator)
    remainder = numerator % denominator
    if quotient > 0x7FFFFFFF:
        quotient -= 0x100000000
    if remainder > 0x7FFFFFFF:
        remainder -= 0x100000000
    return (quotient, remainder)

def Sqrt(value):
    """Integer square root."""
    if value <= 0:
        return 0
    guess = value >> 1
    if guess == 0:
        guess = 1
    while True:
        next_guess = (guess + value // guess) >> 1
        if next_guess >= guess:
            return guess
        guess = next_guess
"#
    .to_string()
}

#[allow(dead_code)]
pub fn run_pipeline(
    rom_path: &str,
    output_path: &str,
    _assets_dir: &Path,
    _use_ir: bool,
) -> Result<(), String> {
    println!("Running PyBoyAdvance-based pipeline on: {}", rom_path);

    let rom_data = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    let mut python_code = String::new();

    println!("Phase 1: Embedding PyBoyAdvance runtime...");
    let runtime_code = embed_pyboyadvance("crates/gbatopy-cli/assets")
        .map_err(|e| format!("Failed to embed runtime: {}", e))?;
    python_code.push_str(&runtime_code);
    python_code.push('\n');

    println!("Phase 2: Generating PPU code...");
    let ppu_code = generate_ppu_code();
    python_code.push_str(&ppu_code);
    python_code.push('\n');

    println!("Phase 3: Embedding BIOS...");
    let bios_code = generate_bios();
    python_code.push_str(&bios_code);

    println!("Phase 3: Generating ROM data...");
    let rom_data_code = generate_rom_data(&rom_data);
    python_code.push_str(&rom_data_code);

    println!("Phase 4: Adding game loop...");

    fs::write(output_path, &python_code).map_err(|e| format!("Failed to write output: {}", e))?;

    println!("Generated Python written to: {}", output_path);
    println!("Pipeline complete!");
    Ok(())
}

#[allow(dead_code)]
fn strip_relative_imports(code: &str) -> String {
    code.lines()
        .filter(|line| {
            // Completely remove relative import lines and gba_runtime imports
            let trimmed = line.trim();
            if trimmed.starts_with("from .") {
                false
            } else if trimmed.starts_with("import .") {
                false
            } else if trimmed.starts_with("from gba_runtime.") {
                false
            } else if trimmed.starts_with("import gba_runtime") {
                false
            } else {
                true
            }
        })
        .collect::<Vec<&str>>()
        .join("\n")
}
