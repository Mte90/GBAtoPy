pub mod data_processing;
pub mod branch;
pub mod load_store;
pub mod coprocessor;

#[cfg(test)]
mod regression_tests;

use crate::codegen::thumb;

use gbatopy_disasm::{DecodedInstruction, ArmMode};

pub fn generate_instruction_python(inst: &DecodedInstruction) -> String {
    let opcode = &inst.opcode;
    
    // Dispatch to Thumb codegen if in Thumb mode
    if matches!(inst.mode, ArmMode::Thumb) {
        return generate_thumb_instruction(inst);
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

    format!("raise NotImplementedError('ARM opcode unimplemented at {:#010x}: {}')", inst.address, opcode)
}

fn generate_thumb_instruction(inst: &DecodedInstruction) -> String {
    let opcode = &inst.opcode;
    
    // Thumb conditionals (BEQ, BNE, etc. with condition codes)
    if let Some(code) = thumb::conditionals::generate(inst) {
        return code;
    }
    
    // Thumb branch instructions
    if let Some(code) = thumb::branch::generate(inst) {
        return code;
    }
    
    // Thumb data processing
    if let Some(code) = thumb::data_processing::generate(inst) {
        return code;
    }
    
    // Thumb load/store
    if let Some(code) = thumb::load_store::generate(inst) {
        return code;
    }
    
    // Thumb multiply
    if let Some(code) = thumb::multiply::generate(inst) {
        return code;
    }
    
    // Thumb misc
    if let Some(code) = thumb::misc::generate(inst) {
        return code;
    }
    format!("raise NotImplementedError('THUMB opcode unimplemented at {:#010x}: {}')", inst.address, opcode)
}