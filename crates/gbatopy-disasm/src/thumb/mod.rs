pub struct ThumbDecoder;

impl ThumbDecoder {
    pub fn new() -> Self {
        Self
    }

    pub fn decode(&self, halfword: u16, address: u32) -> (String, Vec<crate::Operand>, bool) {
        // DEBUG: Log decoding at 0x0800010A
        if address == 0x0800010A {
            eprintln!("DISASM DEBUG: addr=0x{:08X} halfword=0x{:04X} high_byte=0x{:02X}", address, halfword, halfword >> 8);
        }
        match halfword >> 8 {
            0x00..=0x07 => self.format_1_shift(halfword),
            0x08..=0x0F => self.format_1_shift(halfword),
            0x10..=0x17 => self.format_1_shift(halfword),
            0x18..=0x1F => self.format_2_add_sub(halfword),
            0x20..=0x27 => self.format_3_mov(halfword),
            0x28..=0x2F => self.format_3_cmp(halfword),
            0x30..=0x37 => self.format_3_add(halfword),
            0x38..=0x3F => self.format_3_sub(halfword),
            0x40..=0x43 => self.format_4_alu(halfword),
            0x44..=0x47 => self.format_5_hi_reg(halfword),
            0x48..=0x4F => self.format_6_pc_rel_load(halfword, address),
            0x50..=0x57 => self.format_7_reg_offset(halfword),
            0x58..=0x5F => self.format_7_reg_offset(halfword),
            0x60..=0x67 => self.format_9_imm_offset_word(halfword),
            0x68..=0x6F => self.format_9_imm_offset_word(halfword),
            0x70..=0x77 => self.format_9_imm_offset_byte(halfword),
            0x78..=0x7F => self.format_9_imm_offset_byte(halfword),
            0x80..=0x87 => self.format_10_halfword(halfword),
            0x88..=0x8F => self.format_10_halfword(halfword),
            0x90..=0x97 => self.format_11_sp_rel(halfword),
            0x98..=0x9F => self.format_11_sp_rel(halfword),
            0xA0..=0xA7 => self.format_12_load_addr(halfword, address),
            0xA8..=0xAF => self.format_12_load_addr(halfword, address),
            0xB0 => self.format_13_add_offset_sp(halfword),
            0xB1 => self.format_misc_1b1(halfword),
            0xB2 => self.format_extend(halfword),
            0xB3 => self.format_misc_1b3(halfword),
            0xB4..=0xB5 => self.format_14_push_pop(halfword),
            0xB6 => self.format_misc_1b6(halfword),
            0xB7 => self.format_misc_1b7(halfword),
            0xB8 => self.format_misc_1b8(halfword),
            0xB9 => self.format_misc_1b9(halfword),
            0xBA => self.format_misc_1ba(halfword),
            0xBB => self.format_misc_1bb(halfword),
            0xBC..=0xBD => self.format_14_push_pop(halfword),
            0xBE => self.format_misc_1be(halfword),
            0xBF => self.format_misc_1bf(halfword),
            0xC0..=0xC7 => self.format_15_multiple(halfword),
            0xC8..=0xCF => self.format_15_multiple(halfword),
            0xD0..=0xD7 => self.format_16_cond_branch(halfword, address),
            0xD8..=0xDF => self.format_16_cond_branch(halfword, address),
            0xE0..=0xE7 => self.format_18_uncond_branch(halfword, address),
            0xE8..=0xEF => self.format_18_uncond_branch(halfword, address),
            0xF0..=0xF7 => self.format_19_long_branch(halfword, address),
            0xF8..=0xFF => self.format_19_long_branch(halfword, address),
            _ => ("UNKNOWN".to_string(), vec![], false),
        }
    }

    fn reg(&self, r: u8) -> crate::Operand {
        crate::Operand::Register(r)
    }

    fn imm(&self, v: u32) -> crate::Operand {
        crate::Operand::Immediate(v)
    }

    fn format_1_shift(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        // DEBUG: Log decoding at 0x0800010A
        let op = (hw >> 11) & 0x3;
        let offset5 = (hw >> 6) & 0x1F;
        let rs = (hw >> 3) & 0x7;
        let rd = hw & 0x7;
        let name = match op {
            0 => "LSL",
            1 => "LSR",
            2 => "ASR",
            _ => "UNKNOWN",
        };
        (
            name.to_string(),
            vec![
                self.reg(rd as u8),
                self.reg(rs as u8),
                self.imm(offset5 as u32),
            ],
            false,
        )
    }

    fn format_2_add_sub(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let i_bit = (hw >> 10) & 1;
        let op = (hw >> 9) & 1;
        let rn_offset3 = (hw >> 6) & 0x7;
        let rs = (hw >> 3) & 0x7;
        let rd = hw & 0x7;
        let name = if op == 0 { "ADD" } else { "SUB" };
        let src = if i_bit != 0 {
            self.imm(rn_offset3 as u32)
        } else {
            self.reg(rn_offset3 as u8)
        };
        (
            name.to_string(),
            vec![self.reg(rd as u8), self.reg(rs as u8), src],
            true,
        )
    }

    fn format_3_mov(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let rd = (hw >> 8) & 0x7;
        let imm8 = hw & 0xFF;
        (
            "MOV".to_string(),
            vec![self.reg(rd as u8), self.imm(imm8 as u32)],
            true,
        )
    }

    fn format_3_cmp(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let rd = (hw >> 8) & 0x7;
        let imm8 = hw & 0xFF;
        (
            "CMP".to_string(),
            vec![self.reg(rd as u8), self.imm(imm8 as u32)],
            true,
        )
    }

    fn format_3_add(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let rd = (hw >> 8) & 0x7;
        let imm8 = hw & 0xFF;
        (
            "ADD".to_string(),
            vec![
                self.reg(rd as u8),
                self.reg(rd as u8),
                self.imm(imm8 as u32),
            ],
            true,
        )
    }

    fn format_3_sub(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let rd = (hw >> 8) & 0x7;
        let imm8 = hw & 0xFF;
        (
            "SUB".to_string(),
            vec![
                self.reg(rd as u8),
                self.reg(rd as u8),
                self.imm(imm8 as u32),
            ],
            true,
        )
    }

    fn format_4_alu(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let op = (hw >> 6) & 0xF;
        let rs = (hw >> 3) & 0x7;
        let rd = hw & 0x7;
        let (name, sets_flags) = match op {
            0x0 => ("AND", false),
            0x1 => ("EOR", false),
            0x2 => ("LSL", true),
            0x3 => ("LSR", true),
            0x4 => ("ASR", true),
            0x5 => ("ADC", true),
            0x6 => ("SBC", true),
            0x7 => ("ROR", true),
            0x8 => ("TST", true),
            0x9 => ("NEG", true),
            0xA => ("CMP", true),
            0xB => ("CMN", true),
            0xC => ("ORR", false),
            0xD => ("MUL", false),
            0xE => ("BIC", false),
            0xF => ("MVN", false),
            _ => ("UNKNOWN", false),
        };
        (
            name.to_string(),
            vec![self.reg(rd as u8), self.reg(rs as u8)],
            sets_flags,
        )
    }

    fn format_5_hi_reg(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let op = (hw >> 8) & 0x3;
        let h1 = (hw >> 7) & 1;
        let h2 = (hw >> 6) & 1;
        let rs = ((h2 << 3) | (hw >> 3) & 0x7) as u8;
        let rd = ((h1 << 3) | (hw & 0x7)) as u8;
        match op {
            0 => (
                "ADD".to_string(),
                vec![self.reg(rd), self.reg(rd), self.reg(rs)],
                false,
            ),
            1 => ("CMP".to_string(), vec![self.reg(rd), self.reg(rs)], true),
            2 => ("MOV".to_string(), vec![self.reg(rd), self.reg(rs)], false),
            3 => ("BX".to_string(), vec![self.reg(rs)], false),
            _ => ("UNKNOWN".to_string(), vec![], false),
        }
    }

    fn format_6_pc_rel_load(&self, hw: u16, address: u32) -> (String, Vec<crate::Operand>, bool) {
        let rd = ((hw >> 8) & 0x7) as u8;
        let imm8 = (hw & 0xFF) as u32;
        let pc_aligned = (address + 4) & !3;
        let target = pc_aligned + (imm8 << 2);
        (
            "LDR".to_string(),
            vec![self.reg(rd), self.imm(target)],
            false,
        )
    }

    fn format_7_reg_offset(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let op = (hw >> 9) & 0x7;
        let ro = ((hw >> 6) & 0x7) as u8;
        let rb = ((hw >> 3) & 0x7) as u8;
        let rd = (hw & 0x7) as u8;
        let name = match op {
            0b000 => "STR",
            0b001 => "STRH",
            0b010 => "STRB",
            0b011 => "LDRSB",
            0b100 => "LDR",
            0b101 => "LDRH",
            0b110 => "LDRB",
            0b111 => "LDRSH",
            _ => "UNKNOWN",
        };
        (
            name.to_string(),
            vec![self.reg(rd), self.reg(rb), self.reg(ro)],
            false,
        )
    }

    fn format_9_imm_offset_word(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let l_bit = (hw >> 11) & 1;
        let imm5 = ((hw >> 6) & 0x1F) as u32;
        let rb = ((hw >> 3) & 0x7) as u8;
        let rd = (hw & 0x7) as u8;
        let offset = imm5 << 2;
        let name = if l_bit != 0 { "LDR" } else { "STR" };
        (
            name.to_string(),
            vec![self.reg(rd), self.reg(rb), self.imm(offset)],
            false,
        )
    }

    fn format_9_imm_offset_byte(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let l_bit = (hw >> 11) & 1;
        let imm5 = ((hw >> 6) & 0x1F) as u32;
        let rb = ((hw >> 3) & 0x7) as u8;
        let rd = (hw & 0x7) as u8;
        let name = if l_bit != 0 { "LDRB" } else { "STRB" };
        (
            name.to_string(),
            vec![self.reg(rd), self.reg(rb), self.imm(imm5)],
            false,
        )
    }

    fn format_10_halfword(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let l_bit = (hw >> 11) & 1;
        let imm5 = ((hw >> 6) & 0x1F) as u32;
        let rb = ((hw >> 3) & 0x7) as u8;
        let rd = (hw & 0x7) as u8;
        let offset = imm5 << 1;
        let name = if l_bit != 0 { "LDRH" } else { "STRH" };
        (
            name.to_string(),
            vec![self.reg(rd), self.reg(rb), self.imm(offset)],
            false,
        )
    }

    fn format_11_sp_rel(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let l_bit = (hw >> 11) & 1;
        let rd = ((hw >> 8) & 0x7) as u8;
        let imm8 = ((hw & 0xFF) as u32) << 2;
        let name = if l_bit != 0 { "LDR" } else { "STR" };
        (
            name.to_string(),
            vec![self.reg(rd), self.reg(13), self.imm(imm8)],
            false,
        )
    }

    fn format_12_load_addr(&self, hw: u16, _address: u32) -> (String, Vec<crate::Operand>, bool) {
        let sp_flag = (hw >> 11) & 1;
        let rd = ((hw >> 8) & 0x7) as u8;
        let imm8 = ((hw & 0xFF) as u32) << 2;
        let base = if sp_flag != 0 { 13u8 } else { 15u8 };
        (
            "ADD".to_string(),
            vec![self.reg(rd), self.reg(base), self.imm(imm8)],
            false,
        )
    }

    fn format_13_add_offset_sp(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let s_bit = (hw >> 7) & 1;
        let imm7 = ((hw & 0x7F) as u32) << 2;
        let name = if s_bit != 0 { "SUB" } else { "ADD" };
        (
            name.to_string(),
            vec![self.reg(13), self.reg(13), self.imm(imm7)],
            false,
        )
    }

    fn format_extend(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let op = (hw >> 6) & 0x3;
        let rm = ((hw >> 3) & 0x7) as u8;
        let rd = (hw & 0x7) as u8;
        let name = match op {
            0 => "SXTH",
            1 => "SXTB",
            2 => "UXTH",
            _ => "UXTB",
        };
        (
            name.to_string(),
            vec![self.reg(rd), self.reg(rm)],
            false,
        )
    }

    fn format_14_push_pop(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let l_bit = (hw >> 11) & 1;
        let r_flag = (hw >> 8) & 1;
        let rlist = hw & 0xFF;
        let name = if l_bit != 0 { "POP" } else { "PUSH" };
        let mut operands: Vec<crate::Operand> = Vec::new();
        for i in 0..8 {
            if rlist & (1 << i) != 0 {
                operands.push(self.reg(i));
            }
        }
        if r_flag != 0 {
            operands.push(self.reg(if l_bit != 0 { 15 } else { 14 }));
        }
        (name.to_string(), operands, false)
    }

    fn format_15_multiple(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let l_bit = (hw >> 11) & 1;
        let rb = ((hw >> 8) & 0x7) as u8;
        let rlist = hw & 0xFF;
        let name = if l_bit != 0 { "LDMIA" } else { "STMIA" };
        let mut operands: Vec<crate::Operand> = vec![self.reg(rb)];
        for i in 0..8 {
            if rlist & (1 << i) != 0 {
                operands.push(self.reg(i));
            }
        }
        (name.to_string(), operands, false)
    }

    fn format_16_cond_branch(&self, hw: u16, address: u32) -> (String, Vec<crate::Operand>, bool) {
        let cond = (hw >> 8) & 0xF;
        let offset = (hw & 0xFF) as i32;
        let signed_offset = (offset << 24) >> 24;
        let target = address
            .wrapping_add(4)
            .wrapping_add((signed_offset as u32).wrapping_mul(2));
        let cond_name = match cond {
            0 => "BEQ",
            1 => "BNE",
            2 => "BCS",
            3 => "BCC",
            4 => "BMI",
            5 => "BPL",
            6 => "BVS",
            7 => "BVC",
            8 => "BHI",
            9 => "BLS",
            10 => "BGE",
            11 => "BLT",
            12 => "BGT",
            13 => "BLE",
            14 => "B",
            15 => "SWI",
            _ => "B??",
        };
        if cond == 15 {
            let swi_num = hw & 0xFF;
            ("SWI".to_string(), vec![self.imm(swi_num as u32)], false)
        } else {
            (cond_name.to_string(), vec![self.imm(target)], false)
        }
    }

    fn format_18_uncond_branch(
        &self,
        hw: u16,
        address: u32,
    ) -> (String, Vec<crate::Operand>, bool) {
        // Check for BLX (register) encoding: 0xE3F0-0xE3FF
        // Pattern: 1110 0011 1111 0000 Rm[3:0]
        // High byte 0xE3 with low byte 0xF0-0xFF indicates BLX
        if (hw & 0xFFF0) == 0xE3F0 {
            let rm = (hw & 0xF) as u8;
            return ("BLX".to_string(), vec![self.reg(rm)], false);
        }
        
        let offset = (hw & 0x7FF) as i32;
        let signed_offset = (offset << 21) >> 21;
        let target = address
            .wrapping_add(4)
            .wrapping_add((signed_offset as u32).wrapping_mul(2));
        ("B".to_string(), vec![self.imm(target)], false)
    }

    fn format_19_long_branch(&self, hw: u16, address: u32) -> (String, Vec<crate::Operand>, bool) {
        let h_flag = (hw >> 11) & 1;
        let offset = (hw & 0x7FF) as u32;
        if h_flag == 0 {
            let off = ((offset << 21) as i32) >> 21;
            let target = (address as i32 + 4 + (off << 12)) as u32;
            ("BL_PREFIX".to_string(), vec![self.imm(target)], false)
        } else {
            // BL suffix offset is unsigned. The combined BL offset is 22-bit
            // (offset_high << 11 | offset_low), sign-extended from bit 21.
            // The prefix already handles sign extension via offset_high.
            ("BL_SUFFIX".to_string(), vec![self.imm((offset << 1) as u32)], false)
        }
    }

    /// Decode a 32-bit BL/BLX instruction from its two halfwords.
    /// Returns Some(("BL", [target], false, 4)) or Some(("BLX", [target], false, 4)) if hw1 and hw2 form a valid pair.
    /// Returns None if hw2 is not a valid BL_SUFFIX (caller should fall back to BL_PREFIX).
    pub fn decode_bl_pair(&self, hw1: u16, hw2: u16, address: u32) -> Option<(String, Vec<crate::Operand>, bool, u8)> {
        // hw1 must be BL_PREFIX (bit 11 = 0, opcode range 0xF000-0xF3FF or 0xF400-0xF7FF with S=0)
        let h_flag1 = (hw1 >> 11) & 1;
        if h_flag1 != 0 {
            return None; // hw1 is not a BL_PREFIX
        }
        
        // hw2 must be BL_SUFFIX or BLX_SUFFIX (bit 11 = 1, opcode range 0xF800-0xFBFF or 0xFC00-0xFFFF)
        let h_flag2 = (hw2 >> 11) & 1;
        if h_flag2 != 1 {
            return None; // hw2 is not a BL_SUFFIX
        }
        
        // Check if this is BLX (immediate): bit 10 of hw2 = 1 (BL has 0)
        // BL_SUFFIX:  1111 10xx xxxxx... (bits 11-9 = 100 or 101)
        // BLX_SUFFIX: 1111 11xx xxxxx... (bits 11-9 = 110 or 111)
        let j1_bit = (hw2 >> 10) & 1;  // bit 10 distinguishes BL (0) from BLX (1)
        let is_blx = j1_bit == 1;
        
        // Extract the 23-bit offset (22 bits for BL/BLX, bit 22 is sign bit)
        let offset_high = hw1 & 0x7FF;
        let offset_low = hw2 & 0x7FF;
        
        // Combine: offset = (offset_high << 12) | (offset_low << 1)
        let offset = ((offset_high as u32) << 12) | ((offset_low as u32) << 1);
        
        // Sign-extend from bit 22 (the S bit of the combined 23-bit value)
        let signed_offset = if (offset & (1 << 22)) != 0 {
            // Negative: sign-extend
            (offset | (!0u32 << 23)) as i32
        } else {
            offset as i32
        };
        
        // Target = address + 4 + (sign-extended offset)
        // PC-relative: PC = address + 4 (pipeline)
        let target = (address as i32 + 4 + signed_offset) as u32;
        
        // Return address = address + 4 (next instruction after the 4-byte BL/BLX)
        let opcode = if is_blx { "BLX" } else { "BL" };
        Some((opcode.to_string(), vec![self.imm(target)], false, 4))
    }

    // Format 1b1: 0xB1xx - Reserved / undefined (treat as NOP)
    fn format_misc_1b1(&self, _hw: u16) -> (String, Vec<crate::Operand>, bool) {
        ("NOP".to_string(), vec![], false)
    }

    // Format 1b3: 0xB3xx - Reserved / undefined (treat as NOP)
    fn format_misc_1b3(&self, _hw: u16) -> (String, Vec<crate::Operand>, bool) {
        ("NOP".to_string(), vec![], false)
    }

    // Format 1b6: 0xB6xx - CPS instruction
    fn format_misc_1b6(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let m_bit = (hw >> 7) & 1;
        let a_bit = (hw >> 5) & 1;
        let s_bit = (hw >> 4) & 1;
        let d_bit = (hw >> 3) & 1;
        let immed4 = hw & 0xF;
        
        let opcode = if m_bit != 0 { "CPS" } else { "UNKNOWN" };
        let operands = if m_bit != 0 {
            let mut ops = Vec::new();
            if a_bit != 0 { ops.push(crate::Operand::Immediate(1)); }
            if s_bit != 0 { ops.push(crate::Operand::Immediate(2)); }
            if d_bit != 0 { ops.push(crate::Operand::Immediate(4)); }
            if immed4 != 0 { ops.push(crate::Operand::Immediate(immed4 as u32)); }
            ops
        } else {
            vec![]
        };
        (opcode.to_string(), operands, false)
    }

    // Format 1b7: 0xB7xx - Reserved / undefined (treat as NOP)
    fn format_misc_1b7(&self, _hw: u16) -> (String, Vec<crate::Operand>, bool) {
        ("NOP".to_string(), vec![], false)
    }

    // Format 1b8: 0xB8xx - Reserved / undefined (treat as NOP)
    fn format_misc_1b8(&self, _hw: u16) -> (String, Vec<crate::Operand>, bool) {
        ("NOP".to_string(), vec![], false)
    }

    // Format 1b9: 0xB9xx - Reserved / undefined (treat as NOP)
    fn format_misc_1b9(&self, _hw: u16) -> (String, Vec<crate::Operand>, bool) {
        ("NOP".to_string(), vec![], false)
    }

    // Format 1ba: 0xBAxx - Reserved / undefined (treat as NOP)
    fn format_misc_1ba(&self, _hw: u16) -> (String, Vec<crate::Operand>, bool) {
        ("NOP".to_string(), vec![], false)
    }

    // Format 1bb: 0xBBxx - Reserved / undefined (treat as NOP)
    fn format_misc_1bb(&self, _hw: u16) -> (String, Vec<crate::Operand>, bool) {
        ("NOP".to_string(), vec![], false)
    }

    // Format 1be: 0xBExx - BKPT instruction
    fn format_misc_1be(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let imm8 = hw & 0xFF;
        ("BKPT".to_string(), vec![self.imm(imm8 as u32)], false)
    }

    // Format 1bf: 0xBFxx - NOP / Yield / Sev / Wfe / Wfi / Dsb / Dmb / Isb
    fn format_misc_1bf(&self, hw: u16) -> (String, Vec<crate::Operand>, bool) {
        let lower = hw & 0xFF;
        let opcode = match lower {
            0x00 => "NOP",
            0x10 => "YIELD",
            0x30 => "SEV",
            0x40 => "WFE",
            0x50 => "WFI",
            0x70 => "DSB",
            0x80 => "DMB",
            0x90 => "ISB",
            _ => "NOP", // Default to NOP for undefined encodings
        };
        (opcode.to_string(), vec![], false)
    }
}

impl Default for ThumbDecoder {
    fn default() -> Self {
        Self::new()
    }
}
