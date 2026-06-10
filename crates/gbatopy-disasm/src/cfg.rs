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
        let mut current_mode = if entry_point % 2 == 1 { ArmMode::Thumb } else { ArmMode::Arm };
        let arm_decoder = ArmDecoder::new();
        let thumb_decoder = ThumbDecoder::new();

        while let Some(addr) = to_visit.pop() {
            if visited.contains(&addr) {
                continue;
            }
            visited.insert(addr);

            let rom_offset = (addr - 0x08000000) as usize;
            if rom_offset >= rom.len() {
                continue;
            }

            let (opcode_str, operands, is_thumb) = match current_mode {
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
                    arm_decoder.decode(opcode, addr)
                }
                ArmMode::Thumb => {
                    if rom_offset + 2 > rom.len() {
                        continue;
                    }
                    let opcode = u16::from_le_bytes([rom[rom_offset], rom[rom_offset + 1]]);
                    thumb_decoder.decode(opcode, addr)
                }
            };

            self.instruction_addresses.push(addr);
            self.mode_map.push((addr, current_mode));

            // Track register values for indirect jump resolution
            self.track_register_values(&opcode_str, &operands);

            let targets = self.extract_branch_targets(&opcode_str, &operands);
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

            if is_thumb {
                current_mode = ArmMode::Thumb;
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
        let is_branch = matches!(opcode, "B" | "BEQ" | "BNE" | "BCC" | "BCS" | "BVS" | "BVC" | "BHI" | "BLS" | "BGE" | "BLT" | "BGT" | "BLE" | "BL" | "BLX" | "BX");

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
