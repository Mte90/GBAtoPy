# Codegen Pitfalls

Catalogue of codegen bugs fixed across sessions.

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

## 13. Per-Scanline Affine Parameter Snapshots (PPU)

**Symptom:** Affine background rendering in Mode 3/4/5 used stale affine parameters — HBlank DMA updates to BG2PD were not reflected per-scanline.
**Root cause:** _render_mode3/4/5 read affine parameters directly from live registers once per frame, ignoring per-scanline HBlank DMA updates.
**Fix:** step_scanline() captures BG2PA/PB/PC/PD/X/Y into _bg2_affine_snapshots[vcount] before DMA fires. _render_mode3/4/5 read from snapshots, falling back to live read if snapshot is None. step_scanline() takes a capture_snapshot=True flag (main loop=True, fallback=False).
**Files:** crates/gbatopy-cli/assets/gba_runtime/ppu.py
