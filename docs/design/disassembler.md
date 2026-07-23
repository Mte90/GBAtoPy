# Plan 1: Static Disassembler (Rust crate: gbatopy-disasm)

## 1.1 Objective

Build an ARM/Thumb disassembler in Rust that converts raw ROM bytes into structured basic blocks with full instruction decoding, branch resolution, function detection, and code/data separation.

## 1.2 Input/Output

- **Input**: raw ROM bytes (`Vec<u8>`) + base address (0x08000000)
- **Output**: structured disassembly (serializable to JSON via serde)

## 1.3 Core Data Structures

```rust
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Instruction {
    pub address: u32,
    pub opcode: u32,
    pub mnemonic: String,
    pub operands: Vec<Operand>,
    pub condition: Condition,
    pub is_thumb: bool,
    pub size: u8,              // 2 for Thumb, 4 for ARM
    pub affects_pc: bool,
    pub is_branch: bool,
    pub is_memory_access: bool,
    pub is_link: bool,         // BL sets LR
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Operand {
    Register(Reg),
    Immediate(u32),
    Address(u32),
    ShiftReg {
        reg: Reg,
        shift: ShiftType,
        amount: ShiftAmount,
    },
    MemoryAccess {
        base: Reg,
        offset: OffsetType,
        pre_indexed: bool,
        writeback: bool,
        size: AccessSize,
    },
    RegisterList(Vec<Reg>),
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum Condition {
    EQ, NE, CS, CC, MI, PL, VS, VC, HI, LS, GE, LT, GT, LE, AL, NV,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum ShiftType { LSL, LSR, ASR, ROR }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ShiftAmount {
    Immediate(u8),
    Register(Reg),
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum Reg {
    R0, R1, R2, R3, R4, R5, R6, R7,
    R8, R9, R10, R11, R12, R13, R14, R15,
    CPSR, SPSR,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OffsetType {
    Immediate(i32),
    Register(Reg),
    ScaledRegister { reg: Reg, shift: ShiftType, amount: u8 },
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum AccessSize { Byte, HalfWord, Word }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BasicBlock {
    pub id: BlockId,
    pub start_address: u32,
    pub end_address: u32,
    pub instructions: Vec<Instruction>,
    pub is_thumb: bool,
    pub successors: Vec<BlockId>,
    pub predecessors: Vec<BlockId>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Function {
    pub name: String,
    pub address: u32,
    pub is_thumb: bool,
    pub blocks: Vec<BasicBlock>,
    pub entry_block: BlockId,
    pub parameters: Vec<Reg>,
    pub return_reg: Option<Reg>,
    pub callee_saved: Vec<Reg>,
    pub stack_frame_size: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataRegion {
    pub address: u32,
    pub size: u32,
    pub data_type: DataType,
    pub label: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DataType {
    RawBytes,
    Palette,
    TileData,
    MapData,
    SampleData,
    Text,
    PointerTable { count: u32 },
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Disassembly {
    pub rom_size: usize,
    pub entry_point: u32,
    pub functions: Vec<Function>,
    pub blocks: Vec<BasicBlock>,
    pub data_regions: Vec<DataRegion>,
    pub unresolved_indirect_jumps: Vec<u32>,
    pub thumb_mode_addresses: Vec<u32>,
}
```

## 1.4 ARM Instruction Decoding (ARMv4T)

The GBA uses an ARM7TDMI processor implementing ARMv4T. All ARM instructions are 32 bits, conditionally executed.

### Instruction Bit Layout

```
[31:28] Condition code
[27:20] Instruction type + opcode
[19:0]  Operands (varies by type)
```

### Data Processing Instructions (bits [27:26] = 00)

| Opcode [24:21] | Mnemonic | Operation |
|---|---|---|
| 0000 | AND | Rd = Rn AND Op2 |
| 0001 | EOR | Rd = Rn XOR Op2 |
| 0010 | SUB | Rd = Rn - Op2 |
| 0011 | RSB | Rd = Op2 - Rn |
| 0100 | ADD | Rd = Rn + Op2 |
| 0101 | ADC | Rd = Rn + Op2 + C |
| 0110 | SBC | Rd = Rn - Op2 - !C |
| 0111 | RSC | Rd = Op2 - Rn - !C |
| 1000 | TST | Set flags on Rn AND Op2 |
| 1001 | TEQ | Set flags on Rn XOR Op2 |
| 1010 | CMP | Set flags on Rn - Op2 |
| 1011 | CMN | Set flags on Rn + Op2 |
| 1100 | ORR | Rd = Rn OR Op2 |
| 1101 | MOV | Rd = Op2 |
| 1110 | BIC | Rd = Rn AND NOT Op2 |
| 1111 | MVN | Rd = NOT Op2 |

Bit 25: I bit (0 = register with shift, 1 = immediate)
Bit 20: S bit (set condition codes)

### Branch Instructions (bits [27:25] = 101)

- **B**: Branch. Offset = sign_extend(imm24 << 2). Target = PC + 8 + offset.
- **BL**: Branch with Link. Same as B but LR = address of next instruction.
- **BX**: Branch and Exchange. Bit 0 of Rm determines ARM (0) vs Thumb (1).

### Load/Store Instructions

Single transfer (bits [27:26] = 01):
- **LDR/STR**: word load/store
- **LDRB/STRB**: byte load/store
- **LDRH/STRH**: halfword load/store
- **LDRSB**: signed byte load
- **LDRSH**: signed halfword load

Multiple transfer (bits [27:25] = 100, bit 20 = L bit):
- **LDM**: load multiple registers
- **STM**: store multiple registers
- Addressing modes: IA, IB, DA, DB, FD, FA, ED, EA

### Multiply Instructions (bits [27:22] = 000000, bits [7:4] = 1001)

- **MUL**: Rd = Rm * Rs
- **MLA**: Rd = (Rm * Rs) + Rn
- **UMULL**: 64-bit unsigned multiply
- **UMLAL**: 64-bit unsigned multiply-accumulate
- **SMULL**: 64-bit signed multiply
- **SMLAL**: 64-bit signed multiply-accumulate

### Swap Instruction (bits [27:23] = 00010, bit 20 = 0)

- **SWP**: atomic swap word
- **SWPB**: atomic swap byte

### PSR Transfer (bits [27:24] = 0001, bit 21 = I)

- **MRS**: read CPSR/SPSR into register
- **MSR**: write register/immediate to CPSR/SPSR

### Software Interrupt (bits [27:24] = 1111)

- **SWI**: trigger software interrupt. Comment field = imm24 (SWI number).

### Coprocessor Instructions

- **MRC/MCR**: coprocessor register transfer
- **LDC/STC**: coprocessor data transfer
- **CDP**: coprocessor data processing

Note: GBA has no physical coprocessors, but these instructions are used in some BIOS routines.

## 1.5 Thumb Instruction Decoding

All Thumb instructions are 16 bits. No condition codes (except conditional branches).

### Category 1: Move Shifted Register (bits [15:13] = 00, bits [12:11] != 11)

- **LSL Rd, Rm, #imm5**: logical shift left
- **LSR Rd, Rm, #imm5**: logical shift right
- **ASR Rd, Rm, #imm5**: arithmetic shift right

### Category 2: Add/Subtract (bits [15:13] = 00, bits [12:11] = 11)

- **ADD Rd, Rm, Rn**: add register
- **SUB Rd, Rm, Rn**: subtract register
- **ADD Rd, Rm, #imm3**: add immediate
- **SUB Rd, Rm, #imm3**: subtract immediate

### Category 3: Move/Compare/Add/Subtract Immediate (bits [15:11])

- **MOV Rd, #imm8**: move immediate (bits [15:11] = 00100)
- **CMP Rd, #imm8**: compare immediate (bits [15:11] = 00101)
- **ADD Rd, #imm8**: add immediate (bits [15:11] = 00110)
- **SUB Rd, #imm8**: subtract immediate (bits [15:11] = 00111)

### Category 4: ALU Operations (bits [15:10] = 010000)

| Opcode [9:6] | Mnemonic |
|---|---|
| 0000 | AND |
| 0001 | EOR |
| 0010 | LSL |
| 0011 | LSR |
| 0100 | ASR |
| 0101 | ADC |
| 0110 | SBC |
| 0111 | ROR |
| 1000 | TST |
| 1001 | NEG |
| 1010 | CMP |
| 1011 | CMN |
| 1100 | ORR |
| 1101 | MUL |
| 1110 | BIC |
| 1111 | MVN |

### Category 5: Hi Register Operations / Branch Exchange (bits [15:10] = 010001)

- **ADD Rd, Rm**: add (can use high registers)
- **CMP Rd, Rm**: compare (can use high registers)
- **MOV Rd, Rm**: move (can use high registers)
- **BX Rm**: branch and exchange

### Category 6: PC-relative Load (bits [15:11] = 01001)

- **LDR Rd, [PC, #imm8*4]**: load word from PC-relative address

### Category 7: Load/Store with Register Offset (bits [15:12] = 0101)

- **STR Rd, [Rb, Ro]**: store word
- **STRB Rd, [Rb, Ro]**: store byte
- **LDR Rd, [Rb, Ro]**: load word
- **LDRB Rd, [Rb, Ro]**: load byte
- **STRH Rd, [Rb, Ro]**: store halfword
- **LDRH Rd, [Rb, Ro]**: load halfword
- **LDRSB Rd, [Rb, Ro]**: load signed byte
- **LDRSH Rd, [Rb, Ro]**: load signed halfword

### Category 8: Load/Store with Immediate Offset (bits [15:13] = 011/100)

- **STR Rd, [Rb, #imm5*4]**: store word (011)
- **LDR Rd, [Rb, #imm5*4]**: load word (011)
- **STRB Rd, [Rb, #imm5]**: store byte (100)
- **LDRB Rd, [Rb, #imm5]**: load byte (100)
- **STRH Rd, [Rb, #imm5*2]**: store halfword (bits [15:12] = 1000)
- **LDRH Rd, [Rb, #imm5*2]**: load halfword (bits [15:12] = 1000)

### Category 9: SP-relative Load/Store (bits [15:12] = 1001)

- **STR Rd, [SP, #imm8*4]**: store word SP-relative
- **LDR Rd, [SP, #imm8*4]**: load word SP-relative

### Category 10: Load Address (bits [15:12] = 1010)

- **ADD Rd, PC, #imm8*4**: get address PC-relative
- **ADD Rd, SP, #imm8*4**: get address SP-relative

### Category 11: SP Operations (bits [15:12] = 1011)

- **ADD SP, #imm7*4** or **SUB SP, #imm7*4**: adjust stack pointer
- **PUSH {Rlist, LR}**: push registers (bit [15:8] = 1011010)
- **POP {Rlist, PC}**: pop registers (bit [15:8] = 1011110)

### Category 12: Multiple Load/Store (bits [15:12] = 1100)

- **STMIA Rb!, {Rlist}**: store multiple, increment after
- **LDMIA Rb!, {Rlist}**: load multiple, increment after

### Category 13: Conditional Branch (bits [15:12] = 1101, bit 11 = 0)

- **BEQ/BNE/BCS/BCC/BMI/BPL/BVS/BVC/BHI/BLS/BGE/BLT/BGT/BLE**: conditional branch
- Offset = sign_extend(imm8 << 1), condition in bits [11:8]

### Category 14: Software Interrupt (bits [15:8] = 11011111)

- **SWI imm8**: software interrupt

### Category 15: Unconditional Branch (bits [15:11] = 11100)

- **B target**: unconditional branch, offset = sign_extend(imm11 << 1)

### Category 16: Long Branch with Link (bits [15:11] = 11110/11111)

- **BL**: two-instruction sequence. First: offset high bits. Second: offset low bits.

## 1.6 Function Detection Heuristics

### Primary Detectors

1. **Branch-and-Link (BL) targets**: Every BL instruction's target is a function entry point
2. **ROM entry points**: 0x08000000 (reset), 0x08000004 (undefined instruction), 0x08000008 (SWI), 0x0800000C (prefetch abort), 0x08000010 (data abort), 0x08000018 (IRQ), 0x0800001C (FIQ)
3. **Vector table entries**: Addresses at 0x08000000-0x0800003C contain branch instructions

### Secondary Detectors

4. **Prologue patterns**:
   - ARM: `PUSH {r4-rN, lr}` or `STMDB sp!, {r4-rN, lr}`
   - Thumb: `PUSH {r4-r7, lr}`
5. **Thumb interworking**: BX to odd address = Thumb mode entry
6. **Data references**: Pointer tables pointing to code regions

### Function Boundary Rules

- Function starts at detected entry point
- Function ends at: return instruction (POP {PC}, BX LR), unconditional branch to different function, or next detected function entry
- Callee-saved registers (r4-r11) detected from PUSH/POP patterns
- Stack frame size detected from SUB SP, SP, #imm or ADD SP, SP, #imm

## 1.7 Code vs Data Separation

### Strategy

1. **Recursive descent**: Start from known entry points (vector table), follow all reachable code
2. **Literal pool detection**: After conditional branches, the next 1-4 words are often literal data (LDR Rd, [PC, #offset] targets)
3. **Branch table detection**: Patterns like `ADD PC, PC, Rn << 2` indicate jump/switch tables
4. **Heuristic scan**: After recursive descent, scan remaining ROM for undetected code patterns
5. **Oracle validation**: Compare coverage against mGBA execution traces from Plan 2

### Confidence Levels

- **High**: Directly reachable from entry points via direct branches
- **Medium**: Reachable via computed branches with resolved targets
- **Low**: Detected by heuristic pattern matching
- **Data**: Not matching any instruction pattern, or explicitly marked as data

## 1.8 Thumb/ARM Mode Switching

The GBA switches between ARM and Thumb mode via:
- **BX Rm**: Bit 0 of Rm = 1 means Thumb, 0 means ARM
- **BLX Rm**: Same as BX but also sets LR (ARMv5+, not on GBA ARM7TDMI)
- **Vector table entries**: Check if target address is odd (Thumb) or even (ARM)
- **Interworking**: BL from Thumb to ARM or vice versa via veneer code

The disassembler must track mode at each address. Default mode at reset is ARM. Mode switches at BX boundaries.

## 1.9 Disassembler API

```rust
pub struct Disassembler {
    rom_data: Vec<u8>,
    base_address: u32,
    functions: Vec<Function>,
    blocks: Vec<BasicBlock>,
    data_regions: Vec<DataRegion>,
    mode_map: BTreeMap<u32, bool>,  // address -> is_thumb
}

impl Disassembler {
    pub fn new(rom_data: Vec<u8>) -> Self;
    pub fn disassemble(&mut self) -> &Disassembly;
    pub fn decode_arm(&self, address: u32) -> Result<Instruction, DecodeError>;
    pub fn decode_thumb(&self, address: u32) -> Result<Instruction, DecodeError>;
    pub fn resolve_branch(&self, instr: &Instruction) -> Option<u32>;
    pub fn detect_functions(&mut self) -> &[Function];
    pub fn separate_data(&mut self) -> &[DataRegion];
    pub fn export_json(&self) -> Result<String, serde_json::Error>;
}
```

## 1.10 Testing Strategy

### Unit Tests
- Each ARM instruction category tested with known opcode/expected output pairs
- Each Thumb instruction category tested similarly
- Barrel shifter edge cases (shift by 0, 32, ROR with carry)

### Integration Tests
- Run disassembler on jsmolka/gba-tests ROMs
- Compare decoded instructions against ARMWrestler expected results
- Validate function detection on ROMs with known source code

### Accuracy Metrics
- ARM instruction decode accuracy: target >99.5% (533 test cases)
- Thumb instruction decode accuracy: target >99.5% (234 test cases)
- Function boundary detection: target >90% on test ROMs
- Code/data separation: target >95% vs oracle ground truth

## 1.11 Acceptance Criteria

Plan 1 is complete when:
- [ ] All ARMv4T instructions decode correctly (pass jsmolka ARM suite)
- [ ] All Thumb instructions decode correctly (pass jsmolka Thumb suite)
- [ ] CPSR flag behavior matches test ROM expectations
- [ ] Function boundaries identified for all test ROMs
- [ ] Code/data separation achieves >95% accuracy vs mGBA oracle
- [ ] Disassembly output serializes to valid JSON
- [ ] `cargo test -p gbatopy-disasm` passes all tests
- [ ] Crate compiles and exports a clean public API
