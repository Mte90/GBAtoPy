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
