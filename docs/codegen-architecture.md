# Instruction Codegen Architecture

## Overview

The `instruction_codegen/` module translates decoded ARM/Thumb instructions into executable Python code. It is a core component of the GBAtoPy transpiler, converting GBA ROM machine code into human-readable Python that can be executed with pygame.

### Pipeline Flow

```
ROM bytes → Disassembler (gbatopy_disasm) → DecodedInstruction
                                              ↓
                              instruction_codegen::generate_instruction_python()
                                              ↓
                                    Per-instruction dispatch
                                              ↓
                            File-specific generate() functions
                                              ↓
                                    Python code string
                                              ↓
                              Assembled into final .py output
```

The entry point is `generate_instruction_python()` in `mod.rs`, which receives a `DecodedInstruction` from the disassembler and returns a Python code string. The function dispatches to specialized modules based on opcode matching, returning `None` if no module handles the instruction (which triggers a fallback to the interpreter).

---

## File Breakdown

### `mod.rs` — Top-level Dispatch

**Purpose:** Orchestrates instruction dispatch to specialized modules.

**Key Function:**
- `generate_instruction_python(inst: &DecodedInstruction) -> String`

**Dispatch Order:**
1. `data_processing::generate()` — MOV, ADD, SUB, AND, etc.
2. `branch::generate()` — B, BL, BX, BLX, conditional branches
3. `load_store::generate()` — LDR, STR, LDM, STM, multi-word transfers
4. `coprocessor::generate()` — SWI, MRS, MSR, MUL, coprocessor no-ops

**Notable Pattern:**
- Sequential `if let Some(code) = module::generate(inst)` chain — first match wins
- Unhandled instructions emit a warning and route to `_interp_fallback()` instead of silent no-op
- Each module returns `Option<String>` — `None` means "not my instruction, try next"

---

### `branch.rs` — Branch Instructions

**Instruction Classes:**
- **Unconditional branches:** `B` (branch), `BL` (branch with link)
- **Branch exchange:** `BX` (branch and exchange mode), `BLX` (branch with link and exchange)
- **Conditional branches:** `BEQ`, `BNE`, `BCS`, `BCC`, `BMI`, `BPL`, `BVS`, `BVC`, `BHI`, `BLS`, `BGE`, `BLT`, `BGT`, `BLE`
- **Conditional BL variants:** `BLEQ`, `BLNE`, `BLCS`, etc.

**Key Functions:**
- `generate(inst: &DecodedInstruction) -> Option<String>`

**Notable Patterns:**

1. **Target validation:** Branch targets must be in GBA memory region (`0x08000000` to `0x0A000000`). Invalid targets emit a comment rather than crashing.

2. **Thumb interworking:** 
   - `BL` in Thumb mode sets LR bit 0 to indicate Thumb mode for `BX LR` interworking
   - `BX Rn` sets `cpsr['t']` based on the target register's bit 0
   - `BX PC` uses pipeline offset (PC = addr + 4 for Thumb, + 8 for ARM) and always results in ARM mode (bit 0 = 0)

3. **Conditional branch fall-through:** All conditional branches emit an `else` clause that advances PC by 2 (Thumb) or 4 (ARM) — critical for correct sequential execution when condition fails.

4. **Pipeline awareness:** The code accounts for ARM7TDMI pipeline behavior where PC reads return `addr + offset` (8 for ARM, 4 for Thumb).

**Test Coverage:** 35+ regression tests covering all branch types, conditional variants, edge cases (invalid targets, no operands), and interworking scenarios.

---

### `coprocessor.rs` — Coprocessor & System Instructions

**Instruction Classes:**
- **Coprocessor no-ops:** `COPROCESSOR`, `LDC`, `STC`, `CDP` — ARM7TDMI has no coprocessor
- **CP15 cache config:** `MRC` (return 0), `MCR` (no-op) — GBA has no cache
- **Breakpoint/debug:** `BKPT` — no debugger, NOP
- **ARMv6 hints:** `CPS`, `SEV`, `WFE`, `WFI`, `ISB`, `YIELD`, `DSB`, `DMB` — NOP on ARM7TDMI
- **System control:** `SWI`/`SVC` (calls `swi_handler()`), `MRS` (CPSR→register), `MSR` (register→CPSR)
- **Multiplication:** `MUL`, `MLA` (multiply-accumulate), `UMULL`, `SMULL` (64-bit multiply)

**Key Functions:**
- `generate(inst: &DecodedInstruction) -> Option<String>`
- `generate_inner(inst: &DecodedInstruction) -> Option<String>` — core logic
- `wrap_conditional(code: String, opcode: &str) -> String` — wraps code in `if cpsr_check('XX'):` for conditional variants

**Notable Patterns:**

1. **Conditional wrapping:** The `wrap_conditional()` helper strips the condition suffix (e.g., "ge" from "COPROCESSORge") and wraps the generated code in a `cpsr_check()` conditional. This allows a single `generate_inner()` to handle both conditional and unconditional variants.

2. **CP15 stubs:** MRC/MCR to CP15 return 0 / no-op — the disassembler may decode data as CP15 instructions (CFG bug), but the correct behavior on GBA is to do nothing.

3. **SWI handling:** Extracts the SWI number from operands and emits `swi_handler(N)` followed by a check for `_cpu_halted` to handle IRQ returns correctly.

4. **MSR field discipline:** MSR respects the ARM field-mask bits (c/x/s/f) — only updates the specified fields. Control field (c) updates mode and T bit; flags field (f) updates N/Z/C/V.

5. **SMULL sign extension:** SMULL uses `int()` to sign-extend operands before multiplication, distinguishing it from UMULL which treats operands as unsigned.

**Test Coverage:** 30+ tests covering coprocessor no-ops, SWI/SVC, MSR field handling, MRS full CPSR round-trip, MUL/MLA, UMULL/SMULL sign extension, and conditional wrapping.

---

### `data_processing.rs` — ALU Operations

**Instruction Classes:**
- **Data transfer:** `MOV`, `MVN` (move negated)
- **Arithmetic:** `ADD`, `ADC` (add with carry), `SUB`, `SBC` (subtract with borrow), `RSB`, `RSC`
- **Logical:** `AND`, `EOR` (XOR), `ORR` (OR), `BIC` (bit clear)
- **Shifts:** `LSL`, `LSR`, `ASR`, `ROR`
- **Compare:** `CMP`, `CMN` (compare negative), `TST` (test bits), `TEQ` (test equivalence)
- **Other:** `NEG`, `CLZ` (count leading zeros), `MUL`, `SXTH`, `SXTB`, `UXTH`, `UXTB`, `UMLAL`, `SMLAL`

**Key Functions:**
- `generate(inst: &DecodedInstruction) -> Option<String>`
- `shifted_reg_expr(reg, shift, amount) -> String` — generates Python for shifted register operands
- `operand_to_expr(op) -> String` — resolves operand to Python expression
- `resolve_pc_operands(ops, inst, base_opcode) -> Vec<Operand>` — replaces R15 sources with computed PC value
- `shifter_carry_code(op) -> Option<String>` — generates carry-out update code
- Per-instruction generators: `generate_mov()`, `generate_add()`, `generate_sub()`, etc.

**Notable Patterns:**

1. **PC resolution:** R15 (PC) as a *source* operand is replaced with the computed pipeline value (`addr + 8` for ARM, `(addr + 4) & !3` for Thumb). This is done before code generation to simplify expressions.

2. **Flag-setting discipline:** When `sets_flags=true`, the generator emits:
   - Carry update code (from shifter) before destination write
   - N/Z flag computation from result
   - C/V flags for arithmetic ops (full 64-bit math to detect overflow)

3. **RRX special case:** RRX (rotate right extend, `ROR #0`) requires saving the old carry (`_old_c`) before updating it, since the new carry depends on the old value.

4. **Exception return:** `MOVS PC, LR`, `SUBS PC, LR`, `ANDS PC, ...` with S-bit set trigger exception return — they restore CPSR from SPSR and call `_switch_mode()`.

5. **Arithmetic precision:** ADD/SUB with flag setting uses intermediate 64-bit variables (`_full`) to correctly compute carry and overflow flags, then converts to signed arithmetic for V flag.

6. **Shift edge cases:**
   - `LSR #0` and `ASR #0` mean shift by 32, not 0
   - `ROR #0` means RRX (rotate through carry)
   - Register-specified shifts mask the amount to 8 bits (`rs & 0xFF`)

**Test Coverage:** 100+ tests (truncated in source) covering all data processing instructions, flag-setting variants, PC-relative operations, shifts, and edge cases.

---

### `load_store.rs` — Memory Access

**Instruction Classes:**
- **Single data transfer:** `LDR`, `STR`, `LDRB`, `STRB`, `LDRH`, `STRH`, `LDRSH`, `LDRSB`
- **Block data transfer:** `LDM` (load multiple), `STM` (store multiple) with IA/IB/DA/DB addressing
- **Swap:** `SWP`, `SWPB`

**Addressing Modes:**
- Immediate offset: `[Rn, #offset]`
- Register offset: `[Rn, Rm]`
- Scaled register offset: `[Rn, Rm, LSL #2]`
- Pre-indexed: `[Rn, #offset]!`
- Post-indexed: `[Rn], #offset`
- Multi-register: `{R0, R1, R3, R15}` with writeback

**Key Functions:**
- `generate(inst: &DecodedInstruction) -> Option<String>`
- `generate_inner(inst: &DecodedInstruction) -> Option<String>` — core logic
- `base_address_expr(base, inst) -> String` — resolves base register (or PC literal)
- `scaled_reg_offset_expr(reg, shift, amount) -> String` — generates scaled offset expression
- `wrap_conditional(code, opcode) -> String` — conditional wrapping (same as coprocessor.rs)

**Notable Patterns:**

1. **PC-relative loads:** LDR with R15 base uses the same pipeline PC computation as data processing (`addr + 8` for ARM, `(addr + 4) & !3` for Thumb).

2. **Writeback handling:** For pre/post-indexed addressing with writeback, the base register update is emitted *after* the memory access. Special case: LDM with base in register list — the loaded value takes priority over writeback (ARM7TDMI rule).

3. **Multi-register ordering:** LDM/STM always walk registers in ascending order mapped to ascending addresses, regardless of IA/IB/DA/DB mode. The starting address varies:
   - IA (increment after): `[base, base + 4n)`
   - IB (increment before): `[base + 4, base + 4n + 4)`
   - DA (decrement after): `[base - 4n + 4, base + 4)`
   - DB (decrement before): `[base - 4n, base)`

4. **S-bit handling:**
   - LDM with PC in list + S=1: exception return (load PC, restore CPSR from SPSR)
   - LDM without PC + S=1: load into user-bank registers via `_write_user_reg()`
   - STM + S=1: store from user-bank registers via `_read_user_reg()`

5. **Signed extensions:** LDRSH/LDRSB perform sign-extension after the read:
   - LDRSH: `temp & 0xFFFF`, then sign-extend if bit 15 set
   - LDRSB: `temp & 0xFF`, then sign-extend if bit 7 set

6. **SWP atomicity:** SWP emits a temp variable to hold the old memory value, then writes the new value — preserving the atomic swap semantics.

**Test Coverage:** 50+ tests covering all addressing modes, writeback, multi-register transfers, PC-relative loads, signed extensions, and conditional variants.

---

### `regression_tests.rs` — Bug Prevention Suite

**Purpose:** Freezes documented codegen bugs from `docs/codegen-pitfalls.md` as automated tests.

**Test Categories:**

1. **Pitfall #1: STRH immediate offset bug (T1.1)** — Verifies STRH preserves nonzero immediate offsets (was using wrong bit field).

2. **Pitfall #1.2: BL LR assignment (T1.2)** — Verifies BL sets LR *before* branching.

3. **Pitfall #1.3: Conditional branch fall-through (T1.3)** — Verifies conditional branches have `else` clauses.

4. **Pitfall #1.4: LDM PC in list (T1.4)** — Verifies LDM writes R15 when PC is in register list.

5. **Pitfall #1.5-1.6: STMFD/LDMFD address ordering (T1.5, T1.6)** — Verifies correct address walk direction.

6. **Pitfall #1.7-1.9: Immediate offset syntax (T1.7, T1.8, T1.9)** — Verifies offsets appear correctly without `#` prefix.

7. **Pitfall #1.10: MRS full CPSR round-trip (T1.10)** — Verifies MRS emits all CPSR bits (NZCV + F + I + T + mode).

8. **Pitfall #8: SP initialization** — Verifies header template initializes SP to `0x03007F00`, not 0.

9. **Pitfall #14: Thumb BL merged instruction** — Verifies merged BL (from `decode_bl_pair`) emits correct LR and PC assignment with width=4.

10. **Pitfall #2: NOP detection** — Verifies initialization code (MOV R0, #imm) is NOT marked as NOP.

11. **CFG explosion prevention** — Verifies transpilation of known-explosion ROMs stays under 100MB and 2M lines.

**Notable Pattern:**
- Each test constructs a `DecodedInstruction` directly (bypassing disassembler) to isolate codegen behavior
- Tests assert exact string matches in generated Python code
- Some tests read template files to verify header generation

---

## Interface with Rest of Codegen

### Entry Point Integration

The `instruction_codegen` module is called from `codegen/mod.rs` via:
```rust
use instruction_codegen::generate_instruction_python;
let python_code = generate_instruction_python(&decoded_instruction);
```

### Dependencies

- **`gbatopy_disasm`**: Provides `DecodedInstruction`, `Operand`, `ArmMode`, `Condition`, `ShiftType`, `ShiftAmount`, `AddressingMode`
- **`codegen/mod.rs`**: Provides runtime helper names (`cpsr_check`, `_spsr_for_mode`, `_switch_mode`, `_write_user_reg`, etc.) that appear in generated Python

### Shared Patterns

1. **Conditional wrapping:** Both `branch.rs`, `coprocessor.rs`, `data_processing.rs`, and `load_store.rs` use the same pattern for handling condition codes — strip suffix, convert to uppercase, wrap in `if cpsr_check('XX'):`.

2. **PC pipeline offsets:** All modules use consistent PC computation:
   - ARM: `address + 8`
   - Thumb: `(address + 4) & !3` (word-aligned for literal pools)

3. **32-bit masking:** All register writes mask with `& 0xFFFFFFFF` to simulate 32-bit ARM registers.

4. **Memory API:** Generated code uses `memory.read_u8/16/32()` and `memory.write_u8/16/32()` — defined in `gba_runtime/memory.py`.

---

## Design Patterns

### 1. Operand Resolution Chain

```
Operand enum → operand_to_expr() / shifted_reg_expr() → Python expression string
```

The disassembler provides structured operands (Register, Immediate, ShiftedRegister, MemoryAddress). Each operand type has a corresponding generator function that produces a Python expression.

### 2. Flag-Setting Computation

Instructions with the S-bit set follow a consistent pattern:
```python
# 1. Compute full result (may be 64-bit for carry/overflow)
_full = _rn_val + _op2_val

# 2. Write destination (masked to 32 bits)
registers[rd] = _full & 0xFFFFFFFF

# 3. Update N/Z from result
cpsr['n'] = (_result >> 31) & 1
cpsr['z'] = 1 if _result == 0 else 0

# 4. Update C from full computation
cpsr['c'] = 1 if _full >= 0x100000000 else 0

# 5. Update V from signed overflow detection
_rn_s = _rn_val if _rn_val < 0x80000000 else _rn_val - 0x100000000
# ... signed overflow logic ...
```

### 3. Memory Addressing Mode Dispatch

```rust
match offset {
    ImmediateOffset(n) => format!(" + {}" / " - {}", n),
    RegisterOffset(reg) => format!(" + registers[{}]", reg),
    ScaledRegisterOffset { reg, shift, amount } => scaled_reg_offset_expr(...),
    PostIndexed { .. } => handle writeback separately,
    PreIndexed { offset, .. } => format!(" + {}" / " - {}", offset),
}
```

Each addressing mode maps to a Python arithmetic expression combining base register and offset.

### 4. Exception Return Detection

Multiple instruction types can trigger exception return when they write PC with S-bit set:
- `MOVS PC, LR`
- `SUBS PC, LR`
- `ANDS PC, ...`
- `LDM {PC}^`

All follow the same pattern:
```python
registers[15] = <value> & 0xFFFFFFFE
_new_cpsr = _spsr_for_mode(cpsr['mode'])
_cpsr_from_int(cpsr, _new_cpsr)
_switch_mode(cpsr['mode'])
```

---

## Notable Edge Cases

1. **Thumb BL interworking:** LR must have bit 0 set (`(PC + 4) | 1`) so `BX LR` correctly enters Thumb mode.

2. **BX PC pipeline:** `BX PC` in ARM mode jumps to `addr + 8` (pipeline), which is always word-aligned → ARM mode.

3. **LSR/ASR #0 semantics:** These mean shift by 32, not 0. Python's `>> 32` on a 32-bit value yields 0, which is correct.

4. **RRX carry dependency:** RRX uses the *old* carry bit, so `_old_c` must be saved before updating `cpsr['c']`.

5. **LDM writeback priority:** If base register is in the load list, the loaded value wins over writeback (ARM7TDMI erratum).

6. **SMULL sign extension:** Python's arbitrary-precision integers require explicit `int()` conversion to simulate 32-bit sign extension before multiplication.

---

## Testing Strategy

Every file includes a `#[cfg(test)]` module with comprehensive regression tests:
- **branch.rs:** 35+ tests
- **coprocessor.rs:** 30+ tests
- **data_processing.rs:** 100+ tests (partial shown)
- **load_store.rs:** 50+ tests (partial shown)
- **regression_tests.rs:** 20+ integration tests

Tests are run via `cargo test -p gbatopy-cli` and serve as both verification and documentation of expected behavior.
