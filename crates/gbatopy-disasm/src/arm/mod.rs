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
        
        // Halfword load/store (LDRH/STRH/LDRSB/LDRSH), SWP, MUL, MLA all have
        // bits 27-26 = 00 and are handled by decode_data_processing via the
        // (0b00, _) match arm below. No early return here — routing through the
        // match arm ensures the condition suffix is applied uniformly.
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

        // UNDEFINED/UNKNOWN opcodes must not carry a condition suffix:
        // the codegen fallback raises NotImplementedError unconditionally and
        // the cfg filter matches the bare "UNDEFINED"/"UNKNOWN*" strings.
        let full_name = if base_name == "UNDEFINED" || base_name.starts_with("UNKNOWN") {
            base_name
        } else {
            match cond {
                Some(Condition::Al) | Some(Condition::Nv) => base_name,
                _ => {
                    let suffix = cond.map(|c| c.name()).unwrap_or("??");
                    format!("{}{}", base_name, suffix)
                }
            }
        };

        (full_name, operands, is_thumb)
    }

    fn decode_data_processing(&self, word: u32, _address: u32) -> (String, Vec<Operand>, bool) {
        // BX/BLX: bits[27:24]=0x1, bits[23:20]=0x2(BX) or 0x3(BLX), bits[19:16]=0xF, bits[7:4]=0x1
        // BX:  cond 0001 0010 1111 1111 1111 0001 Rm  (bit 20 = 0)
        // BLX: cond 0001 0011 1111 1111 1111 0001 Rm  (bit 20 = 1)
        let bits_27_24 = (word >> 24) & 0xF;
        let bits_23_20 = (word >> 20) & 0xF;
        let bits_19_16 = (word >> 16) & 0xF;
        let bits_7_4 = (word >> 4) & 0xF;

        let is_bx_blx =
            bits_27_24 == 0x1 && (bits_23_20 == 0x2 || bits_23_20 == 0x3) && bits_19_16 == 0xF && bits_7_4 == 0x1;

        if is_bx_blx {
            let l_bit = (word >> 20) & 1;  // bit 20 distinguishes BX (0) from BLX (1)
            let rm = (word & 0xF) as u8;
            let op = if l_bit != 0 { "BLX" } else { "BX" };
            return (op.to_string(), vec![Operand::Register(rm)], false);
        }

        let bits_23_21 = (word >> 21) & 0x7;
        let bits_7_4 = (word >> 4) & 0xF;

        // Halfword/signed byte load/store: bits[27:25]=000, bit[7]=1, bit[4]=1
        // ARM encoding: bits[7:4] = 1 H 1 S (H=0 halfword, H=1 signed; S=0 byte, S=1 word)
        let bit_7_4 = (word >> 4) & 0xF;
        let bit_7 = (word >> 7) & 1;
        let bit_4 = (word >> 4) & 1;
        let i_bit = (word >> 25) & 1;
        // Halfword/signed transfers only exist when I-bit (bit 25) = 0.
        // When I=1, bits 7-0 are the immediate value of a data-processing op,
        // and bit_7/bit_4 being set is just part of the immediate, not a halfword indicator.
        if i_bit == 0 && bit_7 == 1 && bit_4 == 1 && (bit_7_4 == 0xB || bit_7_4 == 0xD || bit_7_4 == 0xF) {
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

            let imm_offset = (word >> 22) & 1 != 0;
            let w_bit = (word >> 21) & 1 != 0;
            let up_bit = (word >> 23) & 1 != 0;
            let p_bit = (word >> 24) & 1 != 0;

            let addressing_mode = if imm_offset {
                let imm4h = (word >> 8) & 0xF;
                let imm4l = word & 0xF;
                let imm = ((imm4h << 4) | imm4l) as i32;
                let signed_imm = if up_bit { imm } else { -imm };
                if !p_bit {
                    AddressingMode::PostIndexed { base: rn, offset: signed_imm, writeback: w_bit }
                } else if w_bit {
                    AddressingMode::PreIndexed { base: rn, offset: signed_imm, writeback: true }
                } else {
                    AddressingMode::ImmediateOffset(signed_imm)
                }
            } else {
                if !p_bit {
                    AddressingMode::PostIndexedRegister { base: rn, reg: rm }
                } else {
                    AddressingMode::RegisterOffset(rm)
                }
            };

            let mem_op = Operand::MemoryAddress {
                base: rn,
                offset: addressing_mode,
                writeback: w_bit || !p_bit,
            };

            (
                op_name.to_string(),
                vec![Operand::Register(rd), mem_op],
                false,
            )
        } else if bits_27_24 == 0x0 && bits_23_21 == 0x0 && bits_7_4 == 0x9 {
            // MUL: cond 0000 000S Rd 0000 Rs 1001 Rm
            let s_bit = (word >> 20) & 1 != 0;
            let rd = ((word >> 16) & 0xF) as u8;
            let rs = ((word >> 8) & 0xF) as u8;
            let rm = (word & 0xF) as u8;
            (
                "MUL".to_string(),
                vec![
                    Operand::Register(rd),
                    Operand::Register(rm),
                    Operand::Register(rs),
                ],
                s_bit,
            )
        } else if bits_27_24 == 0x0 && bits_23_21 == 0x1 && bits_7_4 == 0x9 {
            // MLA: cond 0000 001S Rd Rn Rs 1001 Rm
            // bits_23_21 == 0x1 means bit 21 (A bit) is set → always MLA
            let s_bit = (word >> 20) & 1 != 0;
            let rd = ((word >> 16) & 0xF) as u8;
            let ra = ((word >> 12) & 0xF) as u8;
            let rs = ((word >> 8) & 0xF) as u8;
            let rm = (word & 0xF) as u8;
            (
                "MLA".to_string(),
                vec![
                    Operand::Register(rd),
                    Operand::Register(rm),
                    Operand::Register(rs),
                    Operand::Register(ra),
                ],
                s_bit,
            )
        } else if bits_27_24 == 0x0 && bits_7_4 == 0x9 && (bits_23_21 & 0x4) != 0 {
            // Long multiply (bit 23 = 1): UMULL/SMULL/UMLAL/SMLAL
            let a_bit = (word >> 21) & 1 != 0;
            let s_bit = (word >> 20) & 1 != 0;
            let rd_hi = ((word >> 16) & 0xF) as u8;
            let rd_lo = ((word >> 12) & 0xF) as u8;
            let rm = (word & 0xF) as u8;
            let rs = ((word >> 8) & 0xF) as u8;

            let is_signed = (word >> 22) & 1 != 0;
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
        } else if bits_27_24 == 0x1 && bits_7_4 == 0x9 && ((word >> 20) & 0x3) == 0x0 {
            // SWP/SWPB: cond 0001 0B 00 Rn Rd 0000 1001 Rm
            // bits 7-4 = 1001 is the unique SWP identifier
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
        } else if bits_27_24 == 0x1 && ((word >> 20) & 0x3) == 0x0 && bits_7_4 == 0x0
            && ((word >> 16) & 0xF) == 0xF && ((word >> 12) & 0xF) == 0x0
        {
            // MRS: cond 0001 0R 00 1111 0000 Rd 0000
            // bits 21-20 = 00, bits 19-16 = 1111, bits 15-12 = 0000, bits 7-4 = 0000
            let r_bit = (word >> 22) & 1;
            let rd = ((word >> 12) & 0xF) as u8;
            let sr = if r_bit != 0 { 1 } else { 0 };
            (
                "MRS".to_string(),
                vec![Operand::Register(rd), Operand::Immediate(sr as u32)],
                false,
            )
        } else if bits_27_24 == 0x1 && ((word >> 20) & 0x3) == 0x2 && bits_7_4 == 0x0
            && ((word >> 23) & 1) == 0 && ((word >> 12) & 0xF) == 0xF
        {
            let s_bit = (word >> 20) & 1 != 0;
            let flags = (word >> 16) & 0xF;
            let _rd = ((word >> 12) & 0xF) as u8;

            let _flags_str = match flags {
                0x1 => "C",
                0x2 => "X",
                0x4 => "S",
                0x8 => "F",
                0xF => "CPSR",
                _ => "CPSR",
            };

            let rm = (word & 0xF) as u8;
            let operand = if (word & (1 << 25)) != 0 {
                Operand::Immediate(word & 0xFF)
            } else {
                Operand::Register(rm)
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

            if let Some(op) = DataOp::from_bits(opcode_bits) {
                // MOV and MVN don't use Rn (bits 19-16 are SBZ).
                // TST/TEQ/CMP/CMN only set flags; Rd (bits 15-12) is SBZ and
                // must not be pushed, otherwise the codegen treats it as a
                // source operand, corrupting the computation.
                let has_rn = !matches!(op, DataOp::Mov | DataOp::Mvn);
                let has_rd = !matches!(op, DataOp::Tst | DataOp::Teq | DataOp::Cmp | DataOp::Cmn);
                let mut operands = vec![];
                if has_rd {
                    operands.push(Operand::Register(rd));
                }

                if i_bit {
                    // Immediate operand: calculate rotated immediate value
                    let imm8 = operand2_bits & 0xFF;
                    let rot = (operand2_bits >> 8) & 0xF;
                    // Rotate right by 2*rot bits
                    let imm_val = if rot == 0 {
                        imm8 as u32
                    } else {
                        let shift = ((2 * rot) % 32) as u32;
                        if shift == 0 {
                            imm8 as u32
                        } else {
                            let imm32 = imm8 as u32;
                            ((imm32 >> shift) | (imm32 << (32 - shift))) & 0xFFFFFFFF
                        }
                    };
                    if has_rn {
                        operands.push(Operand::Register(rn));
                    }
                    operands.push(Operand::Immediate(imm_val));
                } else {
                    // Register operand with optional shift
                    if has_rn {
                        operands.push(Operand::Register(rn));
                    }

                    let rm = (operand2_bits & 0xF) as u8;
                    if (operand2_bits & 0x10) != 0 {
                        // bit 4 = 1: register-specified shift amount (Rs in bits 11-8)
                        let rs = ((operand2_bits >> 8) & 0xF) as u8;
                        let shift_type_bits = ((operand2_bits >> 5) & 0x3) as u8;
                        if let Some(shift) = crate::operand::ShiftType::from_bits(shift_type_bits) {
                            operands.push(Operand::ShiftedRegister {
                                reg: rm,
                                shift,
                                amount: crate::operand::ShiftAmount::Register(rs),
                            });
                        } else {
                            operands.push(Operand::Register(rm));
                        }
                    } else {
                        // bit 4 = 0: immediate shift amount (bits 11-7)
                        let shift_imm = ((operand2_bits >> 7) & 0x1F) as u8;
                        let shift_type_bits = ((operand2_bits >> 5) & 0x3) as u8;
                        if shift_imm == 0 && shift_type_bits == 0 {
                            operands.push(Operand::Register(rm));
                        } else if let Some(shift) = crate::operand::ShiftType::from_bits(shift_type_bits) {
                            operands.push(Operand::ShiftedRegister {
                                reg: rm,
                                shift,
                                amount: crate::operand::ShiftAmount::Immediate(shift_imm),
                            });
                        } else {
                            operands.push(Operand::Register(rm));
                        }
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
        
        // Halfword/signed transfers (LDRH/STRH/LDRSB/LDRSH) have bits 27-25 = 000
        // and are decoded by decode_data_processing (lines 116-237). This function
        // only handles word/byte transfers (bits 27-26 = 01), so the B bit alone
        // distinguishes LDR/STR (word) from LDRB/STRB (byte).
        let op_name = if b_bit {
            if l_bit { "LDRB" } else { "STRB" }
        } else {
            if l_bit { "LDR" } else { "STR" }
        };

        if rn == 15 && !i_bit {
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
        // Compute signed immediate offset from U bit and 12-bit immediate field
        let imm12 = (word & 0xFFF) as i32;
        let signed_imm = if u_bit { imm12 } else { -imm12 };

        // Register offset fields (bit 25 = I: 0=immediate, 1=register)
        let rm = (word & 0xF) as u8;
        let shift_type_bits = ((word >> 5) & 0x3) as u8;
        let shift_imm = (word >> 7) & 0x1F;
        // Extract shift type from bits [6:5]
        let shift_type = crate::ShiftType::from_bits(shift_type_bits);
        // Unshifted = I=1 AND (shift_type=LSL OR invalid) AND shift_imm=0
        let is_unshifted_reg = i_bit && (shift_type_bits == 0 || shift_type.is_none()) && shift_imm == 0;

        let writeback = w_bit || !p_bit;

        // Addressing mode depends on P (pre/post), W (writeback), and I (immediate/register)
        let addressing_mode = if !p_bit {
            // Post-indexed: transfer uses [base] only, then base += offset
            if is_unshifted_reg {
                crate::operand::AddressingMode::PostIndexedRegister { base: rn, reg: rm }
            } else if i_bit {
                // I=1 with shift: use actual shift type from bits [6:5]
                if let Some(shift) = shift_type {
                    crate::operand::AddressingMode::ScaledRegisterOffset {
                        reg: rm,
                        shift,
                        amount: shift_imm as u8,
                    }
                } else {
                    // Invalid shift type - treat as unshifted register offset
                    crate::operand::AddressingMode::RegisterOffset(rm)
                }
            } else {
                crate::operand::AddressingMode::PostIndexed { base: rn, offset: signed_imm, writeback: true }
            }
        } else if w_bit {
            // Pre-indexed with writeback: transfer uses [base + offset], base = base + offset
            if i_bit {
                if is_unshifted_reg {
                    crate::operand::AddressingMode::RegisterOffset(rm)
                } else if let Some(shift) = shift_type {
                    crate::operand::AddressingMode::ScaledRegisterOffset {
                        reg: rm,
                        shift,
                        amount: shift_imm as u8,
                    }
                } else {
                    // Invalid shift type - treat as unshifted
                    crate::operand::AddressingMode::RegisterOffset(rm)
                }
            } else {
                crate::operand::AddressingMode::PreIndexed { base: rn, offset: signed_imm, writeback: true }
            }
        } else {
            // Offset addressing: transfer uses [base + offset], base unchanged
            if i_bit {
                if is_unshifted_reg {
                    crate::operand::AddressingMode::RegisterOffset(rm)
                } else if let Some(shift) = shift_type {
                    crate::operand::AddressingMode::ScaledRegisterOffset {
                        reg: rm,
                        shift,
                        amount: shift_imm as u8,
                    }
                } else {
                    // Invalid shift type - treat as unshifted
                    crate::operand::AddressingMode::RegisterOffset(rm)
                }
            } else {
                crate::operand::AddressingMode::ImmediateOffset(signed_imm)
            }
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
                pre_index: p_bit,
                writeback: w_bit,
                s_bit,
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
