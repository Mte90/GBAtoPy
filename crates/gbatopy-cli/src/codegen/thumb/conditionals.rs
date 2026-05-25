pub fn generate_thumb_cbnz_instruction(ops: &[String]) -> String {
    // CBNZ Rn, target - Compare and Branch if Not Zero
    // ops[0] = register number (e.g., "5" for R5)
    // ops[1] = target address (e.g., "0x08000100")
    format!("if r[{}] != 0: r[15] = {}", ops[0], ops[1])
}

pub fn generate_thumb_cbz_instruction(ops: &[String]) -> String {
    // CBZ Rn, target - Compare and Branch if Zero
    // ops[0] = register number (e.g., "5" for R5)
    // ops[1] = target address (e.g., "0x08000100")
    format!("if r[{}] == 0: r[15] = {}", ops[0], ops[1])
}

// Conditional branches (14 variants) - use CPSR flags (placeholders for now, to be implemented in Tasks 14-17)
pub fn generate_thumb_beq_instruction(ops: &[String]) -> String {
    // BEQ target - Branch if Equal (Z=1)
    format!("if cpsr_z == 1: r[15] = {}", ops[0])
}

pub fn generate_thumb_bne_instruction(ops: &[String]) -> String {
    // BNE target - Branch if Not Equal (Z=0)
    format!("if cpsr_z == 0: r[15] = {}", ops[0])
}

pub fn generate_thumb_bcs_instruction(ops: &[String]) -> String {
    // BCS target - Branch if Carry Set (C=1)
    format!("if cpsr_c == 1: r[15] = {}", ops[0])
}

pub fn generate_thumb_bcc_instruction(ops: &[String]) -> String {
    // BCC target - Branch if Carry Clear (C=0)
    format!("if cpsr_c == 0: r[15] = {}", ops[0])
}

pub fn generate_thumb_bmi_instruction(ops: &[String]) -> String {
    // BMI target - Branch if Minus (N=1)
    format!("if cpsr_n == 1: r[15] = {}", ops[0])
}

pub fn generate_thumb_bpl_instruction(ops: &[String]) -> String {
    // BPL target - Branch if Plus (N=0)
    format!("if cpsr_n == 0: r[15] = {}", ops[0])
}

pub fn generate_thumb_bvs_instruction(ops: &[String]) -> String {
    // BVS target - Branch if Overflow Set (V=1)
    format!("if cpsr_v == 1: r[15] = {}", ops[0])
}

pub fn generate_thumb_bvc_instruction(ops: &[String]) -> String {
    // BVC target - Branch if Overflow Clear (V=0)
    format!("if cpsr_v == 0: r[15] = {}", ops[0])
}

pub fn generate_thumb_bhi_instruction(ops: &[String]) -> String {
    // BHI target - Branch if Higher (C=1 and Z=0)
    format!("if cpsr_c == 1 and cpsr_z == 0: r[15] = {}", ops[0])
}

pub fn generate_thumb_bls_instruction(ops: &[String]) -> String {
    // BLS target - Branch if Lower or Same (C=0 or Z=1)
    format!("if cpsr_c == 0 or cpsr_z == 1: r[15] = {}", ops[0])
}

pub fn generate_thumb_bge_instruction(ops: &[String]) -> String {
    // BGE target - Branch if Greater or Equal (N==V)
    format!("if cpsr_n == cpsr_v: r[15] = {}", ops[0])
}

pub fn generate_thumb_blt_instruction(ops: &[String]) -> String {
    // BLT target - Branch if Less Than (N!=V)
    format!("if cpsr_n != cpsr_v: r[15] = {}", ops[0])
}

pub fn generate_thumb_bgt_instruction(ops: &[String]) -> String {
    // BGT target - Branch if Greater Than (Z=0 and N==V)
    format!("if cpsr_z == 0 and cpsr_n == cpsr_v: r[15] = {}", ops[0])
}

pub fn generate_thumb_ble_instruction(ops: &[String]) -> String {
    // BLE target - Branch if Less or Equal (Z=1 or N!=V)
    format!("if cpsr_z == 1 or cpsr_n != cpsr_v: r[15] = {}", ops[0])
}
