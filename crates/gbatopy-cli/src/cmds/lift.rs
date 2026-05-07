use gbatopy_disasm::Disassembler;
use gbatopy_ir::Lifter;
use std::fs;

pub fn lift(rom_path: &str, output_path: &str) -> Result<(), String> {
    println!("Lifting IR from ROM: {}", rom_path);

    let rom_data = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;
    let mut disassembler = Disassembler::new();
    let instructions = disassembler.disassemble(&rom_data, 0x08000000);

    let mut lifter = Lifter::new();
    let statements = lifter.lift_batch(&instructions);

    println!("Lifted {} IR statements", statements.len());

    let json_output = serde_json::to_string_pretty(&statements)
        .map_err(|e| format!("Failed to serialize IR: {}", e))?;

    fs::write(output_path, json_output).map_err(|e| format!("Failed to write output: {}", e))?;

    println!("IR written to: {}", output_path);
    Ok(())
}
