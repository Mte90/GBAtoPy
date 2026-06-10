//! Control Flow Graph (CFG) builder for GBA ROM disassembly.
//!
//! This module implements reachable code analysis by performing a BFS traversal
//! from the entry point, following branch targets to discover all reachable code.

use crate::arm::ArmDecoder;
use crate::thumb::ThumbDecoder;
use crate::{ArmMode, Operand};
use std::collections::{HashMap, HashSet};

/// Tracks constant values in registers for indirect jump resolution.
/// Only tracks simple cases: MOV rN, #imm and LDR rN, =imm
#[derive(Debug, Default)]
pub struct RegisterTracker {
    values: HashMap<u8, u32>,
}

impl RegisterTracker {
    pub fn new() -> Self {
        Self::default()
    }

    /// Track a MOV rN, #imm instruction
    pub fn track_mov_immediate(&mut self, rd: u8, imm: u32) {
        self.values.insert(rd, imm);
    }

    /// Track an LDR rN, =imm pseudo-instruction
    pub fn track_ldr_literal(&mut self, rd: u8, imm: u32) {
        self.values.insert(rd, imm);
    }

    /// Get the tracked value for a register, if any
    pub fn get(&self, rn: u8) -> Option<u32> {
        self.values.get(&rn).copied()
    }

    /// Invalidate a register value
    pub fn invalidate(&mut self, rn: u8) {
        self.values.remove(&rn);
    }

    /// Invalidate all registers (e.g., after a function call)
    pub fn invalidate_all(&mut self) {
        self.values.clear();
    }
}

#[derive(Debug, Default)]
pub struct CfgBuilder {
    pub instruction_addresses: Vec<u32>,
    pub branch_targets: Vec<u32>,
    pub mode_map: Vec<(u32, ArmMode)>,
    register_tracker: RegisterTracker,
}

impl CfgBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn build_from_entry(&mut self, rom: &[u8], entry_point: u32) {
        let mut visited: HashSet<u32> = HashSet::new();
        let mut to_visit = vec![entry_point];
        let arm_decoder = ArmDecoder::new();
        let thumb_decoder = ThumbDecoder::new();
        
        // Safety limit to prevent infinite loops on corrupted ROMs
        const MAX_INSTRUCTIONS: usize = 500_000;
        let mut instruction_count = 0;

        while let Some(addr) = to_visit.pop() {
            if visited.contains(&addr) {
                continue;
            }
            visited.insert(addr);

            // Progress reporting every 100K instructions
            if instruction_count % 100_000 == 0 {
                eprintln!("  CFG progress: {} visited, {} branch targets", 
                          instruction_count, self.branch_targets.len());
            }

            // Determine mode for this specific address
            let current_mode = if addr % 2 == 1 { ArmMode::Thumb } else { ArmMode::Arm };

            let rom_offset = (addr - 0x08000000) as usize;
            if rom_offset >= rom.len() {
                continue;
            }

            let (opcode_str, operands, _is_thumb, _width) = match current_mode {
                ArmMode::Arm => {
                    if rom_offset + 4 > rom.len() {
                        continue;
                    }
                    let opcode = u32::from_le_bytes([
                        rom[rom_offset],
                        rom[rom_offset + 1],
                        rom[rom_offset + 2],
                        rom[rom_offset + 3],
                    ]);
                    let (op, ops, thumb) = arm_decoder.decode(opcode, addr);
                    (op, ops, thumb, 4)
                }
                ArmMode::Thumb => {
                    if rom_offset + 2 > rom.len() {
                        continue;
                    }
                    let opcode = u16::from_le_bytes([rom[rom_offset], rom[rom_offset + 1]]);
                    let (op, ops, thumb) = thumb_decoder.decode(opcode, addr);
                    (op, ops, thumb, 2)
                }
            };

            self.instruction_addresses.push(addr);
            self.mode_map.push((addr, current_mode));

            // Track register values for indirect jump resolution
            self.track_register_values(&opcode_str, &operands);

            let targets = self.extract_branch_targets(&opcode_str, &operands);
            
            // Determine instruction width based on current mode
            let instr_width = if current_mode == ArmMode::Thumb { 2 } else { 4 };
            
            // Check if this is ANY branch (unconditional or conditional)
            // Branches should NOT add fall-through because they may not execute
            // We still add the branch target separately, so we need to be selective about fall-through
            let is_branch = opcode_str.starts_with('B') 
                && !opcode_str.starts_with("BIT")  // Exclude BIT, BIC, etc.
                && opcode_str != "BKPT"  // Not a branch
                && opcode_str != "BLX";  // Handled separately below
            
            // For unconditional branches (B, BL, BX without condition), no fall-through
            // For conditional branches (BEQ, BNE, etc.), we add fall-through because 
            // the branch might not be taken - but we need to be careful
            // Actually, for accurate CFG, we should add fall-through for ALL branches
            // because we don't know if they'll be taken at runtime
            let is_definite_branch = opcode_str == "B" || opcode_str == "BX";
            
            if !is_definite_branch {
                let next_addr = addr + instr_width;
                if !visited.contains(&next_addr) && ((next_addr - 0x08000000) as usize) < rom.len() {
                    to_visit.push(next_addr);
                }
            }

            for target in targets {
                if !visited.contains(&target) {
                    to_visit.push(target);
                }
                if !self.branch_targets.contains(&target) {
                    self.branch_targets.push(target);
                }
            }

            // Invalidate register tracker after BL/BLX (function call)
            if opcode_str == "BL" || opcode_str == "BLX" {
                self.register_tracker.invalidate_all();
            }
        }

        self.instruction_addresses.sort();
        self.branch_targets.sort();
        self.mode_map.sort_by_key(|(a, _)| *a);
    }

    /// Track register values for MOV rN, #imm and LDR rN, =imm patterns
    fn track_register_values(&mut self, opcode: &str, operands: &[Operand]) {
        // MOV rN, #imm
        if opcode.starts_with("MOV") && operands.len() >= 2 {
            if let Operand::Register(rd) = operands[0] {
                if let Operand::Immediate(imm) = operands[1] {
                    self.register_tracker.track_mov_immediate(rd, imm);
                }
            }
        }
        // LDR rN, =literal (PC-relative load of constant)
        else if opcode.starts_with("LDR") && operands.len() >= 2 {
            if let Operand::Register(rd) = operands[0] {
                if let Operand::Immediate(imm) = operands[1] {
                    // Check if this looks like a PC-relative literal load
                    if imm >= 0x08000000 && imm < 0x0A000000 {
                        self.register_tracker.track_ldr_literal(rd, imm);
                    }
                }
            }
        }
    }

    fn extract_branch_targets(&mut self, opcode: &str, operands: &[Operand]) -> Vec<u32> {
        let mut targets = Vec::new();
        let upper_op = opcode.to_uppercase();
        let is_branch = upper_op.starts_with("B") && !upper_op.starts_with("BIT") && !upper_op.starts_with("BIC") && upper_op != "BKPT";

        if is_branch {
            // Handle direct branches with immediate target
            if let Some(Operand::Immediate(target)) = operands.first() {
                targets.push(*target);
            }
            // Handle indirect branches: BX rN or BLX rN
            else if opcode == "BX" || opcode == "BLX" {
                if let Some(Operand::Register(rn)) = operands.first() {
                    // Try to resolve the target from register tracker
                    if let Some(target) = self.register_tracker.get(*rn) {
                        targets.push(target);
                    }
                    // If we can't resolve it, we can't determine the target statically
                }
            }
        }

        targets
    }

    pub fn get_reachable_addresses(&self) -> &[u32] {
        &self.instruction_addresses
    }

    pub fn is_reachable(&self, addr: u32) -> bool {
        self.instruction_addresses.contains(&addr)
    }

    pub fn get_mode(&self, addr: u32) -> Option<ArmMode> {
        self.mode_map
            .binary_search_by_key(&addr, |(a, _)| *a)
            .ok()
            .map(|i| self.mode_map[i].1)
    }
}
