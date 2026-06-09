//! Control Flow Graph (CFG) builder for GBA ROM disassembly.
//!
//! This module implements reachable code analysis by building a CFG starting
//! from the entry point and following all branch instructions.

use crate::{ArmMode, Operand};
use std::collections::HashSet;

/// Control Flow Graph builder
#[derive(Debug, Default)]
pub struct CfgBuilder {
    /// All discovered instruction addresses
    pub instruction_addresses: Vec<u32>,
    /// Set of branch targets (addresses that are jump targets)
    pub branch_targets: Vec<u32>,
    /// ARM/Thumb mode at each address
    pub mode_map: Vec<(u32, ArmMode)>,
}

impl CfgBuilder {
    /// Create a new CFG builder
    pub fn new() -> Self {
        Self::default()
    }

    /// Build CFG from entry point using BFS
    pub fn build_from_entry(&mut self, rom: &[u8], entry_point: u32) {
        let mut visited: HashSet<u32> = HashSet::new();
        let mut to_visit = vec![entry_point];
        let mut current_mode = ArmMode::Arm;
        let arm_decoder = crate::arm::ArmDecoder::new();
        let thumb_decoder = crate::thumb::ThumbDecoder::new();

        while let Some(addr) = to_visit.pop() {
            if visited.contains(&addr) {
                continue;
            }
            visited.insert(addr);

            let rom_offset = (addr - 0x08000000) as usize;
            
            // Check bounds
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

            // Check for branch instructions and extract targets
            let targets = self.extract_branch_targets(&opcode_str, &operands, addr);
            for target in targets {
                if !visited.contains(&target) {
                    to_visit.push(target);
                }
                if !self.branch_targets.contains(&target) {
                    self.branch_targets.push(target);
                }
            }

            // Update mode if Thumb
            if is_thumb {
                current_mode = ArmMode::Thumb;
            }
        }

        self.instruction_addresses.sort();
        self.branch_targets.sort();
        self.mode_map.sort_by_key(|(a, _)| *a);
    }

    fn extract_branch_targets(&self, opcode: &str, operands: &[Operand], _current_addr: u32) -> Vec<u32> {
        let mut targets = Vec::new();

        // Check for branch instructions
        let is_branch = matches!(
            opcode,
            "B" | "BEQ" | "BNE" | "BCC" | "BCS" | "BVS" | "BVC" | "BHI" | "BLS" | 
            "BGE" | "BLT" | "BGT" | "BLE" | "BL" | "BLX" | "BX"
        );

        if is_branch {
            // For direct branches with immediate offset (B, BL with label)
            if let Some(Operand::Immediate(target)) = operands.first() {
                targets.push(*target);
            }
            // For BX/BLX with register (indirect jump) - we can't resolve statically
            // but we mark it as a potential branch target for data protection
            // TODO: Implement register value tracking for indirect jump resolution
            if (opcode == "BX" || opcode == "BLX") && operands.first().is_some() {
                // Indirect branch - target unknown at compile time
                // We'll protect all potential code regions as a fallback
            }
        }

        targets
    }

    /// Get all reachable instruction addresses
    pub fn get_reachable_addresses(&self) -> &[u32] {
        &self.instruction_addresses
    }

    /// Check if an address is reachable
    pub fn is_reachable(&self, addr: u32) -> bool {
        self.instruction_addresses.contains(&addr)
    }

    /// Get the mode (ARM/Thumb) at a given address
    pub fn get_mode(&self, addr: u32) -> Option<ArmMode> {
        self.mode_map
            .binary_search_by_key(&addr, |(a, _)| *a)
            .ok()
            .map(|i| self.mode_map[i].1)
    }
}
