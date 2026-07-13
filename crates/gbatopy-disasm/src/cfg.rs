#![allow(dead_code, unused_variables, unused_mut)]
//! Control Flow Graph (CFG) builder for GBA ROM disassembly.
//!
//! This module implements reachable code analysis by performing a BFS traversal
//! from the entry point, following branch targets to discover all reachable code.

use crate::arm::ArmDecoder;
use crate::thumb::ThumbDecoder;
use crate::{AddressingMode, ArmMode, Operand};
use std::collections::{HashMap, HashSet};

/// Detects instructions that write to R15 (PC), making them indirect branches.
/// This covers LDM with R15 in register list (POP {PC}) — the instruction
/// loads PC from the stack, so execution does NOT fall through to the next
/// address. The CFG must not add the fall-through as reachable code.
pub fn writes_to_pc(opcode: &str, operands: &[Operand]) -> bool {
    if opcode.starts_with("LDM") {
        for op in operands {
            if let Operand::MemoryAddress {
                offset: AddressingMode::Multi { registers, .. },
                ..
            } = op
            {
                if registers.contains(&15) {
                    return true;
                }
            }
        }
    }
    false
}

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
        // BFS queue stores (address, mode) so we propagate the execution mode
        // instead of guessing from address parity. Thumb branch targets can be
        // even addresses, and the parity heuristic decodes them as ARM.
        let mut to_visit: Vec<(u32, ArmMode)> = vec![(entry_point, ArmMode::Arm)];

        let common_entry_points = [
            0x080000A0,
            0x08000100,
            0x08000200,
            0x08000300,
            0x08000400,
            0x08000500,
        ];

        for &addr in &common_entry_points {
            let rom_offset = (addr - 0x08000000) as usize;
            if rom_offset < rom.len() && !to_visit.iter().any(|(a, _)| *a == addr) {
                to_visit.push((addr, ArmMode::Arm));
            }
        }

        let arm_decoder = ArmDecoder::new();
        let thumb_decoder = ThumbDecoder::new();

        const MAX_INSTRUCTIONS: usize = 500_000;
        let mut instruction_count = 0;

        while let Some((addr, current_mode)) = to_visit.pop() {
            if visited.contains(&addr) {
                continue;
            }
            visited.insert(addr);

            instruction_count += 1;
            if instruction_count > MAX_INSTRUCTIONS {
                eprintln!("  CFG: safety limit reached, stopping");
                break;
            }

            if instruction_count % 100_000 == 0 {
                eprintln!("  CFG progress: {} visited, {} branch targets",
                          instruction_count, self.branch_targets.len());
            }

            let decode_addr = if current_mode == ArmMode::Thumb { addr & !1 } else { addr };
            if decode_addr < 0x08000000 {
                continue;
            }
            let rom_offset = (decode_addr - 0x08000000) as usize;
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
                    let (op, ops, thumb) = arm_decoder.decode(opcode, decode_addr);
                    (op, ops, thumb, 4)
                }
                ArmMode::Thumb => {
                    if rom_offset + 2 > rom.len() {
                        continue;
                    }
                    let opcode = u16::from_le_bytes([rom[rom_offset], rom[rom_offset + 1]]);
                    let (op, ops, thumb) = thumb_decoder.decode(opcode, decode_addr);
                    (op, ops, thumb, 2)
                }
            };

            self.instruction_addresses.push(addr);
            self.mode_map.push((addr, current_mode));

            self.track_register_values(&opcode_str, &operands, addr, current_mode);

            let targets = self.extract_branch_targets(&opcode_str, &operands);

            let instr_width = if current_mode == ArmMode::Thumb { 2 } else { 4 };

            let is_uncond_branch = opcode_str == "B"
                || opcode_str == "BX"
                || writes_to_pc(&opcode_str, &operands);

            if !is_uncond_branch {
                let next_addr = addr + instr_width;
                if !visited.contains(&next_addr)
                    && next_addr >= 0x08000000
                    && ((next_addr - 0x08000000) as usize) < rom.len()
                {
                    to_visit.push((next_addr, current_mode));
                }
            }

            for target in targets {
                if target < 0x08000000 || (target - 0x08000000) as usize >= rom.len() {
                    continue;
                }
                if !visited.contains(&target) {
                    let target_mode = if opcode_str == "BX" || opcode_str == "BLX" {
                        if target & 1 == 1 { ArmMode::Thumb } else { ArmMode::Arm }
                    } else {
                        current_mode
                    };
                    to_visit.push((target, target_mode));
                }
                if !self.branch_targets.contains(&target) {
                    self.branch_targets.push(target);
                }
            }

            if opcode_str == "BL" || opcode_str == "BLX" || opcode_str == "BL_SUFFIX" {
                self.register_tracker.invalidate_all();
            }

            // After a BL/BLX/BL_SUFFIX, set LR to the return address so that
            // BX LR at the end of the subroutine can be resolved by the CFG.
            // Thumb BL: LR = (addr + 2) | 1 (return addr with Thumb bit).
            // ARM BL/BLX: LR = addr + 4 (return addr, ARM mode — no Thumb bit).
            if opcode_str == "BL_SUFFIX" {
                self.register_tracker
                    .track_mov_immediate(14, (addr + 2) | 1);
            } else if opcode_str == "BL" || opcode_str == "BLX" {
                self.register_tracker
                    .track_mov_immediate(14, addr + 4);
            }
        }

        self.instruction_addresses.sort();
        self.branch_targets.sort();
        self.mode_map.sort_by_key(|(a, _)| *a);
    }

    /// Track register values for MOV rN, #imm, LDR rN, =imm, and
    /// ADD/SUB Rd, PC, #imm patterns (the ARM ADR pseudo-instruction and
    /// the standard ARM->Thumb switch idiom: ADD Rd, PC, #1; BX Rd).
    fn track_register_values(
        &mut self,
        opcode: &str,
        operands: &[Operand],
        addr: u32,
        mode: ArmMode,
    ) {
        // BL_PREFIX stores the upper target in LR (r14). BL_SUFFIX will add the
        // lower offset and branch to the combined address.
        if opcode == "BL_PREFIX" {
            if let Some(Operand::Immediate(target)) = operands.first() {
                self.register_tracker.track_mov_immediate(14, *target);
            }
            return;
        }

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
                    if imm >= 0x08000000 && imm < 0x0A000000 {
                        self.register_tracker.track_ldr_literal(rd, imm);
                    }
                }
            }
        }

        // ADD Rd, PC, #imm / SUB Rd, PC, #imm (ADR pseudo-instruction).
        // ARM pipeline: PC = current_instruction + 8.
        // Thumb pipeline: PC = current_instruction + 4.
        if (opcode.starts_with("ADD") || opcode.starts_with("SUB")) && operands.len() >= 3 {
            if let (Operand::Register(rd), Operand::Register(rn), Operand::Immediate(imm)) =
                (&operands[0], &operands[1], &operands[2])
            {
                if *rn == 15 {
                    let pipeline_pc = match mode {
                        ArmMode::Thumb => (addr & !1) + 4,
                        ArmMode::Arm => addr + 8,
                    };
                    let target = if opcode.starts_with("ADD") {
                        pipeline_pc.wrapping_add(*imm)
                    } else {
                        pipeline_pc.wrapping_sub(*imm)
                    };
                    self.register_tracker.track_mov_immediate(*rd, target);
                }
            }
        }
    }

    fn extract_branch_targets(&mut self, opcode: &str, operands: &[Operand]) -> Vec<u32> {
        let mut targets = Vec::new();
        let upper_op = opcode.to_uppercase();

        // BL_PREFIX just stores the upper target in LR — not a branch itself.
        // BL_SUFFIX combines LR (from BL_PREFIX) with the lower offset to form
        // the final BL target. Both must be excluded from the generic branch
        // check below, which would otherwise push garbage targets.
        if opcode == "BL_SUFFIX" {
            if let Some(Operand::Immediate(offset)) = operands.first() {
                if let Some(lr) = self.register_tracker.get(14) {
                    targets.push(lr.wrapping_add(*offset));
                }
            }
            return targets;
        }
        if opcode == "BL_PREFIX" {
            return targets;
        }

        let is_branch = upper_op.starts_with("B")
            && !upper_op.starts_with("BIT")
            && !upper_op.starts_with("BIC")
            && upper_op != "BKPT";

        if is_branch {
            if let Some(Operand::Immediate(target)) = operands.first() {
                targets.push(*target);
            } else if opcode == "BX" || opcode == "BLX" {
                if let Some(Operand::Register(rn)) = operands.first() {
                    if let Some(target) = self.register_tracker.get(*rn) {
                        targets.push(target);
                    }
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
