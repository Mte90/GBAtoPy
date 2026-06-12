#![allow(dead_code, unused_variables)]
use gbatopy_disasm::operand::ShiftAmount;
use std::fs;

/// Convert ARM shift operator to Python operator
/// Returns the full expression like "r5 << 2" or "(r5 >> 2) | (r5 << 30) & 0xFFFFFFFF"
pub fn shift_to_python(
    reg: u8,
    shift_type: &gbatopy_disasm::operand::ShiftType,
    amount: &ShiftAmount,
) -> String {
    let amt = match amount {
        ShiftAmount::Immediate(n) => *n,
        _ => 0,
    };

    match shift_type {
        gbatopy_disasm::operand::ShiftType::Lsl => format!("r[{}] << {}", reg, amt),
        gbatopy_disasm::operand::ShiftType::Lsr => format!("r[{}] >> {}", reg, amt),
        gbatopy_disasm::operand::ShiftType::Asr => format!("r[{}] >> {}", reg, amt),
        gbatopy_disasm::operand::ShiftType::Ror => {
            format!(
                "(r[{}] >> {}) | (r[{}] << (32 - {})) & 0xFFFFFFFF",
                reg, amt, reg, amt
            )
        }
    }
}

/// Embed runtime Python files into the generated output
/// Filters out relative imports to make the code standalone
pub fn embed_runtime_files() -> String {
    let mut code = String::new();
    let runtime_files = [
        "crates/gbatopy-cli/assets/gba_runtime/memory.py",
        "crates/gbatopy-cli/assets/gba_runtime/ppu.py",
        "crates/gbatopy-cli/assets/gba_runtime/cpu.py",
        "crates/gbatopy-cli/assets/gba_runtime/interrupts.py",
        "crates/gbatopy-cli/assets/gba_runtime/timer.py",
        "crates/gbatopy-cli/assets/gba_runtime/dma.py",
        "crates/gbatopy-cli/assets/gba_runtime/input.py",
        "crates/gbatopy-cli/assets/gba_runtime/apu.py",
        "crates/gbatopy-cli/assets/gba_runtime/bios.py",
    ];

    code.push_str("# === GBA Runtime (embedded) ===\n\n");
    for file_path in &runtime_files {
        if let Ok(content) = fs::read_to_string(file_path) {
            // Filter out relative imports
            let filtered: String = content
                .lines()
                .filter(|line| {
                    let trimmed = line.trim();
                    !trimmed.starts_with("from .")
                        && !trimmed.starts_with("from gba_runtime.")
                        && !trimmed.starts_with("import gba_runtime")
                        && !trimmed.starts_with("from bios")
                })
                .map(|line| line.trim_end())
                .collect::<Vec<_>>()
                .join("\n");
            code.push_str(&filtered);
            code.push_str("\n\n");
        } else {
            eprintln!("WARNING: Could not read {}", file_path);
        }
    }
    code.push_str("# === End of Runtime ===\n\n");
    code
}

/// Load the GBA/Memory classes from the templates directory
pub fn load_classes_template() -> String {
    fs::read_to_string("crates/gbatopy-cli/assets/templates/classes.py")
        .unwrap_or_else(|_| "class GBA: pass\nclass MemorySimple: pass".to_string())
}

/// Load the game loop template from the templates directory
pub fn load_game_loop_template() -> String {
    fs::read_to_string("crates/gbatopy-cli/assets/templates/game_loop.py")
        .unwrap_or_else(|_| "def run_transpiled(): pass".to_string())
}
