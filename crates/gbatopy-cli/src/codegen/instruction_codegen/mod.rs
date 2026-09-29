pub mod data_processing;
pub mod branch;
pub mod load_store;
pub mod coprocessor;

#[cfg(test)]
mod regression_tests;

use gbatopy_disasm::{DecodedInstruction, ArmMode};

pub fn generate_instruction_python(inst: &DecodedInstruction) -> String {
    let opcode = &inst.opcode;
    
    // Thumb mode not yet implemented - emit NOP with comment
    if matches!(inst.mode, ArmMode::Thumb) {
        return format!("# Thumb instruction at {:#010x}: {} (unimplemented)\npass", inst.address, opcode);
    }
    
    // ARM mode dispatch
    if let Some(code) = data_processing::generate(inst) {
        return code;
    }
    if let Some(code) = branch::generate(inst) {
        return code;
    }
    if let Some(code) = load_store::generate(inst) {
        return code;
    }
    if let Some(code) = coprocessor::generate(inst) {
        return code;
    }

    // Unhandled ARM instruction - emit NOP with comment instead of crashing
    format!("# unhandled ARM at {:#010x}: {}\npass", inst.address, opcode)
}