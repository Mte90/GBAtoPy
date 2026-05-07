use gbatopy_disasm::Disassembler;
use std::fs;

pub fn disassemble(rom_path: &str, output_path: &str, _use_ir: bool) -> Result<(), String> {
    let rom = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    let mut disasm = Disassembler::new();
    let instructions = disasm.disassemble(&rom, 0x08000000);

    let json = serde_json::to_string_pretty(&instructions)
        .map_err(|e| format!("Failed to serialize: {}", e))?;

    fs::write(output_path, json).map_err(|e| format!("Failed to write output: {}", e))?;

    println!(
        "Disassembled {} instructions to {}",
        instructions.len(),
        output_path
    );
    Ok(())
}
