# Plan 3: IR Lifting and Optimization (Rust crate: pygba-ir)

## 3.1 Objective

Convert disassembled ARM/Thumb instructions into a platform-independent SSA (Static Single Assignment) intermediate representation, then apply optimization passes to produce simpler, cleaner IR.

## 3.2 IR Design Principles

- **SSA (Static Single Assignment)**: Each variable is defined exactly once
- **Phi nodes**: At control flow merge points, reconcile multiple definitions
- **Platform-independent**: No ARM/Thumb-specific details remain after lifting
- **Typed**: All values carry type information (populated by Plan 4)
- **Extensible**: GBA-specific IR nodes for hardware access

## 3.3 Core IR Data Structures

```rust
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum IRInstruction {
    // -- Arithmetic --
    Add { dest: Value, lhs: Value, rhs: Operand },
    Sub { dest: Value, lhs: Value, rhs: Operand },
    Mul { dest: Value, lhs: Value, rhs: Operand },
    DivU { dest: Value, lhs: Value, rhs: Operand },
    DivS { dest: Value, lhs: Value, rhs: Operand },
    ModU { dest: Value, lhs: Value, rhs: Operand },
    Neg  { dest: Value, value: Value },

    // -- Bitwise --
    And { dest: Value, lhs: Value, rhs: Operand },
    Or  { dest: Value, lhs: Value, rhs: Operand },
    Xor { dest: Value, lhs: Value, rhs: Operand },
    Not { dest: Value, value: Value },
    Shl { dest: Value, value: Value, amount: Operand },
    Shr { dest: Value, value: Value, amount: Operand },  // logical
    Asr { dest: Value, value: Value, amount: Operand },  // arithmetic
    Ror { dest: Value, value: Value, amount: Operand },

    // -- Comparison --
    CmpEq  { dest: Value, lhs: Value, rhs: Operand },
    CmpNe  { dest: Value, lhs: Value, rhs: Operand },
    CmpLt  { dest: Value, lhs: Value, rhs: Operand },  // signed
    CmpLe  { dest: Value, lhs: Value, rhs: Operand },
    CmpGt  { dest: Value, lhs: Value, rhs: Operand },
    CmpGe  { dest: Value, lhs: Value, rhs: Operand },
    CmpUlt { dest: Value, lhs: Value, rhs: Operand },  // unsigned
    CmpUle { dest: Value, lhs: Value, rhs: Operand },
    CmpUgt { dest: Value, lhs: Value, rhs: Operand },
    CmpUge { dest: Value, lhs: Value, rhs: Operand },

    // -- Memory --
    LoadU8  { dest: Value, address: Value },
    LoadU16 { dest: Value, address: Value },
    LoadU32 { dest: Value, address: Value },
    LoadS8  { dest: Value, address: Value },
    LoadS16 { dest: Value, address: Value },
    StoreU8  { address: Value, value: Value },
    StoreU16 { address: Value, value: Value },
    StoreU32 { address: Value, value: Value },

    // -- Control flow --
    Branch      { condition: Value, true_block: BlockId, false_block: BlockId },
    BranchTable { index: Value, targets: Vec<BlockId> },
    Call        { dest: Option<Value>, target: FunctionRef, args: Vec<Value> },
    Ret         { value: Option<Value> },

    // -- SSA --
    Phi { dest: Value, sources: Vec<(BlockId, Value)> },

    // -- GBA-specific --
    IORead       { dest: Value, register: u32 },
    IOWrite      { register: u32, value: Value },
    SWICall      { number: u32, input_regs: Vec<Value>, output_regs: Vec<Value> },
    DMATransfer  { channel: u8, src: Value, dst: Value, count: Value, control: Value },
    WaitVBlank   {},

    // -- Conversion --
    SExt       { dest: Value, value: Value, from_bits: u8 },
    ZExt       { dest: Value, value: Value, from_bits: u8 },
    Trunc      { dest: Value, value: Value, to_bits: u8 },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Operand {
    Value(Value),
    Constant { value: u64, width: ConstantWidth },
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum ConstantWidth { U8, U16, U32, S8, S16, S32, Bool }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Value {
    pub id: u32,
    pub name: String,
    pub defined_in: Option<BlockId>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct BlockId(pub u32);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionRef(pub u32);  // index into function table

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BasicBlock {
    pub id: BlockId,
    pub instructions: Vec<IRInstruction>,
    pub predecessors: Vec<BlockId>,
    pub successors: Vec<BlockId>,
    pub dominator: Option<BlockId>,
    pub dominated: Vec<BlockId>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IRFunction {
    pub name: String,
    pub address: u32,
    pub blocks: Vec<BasicBlock>,
    pub entry_block: BlockId,
    pub parameters: Vec<Value>,
    pub return_value: Option<Value>,
}
```

## 3.4 Lifting Rules

### ARM to IR Mapping

| ARM Instruction | IR Translation |
|---|---|
| ADD Rd, Rn, Op2 | `Add { dest: Rd, lhs: Rn, rhs: lift_operand(op2) }` |
| SUB Rd, Rn, Op2 | `Sub { dest: Rd, lhs: Rn, rhs: ... }` |
| AND Rd, Rn, Op2 | `And { dest: Rd, lhs: Rn, rhs: ... }` |
| ORR Rd, Rn, Op2 | `Or { dest: Rd, lhs: Rn, rhs: ... }` |
| EOR Rd, Rn, Op2 | `Xor { dest: Rd, lhs: Rn, rhs: ... }` |
| BIC Rd, Rn, Op2 | `And { dest: Rd, lhs: Rn, rhs: Not(Op2) }` |
| MVN Rd, Op2 | `Not { dest: Rd, value: lift_operand(op2) }` |
| MOV Rd, Op2 | Copy via `Add { dest: Rd, lhs: Op2, rhs: Constant(0) }` or direct assignment |
| LDR Rd, [Rn, #off] | `LoadU32 { dest: Rd, address: Add(Rn, off) }` |
| STR Rd, [Rn, #off] | `StoreU32 { address: Add(Rn, off), value: Rd }` |
| LDRB Rd, [Rn, #off] | `LoadU8 { dest: Rd, address: Add(Rn, off) }` |
| STRB Rd, [Rn, #off] | `StoreU8 { address: Add(Rn, off), value: Rd }` |
| LDRH Rd, [Rn, #off] | `LoadU16 { dest: Rd, address: Add(Rn, off) }` |
| STRH Rd, [Rn, #off] | `StoreU16 { address: Add(Rn, off), value: Rd }` |
| LDM Rn!, {list} | Expand to N individual `LoadU32` + SP increment |
| STM Rn!, {list} | Expand to N individual `StoreU32` + SP increment |
| B target | `Branch { condition: always, true_block: target }` |
| BL target | `Call { dest: LR, target, args: [] }` |
| BX Rm | `Branch` with mode switch from Rm bit 0 |
| SWI num | `SWICall { number: num, input_regs, output_regs }` |
| CMP Rn, Op2 | `Cmp* { dest: flags, lhs: Rn, rhs: Op2 }` (no Rd written) |
| TST Rn, Op2 | Same as AND but discard result, only set flags |
| MUL Rd, Rm, Rs | `Mul { dest: Rd, lhs: Rm, rhs: Rs }` |
| MLA Rd, Rm, Rs, Rn | `Add { dest: Rd, lhs: Mul(Rm, Rs), rhs: Rn }` |
| SWP Rd, Rm, [Rn] | Atomic: temp=Load(Rn), Store(Rn, Rm), Rd=temp |

### Barrel Shifter Handling

The ARM barrel shifter becomes explicit IR operations:

| Shift Type | IR Translation |
|---|---|
| LSL #imm | `Shl { value, amount: Constant(imm) }` |
| LSL Rs | `Shl { value, amount: Rs }` |
| LSR #imm | `Shr { value, amount: Constant(imm) }` |
| LSR Rs | `Shr { value, amount: Rs }` |
| ASR #imm | `Asr { value, amount: Constant(imm) }` |
| ASR Rs | `Asr { value, amount: Rs }` |
| ROR #imm | `Ror { value, amount: Constant(imm) }` |
| ROR Rs | `Ror { value, amount: Rs }` |
| RRX | `Ror { value, amount: Constant(1) }` with carry flag |

### Conditional Execution

ARM condition codes transform as follows:
- **AL (always)**: No branch wrapping needed
- **EQ/NE/CS/CC/MI/PL/VS/VC/HI/LS/GE/LT/GT/LE**: Wrap instruction in conditional branch
- For flag-setting instructions (S bit): comparison result feeds the branch condition
- **Thumb IT blocks**: Each instruction in the IT block gets the same condition check

### Load/Store Multiple Expansion

```
LDMIA SP!, {R4, R5, R6, LR}
```
becomes:
```
R4  = LoadU32(SP + 0)
R5  = LoadU32(SP + 4)
R6  = LoadU32(SP + 8)
LR  = LoadU32(SP + 12)
SP  = SP + 16
```

### Thumb-Specific Lifting

- **Push/Pop**: Expand to multiple stores/loads + SP adjustment
- **Short conditional branch**: `Branch { condition, true_block, fallthrough }`
- **Long branch with link (BL)**: Two-instruction sequence combining to `Call`
- **ADD/SUB SP, #imm**: Direct stack pointer adjustment

## 3.5 SSA Construction

1. **Dominance analysis**: Compute dominator tree for all basic blocks
2. **Phi node placement**: At each join point (block with 2+ predecessors), place phi nodes for every variable defined in multiple predecessor blocks
3. **Variable renaming**: Walk the dominator tree, assigning unique SSA names (v0, v1, v2, ...) at each definition
4. **Phi node resolution**: Each phi source refers to the correct renamed variable from its originating block

## 3.6 Optimization Passes

All passes run in sequence. Each transforms the IR while preserving semantics.

### Pass 1: Dead Code Elimination (DCE)
Remove instructions whose results are never read. Side-effecting instructions (stores, IO writes, SWI, DMA) are never removed.

```
Before:  v0 = add(v1, v2)   // v0 unused
         v3 = load_u32(addr)
After:   v3 = load_u32(addr)   // v0 removed
```

### Pass 2: Constant Folding
Evaluate compile-time-known expressions.

```
Before:  v0 = add(const(2), const(3))
After:   v0 = const(5)
```

### Pass 3: Constant Propagation
Track constant values through data flow.

```
Before:  v0 = const(0x04000000)
         v1 = load_u32(v0)
After:   v0 = const(0x04000000)
         v1 = load_u32(const(0x04000000))   // address now known
```

### Pass 4: Strength Reduction
Replace expensive operations with cheaper equivalents:
- `mul(v, const(2^n))` becomes `shl(v, const(n))`
- `div(v, const(2^n))` becomes `shr(v, const(n))`
- `mod(v, const(power_of_2))` becomes `and(v, const(mask))`

### Pass 5: Peephole Optimization
Pattern-match instruction sequences:
- `add(v, const(0))` becomes `v` (identity)
- `mul(v, const(1))` becomes `v` (identity)
- `and(v, const(0xFFFFFFFF))` becomes `v` (identity)
- `store(addr, v0); v1 = load(addr)` becomes `v1 = v0` (redundant load)

### Pass 6: Loop Detection
- Identify back edges in the CFG
- Recognize loop variables (induction, condition, body)
- Extract loop-invariant code outside the loop body

### Pass 7: Memory Access Optimization
- Combine consecutive loads from adjacent addresses
- Eliminate redundant loads (value already in SSA register from prior store)
- Group I/O register reads/writes

## 3.7 IR API

```rust
pub struct IRBuilder {
    next_value_id: u32,
    next_block_id: u32,
}

impl IRBuilder {
    pub fn new() -> Self;
    pub fn lift_arm_instruction(&mut self, instr: &Instruction) -> Result<Vec<IRInstruction>, LiftError>;
    pub fn lift_thumb_instruction(&mut self, instr: &Instruction) -> Result<Vec<IRInstruction>, LiftError>;
    pub fn lift_function(&mut self, func: &Function) -> Result<IRFunction, LiftError>;
    pub fn build_ssa(&mut self, func: &mut IRFunction) -> Result<(), LiftError>;
}

pub struct Optimizer {
    ir: IRFunction,
}

impl Optimizer {
    pub fn new(ir: IRFunction) -> Self;
    pub fn dead_code_elimination(&mut self) -> &mut Self;
    pub fn constant_folding(&mut self) -> &mut Self;
    pub fn constant_propagation(&mut self) -> &mut Self;
    pub fn strength_reduction(&mut self) -> &mut Self;
    pub fn peephole(&mut self) -> &mut Self;
    pub fn loop_optimize(&mut self) -> &mut Self;
    pub fn memory_optimize(&mut self) -> &mut Self;
    pub fn optimize_all(mut self) -> IRFunction;
    pub fn instruction_count(&self) -> usize;
}
```

## 3.8 GBA-Specific IR Extensions

- `IORead` / `IOWrite` carry the register address for traceability through the pipeline
- `SWICall` carries the SWI number (0x00-0x2D) and register mapping
- `DMATransfer` carries channel, source, dest, count, and control word
- `WaitVBlank` is a recognized pattern (loop reading DISPSTAT until VBlank flag)
- Interrupt handler entry points are marked with metadata

## 3.9 Testing

### Unit Tests
- Each ARM instruction category lifted and verified against expected IR
- Each Thumb instruction category lifted and verified
- SSA construction verified: phi nodes at merge points, unique definitions

### Optimization Tests
- Known patterns fed through each pass, output verified
- Measure instruction count reduction (target: >30%)

### Integration Tests
- Full pipeline: disassemble test ROM, lift to IR, optimize
- Compare optimized IR against oracle execution trace
- Verify semantics preserved (same memory writes, same register outcomes)

## 3.10 Acceptance Criteria

- [ ] All ARM instructions lift to valid IR
- [ ] All Thumb instructions lift to valid IR
- [ ] SSA form is valid (single definition per value, phi nodes at merge points)
- [ ] Optimization passes reduce instruction count by >30% on test ROMs
- [ ] Optimized IR semantics match oracle execution traces
- [ ] `cargo test -p pygba-ir` passes all tests
