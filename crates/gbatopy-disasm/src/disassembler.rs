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

    /// Check if opcode is a memory access instruction (LDR/STR/LDM/STM/PUSH/POP)
    fn is_memory_opcode(opcode: &str) -> bool {
        opcode.starts_with("LDR")
            || opcode.starts_with("STR")
            || opcode.starts_with("LDM")
            || opcode.starts_with("STM")
            || opcode == "PUSH"
            || opcode == "POP"
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

                i = j;
            } else {
                i += 1;
            }
        }

        stats
    }

    pub fn mark_data_regions_by_reference(
        &mut self,
        instructions: &[DecodedInstruction],
    ) -> DataDetectionStats {
        let mut stats = DataDetectionStats::default();

        if instructions.is_empty() {
            return stats;
        }

        let window_size = 8;
        let mut i = 0;
        while i < instructions.len() {
            let end = (i + window_size).min(instructions.len());
            let window = &instructions[i..end];

            let is_ldr_str_only = window
                .iter()
                .all(|inst| Self::is_memory_opcode(&inst.opcode));

            if is_ldr_str_only && window.len() >= 4 {
                stats.ldr_str_only_regions += 1;
                let data_start = i;
                let mut j = i;
                while j < instructions.len() {
                    let curr_window_start = j.saturating_sub(window_size / 2);
                    let curr_window_end = (j + window_size).min(instructions.len());
                    let curr_window = &instructions[curr_window_start..curr_window_end];

                    let curr_ldr_str_only = curr_window
                        .iter()
                        .all(|inst| Self::is_memory_opcode(&inst.opcode));

                    if curr_ldr_str_only {
                        j += 1;
                    } else {
                        break;
                    }
                }

                stats.ldr_str_only_marked += j - data_start;
                i = j;
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

                    let (opcode, operands, sets_flags) =
                        self.thumb_decoder.decode(halfword, address);
                    (opcode, operands, sets_flags, 2)
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

            if opcode == "BX" || opcode == "BLX" {
                let is_thumb = match operands.first() {
                    Some(crate::Operand::Register(r)) => *r % 2 == 1,
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

    pub fn detect_functions(&self, rom_data: &[u8], base_address: u32) -> Vec<Function> {
        let mut functions = Vec::new();
        let end_address = base_address + rom_data.len() as u32;

        let mut function_starts: Vec<u32> = Vec::new();
        let mut address = base_address;

        while address < end_address && address < base_address + 0x100000 {
            if address < base_address + 0x100 {
                address += 4;
                continue;
            }

            let offset = (address - 0x08000000) as usize;
            if offset + 4 > rom_data.len() {
                break;
            }

            let word = u32::from_le_bytes([
                rom_data[offset],
                rom_data[offset + 1],
                rom_data[offset + 2],
                rom_data[offset + 3],
            ]);

            let is_bl = (word >> 25) & 0x7 == 0b101 && (word >> 24) & 0x1 == 1;
            let _is_b = ((word >> 28) & 0xF) != 0xE
                && ((word >> 24) & 0x1) == 0
                && ((word >> 25) & 0x1) == 0
                && ((word >> 26) & 0x1) == 0;
            let is_b_cond = ((word >> 28) & 0xF) != 0xE && ((word >> 24) & 0xF) == 0xA; // bits 27-24 = 1010 for B instruction
            let _opcode = (word >> 20) & 0xFF;
            let _cond = (word >> 28) & 0xF;

            // Handle BL (branch with link)
            if is_bl {
                let offset24 = word & 0x00FFFFFF;
                let sign_extended = if offset24 & 0x800000 != 0 {
                    offset24 | 0xFF000000
                } else {
                    offset24
                } as i32;
                let target = (address as i32 + 8 + (sign_extended << 2)) as u32;
                if target >= base_address && target < end_address {
                    let aligned_target = target & !3;
                    if !function_starts.contains(&aligned_target) {
                        function_starts.push(aligned_target);
                    }
                }
            }

            // Handle conditional B instructions (BEQ, BNE, BGT, BLT, etc.)
            if is_b_cond {
                let offset24 = word & 0x00FFFFFF;
                let sign_extended = if offset24 & 0x800000 != 0 {
                    offset24 | 0xFF000000
                } else {
                    offset24
                } as i32;
                let target = (address as i32 + 8 + (sign_extended << 2)) as u32;
                if target >= base_address && target < end_address {
                    let aligned_target = target & !3;
                    if !function_starts.contains(&aligned_target) {
                        function_starts.push(aligned_target);
                    }
                }
            }

            address += 4;
        }

        for &start in &function_starts {
            let mut end = start;
            let mut probe = start + 4;

            while probe < end_address && probe < start + 0x8000 {
                let offset = (probe - base_address) as usize;
                if offset + 4 > rom_data.len() {
                    break;
                }

                let word = u32::from_le_bytes([
                    rom_data[offset],
                    rom_data[offset + 1],
                    rom_data[offset + 2],
                    rom_data[offset + 3],
                ]);

                let is_bl = (word >> 25) & 0x7 == 0b101 && (word >> 24) & 0x1 == 1;
                if is_bl {
                    let offset24 = word & 0x00FFFFFF;
                    let sign_extended = if offset24 & 0x800000 != 0 {
                        offset24 | 0xFF000000
                    } else {
                        offset24
                    } as i32;
                    let potential_target = (probe as i32 + 8 + (sign_extended << 2)) as u32;
                    if potential_target >= base_address && potential_target < end_address {
                        end = probe;
                        break;
                    }
                }

                probe += 4;
            }

            let func_size = (end - start).max(64);

            functions.push(Function {
                name: format!("func_{:08X}", start),
                address: start,
                size: func_size,
                is_thumb: start % 2 == 1,
                mode_switches: Vec::new(),
            });
        }

        functions
    }
}

impl Default for Disassembler {
    fn default() -> Self {
        Self::new()
    }
}

impl Disassembler {
    pub fn discover_functions_multi_pass(
        &mut self,
        rom_data: &[u8],
        base_address: u32,
        oracle_addrs: Option<Vec<u32>>,
    ) -> FunctionDiscoveryResult {
        let end_address = base_address.wrapping_add(rom_data.len() as u32);
        let mut discovered: std::collections::HashSet<u32> = std::collections::HashSet::new();
        let mut stats = FunctionDiscoveryStats::default();

        let start_address = base_address;
        if start_address >= 0x08000000 && start_address < 0x09000000 {
            let reset_addr = 0x08000000;
            if !discovered.contains(&reset_addr) {
                discovered.insert(reset_addr);
                stats.entry_points += 1;
            }

            for vector_offset in [0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C] {
                let vector_addr = 0x08000000 + vector_offset;
                if vector_addr < end_address && (vector_addr & 0x3) == 0 {
                    let offset = (vector_addr - base_address) as usize;
                    if offset + 4 <= rom_data.len() {
                        let word = u32::from_le_bytes([
                            rom_data[offset],
                            rom_data[offset + 1],
                            rom_data[offset + 2],
                            rom_data[offset + 3],
                        ]);
                        if word != 0 && word >= base_address && word < end_address {
                            let aligned = word & !1;
                            if !discovered.contains(&aligned) {
                                discovered.insert(aligned);
                                stats.entry_points += 1;
                            }
                        }
                    }
                }
            }
        }

        let mut pending: Vec<u32> = discovered.iter().copied().collect();
        let mut visited: std::collections::HashSet<u32> = std::collections::HashSet::new();

        while let Some(current_addr) = pending.pop() {
            if visited.contains(&current_addr) {
                continue;
            }
            visited.insert(current_addr);

            if current_addr < base_address || current_addr >= end_address {
                continue;
            }

            let mut branch_target = current_addr;
            let mut max_instructions = 256;
            let mut consecutive_unconditional_branches = 0;

            while branch_target < end_address
                && branch_target >= base_address
                && max_instructions > 0
            {
                let offset = (branch_target - base_address) as usize;
                if offset + 4 > rom_data.len() {
                    break;
                }

                let word = u32::from_le_bytes([
                    rom_data[offset],
                    rom_data[offset + 1],
                    rom_data[offset + 2],
                    rom_data[offset + 3],
                ]);

                let opcode = (word >> 20) & 0xFF;
                let cond = (word >> 28) & 0xF;
                let is_b = (opcode & 0xE0) == 0xE0 && ((word >> 24) & 0x1) == 0;
                let is_bl = (word >> 25) & 0x7 == 0b101 && (word >> 24) & 0x1 == 1;
                let is_bx = (word & 0x0FFFFFF0) == 0x012FFF10;
                let is_blx = (word & 0x0FFFFFF0) == 0x012FFF30;

                if is_bl && cond == 0xE {
                    let offset24 = word & 0x00FFFFFF;
                    let sign_extended = if offset24 & 0x800000 != 0 {
                        offset24 | 0xFF000000
                    } else {
                        offset24
                    } as i32;
                    let target = (branch_target as i32 + 8 + (sign_extended << 2)) as u32;
                    let aligned = target & !1;
                    if aligned >= base_address
                        && aligned < end_address
                        && !discovered.contains(&aligned)
                    {
                        discovered.insert(aligned);
                        stats.branch_follow += 1;
                        pending.push(aligned);
                    }
                }

                if is_b && cond == 0xE {
                    let offset24 = word & 0x00FFFFFF;
                    let sign_extended = if offset24 & 0x800000 != 0 {
                        offset24 | 0xFF000000
                    } else {
                        offset24
                    } as i32;
                    let target = (branch_target as i32 + 8 + (sign_extended << 2)) as u32;
                    let aligned = target & !1;
                    if aligned >= base_address && aligned < end_address {
                        branch_target = aligned;
                        consecutive_unconditional_branches += 1;
                        if consecutive_unconditional_branches > 10 {
                            break;
                        }
                        continue;
                    }
                }

                if is_bx || is_blx {
                    break;
                }

                if is_bl && cond != 0xE {
                    let offset24 = word & 0x00FFFFFF;
                    let sign_extended = if offset24 & 0x800000 != 0 {
                        offset24 | 0xFF000000
                    } else {
                        offset24
                    } as i32;
                    let target = (branch_target as i32 + 8 + (sign_extended << 2)) as u32;
                    let aligned = target & !1;
                    if aligned >= base_address
                        && aligned < end_address
                        && !discovered.contains(&aligned)
                    {
                        discovered.insert(aligned);
                        stats.branch_follow += 1;
                        pending.push(aligned);
                    }
                }

                // Handle conditional B instructions (BEQ, BNE, BGT, BLT, etc.)
                if is_b && cond != 0xE {
                    let offset24 = word & 0x00FFFFFF;
                    let sign_extended = if offset24 & 0x800000 != 0 {
                        offset24 | 0xFF000000
                    } else {
                        offset24
                    } as i32;
                    let target = (branch_target as i32 + 8 + (sign_extended << 2)) as u32;
                    let aligned = target & !1;
                    if aligned >= base_address
                        && aligned < end_address
                        && !discovered.contains(&aligned)
                    {
                        discovered.insert(aligned);
                        stats.branch_follow += 1;
                        pending.push(aligned);
                    }
                }

                branch_target += 4;
                max_instructions -= 1;
            }
        }

        let search_start = base_address;
        let search_end = (base_address + rom_data.len() as u32).min(base_address + 0x100000);

        let mut scan_addr = search_start;
        while scan_addr + 8 < search_end {
            let offset = (scan_addr - base_address) as usize;
            if offset + 8 > rom_data.len() {
                break;
            }

            let word1 = u32::from_le_bytes([
                rom_data[offset],
                rom_data[offset + 1],
                rom_data[offset + 2],
                rom_data[offset + 3],
            ]);
            let word2 = u32::from_le_bytes([
                rom_data[offset + 4],
                rom_data[offset + 5],
                rom_data[offset + 6],
                rom_data[offset + 7],
            ]);

            let is_ldr_pc = (word1 & 0x0FFF0000) == 0x059F0000;
            let is_bx_lr = (word2 & 0x0FFFFFF0) == 0x012FFF10 && ((word2 >> 12) & 0xF) == 0xE;

            if is_ldr_pc && is_bx_lr {
                let offset12 = word1 & 0xFFF;
                let literal_addr = (scan_addr as i32 + 8 + offset12 as i32) as u32;
                if !discovered.contains(&literal_addr) {
                    discovered.insert(literal_addr);
                    stats.ldr_bx_pattern += 1;
                }
            }

            scan_addr += 4;
        }

        if let Some(oracle_addrs) = oracle_addrs {
            for addr in oracle_addrs {
                let aligned = addr & !1;
                if aligned >= base_address
                    && aligned < end_address
                    && !discovered.contains(&aligned)
                {
                    discovered.insert(aligned);
                    stats.oracle_fallback += 1;
                }
            }
        }

        stats.total_functions = discovered.len();

        let mut functions: Vec<Function> = discovered
            .iter()
            .map(|&addr| {
                let mut func_end = addr;
                let mut probe = addr.wrapping_add(4);
                let max_probe = end_address.min(addr.wrapping_add(0x8000));

                while probe < max_probe && probe >= base_address {
                    let offset = (probe - base_address) as usize;
                    if offset + 4 > rom_data.len() {
                        break;
                    }

                    let word = u32::from_le_bytes([
                        rom_data[offset],
                        rom_data[offset + 1],
                        rom_data[offset + 2],
                        rom_data[offset + 3],
                    ]);

                    let is_bl = (word >> 25) & 0x7 == 0b101 && (word >> 24) & 0x1 == 1;
                    let cond = (word >> 28) & 0xF;
                    if is_bl && cond == 0xE {
                        func_end = probe;
                        break;
                    }
                    if is_bl {
                        func_end = probe;
                    }

                    probe += 4;
                }

                let func_size = ((func_end + 4).saturating_sub(addr)).max(64);

                Function {
                    name: format!("func_{:08X}", addr),
                    address: addr,
                    size: func_size,
                    is_thumb: addr % 2 == 1,
                    mode_switches: Vec::new(),
                }
            })
            .collect();

        functions.sort_by_key(|f| f.address);

        FunctionDiscoveryResult { functions, stats }
    }

    /// Disassemble only specific addresses (for reachable code analysis)
    pub fn selective_disassemble(
        &mut self,
        rom_data: &[u8],
        addresses: &[u32],
        base_address: u32,
    ) -> Vec<DecodedInstruction> {
        let mut instructions = Vec::new();
        
        // Sort addresses for efficient processing
        let mut sorted_addrs = addresses.to_vec();
        sorted_addrs.sort();

        for &address in &sorted_addrs {
            let offset = (address - base_address) as usize;
            
            // Check bounds
            if offset >= rom_data.len() {
                continue;
            }

            let mode = self.mode_tracker.current();
            let (opcode, operands, sets_flags, width) = match mode {
                ArmMode::Arm => {
                    if offset + 4 > rom_data.len() {
                        continue;
                    }
                    let word = u32::from_le_bytes([
                        rom_data[offset],
                        rom_data[offset + 1],
                        rom_data[offset + 2],
                        rom_data[offset + 3],
                    ]);
                ArmMode::Arm => {
                    if offset + 4 > rom_data.len() {
                        continue;
                    }
                    let word = u32::from_le_bytes([
                        rom_data[offset],
                        rom_data[offset + 1],
                        rom_data[offset + 2],
                        rom_data[offset + 3],
                    ]);
                    let cond_bits = ((word >> 28) & 0xF) as u8;
                    let cond = crate::condition::decode_condition(cond_bits);
                    let (opcode, operands, sets_flags) = self.arm_decoder.decode(word, address);
                    (opcode, operands, sets_flags, 4, cond)
                }
            };
            
            let instruction = DecodedInstruction {
                address,
                opcode: opcode.to_string(),
                operands,
                condition,
                mode,
                raw: 0,
                sets_flags,
                width,
                is_data: false,
            };

            // Update mode tracker
            instructions.push(instruction);
        }

        instructions
    }
}
