pub fn generate_mov_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = r{}", ops[0], ops[1])
}

pub fn generate_add_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = r{} + r{}", ops[0], ops[1], ops[2])
}

pub fn generate_sub_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = r{} - r{}", ops[0], ops[1], ops[2])
}

pub fn generate_and_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = r{} & r{}", ops[0], ops[1], ops[2])
}

pub fn generate_or_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = r{} | r{}", ops[0], ops[1], ops[2])
}

pub fn generate_xor_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = r{} ^ r{}", ops[0], ops[1], ops[2])
}

pub fn generate_bic_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = r{} & ~r{}", ops[0], ops[1], ops[2])
}

pub fn generate_mvn_instruction(ops: &[arg], _cfg: &arg) -> String {
    format!("r{} = ~r{}", ops[0], ops[1])
}
