// ============================================================================
// Extracted Helper Functions
// These were previously nested inside run_pipeline and are now top-level
// for better testability and code organization.
// ============================================================================

use gbatopy_disasm::{
    operand::AddressingMode, operand::Operand, ArmMode, DecodedInstruction,
};
use std::collections::{HashMap, HashSet};

/// Returns true for ARM conditional branch mnemonics (BEQ, BNE, BCS, etc.).
/// Uses an explicit set instead of a prefix+length heuristic to avoid
/// false positives like BIC (bit-clear) which also starts with 'B' and
/// has length 3.
pub(crate) fn is_conditional_branch(op: &str) -> bool {
    matches!(
        op,
        "BEQ"
            | "BNE"
            | "BCS"
            | "BCC"
            | "BMI"
            | "BPL"
            | "BVS"
            | "BVC"
            | "BHI"
            | "BLS"
            | "BGE"
            | "BLT"
            | "BGT"
            | "BLE"
            | "BAL"
            | "BNV"
    )
}

/// Returns true for conditional non-branch instructions (e.g. LDREQ, ADDNE).
/// Branches handle their own control flow; this identifies data-processing
/// and load/store instructions with a condition code that are NOT branches.
pub(crate) fn is_conditional_non_branch(inst: &DecodedInstruction) -> bool {
    let op = inst.opcode.as_str();
    let full_op = op.split_whitespace().next().unwrap_or(op);
    let base_op = full_op.trim_end_matches(|c: char| c.is_ascii_lowercase());
    let cond_suffix = &full_op[base_op.len()..];
    if cond_suffix.is_empty() || cond_suffix.eq_ignore_ascii_case("al") {
        return false;
    }
    if matches!(
        base_op,
        "B" | "BL" | "BX" | "BLX" | "CBZ" | "CBNZ" | "BL_SUFFIX"
    ) || is_conditional_branch(op)
    {
        return false;
    }
    true
}

/// Returns true for ARM conditional branch mnemonics (BEQ, BNE, BCS, etc.).
/// Uses an explicit set instead of a prefix+length heuristic to avoid
/// false positives like BIC (bit-clear) which also starts with 'B' and
/// has length 3.
pub(crate) fn writes_r15(inst: &DecodedInstruction) -> bool {
    let op = inst.opcode.as_str();
    let base_op = op.trim_end_matches(|c: char| c.is_ascii_lowercase());

    // Branch family: unconditional (B/BL/BX/BLX/CBZ/CBNZ) and conditional (BEQ, BNE, ...).
    // BL_SUFFIX is the Thumb BL branch half that writes PC.
    // Use base_op (condition suffix stripped) so conditional variants like
    // BXeq, BLXne are recognized as block terminators.
    if matches!(
        base_op,
        "B" | "BL" | "BX" | "BLX" | "CBZ" | "CBNZ" | "BL_SUFFIX"
    ) || is_conditional_branch(op)
    {
        return true;
    }

    // Store instructions: first operand is a source, not a destination.
    // STM* covers STMFD, STMIA, STMDB, STMDA, STMEA, STMED, STMFA, STMIB,
    // and their '!' (writeback) variants. PUSH is the Thumb alias.
    let is_store =
        matches!(op, "STR" | "STRH" | "STRB" | "STRD" | "PUSH") || op.starts_with("STM");
    // Comparison instructions: only set flags, no Rd write.
    let is_comparison = matches!(op, "CMP" | "CMN" | "TST" | "TEQ");

    // Only the FIRST operand is the destination for data-processing and loads.
    if !is_store && !is_comparison {
        if let Some(Operand::Register(r)) = inst.operands.first() {
            if *r == 15 {
                return true;
            }
        }
    }

    // LDM: the register list (MemoryAddress.offset = Multi) holds destinations.
    if !is_store {
        for operand in &inst.operands {
            if let Operand::MemoryAddress { offset, .. } = operand {
                // Not collapsible: outer if let destructures offset, inner checks AddressingMode
                #[allow(clippy::collapsible_match)]
                if let AddressingMode::Multi { registers, .. } = offset {
                    if registers.contains(&15) {
                        return true;
                    }
                }
            }
        }
    }

    // Thumb POP: register list is flat Operand::Register(N), not MemoryAddress::Multi.
    // POP {PC} writes R15 and must terminate the basic block.
    if op == "POP" {
        for operand in &inst.operands {
            if let Operand::Register(r) = operand {
                if *r == 15 {
                    return true;
                }
            }
        }
    }

    false
}

/// Helper: check if instruction reads r[15]
/// Used to decide if PC advance is needed before this instruction
pub(crate) fn reads_r15(inst: &DecodedInstruction) -> bool {
    let op = inst.opcode.as_str();
    // Branches implicitly read PC
    if matches!(op, "B" | "BL" | "BX" | "BLX" | "CBZ" | "CBNZ") {
        return true;
    }
    // Check ALL operands for r15 references
    for op in &inst.operands {
        match op {
            Operand::Register(r) if *r == 15 => return true,
            Operand::ShiftedRegister { reg: r, .. } if *r == 15 => return true,
            Operand::MemoryAddress {
                base: r, offset, ..
            } if *r == 15 => return true,
            _ => {}
        }
    }
    false
}

/// Peephole optimization: detect memset loop pattern across basic blocks
/// Pattern: STMIA Rb!, {Rs} -> SUB Rc, #4 -> BNE back to STMIA
/// This detects 3-instruction memset loops that span 3 basic blocks
pub(crate) fn detect_memset_loop_pattern_across_blocks(
    func_groups: &HashMap<(u64, ArmMode), Vec<&DecodedInstruction>>,
) -> HashSet<u64> {
    let mut optimized_blocks = HashSet::new();

    for (&(block_addr, block_mode), block_insts) in func_groups {
        // Block must have exactly 1 instruction
        if block_insts.len() != 1 {
            continue;
        }
        let inst0 = block_insts[0];

        // Instruction 0: STMIA Rb!, {Rs} - single register, post-increment
        if inst0.opcode != "STMIA" {
            continue;
        }
        let stmia_uses = &inst0.operands;
        if stmia_uses.len() != 2 {
            continue;
        }
        let Operand::Register(_rb) = stmia_uses[0] else {
            continue;
        };
        let Operand::Register(_rs) = stmia_uses[1] else {
            continue;
        };

        // Next block should be at addr + 2 (Thumb instruction size)
        let next_addr = (inst0.address + 2) as u64;
        let next_key = (next_addr, block_mode);

        let Some(next_block) = func_groups.get(&next_key) else {
            continue;
        };
        if next_block.len() != 1 {
            continue;
        }
        let inst1 = next_block[0];

        // Instruction 1: SUB Rc, #4 - sets flags
        // Can be either "SUB Rc, #4" (2 operands) or "SUB Rc, Rc, #4" (3 operands)
        if inst1.opcode != "SUB" {
            continue;
        }
        let sub_uses = &inst1.operands;
        if sub_uses.len() < 2 {
            continue;
        }
        let Operand::Register(_rc) = sub_uses[0] else {
            continue;
        };
        // Check for immediate 4 - can be at position 1 or 2 depending on format
        // Format 1: SUB Rd, #imm (2 operands)
        // Format 2: SUB Rd, Rm, #imm (3 operands)
        let is_sub_4 = if sub_uses.len() == 2 {
            // Format 1: SUB Rd, #imm
            matches!(sub_uses[1], Operand::Immediate(4))
        } else if sub_uses.len() >= 3 {
            // Format 2: SUB Rd, Rm, #imm - immediate is at position 2
            matches!(sub_uses[2], Operand::Immediate(4))
        } else {
            false
        };
        if !is_sub_4 {
            continue;
        }
        if !inst1.sets_flags {
            continue;
        }

        // Next-next block should be at addr + 4
        let next2_addr = (inst1.address + 2) as u64;
        let next2_key = (next2_addr, block_mode);

        let Some(next2_block) = func_groups.get(&next2_key) else {
            continue;
        };
        if next2_block.len() != 1 {
            continue;
        }
        let inst2 = next2_block[0];

        // Instruction 2: BNE back to instruction 0
        if inst2.opcode != "BNE" {
            continue;
        }
        let bne_target = if let Some(Operand::Immediate(target)) = inst2.operands.first() {
            *target as u64
        } else {
            continue;
        };
        if bne_target != block_addr {
            continue;
        }

        // Pattern matched! Mark all 3 blocks for optimization
        optimized_blocks.insert(block_addr);
        optimized_blocks.insert(next_addr);
        optimized_blocks.insert(next2_addr);
    }

    optimized_blocks
}

/// Peephole optimization: detect memset loop pattern
/// Pattern: STMIA Rb!, {Rs} -> SUB Rc, #4 -> BNE back to STMIA
/// This detects 3-instruction memset loops and emits a single bulk Python loop
pub(crate) fn detect_memset_loop_pattern(
    insts: &[&DecodedInstruction],
) -> Option<(u8, u8, u8, u64)> {
    // Need exactly 3 instructions
    if insts.len() != 3 {
        return None;
    }

    let inst0 = insts[0];
    let inst1 = insts[1];
    let inst2 = insts[2];

    // Instruction 0: STMIA Rb!, {Rs} - single register, post-increment
    if inst0.opcode != "STMIA" {
        return None;
    }
    // Check for writeback (!) and single register in list
    let stmia_uses = &inst0.operands;
    if stmia_uses.len() != 2 {
        return None; // Must be exactly 2 operands: base reg and single register to store
    }
    let Operand::Register(rb) = stmia_uses[0] else {
        return None;
    };
    let Operand::Register(rs) = stmia_uses[1] else {
        return None;
    };

    // Verify writeback is present (check raw encoding or operand flags)
    // For STMIA with writeback, the disassembler should indicate it
    // We'll check the opcode more carefully - STMIA with ! is typically "STMIA!" or has writeback flag
    // Looking at the disassembler output, writeback STMIA appears as "STMIA R0!, {R2}"
    // The operand parsing should have captured this

    // Instruction 1: SUB Rc, #4 - sets flags
    if inst1.opcode != "SUB" {
        return None;
    }
    let sub_uses = &inst1.operands;
    if sub_uses.len() < 2 {
        return None;
    }
    let Operand::Register(rc) = sub_uses[0] else {
        return None;
    };
    // Check for immediate 4
    let is_sub_4 = if sub_uses.len() >= 2 {
        matches!(sub_uses[1], Operand::Immediate(4))
    } else {
        false
    };
    if !is_sub_4 {
        return None;
    }
    if !inst1.sets_flags {
        return None; // SUB must set flags for BNE to work
    }

    // Instruction 2: BNE back to instruction 0
    if inst2.opcode != "BNE" {
        return None;
    }
    let bne_target = if let Some(Operand::Immediate(target)) = inst2.operands.first() {
        *target as u64
    } else {
        return None;
    };
    if bne_target != inst0.address as u64 {
        return None; // Must branch back to the STMIA
    }

    // Pattern matched! Return (base_reg, source_reg, counter_reg, fallthrough_addr)
    Some((rb, rs, rc, inst2.address as u64 + inst2.width as u64)) // Fallthrough is after BNE
}

/// Helper: extract BL/BLX targets from a function's instructions
pub(crate) fn extract_bl_targets(
    func_instructions: &[&DecodedInstruction],
) -> Vec<(u64, ArmMode)> {
    let mut targets = Vec::new();
    let mut lr_value: Option<u64> = None; // Track LR (r14) for BL_PREFIX/BL_SUFFIX

    for inst in func_instructions {
        let opcode_upper = inst.opcode.to_uppercase();

        // Track LR value for BL_PREFIX/BL_SUFFIX pattern
        if opcode_upper == "BL_PREFIX" {
            // BL_PREFIX stores the upper target bits in LR
            for op in &inst.operands {
                if let Operand::Immediate(prefix_target) = op {
                    if *prefix_target >= 0x08000000 && *prefix_target < 0x0A000000 {
                        lr_value = Some(*prefix_target as u64);
                    }
                }
            }
            continue; // BL_PREFIX doesn't branch directly
        }

        if opcode_upper == "BL_SUFFIX" {
            // BL_SUFFIX combines LR (from BL_PREFIX) with the lower offset
            for op in &inst.operands {
                if let Operand::Immediate(suffix_offset) = op {
                    if let Some(lr) = lr_value {
                        let suffix_shifted = *suffix_offset as u64; // Already shifted by 1
                        let target = lr.wrapping_add(suffix_shifted);
                        if (0x08000000..0x0A000000).contains(&target) {
                            let target_mode = inst.mode; // BL_SUFFIX preserves mode
                            targets.push((target, target_mode));
                        }
                    }
                }
            }
            // Reset LR after BL_SUFFIX
            lr_value = None;
            continue;
        }

        // Check for BL, BLX (both ARM and Thumb)
        if opcode_upper == "BL" || opcode_upper == "BLX" {
            // Try to extract immediate target from operands
            for op in &inst.operands {
                if let Operand::Immediate(target) = op {
                    // Only include valid ROM addresses
                    if *target >= 0x08000000 && *target < 0x0A000000 {
                        // Determine target mode based on instruction type:
                        // BL preserves mode; BLX switches mode
                        let target_mode = if opcode_upper == "BLX" {
                            match inst.mode {
                                ArmMode::Arm => ArmMode::Thumb,
                                ArmMode::Thumb => ArmMode::Arm,
                            }
                        } else {
                            inst.mode
                        };
                        let target_addr = *target; // already even, no Thumb bit to strip
                        targets.push((target_addr as u64, target_mode));
                    }
                }
            }
        }
    }
    targets
}


// ============================================================================
// Unit Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use gbatopy_disasm::{operand::ShiftAmount, operand::ShiftType, ArmMode, Condition, DecodedInstruction, Operand};

    fn make_inst(
        opcode: &str,
        operands: Vec<Operand>,
        sets_flags: bool,
        mode: ArmMode,
        addr: u32,
    ) -> DecodedInstruction {
        DecodedInstruction {
            address: addr,
            opcode: opcode.to_string(),
            operands,
            condition: Some(Condition::Al),
            mode,
            raw: 0,
            sets_flags,
            width: if mode == ArmMode::Arm { 4 } else { 2 },
            is_data: false,
        }
    }

    // === is_conditional_branch tests ===
    #[test]
    fn test_is_conditional_branch_eq() {
        assert!(is_conditional_branch("BEQ"));
    }

    #[test]
    fn test_is_conditional_branch_ne() {
        assert!(is_conditional_branch("BNE"));
    }

    #[test]
    fn test_is_conditional_branch_all_variants() {
        // All conditional branch variants
        assert!(is_conditional_branch("BCS"));
        assert!(is_conditional_branch("BCC"));
        assert!(is_conditional_branch("BMI"));
        assert!(is_conditional_branch("BPL"));
        assert!(is_conditional_branch("BVS"));
        assert!(is_conditional_branch("BVC"));
        assert!(is_conditional_branch("BHI"));
        assert!(is_conditional_branch("BLS"));
        assert!(is_conditional_branch("BGE"));
        assert!(is_conditional_branch("BLT"));
        assert!(is_conditional_branch("BGT"));
        assert!(is_conditional_branch("BLE"));
        assert!(is_conditional_branch("BAL"));
        assert!(is_conditional_branch("BNV"));
    }

    #[test]
    fn test_is_conditional_branch_not_branch() {
        // BIC is NOT a branch (bit-clear instruction)
        assert!(!is_conditional_branch("BIC"));
        // BL is unconditional
        assert!(!is_conditional_branch("BL"));
        // BX is unconditional
        assert!(!is_conditional_branch("BX"));
        // Data processing
        assert!(!is_conditional_branch("ADDeq"));
        assert!(!is_conditional_branch("MOVs"));
    }

    // === is_conditional_non_branch tests ===
    #[test]
    fn test_is_conditional_non_branch_ldreq() {
        let inst = make_inst(
            "LDReq",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(is_conditional_non_branch(&inst));
    }

    #[test]
    fn test_is_conditional_non_branch_addne() {
        let inst = make_inst(
            "ADDne",
            vec![Operand::Register(0), Operand::Register(1), Operand::Immediate(5)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(is_conditional_non_branch(&inst));
    }

    #[test]
    fn test_is_conditional_non_branch_unconditional() {
        // No condition code
        let inst = make_inst(
            "ADD",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(!is_conditional_non_branch(&inst));
    }

    #[test]
    fn test_is_conditional_non_branch_al() {
        // AL (always) is not conditional
        let inst = make_inst(
            "ADDal",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(!is_conditional_non_branch(&inst));
    }

    #[test]
    fn test_is_conditional_non_branch_branch() {
        // Branches are NOT conditional non-branches
        let inst = make_inst(
            "BNE",
            vec![Operand::Immediate(0x100)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(!is_conditional_non_branch(&inst));
    }

    // === writes_r15 tests ===
    #[test]
    fn test_writes_r15_branch() {
        let inst = make_inst(
            "B",
            vec![Operand::Immediate(0x100)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(writes_r15(&inst));
    }

    #[test]
    fn test_writes_r15_bl() {
        let inst = make_inst(
            "BL",
            vec![Operand::Immediate(0x100)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(writes_r15(&inst));
    }

    #[test]
    fn test_writes_r15_bx() {
        let inst = make_inst(
            "BX",
            vec![Operand::Register(14)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(writes_r15(&inst));
    }

    #[test]
    fn test_writes_r15_beq() {
        let inst = make_inst(
            "BEQ",
            vec![Operand::Immediate(0x100)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(writes_r15(&inst));
    }

    #[test]
    fn test_writes_r15_mov_pc() {
        let inst = make_inst(
            "MOV",
            vec![Operand::Register(15), Operand::Register(14)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(writes_r15(&inst));
    }

    #[test]
    fn test_writes_r15_ldm_pc() {
        let inst = make_inst(
            "LDMIA",
            vec![Operand::Register(13), Operand::MemoryAddress {
                base: 13,
                offset: gbatopy_disasm::operand::AddressingMode::Multi {
                    base: 13,
                    registers: vec![0, 1, 15],
                    increment: true,
                    pre_index: true,
                    writeback: false,
                    s_bit: false,
                },
                writeback: false,
            }],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(writes_r15(&inst));
    }

    #[test]
    fn test_writes_r15_pop_pc() {
        let inst = make_inst(
            "POP",
            vec![Operand::Register(15)],
            false,
            ArmMode::Thumb,
            0x08000000,
        );
        assert!(writes_r15(&inst));
    }

    #[test]
    fn test_writes_r15_not_r15() {
        let inst = make_inst(
            "MOV",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(!writes_r15(&inst));
    }

    #[test]
    fn test_writes_r15_cmp() {
        // CMP doesn't write any register
        let inst = make_inst(
            "CMP",
            vec![Operand::Register(0), Operand::Immediate(5)],
            true,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(!writes_r15(&inst));
    }

    #[test]
    fn test_writes_r15_str() {
        // STR doesn't write registers
        let inst = make_inst(
            "STR",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(!writes_r15(&inst));
    }

    // === reads_r15 tests ===
    #[test]
    fn test_reads_r15_branch() {
        let inst = make_inst(
            "B",
            vec![Operand::Immediate(0x100)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(reads_r15(&inst));
    }

    #[test]
    fn test_reads_r15_blx_register() {
        let inst = make_inst(
            "BLX",
            vec![Operand::Register(14)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(reads_r15(&inst));
    }

    #[test]
    fn test_reads_r15_mov_r15_source() {
        let inst = make_inst(
            "MOV",
            vec![Operand::Register(0), Operand::Register(15)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(reads_r15(&inst));
    }

    #[test]
    fn test_reads_r15_shifted_r15() {
        let inst = make_inst(
            "ADD",
            vec![Operand::Register(0), Operand::ShiftedRegister {
                reg: 15,
                shift: ShiftType::Lsl,
                amount: ShiftAmount::Immediate(2),
            }],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(reads_r15(&inst));
    }

    #[test]
    fn test_reads_r15_memory_r15_base() {
        let inst = make_inst(
            "LDR",
            vec![Operand::Register(0), Operand::MemoryAddress {
                base: 15,
                offset: gbatopy_disasm::operand::AddressingMode::ImmediateOffset(4),
                writeback: false,
            }],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(reads_r15(&inst));
    }

    #[test]
    fn test_reads_r15_not_r15() {
        let inst = make_inst(
            "ADD",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000000,
        );
        assert!(!reads_r15(&inst));
    }

    // === detect_memset_loop_pattern tests ===
    #[test]
    fn test_detect_memset_loop_pattern_match() {
        let inst0 = make_inst(
            "STMIA",
            vec![Operand::Register(0), Operand::Register(2)],
            false,
            ArmMode::Thumb,
            0x08000100,
        );
        let inst1 = make_inst(
            "SUB",
            vec![Operand::Register(3), Operand::Immediate(4)],
            true,
            ArmMode::Thumb,
            0x08000102,
        );
        let inst2 = make_inst(
            "BNE",
            vec![Operand::Immediate(0x08000100)],
            false,
            ArmMode::Thumb,
            0x08000104,
        );

        let insts = vec![&inst0, &inst1, &inst2];
        let result = detect_memset_loop_pattern(&insts);

        assert!(result.is_some());
        let (rb, rs, rc, fallthrough) = result.unwrap();
        assert_eq!(rb, 0);
        assert_eq!(rs, 2);
        assert_eq!(rc, 3);
        assert_eq!(fallthrough, 0x08000106); // After BNE
    }

    #[test]
    fn test_detect_memset_loop_pattern_wrong_instructions() {
        // Wrong first instruction
        let inst0 = make_inst(
            "STR",
            vec![Operand::Register(0), Operand::Register(2)],
            false,
            ArmMode::Thumb,
            0x08000100,
        );
        let inst1 = make_inst(
            "SUB",
            vec![Operand::Register(3), Operand::Immediate(4)],
            true,
            ArmMode::Thumb,
            0x08000102,
        );
        let inst2 = make_inst(
            "BNE",
            vec![Operand::Immediate(0x08000100)],
            false,
            ArmMode::Thumb,
            0x08000104,
        );

        let insts = vec![&inst0, &inst1, &inst2];
        assert!(detect_memset_loop_pattern(&insts).is_none());
    }

    #[test]
    fn test_detect_memset_loop_pattern_wrong_sub() {
        let inst0 = make_inst(
            "STMIA",
            vec![Operand::Register(0), Operand::Register(2)],
            false,
            ArmMode::Thumb,
            0x08000100,
        );
        // Wrong immediate value
        let inst1 = make_inst(
            "SUB",
            vec![Operand::Register(3), Operand::Immediate(8)],
            true,
            ArmMode::Thumb,
            0x08000102,
        );
        let inst2 = make_inst(
            "BNE",
            vec![Operand::Immediate(0x08000100)],
            false,
            ArmMode::Thumb,
            0x08000104,
        );

        let insts = vec![&inst0, &inst1, &inst2];
        assert!(detect_memset_loop_pattern(&insts).is_none());
    }

    #[test]
    fn test_detect_memset_loop_pattern_wrong_branch_target() {
        let inst0 = make_inst(
            "STMIA",
            vec![Operand::Register(0), Operand::Register(2)],
            false,
            ArmMode::Thumb,
            0x08000100,
        );
        let inst1 = make_inst(
            "SUB",
            vec![Operand::Register(3), Operand::Immediate(4)],
            true,
            ArmMode::Thumb,
            0x08000102,
        );
        // Wrong branch target
        let inst2 = make_inst(
            "BNE",
            vec![Operand::Immediate(0x08000200)],
            false,
            ArmMode::Thumb,
            0x08000104,
        );

        let insts = vec![&inst0, &inst1, &inst2];
        assert!(detect_memset_loop_pattern(&insts).is_none());
    }

    #[test]
    fn test_detect_memset_loop_pattern_not_sets_flags() {
        let inst0 = make_inst(
            "STMIA",
            vec![Operand::Register(0), Operand::Register(2)],
            false,
            ArmMode::Thumb,
            0x08000100,
        );
        // SUB doesn't set flags
        let inst1 = make_inst(
            "SUB",
            vec![Operand::Register(3), Operand::Immediate(4)],
            false,
            ArmMode::Thumb,
            0x08000102,
        );
        let inst2 = make_inst(
            "BNE",
            vec![Operand::Immediate(0x08000100)],
            false,
            ArmMode::Thumb,
            0x08000104,
        );

        let insts = vec![&inst0, &inst1, &inst2];
        assert!(detect_memset_loop_pattern(&insts).is_none());
    }

    #[test]
    fn test_detect_memset_loop_pattern_wrong_length() {
        // Too few instructions
        let inst0 = make_inst(
            "STMIA",
            vec![Operand::Register(0), Operand::Register(2)],
            false,
            ArmMode::Thumb,
            0x08000100,
        );
        let inst1 = make_inst(
            "SUB",
            vec![Operand::Register(3), Operand::Immediate(4)],
            true,
            ArmMode::Thumb,
            0x08000102,
        );

        let insts = vec![&inst0, &inst1];
        assert!(detect_memset_loop_pattern(&insts).is_none());
    }

    // === extract_bl_targets tests ===
    #[test]
    fn test_extract_bl_targets_bl() {
        let inst0 = make_inst(
            "BL",
            vec![Operand::Immediate(0x08000500)],
            false,
            ArmMode::Arm,
            0x08000100,
        );

        let insts = vec![&inst0];
        let targets = extract_bl_targets(&insts);

        assert_eq!(targets.len(), 1);
        assert_eq!(targets[0].0, 0x08000500);
        assert_eq!(targets[0].1, ArmMode::Arm);
    }

    #[test]
    fn test_extract_bl_targets_blx() {
        let inst0 = make_inst(
            "BLX",
            vec![Operand::Immediate(0x08000600)],
            false,
            ArmMode::Arm,
            0x08000100,
        );

        let insts = vec![&inst0];
        let targets = extract_bl_targets(&insts);

        assert_eq!(targets.len(), 1);
        assert_eq!(targets[0].0, 0x08000600);
        assert_eq!(targets[0].1, ArmMode::Thumb); // BLX switches mode
    }

    #[test]
    fn test_extract_bl_targets_bl_suffix() {
        let inst0 = make_inst(
            "BL_PREFIX",
            vec![Operand::Immediate(0x08000000)],
            false,
            ArmMode::Thumb,
            0x08000100,
        );
        let inst1 = make_inst(
            "BL_SUFFIX",
            vec![Operand::Immediate(0x100)],
            false,
            ArmMode::Thumb,
            0x08000102,
        );

        let insts = vec![&inst0, &inst1];
        let targets = extract_bl_targets(&insts);

        assert_eq!(targets.len(), 1);
        assert_eq!(targets[0].0, 0x08000100); // 0x08000000 + 0x100
        assert_eq!(targets[0].1, ArmMode::Thumb);
    }

    #[test]
    fn test_extract_bl_targets_invalid_address() {
        // Address outside ROM range
        let inst0 = make_inst(
            "BL",
            vec![Operand::Immediate(0x02000000)], // EWRAM, not ROM
            false,
            ArmMode::Arm,
            0x08000100,
        );

        let insts = vec![&inst0];
        let targets = extract_bl_targets(&insts);

        assert_eq!(targets.len(), 0);
    }

    #[test]
    fn test_extract_bl_targets_empty() {
        let insts: Vec<&DecodedInstruction> = vec![];
        let targets = extract_bl_targets(&insts);
        assert_eq!(targets.len(), 0);
    }

    #[test]
    fn test_extract_bl_targets_no_bl_instructions() {
        let inst0 = make_inst(
            "MOV",
            vec![Operand::Register(0), Operand::Register(1)],
            false,
            ArmMode::Arm,
            0x08000100,
        );
        let inst1 = make_inst(
            "ADD",
            vec![Operand::Register(2), Operand::Register(3)],
            false,
            ArmMode::Arm,
            0x08000104,
        );

        let insts = vec![&inst0, &inst1];
        let targets = extract_bl_targets(&insts);

        assert_eq!(targets.len(), 0);
    }
}
// End of Extracted Helper Functions
// ============================================================================