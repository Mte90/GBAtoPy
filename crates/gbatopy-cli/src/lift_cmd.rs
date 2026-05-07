use gbatopy_ir::Lifter;
use std::fs;

pub fn lift(disasm_path: &str, output_path: &str) -> Result<(), String> {
    let disasm_json =
        fs::read_to_string(disasm_path).map_err(|e| format!("Failed to read disasm: {}", e))?;

    let instructions: Vec<gbatopy_disasm::DecodedInstruction> = serde_json::from_str(&disasm_json)
        .map_err(|e| format!("Failed to parse disasm JSON: {}", e))?;

    let mut lifter = Lifter::new();
    let ir_statements = lifter.lift_batch(&instructions);

    let ir_json = serde_json::to_string_pretty(&ir_statements)
        .map_err(|e| format!("Failed to serialize IR: {}", e))?;

    fs::write(output_path, ir_json).map_err(|e| format!("Failed to write output: {}", e))?;

    println!("Lifted to IR, {} statements", ir_statements.len());
    Ok(())
}
