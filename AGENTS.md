# AGENTS.md — GBAtoPy Project Rules

> **Read this BEFORE making any changes.** Violating these rules wastes entire sessions.

## What Is This Project

GBAtoPy is a **transpiler** that converts GBA ROMs into standalone Python files playable with pygame.

**NOT an emulator.** The output is human-readable Python source code that, when executed, reproduces the game's behavior. The goal is a `.py` file you can open, read, and modify.

For detailed implementation status, see `docs/roadmap.md` and `docs/reference/test-roms.md`.

## File Locations

```
Project root:        /home/archimede/Desktop/projects/GBAtoPy
Rust crates:         crates/
CLI:                 crates/gbatopy-cli/src/
Pipeline (active):   crates/gbatopy-cli/src/pipeline_cmd.rs (called from main.rs; cmds/pipeline.rs is a smaller helper)
Codegen tree:        crates/gbatopy-cli/src/codegen/
                       instruction_codegen/{branch,coprocessor,data_processing,load_store,mod}.rs (ARM)
                       thumb/{branch,conditionals,data_processing,load_store,misc,multiply,mod}.rs
                       ppu/{mod,mode1}.rs        (codegen-side PPU stubs; real PPU is runtime-side)
                       sram/{helpers,mod,sram}.rs
                       helpers.rs, memory.rs, mod.rs, ir_ops.rs (empty — IR layer not wired into emit path)
Templates:           crates/gbatopy-cli/assets/templates/
Runtime source:      crates/gbatopy-cli/assets/gba_runtime/   (real PPU/DMA/Memory live here)
                       ppu.py      — PPU renderer (Mode 0-5, per-scanline affine snapshots)
                       dma.py      — DMA controller (HBlank/VBlank = one unit per trigger)
                       memory.py   — Memory map + MMIO dispatch (no step_scanline in reads)
                       arm7tdmi.py — ARM7TDMI CPU core
Current work log:    todo.md (migration knowledge transfer — read before resuming debug)
mGBA:                mgba/ (with custom patches)
mGBA binary:         mgba/build/sdl/mgba
Scripts:             scripts/ — see scripts/README.md
Test framework:      crates/gbatopy-test/
Test config:         test-roms-config.toml (66 ROM entries)
Test ROMs:           test_roms/roms/ (66 ROMs)
Test reports:        test-reports/
Test ROM Reference:  docs/reference/test-roms.md
Roadmap:             docs/roadmap.md
Runtime Architecture: docs/runtime-architecture.md (CRITICAL — includes PPU scanline & DMA architecture)
Memory Mapping:       docs/runtime-architecture.md (Address Mapping: _map_address())
Codegen Pitfalls:    docs/codegen-pitfalls.md (13 documented bug classes)
How to debug a GBA rom: docs/how-debug.md (codegen + runtime bug classes)
Transpiler Output:   /tmp/<romname>.py (generated Python files go to /tmp/, not in project dir)
```

## Build & Test Commands

### ⚠️ CRITICAL: Understanding Test Levels

| Test Level | Command | What It Verifies | What It Does NOT Verify |
|------------|---------|------------------|-------------------------|
| **Syntax Only** | `./scripts/run-all-tests.sh` | ✅ Python compiles | ❌ Graphics, ❌ Audio, ❌ Execution |
| **Execution** | `python3 stripes.py --headless --frame=60` | ✅ Script runs | ❌ Correct graphics/audio |
| **Visual** | `compare_screenshots.py` | ✅ Pixel-perfect match with mGBA | Requires manual golden screenshot |

**Key Rule:** `run-all-tests.sh` only checks Python syntax. For full graphics/audio verification, use `compare_screenshots.py`.

### Quick Reference Commands

```bash
# 1. Build the transpiler
cargo build --release

# 2. Transpile a single ROM
cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py

# 3. SMOKE TEST (syntax only)
./scripts/run-all-tests.sh

# 4. FULL VERIFICATION
# Step A: Generate golden screenshot with mGBA
./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua test_roms/roms/stripes.gba

# Step B: Generate transpiled screenshot
cd /tmp && python3 stripes.py --headless --frame=60 --screenshot /tmp/stripes_transpiled.png

# Step C: Compare (PASS if <30% difference)
python3 scripts/verify/compare_screenshots.py -s /tmp/stripes.png /tmp/stripes_transpiled.png --threshold 30
```

## GBA Hardware Reference

**GBATEK — Authoritative Reference**
- 📚 **[GBATEK GBA Documentation](https://github.com/mgba-emu/gbatek/blob/gh-pages/gba.md)** — The definitive hardware reference for all GBA specifications

### ⚠️ CRITICAL: mGBA as Reference Implementation

**If mGBA renders something correctly, GBAtoPy MUST render the same thing.**

This is a **transpiler**, not an emulator with approximate behavior. The generated Python must produce **pixel-perfect** output matching mGBA.

**Rules:**
1. **Never blame the ROM** — If mGBA shows graphics, the ROM is valid and the transpiler has a bug
2. **Test ROMs may use unconventional patterns** — STRH with post-increment, non-standard tilemap strides, partial tile writes — the runtime must handle ALL valid GBA code
3. **mGBA screenshots are gold standard** — Use `compare_screenshots.py` to verify output, not "does it run without crashing"
4. **Edge cases are not excuses** — If a ROM writes tilemap entries with 4-byte stride instead of 2, the renderer must still read them correctly

**CPU:**
- ARM7TDMI (ARMv4T)
- ARM mode: 32-bit instructions, ~160 unique opcodes
- Thumb mode: 16-bit instructions, ~60 unique opcodes

**Display:**
- 240×160 pixels, 60 fps
- Background modes: 0-5 (text, affine, bitmap)

**PPU Rendering Modes:**
- Mode 0: 4BPP text tiles — VERIFIED (shades, hello, helloWorld, hello_world)
- Mode 1: affine BG2 + text BG0/1 — implemented, not verified
- Mode 2: affine BG2/3 — VERIFIED (mode2)
- Mode 3: 16-bit bitmap — VERIFIED (stripes, mode3, bgx)
- Mode 4: 8BPP bitmap — VERIFIED (mode4)
- Mode 5: 160x128 bitmap — implemented, not verified
- Windows, blend, mosaic: register stubs only (not functional)

**Memory Map (MEMORIZE):**
- 0x08000000-0x09FFFFFF: Game Pak ROM (up to 32MB)
- 0x06000000-0x06017FFF: VRAM (96KB)
- 0x05000000-0x050003FF: Palette RAM
- 0x07000000-0x070003FF: OAM (1KB)
- 0x04000000-0x040003FF: MMIO registers
- 0x03000000-0x03007FFF: IWRAM (32KB)
- 0x02000000-0x0203FFFF: EWRAM (256KB)
- 0x00000000-0x00003FFF: BIOS ROM

**Address Mapping Constraint:**
- MUST handle both absolute addresses (e.g., `0x06000000`) and relative addresses correctly
- Memory regions include mirrors and aliases — verify correct mapping for all accesses

## Memory Map (MEMORIZE)

```
0x00000000-0x00003FFF  BIOS ROM
0x02000000-0x0203FFFF  EWRAM (256KB)
0x03000000-0x03007FFF  IWRAM (32KB)
0x04000000-0x040003FF  MMIO registers
0x05000000-0x050003FF  Palette RAM
0x06000000-0x06017FFF  VRAM (96KB)
0x07000000-0x070003FF  OAM (1KB)
0x08000000-0x09FFFFFF  Game Pak ROM (up to 32MB)
```

## Transpiler Output Requirements

The generated `.py` file must be:
1. **Standalone** — zero external imports except `pygame` (and `numpy` if needed)
2. **Readable** — human can open and understand the code
3. **Modifiable** — user can change colors, speeds, assets
4. **Playable** — correct graphics, input, timing

## Scope Boundaries

### IN scope
- Static ROMs with 4BPP and 8BPP backgrounds and objects
- Linear memory mapping with mirrors
- Mode 0, 2, 3, 4 rendering verified; Mode 1, 5 implemented but not verified
- Windows, blends, mosaic = register stubs only (not functional)
- CPSR flag tracking and conditional execution
- IRQ system, DMA, Timers, Keypad, Sprites, BIOS SWI
- APU audio channels with pygame.mixer output
- Standalone Python output

### ⚠️ MANDATORY IMPLEMENTATION CONSTRAINTS

**Address Mapping:**
- MUST handle both absolute addresses (e.g., `0x06000000`) and relative addresses correctly
- Memory regions include mirrors and aliases — verify correct mapping for all accesses

**Hardware Support (100% Coverage Required):**
- All ARM/Thumb instructions (100% opcode coverage)
- PPU Mode 0 (4BPP text tiles), Mode 3 (16-bit bitmap), Mode 4 (8BPP bitmap)
- Memory regions: VRAM, Palette RAM, OAM, MMIO registers
- Memory mapping with relative address handling

## Rules for Every Session

1. **Read `docs/roadmap.md` first** — it has the full status and strategy
2. **Read `docs/how-debug.md`** — systematic debug workflow for GBA ROMs
3. **Always respond in English** — even if the user writes in other languages (Italian, etc.)
4. **Test with pixels** — "no crash" is not enough. Verify screenshot content against mGBA golden.
5. **One thing at a time** — CPU core → PPU → MMIO hooks → visual validation → coverage
6. **Generated Python must run** — if it doesn't execute, the transpiler is broken
7. **Never modify .gba ROM files** — Patch Python output first, then fix Rust codegen permanently
8. **No type error suppression** — never `as any`, `@ts-ignore`, or equivalent
9. **Verify subagent claims** — always check their work manually
10. **Naming convention** — Transpiled output uses ROM base name (e.g., `stripes.gba` → `stripes.py`)
11. **Debug workflow** — Modify generated Python first to verify fix, then apply to Rust
12. **Check dispatch table completeness** — NOP block bug may skip initialization code
13. **Verify STRH/LDRH offsets** — Disassembler may use wrong bit field (bits 7-3 vs bits 3-0)
14. **Never run the test suite on all ROMs** — `run_tests.py` without `--rom`/`--filter` runs all 66 ROMs and takes too long. Always test **one ROM at a time** with `--rom <name>` (e.g., `python3 scripts/run_tests.py --level 3 --rom stripes`). The goal is to make each individual ROM work first; running the full suite is only useful as a final regression check and wastes time during active debugging. If a ROM fails, iterate on that single ROM until it passes before moving to the next one.
15. **Transpiled Python output (.py files generated from ROMs) must NEVER be written inside the project directory. Always write transpiled output to /tmp/ (e.g., /tmp/<romname>.py). The project directory holds only source code, templates, scripts, and docs — never transpiled ROM artifacts.**
16. **Doc-sync rule** — Any codegen or runtime fix that changes a ROM's pass/fail status MUST update `docs/reference/test-roms.md` in the same task (same commit, same session step). Do not leave the status table stale. The summary counts, per-ROM rows, feature matrix, and compatibility matrix must all reflect the new state.
17. **Check known bug classes before deep debugging** — Before spending time tracing a hang/spin, consult both the "Known Codegen Bug Classes" (5 classes: dispatch routing, dropped condition codes, missing PC-relative offset, wrong Thumb bit-field mask, banked register on MSR) AND the "Known Runtime Bug Classes" (2 classes: DMA double-stepping, fast-forward DISPSTAT reads) in `docs/how-debug.md`. Run `python3 -m pytest crates/gbatopy-cli/assets/gba_runtime/tests/test_dispatch_audit.py` first.
18. **Use built-in debug flags, not ad-hoc injectors** — The generated runtime supports `--pc-trace=FILE`, `--trace-n=N`, `--max-instrs=N` (default 1M; use `--max-instrs=10000000` for ROMs with tight IWRAM poll loops like bgpd). Do not inject `print(f"PC={...}")` into the generated Python or write a one-off CPU stepper. See `docs/how-debug.md` § "Systematic Spin Diagnosis Workflow".
19. **One-shot ROM verification** — Use `./scripts/verify/verify_rom.sh <rom> --no-golden` to transpile, run, and compare against a golden screenshot in one step. Do not run the 4-5 manual steps (transpile, mGBA golden, run transpiled, compare) separately unless debugging a specific step.
20. **Debug probes must flush** — If you inject a probe into generated Python, use `print(..., flush=True)` and place it BEFORE any `os._exit(0)` call. The runtime exits hard, bypassing buffer flush.
21. **Never add step_scanline to memory reads** — The fast-forward DISPSTAT read path was removed because it caused DMA exhaustion. PPU stepping is exclusively in the main loop. See `docs/codegen-pitfalls.md` entry 12.
22. **Fallback interpreter is pure CPU** — `_interp_fallback` in `pipeline_cmd.rs` must NEVER call `step_scanline()`. It only executes CPU instructions and delivers VBlank IRQ. The main loop owns all PPU timing.
23. **Parallelize with subagents** — When work has 2+ independent parts, dispatch them as parallel subagents in one message instead of serializing. Independent investigation lanes (e.g., reading 3 unrelated ROM sources, exploring codegen + runtime + docs simultaneously, researching multiple failing ROMs) MUST run concurrently. Use `@explorer` for codebase recon, `@librarian` for external docs/research, `@oracle` for architecture/risk analysis, `@fixer` for bounded implementation, `@designer` for UI/UX. Track each task ID, keep working on non-overlapping lanes while they run, and reconcile results when they return. Never serialize work that can run in parallel — it wastes wall-clock time. Exception: a single trivial one-file edit (<20 lines) is faster done directly.

## Runtime Invariants (DO NOT VIOLATE)

These invariants were established after multi-session debugging. Violating them reintroduces solved bugs.

1. **Fallback interpreter = pure CPU executor.** `_interp_fallback` in `pipeline_cmd.rs` executes CPU instructions only. It must NEVER call `step_scanline()`. Violating this causes DMA double-stepping (HBlank fires twice per scanline, exhausting source tables).
2. **Main loop is instruction-counted.** The PPU advances one scanline per `instr_per_scanline` CPU instructions. This ties PPU timing to actual execution, not loop iterations.
3. **No step_scanline in memory reads.** `read_u16`/`read_u32`/`read_u64` must NEVER call `step_scanline()`. The removed fast-forward DISPSTAT path caused tight IWRAM poll loops to fire HBlank DMA hundreds of times per scanline.
4. **HBlank/VBlank DMA = full-count burst on first trigger.** `hblank_fire()` and `vblank_fire()` call `_do_transfer()` (full count burst), NOT `_do_transfer_single()` (one unit). mGBA's `GBADMAService` completes all pending transfers when the HBlank/VBlank event fires — the entire `count` is transferred in one burst (~2 cycles per unit), then the channel disables itself for non-Repeat DMA. The old one-unit-per-trigger behavior caused bgpd's gradient to render with a 32-row period instead of the correct ~50-row period.
5. **Per-scanline affine snapshots.** `step_scanline(capture_snapshot=True)` captures BG2PA/PB/PC/PD/X/Y into `_bg2_affine_snapshots[vcount]` BEFORE DMA fires. `_render_mode3/4/5` read from snapshots, falling back to live read if None. The fallback interpreter calls `step_scanline(capture_snapshot=False)`.

See `docs/runtime-architecture.md` § "PPU Scanline & DMA Architecture" for details.

## Migration Strategy

When moving this project to another machine:
1. **Read `todo.md` first** — it has the current debug state, architecture changes, and knowledge not in code comments.
2. **Read `docs/runtime-architecture.md` § "PPU Scanline & DMA Architecture"** — the 5 runtime invariants above are documented there in full.
3. **Read `docs/how-debug.md` "Known Runtime Bug Classes"** — documents the DMA double-stepping and fast-forward DISPSTAT bugs that took multiple sessions to diagnose.
4. **Build verification:** `cargo build --release` (must be 0 errors, 0 warnings).
5. **Transpile + verify one ROM:** `cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py && python3 /tmp/stripes.py --headless --frame=60 --screenshot /tmp/stripes.png`
6. **Test ROMs are NOT in the repo** — run `scripts/setup/download_test_roms.sh` to fetch them.
7. **mGBA must be built** — see README.md for cloning and building the mGBA fork (branch: extend-lua).

## Zero Tolerance for Stubs

**Scope:** This rule applies to **generated Python output** (the transpiler's product) and the **runtime templates** in `crates/gbatopy-cli/assets/gba_runtime/` and `crates/gbatopy-cli/assets/templates/`. Rust codegen stubs (e.g. `ppu/mode1.rs`) are tracked separately as codegen-incomplete markers, not runtime stubs — they do not leak into the generated Python.

These ALL count as unimplemented in generated Python:
- `pass`
- `return 0`
- `return None`
- `NotImplementedError`
- `TODO:` comments
- Empty function bodies
- Functions that only contain `print()` debug statements
