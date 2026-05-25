pub fn gen_arith_32bit(rd: String, expr: String) -> String {
    format!("r[{}] = ({}) & 0xFFFFFFFF", rd, expr)
}

pub fn gen_mov(rd: String, rm: String) -> String {
    format!("r[{}] = {}", rd, rm)
}

pub fn gen_mov_imm(rd: String, imm: String) -> String {
    format!("r[{}] = {}", rd, imm)
}

pub fn gen_add_imm(rd: String, rn: String, imm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] + {}", rn, imm))
}

pub fn gen_add_reg(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] + r[{}]", rn, rm))
}

pub fn gen_sub_imm(rd: String, rn: String, imm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] - {}", rn, imm))
}

pub fn gen_sub_reg(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] - r[{}]", rn, rm))
}

pub fn gen_adc(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] + r[{}] + cpsr_c", rn, rm))
}

pub fn gen_sbc(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] - r[{}] + cpsr_c - 1", rn, rm))
}

pub fn gen_rsc(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] - r[{}] - cpsr_c + 1", rn, rm))
}

pub fn gen_rsb(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] - r[{}]", rm, rn))
}

pub fn gen_and(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] & r[{}]", rn, rm))
}

pub fn gen_eor(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] ^ r[{}]", rn, rm))
}

pub fn gen_orr(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] | r[{}]", rn, rm))
}

pub fn gen_bic(rd: String, rn: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] & ~r[{}]", rn, rm))
}

pub fn gen_mvn(rd: String, rm: String) -> String {
    gen_arith_32bit(rd, format!("~r[{}]", rm))
}

pub fn gen_mov_bitwise(rd: String, rn: String, op: &str, val: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] {} {}", rn, op, val))
}

pub fn gen_mul(rd: String, rm: String, rs: String, acc: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] * r[{}] + {}", rm, rs, acc))
}

pub fn gen_mla(rd: String, rm: String, rs: String, ra: String) -> String {
    gen_arith_32bit(rd, format!("r[{}] * r[{}] + r[{}]", rm, rs, ra))
}

pub fn gen_cmp_flags(rn: String, op2: String) -> String {
    let result = format!("r[{}] - {}", rn, op2);
    format!(
        "result = {}
cpsr_n = 1 if (result & 0x80000000) != 0 else 0
cpsr_z = 1 if result == 0 else 0
cpsr_c = 0
cpsr_v = 0",
        result
    )
}

pub fn gen_cmp_flags_imm(rn: String, imm: String) -> String {
    let result = format!("r[{}] - {}", rn, imm);
    format!(
        "result = {}
cpsr_n = 1 if (result & 0x80000000) != 0 else 0
cpsr_z = 1 if result == 0 else 0
cpsr_c = 0
cpsr_v = 0",
        result
    )
}

pub fn gen_branch(target: String, is_link: bool) -> String {
    let next_pc = if is_link { "r15 = pc + 4" } else { "" };
    format!("{}\nr15 = {}", next_pc, target)
}

pub fn gen_ldr_word(rd: String, rn: String, offset: String) -> String {
    gen_arith_32bit(
        rd,
        format!(
            "memory.read_32(r[{}]{})",
            rn,
            if offset.is_empty() {
                String::new()
            } else {
                format!(" + {}", offset)
            }
        ),
    )
}

pub fn gen_ldr_halfword(rd: String, rn: String, offset: String) -> String {
    format!(
        "r[{}] = memory.read_16(r[{}]{}) & 0xFFFF",
        rd,
        rn,
        if offset.is_empty() {
            String::new()
        } else {
            format!(" + {}", offset)
        }
    )
}

pub fn gen_ldr_byte(rd: String, rn: String, offset: String) -> String {
    format!(
        "r[{}] = memory.read_u8(r[{}]{}) & 0xFF",
        rd,
        rn,
        if offset.is_empty() {
            String::new()
        } else {
            format!(" + {}", offset)
        }
    )
}

pub fn gen_str_word(rn: String, rd: String, offset: String) -> String {
    format!(
        "memory.write_u32(r[{}]{}, r[{}])",
        rn,
        if offset.is_empty() {
            String::new()
        } else {
            format!(" + {}", offset)
        },
        rd
    )
}

pub fn gen_str_halfword(rn: String, rd: String, offset: String) -> String {
    format!(
        "memory.write_u16(r[{}]{}, r[{}] & 0xFFFF)",
        rn,
        if offset.is_empty() {
            String::new()
        } else {
            format!(" + {}", offset)
        },
        rd
    )
}

pub fn gen_swp(rd: String, rm: String, rn: String, is_halfword: bool) -> String {
    let byte = if is_halfword { "True" } else { "False" };
    format!(
        "temp = memory.read_u8(r[{}]) if {} else memory.read_u32(r[{}]); r[{}] = temp; memory.write_u8(r[{}], r[{}]) if {} else memory.write_u32(r[{}], r[{}])",
        rn, byte, rn, rd, rn, rm, byte, rn, rm
    )
}

pub fn gen_mrs(rd: String) -> String {
    format!("r[{}] = cpsr", rd)
}

pub fn gen_msr(operand: String) -> String {
    format!("cpsr = {}", operand)
}

pub fn gen_clz(rd: String, rm: String) -> String {
    format!(
        "r[{}] = (32 - ({}).bit_length()) if {} != 0 else 32",
        rd, rm, rm
    )
}

pub fn gen_shift_ror(reg: String, amount: String) -> String {
    format!(
        "(r[{}] >> {}) | (r[{}] << (32 - {})) & 0xFFFFFFFF",
        reg, amount, reg, amount
    )
}

pub fn gen_shift_lsl(reg: String, amt: String) -> String {
    format!("r[{}] << {}", reg, amt)
}

pub fn gen_shift_lsr(reg: String, amt: String) -> String {
    format!("r[{}] >> {}", reg, amt)
}

pub fn gen_bitfield(reg: String, shift: String, mask: String) -> String {
    format!("({} >> {}) & {}", reg, shift, mask)
}

pub fn gen_mem_addr(base: String, offset: Option<String>) -> String {
    match offset {
        Some(o) => format!("r[{}] + {}", base, o),
        None => base,
    }
}

pub fn gen_cond_branch(flag: &str, then_target: String, else_target: String) -> String {
    format!(
        "if cpsr_{} == 1: r15 = {}\nelse: r15 = {}",
        flag, then_target, else_target
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gen_add_imm() {
        let result = gen_add_imm("r0".to_string(), "r1".to_string(), "4".to_string());
        assert_eq!(result, "r0 = (r1 + 4) & 0xFFFFFFFF");
    }

    #[test]
    fn test_gen_adc() {
        let result = gen_adc("r0".to_string(), "r1".to_string(), "r2".to_string());
        assert_eq!(result, "r0 = (r1 + r2 + cpsr_c) & 0xFFFFFFFF");
    }

    #[test]
    fn test_gen_cmp_flags() {
        let result = gen_cmp_flags("r0".to_string(), "r1".to_string());
        assert!(result.contains("result = r0 - r1"));
        assert!(result.contains("cpsr_n"));
    }

    #[test]
    fn test_gen_ldr_word() {
        let result = gen_ldr_word("r0".to_string(), "r1".to_string(), "8".to_string());
        assert!(result.contains("memory.read_32(r1 + 8)"));
    }

    #[test]
    fn test_gen_mvn() {
        let result = gen_mvn("r0".to_string(), "r1".to_string());
        assert_eq!(result, "r0 = (~r1) & 0xFFFFFFFF");
    }
}
