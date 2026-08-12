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

/// Detects LDR-Literal (PC-relative load) instructions and computes the
/// literal pool address they reference. The pool address must be marked as
/// data so the CFG builder does not decode it as an instruction.
fn literal_pool_addr(opcode: &str, operands: &[Operand], addr: u32, mode: ArmMode) -> Option<u32> {
    if !opcode.starts_with("LDR") {
        return None;
    }
    match mode {
        ArmMode::Thumb => {
            if operands.len() == 2 {
                if let Operand::Immediate(target) = &operands[1] {
                    return Some(*target);
                }
            }
            None
        }
        ArmMode::Arm => {
            if operands.len() >= 2 {
                if let Operand::MemoryAddress {
                    base: 15,
                    offset: AddressingMode::ImmediateOffset(off),
                    ..
                } = &operands[1]
                {
                    let pc = addr.wrapping_add(8);
                    let literal = pc.wrapping_add(*off as u32) & !3;
                    return Some(literal);
                }
            }
            None
        }
    }
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
    /// All (register, literal_value) pairs from LDR rN, =literal where the
    /// loaded value is a ROM address. Used by the post-processing sweep to
    /// resolve indirect branches that the context-insensitive tracker missed
    /// (e.g., a BX rN thunk called from multiple sites with different rN values).
    ldr_literals: Vec<(u8, u32)>,
    /// Registers used in BX/BLX instructions. The post-processing sweep adds
    /// all literal-pool values loaded into these registers as branch targets.
    bx_registers: HashSet<u8>,
}

impl CfgBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn build_from_entry(&mut self, rom: &[u8], entry_point: u32) {
        let mut visited: HashSet<(u32, ArmMode)> = HashSet::new();
        // BFS queue stores (address, mode) so we propagate the execution mode
        // instead of guessing from address parity. Thumb branch targets can be
        // even addresses, and the parity heuristic decodes them as ARM.
        //
        // The main entry point is pushed LAST so it is popped FIRST (LIFO).
        // This ensures addresses reachable from the entry point are visited with
        // the correct mode (propagated through BX/BLX) before the heuristic
        // common_entry_points can override them. Without this ordering, a
        // common_entry_point at 0x08000500 (ARM) would visit 0x08000504 in ARM
        // mode before the main BFS reaches it in Thumb mode via a BX.
        let mut to_visit: Vec<(u32, ArmMode)> = Vec::new();
        let mut data_addresses: HashSet<u32> = HashSet::new();

        let common_entry_points = [
            0x080000C0,
        ];

        for &addr in &common_entry_points {
            let rom_offset = (addr - 0x08000000) as usize;
            if rom_offset < rom.len() {
                // Visit in both ARM and Thumb mode. The visited set tracks
                // (addr, mode) pairs, so there is no collision. Many GBA ROMs
                // interleave ARM and Thumb code at these addresses, and visiting
                // only ARM mode causes the Thumb decoder to miss entire
                // functions that are only reachable via BL from Thumb code.
                to_visit.push((addr, ArmMode::Arm));
                to_visit.push((addr, ArmMode::Thumb));
            }
        }
        to_visit.push((entry_point, ArmMode::Arm));

        let arm_decoder = ArmDecoder::new();
        let thumb_decoder = ThumbDecoder::new();

        const MAX_INSTRUCTIONS: usize = 500_000;
        let mut instruction_count = 0;

        while let Some((addr, current_mode)) = to_visit.pop() {
            if data_addresses.contains(&addr) {
                continue;
            }
            if visited.contains(&(addr, current_mode)) {
                continue;
            }
            visited.insert((addr, current_mode));

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

            // Stop walking when we hit data that doesn't decode as valid instructions
            if opcode_str.starts_with("UNKNOWN") || opcode_str == "UNDEFINED" {
                continue;
            }

            if let Some(pool_addr) = literal_pool_addr(&opcode_str, &operands, addr, current_mode) {
                data_addresses.insert(pool_addr);
            }

            self.instruction_addresses.push(addr);
            self.mode_map.push((addr, current_mode));

            // Extract branch targets BEFORE track_register_values, because
            // track_register_values invalidates LR for BL_SUFFIX and replaces
            // it with the return address. extract_branch_targets needs the old
            // LR (set by BL_PREFIX) to compute the BL target.
            let targets = self.extract_branch_targets(&opcode_str, &operands, addr);

            self.track_register_values(&opcode_str, &operands, addr, current_mode, rom);

            let instr_width = if current_mode == ArmMode::Thumb { 2 } else { 4 };

            let is_uncond_branch = opcode_str == "B"
                || opcode_str == "BX"
                || writes_to_pc(&opcode_str, &operands);

            if !is_uncond_branch {
                let next_addr = addr + instr_width;
                if !visited.contains(&(next_addr, current_mode))
                    && !data_addresses.contains(&next_addr)
                    && next_addr >= 0x08000000
                    && ((next_addr - 0x08000000) as usize) < rom.len()
                {
                    to_visit.push((next_addr, current_mode));
                }
            }

            for raw_target in targets {
                if raw_target < 0x08000000 || (raw_target - 0x08000000) as usize >= rom.len() {
                    continue;
                }
                let target_mode = if opcode_str == "BX" || opcode_str == "BLX" {
                    if raw_target & 1 == 1 { ArmMode::Thumb } else { ArmMode::Arm }
                } else {
                    current_mode
                };
                // Normalize: clear the mode-encoding bit(s) so blocks are recorded
                // at the actual instruction address, not the Thumb-bit-set target.
                // Without this, both 0x...66 and 0x...67 become separate blocks and
                // the dispatch table collides (idx = addr>>1 is identical for both).
                let target = if target_mode == ArmMode::Thumb {
                    raw_target & !1
                } else {
                    raw_target & !3
                };
                if !visited.contains(&(target, target_mode))
                    && !data_addresses.contains(&target)
                {
                    to_visit.push((target, target_mode));
                }
                if !self.branch_targets.contains(&target) {
                    self.branch_targets.push(target);
                }
            }

            // Note: we deliberately do NOT invalidate tracked registers after
            // BL/BLX/BL_SUFFIX. While the called function may clobber caller-
            // saved registers (r0-r3, r12), invalidating would lose branch-
            // target resolution for patterns like:
            //   LDR r3, =func_ptr
            //   BL some_function
            //   BX r3          ← r3 lost if we invalidated
            // Completeness (no missing dispatch entries) matters more than
            // soundness here — a wrong tracked value adds dead code at worst,
            // but a missing target crashes the runtime with "Unknown PC".

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

        // Post-processing sweep: resolve indirect branches that the context-
        // insensitive tracker missed. When a BX rN thunk is called from
        // multiple call sites with different rN values, the main pass only
        // visits the thunk once and resolves rN to a single value. This sweep
        // adds all literal-pool values loaded into BX-target registers as
        // branch targets, ensuring no indirect-branch destination is missing.
        let mut new_targets: Vec<(u32, ArmMode)> = Vec::new();
        for (rn, value) in &self.ldr_literals {
            if !self.bx_registers.contains(rn) {
                continue;
            }
            // Normalize Thumb-bit: the literal may have bit 0 set.
            let target = if value & 1 == 1 {
                (*value & !1, ArmMode::Thumb)
            } else if value & 3 != 0 {
                // Unaligned ARM literal — treat as Thumb.
                (*value & !1, ArmMode::Thumb)
            } else {
                (*value, ArmMode::Arm)
            };
            let (taddr, tmode) = target;
            if taddr < 0x08000000 || (taddr - 0x08000000) as usize >= rom.len() {
                continue;
            }
            if !self.branch_targets.contains(&taddr) {
                self.branch_targets.push(taddr);
                new_targets.push((taddr, tmode));
            }
        }

        // If new targets were discovered, run a mini-CFG pass from them to
        // collect their instruction addresses and any further branches.
        if !new_targets.is_empty() {
            let mut mini_visited: HashSet<(u32, ArmMode)> = HashSet::new();
            let mut mini_queue: Vec<(u32, ArmMode)> = new_targets;
            while let Some((addr, current_mode)) = mini_queue.pop() {
                if data_addresses.contains(&addr) {
                    continue;
                }
                if mini_visited.contains(&(addr, current_mode)) || visited.contains(&(addr, current_mode)) {
                    continue;
                }
                visited.insert((addr, current_mode));

                let decode_addr = if current_mode == ArmMode::Thumb { addr & !1 } else { addr };
                if decode_addr < 0x08000000 {
                    continue;
                }
                let rom_offset = (decode_addr - 0x08000000) as usize;
                if rom_offset >= rom.len() {
                    continue;
                }

                let (opcode_str, operands, instr_width) = match current_mode {
                    ArmMode::Arm => {
                        if rom_offset + 4 > rom.len() { continue; }
                        let opcode = u32::from_le_bytes([
                            rom[rom_offset], rom[rom_offset + 1],
                            rom[rom_offset + 2], rom[rom_offset + 3],
                        ]);
                        let (op, ops, _) = arm_decoder.decode(opcode, decode_addr);
                        (op, ops, 4)
                    }
                    ArmMode::Thumb => {
                        if rom_offset + 2 > rom.len() { continue; }
                        let opcode = u16::from_le_bytes([rom[rom_offset], rom[rom_offset + 1]]);
                        let (op, ops, _) = thumb_decoder.decode(opcode, decode_addr);
                        (op, ops, 2)
                    }
                };

                if let Some(pool_addr) = literal_pool_addr(&opcode_str, &operands, addr, current_mode) {
                    data_addresses.insert(pool_addr);
                }

                self.instruction_addresses.push(addr);
                self.mode_map.push((addr, current_mode));

                let targets = self.extract_branch_targets(&opcode_str, &operands, addr);
                self.track_register_values(&opcode_str, &operands, addr, current_mode, rom);

                let is_uncond_branch = opcode_str == "B"
                    || opcode_str == "BX"
                    || writes_to_pc(&opcode_str, &operands);

                if !is_uncond_branch {
                    let next_addr = addr + instr_width;
                    if !mini_visited.contains(&(next_addr, current_mode))
                        && !visited.contains(&(next_addr, current_mode))
                        && !data_addresses.contains(&next_addr)
                        && next_addr >= 0x08000000
                        && ((next_addr - 0x08000000) as usize) < rom.len()
                    {
                        mini_queue.push((next_addr, current_mode));
                    }
                }

                for raw_target in targets {
                    if raw_target < 0x08000000 || (raw_target - 0x08000000) as usize >= rom.len() {
                        continue;
                    }
                    let target_mode = if opcode_str == "BX" || opcode_str == "BLX" {
                        if raw_target & 1 == 1 { ArmMode::Thumb } else { ArmMode::Arm }
                    } else {
                        current_mode
                    };
                    let target = if target_mode == ArmMode::Thumb {
                        raw_target & !1
                    } else {
                        raw_target & !3
                    };
                    if !mini_visited.contains(&(target, target_mode))
                        && !visited.contains(&(target, target_mode))
                        && !data_addresses.contains(&target)
                    {
                        mini_queue.push((target, target_mode));
                    }
                    if !self.branch_targets.contains(&target) {
                        self.branch_targets.push(target);
                    }
                }

                if opcode_str == "BL_SUFFIX" {
                    self.register_tracker.track_mov_immediate(14, (addr + 2) | 1);
                } else if opcode_str == "BL" || opcode_str == "BLX" {
                    self.register_tracker.track_mov_immediate(14, addr + 4);
                }
            }
        }

        // ROM-wide function pointer scan: use already-resolved LDR literal values.
        // The LDR rN, =literal handler (line 606-631) already resolves two-level
        // indirection by reading the function pointer from the literal pool.
        // This scan just adds those resolved pointers as branch targets without
        // the brute-force ROM scan that caused OOM on large ROMs.
        let mut rom_wide_targets: Vec<(u32, ArmMode)> = Vec::new();
        let size_guard_limit = 5000;
        
        for (_, func_ptr) in &self.ldr_literals {
            // Size guard: stop if we've discovered too many targets
            if rom_wide_targets.len() >= size_guard_limit {
                eprintln!("[CFG] Size guard triggered: {} rom-wide targets, stopping scan", size_guard_limit);
                break;
            }
            
            let value = *func_ptr;
            
            // Determine target address and mode from the function pointer
            let (taddr, tmode) = if value & 1 == 1 {
                (value & !1, ArmMode::Thumb)
            } else if value & 3 == 0 {
                (value, ArmMode::Arm)
            } else {
                (value & !1, ArmMode::Thumb)
            };
            
            if taddr < 0x08000000 || (taddr - 0x08000000) as usize >= rom.len() {
                continue;
            }
            
            if !visited.contains(&(taddr, tmode))
                && !self.branch_targets.contains(&taddr)
            {
                self.branch_targets.push(taddr);
                rom_wide_targets.push((taddr, tmode));
            }
        }

        // Run mini-CFG pass on newly discovered targets, same as above
        if !rom_wide_targets.is_empty() {
            let mut mini2_visited: HashSet<(u32, ArmMode)> = HashSet::new();
            let mut mini2_queue: Vec<(u32, ArmMode)> = rom_wide_targets;
            while let Some((addr, current_mode)) = mini2_queue.pop() {
                if data_addresses.contains(&addr) {
                    continue;
                }
                if mini2_visited.contains(&(addr, current_mode))
                    || visited.contains(&(addr, current_mode))
                {
                    continue;
                }
                mini2_visited.insert((addr, current_mode));

                let decode_addr = if current_mode == ArmMode::Thumb { addr & !1 } else { addr };
                if decode_addr < 0x08000000 {
                    continue;
                }
                let rom_offset = (decode_addr - 0x08000000) as usize;
                if rom_offset >= rom.len() {
                    continue;
                }

                let (opcode_str, operands, instr_width) = match current_mode {
                    ArmMode::Arm => {
                        if rom_offset + 4 > rom.len() { continue; }
                        let opcode = u32::from_le_bytes([
                            rom[rom_offset], rom[rom_offset + 1],
                            rom[rom_offset + 2], rom[rom_offset + 3],
                        ]);
                        let (op, ops, _) = arm_decoder.decode(opcode, decode_addr);
                        (op, ops, 4)
                    }
                    ArmMode::Thumb => {
                        if rom_offset + 2 > rom.len() { continue; }
                        let opcode = u16::from_le_bytes([rom[rom_offset], rom[rom_offset + 1]]);
                        let (op, ops, _) = thumb_decoder.decode(opcode, decode_addr);
                        (op, ops, 2)
                    }
                };

                if let Some(pool_addr) = literal_pool_addr(&opcode_str, &operands, addr, current_mode) {
                    data_addresses.insert(pool_addr);
                }

                self.instruction_addresses.push(addr);
                self.mode_map.push((addr, current_mode));

                let targets = self.extract_branch_targets(&opcode_str, &operands, addr);
                self.track_register_values(&opcode_str, &operands, addr, current_mode, rom);

                let is_uncond_branch = opcode_str == "B"
                    || opcode_str == "BX"
                    || writes_to_pc(&opcode_str, &operands);

                if !is_uncond_branch {
                    let next_addr = addr + instr_width;
                    if !mini2_visited.contains(&(next_addr, current_mode))
                        && !visited.contains(&(next_addr, current_mode))
                        && !data_addresses.contains(&next_addr)
                        && next_addr >= 0x08000000
                        && ((next_addr - 0x08000000) as usize) < rom.len()
                    {
                        mini2_queue.push((next_addr, current_mode));
                    }
                }

                for raw_target in targets {
                    if raw_target < 0x08000000 || (raw_target - 0x08000000) as usize >= rom.len() {
                        continue;
                    }
                    let target_mode = if opcode_str == "BX" || opcode_str == "BLX" {
                        if raw_target & 1 == 1 { ArmMode::Thumb } else { ArmMode::Arm }
                    } else {
                        current_mode
                    };
                    let target = if target_mode == ArmMode::Thumb {
                        raw_target & !1
                    } else {
                        raw_target & !3
                    };
                    if !mini2_visited.contains(&(target, target_mode))
                        && !visited.contains(&(target, target_mode))
                        && !data_addresses.contains(&target)
                    {
                        mini2_queue.push((target, target_mode));
                    }
                    if !self.branch_targets.contains(&target) {
                        self.branch_targets.push(target);
                    }
                }

                if opcode_str == "BL_SUFFIX" {
                    self.register_tracker.track_mov_immediate(14, (addr + 2) | 1);
                } else if opcode_str == "BL" || opcode_str == "BLX" {
                    self.register_tracker.track_mov_immediate(14, addr + 4);
                }
            }
        }

        self.instruction_addresses.sort();
        self.branch_targets.sort();
        self.mode_map.sort_by_key(|(a, _)| *a);
        self.mode_map.dedup();
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
        rom: &[u8],
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
                        let rom_offset = (imm - 0x08000000) as usize;
                        if rom_offset + 4 <= rom.len() {
                            let value = u32::from_le_bytes([
                                rom[rom_offset],
                                rom[rom_offset + 1],
                                rom[rom_offset + 2],
                                rom[rom_offset + 3],
                            ]);
                            self.register_tracker.track_mov_immediate(rd, value);
                            // Collect for the post-processing sweep: this pair
                            // may resolve an indirect branch that the context-
                            // insensitive tracker can't follow (BX thunk called
                            // from multiple sites with different rN values).
                            if value >= 0x08000000 && value < 0x0A000000 {
                                self.ldr_literals.push((rd, value));
                            }
                        }
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

    fn extract_branch_targets(&mut self, opcode: &str, operands: &[Operand], addr: u32) -> Vec<u32> {
        let mut targets = Vec::new();
        let upper_op = opcode.to_uppercase();

        // BL_PREFIX just stores the upper target in LR — not a branch itself.
        // BL_SUFFIX combines LR (from BL_PREFIX) with the lower offset to form
        // the final BL target. Both must be excluded from the generic branch
        // check below, which would otherwise push garbage targets.
        if opcode == "BL_SUFFIX" {
            if let Some(Operand::Immediate(offset)) = operands.first() {
                if let Some(lr) = self.register_tracker.get(14) {
                    let target = lr.wrapping_add(*offset);
                    targets.push(target);
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
                    // Record this register for the post-processing sweep.
                    self.bx_registers.insert(*rn);
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
