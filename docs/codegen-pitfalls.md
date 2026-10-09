# Codegen Pitfalls

Catalogue of codegen bugs fixed across sessions.

> **Before debugging any codegen bug in this list, run the Ghidra oracle to get ground truth:** `scripts/ghidra/ghidra_functions.sh <rom>` for function discovery, `scripts/ghidra/ghidra_decode.sh <rom> <addr>` for instruction decode verification. See AGENTS.md "Ghidra Static Analysis Oracle" section.

## 1. STRH Immediate Offset (Disassembler)

**Symptom:** Half-word stores (STRH) used offset 22 instead of 0.
**Root cause:** Disassembler combined bits 11-8 and 7-3 as (imm4h << 5) | imm5 = 22. Correct formula for half-words is (imm4h << 4) | imm4l.
**Fix:** Changed offset calculation in disassembler.
**File:** disasm module.

## 2. NOP Detection Too Aggressive (Pipeline)

**Symptom:** Codegen marked several blocks as NOP, causing missing functions in the dispatch table (addresses 0xF8-0x104).
**Root cause:** NOP heuristic in pipeline_cmd.rs was overly aggressive, skipping initialization code.
**Fix:** Relaxed the NOP heuristic.
**File:** crates/gbatopy-cli/src/pipeline_cmd.rs

## 3. PPU Default Mode Hard-coded (PPU)

**Symptom:** PPU initialized self.mode = 3 instead of reading DISPCNT.
**Root cause:** PPU initialization routine hard-coded mode 3.
**Fix:** Read DISPCNT register for mode.
**File:** ppu.py (runtime)

## 4. Character Block Base as Number Not Address (PPU)

**Symptom:** self.bg_char_block[bg] stored block number (0-3) instead of VRAM base address (e.g. 0x06004000), causing all tile reads to point at wrong memory.
**Fix:** Map block number to VRAM address before use.
**File:** ppu.py (runtime)

## 5. 4 BPP Nibble Order Reversed + Double-Scale (PPU)

**Symptom:** Only 160 non-black pixels rendered.
**Root cause:** _decode_tile_4bpp multiplied char_block_base by 0x4000 (double-scale) and interpreted 4BPP nibble order reversed (upper nibble used for left pixel).
**Fix:** Removed extra multiplication and swapped nibble extraction.
**File:** ppu.py (runtime)

## 6. Mode 4 Palette Fallback (PPU)

**Symptom:** hello.gba produced 38400 pixels with many colors instead of expected ~209 white pixels.
**Root cause:** Palette fallback routine treated zero palette entry as grayscale intensity instead of black.
**Fix:** Removed fallback; undefined entries return black.
**File:** ppu.py (runtime)

## 7. Block Transfer Write-back Ignored (CPU)

**Symptom:** STMFD/LDMFD never updated stack pointer, corrupting stack and leading to 0x04040404 PC values.
**Root cause:** exec_block_transfer ignored W (write-back) and P (pre/post-index) bits.
**Fix:** Implemented proper write-back handling.
**File:** load_store.rs (codegen) / cpu.py (runtime)

## 8. SP Initialized to 0 (Runtime Header)

**Symptom:** Pushes wrote into MMIO space.
**Root cause:** Generated runtime initialized SP (R13) to 0 instead of GBA default 0x03007F00.
**Fix:** Set SP to 0x03007F00 in header template.
**File:** crates/gbatopy-cli/assets/templates/ (header)

## 9. writes_r15() Only Checked Branches (Codegen)

**Symptom:** LDM ... {PC} returned to incorrect address because codegen appended fall-through registers[15]=... after load, overwriting proper return PC.
**Root cause:** writes_r15() only checked branch opcodes, neglecting PC-writes via LDM, LDR, or data-processing instructions.
**Fix:** Expanded writes_r15() to detect all instructions that modify R15.
**File:** crates/gbatopy-cli/src/pipeline_cmd.rs

## 10. BL Did Not Set LR (Codegen)

**Symptom:** Functions that saved LR and later performed LDMFD ... {PC} loaded garbage, causing PC jumps to 0x04040404.
**Root cause:** BL code generation emitted same code as plain B, setting only PC and never writing return address to LR (R14).
**Fix:** Added registers[14]=registers[15]+4 assignment before PC update for BL.
**File:** crates/gbatopy-cli/src/codegen/instruction_codegen/branch.rs

## 11. DMA Double-Stepping (Fallback Interpreter + Main Loop)

**Symptom:** DMA transfers fire twice per scanline, exhausting the DMA source table by scanline ~94. In bgpd.gba, BG2PD plateaus at 159, producing a vertically stretched gradient.
**Root cause:** Both the fallback interpreter (_interp_fallback) and the main execution loop called step_scanline(). Each scanline advanced the PPU twice, firing HBlank DMA twice per scanline.
**Fix:** Fallback interpreter is now a pure CPU executor (no step_scanline()). Main loop is instruction-counted: advances PPU one scanline per instr_per_scanline CPU instructions. **HBlank/VBlank DMA uses full-count burst on first trigger via `_do_transfer()`** (not one-unit-per-trigger via `_do_transfer_single()`). The old one-unit-per-trigger behavior caused bgpd's gradient to render with a 32-row period instead of the correct ~50-row period. See AGENTS.md runtime invariant #4.
**Files:** crates/gbatopy-cli/assets/gba_runtime/dma.py, crates/gbatopy-cli/src/pipeline_cmd.rs

## 12. Fast-Forward DISPSTAT Read (Memory Read Methods)

**Symptom:** Tight IWRAM poll loops reading DISPSTAT caused premature DMA source table exhaustion. In bgpd.gba, each DISPSTAT read called step_scanline() up to 228 times.
**Root cause:** read_u16 and read_u32 in memory.py had a fast-forward path calling self._ppu.step_scanline() during DISPSTAT/VCount reads.
**Fix:** Removed the fast-forward DISPSTAT reads from memory.py. Removed _last_vcount_read and _last_dispstat_read attributes. PPU stepping is exclusively in the main loop.
**File:** crates/gbatopy-cli/assets/gba_runtime/memory.py

## 13. Thumb BL Prefix/Suffix Split (Codegen + CFG)

**Symptom:** Spurious dispatch entries at BL_ADDR+2 caused garbage jumps and unwanted EWRAM writes in cascade7. BL instructions were split into BL_PREFIX and BL_SUFFIX dispatch entries, and the code generator wrote the full target address to LR instead of the upper bits.
**Root cause:** The decoder stored the full target in the BL_PREFIX operand; the code generator emitted separate prefix/suffix steps that computed wrong branch targets. The CFG BFS advanced by 2 bytes for BL_PREFIX, creating a mid-instruction fall-through.
**Fix:** (1) Decoder now stores only the upper bits of the target in BL_PREFIX operand. (2) Code generator merges prefix/suffix into a single 4-byte emission: `LR = (PC + 3) | 1`, `PC = target & ~1`. (3) CFG BFS advances by 4 bytes for BL_PREFIX, eliminating mid-instruction fall-throughs.
**Files:** crates/gbatopy-disasm/src/thumb/mod.rs, crates/gbatopy-cli/src/codegen/instruction_codegen/branch.rs, crates/gbatopy-disasm/src/cfg.rs

## 14. Thumb disassembler/codegen operand mismatch (F270)

**Symptom:** Thumb load/store instructions silently stubbed as `pass` — 3933 stubs in cascade7, 5118 in fantasy-knight.
**Root cause:** Thumb disassembler emits flat operands `[Register, Immediate]` for load/store instructions, but codegen's `load_store.rs:74-81` only matches `Operand::MemoryAddress`.
**Fix:** Convert Thumb disassembler formats 6-11 to emit `Operand::MemoryAddress` matching ARM pattern. Committed: cascade7 stubs reduced 3933→508.
**Files:** crates/gbatopy-disasm/src/thumb/mod.rs

## 15. SWI number extraction shift bug (F289)

**Symptom:** Every Thumb SWI routed to SoftReset handler (0x0), breaking CpuSet, CpuFastSet, VBlankIntrWait, Diff8bitUnFilter across every ROM.
**Root cause:** `coprocessor.rs:62` extracts SWI number with `(*n >> 16) & 0xFF`. Both disassemblers already extract the SWI number (ARM: `word & 0xFFFFFF`, Thumb: `hw & 0xFF`). For SWI 0x16 (SoftReset): `(0x16 >> 16) & 0xFF = 0`.
**Fix:** `*n & 0xFF` (one line). Committed at e1cf1da.
**Files:** crates/gbatopy-disasm/src/coprocessor.rs

## 16. Thumb PUSH/POP codegen gap (F287)

**Symptom:** 335 stubs in cascade7 ROM (67.1% of remaining stubs).
**Root cause:** Thumb PUSH/POP opcodes have no codegen handler at all. Codegen LDM/STM handler at `load_store.rs:577-689` requires `Operand::MemoryAddress` with `AddressingMode::Multi`, but Thumb disassembler emits flat register lists.
**Status:** NOT YET FIXED.
**Files:** crates/gbatopy-disasm/src/thumb/mod.rs, crates/gbatopy-cli/src/codegen/instruction_codegen/load_store.rs

## 17. Thumb LDMIA/STMIA codegen gap (F288)

**Symptom:** 111 stubs in cascade7 ROM (22.2% of remaining stubs).
**Root cause:** Thumb LDMIA/STMIA opcodes match codegen's `starts_with("LDM") || starts_with("STM")` pattern, but Thumb disassembler emits `ops[0]` as `Register`, codegen expects `MemoryAddress`.
**Status:** NOT YET FIXED.
**Files:** crates/gbatopy-disasm/src/thumb/mod.rs, crates/gbatopy-cli/src/codegen/instruction_codegen/load_store.rs

## 18. Per-Scanline Affine Parameter Snapshots (PPU)

**Symptom:** Affine background rendering in Mode 3/4/5 used stale affine parameters — HBlank DMA updates to BG2PD were not reflected per-scanline.
**Root cause:** _render_mode3/4/5 read affine parameters directly from live registers once per frame, ignoring per-scanline HBlank DMA updates.
**Fix:** step_scanline() captures BG2PA/PB/PC/PD/X/Y into _bg2_affine_snapshots[vcount] before DMA fires. _render_mode3/4/5 read from snapshots, falling back to live read if snapshot is None. step_scanline() takes a capture_snapshot=True flag (main loop=True, fallback=False).
**Files:** crates/gbatopy-cli/assets/gba_runtime/ppu.py

## 19. SWI Handler Mismatch Between Codegen and Fallback Interpreter

**Symptom:** ROMs that use Div/DivArm for audio/timing calculations show pixel diffs when functions switch from ARM fast path to `_interp_fallback`. Behavioral differences between codegen `swi_handler` (game_loop.py template) and ARM7TDMI `swi_handler` (arm7tdmi.py).

**Root cause:** Two SWI dispatch paths exist with different implementations:
- **SWI Div (0x06):** codegen uses truncated division + sets R3=abs(sd); ARM7TDMI uses Python floored `%` + doesn't set R3
- **SWI DivArm (0x07):** codegen sets R0, R1, R3; ARM7TDMI only sets R0
- **SWI SoftReset (0x00):** codegen zeroes R0+R14; ARM7TDMI zeroes R0-R12, not R14
- **IRQ return register restoration:** `_interp_fallback` correctly breaks on IRQ return PC; ARM fast path doesn't, potentially missing register restore window

**Detection:** Compare `swi_handler` in `game_loop.py` template vs `arm7tdmi.py` runtime — any SWI with different register outputs is a bug.

**Fix:** ARM7TDMI `swi_handler` must match codegen `swi_handler` output for all registers (R0-R3, R12, R14). The codegen path is the authoritative implementation.

**Status:** Documentation added. Fixes pending in WORKPLAN.md F301-F304.

**Files:** crates/gbatopy-cli/assets/gba_runtime/arm7tdmi.py, crates/gbatopy-cli/assets/gba_runtime/game_loop.py (template)

## 20. BL/BL_SUFFIX CFG Over-Discovery from Data-as-Code

**Symptom:** Exponential CFG explosion from data regions decoded as Thumb code; spurious function entries at BL_SUFFIX addresses (0x08019ABC+2) causing garbage branches.

**Root cause:** BL/BL_SUFFIX targets bypass prologue validation that BX/BLX targets receive. The 24-bit offset in BL can point to arbitrary data, and since Thumb instructions decode as valid for all 256 byte values, data regions are explored as code.

**Fix:** Reject BL_SUFFIX targets in BFS exploration — they are always the second half of a 32-bit BL instruction, never function entry points. BL targets must undergo the same prologue validation as BX/BLX.

**Status:** Documented. Fix pending in WORKPLAN.md F311.

**Files:** crates/gbatopy-disasm/src/cfg.rs

## 21. Cross-Mode BFS Guard Blocking ARM Function Discovery

**Symptom:** ARM functions unreachable when Thumb BFS claims their address via fall-through through data-as-code.

**Root cause:** Cross-mode guard at cfg.rs:~1790 blocks ARM BFS from overriding stale Thumb classifications. Once Thumb BFS claims an address, ARM BFS cannot correct it.

**Fix:** Allow ARM BFS to override stale Thumb classifications when the address decodes as valid ARM instruction.

**Status:** Documented. Fix pending in WORKPLAN.md F312.

**Files:** crates/gbatopy-disasm/src/cfg.rs

## 22. Stale Register Tracker → BX Rn Data Explosion

**Symptom:** Exponential CFG growth from data regions when BX Rn targets are followed without validating register tracker state.

**Root cause:** Register tracker holds stale values after mode switches or data-as-code regions. BX Rn uses stale register value as branch target, exploring data as code.

**Fix:** Invalidate/clean register tracker before following BX Rn targets; validate target address against known code boundaries.

**Status:** Documented. Fix pending in WORKPLAN.md F317.

**Files:** crates/gbatopy-disasm/src/cfg.rs

## 23. BL-Suffix Addresses Treated as Code Entry Points

**Symptom:** Second half of 32-bit BL instruction (address+2) explored as separate function entry, creating mid-instruction basic blocks.

**Root cause:** CFG BFS advances by 2 bytes for BL_PREFIX, then treats BL_SUFFIX target as valid entry point. Thumb disassembler accepts all 256 byte values as valid opcodes.

**Fix:** Merge BL_PREFIX/BL_SUFFIX into single 4-byte instruction in CFG; reject BL_SUFFIX targets as function entries.

**Status:** Partially addressed in F270 (Thumb BL fix), but BL prologue validation gap remains.

**Files:** crates/gbatopy-disasm/src/cfg.rs, crates/gbatopy-cli/src/codegen/instruction_codegen/branch.rs

## 24. Prologue Scan Limit Too Low (PROLOGUE_MAX_TARGETS=20)

**Symptom:** Late-discovered functions in init sequences dropped when they are the 21st+ prologue target.

**Root cause:** PROLOGUE_MAX_TARGETS=20 silently ignores subsequent prologue targets. ROMs with large initialization sequences lose functions.

**Fix:** Increase PROLOGUE_MAX_TARGETS from 20 to 1000.

**Status:** DONE — fixed in recent session.

**Files:** crates/gbatopy-disasm/src/cfg.rs
