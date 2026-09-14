#![allow(unused_variables, unused_mut)]
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

/// Decodes the word/halfword at `addr` and returns false if it does not look
/// like valid code. Data constants (palette tables, struct pointers, tile
/// data) frequently decode as UNKNOWN/UNDEFINED; filtering them out prevents
/// the CFG sweeps from inflating the dispatch table with non-code addresses.
fn decode_is_valid_code(
    rom: &[u8],
    addr: u32,
    mode: ArmMode,
    arm_decoder: &ArmDecoder,
    thumb_decoder: &ThumbDecoder,
) -> bool {
    if addr < 0x08000000 {
        return false;
    }
    let rom_offset = (addr - 0x08000000) as usize;
    if rom_offset >= rom.len() {
        return false;
    }
    let opcode_str: String = match mode {
        ArmMode::Arm => {
            if rom_offset + 4 > rom.len() {
                return false;
            }
            let word = u32::from_le_bytes([
                rom[rom_offset],
                rom[rom_offset + 1],
                rom[rom_offset + 2],
                rom[rom_offset + 3],
            ]);
            arm_decoder.decode(word, addr).0
        }
        ArmMode::Thumb => {
            if rom_offset + 2 > rom.len() {
                return false;
            }
            let halfword = u16::from_le_bytes([rom[rom_offset], rom[rom_offset + 1]]);
            thumb_decoder.decode(halfword, addr).0
        }
    };
    !opcode_str.starts_with("UNKNOWN") && opcode_str != "UNDEFINED"
}

/// Requires a run of `min_run` consecutive valid decodes starting at `addr`.
/// Single-instruction validation admits audio/graphic data because Thumb
/// decoders are permissive; a run filter rejects data that decodes as one or
/// two valid halfwords but breaks down shortly after. Real code has long
/// valid runs.
fn decode_is_valid_code_run(
    rom: &[u8],
    addr: u32,
    mode: ArmMode,
    min_run: usize,
    arm_decoder: &ArmDecoder,
    thumb_decoder: &ThumbDecoder,
) -> bool {
    let stride = match mode {
        ArmMode::Arm => 4,
        ArmMode::Thumb => 2,
    };
    for i in 0..min_run {
        let probe = addr + (i * stride) as u32;
        if !decode_is_valid_code(rom, probe, mode, arm_decoder, thumb_decoder) {
            return false;
        }
    }
    true
}

/// Returns true if `addr` should be treated as data (not code).
/// An address marked as data by `literal_pool_addr` is re-validated:
/// if the bytes at `addr` decode as a valid code run of length
/// `SOFT_HINT_MIN_RUN`, the address is treated as code. This prevents
/// literal-pool false positives (e.g. CRT0 startup code at 0x08000150)
/// from blocking BFS fall-through and branch-target discovery.
fn is_data_address(
    addr: u32,
    mode: ArmMode,
    data_addresses: &HashSet<u32>,
    rom: &[u8],
    arm_decoder: &ArmDecoder,
    thumb_decoder: &ThumbDecoder,
) -> bool {
    if !data_addresses.contains(&addr) {
        return false;
    }
    const SOFT_HINT_MIN_RUN: usize = 32;
    !decode_is_valid_code_run(rom, addr, mode, SOFT_HINT_MIN_RUN, arm_decoder, thumb_decoder)
}

/// Detects long runs of zero bytes, which are common in data sections
/// (padding, uninitialized data) but rare in executable code.
fn has_long_zero_run(rom: &[u8], addr: u32, min_run: usize) -> bool {
    let rom_offset = (addr - 0x08000000) as usize;
    if rom_offset + min_run > rom.len() {
        return false;
    }
    let mut zero_count = 0;
    for &byte in &rom[rom_offset..rom_offset + min_run] {
        if byte == 0 {
            zero_count += 1;
            if zero_count >= min_run {
                return true;
            }
        } else {
            zero_count = 0;
        }
    }
    false
}

/// Detects repeated byte patterns, which are common in audio/graphics data
/// but rare in executable code. Code typically has high entropy.
fn has_repeated_pattern(rom: &[u8], addr: u32) -> bool {
    let rom_offset = (addr - 0x08000000) as usize;
    if rom_offset + 64 > rom.len() {
        return false;
    }
    
    // Check for 4-byte repeating patterns over 32 bytes
    // This catches audio samples, tile data, palette repeats
    const PATTERN_SIZE: usize = 4;
    const PATTERN_REPEAT_COUNT: usize = 8;  // 8 repeats = 32 bytes
    
    for start in 0..16 {
        let mut matches = 0;
        for i in 0..PATTERN_REPEAT_COUNT {
            let offset1 = rom_offset + start + i * PATTERN_SIZE;
            let offset2 = rom_offset + start + (i + 1) * PATTERN_SIZE;
            if offset2 + PATTERN_SIZE > rom.len() {
                break;
            }
            if rom[offset1..offset1 + PATTERN_SIZE] == rom[offset2..offset2 + PATTERN_SIZE] {
                matches += 1;
            }
        }
        if matches >= PATTERN_REPEAT_COUNT - 2 {
            return true;
        }
    }
    false
}

/// Soft-hint data filter: decodes a run of instructions at `addr` and returns
/// true if the bytes do NOT look like valid code. This catches binary data
/// regions (audio samples, graphics tiles) that the ASCII heuristic misses.
/// Real code must decode as valid instructions for a minimum run length.
fn looks_like_data_soft(
    rom: &[u8],
    addr: u32,
    mode: ArmMode,
    arm_decoder: &ArmDecoder,
    thumb_decoder: &ThumbDecoder,
) -> bool {
    let rom_offset = (addr - 0x08000000) as usize;
    if rom_offset + 64 > rom.len() {
        return false;  // Out of bounds — treat as code to avoid blocking BFS
    }
    
    // New heuristics: check for data patterns BEFORE decoding
    // These catch audio/graphics data that decodes as valid Thumb instructions
    if has_long_zero_run(rom, addr, 16) {
        return true;
    }
    if has_repeated_pattern(rom, addr) {
        return true;
    }
    
    const SOFT_HINT_MIN_RUN: usize = 32;
    let valid_run = decode_is_valid_code_run(rom, addr, mode, SOFT_HINT_MIN_RUN, arm_decoder, thumb_decoder);
    !valid_run
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
    pub branch_targets: HashSet<u32>,
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
                // Only visit in ARM mode. The GBA entry is ARM; mode transitions
                // happen via BX which BFS already handles. Dual-mode entry created
                // phantom Thumb paths through ARM code at common_entry_points.
                to_visit.push((addr, ArmMode::Arm));
            }
        }
        to_visit.push((entry_point, ArmMode::Arm));

        let arm_decoder = ArmDecoder::new();
        let thumb_decoder = ThumbDecoder::new();

        const MAX_INSTRUCTIONS: usize = 500_000;

        // TEMP: check data_addresses for 0x080000C8
        eprintln!("DATA_CHECK: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8u32));
        eprintln!("DATA_CHECK: data_addresses has {} entries", data_addresses.len());
        // Print all entries near 0x080000C0-0x080000D0
        for a in &data_addresses {
            if *a >= 0x080000C0 && *a <= 0x080000D0 {
                eprintln!("DATA_CHECK: found entry 0x{:08X}", a);
            }
        }

        // Main BFS pass
        eprintln!("  CFG: main pass starting...");
        eprintln!("PRE_BFS: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        let main_count = self.bfs_pass(
            &mut to_visit,
            &mut visited,
            None,  // No shared visited set for main pass
            &mut data_addresses,
            rom,
            &arm_decoder,
            &thumb_decoder,
            MAX_INSTRUCTIONS,
            "main pass",
            true,  // Report progress for main pass
        );
        eprintln!("  CFG: main pass complete, {} instructions visited", main_count);

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
            let target_addr = *value & !1;  // Clear bit 0 for the actual address
            if target_addr < 0x08000000 || (target_addr - 0x08000000) as usize >= rom.len() {
                continue;
            }
            // The Thumb bit (bit 0 of the literal value) selects the target mode:
            // bit 0 set → Thumb, bit 0 clear → ARM. Use it instead of adding to both.
            let tmode = if *value & 1 == 1 { ArmMode::Thumb } else { ArmMode::Arm };
            if !decode_is_valid_code(rom, target_addr, tmode, &arm_decoder, &thumb_decoder) {
                continue;
            }
            if self.branch_targets.insert(target_addr) {
                new_targets.push((target_addr, tmode));
            }
        }

        // If new targets were discovered, run a mini-CFG pass from them to
        // collect their instruction addresses and any further branches.
        if !new_targets.is_empty() {
            let mut mini_visited: HashSet<(u32, ArmMode)> = HashSet::new();
            let mut mini_queue: Vec<(u32, ArmMode)> = new_targets;
            const MINI_MAX_INSTRUCTIONS: usize = 200_000;
            let mini_count = self.bfs_pass(
                &mut mini_queue,
                &mut mini_visited,
                Some(&visited),  // Shared visited set
                &mut data_addresses,
                rom,
                &arm_decoder,
                &thumb_decoder,
                MINI_MAX_INSTRUCTIONS,
                "mini-pass",
                false,  // No progress reporting for mini-pass
            );
            eprintln!("  CFG: mini-pass complete, {} instructions visited", mini_count);
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
            
            // LDR-literal targets are already call-confirmed: one valid decode
            // suffices because the code explicitly loaded this address.
            if !decode_is_valid_code(rom, taddr, tmode, &arm_decoder, &thumb_decoder) {
    eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
    eprintln!("AFTER_SCAN: data_addresses size={}", data_addresses.len());
                continue;
            }
    // TEMP DEBUG: check data_addresses for 0x080000C8
    eprintln!("DATA_DEBUG: total data_addresses={} contains_C8={}",
        data_addresses.len(),
        data_addresses.contains(&0x080000C8));
    if data_addresses.contains(&0x080000C8) {
        eprintln!("DATA_DEBUG: 0x080000C8 IS in data_addresses!");
    }
            
            if !visited.contains(&(taddr, tmode))
                && self.branch_targets.insert(taddr)
            {
                rom_wide_targets.push((taddr, tmode));
            }
        }
        
        // Special scan: look for literal pool entries that point to IWRAM addresses.
        // These are likely vector table entries (IRQ, VBlank, etc.) that store handler
        // addresses. When we find such a literal, check if the value stored at that
        // IWRAM address is a code address (handler entry point).
        //
        // This handles the case where the ROM does:
        //   LDR R0, =0x03007FFC    ; Load IRQ vector address
        //   LDR R1, =handler_addr  ; Load handler address  
        //   STR R1, [R0]           ; Store handler to IRQ vector
        //
        // The handler_addr is in the literal pool and should be discovered.
        for (rn, imm) in &self.ldr_literals {
            let value = *imm;
            
            // Check if this loads an IWRAM address in the vector table range
            const IRQ_VECTOR: u32 = 0x03007FFC;
            const VBLANK_VECTOR: u32 = 0x03007FF8;
            const VCOUNT_VECTOR: u32 = 0x03007FF4;
            
            let is_vector_addr = value == IRQ_VECTOR || value == VBLANK_VECTOR || value == VCOUNT_VECTOR;
            
            if is_vector_addr {
                // This is a register holding a vector table address.
                // We can't directly read the handler from IWRAM at transpile time,
                // but we can mark this register for later detection of STR instructions.
                // The STR detection code above (in track_register_values) handles this.
            }
        }
        
        // Final sweep: scan the entire ROM for word values that look like code addresses
        // and add them as branch targets if they decode as valid code.
        // This catches interrupt handlers and other entry points that are stored in
        // literal pools but not dynamically loaded by reachable code.
        //
        // Requires a run of consecutive valid decodes at each seed. Single-instruction
        // validation admits audio/graphic data because Thumb decoders are permissive;
        // a run filter rejects data that decodes as one or two valid halfwords but
        // breaks down shortly after. Real code has long valid runs.
        
        // Saturation check: skip ROM scan if BFS already found enough code
        let mut rom_scan_targets: Vec<(u32, ArmMode)> = Vec::new();
        // ROM-wide brute-force scan DISABLED - it misclassifies audio/graphics data
        // as code, causing CFG explosion (42K+ addresses, 610K lines output).
        // The main BFS pass, ldr_literals resolution, heuristic scan, and IWRAM
        // pass are sufficient to discover all reachable code.
        eprintln!("  CFG: ROM-wide brute-force scan disabled (prevents CFG explosion)");
        
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        // Conservative scan for indirect branch targets.
        // Indirect branches (BX Rn) can jump to any address. This scan:
        // 1. Looks at LDR literal values that are loaded into BX registers
        // 2. Does a limited brute-force scan for valid Thumb code at odd-aligned addresses
        // Uses bit 0 for mode selection: value & 1 == 1 → Thumb, value & 0 == 0 → ARM.
        eprintln!("AFTER_LDR_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8u32));
        eprintln!("  CFG: scanning for indirect branch targets...");
        let mut indirect_targets: Vec<(u32, ArmMode)> = Vec::new();
        const INDIRECT_TARGET_LIMIT: usize = 20_000;
        
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={} data_addresses_len={}", data_addresses.contains(&0x080000C8), data_addresses.len());
        // Pass 1: Look at LDR literal values for BX registers
        for (rn, value) in &self.ldr_literals {
            // Size guard
            if indirect_targets.len() >= INDIRECT_TARGET_LIMIT {
                eprintln!("  CFG: indirect target limit reached ({}), stopping scan", INDIRECT_TARGET_LIMIT);
                break;
            }
            
            // Skip if not a BX register
            if !self.bx_registers.contains(rn) {
                continue;
            }
            
            // Normalize: clear bit 0 for address, use bit 0 for mode selection
            let target_addr = value & !1;
            let target_mode = if value & 1 == 1 { ArmMode::Thumb } else { ArmMode::Arm };
            
            // Conservative check: only add if in ROM or IWRAM range
            let in_rom = (0x08000000..=0x08FFFFFF).contains(&target_addr);
            let in_iwram = (0x03000000..=0x03007FFF).contains(&target_addr);
            if !in_rom && !in_iwram {
                continue;
            }
            
            // Skip if already discovered
            if self.branch_targets.contains(&target_addr) || self.instruction_addresses.contains(&target_addr) {
                continue;
            }
            
            // Validate as code in the selected mode
            if !decode_is_valid_code(rom, target_addr, target_mode, &arm_decoder, &thumb_decoder) {
                continue;
            }
            
            indirect_targets.push((target_addr, target_mode));
            self.branch_targets.insert(target_addr);
        }
        
        // Pass 2: Limited brute-force scan for valid Thumb code at odd-aligned addresses
        // This catches targets that are not loaded via LDR literals
        // Conservative: only scan a small range and require strong code heuristics
        eprintln!("  CFG: scanning odd-aligned addresses for Thumb code...");
        let mut scan_count = 0;
        for addr in (0x08000001..0x08010000).step_by(2) {
            scan_count += 1;
            if scan_count == 133 || scan_count == 207 {
            }
            if indirect_targets.len() >= 500 {  // Stricter limit
                eprintln!("  CFG: indirect target limit reached ({}), stopping scan after checking {} addresses", indirect_targets.len(), scan_count);
                break;
            }
            
            let offset = (addr - 0x08000000) as usize;
            if offset + 4 > rom.len() {
                continue;
            }
            
            // Skip if already discovered
            let already_discovered = self.branch_targets.contains(&addr) || self.instruction_addresses.contains(&addr);
            if already_discovered {
                continue;
            }
            
            // Quick heuristic: check if first halfword looks like valid Thumb code
            let halfword = u16::from_le_bytes([rom[offset], rom[offset + 1]]);
            if halfword == 0 || halfword == 0xFFFF {
                continue;
            }
            
            // Stronger heuristic: require at least one of these patterns:
            // - Branch/BL instruction (indicates function start)
            // - LDR PC-rel (indicates code using literals)
            // - PUSH/POP (indicates function prologue/epilogue)
            // - Common ALU ops (MOV, ADD, etc. - indicates active code)
            // Note: halfword is already in little-endian (from u16::from_le_bytes)
            let hw_high = (halfword >> 8) as u8;
            let has_branch_pattern = (0xD0..=0xDF).contains(&hw_high);  // B cond (0xD0xx-0xDxxx)
            let has_bl_pattern = (0xF0..=0xF7).contains(&hw_high) && (halfword & 0x0800 != 0);  // BL/BLX
            let has_ldr_pc_pattern = (0x40..=0x47).contains(&hw_high);  // LDR R0-R7, [PC, #] (0x40xx-0x47xx in LE)
            let has_push_pop = hw_high == 0xB4 || hw_high == 0xB5 || hw_high == 0xB6 || hw_high == 0xB7;  // PUSH/POP
            let has_common_alu = (0x18..=0x1B).contains(&hw_high) ||  // ADD/SUB Rn, Rm
                                (0x20..=0x27).contains(&hw_high) ||  // MOV/LDR/SUB imm
                                (0x40..=0x4F).contains(&hw_high);  // ALU ops, high register ops
            
            if addr == 0x08000109 || addr == 0x0800019E {
            }
            
            if !has_branch_pattern && !has_bl_pattern && !has_ldr_pc_pattern && !has_push_pop && !has_common_alu {
                continue;
            }
            
            // Validate as Thumb code
            if !decode_is_valid_code(rom, addr, ArmMode::Thumb, &arm_decoder, &thumb_decoder) {
                continue;
            }
            
            indirect_targets.push((addr, ArmMode::Thumb));
            self.branch_targets.insert(addr);
        }
        
        
        eprintln!("  CFG: found {} indirect branch targets", indirect_targets.len());
        
        // Run mini-CFG pass on indirect branch targets
        if !indirect_targets.is_empty() {
            let mut indirect_queue: Vec<(u32, ArmMode)> = indirect_targets;
            let mut indirect_visited: HashSet<(u32, ArmMode)> = HashSet::new();
            const INDIRECT_MAX_INSTRUCTIONS: usize = 10_000;
            let indirect_count = self.bfs_pass(
                &mut indirect_queue,
                &mut indirect_visited,
                Some(&visited),
                &mut data_addresses,
                rom,
                &arm_decoder,
                &thumb_decoder,
                INDIRECT_MAX_INSTRUCTIONS,
                "indirect-pass",
                false,
            );
            eprintln!("  CFG: indirect-pass complete, {} instructions visited", indirect_count);
        }
        if self.instruction_addresses.len() <= 15_000 {
            // Heuristic scan: look for common interrupt handler patterns
        // GBA interrupt handlers often start with:
        // 1. LDR R1, [PC, #imm] - loading a hardware register address
        // 2. LDR R0, [PC, #imm] - loading a value to compare
        // 3. STR Rx, [Rn] - saving registers
        //
        // We scan for code blocks that start with PC-relative loads
        // and add them as potential handler entry points.
        eprintln!("  CFG: heuristic scanning for interrupt handler patterns...");
        let mut heuristic_targets: Vec<u32> = Vec::new();
        
        for addr in (0x08000100..0x08020000).step_by(2) {
            let offset = (addr - 0x08000000) as usize;
            if offset + 4 > rom.len() {
                continue;
            }
            
            // Skip if already discovered
            if self.branch_targets.contains(&addr) {
                continue;
            }
            
            // Check if this looks like an interrupt handler prologue
            // Pattern: LDR Rx, [PC, #imm] (0x48xx or 0x49xx or 0x4axx)
            let hw1 = u16::from_le_bytes([rom[offset], rom[offset+1]]);
            let hw2 = u16::from_le_bytes([rom[offset+2], rom[offset+3]]);
            
            // LDR Rx, [PC, #imm*4] where imm is in range [0x10, 0x50]
            // This is typical for loading hardware register addresses
            let is_ldr_pc = (hw1 & 0xF800) == 0x4800;  // LDR Rx, [PC, #imm]
            let ldr_imm = ((hw1 & 0xFF) * 4) as u32;
            
            if is_ldr_pc && ldr_imm >= 0x40 && ldr_imm <= 0x200 {
                // Check if the loaded value looks like a hardware address
                let load_offset = (addr + 4 + ldr_imm - 0x08000000) as usize;
                if load_offset + 4 <= rom.len() {
                    let loaded_val = u32::from_le_bytes([
                        rom[load_offset],
                        rom[load_offset+1],
                        rom[load_offset+2],
                        rom[load_offset+3],
                    ]);
                    
                    // Hardware addresses are typically in:
                    // - 0x04000000-0x040003FF (MMIO)
                    // - 0x05000000-0x050003FF (Palette RAM)
                    // - 0x06000000-0x06017FFF (VRAM)
                    // - 0x07000000-0x070003FF (OAM)
                    let is_hw_addr = (0x04000000..=0x040003FF).contains(&loaded_val)
                        || (0x05000000..=0x050003FF).contains(&loaded_val)
                        || (0x06000000..=0x06017FFF).contains(&loaded_val)
                        || (0x07000000..=0x070003FF).contains(&loaded_val);
                    
                    if is_hw_addr {
                        // This looks like an interrupt handler!
                        heuristic_targets.push(addr);
                        self.branch_targets.insert(addr);
                    }
                }
            }
        }
        
            eprintln!("  CFG: heuristic scan found {} potential interrupt handlers", heuristic_targets.len());
            for &addr in &heuristic_targets {
                eprintln!("    -> 0x{:08X}", addr);
            }

        // Heuristic scan for loop patterns after BX Rm (indirect branch loops).
        // When we see BX Rm followed by a loop that modifies Rm, add the loop
        // addresses as branch targets. This handles cases like:
        //   BX R3
        //   ... loop that modifies R3 ...
        //   BNE back_to_loop_start
        // 
        // Also scan for basic blocks that start with common prologue instructions
        // (ANDS, LSLS, LSRS, MOVS) followed by conditional branches.
        if !self.bx_registers.is_empty() {
            eprintln!("  CFG: heuristic scan for BX Rm loops...");
            for rn in &self.bx_registers {
                // Scan for loop patterns: SUBS/ADDS Rn, Rn, #imm followed by BNE/BEQ
                for addr in (0x08000100..0x08020000).step_by(2) {
                    let offset = (addr - 0x08000000) as usize;
                    if offset + 8 > rom.len() {
                        continue;
                    }
                    
                    // Skip if already discovered
                    if self.branch_targets.contains(&addr) {
                        continue;
                    }
                    
                    // Check for loop pattern: SUBS/ADDS Rn, Rn, #imm
                    let hw1 = u16::from_le_bytes([rom[offset], rom[offset+1]]);
                    let hw2 = u16::from_le_bytes([rom[offset+2], rom[offset+3]]);
                    
                    // SUBS Rd, Rn, #imm (0x38xx)
                    let is_subs_imm = (hw1 & 0xF800) == 0x3800;
                    let subs_rd = (hw1 >> 8) & 0x7;
                    let subs_rn = (hw1 >> 5) & 0x7;
                    
                    // ADDS Rd, Rn, #imm (0x30xx)
                    let is_adds_imm = (hw1 & 0xF800) == 0x3000;
                    let adds_rd = (hw1 >> 8) & 0x7;
                    let adds_rn = (hw1 >> 5) & 0x7;
                    
                    // Check if this is SUBS/ADDS Rn, Rn, #imm where Rn is our BX register
                    let is_loop_counter = (is_subs_imm && subs_rd == subs_rn && subs_rd == *rn as u16)
                        || (is_adds_imm && adds_rd == adds_rn && adds_rd == *rn as u16);
                    
                    if is_loop_counter {
                        // Check if next instruction is a conditional branch back
                        // BNE/BEQ offset (0xDxxx)
                        let is_cond_branch = (hw2 & 0xF800) == 0xD000;
                        if is_cond_branch {
                            // This looks like a loop! Add as branch target.
                            let target_addr = addr;
                            self.branch_targets.insert(target_addr);
                            heuristic_targets.push(target_addr);
                        }
                    }
                }
            }
            
            // Also scan for basic blocks starting with common prologue instructions
            // followed by conditional branches. This catches blocks that are not
            // reachable through the main CFG traversal.
            for addr in (0x08000100..0x08020000).step_by(2) {
                let offset = (addr - 0x08000000) as usize;
                if offset + 8 > rom.len() {
                    continue;
                }
                
                // Skip if already discovered
                if self.branch_targets.contains(&addr) {
                    continue;
                }
                
                let hw1 = u16::from_le_bytes([rom[offset], rom[offset+1]]);
                let hw2 = u16::from_le_bytes([rom[offset+2], rom[offset+3]]);
                
                // Check for common prologue patterns:
                // ANDS Rn, Rm, Rp (0x00xx)
                // LSLS Rn, Rm, #imm (0x00xx or 0x04xx)
                // LSRS Rn, Rm, #imm (0x08xx)
                // MOVS Rn, #imm (0x20xx)
                let is_and_reg = (hw1 & 0xFE00) == 0x0000;
                let is_lsl_imm = (hw1 & 0xF800) == 0x0000;
                let is_lsr_imm = (hw1 & 0xF800) == 0x0800;
                let is_mov_imm = (hw1 & 0xF800) == 0x2000;
                
                // Check if followed by conditional branch
                let is_cond_branch = (hw2 & 0xF800) == 0xD000;
                
                if (is_and_reg || is_lsl_imm || is_lsr_imm || is_mov_imm) && is_cond_branch {
                    // This looks like a basic block! Add as branch target.
                    let target_addr = addr;
                    self.branch_targets.insert(target_addr);
                    self.instruction_addresses.push(target_addr);
                    self.mode_map.push((target_addr, ArmMode::Thumb));
                    heuristic_targets.push(target_addr);
                    if target_addr == 0x0800010A {
                        eprintln!("  CFG: HEURISTIC FOUND 0x0800010A!");
                    }
                }
            }
        }
        if !heuristic_targets.is_empty() {
            eprintln!("  CFG: heuristic scan found {} loop patterns", heuristic_targets.len());
        }
            
            // Filter speculative targets through data heuristic before mini-passes
            // Skip looks_like_data_soft for both ARM and Thumb modes - it causes false positives
            // for valid code that has data sections later. The data_addresses set already
            // captures known data locations.
            rom_scan_targets.retain(|(addr, mode)| {
                !is_data_address(*addr, *mode, &data_addresses, rom, &arm_decoder, &thumb_decoder)
            });
            heuristic_targets.retain(|addr| {
                !is_data_address(*addr, ArmMode::Thumb, &data_addresses, rom, &arm_decoder, &thumb_decoder)
            });
            
            // Run mini-CFG pass on newly discovered targets
            if !rom_scan_targets.is_empty() || !heuristic_targets.is_empty() {
                eprintln!("  CFG: mini3-pass starting with {} rom_scan + {} heuristic targets", rom_scan_targets.len(), heuristic_targets.len());
            let mut mini3_visited: HashSet<(u32, ArmMode)> = HashSet::new();
            let mut mini3_queue: Vec<(u32, ArmMode)> = rom_scan_targets;
            // Add heuristic targets to the queue
            for addr in heuristic_targets {
                mini3_queue.push((addr, ArmMode::Thumb));
            }
            eprintln!("  CFG: mini3_queue has {} total items", mini3_queue.len());
            const MINI3_MAX_INSTRUCTIONS: usize = 10_000;
            let mini3_count = self.bfs_pass(
                &mut mini3_queue,
                &mut mini3_visited,
                Some(&visited),  // Shared visited set
                &mut data_addresses,
                rom,
                &arm_decoder,
                &thumb_decoder,
                MINI3_MAX_INSTRUCTIONS,
                "mini3-pass",
                false,  // No progress reporting
            );
            eprintln!("  CFG: mini3-pass complete, {} instructions visited", mini3_count);
            }
        } else {
            eprintln!("  CFG: skipping ROM scan/heuristic ({} addresses found)", self.instruction_addresses.len());
        }

        // Run mini-CFG pass on newly discovered targets, same as above
        // Filter rom_wide_targets through data heuristic
        rom_wide_targets.retain(|(addr, mode)| {
            !looks_like_data_soft(rom, *addr, *mode, &arm_decoder, &thumb_decoder)
        });
        
        if !rom_wide_targets.is_empty() {
            let mut mini2_visited: HashSet<(u32, ArmMode)> = HashSet::new();
            let mut mini2_queue: Vec<(u32, ArmMode)> = rom_wide_targets;
            const MINI2_MAX_INSTRUCTIONS: usize = 20_000;
            let mini2_count = self.bfs_pass(
                &mut mini2_queue,
                &mut mini2_visited,
                Some(&visited),  // Shared visited set
                &mut data_addresses,
                rom,
                &arm_decoder,
                &thumb_decoder,
                MINI2_MAX_INSTRUCTIONS,
                "mini2-pass",
                false,  // No progress reporting
            );
            eprintln!("  CFG: mini2-pass complete, {} instructions visited", mini2_count);
        }

        // IWRAM .data resolution: CRT0 copies code+data from ROM to IWRAM,
        // then jumps to IWRAM-resident code. The main BFS skips IWRAM addresses
        // (< 0x08000000), so ROM functions called from IWRAM-resident code are
        // never discovered and run via the slow fallback interpreter.
        //
        // This pass detects .data copy mappings by scanning the ROM for literal
        // pool triples (rom_src, iwram_dst, iwram_end), then runs a mini-BFS
        // from the ROM source to discover BL/B targets in ROM code.
        eprintln!("  CFG: detecting IWRAM .data copy mappings...");
        let mut iwram_entry_targets: Vec<(u32, ArmMode)> = Vec::new();

        for i in (0..rom.len().saturating_sub(12)).step_by(4) {
            let w0 = u32::from_le_bytes([rom[i], rom[i + 1], rom[i + 2], rom[i + 3]]);
            let w1 = u32::from_le_bytes([rom[i + 4], rom[i + 5], rom[i + 6], rom[i + 7]]);
            let w2 = u32::from_le_bytes([rom[i + 8], rom[i + 9], rom[i + 10], rom[i + 11]]);

            if !(w0 >= 0x08000000 && w0 < 0x0A000000) { continue; }
            if !(w1 >= 0x03000000 && w1 < 0x03008000) { continue; }
            if !(w2 > w1 && w2 < 0x03008000) { continue; }
            if w2 - w1 > 0x10000 { continue; }

            // Minimum copy_size filter: only process .data copies >= 64 bytes.
            // Smaller copies are likely data tables (palette entries, small constants),
            // not code regions with function pointers.
            //
            // Maximum copy_size filter: copies > 4 KiB are audio/graphic blobs, not
            // function-pointer tables. Scanning them yields thousands of false seeds
            // that walk into data and inflate the reachable set past the OOM guard.
            let copy_size = (w2 - w1) as usize;
            if copy_size < 64 { continue; }
            let skip_fp_scan = copy_size > 4096;

            let rom_src = w0 & !1;
            let rom_src_offset = (rom_src - 0x08000000) as usize;
            if rom_src_offset + copy_size > rom.len() { continue; }

            eprintln!("    .data copy: ROM 0x{:08X} -> IWRAM 0x{:08X} ({} bytes)",
                      rom_src, w1, copy_size);

            // The .data blob may contain function pointer tables that IWRAM-resident
            // code calls via BLX Rm. Scan the copied bytes for 32-bit values that
            // look like ROM addresses and add them as BFS entry targets.
            //
            // Size guard: limit total IWRAM entry targets to prevent CFG explosion.
            const IWRAM_MAX_ENTRY_TARGETS: usize = 200;
            if iwram_entry_targets.len() >= IWRAM_MAX_ENTRY_TARGETS {
                eprintln!("    [CFG] IWRAM entry target limit reached, skipping remaining .data copies");
                break;
            }
            
            if !skip_fp_scan {
                for fp_off in (0..copy_size.saturating_sub(4)).step_by(4) {
                    let fp = u32::from_le_bytes([
                        rom[rom_src_offset + fp_off],
                        rom[rom_src_offset + fp_off + 1],
                        rom[rom_src_offset + fp_off + 2],
                        rom[rom_src_offset + fp_off + 3],
                    ]);
                    if fp >= 0x08000000 && fp < 0x0A000000 {
                        let target = fp & !1;
                        let mode = if fp & 1 == 1 { ArmMode::Thumb } else { ArmMode::Arm };
                        
                        // Validate alignment: Thumb must be even, ARM must be 4-byte aligned
                        if mode == ArmMode::Thumb && (target & 1) != 0 { continue; }
                        if mode == ArmMode::Arm && (target & 3) != 0 { continue; }
                        
                        // Validate that the address decodes as actual code, not data literals.
                        // Function-pointer tables embedded in .data blobs are the worst
                        // contamination source: audio sample data decodes as valid Thumb
                        // for thousands of halfwords. Require a run of consecutive valid
                        // decodes to confirm real code.
                        const IWRAM_SEED_MIN_RUN: usize = 32;
                        if !decode_is_valid_code_run(rom, target, mode, IWRAM_SEED_MIN_RUN, &arm_decoder, &thumb_decoder) {
                            continue;
                        }
                        
                        if self.branch_targets.insert(target) {
                            iwram_entry_targets.push((target, mode));
                            // Size guard inside the loop too
                            if iwram_entry_targets.len() >= IWRAM_MAX_ENTRY_TARGETS {
                                eprintln!("    [CFG] IWRAM entry target limit reached at 0x{:08X}, stopping scan", target);
                                break;
                            }
                        }
                    }
                }
            } else {
                // Large blob: skip function-pointer scan, add the blob start as a BFS entry
                let blob_target = rom_src & !1;
                let blob_mode = if rom_src & 1 == 1 { ArmMode::Thumb } else { ArmMode::Arm };
                if decode_is_valid_code_run(rom, blob_target, blob_mode, 8, &arm_decoder, &thumb_decoder) {
                    if self.branch_targets.insert(blob_target) {
                        iwram_entry_targets.push((blob_target, blob_mode));
                    }
                }
            }
        }

        // Filter IWRAM entry targets through data heuristic
        iwram_entry_targets.retain(|(addr, mode)| {
            !looks_like_data_soft(rom, *addr, *mode, &arm_decoder, &thumb_decoder)
        });
        
        if !iwram_entry_targets.is_empty() {
            let mut iwram_visited: HashSet<(u32, ArmMode)> = HashSet::new();
            let mut iwram_queue: Vec<(u32, ArmMode)> = iwram_entry_targets;
            const IWRAM_MAX_INSTRUCTIONS: usize = 20_000;
            let iwram_count = self.bfs_pass(
                &mut iwram_queue,
                &mut iwram_visited,
                Some(&visited),  // Shared visited set
                &mut data_addresses,
                rom,
                &arm_decoder,
                &thumb_decoder,
                IWRAM_MAX_INSTRUCTIONS,
                "IWRAM pass",
                false,  // No progress reporting
            );
            eprintln!("  CFG: IWRAM pass complete, {} instructions visited", iwram_count);
        }

        // Scan ROM for Thumb function prologues (PUSH {..., LR} = 0xB5xx).
        // Each is a potential function entry point not reachable via direct branch.
        // Very conservative: only scan first 32 KB, max 20 targets, require LR bit.
        eprintln!("  CFG: scanning for Thumb function prologues...");
        let mut prologue_targets: Vec<(u32, ArmMode)> = Vec::new();
        const PROLOGUE_SCAN_START: usize = 0x100;  // Skip vector table
        const PROLOGUE_SCAN_END: usize = 0x80000;  // Limit to first 512 KB of ROM
        const PROLOGUE_MAX_TARGETS: usize = 20;    // Very strict limit
        for off in (PROLOGUE_SCAN_START..rom.len().saturating_sub(1)).step_by(2) {
            if off >= PROLOGUE_SCAN_END { break; }
            if prologue_targets.len() >= PROLOGUE_MAX_TARGETS { break; }
            let hw = u16::from_le_bytes([rom[off], rom[off + 1]]);
            // PUSH {r0-r7, lr} = 0xB5xx where bit 7 of low byte indicates LR is pushed
            if (hw & 0xFF00) == 0xB500 && (hw & 0x0080) != 0 {
                let target: u32 = 0x08000000 + off as u32;
                if self.branch_targets.contains(&target) { continue; }
                // Require valid code run AND reject if looks like data (audio/graphics)
                if decode_is_valid_code_run(rom, target, ArmMode::Thumb, 16, &arm_decoder, &thumb_decoder)
                    && !looks_like_data_soft(rom, target, ArmMode::Thumb, &arm_decoder, &thumb_decoder) {
                    if self.branch_targets.insert(target) {
                        prologue_targets.push((target, ArmMode::Thumb));
                    }
                }
            }
        }
        eprintln!("  CFG: found {} Thumb function prologues", prologue_targets.len());
        
        // TEMP: check data_addresses before BFS
        eprintln!("PRE_BFS: data_addresses.len()={} contains_C8={}", data_addresses.len(), data_addresses.contains(&0x080000C8u32));
        // Run BFS from prologue targets to discover their code
        if !prologue_targets.is_empty() {
            let mut prologue_visited: HashSet<(u32, ArmMode)> = HashSet::new();
            let mut prologue_queue: Vec<(u32, ArmMode)> = prologue_targets;
            const PROLOGUE_MAX_INSTRUCTIONS: usize = 5_000;
            let prologue_count = self.bfs_pass(
                &mut prologue_queue,
                &mut prologue_visited,
                Some(&visited),
                &mut data_addresses,
                rom,
                &arm_decoder,
                &thumb_decoder,
                PROLOGUE_MAX_INSTRUCTIONS,
                "prologue pass",
                false,
            );
            eprintln!("  CFG: prologue pass complete, {} instructions visited", prologue_count);
        }

        // TEMP: check if 0x080000C8 is in data_addresses
        eprintln!("CHECK_C8: in_instructions={} in_data={}",
            self.instruction_addresses.contains(&0x080000C8u32),
            data_addresses.contains(&0x080000C8u32));
        eprintln!("CHECK_C4: in_instructions={} in_data={}",
            self.instruction_addresses.contains(&0x080000C4u32),
            data_addresses.contains(&0x080000C4u32));

        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8u32));
        // TEMP DEBUG: check data_addresses for 0x080000C8
        let check_c8 = 0x080000C8u32;
        eprintln!("CHECK_DATA: 0x080000C8 in data_addresses={} total_data_addrs={}", 
            data_addresses.contains(&check_c8), data_addresses.len());
        // If it's there, find which check added it by scanning the ROM
        if data_addresses.contains(&check_c8) {
            let rom_len = rom.len() as u32;
            for offset in (0..rom.len().saturating_sub(3)).step_by(4) {
                let addr = 0x08000000u32 + offset as u32;
                let word = u32::from_le_bytes([rom[offset], rom[offset+1], rom[offset+2], rom[offset+3]]);
                let cond = (word >> 29) & 0x7;
                // Check 1: LDR bit4=1
                if (word >> 25) & 0x7 == 0b010 && (word >> 4) & 0x1 == 1 && (word >> 16) & 0xF == 0xF && cond != 0b111 {
                    let pool = addr + 8 + (word & 0xFFF);
                    if pool == check_c8 { eprintln!("FOUND_C8: check1 addr=0x{:08X} word=0x{:08X}", addr, word); }
                }
    eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
                // Check 2: LDR bit4=0
                if (word >> 25) & 0x7 == 0b010 && (word >> 4) & 0x1 == 0 && (word >> 16) & 0xF == 0xF && cond != 0b111 {
                    let pool = addr + 8 + (word & 0xFFF);
                    if pool == check_c8 { eprintln!("FOUND_C8: check2 addr=0x{:08X} word=0x{:08X}", addr, word); }
                }
                // Check 3: LDC/STC
                if (word >> 25) & 0x7 == 0b110 && (word >> 4) & 0x1 == 1 && (word >> 16) & 0xF == 0xF && cond != 0b111 {
                    let pool = addr + 8 + ((word & 0xFF) * 4);
                    if pool == check_c8 { eprintln!("FOUND_C8: check3 addr=0x{:08X} word=0x{:08X}", addr, word); }
                }
            }

// DEBUG: check if 0x080000C8 is in data_addresses after scan
eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
eprintln!("AFTER_SCAN: data_addresses has {} entries", data_addresses.len());
        eprintln!("DATA_SCAN_DONE: 0x080000C8 in data_addresses={} total_entries={}", data_addresses.contains(&0x080000C8), data_addresses.len());
        eprintln!("DATA_SCAN_DONE: 0x080000C8 in data_addresses={} total_entries={}", data_addresses.contains(&0x080000C8), data_addresses.len());

    eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
    eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={} total_entries={}", data_addresses.contains(&0x080000C8), data_addresses.len());
    eprintln!("DATA_SCAN_DONE: 0x080000C8 in data_addresses={} total_entries={}", data_addresses.contains(&0x080000C8), data_addresses.len());
    eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        // TEMP DEBUG: check data_addresses
        eprintln!("DATA_SCAN_COMPLETE: total={} contains_C8={}",
            data_addresses.len(),
            data_addresses.contains(&0x080000C8u32));
    eprintln!("AFTER_SCAN: data_addresses has {} entries", data_addresses.len());
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        eprintln!("DATA_SCAN_RESULT: 0x080000C8 in data_addresses={} total_entries={}", data_addresses.contains(&0x080000C8), data_addresses.len());
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={} total_entries={}", data_addresses.contains(&0x080000C8), data_addresses.len());
            eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={} total_entries={}", data_addresses.contains(&0x080000C8), data_addresses.len());
        }
    eprintln!("DATA_SCAN_RESULT: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8u32));
        eprintln!("AFTER_SCAN: data_addresses has {} entries", data_addresses.len());
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        // TEMP: comprehensive data_addresses check
        eprintln!("DATA_CHECK: 0x080000C8 in data_addresses={} total_data_addrs={}", data_addresses.contains(&0x080000C8u32), data_addresses.len());
        if data_addresses.contains(&0x080000C8u32) {
            eprintln!("DATA_CHECK: 0x080000C8 IS in data_addresses! Investigating...");
        }
        eprintln!("DATA_CHECK: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8u32));
        eprintln!("DATA_CHECK: 0x080000C8 in data_addresses={} total_data_addrs={}", data_addresses.contains(&0x080000C8u32), data_addresses.len());
        // TEMP DEBUG: check if 0x080000C8 is in data_addresses
        eprintln!("POST_SCAN: 0x080000C8 in data_addresses={} total_entries={}",
            data_addresses.contains(&0x080000C8u32), data_addresses.len());
        // Print all entries near 0x080000C0-0x080000D0
        for da in &data_addresses {
            if *da >= 0x080000C0 && *da <= 0x080000D0 {
                eprintln!("  data_addresses contains 0x{:08X}", da);
            }
        }

        eprintln!("POST_SCAN: C8_in_data={}", data_addresses.contains(&0x080000C8u32));
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        eprintln!("AFTER_SCAN: data_addresses has {} entries", data_addresses.len());
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        eprintln!("BEFORE_SORT: 0x080000C8 in data_addresses={} 0x080000C4 in data_addresses={}", data_addresses.contains(&0x080000C8), data_addresses.contains(&0x080000C4));
        eprintln!("DATA_CHECK: 0x080000C8 in data_addresses={} total_entries={}", data_addresses.contains(&0x080000C8), data_addresses.len());
        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        eprintln!("AFTER_SCAN: data_addresses has {} entries", data_addresses.len());
        eprintln!("DATA_ADDR_CHECK: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8u32));
        eprintln!("DATA_ADDR_CHECK: total data_addresses={}", data_addresses.len());

        eprintln!("FINAL_CHECK: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        self.instruction_addresses.sort();
        self.instruction_addresses.dedup();
        if self.instruction_addresses.contains(&0x0800010A) {
            eprintln!("  CFG: 0x0800010A is in instruction_addresses!");
        } else {
            eprintln!("  CFG: 0x0800010A is NOT in instruction_addresses!");
        }
        self.mode_map.sort();
        self.mode_map.dedup();
    }

    /// Track register values for MOV rN, #imm, LDR rN, =imm, and
    /// ADD/SUB Rd, PC, #imm patterns (the ARM ADR pseudo-instruction and
    /// the standard ARM->Thumb switch idiom: ADD Rd, PC, #1; BX Rd).
    /// Also detects stores to known vector table addresses to discover
    /// handler entry points (e.g., IRQ handler stored to 0x03007FFC).
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

        // Track arithmetic operations on registers for indirect branch resolution.
        // When we see ADD Rd, Rn, Rm or SUBS Rd, Rn, #imm, we can't know the exact
        // value, but we can track that the register is "in use" for arithmetic.
        // This helps the CFG recognize that BX Rn after arithmetic operations
        // may jump to a loop or computed address.
        // 
        // For Thumb ADD/SUB (format 2): ADD/SUB Rd, Rn, Rm or ADD/SUB Rd, Rn, #imm
        if (opcode == "ADD" || opcode == "SUB" || opcode == "ADDS" || opcode == "SUBS") && operands.len() >= 2 {
            // Track the destination register as being modified by arithmetic
            if let Operand::Register(rd) = operands[0] {
                // Invalidate the register since its value is now computed
                // This prevents false positives from stale tracked values
                self.register_tracker.invalidate(rd);
            }
        }

        // Detect stores to GBA vector table addresses to discover handler entry points.
        // The GBA vector table is in IWRAM at 0x03007FF0-0x03007FFF.
        // Common vectors:
        //   0x03007FFC: IRQ handler
        //   0x03007FF8: VBlank interrupt handler
        //   0x03007FF4: VCount interrupt handler
        // When we see STR Rx, [Rn, #offset] where the effective address is a vector,
        // extract the stored value (from Rx) and add it as a branch target.
        if opcode.starts_with("STR") && operands.len() == 2 {
            if let Operand::Register(src_reg) = operands[0] {
                if let Operand::MemoryAddress { base, offset, .. } = &operands[1] {
                    let store_addr = match offset {
                        AddressingMode::ImmediateOffset(off) => {
                            if let Some(base_val) = self.register_tracker.get(*base) {
                                base_val.wrapping_add(*off as u32)
                            } else {
                                0
                            }
                        }
                        AddressingMode::RegisterOffset(reg_off) => {
                            if let Some(base_val) = self.register_tracker.get(*base) {
                                if let Some(off_val) = self.register_tracker.get(*reg_off) {
                                    base_val.wrapping_add(off_val)
                                } else {
                                    0
                                }
                            } else {
                                0
                            }
                        }
                        _ => 0,
                    };

                    // Check if this is a store to a known vector address
                    const IRQ_VECTOR: u32 = 0x03007FFC;
                    const VBLANK_VECTOR: u32 = 0x03007FF8;
                    const VCOUNT_VECTOR: u32 = 0x03007FF4;
                    
                    let is_vector_store = store_addr == IRQ_VECTOR 
                        || store_addr == VBLANK_VECTOR 
                        || store_addr == VCOUNT_VECTOR;
                    
                    if is_vector_store && store_addr != 0 {
                        // Try to get the value being stored
                        if let Some(handler_addr) = self.register_tracker.get(src_reg) {
                            if handler_addr >= 0x08000000 && handler_addr < 0x0A000000 {
                                // This looks like a handler address, add it as a branch target
                                self.ldr_literals.push((src_reg, handler_addr));
                            }
                        }
                    }
                }
            }
        }
        
        // Special case: detect LDR instructions that load IWRAM vector addresses.
        // When we see LDR Rn, [PC, #offset] where the loaded value is in the IWRAM
        // vector table range (0x03007FF0-0x03007FFF), track the register so we can
        // later detect stores to that address.
        // Also track LDR Rn, [PC, #offset] that load ROM addresses for indirect branch resolution.
        if opcode.starts_with("LDR") && operands.len() >= 2 {
            if let Operand::Register(rd) = operands[0] {
                if let Operand::MemoryAddress { base: 15, offset: AddressingMode::ImmediateOffset(off), .. } = &operands[1] {
                    let pc = match mode {
                        ArmMode::Thumb => (addr & !1) + 4,
                        ArmMode::Arm => addr + 8,
                    };
                    let load_addr = pc.wrapping_add(*off as u32) & !3;
                    let rom_offset = (load_addr - 0x08000000) as usize;
                    
                    if rom_offset + 4 <= rom.len() {
                        let loaded_value = u32::from_le_bytes([
                            rom[rom_offset],
                            rom[rom_offset + 1],
                            rom[rom_offset + 2],
                            rom[rom_offset + 3],
                        ]);
                        
                        // Check if this loads a vector table address
                        const IRQ_VECTOR: u32 = 0x03007FFC;
                        const VBLANK_VECTOR: u32 = 0x03007FF8;
                        const VCOUNT_VECTOR: u32 = 0x03007FF4;
                        
                        if loaded_value == IRQ_VECTOR || loaded_value == VBLANK_VECTOR || loaded_value == VCOUNT_VECTOR {
                            // Track this register so subsequent STR instructions can be detected
                            self.register_tracker.track_mov_immediate(rd, loaded_value);
                        }
                        
                        // Also track LDR PC-relative loads that load ROM/IWRAM addresses.
                        // This helps resolve indirect branches (BX Rn) where Rn is loaded
                        // from a literal pool and then used as a branch target.
                        // We track both ROM addresses (0x08000000+) and IWRAM addresses (0x03000000-0x03008000)
                        // because IWRAM-resident code may call ROM functions.
                        if (loaded_value >= 0x08000000 && loaded_value < 0x0A000000) ||
                           (loaded_value >= 0x03000000 && loaded_value < 0x03008000) {
                            self.register_tracker.track_mov_immediate(rd, loaded_value);
                            // Collect for the post-processing sweep
                            if loaded_value >= 0x08000000 && loaded_value < 0x0A000000 {
                                self.ldr_literals.push((rd, loaded_value));
                            }
                        }
                    }
                }
            }
        }
    }

    fn extract_branch_targets(&mut self, opcode: &str, operands: &[Operand], addr: u32) -> Vec<u32> {
        let mut targets = Vec::new();
        let upper_op = opcode.to_uppercase();

        // BL stores the full target directly - extract it from the operand
        if opcode == "BL" {
            if let Some(Operand::Immediate(target)) = operands.first() {
                targets.push(*target);
            }
            return targets;
        }

        // BLX (immediate) also stores the full target directly - extract it from the operand
        // This is distinct from BLX Rm (register variant) which is handled below
        if opcode == "BLX" {
            if let Some(Operand::Immediate(target)) = operands.first() {
                targets.push(*target);
            }
            return targets;
        }

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
                        // Indirect branch (BX Rm / BLX Rm): the register value is known via tracking.
                        // The target address has bit 0 as the Thumb-mode indicator.
                        // If bit 0 is set → Thumb mode, if clear → ARM mode.
                        if target & 1 == 1 {
                            // Thumb mode target: normalize by clearing bit 0
                            targets.push(target & !1);
                        } else {
                            // ARM mode target: use as-is (already 4-byte aligned)
                            targets.push(target);
                        }
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

    /// Runs a single BFS pass over reachable code.
    ///
    /// This is the shared implementation for all 5 BFS passes (main, mini, mini2, mini3, IWRAM).
    /// The only differences between passes are:
    /// - Queue/visited variable names (passed as mutable references)
    /// - Max instructions limit (passed as parameter)
    /// - Max consecutive non-branch limit (always 128, hardcoded)
    /// - Whether to check a shared visited set (passed as parameter)
    ///
    /// Returns the number of instructions visited in this pass.
    fn bfs_pass(
        &mut self,
        queue: &mut Vec<(u32, ArmMode)>,
        own_visited: &mut HashSet<(u32, ArmMode)>,
        shared_visited: Option<&HashSet<(u32, ArmMode)>>,
        data_addresses: &mut HashSet<u32>,
        rom: &[u8],
        arm_decoder: &ArmDecoder,
        thumb_decoder: &ThumbDecoder,
        max_instructions: usize,
        label: &str,
        report_progress: bool,
    ) -> usize {
        // Cut fall-through after this many consecutive non-branch instructions.
        // Real Thumb code branches every ~10-20 instructions; audio/graphic data
        // decoded as Thumb produces thousands of consecutive valid-looking
        // halfwords with no branches. 32 catches data walks early. Legitimate
        // long straight-line runs (memcpy loops, LDR/STR sequences) are kept
        // reachable via explicit branch targets and BL fall-through, not by
        // inflating this limit.
        const MAX_CONSECUTIVE_NON_BRANCH: usize = 32;
        let mut count = 0;
        let mut consecutive_non_branch: usize = 0;

        while let Some((addr, current_mode)) = queue.pop() {
            // Each queue item is the start of a new basic block; reset the
            // non-branch counter so saturation from a prior block doesn't
            // block fall-through pushes for this one.
            consecutive_non_branch = 0;
            // Skip if in data_addresses (soft hint: re-validate as code)
            // Skip looks_like_data_soft for ARM mode - it causes false positives
            // for valid ARM code that has data sections later (e.g., 0x08000144 = 0x00000000).
            // The data_addresses set already captures known data locations.
            if is_data_address(addr, current_mode, data_addresses, rom, arm_decoder, thumb_decoder)
                || (matches!(current_mode, ArmMode::Thumb) && looks_like_data_soft(rom, addr, current_mode, arm_decoder, thumb_decoder)) {
                continue;
            }

            // Skip if already visited in own set or shared set
            if own_visited.contains(&(addr, current_mode)) {
                continue;
            }
            if let Some(shared) = shared_visited {
                if shared.contains(&(addr, current_mode)) {
                    continue;
                }
            }

            own_visited.insert((addr, current_mode));

            count += 1;
            if report_progress && count % 100_000 == 0 {
                eprintln!("  CFG progress: {} visited, {} branch targets",
                          count, self.branch_targets.len());
            }
            if count >= max_instructions {
                eprintln!("  CFG {} safety limit reached, stopping", label);
                break;
            }

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
                    let hw1 = u16::from_le_bytes([rom[rom_offset], rom[rom_offset + 1]]);
                    
                    // Check if this is the first half of a 32-bit BL instruction
                    let (op, ops, width) =
                        if (hw1 & 0xF800) == 0xF000 {
                            // Potential BL_PREFIX: opcode range 0xF000-0xF7FF with bit 11 = 0
                            // Try to read the next halfword for BL_SUFFIX
                            if rom_offset + 4 <= rom.len() {
                                let hw2 = u16::from_le_bytes([rom[rom_offset + 2], rom[rom_offset + 3]]);
                                // Check if hw2 is a valid BL_SUFFIX (bit 11 = 1)
                                if let Some((op, ops, _, w)) = thumb_decoder.decode_bl_pair(hw1, hw2, decode_addr) {
                                    (op, ops, w)
                                } else {
                                    // hw2 is not a valid BL_SUFFIX, fall back to BL_PREFIX
                                    let (op, ops, _) = thumb_decoder.decode(hw1, decode_addr);
                                    (op, ops, 2)
                                }
                            } else {
                                // Can't read next halfword, fall back to BL_PREFIX
                                let (op, ops, _) = thumb_decoder.decode(hw1, decode_addr);
                                (op, ops, 2)
                            }
                        } else {
                            // Not a BL_PREFIX, decode normally
                            let (op, ops, _) = thumb_decoder.decode(hw1, decode_addr);
                            (op, ops, 2)
                        };
                    (op, ops, width)
                }
            };

            if opcode_str.starts_with("UNKNOWN") || opcode_str == "UNDEFINED" {
                continue;
            }
            if let Some(pool_addr) = literal_pool_addr(&opcode_str, &operands, addr, current_mode) {
                data_addresses.insert(pool_addr);
            }

            // Filter out data regions (audio/graphics) that decode as valid instructions
            // This prevents CFG explosion from misclassifying data as code
            // Skip looks_like_data_soft for both ARM and Thumb modes - it causes false positives
            // for valid code that has data sections later. The data_addresses set already
            // captures known data locations.
            let is_data = is_data_address(addr, current_mode, data_addresses, rom, arm_decoder, thumb_decoder);
            if !is_data {
                self.instruction_addresses.push(addr);
                self.mode_map.push((addr, current_mode));
            }

            let targets = self.extract_branch_targets(&opcode_str, &operands, addr);
            self.track_register_values(&opcode_str, &operands, addr, current_mode, rom);

            let is_uncond_branch = opcode_str == "B"
                || opcode_str == "BX"
                || writes_to_pc(&opcode_str, &operands);

            // Reset on any control flow. BL_PREFIX is part of a BL call pair
            // (BL_PREFIX + BL_SUFFIX); reset here so the pair isn't penalized.
            if is_uncond_branch
                || !targets.is_empty()
                || opcode_str == "BL"
                || opcode_str == "BLX"
                || opcode_str == "BL_PREFIX"
            {
                consecutive_non_branch = 0;
            } else {
                consecutive_non_branch += 1;
            }
            if !is_uncond_branch && consecutive_non_branch < MAX_CONSECUTIVE_NON_BRANCH {
                let next_addr = addr + instr_width as u32;
                let next_rom_offset = (next_addr - 0x08000000) as usize;
                // Skip looks_like_data_soft for both ARM and Thumb modes - it causes false positives
                // for valid code that has data sections later. The data_addresses set already
                // captures known data locations.
                let next_is_data = is_data_address(next_addr, current_mode, data_addresses, rom, arm_decoder, thumb_decoder);
                if addr >= 0x080000C0 && addr <= 0x080000D0 {
                    eprintln!("DEBUG FALLTHROUGH: addr=0x{:08X} next_addr=0x{:08X} next_is_data={} visited={}", addr, next_addr, next_is_data, own_visited.contains(&(next_addr, current_mode)));
                }
                if !own_visited.contains(&(next_addr, current_mode))
                    && shared_visited.map_or(true, |s| !s.contains(&(next_addr, current_mode)))
                    && next_addr >= 0x08000000
                    && next_rom_offset < rom.len()
                    && !next_is_data
                {
                    queue.push((next_addr, current_mode));
                } else if addr >= 0x080000C0 && addr <= 0x080000D0 {
                    eprintln!("DEBUG FALLTHROUGH: Skipping 0x{:08X} - visited={}, shared_visited={}, in_range={}, is_data={}", 
                        next_addr, 
                        own_visited.contains(&(next_addr, current_mode)),
                        shared_visited.map_or(false, |s| s.contains(&(next_addr, current_mode))),
                        next_rom_offset < rom.len(),
                        next_is_data);
                }
            }

            for raw_target in targets {
                if raw_target < 0x08000000 || (raw_target - 0x08000000) as usize >= rom.len() {
                    continue;
                }
                let target_mode = if opcode_str == "BX" || opcode_str == "BLX" || opcode_str == "BL" {
                    if raw_target & 1 == 1 { ArmMode::Thumb } else { ArmMode::Arm }
                } else {
                    current_mode
                };
                let target = if target_mode == ArmMode::Thumb {
                    raw_target & !1
                } else {
                    raw_target & !3
                };
                // Explicit branch targets are always added to instruction_addresses - do NOT filter by data heuristics.
                // If code explicitly jumps to an address, it must be in the dispatch table.
                // Data heuristics only apply to fall-through, not to explicit branches.
                if !self.instruction_addresses.contains(&target) {
                    self.instruction_addresses.push(target);
                    self.mode_map.push((target, target_mode));
                }
                if !own_visited.contains(&(target, target_mode))
                    && shared_visited.map_or(true, |s| !s.contains(&(target, target_mode)))
                {
                    queue.push((target, target_mode));
                }
                self.branch_targets.insert(target);
            }

            if opcode_str == "BL_SUFFIX" {
                self.register_tracker.track_mov_immediate(14, (addr + 2) | 1);
            } else if opcode_str == "BL" || opcode_str == "BLX" {
                self.register_tracker.track_mov_immediate(14, addr + 4);
            }
        }

        eprintln!("AFTER_SCAN: 0x080000C8 in data_addresses={}", data_addresses.contains(&0x080000C8));
        count
    }
}
