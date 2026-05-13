pub fn generate_cmp_instruction(ops: &[arg], _cfg: &arg) -> String {
    // CMP doesn't write to Rd
    format!("r0 = r0 # CMP (flags set)")
}

pub fn generate_cmn_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r0 = r0 # CMN (flags set)")
}

pub fn generate_tst_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r0 = r0 # TST (flags set)")
}

pub fn generate_teq_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r0 = r0 # TEQ (flags set)")
}
