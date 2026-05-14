pub fn generate_cmp_instruction(ops: &[String]) -> String {
    format!("r{} = cmp r{}", ops[0], ops[1])
}

pub fn generate_cmn_instruction(ops: &[String]) -> String {
    format!("r{} = cmn r{}", ops[0], ops[1])
}

pub fn generate_tst_instruction(ops: &[String]) -> String {
    format!("r{} = tst r{}", ops[0], ops[1])
}

pub fn generate_teq_instruction(ops: &[String]) -> String {
    format!("r{} = teq r{}", ops[0], ops[1])
}
