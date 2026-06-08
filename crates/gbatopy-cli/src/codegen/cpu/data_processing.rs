pub fn generate_mov_instruction(ops: &[String]) -> String {
    // ops[0] = Rd, ops[1] = operand
    let mut code = format!("r[{}] = {}", ops[0], ops[1]);
    // Update flags if S-bit is set (for MOVS)
    if ops.len() > 2 && ops[2] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if ({} & 0x80000000) != 0 else 0",
            ops[1]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if {} == 0 else 0", ops[1]));
        code.push_str("\ncpsr_c = 0\n"); // Clear carry for MOV
        code.push_str("\ncpsr_v = 0\n"); // Clear overflow for MOV
    }
    code
}

pub fn generate_add_instruction(ops: &[String]) -> String {
    // ops[0] = Rd, ops[1] = Rn, ops[2] = operand
    let mut code = format!("r[{}] = r[{}] + {}", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str(&format!(
            "\ncpsr_c = 1 if r[{}] + {} >= 0x100000000 else 0",
            ops[1], ops[2]
        ));
        code.push_str(&format!("\ncpsr_v = 1 if ((r[{}] ^ {}) & (r[{}] ^ {})) != 0 and ((r[{}] ^ {}) & 0x80000000) != 0 else 0", ops[1], ops[2], ops[0], ops[1], ops[0], ops[1]));
    }
    code
}

pub fn generate_sub_instruction(ops: &[String]) -> String {
    // ops[0] = Rd, ops[1] = Rn, ops[2] = operand
    let mut code = format!("r[{}] = r[{}] - {}", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str(&format!("\ncpsr_c = 1 if r[{}] >= {} else 0", ops[1], ops[2]));
        code.push_str(&format!("\ncpsr_v = 1 if ((r[{}] ^ {}) & (r[{}] ^ {})) != 0 and ((r[{}] ^ {}) & 0x80000000) != 0 else 0", ops[1], ops[2], ops[0], ops[1], ops[0], ops[1]));
    }
    code
}

pub fn generate_and_instruction(ops: &[String]) -> String {
    let mut code = format!("r[{}] = r[{}] & {}", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str("\ncpsr_c = cpsr_c  // Carry unchanged for AND\n");
        code.push_str("\ncpsr_v = 0\n");
    }
    code
}

pub fn generate_or_instruction(ops: &[String]) -> String {
    let mut code = format!("r[{}] = r[{}] | {}", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str("\ncpsr_c = cpsr_c\n");
        code.push_str("\ncpsr_v = 0\n");
    }
    code
}

pub fn generate_xor_instruction(ops: &[String]) -> String {
    let mut code = format!("r[{}] = r[{}] ^ {}", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str("\ncpsr_c = cpsr_c\n");
        code.push_str("\ncpsr_v = 0\n");
    }
    code
}

pub fn generate_bic_instruction(ops: &[String]) -> String {
    let mut code = format!("r[{}] = r[{}] & ~{}", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str("\ncpsr_c = cpsr_c\n");
        code.push_str("\ncpsr_v = 0\n");
    }
    code
}

pub fn generate_mvn_instruction(ops: &[String]) -> String {
    let mut code = format!("r[{}] = ~{}", ops[0], ops[1]);
    if ops.len() > 2 && ops[2] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str("\ncpsr_c = cpsr_c\n");
        code.push_str("\ncpsr_v = 0\n");
    }
    code
}

pub fn generate_cmp_instruction(ops: &[String]) -> String {
    let mut code = format!("_cmp_result = r[{}] - {}", ops[0], ops[1]);
    code.push_str(&format!(
        "\ncpsr_n = 1 if (_cmp_result & 0x80000000) != 0 else 0"
    ));
    code.push_str(&format!("\ncpsr_z = 1 if _cmp_result == 0 else 0"));
    code.push_str(&format!("\ncpsr_c = 1 if r[{}] >= {} else 0", ops[0], ops[1]));
    code.push_str(&format!("\ncpsr_v = 1 if ((r[{}] ^ {}) & (r[{}] ^ _cmp_result)) != 0 and ((r[{}] ^ {}) & 0x80000000) != 0 else 0", ops[0], ops[1], ops[0], ops[0], ops[1]));
    code
}

pub fn generate_cmn_instruction(ops: &[String]) -> String {
    let mut code = format!("_cmn_result = r[{}] + {}", ops[0], ops[1]);
    code.push_str(&format!(
        "\ncpsr_n = 1 if (_cmn_result & 0x80000000) != 0 else 0"
    ));
    code.push_str(&format!("\ncpsr_z = 1 if _cmn_result == 0 else 0"));
    code.push_str(&format!(
        "\ncpsr_c = 1 if r[{}] + {} >= 0x100000000 else 0",
        ops[0], ops[1]
    ));
    code.push_str(&format!("\ncpsr_v = 1 if ((r[{}] ^ {}) & (r[{}] ^ _cmn_result)) != 0 and ((r[{}] ^ {}) & 0x80000000) != 0 else 0", ops[0], ops[1], ops[0], ops[0], ops[1]));
    code
}

pub fn generate_teq_instruction(ops: &[String]) -> String {
    let mut code = format!("_teq_result = r[{}] ^ {}", ops[0], ops[1]);
    code.push_str(&format!(
        "\ncpsr_n = 1 if (_teq_result & 0x80000000) != 0 else 0"
    ));
    code.push_str(&format!("\ncpsr_z = 1 if _teq_result == 0 else 0"));
    code.push_str("\ncpsr_c = cpsr_c\n");
    code.push_str("\ncpsr_v = 0\n");
    code
}

pub fn generate_tst_instruction(ops: &[String]) -> String {
    let mut code = format!("_tst_result = r[{}] & {}", ops[0], ops[1]);
    code.push_str(&format!(
        "\ncpsr_n = 1 if (_tst_result & 0x80000000) != 0 else 0"
    ));
    code.push_str(&format!("\ncpsr_z = 1 if _tst_result == 0 else 0"));
    code.push_str("\ncpsr_c = cpsr_c\n");
    code.push_str("\ncpsr_v = 0\n");
    code
}

pub fn generate_rsb_instruction(ops: &[String]) -> String {
    // RSB Rd, Rn, Operand2 (Reverse Subtract: Rd = Operand2 - Rn)
    let mut code = format!("r[{}] = {} - r[{}]", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str(&format!("\ncpsr_c = 1 if {} >= r[{}] else 0", ops[1], ops[2]));
        code.push_str(&format!("\ncpsr_v = 1 if (({} ^ r[{}]) & (r[{}] ^ {})) != 0 and (({} ^ r[{}]) & 0x80000000) != 0 else 0", ops[1], ops[2], ops[0], ops[1], ops[1], ops[2]));
    }
    code
}

pub fn generate_adc_instruction(ops: &[String]) -> String {
    // ADC Rd, Rn, Operand2 (Add with Carry: Rd = Rn + Operand2 + Carry)
    let mut code = format!("r[{}] = r[{}] + {} + cpsr_c", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str(&format!(
            "\ncpsr_c = 1 if r[{}] + {} + cpsr_c >= 0x100000000 else 0",
            ops[1], ops[2]
        ));
        code.push_str(&format!("\ncpsr_v = 1 if ((r[{}] ^ {}) & (r[{}] ^ r[{}])) != 0 and ((r[{}] ^ {}) & 0x80000000) != 0 else 0", ops[1], ops[2], ops[0], ops[1], ops[0], ops[1]));
    }
    code
}

pub fn generate_sbc_instruction(ops: &[String]) -> String {
    // SBC Rd, Rn, Operand2 (Subtract with Carry: Rd = Rn - Operand2 + Carry - 1)
    let mut code = format!("r[{}] = r[{}] - {} + cpsr_c - 1", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str(&format!(
            "\ncpsr_c = 1 if r[{}] >= {} + (1 - cpsr_c) else 0",
            ops[1], ops[2]
        ));
        code.push_str(&format!("\ncpsr_v = 1 if ((r[{}] ^ {}) & (r[{}] ^ r[{}])) != 0 and ((r[{}] ^ {}) & 0x80000000) != 0 else 0", ops[1], ops[2], ops[0], ops[1], ops[0], ops[1]));
    }
    code
}

pub fn generate_rsc_instruction(ops: &[String]) -> String {
    // RSC Rd, Rn, Operand2 (Reverse Subtract with Carry: Rd = Operand2 - Rn + Carry - 1)
    let mut code = format!("r[{}] = {} - r[{}] + cpsr_c - 1", ops[0], ops[1], ops[2]);
    if ops.len() > 3 && ops[3] == "s" {
        code.push_str(&format!(
            "\ncpsr_n = 1 if (r[{}] & 0x80000000) != 0 else 0",
            ops[0]
        ));
        code.push_str(&format!("\ncpsr_z = 1 if r[{}] == 0 else 0", ops[0]));
        code.push_str(&format!(
            "\ncpsr_c = 1 if {} >= r[{}] + (1 - cpsr_c) else 0",
            ops[1], ops[2]
        ));
        code.push_str(&format!("\ncpsr_v = 1 if (({} ^ r[{}]) & (r[{}] ^ {})) != 0 and (({} ^ r[{}]) & 0x80000000) != 0 else 0", ops[1], ops[2], ops[0], ops[1], ops[1], ops[2]));
    }
    code
}

pub fn generate_umull_instruction(ops: &[String]) -> String {
    // UMULL RdLo, RdHi, Rn, Operand2 (Unsigned Multiply Long: 64-bit result)
    let rd_lo = &ops[0];
    let rd_hi = &ops[1];
    let rn = &ops[2];
    let op2 = &ops[3];
    let mut code = format!("_umull_result = (r[{}] * {}) & 0xFFFFFFFFFFFFFFFF", rn, op2);
    code.push_str(&format!("\nr[{}] = _umull_result & 0xFFFFFFFF", rd_lo));
    code.push_str(&format!(
        "\nr[{}] = (_umull_result >> 32) & 0xFFFFFFFF",
        rd_hi
    ));
    if ops.len() > 4 && ops[4] == "s" {
        code.push_str("\ncpsr_n = 1 if (_umull_result & 0x8000000000000000) != 0 else 0");
        code.push_str("\ncpsr_z = 1 if _umull_result == 0 else 0");
        code.push_str("\ncpsr_c = cpsr_c\n");
        code.push_str("\ncpsr_v = 0\n");
    }
    code
}

pub fn generate_smull_instruction(ops: &[String]) -> String {
    // SMULL RdLo, RdHi, Rn, Operand2 (Signed Multiply Long: 64-bit result)
    let rd_lo = &ops[0];
    let rd_hi = &ops[1];
    let rn = &ops[2];
    let op2 = &ops[3];
    let mut code = format!("_smull_result = (r[{}] * {}) & 0xFFFFFFFFFFFFFFFF", rn, op2);
    code.push_str(&format!("\nr[{}] = _smull_result & 0xFFFFFFFF", rd_lo));
    code.push_str(&format!(
        "\nr[{}] = (_smull_result >> 32) & 0xFFFFFFFF",
        rd_hi
    ));
    if ops.len() > 4 && ops[4] == "s" {
        code.push_str("\ncpsr_n = 1 if (_smull_result & 0x8000000000000000) != 0 else 0");
        code.push_str("\ncpsr_z = 1 if _smull_result == 0 else 0");
        code.push_str("\ncpsr_c = cpsr_c\n");
        code.push_str("\ncpsr_v = 0\n");
    }
    code
}

pub fn generate_umlal_instruction(ops: &[String]) -> String {
    // UMLAL RdLo, RdHi, Rn, Operand2 (Unsigned Multiply Accumulate Long)
    let rd_lo = &ops[0];
    let rd_hi = &ops[1];
    let rn = &ops[2];
    let op2 = &ops[3];
    let mut code = format!("_umlal_acc = (r[{}] << 32) | r[{}]", rd_hi, rd_lo);
    code.push_str(&format!(
        "\n_umlal_result = _umlal_acc + (r[{}] * {}) & 0xFFFFFFFFFFFFFFFF",
        rn, op2
    ));
    code.push_str(&format!("\nr[{}] = _umlal_result & 0xFFFFFFFF", rd_lo));
    code.push_str(&format!(
        "\nr[{}] = (_umlal_result >> 32) & 0xFFFFFFFF",
        rd_hi
    ));
    if ops.len() > 4 && ops[4] == "s" {
        code.push_str("\ncpsr_n = 1 if (_umlal_result & 0x8000000000000000) != 0 else 0");
        code.push_str("\ncpsr_z = 1 if _umlal_result == 0 else 0");
        code.push_str("\ncpsr_c = cpsr_c\n");
        code.push_str("\ncpsr_v = 0\n");
    }
    code
}

pub fn generate_smlal_instruction(ops: &[String]) -> String {
    // SMLAL RdLo, RdHi, Rn, Operand2 (Signed Multiply Accumulate Long)
    let rd_lo = &ops[0];
    let rd_hi = &ops[1];
    let rn = &ops[2];
    let op2 = &ops[3];
    let mut code = format!("_smlal_acc = (r[{}] << 32) | r[{}]", rd_hi, rd_lo);
    code.push_str(&format!(
        "\n_smlal_result = _smlal_acc + (r[{}] * {}) & 0xFFFFFFFFFFFFFFFF",
        rn, op2
    ));
    code.push_str(&format!("\nr[{}] = _smlal_result & 0xFFFFFFFF", rd_lo));
    code.push_str(&format!(
        "\nr[{}] = (_smlal_result >> 32) & 0xFFFFFFFF",
        rd_hi
    ));
    if ops.len() > 4 && ops[4] == "s" {
        code.push_str("\ncpsr_n = 1 if (_smlal_result & 0x8000000000000000) != 0 else 0");
        code.push_str("\ncpsr_z = 1 if _smlal_result == 0 else 0");
        code.push_str("\ncpsr_c = cpsr_c\n");
        code.push_str("\ncpsr_v = 0\n");
    }
    code
}

pub fn generate_swap_instruction(ops: &[String]) -> String {
    // SWP Rd, Rn, Rm (Atomic swap: Rd = [Rn], [Rn] = Rm)
    let rd = ops[0].clone();
    let rn = ops[1].clone();
    let rm = ops[2].clone();
    let code = format!("_swap_addr = r[{}]\n_swap_old = memory.read_u32(_swap_addr)\nmemory.write_u32(_swap_addr, r[{}])\nr[{}] = _swap_old", rn, rm, rd);
    code
}

pub fn generate_swapb_instruction(ops: &[String]) -> String {
    // SWPB Rd, Rn, Rm (Atomic swap byte: Rd = [Rn][0], [Rn][0] = Rm[0])
    let rd = ops[0].clone();
    let rn = ops[1].clone();
    let rm = ops[2].clone();
    let code = format!("_swapb_addr = r[{}]\n_swapb_old = memory.read_u8(_swapb_addr)\nmemory.write_u8(_swapb_addr, r[{}] & 0xFF)\nr[{}] = _swapb_old", rn, rm, rd);
    code
}

pub fn generate_mrs_instruction(ops: &[String]) -> String {
    // MRS Rd, CPSR/SPSR (Move Status Register to general register)
    let rd = ops[0].clone();
    let status_reg = ops[1].clone(); // "cpsr" or "spsr"
    let code = format!("if {} == \"cpsr\":\n    r[{}] = (cpsr_n << 31) | (cpsr_z << 30) | (cpsr_c << 29) | (cpsr_v << 28)\nelse:\n    r[{}] = (spsr_n << 31) | (spsr_z << 30) | (spsr_c << 29) | (spsr_v << 28)", status_reg, rd, rd);
    code
}

pub fn generate_msr_instruction(ops: &[String]) -> String {
    let status_reg = ops[0].clone();
    let op = ops[1].clone();
    let mut code = String::new();
    if status_reg == "cpsr" {
        code.push_str(&format!("_msr_val = {}\n", op));
        code.push_str("cpsr_n = 1 if (_msr_val & 0x80000000) != 0 else 0\n");
        code.push_str("cpsr_z = 1 if (_msr_val & 0x40000000) != 0 else 0\n");
        code.push_str("cpsr_c = 1 if (_msr_val & 0x20000000) != 0 else 0\n");
        code.push_str("cpsr_v = 1 if (_msr_val & 0x10000000) != 0 else 0\n");
    } else {
        code.push_str(&format!("_msr_val = {}\n", op));
        code.push_str("spsr_n = 1 if (_msr_val & 0x80000000) != 0 else 0\n");
        code.push_str("spsr_z = 1 if (_msr_val & 0x40000000) != 0 else 0\n");
        code.push_str("spsr_c = 1 if (_msr_val & 0x20000000) != 0 else 0\n");
        code.push_str("spsr_v = 1 if (_msr_val & 0x10000000) != 0 else 0\n");
    }
    code
}

pub fn generate_clz_instruction(ops: &[String]) -> String {
    // CLZ Rd, Rm (Count Leading Zeros)
    let rd = ops[0].clone();
    let rm = ops[1].clone();
    let code = format!("_clz_val = r[{}] & 0xFFFFFFFF\n_clz_count = 0\nfor _i in range(32):\n    if (_clz_val & 0x80000000) != 0:\n        break\n    _clz_count += 1\n    _clz_val = (_clz_val << 1) & 0xFFFFFFFF\nr[{}] = _clz_count", rm, rd);
    code
}

pub fn generate_qadd_instruction(ops: &[String]) -> String {
    // QADD Rd, Rn, Rm (Saturating Add)
    let rd = ops[0].clone();
    let rn = ops[1].clone();
    let rm = ops[2].clone();
    let mut code = format!("_qadd_result = r[{}] + r[{}]\n", rn, rm);
    code.push_str("if _qadd_result > 0x7FFFFFFF:\n");
    code.push_str(&format!("    r[{}] = 0x7FFFFFFF\n", rd));
    code.push_str("elif _qadd_result < 0x80000000:\n");
    code.push_str(&format!("    r[{}] = 0x80000000\n", rd));
    code.push_str("else:\n");
    code.push_str(&format!("    r[{}] = _qadd_result\n", rd));
    code
}

pub fn generate_qsub_instruction(ops: &[String]) -> String {
    // QSUB Rd, Rn, Rm (Saturating Subtract)
    let rd = ops[0].clone();
    let rn = ops[1].clone();
    let rm = ops[2].clone();
    let mut code = format!("_qsub_result = r[{}] - r[{}]\n", rn, rm);
    code.push_str("if _qsub_result > 0x7FFFFFFF:\n");
    code.push_str(&format!("    r[{}] = 0x7FFFFFFF\n", rd));
    code.push_str("elif _qsub_result < 0x80000000:\n");
    code.push_str(&format!("    r[{}] = 0x80000000\n", rd));
    code.push_str("else:\n");
    code.push_str(&format!("    r[{}] = _qsub_result\n", rd));
    code
}

pub fn generate_qdadd_instruction(ops: &[String]) -> String {
    // QDADD Rd, Rn, Rm (Saturating Double Add with Rn doubled)
    let rd = ops[0].clone();
    let rn = ops[1].clone();
    let rm = ops[2].clone();
    let mut code = format!("_qdadd_doubled = (r[{}] * 2) & 0xFFFFFFFF\n", rn);
    code.push_str("if _qdadd_doubled > 0x7FFFFFFF:\n");
    code.push_str("    _qdadd_doubled = 0x7FFFFFFF\n");
    code.push_str("elif _qdadd_doubled < 0x80000000:\n");
    code.push_str("    _qdadd_doubled = 0x80000000\n");
    code.push_str(&format!("_qdadd_result = _qdadd_doubled + r[{}]\n", rm));
    code.push_str("if _qdadd_result > 0x7FFFFFFF:\n");
    code.push_str(&format!("    r[{}] = 0x7FFFFFFF\n", rd));
    code.push_str("elif _qdadd_result < 0x80000000:\n");
    code.push_str(&format!("    r[{}] = 0x80000000\n", rd));
    code.push_str("else:\n");
    code.push_str(&format!("    r[{}] = _qdadd_result\n", rd));
    code
}

pub fn generate_qdsub_instruction(ops: &[String]) -> String {
    // QDSUB Rd, Rn, Rm (Saturating Double Subtract with Rn doubled)
    let rd = ops[0].clone();
    let rn = ops[1].clone();
    let rm = ops[2].clone();
    let mut code = format!("_qdsub_doubled = (r[{}] * 2) & 0xFFFFFFFF\n", rn);
    code.push_str("if _qdsub_doubled > 0x7FFFFFFF:\n");
    code.push_str("    _qdsub_doubled = 0x7FFFFFFF\n");
    code.push_str("elif _qdsub_doubled < 0x80000000:\n");
    code.push_str("    _qdsub_doubled = 0x80000000\n");
    code.push_str(&format!("_qdsub_result = _qdsub_doubled - r[{}]\n", rm));
    code.push_str("if _qdsub_result > 0x7FFFFFFF:\n");
    code.push_str(&format!("    r[{}] = 0x7FFFFFFF\n", rd));
    code.push_str("elif _qdsub_result < 0x80000000:\n");
    code.push_str(&format!("    r[{}] = 0x80000000\n", rd));
    code.push_str("else:\n");
    code.push_str(&format!("    r[{}] = _qdsub_result\n", rd));
    code
}
