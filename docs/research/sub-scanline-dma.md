# Sub-scanline DMA timing model

Research lane T3.1. Goal: decide whether the transpiled runtime's HBlank DMA should be
**full-burst** (all units in one HBlank) or **progressive** (one unit per HBlank), and
how the PPU sees VRAM mid-scanline. Every claim cites `file:line` (this repo's custom
mGBA at `mgba/`, GBATEK, or the transpiled `mode2.py`).

> **Scope note (memory map).** The `mgba/` tree uses the **standard GBA memory map**
> (GBATEK, "GBA Memory Map"): `0x02000000` = EWRAM (on-board WRAM), `0x03000000` = IWRAM
> (on-chip WRAM), `0x04000000` = I/O, `0x05000000` = palette RAM, `0x06000000` = **VRAM**
> (96 KB), `0x07000000` = OAM. So `0x06000000` is VRAM on **both** this mGBA build and real
> GBA hardware — there is no remap. Cited lines:
> - `mgba/include/mgba/internal/gba/memory.h:43-48`
>   `GBA_BASE_EWRAM = 0x02000000`, `GBA_BASE_IWRAM = 0x03000000`, `GBA_BASE_VRAM = 0x06000000`,
>   `GBA_BASE_OAM = 0x07000000` — matches the standard GBATEK map exactly.
> - `mgba/src/gba/memory.c:535` (`GBALoad16`) / `:476` (`GBALoad32`) dispatch on the
>   region nibble `address >> BASE_OFFSET` (`:541`), so CPU/DMA accesses to
>   `0x06000000` (region 6 = `GBA_REGION_VRAM`) hit the VRAM buffer.

Timing constants (this build, `mgba/include/mgba/internal/gba/video.h:25-40`, an
anonymous `enum`):
- `VIDEO_HDRAW_LENGTH = 1008` (video.h:27) — the 1008-cycle draw window per line
- `VIDEO_HBLANK_LENGTH = 224` (video.h:28) — the 224-cycle blanking window per line
- `VIDEO_HORIZONTAL_LENGTH = 1232` (video.h:29) — total cycles per line
- `VIDEO_VBLANK_PIXELS = 68` (video.h:31), `VIDEO_VERTICAL_TOTAL_PIXELS = 228`
  (video.h:32) — total vertical lines including VBlank
- The GBA screen is 240 wide × 160 tall; visible lines are 0–159 and VBlank is
  lines 160–227 (68 lines), so total = 228 = `VIDEO_VERTICAL_TOTAL_PIXELS`.

So one scanline is `1232` cycles: `1008` (hdraw) + `224` (hblank). GBATEK reports the
same `1232` total and breaks the 1008 hdraw into "draw ~960 / H-Blank-flag ~1006 / tail"
(see Q1).

---

## Q1 — When does HBlank DMA fire relative to PPU rendering?

**It fires at the END of the visible line's draw window (after that line's pixels are
produced) and BEFORE the next line's draw begins.** It does not fire at the start of the
blanking interval as a separate event — in this mGBA build the "hblank" event is the
boundary event where the previous line finishes and DMA is permitted.
 
> **Timing-model note (mGBA vs GBATEK).** mGBA's PPU uses a two-event model with
> `HDRAW=1008` / `HBLANK=224` cycles (`video.c:25-40`), which sums to GBATEK's
> 1232-cycle scanline. GBATEK's more detailed PPU timing is a 960-cycle draw + a
> 272-cycle H-Blanking window (16.212µs), and states the DISPSTAT H-Blank flag is held
> for 1006 cycles. The two agree on the 1232-cycle total and on the *ordering* that
> matters here (draw → HBlank DMA → next draw); only the exact split of draw vs blank
> differs. The transpiler's `instr_per_scanline` budget should be derived from the
> 1232-cycle total, not from either model's individual split.

mGBA event chain (`mgba/src/gba/video.c`, two static timing-event callbacks):
1. `_startHdraw` (`video.c:148`) — fires at the START of scanline `vcount`'s 1008-cycle
   draw window. It increments `vcount` (line 153), updates the `VCOUNT` register
   (line 157), and schedules `_startHblank` `VIDEO_HDRAW_LENGTH` (1008) cycles later
   (line 151). When `vcount == GBA_VIDEO_VERTICAL_PIXELS` (line 181) it also runs the
   VBlank block: `finishFrame` + `GBADMARunVblank` (line 186) + VBlank IRQ.
2. `_startHblank` (`video.c:205`) — fires at the END of the 1008 hdraw window
   (`hdraw_start + 1008`), i.e. the start of the 224-cycle blanking window. Inside it,
   in order:
   - schedules the next `_startHdraw` `VIDEO_HBLANK_LENGTH` (224) cycles later
     (line 208);
   - sets the `InHblank` DISPSTAT flag (line 212);
   - **draws the line**: `video->renderer->drawScanline(video->renderer, video->vcount)`
     (line 214) — scanline `vcount` is committed to the framebuffer;
   - **then fires HBlank DMA**: `GBADMARunHblank(video->p, -cyclesLate)` (line 218);
   - raises the HBlank IRQ (line 224).
3. `GBADMARunHblank` (`mgba/src/gba/dma.c:147-165`) sets `dma->when = now + 3 + cycles`
   (line 155), latches `nextCount = count` (line 157), then calls `GBADMAUpdate`
   (line 163) which starts the per-unit transfer chain (see Q2).

The ordering inside `_startHblank` is the key fact: `drawScanline` (line 214) runs
BEFORE `GBADMARunHblank` (line 218). So the HBlank DMA for scanline N fires AFTER line N
has been rendered and BEFORE line N+1 is rendered (line N+1's `drawScanline` runs in
the next `_startHblank`, 1232 cycles later).

**Conclusion:** the DMA is gated on the hblank boundary event that occurs after the
previous visible line's 1008-cycle draw completes and before the next line's draw
starts. The DMA runs during the 224-cycle blanking window, so it is invisible to the
line it precedes but visible to the line it follows (see Q3).

GBATEK (GBA LCD Video Controller, DISPSTAT section):
> "The PPU has a total of 1232 cycles to scan a scanline, of which it only uses 960
> to draw, and 1006 to keep the H-Blank flag "0". The PPU starts drawing the scanline
> after the V-Count/H-Count is updated. The PPU then takes 120 cycles to complete the
> scanline. The scanline timing is shown in Figure 13.5."

GBATEK's H-Blank flag being clear for 1006 cycles means the "HBlank" window spans most
of the non-drawing portion of the 1232-cycle line; the practical DMA-permission window
(the 224 cycles mGBA models as hblank) is a subset of it. Either way the DMA lands
between line N's draw and line N+1's draw.

**Implication for the transpiler:** "HBlank-triggered" = fires once, at the line
boundary, after the previous line renders. It is a timing *gate*, not a per-pixel or
per-scanline-internal signal. The transpiled runtime already models DMA as an event on
the scanline budget (`instr_per_scanline`), which matches this: DMA completes within
one scanline's budget, so the next line sees it.

---

## Q2 — Is HBlank DMA full-burst or progressive? Cycle cost per unit?

**mGBA does full-burst: it transfers ALL units of the latched count in a single HBlank
trigger, not one unit per HBlank.** The project memory note ("mGBA uses full-burst
HBlank DMA, not progressive") is **confirmed** for this build and for HBlank-triggered
transfers.

Mechanism (`mgba/src/gba/dma.c`): one HBlank trigger starts a **per-unit event chain**
that keeps going until the whole latched count is drained. There is no single
"transfer all units" loop — each unit is a separate `_dmaEvent` tick — but the ticks are
scheduled back-to-back with `cpuBlocked = true`, so the CPU never runs in between and
the burst is consumed as one continuous full-burst within the single HBlank trigger.

- `GBADMARunHblank` (`dma.c:147-165`) — on the HBlank trigger, sets
  `dma->when = now + 3 + cycles` (line 155), latches `nextCount = count` (line 157),
  then calls `GBADMAUpdate` (line 163).
- `_dmaEvent` (`dma.c:199`) — when `dma->when` elapses and `nextCount` is non-zero,
  calls `GBADMAService(gba, memory->activeDMA, dma)` (line 209).
- `GBADMAService` (`dma.c:259-358`) — transfers **one unit**:
  - `width = 2 << GBADMARegisterGetWidth(info->reg)` (line 262) → 2 for 16-bit, 4 for
    32-bit;
  - `gba->cpuBlocked = true` (line 270) — the CPU is halted for the whole burst;
  - computes this unit's cycle cost (lines 274-288) and advances `info->when += cycles`
    (line 288);
  - performs the bus op: 16-bit `store16` (line 313) or 32-bit `store32` (line 294),
    honoring `SrcIncrement`/`DstIncrement`/`DstFixed` via `info->sourceOffset` /
    `info->destOffset` (lines 318-319);
  - `--info->nextCount` (line 335); on reaching 0 it marks completion
    (`nextCount |= 0x80000000`, line 352);
  - calls `GBADMAUpdate` (line 357) which schedules the **next** unit's `_dmaEvent` —
    so the chain re-enters at line 209 and repeats until `nextCount` is exhausted.

The chain keeps re-scheduling itself (209 → 357 → 209 → …) until `nextCount` reaches zero
within the same HBlank trigger. It does **not** stop after one unit to let the CPU run or
to wait for the next HBlank — that is what "full-burst" means, and it matches the project
memory note. (The `Repeat` bit, masked at `dma.c:211-220`, is a *different* feature: it
re-arms the DMA at *every* HBlank. That is not "one unit per HBlank" — it is a
whole-burst-per-HBlank.)

> **Duration caveat.** The burst is continuous, but it runs at the DMA's own per-unit
> cycle cost, so its *duration* = `count × cycles-per-unit`. For a short transfer that is
> less than one 1232-cycle scanline; for a long transfer (e.g. ~1232 cycles) the burst
> spills from line N's hblank across line N+1's hdraw and completes around line N+1's
> hblank. Because the PPU reads VRAM live (Q3), a burst that spans a scanline is seen by
> the PPU *progressively* across the lines it overlaps — even though the DMA *mechanism*
> is a single full-burst trigger, not one-unit-per-HBlank.

**Cycle cost per unit** (`mgba/src/gba/dma.c:268, 274-288`, with the base waitstate
tables at `mgba/src/gba/memory.c:35-38`, mapped into the live arrays at
`memory.c:64-68`). A unit costs
`2 + waitstatesSeq{16|32}[srcRegion] + waitstatesSeq{16|32}[dstRegion]` cycles
(`2` is the base at `dma.c:268`; the first unit uses the non-sequential table at
`dma.c:276/282`, subsequent units reuse the cached `info->cycles` at `dma.c:283/286`).
Region indices: `2`=EWRAM, `3`=IWRAM, `6`=VRAM. From `GBA_BASE_WAITSTATES_SEQ`
(`memory.c:37`): EWRAM=2, IWRAM=0, VRAM=0.
- mode2's 16-bit IWRAM→VRAM: `2 + 0 + 0 = 2` cycles/unit → `616 × 2 ≈ 1232` cycles,
  about exactly one scanline.
- generic 16-bit IWRAM→EWRAM: `2 + 0 + 2 = 4` cycles/unit.
- 32-bit IWRAM→VRAM: `2 + 0 + 1 = 3` cycles/unit (VRAM's 32-bit seq waitstate = 1,
  `memory.c:38`).

So a 16-bit burst of 616 units takes on the order of ~1200–2500 cycles (region-
dependent) — a small multiple of one 1232-cycle scanline. A "one unit per HBlank" model
would instead stretch a 616-unit transfer across 616 scanlines (~13 display frames),
which no GBA game does (see Q4).

**Implication for the transpiler:** keep **full-burst** HBlank DMA. A progressive
(one-unit-per-HBlank) model is wrong for HBlank-triggered DMA and would make a
616-unit transfer take 616 scanlines (~13 display frames), which no GBA game does.

---

## Q3 — Does the PPU see DMA writes mid-scanline? Snapshot or live?

**Live. There is no snapshot/copy.** The mGBA PPU reads VRAM directly, word-for-word,
at each scanline's draw. A DMA write that lands before a scanline's draw is visible to
that scanline; a DMA write that lands during the blanking window of the *next* line is
visible to that next line. There is no frozen per-scanline copy of VRAM.

Evidence — the mode-2 (256BPP) background renderer reads the VRAM buffer live at draw
time, no cache:
- `mgba/src/gba/renderers/software-bg.c:155`
  `color = ((uint8_t*)renderer->d.vram)[offset + (localX >> 8) + (localY >> 8) * GBA_VIDEO_HORIZONTAL_PIXELS];`
- `mgba/src/gba/renderers/software-bg.c:164` (second half of the row)
- (8bpp/4bpp paths at lines 112/122/196/206 use `LOAD_16(..., renderer->d.vram)` — same
  live read.)

The ordering inside `_startHblank` (`video.c:205-224`) is: schedule next hdraw at
`+224` cycles (line 208) → set the InHblank flag (line 212) → **draw the line**
(`drawScanline`, line 214) → **fire HBlank DMA** (`GBADMARunHblank`, line 218) →
HBlank IRQ (line 224). So at a scanline boundary the order is: **line N draw → line N's
HBlank DMA → blank → line N+1 draw (reads live VRAM, sees line N's DMA)**.

Because the PPU reads VRAM live at each line's draw (`software-bg.c:155`), a DMA write
is visible to the *first line drawn after the write lands*. Two cases, per Q2's
duration caveat:
- **Short burst** (duration < one 1232-cycle scanline): the burst finishes during line
  N's blanking window, so line N+1's draw sees the **completed** burst.
- **Long burst** (duration ≥ one scanline, e.g. mode2's ~1232 cycles): the burst is
  still in progress when line N+1 is drawn, so the PPU sees VRAM in its state *at each
  line's draw* — the transfer effectively completes *across* the lines it overlaps
  (progressive from the PPU's point of view, even though the DMA mechanism is a single
  full-burst trigger, not one-unit-per-HBlank).

**Practical consequence:** HBlank DMA updates the line(s) it *precedes and overlaps*;
there is never a frozen per-scanline copy of VRAM. The "PPU sees a half-written table"
artifact is real on hardware for a long burst, but only for the lines the burst spans.

**Implication for the transpiler:** read the **live** VRAM buffer each scanline (no
snapshot/copy). Model the HBlank burst as a per-unit cycle-cost chain that may straddle
the scanline boundary; the PPU sees whatever is in VRAM at each line's draw. A
"DMA completes atomically before the next draw" model is only correct for short bursts.

---

## Q4 — What does mode2.gba specifically do?

The ROM's DMA setup, decoded from the transpiled `mode2.py` (literal pool + register
traces):

- `func_08000298` (boot/frame init, `mode2.py:10594-10637`):
  - `registers[12] = read_u32(0x080002E0 + 284)` → literal `0x080003FC` = `0x03000000`
    (`mode2.py:10624`). This is **SAD = IWRAM 0x03000000**.
- `func_08000368` (DMA arm setup, `mode2.py:10853-10876`):
  - `registers[2] = 0x04000000` (IO base, `mode2.py:10854`).
  - `registers[0]  = 0x06000000` (DAD value, `mode2.py:10856`).
  - `registers[14] = read_u32(0x0800038C + 128)` → literal `0x0800040C` = `0xA0400268`
    (CNT value, `mode2.py:10865`).
- DMA0 register writes (in small helper funcs, one store each):
  - `write_u32(registers[2] + 176, registers[12])` → `DMA0SAD` (`0x040000B0`) =
    `0x03000000` (`mode2.py:10940`, `func_080003D4_a`).
  - `write_u32(registers[2] + 180, registers[0])`  → `DMA0DAD` (`0x040000B4`) =
    `0x06000000` (`mode2.py:10954`, `func_080003D8_a`).
  - `write_u32(registers[2] + 184, registers[14])` → `DMA0CNT` (`0x040000B8`) =
    `0xA0400268` (`mode2.py:10955`, `func_080003D8_a`).

**Control `0xA040` decode** (DMA0CNT bits, GBATEK "GBA DMA Transfers" +
`mgba/include/mgba/internal/gba/dma.h:35` `DECL_BITS(GBADMARegister, Timing, 12, 2)`):
- bit 15 = 1  → DMA0 enable (1)
- bits 14-13 = `10` → **HBlank trigger** (timing = HBlank)
- bits 12-11 = `01` → **16-bit units**
- bit 9 = 0  → **one-shot** (Repeat bit clear; the DMA disables itself after this
  single transfer — on completion `dma.c:215-219` clears the enable bit in the register
  and in IO memory)
- bit 8 → SrcIncrement = 1 (source address increments)
- bit 6 → **DstFixed = 1** (destination address is fixed, does not increment)

So the control word `0xA040` = **enable, one-shot HBlank trigger, 16-bit units,
SrcIncrement, DstFixed**, with `count = 0x0268 = 616` halfwords. It fires **once**, at
the first HBlank after it is armed, and does **not** re-arm each scanline.

> ⚠️ **Premise check (rule 8d / 1e).** The task brief states "control=0xA040
> (HBlank trigger, DstCtrl=Fixed), Source=IWRAM 0x03000000, dest=VRAM 0x06000000,
> count=616". Verified against the ROM: **all of that is correct.** `0xA040` really is
> HBlank-triggered with DstFixed, SAD is IWRAM `0x03000000`, DAD is `0x06000000`, and
> count is 616. Two refinements: (a) the trigger is **one-shot** (bit 9 Repeat = 0), so
> it fires a single 616-unit burst at the first HBlank after arming and then disables
> itself — it does **not** re-fire every scanline. (b) The dest `0x06000000` is **VRAM**
> on both this mGBA build and real GBA hardware (standard map, `memory.h:47` / GBATEK
> memory map), so the DMA writes directly into the 256BPP background tile memory.

**Expected visual effect:** `DAD = 0x06000000` is **VRAM** (standard GBA map — both
mGBA and real hardware), and with **DstFixed** all 616 halfwords write to the *same*
16-bit word `VRAM[0x000000]`. Because the trigger is **one-shot** (bit 9 = 0), this
616-unit burst fires **exactly once**, at the first HBlank after `func_08000368` arms
it, and the DMA then disables itself (`dma.c:215-219` clears the enable bit on
completion). After that single burst `VRAM[0]` holds the 616th halfword's value from
IWRAM (`0x03000000 + 615*2`) and **stays frozen** for the rest of the run — the ROM
performs a single set of DMA0 register writes (SAD at `+176` = `0x040000B0`, DAD at
`+180` = `0x040000B4`, CNT at `+184` = `0x040000B8`; `mode2.py:10940,10954,10955`) with **no
re-arm loop**, so the DMA cannot fire again. The PPU (Mode 2 / 256BPP, per `mode2.py`
DISPCNT writes) renders the background from VRAM live (Q3), so the screen shows a
**static (non-scrolling, non-animating) 256BPP field** whose color comes from the frozen
`VRAM[0]` value against the current palette. This matches the documented
`docs/roadmap.md` F423 expected golden: **~80% black / ~18% red / ~2% white** — a flat,
frame-stable color field. The one-shot DMA is functionally a "write `VRAM[0]` once and
freeze the frame" operation.

**Net:** `mode2.gba`'s DMA0 (0xA040, count 616, IWRAM→0x06000000 DstFixed) is a
**one-shot HBlank 16-bit full-burst DMA that writes `VRAM[0]` once and freezes the
frame**, and the Mode-2 PPU renders that as a **static 256BPP color field
(≈80% black / 18% red / 2% white)**. It is full-burst (Q2) and the PPU sees it live
(Q3), so the screen is stable frame-to-frame — which is why a frozen golden is the
correct expectation, not an animation.

---

## Bottom line for the transpiler

1. **Keep HBlank DMA full-burst** (all units in one HBlank trigger). mGBA does this via
   the per-unit chain (`dma.c:209 → 357`, CPU halted at `dma.c:270`); progressive
   per-HBlank is wrong and would take 616 frames.
2. **Keep the PPU reading live VRAM each scanline** (no snapshot). mGBA's renderer does
   this (`software-bg.c:155`); a short burst completes before the next draw reads VRAM,
   a long burst is seen progressively across the lines it spans.
3. **HBlank DMA fires at the line boundary** (after the previous line's 1008-cycle draw,
   before the next line's draw) — `video.c:218` inside `_startHblank`, after
   `drawScanline` (line 214). Model the burst as a per-unit cycle-cost chain that may
   straddle the scanline boundary.
4. **mode2.gba's expected result is a static 256BPP field (≈80/18/2),** not animation —
   consistent with full-burst + live-VRAM + DstFixed-pinned `VRAM[0]`.

### Sources
- mGBA `mgba/src/gba/video.c:25-40` (timing constants enum), `148-224` (`_startHdraw` /
  `_startHblank`: VCOUNT update, `drawScanline` at 214, `GBADMARunHblank` at 218, next
  hdraw scheduled at 208).
- mGBA `mgba/src/gba/dma.c:147-165` (`GBADMARunHblank`), `167-185` (`GBADMARunVblank`),
  `199-222` (`_dmaEvent` full-burst dispatcher; one-shot enable-bit clear at 215-219), `259-358` (`GBADMAService` per-unit
  transfer; `cycles=2` base at 268, `cpuBlocked` at 270, nonseq/seq waitstates at
  276-286, `store32`/`store16` at 294/313, `--nextCount` at 335, completion flag at 352).
- mGBA `mgba/src/gba/memory.c:35-38` (base waitstate tables; SEQ: IWRAM=0, VRAM=0,
  EWRAM=2; SEQ_32: VRAM=1), `64-68` (mapped into the live `waitstatesSeq{16|32}` arrays).
- mGBA `mgba/include/mgba/internal/gba/video.h:25-40` (`VIDEO_HDRAW_LENGTH=1008`,
  `VIDEO_HBLANK_LENGTH=224`, `VIDEO_HORIZONTAL_LENGTH=1232`).
- mGBA `mgba/include/mgba/internal/gba/memory.h:23-39` (region enum), `41-57` (region
  bases; VRAM=`0x06000000` line 47, OAM=`0x07000000` line 48).
- mGBA `mgba/include/mgba/internal/gba/dma.h:22-26` (`GBADMATiming` enum), `35`
  (`Timing` bits 12-13).
- mGBA `mgba/src/gba/renderers/software-bg.c:155/164` (live 256BPP VRAM read, Mode 2);
  `112/122/196/206` (8bpp/4bpp live reads).
- GBATEK (problemkaputt.de/gbatek.htm) — "GBA Memory Map" (`0x02000000`=EWRAM/on-board
   WRAM, `0x03000000`=IWRAM/on-chip WRAM, `0x06000000`=VRAM, `0x07000000`=OAM), "GBA DMA
   Transfers" (transfer time for n units
  = `2N + 2(n-1)S + xI`, where N/S are non-sequential/sequential access cycle counts and
  I is internal DMA processing; H-Blanking = 272 cycles / 16.212µs) and "GBA LCD Video
  Controller / DISPSTAT" (1232 cycles/scanline: 960-cycle draw + H-Blank flag held
  1006 cycles; PPU draws after VCount/HCount update).
- Transpiled `mode2.py` — `func_08000298` (10594-10637; SAD load 10624), `func_08000368` (10853-10876; DAD value 10856, CNT value 10865), DMA0 writes 10940/10954/10955;
  literal pool `0x080003FC=0x03000000` (SAD/IWRAM),
  `0x08000400=0x06000800`, `0x08000404=0x802`, `0x08000408=0xC02`,
  `0x0800040C=0xA0400268` (count `0x268` + control `0xA040`).
- `docs/roadmap.md` F423 — mode2 cycle-accurate DMA target, golden 80% black / 18% red /
  2% white.
