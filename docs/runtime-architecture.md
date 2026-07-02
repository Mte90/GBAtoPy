# GBAtoPy Python Runtime Architecture

> **Target Audience**: AI agents contributing to GBAtoPy code generation
>
> **Purpose**: Document the runtime architecture to prevent common mistakes in code generation and debugging

---

## 1. Memory Management

### 1.1 Memory Map Overview

The GBA memory map is implemented in `memory.py` with the following regions:

| Region | Start | End | Size | Purpose |
|--------|-------|-----|------|---------|
| BIOS | 0x00000000 | 0x00003FFF | 16KB | Boot code (read-only) |
| EWRAM | 0x02000000 | 0x0203FFFF | 256KB | External work RAM |
| IWRAM | 0x03000000 | 0x03007FFF | 32KB | Internal work RAM |
| IO | 0x04000000 | 0x040003FF | 1KB | Memory-mapped I/O registers |
| Palette | 0x05000000 | 0x050003FF | 1KB | Color palette RAM |
| VRAM | 0x06000000 | 0x06017FFF | 96KB | Video RAM |
| OAM | 0x07000000 | 0x070003FF | 1KB | Object attribute memory |
| ROM | 0x08000000 | 0x09FFFFFF | 32MB | Game ROM |
| SRAM | 0x0A000000 | 0x0A00FFFF | 64KB | Save RAM |

### 1.2 Address Mapping: `_map_address()`

The `_map_address()` function converts **relative addresses** (used by some test ROMs) to **absolute GBA addresses**.

**Why relative addresses exist**: Some ROMs (like `stripes.gba`) use relative addressing where:
- `0x00000-0x0FFFF` → MMIO (relative to 0x04000000)
- `0x10000-0x37FFF` → VRAM (relative to 0x06000000)
- `0x40000-0x403FF` → Palette (relative to 0x05000000)
- `0x60000-0x603FF` → OAM (relative to 0x07000000)

**Implementation** (lines 320-360 in memory.py):
```python
def _map_address(self, addr: int) -> int:
    # Handle relative addresses used by some test ROMs
    if 0x00000 <= addr <= 0x0FFFF:
        return ((addr - 0x00000) & 0x03FF) | 0x04000000  # MMIO
    
    if 0x10000 <= addr <= 0x37FFF:
        return ((addr - 0x10000) & 0x17FFF) | 0x06000000  # VRAM
    
    if 0x40000 <= addr <= 0x403FF:
        return ((addr - 0x40000) & 0x03FF) | 0x05000000  # Palette
    
    if 0x60000 <= addr <= 0x603FF:
        return ((addr - 0x60000) & 0x03FF) | 0x07000000  # OAM
    
    # Absolute address handling for all other regions
    if 0x00000000 <= addr <= 0x01FFFFFF:
        return addr & 0x00003FFF  # BIOS
    
    if 0x02000000 <= addr <= 0x02FFFFFF:
        return (addr & 0x0003FFFF) | 0x02000000  # EWRAM
    
    if 0x03000000 <= addr <= 0x03FFFFFF:
        return (addr & 0x00007FFF) | 0x03000000  # IWRAM
    
    if 0x04000000 <= addr <= 0x04FFFFFF:
        return (addr & 0x000003FF) | 0x04000000  # IO
    
    if 0x05000000 <= addr <= 0x05FFFFFF:
        return (addr & 0x000003FF) | 0x05000000  # Palette
    
    if 0x06000000 <= addr <= 0x06FFFFFF:
        return (addr & 0x00017FFF) | 0x06000000  # VRAM
    
    if 0x07000000 <= addr <= 0x07FFFFFF:
        return (addr & 0x000003FF) | 0x07000000  # OAM
    
    return addr  # ROM, SRAM, etc.
```

### 1.3 CRITICAL BUG PATTERN: Double Address Mapping

**The Bug**:
```python
# ❌ WRONG - Double mapping causes incorrect addresses
def write_u32(self, addr: int, value: int):
    addr = self._map_address(addr)  # First mapping
    self.write_u8(addr, value & 0xFF)  # write_u8 calls _map_address AGAIN!
```

**The Fix** (lines 483-548 in memory.py):
```python
def write_u8(self, addr: int, value: int):
    addr &= 0xFFFFFFFF
    value &= 0xFF
    # Note: write_u8 is called from write_u32/write_u16 AFTER _map_address
    # so we don't map again - the address is already absolute
    # Only map if this is a direct call (not from write_u32/write_u16)
    # We detect this by checking if addr is already in an absolute region
    if not (0x04000000 <= addr <= 0x07FFFFFF):
        addr = self._map_address(addr)
    
    # ... rest of implementation
```

**Why this works**:
- `write_u32()` and `write_u16()` call `_map_address()` first, then call `write_u8()`
- `write_u8()` detects if the address is already in the absolute range (0x04000000-0x07FFFFFF)
- If already absolute, it skips the second mapping
- If relative (0x00000-0x0FFFF), it performs the mapping

**Impact**: This bug causes writes to go to wrong memory regions, breaking game logic.

### 1.4 Read/Write Methods

| Method | Size | Mapping | Notes |
|--------|------|---------|-------|
| `read_u8(addr)` | 8-bit | Yes | Calls `_map_address()` internally |
| `read_u16(addr)` | 16-bit | Yes | Calls `_map_address()` internally |
| `read_u32(addr)` | 32-bit | Yes | Calls `_map_address()` internally |
| `write_u8(addr, value)` | 8-bit | Conditional | Skips mapping if already absolute |
| `write_u16(addr, value)` | 16-bit | Yes | Calls `_map_address()` internally |
| `write_u32(addr, value)` | 32-bit | Yes | Calls `_map_address()` internally |

**Key Insight**: All read/write methods call `_map_address()` internally. The "conditional mapping" in `write_u8()` is a workaround for the double-mapping issue when called from `write_u16()`/`write_u32()`.

---

## 2. Code Generation Pipeline

The transpiler uses a **3-stage pipeline**:

```
Stage 1: Disassembly
  ↓
Stage 2: Asset Extraction
  ↓
Stage 3: Python Code Generation
```

### 2.1 Stage 1: Disassembly

**Location**: `gbatopy_disasm` crate (separate from codegen)

**What it does**:
- Decodes ARM/Thumb instructions from ROM bytes
- Tracks ARM/Thumb mode via `ModeTracker`
- Builds control flow graph (CFG) for branch target analysis
- Identifies reachable addresses for large ROMs

**Output**: `Vec<DecodedInstruction>` with:
- `address`: PC address (0x08000000-based)
- `opcode`: Instruction mnemonic (e.g., "ADD", "LDR", "BEQ")
- `operands`: List of operand types (Register, Immediate, MemoryAddress)
- `width`: Instruction size (2 for Thumb, 4 for ARM)

### 2.2 Stage 2: Asset Extraction

**Location**: `asset_extractor` module

**What it extracts**:
- **Palette data**: 16-bit RGB555 colors (up to 256 colors)
- **Tile data**: 4BPP/8BPP tile graphics (32 bytes per 4BPP tile, 64 bytes per 8BPP tile)
- **Tilemap data**: 16-bit tile indices with palette/priority/flip flags
- **Wave data**: Audio samples for APU Channel 3
- **Sample metadata**: (start_addr, length, format) tuples

**Output**: `Assets` struct with embedded bytearray data

### 2.3 Stage 3: Python Code Generation

**Location**: `pipeline_cmd.rs` (main entry point)

**What it generates**:

1. **Runtime embedding** (lines 279-345):
   - Embeds all runtime modules (memory.py, ppu.py, arm7tdmi.py, bios.py, etc.)
   - Strips relative imports (`.`, `from gba_runtime`)
   - Minifies by removing blank lines

2. **ROM data loading** (lines 616-624):
   ```python
   def load_rom_data():
       with open('rom_name.bin', 'rb') as f:
           return bytearray(f.read())
   ROM_DATA = load_rom_data()
   ```

3. **Asset embedding** (lines 627-713):
   - `WAVE_DATA`: Audio samples
   - `bg0_tilemap`: Background tilemap
   - `tile_data`: Tile graphics
   - `palette_data`: Color palette
   - `SAMPLES`: Sample metadata

4. **Basic block generation** (lines 477-869):
   - Groups sequential instructions into basic blocks
   - Branch targets start new blocks
   - Branch instructions terminate their block
   - Generates `func_{address}()` for each block

5. **Dispatch table** (lines 874-886):
   ```python
   dispatch_table = {
       0x0000000: func_08000000,
       0x0000001: func_08000004,
       # ... sparse mapping
   }
   ```

6. **Game loop** (lines 889-1080):
   - Executes instructions via dispatch table
   - Handles pygame events
   - Manages frame timing
   - Supports headless mode and screenshots

### 2.4 Basic Block Merging

**Algorithm** (lines 527-599 in pipeline_cmd.rs):

1. **Pass 1**: Collect all branch targets from branch instructions (B, BEQ, BNE, etc.)
2. **Pass 2**: Group instructions into blocks:
   - Branch targets start new blocks
   - Branch instructions terminate their block
   - Non-sequential addresses start new blocks
   - Sequential instructions merge into same block

**Example**:
```
0x08000000: ADD r0, r1, r2    \
0x08000004: ADD r0, r0, r3     }→ Block 1 (0x08000000)
0x08000008: BNE 0x08000020   /
0x0800000C: ADD r1, r2, r3    \
0x08000010: LDR r0, [r1]      }→ Block 2 (0x0800000C)
0x08000014: ADD r0, r0, r4   /
0x08000020: STR r0, [r2]      }→ Block 3 (0x08000020)
```

**Benefits**:
- Reduces function call overhead
- Improves execution speed (52-80% code size reduction)
- Better JIT compilation opportunities

**⚠️ CRITICAL BUG: NOP Block Detection**

The pipeline marks blocks as "NOP" if they only contain PC advances and comments. This is WRONG for initialization code that sets up registers before loops.

**Symptom**: Code jumps over initialization, loops execute with wrong register values (e.g., R0=0 instead of expected value)

**Check**: Search dispatch table for missing addresses:
```python
# In generated Python, check if addresses between branch source and target exist
grep -n "0x000003E" rom.py  # Should find func_080000F8
```

**Fix**: In `pipeline_cmd.rs`, the NOP detection logic (lines 841-869) must be updated to NOT mark blocks as NOP if they contain register initialization instructions.

**Workaround**: Manually add missing functions to dispatch table in generated Python.

---

## 3. MMIO Register Handling

### 3.1 MMIO Register Map

| Range | Purpose | Key Registers |
|-------|---------|---------------|
| 0x04000000-0x0400005F | PPU | DISPCNT, BG0CNT, BG1CNT, BG2CNT, BG3CNT |
| 0x04000060-0x0400008F | APU | SOUNDCNT_L, SOUNDCNT_H, SOUNDCNT_X |
| 0x04000090-0x0400009F | DMA | DMA0SAD, DMA0DAD, DMA0CNT_L, etc. |
| 0x040000B0-0x040000CF | DMA | DMA1-3 registers |
| 0x04000100-0x0400010F | Timers | TM0CNT_L, TM0CNT_H, TM1CNT_L, etc. |
| 0x04000130-0x04000133 | Input | KEYINPUT, KEYCNT |
| 0x04000200-0x04000208 | IRQ | IE, IF, IME |

### 3.2 Dispatch Mechanism

**`_dispatch_hal_write()`** (lines 136-159 in memory.py):

```python
def _dispatch_hal_write(self, addr: int, value: int):
    # PPU registers (0x04000000-0x0400005F)
    if 0x04000000 <= addr <= 0x0400005F:
        if self._ppu:
            self._ppu.write_register(addr, value)
    
    # Window registers (0x04000048-0x0400004F)
    if 0x04000048 <= addr <= 0x0400004F:
        self._handle_window_write(addr, value)
    
    # Affine background registers (0x04000080-0x0400008E)
    if 0x04000080 <= addr <= 0x0400008E:
        self._handle_affine_bg_write(addr, value)
    
    # Sound registers (0x04000060-0x0400008F)
    if 0x04000060 <= addr <= 0x0400008F:
        self._handle_sound_write(addr, value)
    
    # APU registers (0x04000090-0x040000AF)
    if 0x04000090 <= addr <= 0x040000AF:
        if self._apu:
            self._apu.write_register(addr, value)
    
    # DMA registers (0x040000B0-0x040000EF)
    if 0x040000B0 <= addr <= 0x040000EF:
        if self._dma:
            self._handle_dma_write(addr, value)
    
    # Timer registers (0x04000100-0x0400010F)
    if 0x04000100 <= addr <= 0x0400010F:
        if self._timers:
            self._handle_timer_write(addr, value)
    
    # Interrupt registers (0x04000200-0x04000208)
    if 0x04000200 <= addr <= 0x04000208:
        if self._interrupts:
            self._handle_interrupt_write(addr, value)
```

### 3.3 Register Handlers

**DISPCNT (0x04000000)**:
- Controls display mode (bits 0-2)
- Enables background layers (bits 8-13)
- Sets frame buffer mode (bit 7)

**Example**: `DISPCNT = 0x0400` → Mode 1, BG0/BG1 enabled

**Timer Registers** (lines 230-262 in memory.py):
```python
def _handle_timer_write(self, addr: int, value: int):
    timer_idx = (addr - 0x04000100) // 4
    reg_offset = (addr - 0x04000100) % 4
    
    if reg_offset == 0:  # CNT_L: reload value
        self._timers.set_reload(timer_idx, value & 0xFFFF)
    elif reg_offset == 2:  # CNT_H: control register
        self._timers.set_control(timer_idx, value & 0xFFFF)
```

### 3.4 Register Registration

**`register_mmio_write()`** (lines 113-119 in memory.py):
```python
def register_mmio_write(self, offset: int, handler: Callable[[int, int], None]):
    if 0 <= offset < MemoryMap.IO_SIZE:
        self._mmio_write_handlers[offset] = handler
```

**Usage in codegen**: Runtime modules register handlers for their registers:
```python
# In timers.py
memory.register_mmio_write(0x00, timers.handle_timer0_write)
memory.register_mmio_write(0x04, timers.handle_timer1_write)
# ...
```

---

## 4. Common Pitfalls for AI Agents

### 4.1 Never Modify .gba ROM Files

**Rule**: All debugging/fixes must be done in the **generated Python**, not the ROM.

**Why**:
- ROM files are binary blobs that can't be easily modified
- Changes to ROM require re-transpilation
- Python output is human-readable and modifiable

**Correct workflow**:
1. Transpile ROM → Python
2. Run Python and observe bug
3. Patch Python code to fix bug
4. Fix the codegen (Rust) to prevent future occurrences

### 4.2 Address Mapping Gotchas

**Absolute vs Relative Addresses**:
- Most ROMs use absolute addresses (0x06000000 for VRAM)
- Some test ROMs use relative addresses (0x10000 for VRAM)
- `_map_address()` handles both, but codegen must be aware

**Codegen tip**: When generating LDR/STR with immediate offsets:
```python
# ❌ WRONG - doesn't handle relative addresses
memory.write_u32(0x06000000, value)

# ✅ CORRECT - uses register + offset (lets _map_address handle it)
memory.write_u32(r0 + 0, value)
```

### 4.3 Double Mapping Bug

**Symptoms**:
- Writes go to wrong memory regions
- VRAM writes affect OAM or Palette
- MMIO writes affect ROM data

**Fix**: `write_u8()` must check if address is already absolute:
```python
if not (0x04000000 <= addr <= 0x07FFFFFF):
    addr = self._map_address(addr)
```

### 4.4 PC-Relative LDR/STR

**Problem**: PC-relative loads use PC+8 offset (ARM) or PC+4 (Thumb):
```python
# ARM: LDR r0, [PC, #12] → reads from address (PC+8+12)
# Thumb: LDR r0, [PC, #4] → reads from address (PC+4+4)
```

**Codegen handling** (in `load_store.rs`):
- Calculate target address as `PC + offset + instruction_size`
- For ARM: `PC + 8 + offset`
- For Thumb: `PC + 4 + offset`

### 4.5 LDM/STM Parsing Limitations

**Known Issue**: LDM/STM instruction parsing is imperfect.

**Symptoms**:
- Multiple register loads/stores may not work correctly
- Writeback mode may not update base register

**Workaround**: Test with simple LDM/STM cases first. Complex cases may need manual codegen.

### 4.6 CPSR Flag Tracking

**Critical**: All conditional instructions must track CPSR flags.

**Flag bits**:
- N (bit 31): Negative result
- Z (bit 30): Zero result
- C (bit 29): Carry/borrow
- V (bit 28): Overflow

**Codegen tip**: Generate flag updates after every data processing instruction:
```python
# After ADD r0, r1, r2
result = (r1 + r2) & 0xFFFFFFFF
r0 = result
cpsr['n'] = 1 if result & 0x80000000 else 0
cpsr['z'] = 1 if result == 0 else 0
# ... carry, overflow
```

### 4.7 Basic Block Boundaries

**Rule**: Branch instructions always start and terminate their own block.

**Correct**:
```
Block 1: ... → BNE target
Block 2: target: ... (starts new block)
```

**Incorrect**:
```
Block 1: ... → BNE target → next instruction
```

### 4.8 Dispatch Table Indexing

**Formula**: `idx = (pc - 0x08000000) >> 2`

**Why**: Instructions are 4-byte aligned (ARM) or 2-byte (Thumb), but dispatch uses 4-byte slots.

**Example**:
```
PC = 0x08000000 → idx = 0
PC = 0x08000004 → idx = 1
PC = 0x08000008 → idx = 2
```

---

## 5. Runtime Module Reference

### 5.1 Core Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| `memory.py` | 791 | Memory map, read/write, MMIO dispatch |
| `arm7tdmi.py` | 849 | CPU core, instruction execution |
| `cpu.py` | 706 | ARM/Thumb instruction handlers |
| `ppu.py` | 1000+ | Graphics rendering (Modes 0-5) |
| `bios.py` | 500+ | SWI handlers (54 functions) |

### 5.2 Optional Modules

| Module | Enabled by | Purpose |
|--------|------------|---------|
| `apu.py` | `--audio` | Audio processing (4 channels) |
| `dma.py` | `--dma` | DMA controller (4 channels) |
| `timers.py` | `--timers` | Timer units (4 timers) |
| `interrupts.py` | `--irq` | IRQ handling (VBlank, HBlank, etc.) |

### 5.3 Feature Detection

**Auto-detection** (lines 42-127 in pipeline_cmd.rs):
- Scans instructions for MMIO register accesses
- Enables features based on ROM usage
- Can be overridden via CLI flags

---

## 6. Debugging Checklist

### 6.1 Visual Issues

1. **Check DISPCNT register** (0x04000000):
   - Mode bits (0-2) match expected mode
   - Background enable bits (8-13) set correctly

2. **Verify VRAM writes**:
   - Check `memory.vram` array is being written
   - Verify tile data at correct offsets

3. **Palette verification**:
   - Check `memory.palette` for color data
   - Verify palette index in tilemap

### 6.2 Execution Issues

1. **Check dispatch table**:
   - Is PC in expected range?
   - Is dispatch_table entry present?

2. **Verify CPSR flags**:
   - Are flags being updated after operations?
   - Are condition checks using correct flag values?

3. **Basic block boundaries**:
   - Are branch targets starting new blocks?
   - Are branch instructions terminating blocks?

### 6.3 Memory Issues

1. **Address mapping**:
   - Is address already absolute (0x04000000+)?
   - Is double mapping occurring?

2. **Memory region bounds**:
   - Is address within valid region?
   - Are mirrors handled correctly?

---

## 7. Quick Reference

### 7.1 Memory Map (Absolute Addresses)

```
0x00000000-0x00003FFF  BIOS (16KB)
0x02000000-0x0203FFFF  EWRAM (256KB)
0x03000000-0x03007FFF  IWRAM (32KB)
0x04000000-0x040003FF  IO (1KB)
0x05000000-0x050003FF  Palette (1KB)
0x06000000-0x06017FFF  VRAM (96KB)
0x07000000-0x070003FF  OAM (1KB)
0x08000000-0x09FFFFFF  ROM (32MB)
0x0A000000-0x0A00FFFF  SRAM (64KB)
```

### 7.2 Relative Address Mapping

```
0x00000-0x0FFFF  → MMIO (0x04000000)
0x10000-0x37FFF  → VRAM (0x06000000)
0x40000-0x403FF  → Palette (0x05000000)
0x60000-0x603FF  → OAM (0x07000000)
```

### 7.3 Key Functions

| Function | Purpose |
|----------|---------|
| `_map_address(addr)` | Convert relative → absolute |
| `read_u8/16/32(addr)` | Read from memory |
| `write_u8/16/32(addr, value)` | Write to memory |
| `_dispatch_hal_write(addr, value)` | Route MMIO writes |
| `func_map[idx]` | Dispatch to basic block |

---

**Document Version**: 1.0  
**Last Updated**: 2026-06-26  
**Maintained By**: GBAtoPy Core Team
