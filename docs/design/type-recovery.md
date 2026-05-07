# Plan 4: Type and Struct Recovery (Rust crate: pygba-types)

## 4.1 Objective

Analyze the SSA IR to recover type information: detect pointers, identify struct layouts, infer function signatures, and generate meaningful variable names. This stage bridges the gap between raw IR and human-readable code.

## 4.2 Type System

```rust
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GBAType {
    Void,
    U8,
    U16,
    U32,
    S8,
    S16,
    S32,
    Bool,
    Pointer(Box<GBAType>),
    Array(Box<GBAType>, usize),
    Struct(StructDef),
    Function(FunctionSig),
    HardwareRegister(HWReg),
    FixedString(usize),  // fixed-length character array
    Opaque,              // unknown, could not determine
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StructDef {
    pub name: String,
    pub fields: Vec<StructField>,
    pub total_size: usize,
    pub address: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StructField {
    pub offset: usize,
    pub name: String,
    pub ty: GBAType,
    pub access_count: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionSig {
    pub name: String,
    pub params: Vec<(String, GBAType)>,
    pub return_type: Box<GBAType>,
    pub calling_convention: CallingConvention,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum CallingConvention { Arm, Thumb }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum HWReg {
    Display,    // 0x04000000-0x0400005F
    Sound,      // 0x04000060-0x040000A5
    DMA,        // 0x040000B0-0x040000DE
    Timer,      // 0x04000100-0x0400010E
    Serial,     // 0x04000120-0x0400015A
    Keypad,     // 0x04000130-0x04000132
    Interrupt,  // 0x04000200-0x04000208
    System,     // 0x04000204, 0x04000300-0x04000301
}
```

## 4.3 Analysis Phases

### Phase 1: Pointer Detection

Identify which SSA values are used as memory addresses:

| Address Range | Inferred Type |
|---|---|
| 0x00000000-0x00003FFF | `Pointer(BIOS)` (read-only code) |
| 0x02000000-0x0203FFFF | `Pointer(U8)` or `Pointer(Struct)` in EWRAM |
| 0x03000000-0x03007FFF | `Pointer(U8)` or `Pointer(Struct)` in IWRAM |
| 0x04000000-0x040003FF | `HardwareRegister(HWReg::*)` |
| 0x05000000-0x050003FF | `Pointer(U16)` palette data |
| 0x06000000-0x06017FFF | `Pointer(U16)` VRAM |
| 0x07000000-0x070003FF | `Pointer(Struct)` OAM entries |
| 0x08000000-0x09FFFFFF | `Pointer(U8)` ROM data or code |
| 0x0E000000-0x0E00FFFF | `Pointer(U8)` SRAM |

Any value passed as the `address` parameter of a `Load*` or `Store*` IR node is marked as a pointer. The target type is inferred from the access width and the address range.

### Phase 2: Integer Type Narrowing

| Evidence | Inferred Type |
|---|---|
| Used in `LoadU8` / `StoreU8` | U8 |
| Used in `LoadU16` / `StoreU16` | U16 |
| Used in `LoadU32` / `StoreU32` | U32 |
| `And(v, 0xFF)` result | U8 (masked to byte) |
| `And(v, 0xFFFF)` result | U16 (masked to halfword) |
| Compared only against values 0-255 | candidate U8 |
| Compared only against values 0-65535 | candidate U16 |
| Used in signed comparison (`CmpLt` without `U`) | candidate S32 |
| Used with `Asr` (arithmetic shift) | signed type |
| Barrel shifter result with overflow check | U32 |

### Phase 3: Struct Recovery

1. **Base identification**: Find SSA values used as base addresses for multiple offset accesses
2. **Field grouping**: Group all accesses sharing the same base pointer
3. **Offset analysis**: Different offsets from the same base = different struct fields
4. **Type inference per field**: Access width (u8/u16/u32) determines field type
5. **Naming**: Match against GBATEK register definitions for I/O, or generate `field_0`, `field_1`, etc.
6. **Array detection**: Regular stride pattern (e.g., every +4 bytes) = array of the element type

Example:
```
v0 = const(0x04000000)       // base = I/O registers
store_u16(v0 + 0x00, v1)     // offset 0x00: DISPCNT (U16)
store_u16(v0 + 0x04, v2)     // offset 0x04: DISPSTAT (U16)
store_u16(v0 + 0x08, v3)     // offset 0x08: BG0CNT (U16)
```
The inferred struct matches the display controller register group from GBATEK.

For OAM (Object Attribute Memory), each entry is 12 bytes (3 x u32):
```
base = 0x07000000
field_0 (attr0) at offset 0:  u16  (y pos, rotation flag, size, etc.)
field_1 (attr1) at offset 2:  u16  (x pos, flip, size)
field_2 (attr2) at offset 4:  u16  (tile index, priority, palette)
field_3 (padding) at offset 6: u16  (unused)
// Next entry at offset 8
```
Array detection: stride of 8 bytes, 128 entries.

### Phase 4: Function Signature Recovery

ARM calling convention on GBA:
- **Parameters**: r0, r1, r2, r3 for first 4 arguments
- **Additional parameters**: Stack (SP-relative, beyond the 4 register params)
- **Return value**: r0
- **Callee-saved**: r4-r11, SP (detected from PUSH/POP patterns)
- **Caller-saved**: r0-r3, r12

Signature recovery algorithm:
1. Identify function entry point and all return instructions
2. Check if r0 is written before any return: it is the return value
3. Check registers read before first write: these are parameters (r0-r3)
4. Check for stack accesses at positive SP offsets: additional parameters
5. Use oracle trace to validate: actual values in r0-r3 at call sites

Naming progression:
- Initial: `sub_08001234` (address-based)
- After signature: `sub_08001234(r0: u32, r1: *u16) -> u32`
- After analysis: `copy_memory(src: *u8, dst: *u8, count: u32) -> u32`

### Phase 5: Variable Naming

| Context | Naming Convention |
|---|---|
| I/O register accesses | Named constants: `REG_DISPCNT`, `REG_BG0CNT`, etc. |
| Stack variables (SP-relative) | `local_0`, `local_1`, etc. or inferred from usage |
| Function parameters | `arg0`, `arg1`, etc. or inferred from usage |
| Return values | `result` or named by what they represent |
| ROM data references | `data_0800XXXX` initially, then `tiles_player` if identified |
| Loop counters | `i`, `j`, `count`, etc. based on usage pattern |
| Temporary SSA values | `v0`, `v1`, `v2`, ... |

### Phase 6: Hardware Register Mapping

Full I/O register mapping from GBATEK (0x04000000-0x040003FF):

| Address | Name | Width | Category |
|---|---|---|---|
| 0x04000000 | DISPCNT | U16 | Display |
| 0x04000004 | DISPSTAT | U16 | Display |
| 0x04000006 | VCOUNT | U16 (R) | Display |
| 0x04000008 | BG0CNT | U16 | Display |
| 0x0400000A | BG1CNT | U16 | Display |
| 0x0400000C | BG2CNT | U16 | Display |
| 0x0400000E | BG3CNT | U16 | Display |
| 0x040000B0-DE | DMA0-3 | U32 | DMA |
| 0x04000100-0E | TM0-3 | U16 | Timer |
| 0x04000130 | KEYINPUT | U16 (R) | Keypad |
| 0x04000132 | KEYCNT | U16 | Keypad |
| 0x04000200 | IE | U16 | Interrupt |
| 0x04000202 | IF | U16 | Interrupt |
| 0x04000208 | IME | U16 | Interrupt |

Common patterns to detect:
- **VBlank wait loop**: `while not (DISPSTAT & 0x0001): pass`
- **DMA setup sequence**: 3 consecutive writes to DMA SAD/DAD/CNT
- **Display mode switch**: write to DISPCNT with mode bits changed
- **Sound channel init**: write to SOUND*N registers in sequence
- **Interrupt handler setup**: write to IE + IME + vector table

## 4.4 Oracle-Assisted Type Recovery

The oracle validates static analysis with runtime data:

- **Pointer validation**: Oracle shows actual addresses used, confirming pointer types
- **Range validation**: Observed values confirm U8 vs U16 vs U32
- **Function signatures**: Actual r0-r3 values at call sites confirm parameter types
- **Struct layout verification**: Memory access patterns from trace confirm field offsets
- **String detection**: Sequences of byte reads from ROM with ASCII values = string data

## 4.5 Type Propagation

Once types are inferred, propagate through the IR:
- `v0 = load_u32(ptr)` where ptr is `*Struct` -> v0 has the Struct's field type
- `v1 = add(v0, const(1))` where v0 is U32 -> v1 is U32
- `v2 = and(v0, const(0xFF))` where v0 is U32 -> v2 is narrowed to U8
- `v3 = store_u16(ptr, v2)` where v2 is U16 -> consistent field type

## 4.6 Type Inference API

```rust
pub struct TypeAnalyzer {
    types: HashMap<u32, GBAType>,      // Value.id -> type
    functions: HashMap<u32, FunctionSig>,
    structs: Vec<StructDef>,
    register_map: HashMap<u32, String>,  // I/O address -> register name
}

impl TypeAnalyzer {
    pub fn new() -> Self;
    pub fn analyze_function(&mut self, ir: &IRFunction) -> Result<(), TypeError>;
    pub fn detect_pointers(&mut self, ir: &IRFunction) -> Vec<u32>;
    pub fn narrow_integers(&mut self, ir: &IRFunction);
    pub fn recover_structs(&mut self, ir: &IRFunction) -> Vec<StructDef>;
    pub fn infer_signatures(&mut self, ir: &IRFunction) -> FunctionSig;
    pub fn generate_names(&mut self, ir: &mut IRFunction);
    pub fn map_hardware_registers(&mut self, ir: &IRFunction);
    pub fn apply_oracle_data(&mut self, oracle: &OracleDB);
    pub fn get_type(&self, value_id: u32) -> &GBAType;
    pub fn export_types(&self) -> TypeReport;
}
```

## 4.7 Testing

- Test type inference on ROMs with known source code
- Validate struct recovery against GBATEK register definitions
- Verify function signatures match ARM calling convention
- Compare oracle-inferred types against actual types in test ROMs
- Verify pointer detection accuracy with oracle address data

## 4.8 Acceptance Criteria

- [ ] All I/O register accesses correctly typed and named
- [ ] Pointer detection accuracy >90% on test ROMs
- [ ] Struct recovery identifies known hardware register groups (display, DMA, timer, etc.)
- [ ] Function signatures match ARM calling convention
- [ ] Variable names are consistent within each function
- [ ] `cargo test -p pygba-types` passes all tests
