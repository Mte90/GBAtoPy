pub mod data_processing;
pub mod branch;
pub mod load_store;
pub mod coprocessor;

use gbatopy_disasm::DecodedInstruction;

pub fn generate_instruction_python(inst: &DecodedInstruction) -> String {
    let opcode = &inst.opcode;
    
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
    
    format!("# {} unimplemented", opcode)
}