pub mod branch;
pub mod coprocessor;
pub mod data_processing;
pub mod load_store;

#[cfg(test)]
mod regression_tests;

use gbatopy_disasm::DecodedInstruction;

pub fn generate_instruction_python(inst: &DecodedInstruction) -> String {
    let opcode = &inst.opcode;

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

    // Unhandled ARM instruction - emit stderr diagnostic (survives minification) + pass
    format!(
        "sys.stderr.write('unhandled ARM at {:#010x}: {}\\n')\npass",
        inst.address, opcode
    )
}
