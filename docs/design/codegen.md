# Plan 5: Python Code Generation (Rust crate: pygba-codegen)

> **⚠️ HISTORICAL DESIGN DOCUMENT**
>
> This document describes the original SSA-IR-based codegen design (`pygba-codegen` consuming typed IR with phi nodes).
> The **actual implementation** differs: codegen emits Python directly from disassembly via per-instruction `generate_*_python()`
> functions, using a `dispatch_table`/`func_map`/`call_func` runtime with an embedded Py7TDMI interpreter.
> `codegen/ir_ops.rs` is empty; the `gbatopy-ir` crate exists but is not wired into the emit path.
>
> For the **current** architecture, see:
> - [`docs/design/transpilation-patterns.md`](transpilation-patterns.md) — interpreter fallback, dispatch table, hotspot tracking
> - [`docs/runtime-architecture.md`](../runtime-architecture.md) — memory management, address mapping
> - [`docs/codegen-pitfalls.md`](../codegen-pitfalls.md) — bugs fixed during codegen development

## 5.1 Objective

Convert the typed, optimized SSA IR into readable, executable Python 3 source code that uses `gba_runtime` for hardware abstraction. The generated code is pure Python. Rust is not needed at runtime.

## 5.2 Output Structure

> **NOTE (2026-04-17)**: The original plan described a directory structure, but the actual implementation generates a **single Python file** with inline runtime for simplicity.

```
output_python/
└── {rom_name}.py       # Single standalone file with inline gba_runtime classes
```

The generated file contains:
- All GBA hardware emulation classes (CPU, PPU, APU, DMA, BIOS, etc.)
- Decompiled ARM/Thumb code as Python functions
- Asset data extracted to separate .bin files (palette.bin, tiles.bin, sprites.bin, tilemap.bin) and loaded via load_assets() at runtime
- Game loop with keyboard input handling
- No external dependencies except pygame

## 5.2.1 Legacy Description (Original Plan)

```
output/
├── main.py              # Entry point: loads ROM, initializes runtime, calls entry function
├── functions/           # Decompiled functions, one file per function
│   ├── __init__.py
│   ├── sub_08001234.py
│   ├── sub_08002000.py
│   └── ...
├── data/                # Extracted ROM data
│   ├── __init__.py
│   ├── assets.py        # Tile, sprite, palette data as Python lists
│   └── tables.py        # Lookup tables, string tables
└── runtime/             # gba_runtime package (copy from Plan 0)
    └── ...
```

## 5.3 IR-to-Python Translation Rules

### Arithmetic

| IR Node | Python |
|---|---|
| `Add { dest, lhs, rhs }` | `dest = (lhs + rhs) & 0xFFFFFFFF` |
| `Sub { dest, lhs, rhs }` | `dest = (lhs - rhs) & 0xFFFFFFFF` |
| `Mul { dest, lhs, rhs }` | `dest = (lhs * rhs) & 0xFFFFFFFF` |
| `DivU { dest, lhs, rhs }` | `dest = lhs // rhs` |
| `DivS { dest, lhs, rhs }` | `dest = _sign_div(lhs, rhs)` |
| `ModU { dest, lhs, rhs }` | `dest = lhs % rhs` |
| `Neg { dest, value }` | `dest = (-value) & 0xFFFFFFFF` |

### Bitwise

| IR Node | Python |
|---|---|
| `And { dest, lhs, rhs }` | `dest = lhs & rhs` |
| `Or { dest, lhs, rhs }` | `dest = lhs \| rhs` |
| `Xor { dest, lhs, rhs }` | `dest = lhs ^ rhs` |
| `Not { dest, value }` | `dest = ~value & 0xFFFFFFFF` |
| `Shl { dest, value, amount }` | `dest = (value << amount) & 0xFFFFFFFF` |
| `Shr { dest, value, amount }` | `dest = value >> amount` |
| `Asr { dest, value, amount }` | `dest = _asr(value, amount)` |

### Comparison

| IR Node | Python |
|---|---|
| `CmpEq { dest, lhs, rhs }` | `dest = 1 if lhs == rhs else 0` |
| `CmpNe { dest, lhs, rhs }` | `dest = 1 if lhs != rhs else 0` |
| `CmpLt { dest, lhs, rhs }` | `dest = 1 if _signed(lhs) < _signed(rhs) else 0` |
| `CmpUlt { dest, lhs, rhs }` | `dest = 1 if lhs < rhs else 0` |

### Memory

| IR Node | Python |
|---|---|
| `LoadU8 { dest, address }` | `dest = runtime.memory.read_u8(address)` |
| `LoadU16 { dest, address }` | `dest = runtime.memory.read_u16(address)` |
| `LoadU32 { dest, address }` | `dest = runtime.memory.read_u32(address)` |
| `StoreU8 { address, value }` | `runtime.memory.write_u8(address, value)` |
| `StoreU16 { address, value }` | `runtime.memory.write_u16(address, value)` |
| `StoreU32 { address, value }` | `runtime.memory.write_u32(address, value)` |

### I/O Registers

| IR Node | Python |
|---|---|
| `IORead { dest, register }` | `dest = runtime.read_io(0x0400XXXX)` |
| `IOWrite { register, value }` | `runtime.write_io(0x0400XXXX, value)` |

With named constants imported from `gba_runtime.constants`.

### Control Flow

| IR Node | Python |
|---|---|
| `Branch { condition, true_block, false_block }` | `if condition: true_block(runtime) else: false_block(runtime)` |
| `Branch { condition, true_block, None }` | `if condition: true_block(runtime)` |
| `Call { dest, target, args }` | `result = target(runtime, *args); dest = result` |
| `Ret { value }` | `return value` |
| `Ret { None }` | `return` |

### GBA-Specific

| IR Node | Python |
|---|---|
| `SWICall { number, ... }` | `result = runtime.bios.handle(number, regs)` |
| `DMATransfer { ch, src, dst, cnt, ctrl }` | `runtime.dma.get_channel(ch).configure(src, dst, cnt, ctrl)` |
| `WaitVBlank` | `runtime.run_until_vblank()` |

### Phi Nodes

Phi nodes are resolved during code generation by merging variable names:

```python
# IR has phi: v2 = (block_A -> v0, block_B -> v1)
# Generated Python tracks which block we came from:
v2 = v0 if came_from_a else v1
# Or simply reuses the last assignment if control flow is clear
```

## 5.4 Control Flow Reconstruction

### If/Else
```python
if v0 == 0:
    sub_08001234(runtime)
else:
    sub_08002000(runtime)
```

### While Loops (back edge detection)
```python
while True:
    v0 = runtime.memory.read_u16(0x04000004)  # DISPSTAT
    if not (v0 & 0x0001):  # VBlank flag
        break
    # loop body
```

### Switch/Case (branch tables)
```python
if v0 == 0:
    handler_0(runtime)
elif v0 == 1:
    handler_1(runtime)
elif v0 == 2:
    handler_2(runtime)
else:
    default_handler(runtime)
```

### Nested Loops
```python
for y in range(160):
    for x in range(240):
        runtime.memory.write_u16(vram_base + (y * 240 + x) * 2, color)
```

## 5.5 Function Generation Template

```python
"""Decompiled from GBA ROM address 0x08001234 (ARM mode)."""
from __future__ import annotations
from gba_runtime.runtime import GBARuntime
from gba_runtime.constants import REG_DISPCNT, DISPCNT_BG_MODE


def sub_08001234(runtime: GBARuntime, r0: int, r1: int, r2: int) -> int:
    """Copies count bytes from src to dst.

    Decompiled from 0x08001234 (ARM, 24 instructions).

    Args:
        r0: Source address (EWRAM/ROM pointer)
        r1: Destination address (EWRAM/VRAM pointer)
        r2: Byte count

    Returns:
        Destination address after copy
    """
    src = r0
    dst = r1
    count = r2

    while count > 0:
        byte_val = runtime.memory.read_u8(src)
        runtime.memory.write_u8(dst, byte_val)
        src = (src + 1) & 0xFFFFFFFF
        dst = (dst + 1) & 0xFFFFFFFF
        count = (count - 1) & 0xFFFFFFFF

    return dst
```

## 5.6 Data Extraction

### Tile Data
```python
# data/assets.py
TILES_PLAYER = [
    # 4bpp tiles, 8x8 pixels each
    # Source: ROM address 0x08008000, 256 tiles
    [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
     0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
     ...],
    ...
]
```

### Palette Data
```python
# data/assets.py
PALETTE_BG0 = [
    # 256 colors, RGB555 format
    # Source: ROM address 0x08007000
    (0, 0, 0),        # Color 0: transparent/black
    (31, 0, 0),       # Color 1: max red
    (0, 31, 0),       # Color 2: max green
    ...
]
```

### String Tables
```python
# data/tables.py
STRINGS = {
    0x08009000: "Hello World",
    0x08009010: "Game Over",
    0x08009020: "Press Start",
}
```

### Lookup Tables
```python
# data/tables.py
SINE_TABLE = [
    # u16 values, 256 entries
    # Source: ROM address 0x0800A000
    0, 402, 804, 1206, 1608, 2010, 2412, 2814,
    ...
]
```

## 5.7 Special Pattern Recognition

The codegen detects common GBA programming patterns and emits clean Python:

### VBlank Wait Loop
```python
# Detected pattern: loop reading DISPSTAT bit 0
while not (runtime.memory.read_u16(REG_DISPSTAT) & DISPSTAT_VBLANK_FLAG):
    pass
```

### DMA Setup
```python
# Detected pattern: consecutive writes to DMA SAD/DAD/CNT
from gba_runtime.constants import DMA_SRC_INC, DMA_DST_INC, DMA_32BIT, DMA_ENABLE

runtime.dma.get_channel(3).configure(
    src=0x02000000,
    dst=0x06000000,
    count=0x4000,
    control=DMA_SRC_INC | DMA_DST_INC | DMA_32BIT | DMA_ENABLE,
)
```

### Key Input Polling
```python
# Detected pattern: load KEYINPUT, check button bits
keys = runtime.keypad.get_state()
if not (keys & KEY_A):
    handle_a_press(runtime)
if not (keys & KEY_START):
    handle_start(runtime)
```

### OAM Sprite Setup
```python
# Detected pattern: write 3 halfwords to OAM at computed offset
runtime.display.set_oam(sprite_index, attr0=0x8000 | y_pos, attr1=x_pos, attr2=tile_idx)
```

### Interrupt Handler Registration
```python
# Detected pattern: write handler address to vector table + enable in IE/IME
runtime.interrupts.set_handler(IRQ_VBLANK, vblank_handler)
runtime.interrupts.enable_irq(IRQ_VBLANK)
runtime.interrupts.master_enable(True)
```

## 5.8 Entry Point Generation

`main.py` ties everything together:

```python
"""Auto-generated entry point for GBA ROM."""
from gba_runtime.runtime import GBARuntime
from functions import sub_080000C0, sub_08000100


def main():
    runtime = GBARuntime("game.gba")
    # Reset vector at 0x08000000 jumps to 0x080000C0
    sub_080000C0(runtime)


if __name__ == "__main__":
    main()
```

## 5.9 Code Formatting Rules

- Black-compatible formatting (4-space indent, 88-character line limit)
- Type hints on all function signatures
- Docstrings include original ROM address and instruction mode
- Imports grouped: stdlib, gba_runtime, local functions, data
- No global mutable state; all state flows through the `runtime` parameter
- Constants from `gba_runtime.constants` imported at module top
- Hex formatting for addresses and hardware values: `0x04000000`
- Decimal formatting for game logic values: `count = 32`

## 5.10 Helper Functions

Some ARM operations need Python helper functions for correct behavior:

```python
# runtime/helpers.py

def _asr(value: int, amount: int) -> int:
    """Arithmetic shift right (sign-extending)."""
    if amount == 0:
        return value
    value &= 0xFFFFFFFF
    if value & 0x80000000:
        return (value >> amount) | (0xFFFFFFFF << (32 - amount)) & 0xFFFFFFFF
    return value >> amount

def _signed(value: int) -> int:
    """Convert unsigned 32-bit to signed Python int."""
    if value & 0x80000000:
        return value - 0x100000000
    return value

def _sign_div(a: int, b: int) -> int:
    """Signed integer division matching ARM behavior."""
    sa = _signed(a)
    sb = _signed(b)
    if sb == 0:
        return 0
    result = sa // sb
    return result & 0xFFFFFFFF
```

## 5.11 Output Validation

1. **Syntax check**: `python -c "compile(open('main.py').read(), 'main.py', 'exec')"` passes
2. **Type check**: `mypy output/` passes with no errors
3. **Runtime check**: Execute with gba_runtime for 60+ frames
4. **Memory comparison**: Compare register + memory state against oracle at each frame boundary
5. **Visual comparison**: If display implemented, compare framebuffer against mGBA screenshot (pixel diff < 1%)

### Coverage Targets

| Metric | Target |
|---|---|
| Syntax validity | 100% (all generated code compiles) |
| Runtime correctness | >95% register value match vs oracle |
| Memory accuracy | >95% memory state match vs oracle |
| No Rust dependency | 100% (pure Python only) |
| Type check (mypy) | ⚠️ Not run as part of CI |

### mGBA Golden Screenshot Workflow

mGBA SDL supports Lua scripting via the `-S` flag. Golden screenshots are captured with:

```bash
./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua test_roms/roms/<rom>.gba
```

The Lua API quirk: use `memory.read8(addr)` (not `memory:read_u8`). For u16/u32, read bytes
manually and combine little-endian. See `scripts/screenshot/screenshot.lua` for the working
capture script, and `scripts/verify/compare_screenshots.py` for the pixel-diff comparator
(PASS if difference < 30%).

## 5.12 Code Generation API

```rust
pub struct CodeGenerator {
    config: CodegenConfig,
}

#[derive(Debug, Clone)]
pub struct CodegenConfig {
    pub output_dir: PathBuf,
    pub module_per_function: bool,   // true = one .py file per function
    pub format_black: bool,          // run black formatter on output
    pub extract_assets: bool,        // extract tile/palette data
    pub pattern_recognition: bool,   // detect GBA patterns (DMA, VBlank, etc.)
}

impl CodeGenerator {
    pub fn new(config: CodegenConfig) -> Self;
    pub fn generate(&self, ir: &[IRFunction], types: &TypeAnalyzer) -> Result<(), CodegenError>;
    pub fn generate_function(&self, func: &IRFunction, types: &TypeAnalyzer) -> Result<String, CodegenError>;
    pub fn generate_main(&self, entry_point: u32) -> Result<String, CodegenError>;
    pub fn extract_data(&self, rom: &[u8], data_regions: &[DataRegion]) -> Result<(), CodegenError>;
    pub fn validate_output(&self) -> Result<ValidationReport, CodegenError>;
}
```

## 5.13 Testing

- Generate Python from each test ROM's IR
- Run generated code through gba_runtime for 60 frames
- Capture memory state at each frame boundary
- Compare against mGBA oracle data from the same ROM
- Assert: register values match, memory writes match, no crashes

## 5.14 Acceptance Criteria (Updated 2026-04-17)

### Implemented ✅
- [x] Generated Python is syntactically valid for all test ROMs (41 ROMs tested)
- [x] Generated Python runs without runtime errors (exit code 0)
- [x] No Rust dependency at runtime (pure Python only)
- [x] `cargo build` passes with 6 crates, 0 errors
- [x] Zero NotImplementedError stubs in Python runtime
- [x] Game loop with pygame renders window
- [x] ARM7TDMI interpreter executes real ARM code
- [x] Asset extraction script works (LZ77/Huffman/RLE decompression)
- [x] 54 BIOS handlers implemented
- [x] PPU Mode 3 verified (stripes.gba 100% golden match); Mode 0 verified (shades.gba 100% golden match, after 5 bug fixes); Mode 4 partial; Mode 1/2 affine, windows, blend, mosaic = stubs
- [x] Conditional execution FIXED (branch instructions check CPSR flags)

### Verification Scripts
- [x] `compare_screenshots.py` - mGBA golden vs transpiled pixel comparison
- [x] `coverage_tracker.py` - instruction codegen coverage tracking
- [x] `screenshot.lua` - mGBA golden screenshot capture

### Known Limitations (Updated 2026-07-06)
- [ ] **STMFD/LDMFD register order** (BLOCKING) — corrupts stack on real-game ROMs → PC=0x04040404 (hello.gba). See `docs/codegen-pitfalls.md`.
- [ ] **helloAudio, rates** smoke failures — cause undiagnosed
- [ ] **Automated ScreenshotGolden** — 32 goldens exist, comparison not wired into CI
- [ ] Test ROMs are minimal - no compressed graphics/audio (need commercial ROMs with LZ77/Huffman/RLE data)
- [x] Visual rendering verified against mGBA (stripes.gba, shades.gba — 100% golden match, manual comparison)
- [ ] APU audio synthesis not yet producing sound output
- [ ] Affine backgrounds (Mode 1/2) not rendered
- [ ] Window/blend/mosaic effects not rendered
