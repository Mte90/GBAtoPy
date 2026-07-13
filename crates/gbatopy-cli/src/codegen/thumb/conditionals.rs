pub fn generate_thumb_cbnz_instruction(ops: &[String]) -> String {
    format!("if registers[{}] != 0: registers[15] = {}", ops[0], ops[1])
}

pub fn generate_thumb_cbz_instruction(ops: &[String]) -> String {
    format!("if registers[{}] == 0: registers[15] = {}", ops[0], ops[1])
}

pub fn generate_thumb_beq_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('EQ'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bne_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('NE'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bcs_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('CS'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bcc_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('CC'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bmi_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('MI'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bpl_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('PL'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bvs_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('VS'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bvc_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('VC'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bhi_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('HI'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bls_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('LS'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bge_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('GE'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_blt_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('LT'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_bgt_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('GT'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate_thumb_ble_instruction(ops: &[String]) -> String {
    format!(
        "if cpsr_check('LE'):\n    registers[15] = {}\nelse:\n    registers[15] = (registers[15] + 2) & 0xFFFFFFFF",
        ops[0]
    )
}

pub fn generate(inst: &gbatopy_disasm::DecodedInstruction) -> Option<String> {
    let opcode = &inst.opcode.to_uppercase();
    let ops: Vec<String> = inst.operands.iter().map(|op| op.to_codegen()).collect();

    match opcode.as_str() {
        "CBNZ" => Some(generate_thumb_cbnz_instruction(&ops)),
        "CBZ" => Some(generate_thumb_cbz_instruction(&ops)),
        "BEQ" => Some(generate_thumb_beq_instruction(&ops)),
        "BNE" => Some(generate_thumb_bne_instruction(&ops)),
        "BCS" => Some(generate_thumb_bcs_instruction(&ops)),
        "BCC" => Some(generate_thumb_bcc_instruction(&ops)),
        "BMI" => Some(generate_thumb_bmi_instruction(&ops)),
        "BPL" => Some(generate_thumb_bpl_instruction(&ops)),
        "BVS" => Some(generate_thumb_bvs_instruction(&ops)),
        "BVC" => Some(generate_thumb_bvc_instruction(&ops)),
        "BHI" => Some(generate_thumb_bhi_instruction(&ops)),
        "BLS" => Some(generate_thumb_bls_instruction(&ops)),
        "BGE" => Some(generate_thumb_bge_instruction(&ops)),
        "BLT" => Some(generate_thumb_blt_instruction(&ops)),
        "BGT" => Some(generate_thumb_bgt_instruction(&ops)),
        "BLE" => Some(generate_thumb_ble_instruction(&ops)),
        _ => None,
    }
}
