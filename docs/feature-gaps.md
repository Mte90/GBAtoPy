# GBAtoPy Feature Gaps

Audit of unimplemented or partially implemented GBA features in the runtime (`crates/gbatopy-cli/assets/gba_runtime/ppu.py`) and codegen (`crates/gbatopy-cli/src/codegen/ppu/`).

**Key finding:** The AGENTS.md claim "Windows, blend, mosaic: register stubs only (not functional)" is **inaccurate**. All four features have non-stub implementations of varying correctness. The codegen `ppu/` directory is vestigial — all rendering lives in the runtime Python.

---

## Summary Table

| Feature | State | Affected ROMs | Effort | Priority |
|---------|-------|---------------|--------|----------|
| Windows (WIN0/WIN1/OBJ) | PARTIAL — wrong register addresses | `window_midframe` | S | High |
| Alpha Blending (BLDCNT mode 1) | PARTIAL — brightness leak, no 2nd-target FB | None verified | M | Medium |
| Mosaic (BG + OBJ) | PARTIAL — OBJ mosaic stubbed, per-BG flag ignored | `sprite-hmosaic` | M | High |
| Brightness (BLDCNT mode 2/3) | PARTIAL — applied to all pixels, not 1st-target | None verified | S | Medium |
| Mode 1 rendering | FUNCTIONAL, unverified | None verified | S | Low |
| Mode 5 rendering | PARTIAL — no affine scaling, hardcoded backdrop | None verified | M | Low |

---

## 1. Windows (WIN0H/WIN0V/WIN1H/WIN1V/WININ/WINOUT/WINOBJ)

**State:** PARTIAL — code exists and is called from `_render_mode0/1/2` and sprite rendering, but has wrong register addresses.

**Bug — wrong register addresses** (`ppu.py:645-648`):
```python
REG_WIN0H = 0x04000040  # correct
REG_WIN1H = 0x04000041  # WRONG — should be 0x04000042 (16-bit stride)
REG_WIN0V = 0x04000042  # WRONG — should be 0x04000044
REG_WIN1V = 0x04000043  # WRONG — should be 0x04000046
```
GBATEK specifies each window register is 16-bit: WIN0H=0x04000040, WIN1H=0x04000042, WIN0V=0x04000044, WIN1V=0x04000046. Any game writing WIN1H at 0x04000042 will not be caught by the current register dispatch.

**Methods involved:**
- `_is_in_window(x, y, win_num)` — line 1396 — WIN0/WIN1 hit-test
- `_is_in_obj_window(x, y)` — line 1420 — OBJ window hit-test
- `_get_window_layer_enable(x, y, layer)` — line 1426 — per-pixel layer-enable mask
- Register I/O: `_write_register` window branch (line 975), `_read_register` window branch (line 1107)

**Registers:** 0x04000040-0x0400004A (WIN0H through WINOUT), 0x0400004C (WINOBJ), DISPCNT bits 13-15 (win0/win1/obj_window enables).

**Affected ROMs:** `window_midframe.gba` — FAIL (55.6% diff, all-black output). The wrong register addresses prevent window configuration from being read.

**Effort to fix:** S (small). Fix the four register address constants, verify init order (`_read_registers` must be called before first render).

---

## 2. Alpha Blending (BLDCNT mode 1 / BLDALPHA / BLDY)

**State:** PARTIAL — blend mode 1 is implemented but has three correctness bugs.

**Bug 1 — brightness leak into alpha-blend branch** (`ppu.py:2526-2534`):
When BLDCNT mode=1 (alpha blend) and BLDY>0, the code applies BOTH alpha blend AND brightness increase. GBATEK says BLDY only applies when mode=2 or 3. The brightness-increase loop at lines 2526-2534 runs unconditionally inside the `blend_mode == 1` branch.

**Bug 2 — `second_target_framebuffer` never populated** (`ppu.py:860`):
`_apply_blending_to_framebuffer` reads `self.second_target_framebuffer[y][x]` for non-backdrop 2nd targets, but no code path writes to it. Non-backdrop 2nd targets always fall through to the backdrop color.

**Bug 3 — blend runs before sprites** (`ppu.py:1622-1626`):
`_apply_blending_to_framebuffer` is called from `render_frame` after mode render but before `_render_sprites`. OBJ-layer pixels (layer_origin=4) are not yet drawn when blend runs, so OBJ as 1st/2nd target is broken.

**Methods involved:**
- `_blending_enabled()` — line 2475
- `_apply_blending_to_framebuffer()` — line 2478

**Registers:** 0x04000050 (BLDCNT), 0x04000052 (BLDALPHA), 0x04000054 (BLDY).

**Affected ROMs:** None verified. No test ROM in the current suite exercises BLDCNT mode 1.

**Effort to fix:** M (medium). Remove brightness leak from mode==1 branch, populate `second_target_framebuffer` during mode render, move blend call after sprite render.

---

## 3. Mosaic (MOSAIC / BGxCNT bit 6)

**State:** PARTIAL — BG mosaic implemented for Mode 0/1 text BGs only. OBJ mosaic is a stub (register parsed but never applied).

**Bug 1 — OBJ mosaic never applied** (`ppu.py:2740-2770`):
`_apply_mosaic(is_obj=True)` is never called from `_render_sprites`. The sprite mosaic bits (`obj_mosaic_h/v`) are parsed from the MOSAIC register (line 1003) but unused. This is why `sprite-hmosaic.gba` shows 0% content vs 21.53% golden.

**Bug 2 — per-BG mosaic enable ignored** (`ppu.py:744, 1078`):
`bg_mosaic[bg]` is read from BGxCNT bit 6 but `_apply_mosaic` only checks the global `mosaic_enabled` flag, not the per-BG flag. If BG0 has mosaic disabled in BG0CNT but BG3 has it enabled, BG0 still gets mosaiced.

**Bug 3 — vertical mosaic Y-snap breaks scrolling** (`ppu.py:1448-1465`):
`_apply_mosaic` snaps screen (x,y) to block boundaries, then the caller adds `bg_hofs/bg_vofs`. GBATEK mosaic should advance the source row every `v_size` scanlines, not snap Y. The current implementation breaks vertical scrolling.

**Methods involved:**
- `_apply_mosaic(x, y, is_obj)` — line 1448
- `_write_register` MOSAIC branch — line 1003
- `_write_bg_control` (BGxCNT bit 6) — line 744

**Registers:** 0x0400004E (MOSAIC), BGxCNT bit 6 per-BG enable.

**Affected ROMs:** `sprite-hmosaic.gba` — Partial FAIL (0% transpiled content vs 21.53% golden). Tests OBJ horizontal mosaic which is not implemented.

**Effort to fix:** M (medium). Add OBJ mosaic call in `_render_sprites`, honor per-BG `bg_mosaic[bg]` flag, fix vertical mosaic to advance source row every `v_size` scanlines.

---

## 4. Brightness (BLDCNT mode 2/3 / BLDY)

**State:** PARTIAL — brightness increase (mode 2) and decrease (mode 3) are implemented but applied to the entire framebuffer unconditionally.

**Bug 1 — brightness applied to ALL pixels, not just 1st-target** (`ppu.py:2535-2556`):
GBATEK says brightness (modes 2/3) only affects pixels whose source layer is in BLDCNT bits 0-5 (1st target). The current code brightens/darkens every pixel including backdrop and non-target layers.

**Bug 2 — blend-mode-1 leak** (`ppu.py:2526-2534`):
The brightness-increase loop also runs inside `blend_mode == 1`, so alpha-blend mode unintentionally also brightens when BLDY>0 (same as Bug 1 in section 2 above).

**Methods involved:**
- `_apply_blending_to_framebuffer()` — lines 2535-2556 (brightness branches)

**Registers:** 0x04000050 (BLDCNT bits 6-7 select mode 0-3), 0x04000054 (BLDY bits 0-4 = Evy).

**Affected ROMs:** None verified. No test ROM exercises BLDCNT mode 2/3.

**Effort to fix:** S (small). Gate brightness on 1st-target mask (BLDCNT bits 0-5), remove leak from `blend_mode == 1` branch.

---

## 5. Codegen PPU Tree (vestigial)

**State:** The codegen directory `crates/gbatopy-cli/src/codegen/ppu/` is vestigial.

**Contents:**
- `mod.rs` — 1 line: `pub mod mode1;` (module declaration only, no dispatch)
- `mode1.rs` — 3 lines: dead stub, zero callers across the entire `crates/` tree

**No `mode0.rs`, `mode2.rs`, `mode3.rs`, `mode4.rs`, or `mode5.rs` exist.** All six mode renderers live in the runtime Python at `ppu.py:render_frame()` (line 1608-1619), which dispatches via if/elif to `_render_mode0()` through `_render_mode5()`.

The `mode1.rs` function `generate_mode1_rendering()` emits only `ppu_instance.mode = 1` and is never called. It is dead code.

**Recommendation:** Delete `mode1.rs` and `mod.rs`, or wire them in. Currently they do nothing.

---

## 6. Mode 1 Rendering (runtime)

**State:** FUNCTIONAL but unverified — `_render_mode1` at `ppu.py:1727-1936` (210 lines).

**Implemented:**
- BG0/BG1 text-mode rendering with tile cache, 4BPP/8BPP, palette, priority (lines 1808-1847)
- BG2 affine transform with per-scanline snapshots (lines 1778-1793, 1849-1925)
- Affine math: `source_x = sx + x*dx + y*dmx`, fixed-point `>> 8` (lines 1857-1862)
- BG2 wrap-around for all 4 size cases (256x256 / 512x256 / 256x512 / 512x512) via `overflow` flag (lines 1865-1878)
- Windows, mosaic (text BGs only), sprite composite (lines 1776, 1815, 1935-1936)

**Gaps vs verified modes:**
- `try/except: continue` around BG2 tilemap read (lines 1901-1904) silently drops pixels on addressing errors — masks real bugs. Mode 0 has no such swallow.
- Non-overflow out-of-bounds does `continue` leaving backdrop (line 1879-1880); Mode 3 fills backdrop color explicitly (line 2292). Inconsistent.

**Affected ROMs:** None verified.

**Effort to verify:** S (small). Generate golden screenshot with mGBA for a Mode 1 ROM, compare. Code is functionally complete.

---

## 7. Mode 5 Rendering (runtime)

**State:** PARTIAL — `_render_mode5` at `ppu.py:2407-2473` (67 lines). Two real gaps.

**Gap 1 — no affine scaling 160x128 → 240x160** (lines 2436-2470):
Mode 5 is a 160x128 16-bit bitmap scaled by BG2 affine to fill 240x160. The current renderer reads affine params but writes directly to `fb[y][px]` with `y in range(128)`, `px in range(160)` — no scaling to 240x160 occurs. Rows 128-159 are left as the `_init_framebuffer()` backdrop. This is the likely reason Mode 5 is "not verified."

**Gap 2 — hardcoded black backdrop** (lines 2454, 2467):
Mode 5 uses `(0,0,0)` as backdrop. Mode 3 reads palette entry 0 from `0x05000000` (lines 2248-2256). A Mode 5 ROM with a non-black backdrop will render wrong.

**Implemented:**
- 160x128 16-bit bitmap via affine BG2 (lines 2431-2432, 2445-2470)
- Per-scanline affine snapshots (lines 2421-2440)
- Affine pipeline structurally identical to Mode 3 (lines 2233-2311)
- Page-flip handling (`page == 0 ? 0x06000000 : 0x0600A000`) — consistent with Mode 3

**Affected ROMs:** None verified.

**Effort to complete:** M (medium). Implement BG2 affine scaling (map 160x128 source → 240x160 destination), replace hardcoded backdrop with palette read from 0x05000000.

---

## Additional Findings

- `REG_BLDWIN = 0x04000056` is defined twice (`ppu.py:660-661`) and never used by any blend logic. 0x04000056 is not a standard GBA register.
- `REG_MOSAIC_EXT = 0x040000F4` (`ppu.py:667`) is a non-standard alias with no GBATEK basis.
- Lines 706-707 (`self.win1_enable = False`, `self.obj_window_enable = False`) are set in `__init__` after the BGxCNT read loop — benign only if `_read_registers()` is always called before the first render.

---

## Priority Order for Implementation

| Priority | Feature | Effort | Affects |
|----------|---------|--------|---------|
| P0 | Fix window register addresses (§1) | S | `window_midframe` |
| P0 | Add OBJ mosaic call in `_render_sprites` (§3) | S | `sprite-hmosaic` |
| P1 | Fix brightness leak in alpha-blend branch (§2, §4) | S | None verified |
| P1 | Gate brightness on 1st-target mask (§4) | S | None verified |
| P1 | Delete vestigial codegen `ppu/mode1.rs` + `mod.rs` (§5) | S | Code hygiene |
| P2 | Populate `second_target_framebuffer` (§2) | M | None verified |
| P2 | Move blend call after sprite render (§2) | S | None verified |
| P2 | Fix per-BG mosaic flag (§3) | S | None verified |
| P2 | Fix vertical mosaic Y-snap (§3) | S | None verified |
| P3 | Implement Mode 5 affine scaling (§7) | M | None verified |
| P3 | Verify Mode 1 with golden screenshot (§6) | S | None verified |
| P3 | Remove `try/except: continue` in Mode 1 BG2 path (§6) | S | None verified |
