pub fn generate_load_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = load(0x{:08X})", ops[0], 0x1234)
}

pub fn generate_store_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("store(0x{:08X}, r{})", 0x5678, ops[1])
}

pub fn generate_ldm_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("ldm(0x{:08X}, [{}])", 0x1234, ops[1..].join(", "))
}

pub fn generate_stm_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("stm(0x{:08X}, [{}])", 0x5678, ops[1..].join(", "))
}

pub fn generate_prefetch_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("prefetch(0x{:08X})", 0x1234)
}
