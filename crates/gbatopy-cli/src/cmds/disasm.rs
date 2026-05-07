use gbatopy_disasm::Disassembler;
use std::fs;

pub fn disassemble(rom_path: &str, output_path: &str, _use_ir: bool) -> Result<(), String> {
    println!("Disassembling ROM: {}", rom_path);

    let rom_data = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;
    let mut disassembler = Disassembler::new();
    let instructions = disassembler.disassemble(&rom_data, 0x08000000);

    println!("Disassembled {} instructions", instructions.len());

    let json_output = serde_json::to_string_pretty(&instructions)
        .map_err(|e| format!("Failed to serialize instructions: {}", e))?;

    fs::write(output_path, json_output).map_err(|e| format!("Failed to write output: {}", e))?;

    println!("Disassembly written to: {}", output_path);
    Ok(())
}
