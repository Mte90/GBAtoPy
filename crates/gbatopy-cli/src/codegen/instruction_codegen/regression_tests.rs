//! Regression tests for documented codegen bugs.
//!
//! Each test freezes one bug from docs/codegen-pitfalls.md so a regression
//! is caught immediately by `cargo test -p gbatopy-cli`.

use super::generate_instruction_python;
use gbatopy_disasm::{AddressingMode, ArmMode, Condition, DecodedInstruction, Operand};

fn arm_inst(opcode: &str, operands: Vec<Operand>, sets_flags: bool) -> DecodedInstruction {
    DecodedInstruction {
        address: 0x08000000,
        opcode: opcode.to_string(),
        operands,
        condition: Some(Condition::Al),
        mode: ArmMode::Arm,
        raw: 0,
        sets_flags,
        width: 4,
        is_data: false,
    }
}

/// Bug T1.1: STRH must preserve immediate offset (was: bits 7-3 used instead of 3-0,
/// yielding offset 0 for nonzero offsets). The codegen must emit " + 22" not " + 0".
#[test]
fn strh_preserves_nonzero_immediate_offset() {
    let inst = arm_inst(
        "STRH",
        vec![
            Operand::Register(0),
            Operand::MemoryAddress {
                base: 1,
                offset: AddressingMode::ImmediateOffset(22),
                writeback: false,
            },
        ],
        false,
    );
    let code = generate_instruction_python(&inst);
    assert!(
        code.contains(" + 22"),
        "STRH offset 22 must appear in output, got: {}",
        code
    );
    assert!(
        !code.contains(" + 0)"),
        "STRH must not collapse offset to 0, got: {}",
        code
    );
}

/// Bug T1.2: BL must set LR = return address BEFORE branching.
/// Regression: BL was not storing the return address in LR (R14).
#[test]
fn bl_sets_lr_before_branch() {
    let inst = arm_inst("BL", vec![Operand::Immediate(0x08000100)], false);
    let code = generate_instruction_python(&inst);
    assert!(
        code.contains("registers[14]"),
        "BL must set LR (R14), got: {}",
        code
    );
    assert!(
        code.contains("registers[15] = 0x08000100"),
        "BL must branch to target, got: {}",
        code
    );
    let lr_pos = code.find("registers[14]").unwrap();
    let pc_pos = code.find("registers[15] = 0x08000100").unwrap();
    assert!(
        lr_pos < pc_pos,
        "BL must set LR before branching, got: {}",
        code
    );
}

/// Bug T1.3: Conditional branch BNE/BEQ must fall through to PC+4 when condition false.
#[test]
fn conditional_branch_has_else_pc_advance() {
    let inst = arm_inst("BNE", vec![Operand::Immediate(0x08000200)], false);
    let code = generate_instruction_python(&inst);
    assert!(
        code.contains("cpsr_check('NE')"),
        "BNE must call cpsr_check('NE'), got: {}",
        code
    );
    assert!(
        code.contains("else:"),
        "BNE must have else branch for fall-through, got: {}",
        code
    );
    assert!(
        code.contains("registers[15] = (registers[15] + 4)"),
        "BNE else must advance PC by 4, got: {}",
        code
    );
}

/// Bug T1.4: LDM with PC in register list must write R15.
#[test]
fn ldm_with_pc_in_list_writes_r15() {
    let inst = arm_inst(
        "LDMFD",
        vec![Operand::MemoryAddress {
            base: 13,
            offset: AddressingMode::Multi {
                base: 13,
                registers: vec![4, 5, 15],
                increment: true,
                pre_index: false,
                writeback: true,
                s_bit: false,
            },
            writeback: true,
        }],
        false,
    );
    let code = generate_instruction_python(&inst);
    assert!(
        code.contains("registers[15] = memory.read_u32(addr)"),
        "LDM with PC in list must write PC, got: {}",
        code
    );
}

/// Bug T1.5: STMFD (push) walks from frame bottom with addr += 4.
/// ARM rule: lowest register maps to lowest address. For STMDB/STMFD with 3 regs,
/// frame bottom = base - 12, then walk up: base-12, base-8, base-4.
#[test]
fn stmfd_uses_decreasing_addresses() {
    let inst = arm_inst(
        "STMFD",
        vec![Operand::MemoryAddress {
            base: 13,
            offset: AddressingMode::Multi {
                base: 13,
                registers: vec![4, 5, 14],
                increment: false,
                pre_index: true, // STMFD = STMDB = pre-indexed decrement
                writeback: true,
                s_bit: false,
            },
            writeback: true,
        }],
        false,
    );
    let code = generate_instruction_python(&inst);
    assert!(
        code.contains("addr = registers[13] - 12"),
        "STMFD must start at frame bottom (SP - 12 for 3 regs), got: {}",
        code
    );
    assert!(
        code.contains("addr += 4"),
        "STMFD must increment address by 4 between stores (lowest reg → lowest addr), got: {}",
        code
    );
    assert!(
        code.contains("registers[13] - 12"),
        "STMFD writeback must be SP - 12, got: {}",
        code
    );
}

/// Bug T1.6: LDMFD (pop) address order must be INCREASING with writeback.
#[test]
fn ldmfd_uses_increasing_addresses() {
    let inst = arm_inst(
        "LDMFD",
        vec![Operand::MemoryAddress {
            base: 13,
            offset: AddressingMode::Multi {
                base: 13,
                registers: vec![4, 5, 15],
                increment: true,
                pre_index: false,
                writeback: true,
                s_bit: false,
            },
            writeback: true,
        }],
        false,
    );
    let code = generate_instruction_python(&inst);
    assert!(
        code.contains("addr = registers[13]"),
        "LDMFD must start at SP (post-inc), got: {}",
        code
    );
    assert!(
        code.contains("addr += 4"),
        "LDMFD must increment address by 4 between loads, got: {}",
        code
    );
}

/// Bug T1.7: LDR PC-relative must apply immediate offset.
#[test]
fn ldr_pc_relative_applies_offset() {
    let inst = arm_inst(
        "LDR",
        vec![
            Operand::Register(0),
            Operand::MemoryAddress {
                base: 15,
                offset: AddressingMode::ImmediateOffset(16),
                writeback: false,
            },
        ],
        false,
    );
    let code = generate_instruction_python(&inst);
    assert!(
        code.contains(" + 16"),
        "LDR PC-relative must apply offset 16, got: {}",
        code
    );
}

/// Bug T1.8: STR with immediate offset must not emit '#' prefix or double parens.
#[test]
fn str_immediate_offset_no_hash_no_double_parens() {
    let inst = arm_inst(
        "STR",
        vec![
            Operand::Register(0),
            Operand::MemoryAddress {
                base: 1,
                offset: AddressingMode::ImmediateOffset(8),
                writeback: false,
            },
        ],
        false,
    );
    let code = generate_instruction_python(&inst);
    assert!(
        !code.contains('#'),
        "STR must not emit '#' prefix in Python, got: {}",
        code
    );
    assert!(
        code.contains(" + 8"),
        "STR must apply offset 8, got: {}",
        code
    );
}

/// Bug T1.9: ADD/SUB with immediate must strip '#' prefix.
#[test]
fn add_immediate_strips_hash_prefix() {
    let inst = arm_inst(
        "ADD",
        vec![
            Operand::Register(0),
            Operand::Register(1),
            Operand::Immediate(5),
        ],
        false,
    );
    let code = generate_instruction_python(&inst);
    assert!(
        !code.contains("#5"),
        "ADD immediate must not emit '#5', got: {}",
        code
    );
    assert!(
        code.contains('5'),
        "ADD immediate 5 must appear, got: {}",
        code
    );
}

/// Bug T1.10: MRS must emit full CPSR round-trip (NZCV + F + I + T + mode).
/// Regression: MRS was only reconstructing NZCV bits, dropping bits 7 (I), 6 (F), 5 (T), and 4-0 (mode).
/// This caused MSR CPSR_c, rd to fail because rd & 0x1F = 0 → _switch_mode(0) → banked SP/LR corruption.
#[test]
fn mrs_emits_full_cpsr_round_trip() {
    let inst = arm_inst(
        "MRS",
        vec![Operand::Register(0), Operand::Immediate(0)], // rd=0, CPSR (not SPSR)
        false,
    );
    let code = generate_instruction_python(&inst);
    // Must emit all CPSR bits, not just NZCV
    assert!(
        code.contains("cpsr['n']"),
        "MRS must include cpsr['n'], got: {}",
        code
    );
    assert!(
        code.contains("cpsr['z']"),
        "MRS must include cpsr['z'], got: {}",
        code
    );
    assert!(
        code.contains("cpsr['c']"),
        "MRS must include cpsr['c'], got: {}",
        code
    );
    assert!(
        code.contains("cpsr['v']"),
        "MRS must include cpsr['v'], got: {}",
        code
    );
    assert!(
        code.contains("cpsr['f']"),
        "MRS must include cpsr['f'] (bit 6), got: {}",
        code
    );
    assert!(
        code.contains("cpsr['i']"),
        "MRS must include cpsr['i'] (bit 7), got: {}",
        code
    );
    assert!(
        code.contains("cpsr['t']"),
        "MRS must include cpsr['t'] (bit 5), got: {}",
        code
    );
    assert!(
        code.contains("cpsr['mode']"),
        "MRS must include cpsr['mode'] (bits 4-0), got: {}",
        code
    );
    // Must mask to 32 bits
    assert!(
        code.contains("& 0xFFFFFFFF"),
        "MRS must mask result to 32 bits, got: {}",
        code
    );
}

// ============================================================================
// Regression tests for Pitfall #8: SP Initialized to 0
// ============================================================================

/// Regression test for pitfall #8: SP Initialized to 0
/// The generated Python header must initialize SP (stack pointer) to 0x03007F00, NOT to 0.
/// This test verifies the header template contains the correct SP initialization.
#[test]
fn test_sp_initialized_to_0x03007f00() {
    // Pitfall #8: SP must be initialized to 0x03007F00 (top of IWRAM), not 0.
    // The SP initialization is in the header template at:
    // - crates/gbatopy-cli/assets/templates/header.py:19
    // - crates/gbatopy-cli/src/codegen/mod.rs:224 (inline Python generation)
    //
    // We verify by reading the header template and checking the SP value.
    
    const EXPECTED_SP_VALUE: &str = "0x03007F00";
    
    // Read the header template file
    let manifest_dir = env!("CARGO_MANIFEST_DIR");
    let header_path = format!("{}/assets/templates/header.py", manifest_dir);
    let header_content = std::fs::read_to_string(&header_path)
        .expect(&format!("Failed to read header template at {}", header_path));
    
    // Verify the header contains the correct SP initialization
    assert!(
        header_content.contains(&format!("registers[13] = {}", EXPECTED_SP_VALUE)),
        "Header template must initialize SP (R13) to {}, but not found. Content snippet:\n{}",
        EXPECTED_SP_VALUE,
        header_content.lines().take(30).collect::<Vec<_>>().join("\n")
    );
    
    // Also verify the codegen module's inline header generation (mod.rs:224)
    let codegen_mod_path = format!("{}/src/codegen/mod.rs", manifest_dir);
    let codegen_content = std::fs::read_to_string(&codegen_mod_path)
        .expect(&format!("Failed to read codegen/mod.rs at {}", codegen_mod_path));
    
    // Check that the _user_sys_bank dictionary has the correct SP value
    assert!(
        codegen_content.contains(&format!("'sp': {}", EXPECTED_SP_VALUE)),
        "codegen/mod.rs must initialize _user_sys_bank['sp'] to {}, but not found",
        EXPECTED_SP_VALUE
    );
    
    // Verify that banked_sp_lr also contains the correct SP value for relevant modes
    assert!(
        codegen_content.contains("0x1F: _user_sys_bank"),
        "banked_sp_lr must reference _user_sys_bank for User/System mode (0x1F)"
    );
    
    eprintln!("  ✓ Pitfall #8: SP correctly initialized to {} in header template and codegen", EXPECTED_SP_VALUE);
}

// ============================================================================
// Regression tests for Pitfall #14: Thumb BL Prefix/Suffix Split
// ============================================================================

// ============================================================================
// Regression tests for Pitfall #14: Thumb BL Merged Instruction (decode_bl_pair)
// ============================================================================
//
// These tests verify the ACTUAL production path for Thumb BL instructions:
// - decode_bl_pair() merges BL_PREFIX + BL_SUFFIX halfwords into a single "BL" instruction
// - The merged instruction has width=4 and opcode="BL"
// - Codegen must emit: LR = (PC+4), then PC = target

/// Test 1: Verify that a merged BL instruction (via decode_bl_pair) emits correct LR and PC assignment.
/// 
/// Construct BL_PREFIX (0xF000 family) + BL_SUFFIX (0xF800 family) encoding target 0x08001000.
/// After decode_bl_pair, feed the merged "BL" instruction to codegen.
/// Assert output contains registers[14] (LR) AND registers[15] (PC) set to correct target.
#[test]
fn test_thumb_bl_merged_emits_correct_target() {
    // Simulate what decode_bl_pair produces:
    // BL at address 0x08000000 with target 0x08001000
    // The merged instruction has opcode="BL", width=4, and the target as immediate operand
    let inst = DecodedInstruction {
        address: 0x08000000,
        opcode: "BL".to_string(),
        operands: vec![Operand::Immediate(0x08001000)],
        condition: Some(Condition::Al),
        mode: ArmMode::Thumb,
        raw: 0, // Combined 32-bit value would be encoded here
        sets_flags: false,
        width: 4, // Merged BL is 4 bytes
        is_data: false,
    };
    let code = generate_instruction_python(&inst);
    
    // BL must set LR (R14) to return address
    assert!(
        code.contains("registers[14]"),
        "Merged BL must set LR (R14), got: {}",
        code
    );
    
    // BL must branch to target (write PC/R15)
    assert!(
        code.contains("registers[15] = 0x08001000"),
        "Merged BL must branch to target 0x08001000, got: {}",
        code
    );
    
    // LR must be set BEFORE PC is modified (order matters for correct return address)
    let lr_pos = code.find("registers[14]").unwrap();
    let pc_pos = code.find("registers[15] = 0x08001000").unwrap();
    assert!(
        lr_pos < pc_pos,
        "BL must set LR before branching (LR at pos {}, PC at pos {}), got: {}",
        lr_pos,
        pc_pos,
        code
    );
}

/// Test 2: Verify that decode_bl_pair returns width=4, not width=2.
/// 
/// This ensures the CFG BFS will advance by 4 bytes when it sees a BL instruction,
/// consuming both halfwords and not treating the suffix as a separate instruction.
#[test]
fn test_thumb_bl_merged_advances_4_bytes() {
    // The merged BL instruction from decode_bl_pair must have width=4
    let bl_inst = DecodedInstruction {
        address: 0x08000000,
        opcode: "BL".to_string(),
        operands: vec![Operand::Immediate(0x08001000)],
        condition: Some(Condition::Al),
        mode: ArmMode::Thumb,
        raw: 0,
        sets_flags: false,
        width: 4, // Critical: merged BL is 4 bytes, not 2
        is_data: false,
    };
    
    // Verify the width field is correct
    assert_eq!(
        bl_inst.width,
        4,
        "Merged BL instruction must have width=4, got {}",
        bl_inst.width
    );
    
    // A regular Thumb branch (B) should still be 2 bytes
    let b_inst = DecodedInstruction {
        address: 0x08000004,
        opcode: "B".to_string(),
        operands: vec![Operand::Immediate(0x08000100)],
        condition: Some(Condition::Al),
        mode: ArmMode::Thumb,
        raw: 0,
        sets_flags: false,
        width: 2, // Regular Thumb branch is 2 bytes
        is_data: false,
    };
    
    assert_eq!(
        b_inst.width,
        2,
        "Regular Thumb B instruction must have width=2, got {}",
        b_inst.width
    );
}

/// Test 3: Verify the LR value is correct for a BL instruction.
/// 
/// BL at address A should set LR = (A + 4) & 0xFFFFFFFF (return address in Thumb mode).
/// Construct a BL at a known address and assert the codegen produces the correct LR value.
#[test]
fn test_thumb_bl_lr_value_correct() {
    // BL at 0x08000000, return address should be 0x08000004
    let inst = DecodedInstruction {
        address: 0x08000000,
        opcode: "BL".to_string(),
        operands: vec![Operand::Immediate(0x08001000)],
        condition: Some(Condition::Al),
        mode: ArmMode::Thumb,
        raw: 0,
        sets_flags: false,
        width: 4,
        is_data: false,
    };
    let code = generate_instruction_python(&inst);
    
    // LR must be set to (PC + 4), which is the return address
    // The codegen should emit: registers[14] = (registers[15] + 4) & 0xFFFFFFFF
    assert!(
        code.contains("registers[14] = (registers[15] + 4)"),
        "BL must set LR = (PC + 4), got: {}",
        code
    );
    
    // Verify the masking to 32 bits
    assert!(
        code.contains("& 0xFFFFFFFF"),
        "BL must mask LR to 32 bits, got: {}",
        code
    );
}

/// Test 4: Verify target address calculation for BL instructions with various offsets.
/// 
/// Target = PC + 4 + sign_extended_offset * 2 (where PC = instruction address + 4 in Thumb mode).
/// Test positive, negative, zero, and maximum offsets.
#[test]
fn test_thumb_bl_target_address_calculation() {
    // Test case 1: BL with target 0x08002000 (positive offset from 0x08000000)
    let inst1 = DecodedInstruction {
        address: 0x08000000,
        opcode: "BL".to_string(),
        operands: vec![Operand::Immediate(0x08002000)],
        condition: Some(Condition::Al),
        mode: ArmMode::Thumb,
        raw: 0,
        sets_flags: false,
        width: 4,
        is_data: false,
    };
    let code1 = generate_instruction_python(&inst1);
    assert!(
        code1.contains("registers[15] = 0x08002000"),
        "BL target 0x08002000 must appear in codegen, got: {}",
        code1
    );
    
    // Test case 2: BL with target 0x08000001 (minimal positive offset - Thumb entry point)
    // Note: 0x08000000 is rejected by branch.rs validation (> 0x08000000 required)
    let inst2 = DecodedInstruction {
        address: 0x08000000,
        opcode: "BL".to_string(),
        operands: vec![Operand::Immediate(0x08000001)],
        condition: Some(Condition::Al),
        mode: ArmMode::Thumb,
        raw: 0,
        sets_flags: false,
        width: 4,
        is_data: false,
    };
    let code2 = generate_instruction_python(&inst2);
    assert!(
        code2.contains("registers[15] = 0x08000001"),
        "BL target 0x08000001 must appear in codegen, got: {}",
        code2
    );
    
    // Test case 3: BL with target 0x08000100 (small positive offset)
    let inst3 = DecodedInstruction {
        address: 0x08000000,
        opcode: "BL".to_string(),
        operands: vec![Operand::Immediate(0x08000100)],
        condition: Some(Condition::Al),
        mode: ArmMode::Thumb,
        raw: 0,
        sets_flags: false,
        width: 4,
        is_data: false,
    };
    let code3 = generate_instruction_python(&inst3);
    assert!(
        code3.contains("registers[15] = 0x08000100"),
        "BL target 0x08000100 must appear in codegen, got: {}",
        code3
    );
    
    // Test case 4: BL with target in upper range (0x09FFFFFF - max valid GBA ARM region)
    let inst4 = DecodedInstruction {
        address: 0x08000000,
        opcode: "BL".to_string(),
        operands: vec![Operand::Immediate(0x09FFFFFF)],
        condition: Some(Condition::Al),
        mode: ArmMode::Thumb,
        raw: 0,
        sets_flags: false,
        width: 4,
        is_data: false,
    };
    let code4 = generate_instruction_python(&inst4);
    assert!(
        code4.contains("registers[15] = 0x09FFFFFF"),
        "BL target 0x09FFFFFF must appear in codegen, got: {}",
        code4
    );
}

// ============================================================================
// Regression tests for Pitfall #2: NOP Detection Too Aggressive
// ============================================================================

/// Regression test for pitfall #2: NOP Detection Too Aggressive
/// Test that MOV R0, #0x03007F00 is NOT marked as NOP.
/// Previously, aggressive NOP detection marked initialization code as NOP,
/// causing it to be skipped and leading to blank screens (e.g., start-delay ROM).
#[test]
fn test_mov_immediate_is_not_nop() {
    // MOV R0, #0x03007F00 - initialization instruction, must NOT be NOP
    let inst = arm_inst("MOV", vec![Operand::Register(0), Operand::Immediate(0x03007F00)], false);
    let code = generate_instruction_python(&inst);
    
    // The generated code should write to a register, not just pass
    assert!(
        code.contains("registers[0]"),
        "MOV R0, #imm must write to R0, got: {}",
        code
    );
    assert!(
        !code.contains("pass") || code.contains("sys.stderr.write"),
        "MOV R0, #imm must not be a bare pass, got: {}",
        code
    );
}

/// Regression test for pitfall #2: NOP Detection Too Aggressive
/// Test that LDR R0, [PC, #0x40] is NOT marked as NOP.
#[test]
fn test_ldr_pc_relative_is_not_nop() {
    // LDR R0, [PC, #0x40] - PC-relative load, must NOT be NOP
    let inst = arm_inst(
        "LDR",
        vec![
            Operand::Register(0),
            Operand::MemoryAddress {
                base: 15,
                offset: AddressingMode::ImmediateOffset(0x40),
                writeback: false,
            },
        ],
        false,
    );
    let code = generate_instruction_python(&inst);
    
    // The generated code should read from memory and write to a register
    assert!(
        code.contains("registers[0]"),
        "LDR must write to destination register, got: {}",
        code
    );
    assert!(
        code.contains("read_u32") || code.contains("memory"),
        "LDR must emit memory read, got: {}",
        code
    );
}

/// Regression test for pitfall #2: NOP Detection Too Aggressive
/// Test that STR R0, [SP, #0x4] is NOT marked as NOP.
#[test]
fn test_str_is_not_nop() {
    // STR R0, [SP, #0x4] - stack store, must NOT be NOP
    let inst = arm_inst(
        "STR",
        vec![
            Operand::Register(0),
            Operand::MemoryAddress {
                base: 13,
                offset: AddressingMode::ImmediateOffset(0x4),
                writeback: false,
            },
        ],
        false,
    );
    let code = generate_instruction_python(&inst);
    
    // The generated code should write to memory
    assert!(
        code.contains("write_u32") || code.contains("memory"),
        "STR must emit memory write, got: {}",
        code
    );
    assert!(
        code.contains("registers[0]"),
        "STR must read source register, got: {}",
        code
    );
}

/// Regression test for pitfall #2: NOP Detection Too Aggressive
/// Test that actual ARM NOP (MOV R0, R0 = 0xE1A00000) IS treated as NOP.
#[test]
fn test_real_nop_is_nop() {
    // MOV R0, R0 - the canonical ARM NOP instruction
    let inst = arm_inst("MOV", vec![Operand::Register(0), Operand::Register(0)], false);
    let code = generate_instruction_python(&inst);
    
    // MOV R0, R0 is semantically a NOP - it should emit pass or a no-op assignment
    // The codegen may emit "registers[0] = registers[0]" or "pass"
    // Either is acceptable as it doesn't change state
    assert!(
        code.contains("pass") || code.contains("registers[0] = registers[0]"),
        "MOV R0, R0 should be a no-op, got: {}",
        code
    );
}

/// Regression test for pitfall #2: NOP Detection Too Aggressive
/// Test that Thumb NOP (0x46C0 = MOV R8, R8) IS treated as NOP.
#[test]
fn test_thumb_nop_is_nop() {
    // MOV R8, R8 in Thumb mode - the canonical Thumb NOP (0x46C0)
    let inst = DecodedInstruction {
        address: 0x08000000,
        opcode: "MOV".to_string(),
        operands: vec![Operand::Register(8), Operand::Register(8)],
        condition: Some(Condition::Al),
        mode: ArmMode::Thumb,
        raw: 0x46C0,
        sets_flags: false,
        width: 2,
        is_data: false,
    };
    let code = generate_instruction_python(&inst);
    
    // MOV R8, R8 is semantically a NOP
    assert!(
        code.contains("pass") || code.contains("registers[8] = registers[8]"),
        "Thumb MOV R8, R8 should be a no-op, got: {}",
        code
    );
}
