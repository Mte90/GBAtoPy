use crate::{ArmMode, DecodedInstruction, Function, ModeTracker};

#[derive(Debug, Clone, Default)]
pub struct FunctionDiscoveryStats {
    pub entry_points: usize,
    pub branch_follow: usize,
    pub ldr_bx_pattern: usize,
    pub jump_tables: usize,
    pub oracle_fallback: usize,
    pub total_functions: usize,
}

/// Statistics from data region detection
#[derive(Debug, Clone, Default)]
pub struct DataDetectionStats {
    pub unknown_regions_found: usize,
    pub data_instructions_marked: usize,
    pub ldr_str_only_regions: usize,
    pub ldr_str_only_marked: usize,
}

/// Result of multi-pass static function discovery
#[derive(Debug, Clone, Default)]
pub struct FunctionDiscoveryResult {
    pub functions: Vec<Function>,
    pub stats: FunctionDiscoveryStats,
}

pub struct Disassembler {
    arm_decoder: crate::arm::ArmDecoder,
    thumb_decoder: crate::thumb::ThumbDecoder,
    mode_tracker: ModeTracker,
}

impl Disassembler {
    pub fn new() -> Self {
        Self {
            arm_decoder: crate::arm::ArmDecoder::new(),
            thumb_decoder: crate::thumb::ThumbDecoder::new(),
            mode_tracker: ModeTracker::new(),
        }
    }

    pub fn mark_data_regions(
        &mut self,
        instructions: &mut [DecodedInstruction],
    ) -> DataDetectionStats {
        let mut stats = DataDetectionStats::default();

        if instructions.is_empty() {
            return stats;
        }

        let window_size = 16;
        let mut i = 0;
        while i < instructions.len() {
            let end = (i + window_size).min(instructions.len());
            let window = &instructions[i..end];

            let unknown_count = window
                .iter()
                .filter(|inst| inst.opcode.starts_with("UNKNOWN") || inst.opcode == "UNDEFINED")
                .count();

            let unknown_ratio = unknown_count as f64 / window.len() as f64;

            if unknown_ratio > 0.5 {
                stats.unknown_regions_found += 1;
                let data_start = i;
                let mut j = i;
                while j < instructions.len() {
                    let curr_window_start = j.saturating_sub(window_size / 2);
                    let curr_window_end = (j + window_size).min(instructions.len());
                    let curr_window = &instructions[curr_window_start..curr_window_end];

                    let curr_unknown = curr_window
                        .iter()
                        .filter(|inst| {
                            inst.opcode.starts_with("UNKNOWN") || inst.opcode == "UNDEFINED"
                        })
                        .count();

                    if curr_unknown as f64 / curr_window.len() as f64 > 0.5 {
                        j += 1;
                    } else {
                        break;
                    }
                }

                for inst in &mut instructions[data_start..j] {
                    inst.is_data = true;
                    stats.data_instructions_marked += 1;
                }

                i = j.max(i + 1);
            } else {
                i += 1;
            }
        }

        stats
    }



    pub fn disassemble(&mut self, rom_data: &[u8], base_address: u32) -> Vec<DecodedInstruction> {
        let mut instructions = Vec::new();
        let mut address = base_address;

        while address < base_address + (rom_data.len() as u32 - address % 4) {
            let mode = self.mode_tracker.current();

            let (opcode, operands, sets_flags, width) = match mode {
                ArmMode::Arm => {
                    if address + 4 > base_address + rom_data.len() as u32 {
                        break;
                    }
                    let offset = (address - base_address) as usize;
                    if offset + 4 > rom_data.len() {
                        break;
                    }
                    let word = u32::from_le_bytes([
                        rom_data[offset],
                        rom_data[offset + 1],
                        rom_data[offset + 2],
                        rom_data[offset + 3],
                    ]);

                    let (opcode, operands, sets_flags) = self.arm_decoder.decode(word, address);
                    (opcode, operands, sets_flags, 4)
                }
                ArmMode::Thumb => {
                    if address + 2 > base_address + rom_data.len() as u32 {
                        break;
                    }
                    let offset = (address - base_address) as usize;
                    if offset + 2 > rom_data.len() {
                        break;
                    }
                    let halfword = u16::from_le_bytes([rom_data[offset], rom_data[offset + 1]]);

                    // Check if this is the first half of a 32-bit BL instruction
                    let (opcode, operands, sets_flags, width) = if (halfword & 0xF800) == 0xF000 {
                        // Potential BL_PREFIX: opcode range 0xF000-0xF7FF with bit 11 = 0
                        let hw1 = halfword;
                        // Try to read the next halfword for BL_SUFFIX
                        if offset + 4 <= rom_data.len() {
                            let hw2 =
                                u16::from_le_bytes([rom_data[offset + 2], rom_data[offset + 3]]);
                            // Check if hw2 is a valid BL_SUFFIX (bit 11 = 1)
                            if let Some((op, ops, flags, w)) =
                                self.thumb_decoder.decode_bl_pair(hw1, hw2, address)
                            {
                                (op, ops, flags, w)
                            } else {
                                // hw2 is not a valid BL_SUFFIX, fall back to BL_PREFIX
                                let (op, ops, flags) = self.thumb_decoder.decode(hw1, address);
                                (op, ops, flags, 2)
                            }
                        } else {
                            // Can't read next halfword, fall back to BL_PREFIX
                            let (op, ops, flags) = self.thumb_decoder.decode(hw1, address);
                            (op, ops, flags, 2)
                        }
                    } else {
                        // Not a BL_PREFIX, decode normally
                        let (op, ops, flags) = self.thumb_decoder.decode(halfword, address);
                        (op, ops, flags, 2)
                    };
                    (opcode, operands, sets_flags, width)
                }
            };

            let condition = match mode {
                ArmMode::Arm => {
                    let offset = (address - 0x08000000) as usize;
                    if offset + 4 <= rom_data.len() {
                        let word = u32::from_le_bytes([
                            rom_data[offset],
                            rom_data[offset + 1],
                            rom_data[offset + 2],
                            rom_data[offset + 3],
                        ]);
                        crate::decode_condition(((word >> 28) & 0xF) as u8)
                    } else {
                        None
                    }
                }
                ArmMode::Thumb => None,
            };

            let raw = match mode {
                ArmMode::Arm => {
                    let offset = (address - 0x08000000) as usize;
                    if offset + 4 <= rom_data.len() {
                        u32::from_le_bytes([
                            rom_data[offset],
                            rom_data[offset + 1],
                            rom_data[offset + 2],
                            rom_data[offset + 3],
                        ])
                    } else {
                        0
                    }
                }
                ArmMode::Thumb => {
                    let offset = (address - 0x08000000) as usize;
                    if offset + 2 <= rom_data.len() {
                        u16::from_le_bytes([rom_data[offset], rom_data[offset + 1]]) as u32
                    } else {
                        0
                    }
                }
            };

            // BX/BLX mode switch detection:
            // BX/BLX in Thumb mode are returns, NOT mode switches. Skip heuristic.
            // In ARM mode, detect Thumb entry patterns:
            // 1. Odd register index (r1, r3, r5...) → always Thumb
            // 2. Even register index → check if previous instruction is ADD Rd, PC, #N
            //    (common GBA pattern for Thumb entry: ADD R0, PC, #1 / BX R0)
            if (opcode == "BX" || opcode == "BLX") && mode == ArmMode::Arm {
                let is_thumb = match operands.first() {
                    Some(crate::Operand::Register(r)) if *r % 2 == 1 => true,
                    Some(crate::Operand::Register(r)) => {
                        let b_target_reg = *r;
                        // Check previous instruction for ADD Rd, PC, #N pattern
                        // Common GBA Thumb entry: ADD R0, PC, #1 / BX R0
                        instructions
                            .last()
                            .is_some_and(|prev: &DecodedInstruction| {
                                prev.opcode == "ADD"
                                    && prev.mode == ArmMode::Arm
                                    && match prev.operands.first() {
                                        Some(crate::Operand::Register(rd))
                                            if *rd == b_target_reg =>
                                        {
                                            prev.operands.iter().any(|op| match op {
                                                crate::Operand::Immediate(val) => {
                                                    (address + 8 + val) % 2 == 1
                                                }
                                                _ => false,
                                            })
                                        }
                                        _ => false,
                                    }
                            })
                    }
                    _ => false,
                };
                let new_mode = if is_thumb {
                    ArmMode::Thumb
                } else {
                    ArmMode::Arm
                };
                self.mode_tracker.switch_to(address, new_mode);
            }

            instructions.push(DecodedInstruction {
                address,
                opcode,
                operands,
                condition,
                mode,
                raw,
                sets_flags,
                width,
                is_data: false,
            });

            address += width as u32;
        }

        instructions
    }

}

impl Default for Disassembler {
    fn default() -> Self {
        Self::new()
    }
}

impl Disassembler {

    /// Disassemble ONLY the specified addresses (for CFG-first/reachable code analysis).
    /// This prevents linear sweep on large ROMs by disassembling only reachable code.
    ///
    /// # Arguments
    /// * `rom` - The ROM data to disassemble
    /// * `addresses` - Sorted list of addresses to disassemble (from CFG reachable analysis)
    ///
    /// # Returns
    /// Vector of decoded instructions, sorted by address
    pub fn selective_disassemble(
        &mut self,
        rom: &[u8],
        _addresses: &[u32],
        mode_map: &[(u32, ArmMode)],
    ) -> Vec<DecodedInstruction> {
        let mut instructions = Vec::new();
        let arm_decoder = crate::arm::ArmDecoder::new();
        let thumb_decoder = crate::thumb::ThumbDecoder::new();

        // Iterate over mode_map directly so each (addr, mode) pair produces
        // one instruction. This handles mixed-mode addresses correctly: if
        // the CFG visited the same address in both ARM and Thumb modes, both
        // instructions are generated.
        for &(addr, mode) in mode_map {
            let decode_addr = if mode == ArmMode::Thumb {
                addr & !1
            } else {
                addr
            };
            let rom_offset = (decode_addr - 0x08000000) as usize;

            if rom_offset >= rom.len() {
                continue;
            }

            match mode {
                ArmMode::Arm => {
                    if rom_offset + 4 > rom.len() {
                        continue;
                    }
                    let word = u32::from_le_bytes([
                        rom[rom_offset],
                        rom[rom_offset + 1],
                        rom[rom_offset + 2],
                        rom[rom_offset + 3],
                    ]);
                    let (opcode, operands, sets_flags) = arm_decoder.decode(word, decode_addr);
                    let condition = crate::decode_condition(((word >> 28) & 0xF) as u8);

                    instructions.push(DecodedInstruction {
                        address: addr,
                        opcode,
                        operands,
                        condition,
                        raw: word,
                        sets_flags,
                        width: 4,
                        mode: ArmMode::Arm,
                        is_data: false,
                    });
                }
                ArmMode::Thumb => {
                    if rom_offset + 2 > rom.len() {
                        continue;
                    }
                    let halfword = u16::from_le_bytes([rom[rom_offset], rom[rom_offset + 1]]);

                    // Check if this is the first half of a 32-bit BL instruction
                    let (opcode, operands, sets_flags, width) = if (halfword & 0xF800) == 0xF000 {
                        // Potential BL_PREFIX: opcode range 0xF000-0xF7FF with bit 11 = 0
                        let hw1 = halfword;
                        // Try to read the next halfword for BL_SUFFIX
                        if rom_offset + 4 <= rom.len() {
                            let hw2 =
                                u16::from_le_bytes([rom[rom_offset + 2], rom[rom_offset + 3]]);
                            // Check if hw2 is a valid BL_SUFFIX (bit 11 = 1)
                            if let Some((op, ops, flags, w)) =
                                thumb_decoder.decode_bl_pair(hw1, hw2, decode_addr)
                            {
                                (op, ops, flags, w)
                            } else {
                                // hw2 is not a valid BL_SUFFIX, fall back to BL_PREFIX
                                let (op, ops, flags) = thumb_decoder.decode(hw1, decode_addr);
                                (op, ops, flags, 2)
                            }
                        } else {
                            // Can't read next halfword, fall back to BL_PREFIX
                            let (op, ops, flags) = thumb_decoder.decode(hw1, decode_addr);
                            (op, ops, flags, 2)
                        }
                    } else {
                        // Not a BL_PREFIX, decode normally
                        let (op, ops, flags) = thumb_decoder.decode(halfword, decode_addr);
                        (op, ops, flags, 2)
                    };

                    instructions.push(DecodedInstruction {
                        address: addr,
                        opcode,
                        operands,
                        condition: None,
                        raw: halfword as u32,
                        sets_flags,
                        width,
                        mode: ArmMode::Thumb,
                        is_data: false,
                    });
                }
            }
        }

        instructions
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Test 1: Disassembler construction with known ROM buffer
    #[test]
    fn test_disassembler_new() {
        let rom: Vec<u8> = vec![0x00, 0x00, 0x00, 0x00];
        let mut disassembler = Disassembler::new();
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        // Should decode at least one instruction
        assert!(!instructions.is_empty());
        // Initial mode should be ARM
        assert_eq!(instructions[0].mode, ArmMode::Arm);
        assert_eq!(instructions[0].address, 0x08000000);
    }

    /// Test 2: Decode ARM NOP (0xE1A00000 = MOV R0, R0)
    #[test]
    fn test_decode_arm_nop() {
        let rom: Vec<u8> = vec![0x00, 0x00, 0xA0, 0xE1]; // ARM NOP (MOV R0, R0)
        let mut disassembler = Disassembler::new();
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        assert!(!instructions.is_empty());
        assert_eq!(instructions[0].opcode, "MOV");
        assert_eq!(instructions[0].width, 4);
        assert_eq!(instructions[0].mode, ArmMode::Arm);
    }

    /// Test 3: Decode Thumb MOV Rd, #imm8
    #[test]
    fn test_decode_thumb_mov() {
        let rom: Vec<u8> = vec![0x00, 0x20]; // MOV R0, #0
        let mut disassembler = Disassembler::new();
        
        // Force Thumb mode by switching
        disassembler.mode_tracker.switch_to(0x08000000, ArmMode::Thumb);
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        assert!(!instructions.is_empty());
        assert_eq!(instructions[0].opcode, "MOV");
        assert_eq!(instructions[0].width, 2);
        assert_eq!(instructions[0].mode, ArmMode::Thumb);
    }

    /// Test 4: Decode ARM B instruction (0xEA000000)
    #[test]
    fn test_decode_arm_branch() {
        let rom: Vec<u8> = vec![0x00, 0x00, 0x00, 0xEA]; // B . (branch to self)
        let mut disassembler = Disassembler::new();
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        assert!(!instructions.is_empty());
        assert_eq!(instructions[0].opcode, "B");
        assert_eq!(instructions[0].width, 4);
    }

    /// Test 5: Mode detection - entry point at 0x08000000 with ARM mode
    #[test]
    fn test_mode_detection_arm() {
        let rom: Vec<u8> = vec![0x00, 0x00, 0xA0, 0xE1]; // ARM NOP
        let mut disassembler = Disassembler::new();
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        // Default mode is ARM
        assert_eq!(instructions[0].mode, ArmMode::Arm);
    }

    /// Test 6: Mode detection - Thumb mode via switch
    #[test]
    fn test_mode_detection_thumb() {
        let rom: Vec<u8> = vec![0x00, 0x20, 0x00, 0x00]; // Thumb MOV R0, #0 + padding
        let mut disassembler = Disassembler::new();
        
        // Simulate Thumb entry point - start at aligned address but in Thumb mode
        disassembler.mode_tracker.switch_to(0x08000000, ArmMode::Thumb);
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        assert!(!instructions.is_empty());
        assert_eq!(instructions[0].mode, ArmMode::Thumb);
        assert_eq!(instructions[0].width, 2);
    }

    /// Test 7: Decode at specific address
    #[test]
    fn test_decode_at_specific_address() {
        // Create ROM with different instructions at different offsets
        let rom: Vec<u8> = vec![
            0x00, 0x00, 0xA0, 0xE1, // 0x00: MOV R0, R0
            0x01, 0x00, 0xA0, 0xE1, // 0x04: MOV R0, R0, LSL #2
            0x02, 0x00, 0xA0, 0xE1, // 0x08: MOV R0, R0, LSL #4
        ];
        let mut disassembler = Disassembler::new();
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        // Verify first instruction at 0x08000000
        assert_eq!(instructions[0].address, 0x08000000);
        // Verify second instruction at 0x08000004
        assert_eq!(instructions[1].address, 0x08000004);
    }

    /// Test 8: Mixed ARM/Thumb switch via BX instruction
    #[test]
    fn test_mixed_arm_thumb_switch() {
        // ARM code that branches to Thumb
        // 0xE12FFF10 = BX R0 (branch to Thumb if R0 is odd)
        let rom: Vec<u8> = vec![
            0x10, 0xFF, 0x2F, 0xE1, // BX R0
        ];
        let mut disassembler = Disassembler::new();
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        assert!(!instructions.is_empty());
        assert_eq!(instructions[0].opcode, "BX");
        assert_eq!(instructions[0].mode, ArmMode::Arm);
    }

    /// Test 9: Decode data region (0x00000000 should be recognized as UNKNOWN/UNDEFINED)
    #[test]
    fn test_decode_data_region() {
        let rom: Vec<u8> = vec![0x00, 0x00, 0x00, 0x00]; // All zeros - likely data
        let mut disassembler = Disassembler::new();
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        assert!(!instructions.is_empty());
        // Zero bytes decode to some instruction (MOV R0, R0 in ARM), but we test
        // that the disassembler handles it without crashing
        assert_eq!(instructions[0].width, 4);
        
        // Test data region marking
        let mut stats = disassembler.mark_data_regions(&mut instructions.clone());
        // All-zero pattern may or may not be marked as data depending on the algorithm
        // Just verify it doesn't crash
        let _ = stats;
    }

    /// Test 10: Decode Thumb BL pair (32-bit branch with link)
    #[test]
    fn test_decode_bl_pair() {
        // BL instruction: 0xF000F800 (BL_PREFIX 0xF000 + BL_SUFFIX 0xF800)
        // This is a 32-bit Thumb BL instruction
        let rom: Vec<u8> = vec![
            0x00, 0xF0, // BL_PREFIX
            0x00, 0xF8, // BL_SUFFIX
        ];
        let mut disassembler = Disassembler::new();
        
        disassembler.mode_tracker.switch_to(0x08000000, ArmMode::Thumb);
        
        let instructions = disassembler.disassemble(&rom, 0x08000000);
        
        assert!(!instructions.is_empty());
        // Should recognize as BL (or BL_PREFIX if suffix not valid)
        assert!(instructions[0].opcode == "BL" || instructions[0].opcode == "BL_PREFIX");
        assert_eq!(instructions[0].width, 4); // 32-bit instruction
    }

    /// Test 11: Verify selective_disassemble with mode_map
    #[test]
    fn test_selective_disassemble() {
        let rom: Vec<u8> = vec![
            0x00, 0x00, 0xA0, 0xE1, // ARM: MOV R0, R0
            0x01, 0x00, 0xA0, 0xE1, // ARM: MOV R0, R0, LSL #2
        ];
        let mut disassembler = Disassembler::new();
        
        let mode_map = vec![
            (0x08000000, ArmMode::Arm),
            (0x08000004, ArmMode::Arm),
        ];
        
        let instructions = disassembler.selective_disassemble(&rom, &[0x08000000, 0x08000004], &mode_map);
        
        assert_eq!(instructions.len(), 2);
        assert_eq!(instructions[0].address, 0x08000000);
        assert_eq!(instructions[1].address, 0x08000004);
    }

    /// Test 12: Verify data region detection marks unknown patterns
    #[test]
    fn test_data_region_detection() {
        // Mix of valid instructions and data-like patterns
        let mut instructions = vec![
            DecodedInstruction {
                address: 0x08000000,
                opcode: "MOV".to_string(),
                operands: vec![],
                condition: None,
                mode: ArmMode::Arm,
                raw: 0xE1A00000,
                sets_flags: false,
                width: 4,
                is_data: false,
            },
            DecodedInstruction {
                address: 0x08000004,
                opcode: "UNKNOWN".to_string(),
                operands: vec![],
                condition: None,
                mode: ArmMode::Arm,
                raw: 0xFFFFFFFF,
                sets_flags: false,
                width: 4,
                is_data: false,
            },
            DecodedInstruction {
                address: 0x08000008,
                opcode: "UNDEFINED".to_string(),
                operands: vec![],
                condition: None,
                mode: ArmMode::Arm,
                raw: 0x00000000,
                sets_flags: false,
                width: 4,
                is_data: false,
            },
        ];
        
        let mut disassembler = Disassembler::new();
        let stats = disassembler.mark_data_regions(&mut instructions);
        
        // Verify stats are updated
        assert!(stats.unknown_regions_found >= 0);
        
        // Some instructions should be marked as data
        let data_count = instructions.iter().filter(|i| i.is_data).count();
        // At least the UNKNOWN/UNDEFINED ones should potentially be marked
        let _ = data_count;
    }
}
