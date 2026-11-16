# Runtime Modules

Reference for the Python runtime modules in `crates/gbatopy-cli/assets/gba_runtime/`.
These modules are embedded in every transpiled `.py` file and provide the hardware
simulation layer the transpiled game code runs against.

For architecture-level coverage of the PPU, DMA, memory, and CPU instruction
execution, see:
- [hardware-reference.md](../hardware-reference.md) — CPU, display, memory map, PPU modes
- [runtime-architecture.md](../runtime-architecture.md) — PPU scanline & DMA architecture, `_map_address()`
- [apu-architecture.md](../apu-architecture.md) — APU channels, registers, mixer
- [design/interrupts.md](interrupts.md) — Interrupt controller
- [reference/bios-swi.md](../reference/bios-swi.md) — BIOS SWI handlers

This document covers the remaining modules not described above.

---

## Module Index

| Module | Lines | Purpose |
|--------|-------|---------|
| `cpu.py` | 1188 | Fast-path ARM7TDMI CPU interpreter (fallback executor) |
| `rom.py` | 122 | GBA ROM loading and header parsing |
| `input.py` | 192 | Keyboard to GBA keypad mapping |
| `timers.py` | 173 | 4-channel timer controller with prescaler and cascade |
| `serial.py` | 136 | Serial I/O (link cable, multiplayer, UART) |
| `rtc.py` | 488 | S-3511A real-time clock (3-wire serial) |
| `save_state.py` | 644 | Full emulator state serialization (JSON) |
| `assets.py` | 523 | Asset extraction (tiles, palettes, LZ77 decompression) |
| `oracle_assets.py` | 232 | Runtime-guided asset tracking via VRAM/OAM write monitoring |
| `hooks.py` | 219 | Debugging hooks (breakpoints, trace, memory watch) |

---

## cpu.py — Fast-Path CPU Interpreter

The `CPU` class is the ARM7TDMI processor simulator used by the fallback
interpreter. When the transpiled dispatch loop encounters a PC that is not in
the dispatch table (EWRAM, IWRAM, or mid-function entry), it delegates
execution to this CPU via `_interp_fallback` in the game loop template.

### Key Design Points

- **Condition codes:** A 16-entry lookup table (`_CONDITION`) maps each ARM
  condition code (EQ, NE, CS, CC, MI, PL, VS, VC, HI, LS, GE, LT, GT, LE, AL,
  NV) to a 16-element tuple indexed by a 4-bit flag key
  `(z<<3 | c<<2 | n<<1 | v)`. This avoids branching for condition evaluation.
- **Mode switching:** `_switch_mode` swaps banked registers (R13/R14,
  and R8–R12 for FIQ) when entering/leaving IRQ, SVC, FIQ, ABT, UND modes.
  System mode (0x1F) shares user-bank registers.
- **Instruction execution:** `step()` fetches the opcode at PC, checks
  `self.thumb_mode` to select 16-bit Thumb or 32-bit ARM fetch, and dispatches
  to `_execute_arm` or `_execute_thumb`. ARM handlers cover data-processing,
  load/store, multiply, block transfer, halfword transfer, and SWI.
- **SWI dispatch:** `_swi_handler` implements BIOS calls (SoftReset,
  RegisterRamReset, Halt, IntrWait, VBlankIntrWait, Div, Sqrt, ArcTan,
  CpuSet, CpuFastSet, BgAffineSet, ObjAffineSet, LZ77UnComp, etc.).
  Per runtime invariant 7, the SWI dispatch table must be single-source — the
  same table is shared by `cpu.py` and `arm7tdmi.py`.

### RegisterDump

`RegisterDump` (lines 1071-1188) is a debugging utility that snapshots CPU
register state, saves it to disk, and produces diff reports comparing two
register snapshots. Used for differential testing against mGBA.

### Relationship to arm7tdmi.py

`arm7tdmi.py` (2019 lines) is the instruction decoder/executor library — it
contains the per-opcode handlers for every ARM and Thumb instruction. `cpu.py`
is the CPU state container that calls `arm7tdmi.py` handlers via `step()`.
The transpiler's game loop template calls `_interp_fallback` which uses `cpu.py`
to execute instructions not covered by transpiled code.

---

## rom.py — ROM Loading

The `ROM` class loads a `.gba` cartridge image and parses its header.

### Header Fields

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 4 | Entry point (ARM branch instruction) |
| 0x04 | 156 | Nintendo logo (compressed) |
| 0xA0 | 12 | Game title (ASCII) |
| 0xAC | 4 | Game code |
| 0xB0 | 2 | Maker code |
| 0xB4 | 1 | ROM size code |

The ROM enforces a minimum size of 0xC0 bytes (header length). The `load` method
reads the file and populates `_data` and `_header`.

---

## input.py — Keypad Input

Maps host keyboard events to the GBA `KEYINPUT` register (0x04000130).

### GBA Key Encoding

The GBA keypad is **active-low**: 0 = pressed, 1 = released. The register uses
10 bits (bits 0-9):

| Bit | Key |
|-----|-----|
| 0 | A |
| 1 | B |
| 2 | Select |
| 3 | Start |
| 4 | Right |
| 5 | Left |
| 6 | Up |
| 7 | Down |
| 8 | R |
| 9 | L |

### Default Keyboard Mapping

| Keyboard Key | GBA Button |
|--------------|------------|
| Z | A |
| S | B |
| Enter | Start |
| Space | Select |
| Arrow keys | D-Pad |
| A | L |
| X | R |

The `Input` class manages current key state and translates pygame key events
into `KEYINPUT` register writes. The default value when no keys are pressed is
`0x3FF` (all 10 bits set = all released).

---

## timers.py — Timer Controller

The GBA has 4 timer channels (TM0CNT–TM3CNT), each with a 16-bit counter,
reload value, and control register.

### TimerChannel Properties

| Property | Bit | Description |
|----------|-----|-------------|
| `enabled` | 7 | Timer active |
| `irq_enable` | 6 | Fire IRQ on overflow |
| `cascade` | 2 | Use previous timer's overflow as clock (no prescaler) |
| `prescaler_value` | 0-1 | Clock divider: 1, 64, 256, or 1024 |

### Overflow Behavior

When a timer's 16-bit counter overflows (0xFFFF → 0x0000), it:
1. Reloads from the reload value
2. Fires an IRQ if `irq_enable` is set
3. Triggers timer-triggered DMA if a DMA channel is configured for this timer

When `set_control` transitions bit 7 from 0→1 (enable), the counter is reset
to the reload value — matching hardware behavior.

The `Timers` class manages all 4 channels and provides `step(cycles)` to advance
them. Timers are clocked by the CPU clock (16.78 MHz) divided by the prescaler.

---

## serial.py — Serial Communication

The `Serial` class implements the GBA serial I/O subsystem, used for link cable
multiplayer, UART, and general-purpose serial communication.

### Registers

| Address | Register | Purpose |
|---------|----------|---------|
| 0x04000120 | SIOMULTI0 | Multiplayer data (player 1) |
| 0x04000122 | SIOMULTI1 | Multiplayer data (player 2) |
| 0x04000124 | SIOMULTI2 | Multiplayer data (player 3) |
| 0x04000126 | SIOMULTI3 | Multiplayer data (player 4) |
| 0x04000128 | SIOCNT | Serial control |
| 0x0400012A | SIODATA8 | 8-bit data |
| 0x0400012C | RCNT | General-purpose SI/O mode (runtime treats as SIOCNT mirror) |

### Modes

The SIOCNT register (bits 12-13) selects one of four SIO modes:

- **Normal (0):** Single-byte transfers with immediate loopback (send→receive)
- **Multiplayer (1):** 4-player shared bus, `SIOMULTI0-3` hold each player's data
- **UART (2):** No specific handling
- **JOY-bus (3):** No specific handling

The `Serial` class tracks transfer state (`busy_flag`, `transfer_enabled`),
player ID, and error flags. Transfers start on SIOCNT bit 7 transition and
complete on the next `step()` call (1-frame delay, simulating shift register
timing). No external link partner is connected.

---

## rtc.py — Real-Time Clock

Implements the S-3511A RTC chip used in Pokémon Gold/Silver, Mario Artist,
and other GBA games that ship with a cart-based RTC.

### Interface

3-wire serial bus:
- **SCK** (0x04000138): Clock
- **SI** (0x04000134): Serial input (host → RTC)
- **SO** (0x04000136): Serial output (RTC → host)
- **CS** (0x0400013C): Chip select

### Registers

| Register | Address | Contents |
|----------|---------|----------|
| Status 1 | 0x00 | Control (reset, power, 24h/12h format, stop) |
| Status 2 | 0x02 | Flags (interrupt, alarm) |
| Time | 0x04 | Seconds, minutes, hours |
| Date | 0x08 | Day, month, year |

### Commands

| Command | Operation |
|---------|-----------|
| 0x6E | Read status register 1 |
| 0x6A | Read status register 2 |
| 0x66 | Read time (sec/min/hr) |
| 0x62 | Read date (day/month/yr) |
| 0x80 | Write time |
| 0x82 | Write date |
| 0xA0 | Write status register |

The `RTC` class implements the 3-wire protocol state machine, bit-banging SI/SO
on SCK edges. Time is sourced from the host system clock (`datetime.now()`).

---

## save_state.py — State Serialization

The `SaveState` class serializes and deserializes the complete emulator state to
JSON format for save states and debugging.

### Serialized Components

| Component | Method | Contents |
|-----------|--------|----------|
| CPU | `_save_cpu` | Registers R0-R15, CPSR, SPSR bank, mode, thumb_mode, cycles |
| Memory | `_save_memory` | VRAM, palette RAM, OAM, IWRAM, EWRAM, I/O, SRAM |
| PPU | `_save_ppu` | DISPCNT, BG registers, scroll, window, mosaic, blend |
| APU | `_save_apu` | Channel registers, envelope, sweep, duty, mixer state |
| DMA | `_save_dma` | 4-channel source/dest/count/control, enabled flags |
| Timers | `_save_timers` | 4-channel count/reload/control |
| Interrupts | `_save_interrupts` | IE, IF, IME, pending flags |
| Input | `_save_input` | KEYINPUT state |

### Format

JSON with a `VERSION` field (currently 1) for forward compatibility. The file
format is human-readable, allowing manual inspection and editing of saved states.

The factory function `create_save_state(cpu, memory, ppu, apu, dma, timers,
interrupts, input_state)` constructs a `SaveState` from component references.

---

## assets.py — Asset Extraction

The `AssetExtractor` class extracts graphical assets (tiles, palettes, sprites,
tilemaps) from GBA ROM data. Used at build time by the transpiler to embed
assets in the transpiled Python output.

### Asset Types

| Type | Description |
|------|-------------|
| `TILE_4BPP` | 4-bit per pixel tiles (16 colors, 32 bytes per 8x8 tile) |
| `TILE_8BPP` | 8-bit per pixel tiles (256 colors, 64 bytes per 8x8 tile) |
| `PALETTE` | 15-bit BGR color palette (16 or 256 entries) |
| `TILEMAP` | Tile indices and attributes for background maps |
| `SPRITE` | Object attribute data and tile data |
| `COMPRESSED` | LZ77 or Huffman compressed data |

### LZ77 Decompression

`decompress_lz77` handles GBA LZ77 format (method 0x10):
- Byte 0: 0x10 (method identifier)
- Bytes 1-3: 24-bit decompressed size (little-endian)
- Flag byte + back-references follow

The decompressor uses a sliding window with 4-bit length encoding (3-18 bytes)
and 12-bit offset. Each 16-bit back-reference packs the offset in the top
12 bits and the length in the bottom 4 bits.

### Relationship to Oracle Assets

`assets.py` performs **static** extraction (scanning ROM data at known
offsets). `oracle_assets.py` performs **dynamic** extraction (monitoring what
the game actually writes to VRAM during execution). The oracle approach is more
accurate but requires a runtime pass; static extraction is used when the oracle
is unavailable.

---

## oracle_assets.py — Oracle-Guided Asset Tracking

The `OracleAssetTracker` class monitors VRAM/OAM writes during execution to
discover which addresses the game actually uses for tiles, palettes, and
tilemaps. This provides runtime-validated asset boundaries that static ROM
scanning cannot determine.

### Tracked Regions

The tracker classifies VRAM writes by offset:

| VRAM Offset Range | Classification | Storage |
|-------------------|----------------|--------|
| 0x0000-0x7FFF | Tile data (char base) | `vram_tile_writes` |
| 0x8000-0xFFFF | Tilemap data (screen base) | `vram_tilemap_writes` |
| 0x10000+ | Framebuffer (bitmap modes) | `vram_tile_writes` |

Palette RAM writes (0x05000000-0x050003FF) are tracked via
`track_palette_write`. OAM writes (0x07000000-0x070003FF) are tracked via
`track_oam_write`, which parses sprite attributes (x, y, tile index) from each
8-byte OAM entry.

After execution, the collected writes are exported as asset definitions for
the transpiler.

---

## hooks.py — Debugging Hooks

The `HookManager` class provides zero-overhead debugging instrumentation for
the runtime. When no hooks are registered, all check methods return immediately
via the `_has_any_hooks` fast-path flag.

### Hook Types

| Hook | Trigger | Callback |
|------|---------|----------|
| Instruction | PC matches address | `callback(pc: int)` |
| Write | Memory write to address | `callback(addr: int, value: int)` |
| Read | Memory read from address | `callback(addr: int) → int` |
| Frame | End of video frame | `callback(frame_num: int)` |
| Breakpoint | PC matches address | Halts execution |

### API

- `on_instruction(addr, callback)` — trace a specific PC
- `on_write(addr, callback)` — watch memory writes
- `on_read(addr, callback)` — intercept memory reads (return value overrides)
- `on_frame(callback)` — per-frame notification
- `add_breakpoint(addr)` / `remove_breakpoint(addr)` — set/clear breakpoints
- `enable_step_mode(enabled)` — single-step execution
- `check_hooks(pc, event_type)` — called per instruction by the dispatch loop
- `check_write_hook(addr, value)` — called on memory writes
- `check_read_hook(addr)` — called on memory reads
- `clear_all()` — remove all hooks and breakpoints

The `has_hooks()` method returns `True` when any hooks are registered, allowing
the dispatch loop to skip hook checks entirely when debugging is inactive.
