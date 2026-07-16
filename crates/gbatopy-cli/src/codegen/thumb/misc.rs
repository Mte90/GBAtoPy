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
        "SWI" => {
            // SWI/SVC: software interrupt - call the global swi_handler(swi_num)
            // with the 8-bit immediate SWI number embedded in the Thumb instruction.
            let swi_num = match inst.operands.first() {
                Some(gbatopy_disasm::Operand::Immediate(n)) => *n & 0xFF,
                _ => 0,
            };
            Some(format!("swi_handler({:#X})", swi_num))
        }
        _ => None,
    }
}
