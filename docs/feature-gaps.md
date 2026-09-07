# GBAtoPy Feature Gaps

Audit of unimplemented or partially implemented GBA features in the runtime (`crates/gbatopy-cli/assets/gba_runtime/ppu.py`). Note: The `crates/gbatopy-cli/src/codegen/ppu/` directory was deleted per F98 and no longer exists.

---

## Summary Table

| Feature | State | Affected ROMs | Effort | Priority |
|---------|-------|---------------|--------|----------|
| Windows (WIN0/WIN1/OBJ) | ✅ Verified (window_midframe PASS) | `window_midframe` passes | S | High |
| Alpha Blending (BLDCNT mode 1) | ✅ Working | None verified | M | Medium |
| Mosaic (BG + OBJ) | Implemented (per-BG + OBJ) | `sprite-hmosaic` passes | M | High |
| Brightness (BLDCNT mode 2/3) | ✅ Working — first-target gating implemented | None verified | S | Medium |
| Mode 1 rendering | FUNCTIONAL, unverified | None verified | S | Low |
| Mode 5 rendering | ✅ Implemented correctly (affine scaling + backdrop) | None verified | M | Low |

---

## 1. Windows (WIN0H/WIN0V/WIN1H/WIN1V/WININ/WINOUT)

**State:** Working — `window_midframe.gba` PASSES with 15.58% diff.

**Registers:** WIN0H=0x04000040, WIN1H=0x04000042, WIN0V=0x04000044, WIN1V=0x04000046, WININ=0x04000048, WINOUT=0x0400004A.

**Methods involved:**
- `_is_in_window(x, y, win_num)` — line 1396 — WIN0/WIN1 hit-test
- `_is_in_obj_window(x, y)` — line 1420 — OBJ window hit-test
- `_get_window_layer_enable(x, y, layer)` — line 1426 — per-pixel layer-enable mask
- Register I/O: `_write_register` window branch (line 975), `_read_register` window branch (line 1107)

**Registers:** 0x04000040-0x0400004A (WIN0H through WINOUT), 0x0400004C (MOSAIC), DISPCNT bits 13-15 (win0/win1/obj_window enables).

**Affected ROMs:** `window_midframe.gba` — PASS (15.58% diff).

**Effort to fix:** S (small). Fix the four register address constants, verify init order (`_read_registers` must be called before first render).

---

## 2. Alpha Blending (BLDCNT mode 1 / BLDALPHA / BLDY)

**State:** ✅ Working — alpha blend mode 1 is fully implemented.

**Methods involved:**
- `_blending_enabled()` — line 2475
- `_apply_blending_to_framebuffer()` — line 2478

**Registers:** 0x04000050 (BLDCNT), 0x04000052 (BLDALPHA), 0x04000054 (BLDY).

**Affected ROMs:** None verified. No test ROM in the current suite exercises BLDCNT mode 1.

**Effort to fix:** M (medium). Remove brightness leak from mode==1 branch, populate `second_target_framebuffer` during mode render, move blend call after sprite render.

---

## 3. Mosaic (MOSAIC / BGxCNT bit 6)

**State:** ✅ Implemented (per-BG + OBJ) — `sprite-hmosaic.gba` PASSES.

**Methods involved:**
- `_apply_mosaic(x, y, is_obj)` — line 1448
- `_write_register` MOSAIC branch — line 1003
- `_write_bg_control` (BGxCNT bit 6) — line 744

**Registers:** 0x0400004C (MOSAIC), BGxCNT bit 6 per-BG enable.

**Affected ROMs:** `sprite-hmosaic.gba` — PASS (27.02% diff). Tests OBJ horizontal mosaic which is implemented.

---

## 4. Brightness (BLDCNT mode 2/3 / BLDY)

**State:** ✅ Working — brightness increase (mode 2) and decrease (mode 3) correctly gate on 1st-target mask.

**Methods involved:**
- `_apply_blending_to_framebuffer()` — lines 2535-2556 (brightness branches)

**Registers:** 0x04000050 (BLDCNT bits 6-7 select mode 0-3), 0x04000054 (BLDY bits 0-4 = Evy).

**Affected ROMs:** None verified. No test ROM exercises BLDCNT mode 2/3.

**Effort to fix:** S (small). Gate brightness on 1st-target mask (BLDCNT bits 0-5), remove leak from `blend_mode == 1` branch.

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

**State:** Implemented correctly — `_render_mode5` at `ppu.py:2407-2473` (67 lines).

**Implemented:**
- 160x128 16-bit bitmap via affine BG2 (lines 2431-2432, 2445-2470)
- Per-scanline affine snapshots (lines 2421-2440)
- Affine math: `source_x = sx + x*dx + y*dmx`, fixed-point `>> 8`
- Page-flip handling (`page == 0 ? 0x06000000 : 0x0600A000`) — consistent with Mode 3
- Windows, blend, sprite composite

**Affected ROMs:** None verified.

---

## Additional Findings

- `REG_BLDWIN = 0x04000056` is defined twice (`ppu.py:660-661`) and never used by any blend logic. 0x04000056 is not a standard GBA register.
- `REG_MOSAIC_EXT = 0x040000F4` (`ppu.py:667`) is a non-standard alias with no GBATEK basis.
- Lines 706-707 (`self.win1_enable = False`, `self.obj_window_enable = False`) are set in `__init__` after the BGxCNT read loop — benign only if `_read_registers()` is always called before the first render.

---

## Priority Order for Implementation

| Priority | Feature | Effort | Affects |
|----------|---------|--------|---------|
| P1 | Fix brightness leak in alpha-blend branch (§2, §4) | S | None verified |
| P2 | Populate `second_target_framebuffer` (§2) | M | None verified |
| P2 | Move blend call after sprite render (§2) | S | None verified |
| P2 | Fix per-BG mosaic flag (§3) | S | None verified |
| P2 | Fix vertical mosaic Y-snap (§3) | S | None verified |
| P3 | Verify Mode 1 with golden screenshot (§6) | S | None verified |
| P3 | Remove `try/except: continue` in Mode 1 BG2 path (§6) | S | None verified |
