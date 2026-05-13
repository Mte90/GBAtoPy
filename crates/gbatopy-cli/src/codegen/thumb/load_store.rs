pub fn generate_ldrh_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = load_halfword(0x{:08X})", ops[0], 0x1234)
}

pub fn generate_strh_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("store_halfword(0x{:08X}, r{})", 0x5678, ops[1])
}

pub fn generate_ldrb_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = load_byte(0x{:08X})", ops[0], 0x1234)
}

pub fn generate_strb_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("store_byte(0x{:08X}, r{})", 0x5678, ops[1])
}
