pub fn generate_thumb_movw_instruction(ops: &[String]) -> String {
    format!("registers[{}] = {}", ops[0], ops[1])
}

pub fn generate_thumb_movt_instruction(ops: &[String]) -> String {
    format!("registers[{}] = (registers[{}] & 0xFFFF) | ({} << 16)", ops[0], ops[0], ops[1])
}

pub fn generate(inst: &gbatopy_disasm::DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode.to_uppercase();
    let ops: Vec<String> = inst.operands.iter().map(|op| op.to_codegen()).collect();
    
    match opcode.as_str() {
        "MOVW" => Some(generate_thumb_movw_instruction(&ops)),
        "MOVT" => Some(generate_thumb_movt_instruction(&ops)),
        _ => None,
    }
}
