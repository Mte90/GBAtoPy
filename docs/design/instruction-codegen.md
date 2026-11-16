# Instruction Codegen Architecture

> The `crates/gbatopy-cli/src/codegen/instruction_codegen/` module translates each
> decoded ARM/Thumb instruction into a Python source string. This document
> describes the dispatch mechanism, per-category structure, and key design
> decisions including known issues (F406/F407).

## Overview

The codegen is **direct**: each `DecodedInstruction` from the disassembler becomes
one Python code snippet. There is no intermediate IR, no phi nodes, no control-flow
reconstruction. The transpiled output is a flat sequence of register-mutating
statements inside per-function Python bodies, driven by a dispatch-table main loop
(see [`transpilation-patterns.md`](transpilation-patterns.md)).

**Entry point:** `generate_instruction_python(inst: &DecodedInstruction) -> String`

Tries four category generators in order; the first that returns `Some(code)` wins:

1. `data_processing::generate` — arithmetic, logic, shifts, comparisons, multiply
2. `branch::generate` — B, BL, BX, BLX
3. `load_store::generate` — LDR, STR, LDM, STM
4. `coprocessor::generate` — MCR, MRC, CDP, LDC, STC

If none matches, the instruction is emitted as an **interpreter fallback call**:

```python
sys.stderr.write('unhandled at 0x0800XXXX: OPCODE\n')
_interp_fallback(registers, cpsr, max_steps=1, irq_return_pc=None)
```

This is the catch-all for any instruction the codegen cannot transpile. The
fallback interpreter (`arm7tdmi.py`) executes the single instruction and returns.

## Category Structure

### Data Processing (`data_processing.rs`)

Largest module (~1,700 lines). Handles the ARM data-processing class:

| Opcode | Handler | Notes |
|--------|---------|-------|
| MOV, MVN | `generate_mov`, `generate_mvn` | |
| ADD, ADC | `generate_add` | |
| SUB, SBC, RSB, RSC | `generate_sub` | |
| AND, EOR, ORR, BIC | `generate_logic` | |
| LSL, LSR, ASR, ROR | `generate_shift` | |
| CMP, CMN, TST, TEQ | `generate_cmp` etc. | No destination register; update flags only |
| MUL | `generate_mul` | |
| UMLAL, SMLAL | `generate_umlal` | |
| CLZ | `generate_clz` | |
| NEG | `generate_neg` | Thumb-only |
| SXTH, SXTB, UXTH, UXTB | `generate_extend` | Sign/zero-extend |

**Key helper: `resolve_pc_operands()`** — replaces R15 (PC) source operands with
a computed immediate value. See [PC Handling](#pc-handling) below.

**Flag setting:** when the S bit is set (`inst.sets_flags`), handlers emit
CPSR flag updates (N, Z, C, V). Flag computation is inline, not via a helper.

### Branch (`branch.rs`)

Handles control-flow instructions:

- **B / BL** — direct branches to immediate targets. BL sets LR = return address
  (Thumb: `registers[15] + 4 | 1` for interworking; ARM: `registers[15] + 4`).
  Targets outside ROM range (0x08000000–0x0A000000) are rejected as invalid.
- **BX Rm** — branch via register. Sets `cpsr['t'] = registers[Rm] & 1` and
  `registers[15] = registers[Rm] & 0xFFFFFFFE`. BX PC switches mode using the
  pipeline value (addr + 4 Thumb, addr + 8 ARM).
- **BLX Rm** — branch with link via register. LR = `(registers[15] + 2) | 1`
  for Thumb (2-byte instruction, interworking bit set), `registers[15] + 4` for ARM.
  Target and mode set from `registers[Rm]`.

Conditional branches (Bcc, BLcc) are wrapped in `if cpsr_check('CC'):` blocks.

### Load/Store (`load_store.rs`)

Handles memory access:

- **LDR / STR** — single-register load/store, with immediate, register, and
  scaled-register offset addressing modes.
- **LDM / STM** — multiple-register load/store (stack operations: PUSH, POP,
  STMFD, LDMFD). Register order matters and follows ARM7TDMI semantics.
- **PLD** — preload (treated as no-op on ARM7TDMI).

Base address computation via `base_address_expr()`. Scaled register offsets
via `scaled_reg_offset_expr()`. PC-relative loads (literal pools) use
`(addr + 4) & !3` word-alignment (see [PC Handling](#pc-handling)).

### Coprocessor (`coprocessor.rs`)

Handles coprocessor instructions (MCR, MRC, CDP, LDC, STC). On the GBA, the
only coprocessor is the system control coprocessor (CP15), but the ARM7TDMI
has no cache/MMU, so most of these are no-ops or route to the interpreter fallback.

## PC Handling

The program counter (R15) has special semantics in ARM7TDMI:

- **Pipeline offset:** PC reads as `instruction_address + 8` in ARM mode,
  `instruction_address + 4` in Thumb mode (two instructions ahead).
- **Alignment:** when PC is used as a source operand, the value is aligned
  differently depending on the instruction format:

### `resolve_pc_operands()`

This function replaces R15 source operands with computed immediates. It skips
operand 0 (the destination register) for instructions that have Rd.

```rust
let pc_val = if inst.mode == ArmMode::Thumb {
    (inst.address + 4) & !3   // word-aligned
} else {
    inst.address + ARM_PC_OFFSET  // +8
};
```

**Known issue (F406/F407):** the `& !3` mask is used for ALL Thumb data-processing
instructions with PC source. Per ARM7TDMI spec:
- **Format 12 (ADR: `ADD Rd, PC, #imm`)** — correct: `(addr + 4) & !3` (word-aligned)
- **Format 5 (`ADD Rd, PC, Rm` high register)** — should be `(addr + 4) & !1`
  (halfword-aligned, only bit 0 cleared)

The spec-correct `& !1` was applied and reverted twice because it causes a
regression in `the-dungeon-puzzlers-lament.gba`: at instruction 1618 (PC
0x0800611E), the correct PC value causes R3=0 instead of R3=1, entering a
2-instruction infinite IWRAM loop (0x030009E2 ↔ 0x030009E6). This is NOT a
fallback interpreter bug — it's a codegen semantics issue where correct PC
values expose a different bug at 0x0800611E.

See WORKPLAN.md F407 for details.

### LDR/STR PC-relative (literal pools)

`load_store.rs` correctly uses `(addr + 4) & !3` for PC-relative loads. This is
spec-correct: literal pool loads require word alignment.

## Conditional Execution

ARM instructions carry a 4-bit condition code in bits 31–28. The codegen extracts
this from the opcode string (e.g., `"ADDeq"` → condition `EQ`) and wraps the
emitted code in an `if cpsr_check('CC'):` block:

```python
if cpsr_check('EQ'):
    registers[0] = (registers[1] + registers[2]) & 0xFFFFFFFF
```

If the condition is false, the block is skipped and execution falls through to
the next instruction in the function body. There is no explicit `else` branch —
the transpiled function body is a flat sequence of instruction snippets, so
skipping a conditional instruction naturally advances to the next one.

**Exception:** conditional branches in branch.rs (Bcc, BLcc, BXcc) emit an
explicit `else` that advances PC, because taken branches set `registers[15]`
to the target — the not-taken path must explicitly advance PC to the next
instruction.

Unconditional instructions (condition `AL`) emit no wrapper.

## 32-bit Semantics

All arithmetic is masked to 32 bits with `& 0xFFFFFFFF`. This matches ARM7TDMI's
32-bit register width. Signed operations use `_signed()` helper to convert to
Python's native int, then mask back.

## Flag Computation

When the S bit is set, handlers emit inline CPSR updates:

- **N flag:** bit 31 of result
- **Z flag:** result == 0
- **C flag:** carry-out from shifter (logic ops) or ALU (arithmetic ops)
- **V flag:** signed overflow (arithmetic ops only)

Carry-out computation differs between ADD (carry = no unsigned overflow) and SUB
(borrow = `lhs < rhs`).

## Dispatch Table Integration

The generated per-instruction snippets are assembled into per-function Python
bodies. Each function starts with a `def func_XXXXXXXX_t(registers, cpsr):`
signature and contains the sequential instruction codegen. The main loop
(`game_loop.py` template) dispatches to these functions via a dispatch table
indexed by `(pc - 0x08000000) >> 1` (Thumb) or `>> 2` (ARM).

When a function is not in the dispatch table (indirect call to EWRAM/IWRAM, or
mid-function entry), the fallback interpreter handles execution.

## Testing

`regression_tests.rs` contains 23 test functions covering:
- PC source operand resolution (ARM and Thumb)
- Conditional execution wrapping (if/else PC advance for branches)
- Flag setting (S bit)
- Branch target computation (BL LR, BX Rm mode switch)
- Load/store addressing modes
- Immediate and register operands

Additional tests exist within individual module files (e.g.,
`test_generate_add_pc_source_thumb` in `data_processing.rs`) for PC alignment
behavior.

All tests are run via `cargo test` in the `gbatopy-cli` crate.

## Known Issues

| ID | Issue | Status |
|----|-------|--------|
| F406 | `& !3` used for all Thumb PC-source data-processing; spec requires `& !1` for format 5 | REVERTED — causes regression |
| F407 | `& !1` fix causes the-dungeon-puzzlers-lament to hang in IWRAM loop | PARKED — no net PASS gain |
| F408 | BLX Rm LR offset used `+4` instead of `+2` for Thumb | FIXED (commit a76feb3) |

## See Also

- [`transpilation-patterns.md`](transpilation-patterns.md) — runtime dispatch table, interpreter fallback, hotspot tracking
- [`codegen-pitfalls.md`](../codegen-pitfalls.md) — bug classes found during codegen development
- [`hardware-reference.md`](../hardware-reference.md) — ARM7TDMI spec references for PC pipeline and alignment
- [WORKPLAN.md](../../WORKPLAN.md) — F406/F407/F408 task tracking
