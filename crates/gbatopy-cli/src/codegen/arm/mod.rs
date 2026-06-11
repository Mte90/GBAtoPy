pub mod data_processing;
pub mod load_store;
pub mod branch;
pub mod multiply;
pub mod coprocessor;

pub use data_processing::generate_data_processing;
pub use load_store::generate_load_store;
pub use branch::generate_branch;
pub use multiply::generate_multiply;
pub use coprocessor::generate_coprocessor;

use gbatopy_disasm::DecodedInstruction;

pub fn generate_arm_instruction(inst: &DecodedInstruction) -> String {
    let opcode = &inst.opcode;
    let ops = &inst.operands;
    
    let base_opcode = opcode.split_whitespace().next().unwrap_or(opcode);
    
    if let Some(code) = generate_data_processing(inst) {
        return code;
    }
    if let Some(code) = generate_load_store(inst) {
        return code;
    }
    if let Some(code) = generate_branch(inst) {
        return code;
    }
    if let Some(code) = generate_multiply(inst) {
        return code;
    }
    if let Some(code) = generate_coprocessor(inst) {
        return code;
    }
    
    format!("# {} unimplemented", opcode)
}