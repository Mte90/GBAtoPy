use crate::{decode_condition, AddressingMode, Condition, Operand};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DataOp {
    And,
    Eor,
    Sub,
    Rsb,
    Add,
    Adc,
    Sbc,
    Rsc,
    Tst,
    Teq,
    Cmp,
    Cmn,
    Orr,
    Mov,
    Bic,
    Mvn,
}

impl DataOp {
    pub fn from_bits(bits: u8) -> Option<DataOp> {
        match bits & 0xF {
            0x0 => Some(DataOp::And),
            0x1 => Some(DataOp::Eor),
            0x2 => Some(DataOp::Sub),
            0x3 => Some(DataOp::Rsb),
            0x4 => Some(DataOp::Add),
            0x5 => Some(DataOp::Adc),
            0x6 => Some(DataOp::Sbc),
            0x7 => Some(DataOp::Rsc),
            0x8 => Some(DataOp::Tst),
            0x9 => Some(DataOp::Teq),
            0xA => Some(DataOp::Cmp),
            0xB => Some(DataOp::Cmn),
            0xC => Some(DataOp::Orr),
            0xD => Some(DataOp::Mov),
            0xE => Some(DataOp::Bic),
            0xF => Some(DataOp::Mvn),
            _ => None,
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            DataOp::And => "AND",
            DataOp::Eor => "EOR",
            DataOp::Sub => "SUB",
            DataOp::Rsb => "RSB",
            DataOp::Add => "ADD",
            DataOp::Adc => "ADC",
            DataOp::Sbc => "SBC",
            DataOp::Rsc => "RSC",
            DataOp::Tst => "TST",
            DataOp::Teq => "TEQ",
            DataOp::Cmp => "CMP",
            DataOp::Cmn => "CMN",
            DataOp::Orr => "ORR",
            DataOp::Mov => "MOV",
            DataOp::Bic => "BIC",
            DataOp::Mvn => "MVN",
        }
    }
}

pub struct ArmDecoder;

impl ArmDecoder {
    pub fn new() -> Self {
        Self
    }

    pub fn decode(&self, word: u32, address: u32) -> (String, Vec<Operand>, bool) {
        let bx_upper = ((word >> 24) & 0xF) == 6 || ((word >> 24) & 0xF) == 7;
        let bx_lower = (word & 0xFF) == 0x08;
        if bx_upper && bx_lower {
            let rm = (word >> 16) & 0xF;
            let is_blx = ((word >> 24) & 0x1) != 0; // bit 25 within the 0x6/0x7 nibble
            let op = if is_blx { "BLX" } else { "BX" };
            return (op.to_string(), vec![Operand::Register(rm as u8)], false);
        }

        let cond_bits = ((word >> 28) & 0xF) as u8;
        let cond = decode_condition(cond_bits);

        // Get instruction type from bits 27-26 and bit 25
        // ARM encoding:
        //   Bits 27-26 = 00, Bit 25 = 0 → Data Processing (register)
        //   Bits 27-26 = 00, Bit 25 = 1 → Data Processing (immediate)
        //   Bits 27-26 = 01 → Load/Store
        let bits_27_26 = (word >> 26) & 0x3;
        let bit_25 = (word >> 25) & 0x1;

        // Check bits 27-25 FIRST for instructions that span multiple (bits_27_26, bit_25) combinations
        let bits_27_25 = (word >> 25) & 0x7;
        
        // LDM/STM: bits 27-25 = 100 (can have bits_27_26 = 10 or 11 depending on encoding)
        if bits_27_25 == 0b100 {
            return self.decode_block_transfer(word, address);
        }
        
        // B/BL: bits 27-25 = 101
        if bits_27_25 == 0b101 {
            return self.decode_branch(word, address);
        }
        
        // CRITICAL FIX: Load/Store with register offset can have bits 27-26 = 00
        // Pattern: bits 27-26 = 00, bit 25 = 0, bit 21 = 0 (W=0), bit 20 = 1 (L=1) or 0 (L=0)
        // This is actually a load/store instruction, NOT data processing!
        if bits_27_26 == 0b00 && bit_25 == 0 {
            let w_bit = (word >> 21) & 0x1;
            let _l_bit = (word >> 20) & 0x1;
            // Check if this looks like load/store register offset
            // bits 7-5 = shift type, bit 4 = type bit (0 for register offset)
            let type_bit = (word >> 4) & 0x1;
            if type_bit == 0 && w_bit == 0 {
                // This is load/store with register offset!
                return self.decode_load_store(word, address);
            }
        }

        let (base_name, operands, is_thumb) = match (bits_27_26, bit_25) {
            (0b00, _) => self.decode_data_processing(word, address), // Bits 27-26 = 00
            (0b01, _) => self.decode_load_store(word, address),      // Bits 27-26 = 01
            (0b10, _) => self.decode_load_store_imm(word, address),  // Bits 27-26 = 10
            (0b11, _) => {
                // Check bit 25 for more specific classification
                match bits_27_25 {
                    0b110 => (format!("COPROCESSOR"), vec![], false),
                    0b111 => {
                        let swi_num = (word & 0xFFFFFF) as u32;
                        (format!("SWI"), vec![Operand::Immediate(swi_num)], false)
                    }
                    _ => (format!("UNKNOWN"), vec![], false),
                }
            }
            _ => (
                format!("UNKNOWN_0b{:02b}_{}", bits_27_26, bit_25),
                vec![],
                false,
            ),
        };

        let full_name = match cond {
            Some(Condition::Al) | Some(Condition::Nv) => base_name,
            _ => {
                let suffix = cond.map(|c| c.name()).unwrap_or("??");
                format!("{}{}", base_name, suffix)
            }
        };

        (full_name, operands, is_thumb)
    }

    fn decode_data_processing(&self, word: u32, address: u32) -> (String, Vec<Operand>, bool) {
        // BX/BLX: bits[27:24]=0x1, bits[23:20]=0x2, bits[19:16]=0xF, bits[7:4]=0x1
        let bits_27_24 = (word >> 24) & 0xF;
        let bits_23_20 = (word >> 20) & 0xF;
        let bits_19_16 = (word >> 16) & 0xF;
        let bits_7_4 = (word >> 4) & 0xF;

        let is_bx_blx =
            bits_27_24 == 0x1 && bits_23_20 == 0x2 && bits_19_16 == 0xF && bits_7_4 == 0x1;

        if is_bx_blx {
            let h_bit = (word >> 21) & 1;
            let rm = (word & 0xF) as u8;
            let op = if h_bit != 0 { "BLX" } else { "BX" };
            return (op.to_string(), vec![Operand::Register(rm)], false);
        }

        let bits_23_21 = (word >> 21) & 0x7;
        let bits_7_4 = (word >> 4) & 0xF;

        // Halfword/signed byte load/store: bits[27:25]=000, bit[7]=1, bit[4]=1
        // ARM encoding: bits[7:4] = 1 H 1 S (H=0 halfword, H=1 signed; S=0 byte, S=1 word)
        let bit_7_4 = (word >> 4) & 0xF;
        let bit_7 = (word >> 7) & 1;
        let bit_4 = (word >> 4) & 1;
        if bits_27_24 == 0x1 && bit_7 == 1 && bit_4 == 1 {
            let l_bit = (word >> 20) & 1 != 0;
            let rn = ((word >> 16) & 0xF) as u8;
            let rd = ((word >> 12) & 0xF) as u8;
            let rm = (word & 0xF) as u8;

            // Determine opcode from bits[7:4] pattern
            let op_name = match bit_7_4 {
                0xB => if l_bit { "LDRH" } else { "STRH" },    // halfword
                0xD => if l_bit { "LDRSB" } else { "UNDEFINED" }, // signed byte
                0xF => if l_bit { "LDRSH" } else { "UNDEFINED" }, // signed halfword
                _ => "UNDEFINED",
            };

            // bit 22 = I: 0 = register offset (Rm), 1 = immediate offset (imm4H:imm4L)
            let imm_offset = (word >> 22) & 1 != 0;
            let offset = if imm_offset {
                let imm = (((word >> 8) & 0xF) << 4) | (word & 0xF);
                Operand::Immediate(imm as u32)
            } else {
                Operand::Register(rm)
            };

            let mem_op = Operand::MemoryAddress {
                base: rn,
                offset: crate::operand::AddressingMode::ImmediateOffset(
                    if (word & (1 << 23)) != 0 {
                        offset.immediate_value()
                    } else {
                        -offset.immediate_value()
                    },
                ),
                writeback: false,
            };

            (
                op_name.to_string(),
                vec![Operand::Register(rd), mem_op],
                false,
            )
        } else if bits_27_24 == 0x0 && bits_23_21 == 0x1 && bits_7_4 == 0x9 {
            let is_mla = (word >> 20) & 1 != 0;
            let rd = ((word >> 16) & 0xF) as u8;
            let rs = ((word >> 8) & 0xF) as u8;
            let rm = (word & 0xF) as u8;

            if is_mla {
                let ra = ((word >> 12) & 0xF) as u8;
                (
                    "MLA".to_string(),
                    vec![
                        Operand::Register(rd),
                        Operand::Register(rm),
                        Operand::Register(rs),
                        Operand::Register(ra),
                    ],
                    false,
                )
            } else {
                (
                    "MUL".to_string(),
                    vec![
                        Operand::Register(rd),
                        Operand::Register(rm),
                        Operand::Register(rs),
                    ],
                    false,
                )
            }
        } else if bits_27_24 == 0x0 && bits_7_4 == 0x9 && bits_23_21 != 0x1 {
            let a_bit = (word >> 21) & 1 != 0;
            let s_bit = (word >> 20) & 1 != 0;
            let rd_lo = ((word >> 16) & 0xF) as u8;
            let rd_hi = ((word >> 12) & 0xF) as u8;
            let rm = (word & 0xF) as u8;
            let rs = ((word >> 8) & 0xF) as u8;

            let is_signed = (word >> 22) & 1 == 0;
            let base_op = if is_signed { "SMULL" } else { "UMULL" };
            let op_name = if a_bit {
                if is_signed {
                    "SMLAL"
                } else {
                    "UMLAL"
                }
            } else {
                base_op
            };

            let operands = vec![
                Operand::Register(rd_lo),
                Operand::Register(rd_hi),
                Operand::Register(rm),
                Operand::Register(rs),
            ];

            (op_name.to_string(), operands, s_bit)
        } else if bits_27_24 == 0x1 && bits_23_21 == 0x1 && bits_7_4 == 0x0 {
            let b_bit = (word >> 22) & 1 != 0;
            let rd = ((word >> 12) & 0xF) as u8;
            let rm = (word & 0xF) as u8;
            let rn = ((word >> 16) & 0xF) as u8;

            let op_name = if b_bit { "SWPB" } else { "SWP" };
            (
                op_name.to_string(),
                vec![
                    Operand::Register(rd),
                    Operand::Register(rm),
                    Operand::Register(rn),
                ],
                false,
            )
        } else if ((word >> 28) & 0xF) == 0xE && ((word >> 27) & 1) == 1 {
            let rd = ((word >> 12) & 0xF) as u8;
            let sr = ((word >> 8) & 0xF) as u8;
            (
                "MRS".to_string(),
                vec![Operand::Register(rd), Operand::Immediate(sr as u32)],
                false,
            )
        } else if (word >> 23) & 0x1F == 0x00011 {
            let s_bit = (word >> 20) & 1 != 0;
            let flags = (word >> 16) & 0xF;
            let rd = ((word >> 12) & 0xF) as u8;

            let _flags_str = match flags {
                0x1 => "C",
                0x2 => "X",
                0x4 => "S",
                0x8 => "F",
                0xF => "CPSR",
                _ => "CPSR",
            };

            let operand = if (word & (1 << 25)) != 0 {
                Operand::Immediate(word & 0xFF)
            } else {
                Operand::Register(rd)
            };

            (
                "MSR".to_string(),
                vec![Operand::Immediate(flags), operand],
                s_bit,
            )
        } else if bits_27_24 == 0xF {
            // SWI: bits[27:24]=1111
            let swi_num = word & 0xFFFFFF;
            ("SWI".to_string(), vec![Operand::Immediate(swi_num)], false)
        } else if ((word >> 26) & 0x3) == 0b01 && (word & (1 << 25)) == 0 {
            // Load/Store with register offset: bits[27-26]=01, I-bit=0
            let _p_bit = (word >> 24) & 1 != 0;
            let _u_bit = (word >> 23) & 1 != 0;
            let b_bit = (word >> 22) & 1 != 0;
            let w_bit = (word >> 21) & 1 != 0;
            let l_bit = (word >> 20) & 1 != 0;
            let rn = ((word >> 16) & 0xF) as u8;
            let rd = ((word >> 12) & 0xF) as u8;
            let rm = (word & 0xF) as u8;
            
            let op_name = if l_bit {
                if b_bit { "LDRB" }
                else { "LDR" }
            } else {
                if b_bit { "STRB" }
                else { "STR" }
            };
            
            // Register offset addressing mode
            let addressing_mode = AddressingMode::RegisterOffset(rm);
            
            (
                op_name.to_string(),
                vec![
                    Operand::Register(rd),
                    Operand::MemoryAddress {
                        base: rn,
                        offset: addressing_mode,
                        writeback: w_bit,
                    },
                ],
                false,
            )
        } else {
            let opcode_bits = ((word >> 21) & 0xF) as u8;
            let s_bit = (word >> 20) & 1 != 0;
            let rn = ((word >> 16) & 0xF) as u8;
            let rd = ((word >> 12) & 0xF) as u8;
            let i_bit = (word >> 25) & 1 != 0; // I flag: 1=immediate, 0=register
            let operand2_bits = word & 0xFFF;

            // DEBUG: Log ORR instructions
            if opcode_bits == 0xC {
                eprintln!("DEBUG ORR at 0x{:08X}: word=0x{:08X}, rd=R{}, rn=R{}, i_bit={}, operand2=0x{:03X}", 
                         address, word, rd, rn, i_bit, operand2_bits);
            }

            if let Some(op) = DataOp::from_bits(opcode_bits) {
                let mut operands = vec![Operand::Register(rd)];

                if i_bit {
                    // Immediate operand: calculate rotated immediate value
                    let imm8 = operand2_bits & 0xFF;
                    let rot = (operand2_bits >> 8) & 0xF;
                    // Rotate right by 2*rot bits
                    let imm_val = if rot == 0 {
                        imm8 as u32
                    } else {
                        let shift = (2 * rot) as u32;
                        ((imm8 >> shift) | (imm8 << (32 - shift))) & 0xFFFFFFFF
                    };
                    operands.push(Operand::Immediate(imm_val));
                } else {
                    // Register operand with optional shift
                    operands.push(Operand::Register(rn));

                    let rm = (operand2_bits & 0xF) as u8;
                    if (operand2_bits & 0x10) != 0 {
                        let shift_imm = ((operand2_bits >> 7) & 0x1F) as u8;
                        let shift_type_bits = ((operand2_bits >> 5) & 0x3) as u8;
                        if let Some(shift) = crate::operand::ShiftType::from_bits(shift_type_bits) {
                            operands.push(Operand::ShiftedRegister {
                                reg: rm,
                                shift,
                                amount: crate::operand::ShiftAmount::Immediate(shift_imm),
                            });
                        } else {
                            operands.push(Operand::Register(rm));
                        }
                    } else {
                        operands.push(Operand::Register(rm));
                    }
                }

                (op.name().to_string(), operands, s_bit)
            } else {
                ("UNDEFINED".to_string(), vec![], false)
            }
        }
    }

    fn decode_load_store(&self, word: u32, _address: u32) -> (String, Vec<Operand>, bool) {
        let i_bit = (word >> 25) & 1 != 0;
        let p_bit = (word >> 24) & 1 != 0;
        let u_bit = (word >> 23) & 1 != 0;
        let b_bit = (word >> 22) & 1 != 0;
        let w_bit = (word >> 21) & 1 != 0;
        let l_bit = (word >> 20) & 1 != 0;
        let rn = ((word >> 16) & 0xF) as u8;
        let rd = ((word >> 12) & 0xF) as u8;
        
        // Check for halfword instructions (STRH/LDRH) - bits 5-4 = 0b01
        let h_bit = (word >> 4) & 1 != 0;
        let s_bit = (word >> 5) & 1 != 0;
        let is_halfword = s_bit && h_bit;
        
        // Determine instruction name
        let op_name = if is_halfword {
            if l_bit { "LDRH" } else { "STRH" }
        } else if b_bit {
            if l_bit { "LDRB" } else { "STRB" }
        } else {
            if l_bit { "LDR" } else { "STR" }
        };

        if rn == 15 {
            let imm = word & 0xFFF;
            let offset = if u_bit { imm as i32 } else { -(imm as i32) };

            let mem_op = Operand::MemoryAddress {
                base: rn,
                offset: crate::operand::AddressingMode::ImmediateOffset(offset),
                writeback: false,
            };

            return (
                op_name.to_string(),
                vec![Operand::Register(rd), mem_op],
                false,
            );
        }
        // For halfword instructions, offset extraction is different
        let offset = if is_halfword {
            // Halfword instructions use bits 11-8 and 3-0 for immediate offset
            let h2 = (word >> 8) & 0xF;
            let h0 = word & 0xF;
            let imm = (h2 << 4) | h0;
            if u_bit {
                Operand::Immediate(imm)
            } else {
                Operand::Immediate((-(imm as i32)) as u32)
            }
        } else if i_bit {
            let rm = (word & 0xF) as u8;
            // Check if this is a register offset (no shift) or shifted register
            let shift_bits = (word >> 5) & 0x3;
            let shift_imm = (word >> 7) & 0x1F;
            if shift_bits == 0 && shift_imm == 0 {
                // Register offset without shift: STR R0, [R1, R2]
                Operand::Register(rm)
            } else {
                // Shifted register: STR R0, [R1, R2, LSL #imm]
                Operand::ShiftedRegister {
                    reg: rm,
                    shift: crate::operand::ShiftType::Lsl,
                    amount: crate::operand::ShiftAmount::Immediate(shift_imm as u8),
                }
            }
        } else {
            let imm = word & 0xFFF;
            if u_bit {
                Operand::Immediate(imm)
            } else {
                Operand::Immediate((-(imm as i32)) as u32)
            }
        };

        let writeback = w_bit && !p_bit;

        // Convert offset Operand to AddressingMode
        let addressing_mode = match offset {
            Operand::Immediate(imm) => {
                crate::operand::AddressingMode::ImmediateOffset(imm as i32)
            }
            Operand::Register(reg) => {
                crate::operand::AddressingMode::RegisterOffset(reg)
            }
            Operand::ShiftedRegister { reg, shift, amount } => {
                // Extract immediate value from ShiftAmount::Immediate
                let imm = match amount {
                    crate::operand::ShiftAmount::Immediate(v) => v as i32,
                    _ => 0,
                };
                crate::operand::AddressingMode::ScaledRegisterOffset {
                    reg,
                    shift,
                    amount: imm as u8,
                }
            }
            _ => crate::operand::AddressingMode::ImmediateOffset(0),
        };

        let mem_op = Operand::MemoryAddress {
            base: rn,
            offset: addressing_mode,
            writeback,
        };

        (
            op_name.to_string(),
            vec![Operand::Register(rd), mem_op],
            false,
        )
    }

    fn decode_load_store_imm(&self, word: u32, _address: u32) -> (String, Vec<Operand>, bool) {
        if let Some(result) = self.decode_bx_blx(word) {
            return result;
        }
        self.decode_load_store(word, _address)
    }

    fn decode_bx_blx(&self, word: u32) -> Option<(String, Vec<Operand>, bool)> {
        let bits_27_24 = (word >> 24) & 0xF;
        let bit_20 = (word >> 20) & 1;
        let rm = (word >> 16) & 0xF;

        let is_bx_blx = bits_27_24 == 0x6 || bits_27_24 == 0x7;
        if is_bx_blx && bit_20 == 1 && (word & 0xFF) == 0x08 {
            let is_blx = (word >> 28) & 0x1 != 0;
            let op = if is_blx { "BLX" } else { "BX" };
            return Some((op.to_string(), vec![Operand::Register(rm as u8)], false));
        }
        None
    }

    fn decode_block_transfer(&self, word: u32, _address: u32) -> (String, Vec<Operand>, bool) {
        let p_bit = (word >> 24) & 1 != 0;
        let u_bit = (word >> 23) & 1 != 0;
        let s_bit = (word >> 22) & 1 != 0;
        let w_bit = (word >> 21) & 1 != 0;
        let l_bit = (word >> 20) & 1 != 0;
        let rn = ((word >> 16) & 0xF) as u8;
        let reg_list = word & 0xFFFF;

        let mut registers = Vec::new();
        for i in 0..16 {
            if (reg_list & (1 << i)) != 0 {
                registers.push(i as u8);
            }
        }

        let mode = match (p_bit, u_bit) {
            (true, true) => "IA",
            (true, false) => "DB",
            (false, true) => "IA",
            (false, false) => "DA",
        };

        let (prefix, suffix_mode) = if rn == 13 {
            let sp_suffix = match (p_bit, u_bit) {
                (true, false) => "FD",
                (false, true) => "IA",
                (true, true) => "EA",
                (false, false) => "DB",
            };
            (if l_bit { "LDM" } else { "STM" }, sp_suffix)
        } else {
            (if l_bit { "LDM" } else { "STM" }, mode)
        };

        let writeback_suffix = if w_bit { "!" } else { "" };

        Self::format_register_list(&registers);

        let op = Operand::MemoryAddress {
            base: rn,
            offset: crate::operand::AddressingMode::Multi {
                base: rn,
                registers,
                increment: u_bit,
                writeback: w_bit,
            },
            writeback: w_bit,
        };

        (
            format!("{}{}{}", prefix, suffix_mode, writeback_suffix),
            vec![op],
            s_bit,
        )
    }

    fn format_register_list(registers: &[u8]) -> String {
        if registers.is_empty() {
            return "{}".to_string();
        }

        // Convert to register names

        // Find contiguous ranges
        let mut ranges: Vec<(u8, u8)> = Vec::new();
        let mut start = registers[0];
        let mut prev = start;

        for &r in &registers[1..] {
            if r == prev + 1 {
                prev = r;
            } else {
                ranges.push((start, prev));
                start = r;
                prev = r;
            }
        }
        ranges.push((start, prev));

        // Format ranges
        let parts: Vec<String> = ranges
            .iter()
            .map(|(s, e)| {
                if *s == *e {
                    match s {
                        13 => "lr".to_string(),
                        15 => "pc".to_string(),
                        _ => format!("r{}", s),
                    }
                } else {
                    let s_name = match s {
                        13 => "lr".to_string(),
                        15 => "pc".to_string(),
                        _ => format!("r{}", s),
                    };
                    let e_name = match e {
                        13 => "lr".to_string(),
                        15 => "pc".to_string(),
                        _ => format!("r{}", e),
                    };
                    format!("{}-{}", s_name, e_name)
                }
            })
            .collect();

        format!("{{{}}}", parts.join(", "))
    }

    fn decode_branch(&self, word: u32, address: u32) -> (String, Vec<Operand>, bool) {
        let l_bit = (word >> 24) & 1 != 0;
        let offset = word & 0xFFFFFF;
        let signed_offset = ((offset as i32) << 8) >> 8;
        // ARM pipeline: PC = current_instruction_address + 8
        // (Thumb uses +4, but this is the ARM decoder)
        let target = address
            .wrapping_add(8)
            .wrapping_add((signed_offset as u32).wrapping_mul(4));

        // Get condition code (bits 28-31)
        let cond_bits = ((word >> 28) & 0xF) as u8;
        let _cond = decode_condition(cond_bits);
        
        // Build opcode name with condition for conditional branches
        // AL (0xE) is unconditional, so use plain B/BL
        // Other conditions: BEQ, BNE, BCS, BCC, etc.
        let op_name = if cond_bits == 0xE {
            // Unconditional branch (AL condition)
            if l_bit { "BL".to_string() } else { "B".to_string() }
        } else {
            // Conditional branch: add condition suffix
            let cond_str = match cond_bits {
                0x0 => "EQ", 0x1 => "NE", 0x2 => "CS", 0x3 => "CC",
                0x4 => "MI", 0x5 => "PL", 0x6 => "VS", 0x7 => "VC",
                0x8 => "HI", 0x9 => "LS", 0xA => "GE", 0xB => "LT",
                0xC => "GT", 0xD => "LE", _ => "AL",
            };
            if l_bit {
                format!("BL{}", cond_str)
            } else {
                format!("B{}", cond_str)
            }
        };

        (op_name, vec![Operand::Immediate(target)], false)
    }
}

impl Default for ArmDecoder {
    fn default() -> Self {
        Self::new()
    }
}

trait ImmediateValue {
    fn immediate_value(&self) -> i32;
}

impl ImmediateValue for Operand {
    fn immediate_value(&self) -> i32 {
        match self {
            Operand::Immediate(v) => *v as i32,
            _ => 0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ldmfd_sp_writeback() {
        // LDMFD r13, {r0-r3, lr}!  - p=1, u=0, L=1, W=1
        // 1110 1001 0011 1101 0000 0000 0000 1111 = 0xe93d000f
        let decoder = ArmDecoder::new();
        let word = 0xe93d000f;
        let (opcode, _, _) = decoder.decode(word, 0);
        assert_eq!(opcode, "LDMFD!");
    }

    #[test]
    fn test_stmia_r0_writeback() {
        // STMIA r0, {r0-r3}!  - p=1, u=1, L=0, W=1
        // 1110 1000 1010 0000 0000 0000 0001 1111 = 0xe8a0001f
        let decoder = ArmDecoder::new();
        let word = 0xe8a0001f;
        let (opcode, _, _) = decoder.decode(word, 0);
        assert_eq!(opcode, "STMIA!");
    }

    #[test]
    fn test_ldmfd_sp_pc() {
        // LDMFD r13, {r0-r3, pc}! - p=1, u=0, L=1, W=1
        // 1110 1001 0011 1101 1000 0000 0000 1111 = 0xe93d800f
        let decoder = ArmDecoder::new();
        let word = 0xe93d800f;
        let (opcode, _, _) = decoder.decode(word, 0);
        assert_eq!(opcode, "LDMFD!");
    }

    #[test]
    fn test_format_register_list() {
        assert_eq!(
            ArmDecoder::format_register_list(&[0, 1, 2, 3, 13]),
            "{r0-r3, lr}"
        );
        assert_eq!(ArmDecoder::format_register_list(&[0, 1, 2, 3]), "{r0-r3}");
        assert_eq!(
            ArmDecoder::format_register_list(&[0, 2, 4, 6]),
            "{r0, r2, r4, r6}"
        );
        assert_eq!(
            ArmDecoder::format_register_list(&[0, 1, 2, 3, 15]),
            "{r0-r3, pc}"
        );
    }

    #[test]
    fn test_branch_instruction() {
        // B instruction: 0xEA00002E (unconditional branch)
        // Bits 27-25 = 101 = branch
        let decoder = ArmDecoder::new();
        let word = 0xEA00002E;
        let (opcode, operands, _) = decoder.decode(word, 0x08000000);
        println!("B instruction: 0x{:08X} -> {} {:?}", word, opcode, operands);
        assert_eq!(opcode, "B");
    }

    #[test]
    fn test_bx_instruction() {
        let decoder = ArmDecoder::new();
        let word = 0x46000008;
        let (opcode, operands, _) = decoder.decode(word, 0x08000000);
        assert_eq!(opcode, "BX");
        assert_eq!(operands[0].display(), "r0");
    }

    #[test]
    fn test_blx_instruction() {
        let decoder = ArmDecoder::new();
        let word = 0x47000008;
        let (opcode, operands, _) = decoder.decode(word, 0x08000000);
        assert_eq!(opcode, "BLX");
        assert_eq!(operands[0].display(), "r0");
    }
}
