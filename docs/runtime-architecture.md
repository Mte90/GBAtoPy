# GBAtoPy Python Runtime Architecture

> **Target Audience**: AI agents contributing to GBAtoPy code generation
>
> **Purpose**: Document the runtime architecture to prevent common mistakes in code generation and debugging
>
> **Related**: For the five core transpilation patterns (interpreter fallback, dispatch table, hotspot tracking, differential execution, code/data separation), see [`docs/design/transpilation-patterns.md`](design/transpilation-patterns.md) — the authoritative description of the current architecture.

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
| SRAM | 0x0E000000 | 0x0E00FFFF | 64KB | Save RAM |

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
| `read_u8(addr)` | 8-bit | Yes | Calls `_map_address()` internally; NO scanline advancement |
| `read_u16(addr)` | 16-bit | Yes | Calls `_map_address()` internally; NO scanline advancement |
| `read_u32(addr)` | 32-bit | Yes | Calls `_map_address()` internally; NO scanline advancement |
| `write_u8(addr, value)` | 8-bit | Conditional | Skips mapping if already absolute; NO scanline advancement |
| `write_u16(addr, value)` | 16-bit | Yes | Calls `_map_address()` internally; NO scanline advancement |
| `write_u32(addr, value)` | 32-bit | Yes | Calls `_map_address()` internally; NO scanline advancement |

**Key Insight**: All read/write methods call `_map_address()` internally. The "conditional mapping" in `write_u8()` is a workaround for the double-mapping issue when called from `write_u16()`/`write_u32()`.

**⚠️ CRITICAL**: Memory read/write methods do NOT advance the PPU scanline. Scanline advancement is owned exclusively by the main loop (see Section 2.5). This ensures that memory accesses during HBlank/VBlank do not interfere with PPU timing.

---

## 2. PPU Scanline & DMA Architecture

### 2.1 Per-Scanline Affine Parameter Snapshots

Affine background parameters (BG2PA, BG2PB, BG2PC, BG2PD, BG2X, BG2Y) are captured into a snapshot array at the start of each scanline, BEFORE HBlank DMA fires.

**Implementation**:

- `_bg2_affine_snapshots`: Array of 160 elements (one per scanline), each storing a 6-tuple of affine parameters.
- `step_scanline(capture_snapshot=True)`: Captures current affine register values into `self._bg2_affine_snapshots[self.vcount]` before rendering.
- The main loop passes `capture_snapshot=True`; the fallback interpreter passes `False`.

**Why this matters**: HBlank DMA can update affine parameters during the HBlank period. By capturing snapshots BEFORE DMA fires, we ensure that the correct parameter set is used for rendering each scanline.

**Rendering fallback**:

- `_render_mode3/4/5` read affine parameters from `self._bg2_affine_snapshots[y]`.
- If the snapshot is `None` (e.g., when called from fallback interpreter), falls back to reading live registers.

### 2.2 Fallback Interpreter Contract

The fallback interpreter (`_interp_fallback` in `pipeline_cmd.rs`) is a PURE CPU executor with strict boundaries:

**What it DOES**:
- Executes CPU instructions (ARM/Thumb)
- Handles branch targets not in the dispatch table
- Delivers VBlank IRQ before breaking on VBlank detection

**What it does NOT DO**:
- NEVER calls `step_scanline()`
- NEVER advances PPU scanlines
- NEVER handles DMA transfers

**Why**: PPU timing is owned exclusively by the main loop. The fallback interpreter exists only to execute CPU instructions that cannot be dispatched via the generated code path.

### 2.3 Instruction-Counted Main Loop

The main loop synchronizes CPU execution with PPU timing using instruction counting:

**Algorithm**:

1. Track CPU instructions executed since last scanline advance
2. When `instr_count >= instr_per_scanline`:
   - Call `step_scanline(capture_snapshot=True)`
   - Reset instruction counter
3. Continue until VBlank IRQ or frame complete

**instr_per_scanline calculation**: `(gba_hz / 60) // 228` — approximately 613 instructions per scanline. A previous `// 2` halving caused VBlank IRQ wake failures and 7-frame timing divergence in cascade7 (hash routine ran at F2 instead of F9). The halving has been removed.

**Key properties**:

- `step_scanline()` is called ONLY from the main loop, never from memory reads or the fallback interpreter.
- PPU timing is proportional to actual CPU execution, not loop iterations.
- This ensures accurate synchronization between CPU and PPU.

### 2.4 DMA Full-Count Burst Semantics

HBlank and VBlank DMA transfers follow full-count burst-on-trigger semantics:

**Implementation**:

- `_do_transfer()`: Transfers the entire `count` in one burst (used by HBlank/VBlank/manual DMA).
- `_do_transfer_single()`: Transfers exactly ONE unit per call (unused by HBlank/VBlank path; retained for other internal uses).
- `hblank_fire()` and `vblank_fire()` call `_do_transfer()` once per trigger.

**Repeat flag behavior**:

- The Repeat flag controls count reload, NOT per-trigger transfer size.
- On each HBlank/VBlank trigger, the full `count` is transferred in one burst (~2 cycles per unit).
- If Repeat is set, the count is reloaded after the burst; otherwise, DMA is disabled.

**VBlank gating**: `step_scanline()` fires `hblank_fire()` only when `vcount < 160` (visible scanlines), matching mGBA `video.c:217`. Firing during VBlank consumes source values that belong to the next frame's visible lines, shifting per-scanline gradients (bgpd) by ~50 scanlines.

**Why this matters**: This matches mGBA's `GBADMAService` behavior. The old per-unit-per-trigger model caused bgpd's gradient to render with a ~128-scanline period instead of the correct ~52-scanline period (verified pixel-perfect, 0.0% diff).

---

## SWI Handler Architecture

### Two Dispatch Paths

The GBAtoPy runtime has **two SWI dispatch paths** that must produce identical results:

1. **Codegen `swi_handler`** (in `game_loop.py` template) — the authoritative implementation
2. **ARM7TDMI `swi_handler`** (in `arm7tdmi.py`) — fallback interpreter handler

### Invariant: Identical Register Outputs

Both handlers must produce **identical register outputs** for all SWI numbers (0x00-0x1F). Violating this invariant causes behavioral differences when functions execute via `_interp_fallback` instead of the ARM fast path (`dispatch_table_arm`).

### Known Mismatches and Fixes

| SWI | Codegen Behavior | ARM7TDMI Behavior | Fix Status |
|-----|------------------|-------------------|------------|
| 0x00 (SoftReset) | Zeroes R0 + R14 | Zeroes R0-R12, not R14 | F302 |
| 0x06 (Div) | Truncated division + sets R3=abs(sd) | Python floored `%` + doesn't set R3 | F301 |
| 0x07 (DivArm) | Sets R0, R1, R3 | Only sets R0 | F301 |
| IRQ return | Breaks inner loop on IRQ return PC | Doesn't break, may miss register restore | F303 |

### Audit Requirement

All remaining SWI handlers (0x00-0x1F) must be audited for mismatches. See WORKPLAN.md F304.

---

## Runtime Invariants

This section documents critical runtime invariants that must be preserved to ensure correct GBA emulation behavior. Violating any of these invariants introduces subtle bugs that manifest as timing errors, incorrect graphics, or silent IRQ failures.

### Invariant #1: Fallback interpreter is pure CPU executor

**Statement**: The fallback interpreter (`_interp_fallback` in `pipeline_cmd.rs`) executes CPU instructions only — NEVER calls `step_scanline()`.

**Rationale**: PPU timing is owned exclusively by the main loop. Calling `step_scanline()` from the fallback interpreter causes DMA double-stepping, where DMA transfers fire twice per scanline.

**Violation consequence**: DMA timing errors, corrupted graphics, IRQ delivery failures.

### Invariant #2: Main loop is instruction-counted

**Statement**: PPU advances one scanline per `instr_per_scanline` CPU instructions, calculated as `(gba_hz / 60) // 228`.

**Rationale**: This ensures accurate synchronization between CPU execution and PPU timing. The calculation matches the GBA's hardware behavior where 228 clock cycles occur per scanline at 60Hz refresh.

**Violation consequence**: Timing divergence, IRQ wake failures, frame timing errors (e.g., 7-frame drift in cascade7).

### Invariant #3: No step_scanline in memory reads

**Statement**: `read_u16`/`read_u32`/`read_u64` must NEVER call `step_scanline()`.

**Rationale**: Memory accesses during HBlank/VBlank must not interfere with PPU timing. Scanline advancement is owned exclusively by the main loop.

**Violation consequence**: PPU timing corruption, DMA fires at wrong scanlines, rendering artifacts.

### Invariant #4: HBlank/VBlank DMA = full-count burst on first trigger

**Statement**: `hblank_fire()` and `vblank_fire()` call `_do_transfer()`, NOT `_do_transfer_single()`.

**Rationale**: The GBA transfers the entire DMA count in one burst on each trigger. The old per-unit-per-trigger model caused bgpd's gradient to render with a ~128-scanline period instead of the correct ~52-scanline period.

**Violation consequence**: DMA timing errors, gradient shifts (~50 scanlines in bgpd), incorrect DMA behavior.

### Invariant #5: Per-scanline affine snapshots

**Statement**: `step_scanline(capture_snapshot=True)` captures BG2PA/PB/PC/PD/X/Y BEFORE DMA fires. The main loop passes `capture_snapshot=True`; the fallback interpreter passes `False`.

**Rationale**: HBlank DMA can update affine parameters during the HBlank period. By capturing snapshots BEFORE DMA fires, we ensure that the correct parameter set is used for rendering each scanline.

**Violation consequence**: Affine background rendering errors, wrong transformation matrices per scanline.

### Invariant #6: All memory regions must be zero-initialized at construction

**Statement**: `memory.py` must use `[0] * SIZE` for VRAM, Palette RAM, OAM, IWRAM, EWRAM.

**Rationale**: Debug patterns like `[(i%256) for i in range(SIZE)]` left in production cause uninitialized tiles to decode to non-zero palette indices → black screens.

**Violation consequence**: Black screens, garbage graphics from uninitialized memory.

### Invariant #7: All instruction/SWI dispatch tables must be single-source

**Statement**: There must be ONE dispatch table for SWI instructions, shared by both the fast-path and fallback interpreters.

**Rationale**: Two SWI dispatchers existed (cpu.py:_arm_swi with 4 handlers, arm7tdmi.py:swi_handler with 24). The fast-path CPU silently dropped CpuSet/CpuFastSet. Having a single source ensures all SWI handlers are available to both execution paths.

**Violation consequence**: SWI handlers missing in fast path, wrong register outputs, behavioral regressions.

### Invariant #8: PPU `forced_blank` must track DISPCNT bit 7 live

**Statement**: `ppu.py` maintains `self.forced_blank` as the authoritative field; all forced-blank checks must read `self.forced_blank`, not `self.dispcnt & 0x0080`.

**Rationale**: Code that reads `self.dispcnt & 0x0080` uses a stale cached value (initialized to 0x0480 at line 519, never updated). This caused a GLOBAL white-screen regression — every ROM rendered blank.

**Violation consequence**: Global white-screen regression, all ROMs render blank.

### Invariant #9: CFG builder must reject BL_SUFFIX addresses

**Statement**: CFG builder must reject BL_SUFFIX addresses as BFS exploration targets — they are always the second half of a 33-bit BL instruction, never function entry points.

**Rationale**: BL_SUFFIX addresses (second halfword of 32-bit Thumb BL instruction) treated as valid code entry points by BFS causes exponential CFG growth from data-as-code. Since Thumb instructions decode as valid for all 256 values of `(halfword >> 8)`, data regions explode exponentially in the CFG.

**Violation consequence**: Exponential CFG growth, transpiler OOM or timeout, thousands of unreachable `func_XXXXXX()` entries.

### Invariant #10: Cross-mode BFS guard must allow ARM override

**Statement**: Cross-mode BFS guard must allow ARM BFS to override stale Thumb classifications when an ARM prologue is found at the target address.

**Rationale**: When Thumb BFS claims an ARM address (via fall-through through data-as-code), the cross-mode guard blocks ARM BFS from correcting the classification. ARM functions then execute via `_interp_fallback` instead of `dispatch_table_arm`, causing behavioral regressions (e.g., SWI handlers drop, wrong register outputs).

**Violation consequence**: ARM functions execute via fallback interpreter, SWI handler mismatches, register output errors.

### Invariant #11: Timer stepping must be per-instruction in fallback path

**Statement**: Timer stepping in the fallback interpreter must be per-instruction (matching the fast path), not batch-stepped after the call returns.

**Rationale**: Fast path steps timers per-instruction (`step(4)`), but the fallback path batch-stepped after the call (`step(4 * steps)`). After BX fix increased fallback usage, this caused IRQ timing regressions and timer-based ROM failures.

**Violation consequence**: IRQ timing regressions, timer-based ROMs show pixel diffs or timing divergence.

### Invariant #12: IE register writes must preserve high byte

**Statement**: IE register writes must preserve the high byte — IE is a 16-bit register and partial byte writes must not clobber the other byte.

**Rationale**: Partial writes that clobber the high byte silently disable IRQs. The IE register is 16-bit, but some write paths only update the low byte and zero the high byte, causing ROMs to hang waiting for IRQs that never fire.

**Violation consequence**: IRQs silently disabled, ROM hangs waiting for IRQ that never fires.

---

## 3. Code Generation Pipeline

The transpiler uses a **3-stage pipeline**:

```
Stage 1: Disassembly
  ↓
Stage 2: Asset Extraction
  ↓
Stage 3: Python Code Generation
```

### 3.1 Stage 1: Disassembly

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

### 3.2 Stage 2: Asset Extraction

**Location**: `asset_extractor` module

**What it extracts**:
- **Palette data**: 16-bit RGB555 colors (up to 256 colors)
- **Tile data**: 4BPP/8BPP tile graphics (32 bytes per 4BPP tile, 64 bytes per 8BPP tile)
- **Tilemap data**: 16-bit tile indices with palette/priority/flip flags
- **Wave data**: Audio samples for APU Channel 3
- **Sample metadata**: (start_addr, length, format) tuples

**Output**: `Assets` struct with embedded bytearray data

### 3.3 Stage 3: Python Code Generation

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
    - Counts CPU instructions executed
    - Advances PPU by one scanline per `instr_per_scanline` instructions
    - Calls `step_scanline(capture_snapshot=True)` to capture affine parameters and render
    - Handles pygame events
    - Manages frame timing
    - Supports headless mode and screenshots

### 3.4 Basic Block Merging

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

## 4. MMIO Register Handling

### 4.1 MMIO Register Map

| Range | Purpose | Key Registers |
|-------|---------|---------------|
| 0x04000000-0x0400005F | PPU | DISPCNT, BG0CNT, BG1CNT, BG2CNT, BG3CNT |
| 0x04000060-0x040000A5 | APU | SOUNDCNT_L, SOUNDCNT_H, SOUNDCNT_X, SOUNDBIAS, SOUNDSTEP, FIFO_A/B |
| 0x040000B0-0x040000BF | DMA | DMA0SAD, DMA0DAD, DMA0CNT_L, etc. |
| 0x040000B0-0x040000CF | DMA | DMA1-3 registers |
| 0x04000100-0x0400010F | Timers | TM0CNT_L, TM0CNT_H, TM1CNT_L, etc. |
| 0x04000130-0x04000133 | Input | KEYINPUT, KEYCNT |
| 0x04000200-0x04000208 | IRQ | IE, IF, IME |

### 4.2 Dispatch Mechanism

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
    
    # Sound registers (0x04000060-0x040000A5)
    if 0x04000060 <= addr <= 0x040000A5:
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

### 4.3 Register Handlers

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

### 4.4 Register Registration

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

## 5. Common Pitfalls for AI Agents

### 5.1 Never Modify .gba ROM Files

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

### 5.2 Address Mapping Gotchas

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

### 5.3 Double Mapping Bug

**Symptoms**:
- Writes go to wrong memory regions
- VRAM writes affect OAM or Palette
- MMIO writes affect ROM data

**Fix**: `write_u8()` must check if address is already absolute:
```python
if not (0x04000000 <= addr <= 0x07FFFFFF):
    addr = self._map_address(addr)
```

### 5.4 PC-Relative LDR/STR

**Problem**: PC-relative loads use PC+8 offset (ARM) or PC+4 (Thumb):
```python
# ARM: LDR r0, [PC, #12] → reads from address (PC+8+12)
# Thumb: LDR r0, [PC, #4] → reads from address (PC+4+4)
```

**Codegen handling** (in `load_store.rs`):
- Calculate target address as `PC + offset + instruction_size`
- For ARM: `PC + 8 + offset`
- For Thumb: `PC + 4 + offset`

### 5.5 LDM/STM Parsing Limitations

**Known Issue**: LDM/STM instruction parsing is imperfect.

**Symptoms**:
- Multiple register loads/stores may not work correctly
- Writeback mode may not update base register

**Workaround**: Test with simple LDM/STM cases first. Complex cases may need manual codegen.

### 5.6 CPSR Flag Tracking

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

### 5.7 Basic Block Boundaries

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

### 5.8 Dispatch Table Indexing

**Formula**: `idx = (pc - 0x08000000) >> 2`

**Why**: Instructions are 4-byte aligned (ARM) or 2-byte (Thumb), but dispatch uses 4-byte slots.

**Example**:
```
PC = 0x08000000 → idx = 0
PC = 0x08000004 → idx = 1
PC = 0x08000008 → idx = 2
```

---

## 6. Runtime Module Reference

### 6.1 Core Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| `memory.py` | 791 | Memory map, read/write, MMIO dispatch |
| `arm7tdmi.py` | 849 | CPU core, instruction execution |
| `cpu.py` | 706 | ARM/Thumb instruction handlers |
| `ppu.py` | 2800+ | Graphics rendering (Modes 0-5) |
| `bios.py` | 500+ | SWI handlers (54 functions) |

### 6.2 Optional Modules

| Module | Enabled by | Purpose |
|--------|------------|---------|
| `apu.py` | `--audio` | Audio processing (4 channels) |
| `dma.py` | `--dma` | DMA controller (4 channels) |
| `timers.py` | `--timers` | Timer units (4 timers) |
| `interrupts.py` | `--irq` | IRQ handling (VBlank, HBlank, etc.) |

### 6.3 Feature Detection

**Auto-detection** (lines 42-127 in pipeline_cmd.rs):
- Scans instructions for MMIO register accesses
- Enables features based on ROM usage
- Can be overridden via CLI flags

---

## 7. Debugging Checklist

### 7.1 Visual Issues

1. **Check DISPCNT register** (0x04000000):
   - Mode bits (0-2) match expected mode
   - Background enable bits (8-13) set correctly

2. **Verify VRAM writes**:
   - Check `memory.vram` array is being written
   - Verify tile data at correct offsets

3. **Palette verification**:
   - Check `memory.palette` for color data
   - Verify palette index in tilemap

### 7.2 Execution Issues

1. **Check dispatch table**:
   - Is PC in expected range?
   - Is dispatch_table entry present?

2. **Verify CPSR flags**:
   - Are flags being updated after operations?
   - Are condition checks using correct flag values?

3. **Basic block boundaries**:
   - Are branch targets starting new blocks?
   - Are branch instructions terminating blocks?

### 7.3 Memory Issues

1. **Address mapping**:
   - Is address already absolute (0x04000000+)?
   - Is double mapping occurring?

2. **Memory region bounds**:
   - Is address within valid region?
   - Are mirrors handled correctly?

---

## 8. Quick Reference

### 8.1 Memory Map (Absolute Addresses)

```
0x00000000-0x00003FFF  BIOS (16KB)
0x02000000-0x0203FFFF  EWRAM (256KB)
0x03000000-0x03007FFF  IWRAM (32KB)
0x04000000-0x040003FF  IO (1KB)
0x05000000-0x050003FF  Palette (1KB)
0x06000000-0x06017FFF  VRAM (96KB)
0x07000000-0x070003FF  OAM (1KB)
0x08000000-0x09FFFFFF  ROM (32MB)
0x0E000000-0x0E00FFFF  SRAM (64KB)
```

### 8.2 Relative Address Mapping

```
0x00000-0x0FFFF  → MMIO (0x04000000)
0x10000-0x37FFF  → VRAM (0x06000000)
0x40000-0x403FF  → Palette (0x05000000)
0x60000-0x603FF  → OAM (0x07000000)
```

### 8.3 Key Functions

| Function | Purpose |
|----------|---------|
| `_map_address(addr)` | Convert relative → absolute |
| `read_u8/16/32(addr)` | Read from memory |
| `write_u8/16/32(addr, value)` | Write to memory |
| `_dispatch_hal_write(addr, value)` | Route MMIO writes |
| `func_map[idx]` | Dispatch to basic block |

---

**Document Version**: 1.1  
**Last Updated**: 2026-07-30  
**Maintained By**: GBAtoPy Core Team

**Changelog**:
- v1.1 (2026-07-30): Added Section 2 documenting PPU scanline architecture, affine parameter snapshots, fallback interpreter contract, instruction-counted main loop, and DMA single-unit semantics. Updated Section 1.4 to clarify that memory reads/writes do not advance scanlines. Renumbered subsequent sections.
