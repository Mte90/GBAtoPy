# ARM7TDMI Instruction Cycle Weights

Research notes for the GBAtoPy timing model (per-scanline instruction budgets, instruction-counted
main loop). Every claim carries a `file:line` or a document/section citation.
mGBA source tree root: `/home/d.scasciafratte/gbatopy/mgba/` (custom patches, not a git repo).

Status: researched 2026-11-16 (T3.1). Confidence: high for the mGBA model (read directly);
medium for TRM section numbering across revisions (E and G revisions number the same content
differently — both cited below).

---

## 1. Cycle-type taxonomy (S / N / I / C)

The ARM7TDMI timing model expresses instruction cost in four bus-cycle types:

| Type | Meaning | Cost |
|---|---|---|
| `1S` | Sequential access — transfer to/from the address directly after the previous cycle's address (GBA "2nd access") | 1 clock + sequential waitstates |
| `1N` | Non-sequential access — transfer to an address unrelated to the previous cycle's (GBA "1st access") | 1 clock + non-sequential waitstates |
| `1I` | Internal cycle — CPU busy, no memory transfer requested | 1 clock, no waitstates |
| `1C` | Coprocessor cycle — data bus used for coprocessor, no memory transfer | coprocessor-dependent |

Sources:
- GBATEK, "ARM CPU Instruction Cycle Times" (https://www.problemkaputt.de/gbatek-arm-cpu-instruction-cycle-times.htm) —
  definitions: "N - Non-sequential cycle ... The execution time for 1N is 1 clock cycle (plus
  non-sequential access waitstates). S - Sequential cycle ... I - Internal Cycle CPU is just too
  busy ... The execution time for 1I is 1 clock cycle (without any waitstates). C - Coprocessor
  Cycle ... no memory transfers are requested."
- ARM7TDMI TRM, DDI 0029E (1996) "Instruction cycle timings", §4.2.1 "Instruction cycle types"
  (1S, 1N, 1I, 1C definitions; PDF via https://www.manualslib.com/manual/830846/Arm/Arm7Tdm-Core.html).
- ARM7TDMI TRM, DDI 0029G (current), §4.2.1 (same four types;
  https://support.arm.com/documentation/ddi0029/g/instruction-cycle-timings/instruction-cycle-types).
- mGBA implements the same classification in the memory waitstate tables:
  `mgba/src/gba/memory.c:1319` (16-bit waitstates: `waitstatesNonseq16 = 2*ws+2`,
  `waitstatesSeq16 = 2*ws+1`), `memory.c:1324-1329` (32-bit:
  `waitstatesNonseq32 = 2*ws+2`, `waitstatesSeq32 = 2*ws+1`), ROM region at `memory.c:1342-1347`.

GBA memory waitstates (source: `mgba/src/gba/memory.c`, `GBAMemoryStall` init):
- IWRAM / EWRAM: 0 waitstates (`memory.c:1304-1305`)
- BIOS: 0 (`memory.c:1309`)
- IO, VRAM, OAM, Palette: 0 (`memory.c:1315-1317`, `1330-1331`, `1335`, `1338`)
- ROM: WS0-WS2 from waitstate control register; `nonseq16 = 2*ws+2`, `seq16 = 2*ws+1`,
  `nonseq32 = 2*ws+2`, `seq32 = 2*ws+1` (`memory.c:1319-1329` applied at `1342-1347`),
  runtime adjustment via `GBAAdjustWaitstates` (`memory.c:1686+`, register decode
  `sram/ws0/ws0seq/ws1/ws1seq/ws2/ws2seq` at `memory.c:1689-1695`).
- SRAM: 0 in mGBA's initialization (`memory.c:1365-1370` — mGBA models SRAM with no waitstates).

So for the common GBA case (code in ROM WS0=0, data in IWRAM/EWRAM/VRAM):
`seq16 = 1`, `nonseq16 = 2`, `seq32 = 3`, `nonseq32 = 6` (all from the formulas above).

---

## 2. ARM-state instruction cycle counts (TRM)

Source tables (per-instruction, ARM state):
- DDI 0029E data sheet, §4.1–4.13 "Instruction cycle timings" (per-instruction incremental-cycle
  tables; PDF via manualslib, sections listed at `p.4-9`..`p.4-15` of the TOC:
  4.1 data processing, 4.2 MSR/MRS, 4.3 LDR, 4.4 LDRB/LDRH/LDR-misaligned/LDR-literal,
  4.5 STR, 4.6 STRB/STRH, 4.7 LDM, 4.8 STM, 4.9 SWP, 4.10 B/BL/BLX, 4.11 MUL, 4.12 MLA/MULL/MLAL,
  4.13 coprocessor instructions).
- DDI 0029G, §6.23 "Instruction speed summary", Table 6-23 (p. 171) — the compact summary table,
  identical in substance to the E-revision per-instruction tables:
  (https://support.arm.com/documentation/ddi0029/g/instruction-cycle-timings/instruction-speed-summary?lang=en)
- GBATEK summary table (URL in §1) — matches Table 6-23 and adds GBA-specific notes
  (code/data split, Thumb BL).

| Instruction class | Incremental cycles (0 waitstates) | Additional |
|---|---|---|
| Data processing (ALU) | `1S` | `+1S+1N` if R15 (PC) loaded; `+1I` if SHIFT(Rs) |
| MSR / MRS (PSR transfer) | `1S` | — |
| LDR (word, 32-bit) | `1S+1N+1I` | `+1S+1N` if R15 loaded |
| LDRB / LDRH / LDR misaligned / LDR literal | `1S+1N+2I` | `+1S+1N` if R15 loaded |
| STR (word) | `2N` | — |
| STRB / STRH | `2N` | — |
| LDM (n words) | `nS+1N+1I` | `+1S+1N` if R15 loaded |
| STM (n words) | `(n-1)S+2N` | — (PC not allowed in list) |
| SWP | `1S+2N+1I` | — |
| B, BL (ARM state), BLX | `2S+1N` | — |
| MUL | `1S+m` | m = multiplier cycles, 1–4 |
| MLA / MULL | `1S+(m+1)I` | m = 1–4 |
| MLAL | `1S+(m+2)I` | m = 1–4 |
| CDP | `1S+bI` | b = coprocessor busy-wait cycles |
| LDC / STC (n words) | `(n-1)S+2N+bI` | — |
| MCR | `1N+bI+1C` | — |
| MRC | `1S+(b+1)I+1C` | — |
| `{cond}` false (non-executed conditional) | `1S` | — |
| SWI / exception entry | `2S+1N` | — |

Variable definitions (GBATEK): `n` = number of words transferred; `b` = coprocessor
busy-wait cycles; `m` = multiplier cycles (depends on the most significant byte(s) of the
multiplier operand).

At zero waitstates these collapse to plain clock counts:
- ALU: 1 (2 with register shift, 3 if writing PC)
- LDR word: 3 (5 if writing PC)
- LDRB/LDRH: 5 (per `1S+1N+2I`)
- STR: 2
- LDM n: n+2 (n+4 if writing PC, per `nS+1N+1I + 1S+1N`)
- STM n: n+1
- SWP: 4
- B/BL taken: 3
- MUL: 2–5
- MRC: 3+b+1, MCR: 1+b+1 (b=0 typical)
- Non-executed conditional: 1

Code/data split note (GBATEK): "When executing code in one area which accesses data in another
area, then the S+N cycles must be split into code and data accesses: 1N is used for data access,
plus (n-1)S for LDM/STM, the remaining S+N are code access. If an instruction jumps to a
different memory area, then all code cycles for that opcode are having waitstate characteristics
of the NEW memory area (except Thumb BL which still executes 1S in OLD area)." This is why
LDR-from-ROM-WS0 costs more than LDR-from-IWRAM even for the same opcode.

---

## 3. Thumb-state instruction cycle counts

Documented Thumb-specific timing data:

1. **Thumb BL (combined form)** — the only Thumb instruction with a dedicated TRM table:
   - DDI 0029G §6.3 "B, BL (Thumb combined form)" (p. 130): the combined BL executes in two
     halves. "The first half is a simple instruction fetch (1S). The second half ... requires a
     total of 4 bus cycles. The cycle timings ... are given in Table 6-2."
     (https://support.arm.com/documentation/ddi0029/g/instruction-cycle-timings/thumb-bl?lang=en)
   - DDI 0029E §4.10 "B, BL, BLX" (p. 4-14) carries the same ARM-side `B, BL = 2S+1N` and the
     Thumb combined form.
   - GBATEK: `BL (THUMB) 3S+1N` (i.e. 4 cycles at zero waitstates), consistent with the TRM's
     "total of 4 bus cycles".

2. **No other per-instruction Thumb tables exist in the TRM.** The E-revision data sheet's
   cycle-timing chapter (§4) and the G-revision's §6.x cover ARM-state instructions only; the G
   revision adds §6.3 (Thumb BL) as the sole Thumb exception. Consequence: for a Thumb timing
   model one must use (a) the ARM-state tables as the base (Thumb executes the same operations)
   with (b) the known structural differences — 16-bit instruction fetch (so the instruction-fetch
   cycle uses `seq16` waitstates, not `seq32`) and (c) the specific Thumb quirks (Thumb BL,
   Thumb SWI) from (1) and from emulator practice. GBATEK's summary table likewise lists only one
   Thumb-specific row (`BL (THUMB)`).

This is a research gap, not an oversight: neither cited TRM revision publishes Thumb LDR/STR or
Thumb data-processing tables. The mGBA model below (§4) is the authoritative machine for what a
reference GBA emulator actually charges per Thumb instruction.

---

## 4. How mGBA assigns cycle costs per instruction

**There is no static per-instruction cycle table.** Every instruction handler accumulates a
per-execution `currentCycles` counter that starts from a fetch base and is then extended by
operation-specific costs and by waitstate-stall costs from the memory layer.

### 4.1 The base: instruction fetch (the "1S")

- ARM state: `DEFINE_INSTRUCTION_ARM` begins every ARM handler with
  `int currentCycles = ARM_PREFETCH_CYCLES;` (`mgba/src/arm/isa-arm.c:280`) and finishes with
  `cpu->cycles += currentCycles;` (`isa-arm.c:282`).
- `ARM_PREFETCH_CYCLES` is `1 + cpu->memory.waitstatesSeq32[cpu->prefetchAddr >> BASE_OFFSET]`
  (`mgba/include/mgba/internal/arm/isa-arm.h:13`) — one instruction-fetch cycle plus the
  *sequential 32-bit* waitstates of the region the instruction is fetched from.
- Thumb state: `DEFINE_INSTRUCTION_THUMB` does the same with
  `THUMB_PREFETCH_CYCLES` = `1 + waitstatesSeq16[...]` (`mgba/src/arm/isa-thumb.c:50`).

So an ALU instruction in IWRAM costs exactly 1; in ROM WS0 it costs 1 + 3 = 4 (ARM) or
1 + 1 = 2 (Thumb), matching the TRM "code cycles take the NEW area's waitstates" rule.

Non-executed conditionals cost exactly the fetch: the decode loop, when the condition fails,
falls into `cpu->cycles += ARM_PREFETCH_CYCLES;` (`mgba/src/arm/arm.c:207-212`). Matches the
TRM `{cond} false = 1S`.

### 4.2 Operation-specific costs (all in `mgba/src/arm/`)

| Cost | Where | Value |
|---|---|---|
| PC write (branch / exception return) | `ARMWritePC` (`isa-arm.c:97-103`) | `2` + code waitstates (the 1S+1N refill penalty) |
| PC write (Thumb) | `ThumbWritePC` (`isa-thumb.c:40-47`) | `2` (flat, no code-wait addition) |
| Register shift | `isa-arm.c:21` (shift by shifted immediate), `:56` (shift by register), `:91`, `:126` | `+1` each |
| 32-bit load base | `GBALoad32` (`mgba/src/gba/memory.c:1564-1575`): `wait = 2 + GBAMemoryStall(cpu, nonseq32[region])`, then `currentCycles += wait`, then caller adds `nonseq32 - seq32` post | +2 before, +(nonseq32−seq32) after |
| 16-bit load base | `GBALoad16` (`memory.c:1578-1601`) | +0 (waitstates only) |
| 8-bit load base | `GBALoad8` (`memory.c:1603-1614`) | +0 (waitstates only) |
| 32-bit store base | `GBAStore32` (`memory.c:1597`) | `+1` |
| 16/8-bit store base | `GBAStore16`/`GBAStore8` (`memory.c:1598-1614`) | +0 (waitstates only) |
| Block transfer, per word | `LDM_LOOP` / `STM_LOOP` (`memory.c:1450-1482`, `:1568-1597`) | `++wait` per transferred word |
| Block transfer, PC in list | `LDM_LOOP` `wait += 16` (`memory.c:1454`), `STM_LOOP` `wait += 16` (`memory.c:1572`) | +16 |
| LDM trailing internal cycle | `GBALoadMultiple` `++wait` (`memory.c:1550`) | +1 |
| STM: no trailing cycle | `GBAStoreMultiple` just `*cycleCounter += wait` (`memory.c:1668-1672`) | 0 |
| Multiply | `ARM_WAIT_MUL` (`isa-arm.h:14-17`): `r & 0xFF` ? `r & 0x80` ? 4 : 2 : (`r & 0x7F` ? 3 : 1) | 1–4 |
| Stall on ROM accesses | `GBAMemoryStall` (`memory.c:1779`), called from the load/store/block paths (`memory.c:1566`, `1610`, `1659-1671`, `1779+`) | +`nonseq/seq32[ROM]` |

Handler-level examples (cite these when auditing the model):
- ARM B/BL: `currentCycles += ARMWritePC(cpu)` (`isa-arm.c:1261-1265`).
- ARM BX: `currentCycles += ARMWritePC(cpu)` (`isa-arm.c:1498-1502`).
- ARM MRS (read PC as R15): `currentCycles += ARMWritePC(cpu)` (`isa-arm.c:1513-1517`).
- ARM SWP: load via `GBALoad32` + store via `GBAStore32` (`isa-arm.c` SWP handler — the
  `GBALoad32`/`GBAStore32` calls at the handler body).
- ARM SWI: `cpu->irqh.swi32(cpu, opcode & 0xFFFFFF)` (`isa-arm.c:780`) — returns via the
  exception path, which charges `ARMWritePC`.
- ARM MUL: `currentCycles += ARM_WAIT_MUL(cpu->gprs[rm])` (`isa-arm.c:1656`); MLA/MULL/MLAL
  use `ARM_WAIT_MLA`/`ARM_WAIT_MULL`/`ARM_WAIT_MLAL` (`isa-arm.c:1661-1665`).
- Thumb B/BCC taken: `currentCycles += ThumbWritePC(cpu)` (`isa-thumb.c:324-330`).
- Thumb BX: `currentCycles += ARMWritePC(cpu)` (`isa-thumb.c:248-251`).
- Thumb BL second half: `currentCycles += ARMWritePC(cpu)` (`isa-thumb.c:285` inside the
  `BL` handler, following the first-half data form at `isa-thumb.c:~278-284`).
- Thumb SWI: `cpu->irqh.swi16(cpu, opcode)` with **no** `ARMWritePC`
  (`isa-thumb.c:232-260`, SWI handler) — Thumb SWI costs only the fetch base.
- Thumb LDMIA/STMIA: `DEFINE_LOAD_STORE_MULTIPLE_THUMB` dispatches to
  `cpu->memory.loadMultiple` / `cpu->memory.storeMultiple` (`isa-thumb.c:293-301`,
  `:303-314`, `:316-322`); Thumb LDMIA with PC adds `ThumbWritePC`
  (`isa-thumb.c:309-311`).
- Thumb load/store with register offset: `DEFINE_LOAD_STORE_WITH_REGISTER_THUMB`
  (`isa-thumb.c:280-291`) — note `LDRSB`/`LDRSH` **do exist** in mGBA's Thumb set
  (`isa-thumb.c:287-288`), matching the ARMv4T Thumb ISA.

### 4.3 Resulting cost table (computed from the sources above)

At zero waitstates (code + data in IWRAM):

| Instruction | mGBA cost | TRM equivalent | Match? |
|---|---|---|---|
| ARM ALU | 1 | 1S | ✓ |
| ARM ALU, register shift | 2 | 1S+1I | ✓ |
| ARM ALU writing PC | 3 | 1S+1S+1N | ✓ |
| ARM LDR (word) | 3 | 1S+1N+1I | ✓ |
| ARM LDRB / LDRH | 1 (+waitstates) | 1S+1N+2I | ✗ mGBA is lighter (no 2I, no 2N base) |
| ARM STR (word) | 2 | 2N | ✓ |
| ARM STRB / STRH | 1 | 2N | ✗ mGBA lighter |
| ARM LDM n words | 1 + n + 1 = n+2 | nS+1N+1I = n+2 | ✓ |
| ARM LDM n words, PC in list | n+18 | nS+1N+1I+1S+1N = n+4 | ✗ mGBA adds a flat +16 PC penalty |
| ARM STM n words | 1 + n = n+1 | (n-1)S+2N = n+1 | ✓ |
| ARM SWP | 1 + 2 + 1 = 4 | 1S+2N+1I = 4 | ✓ |
| ARM B/BL taken | 1 + 2 = 3 | 2S+1N = 3 | ✓ |
| ARM B/BL not taken | 1 | 1S | ✓ |
| ARM MUL | 1 + (1–4) = 2–5 | 1S+m | ✓ |
| ARM MRC (coproc) | not modeled as a coproc op — GBA has no coproc instructions in practice | 1S+(b+1)I+1C | n/a |
| Thumb ALU | 1 | (1S) | ✓ |
| Thumb LDR (word) | 3 | (1S+1N+1I) | ✓ |
| Thumb LDRB/LDRH/LDRSB/LDRSH | 1 (+waitstates) | — (no TRM Thumb table) | — |
| Thumb STR (word) | 2 | (2N) | ✓ |
| Thumb LDMIA n | n+2 | — (no TRM Thumb table) | — |
| Thumb LDMIA n, PC | n+2+2 = n+4 | (3S+1N-style) | model-specific |
| Thumb STMIA n | n+1 | — | — |
| Thumb B/BCC taken | 1 + 2 = 3 | — | — |
| Thumb BX | 1 + 2 = 3 (ARMWritePC) | — | — |
| Thumb BL | first half 1, second half 1 + 2 = 4 total | 3S+1N = 4 | ✓ |
| Thumb MUL | 1 + (1–4) = 2–5 | — | ✓ (MUL is a Thumb op in ARMv4T) |
| Thumb SWI | 1 | (2S+1N = 3 in ARM state) | ✗ mGBA charges no PC penalty for Thumb SWI |
| Non-executed conditional | 1 | 1S | ✓ |

With code in ROM WS0 (`seq32 = 3`, `seq16 = 1`, `nonseq32 = 6`, `nonseq16 = 2`), the fetch base
becomes `1 + seq32[ROM] = 4` (ARM) or `1 + seq16[ROM] = 2` (Thumb), and each data access adds
`GBAMemoryStall` on ROM data (`memory.c:1779`). E.g. ROM WS0 → IWRAM word LDR:
4 (fetch) + 2 (GBALoad32 base) + 0 (IWRAM stall) + (6−3) post = **9**; ROM→ROM: 4 + 2 + 6 + 3 =
**15** — the split matches the GBATEK code/data rule.

### 4.4 Model caveats (read before building a timing model on this)

1. **16/8-bit loads/stores are under-priced** relative to the TRM (`2N` / `1S+1N+2I`): mGBA
   charges only waitstates plus the 1S fetch. For IWRAM data this means 1 cycle for LDRB — the
   TRM would say 5. If the transpiled runtime counts instructions like mGBA, budgets are
   *optimistic* for 8/16-bit-heavy code; this is the single biggest model skew.
2. **PC-in-block-transfer penalty is flat +16** in mGBA (both LDM and STM loops,
   `memory.c:1454` / `1572`), whereas the TRM adds only `1S+1N` (≈2 at zero wait).
3. **Thumb SWI** is modeled at 1 cycle (no PC penalty) — fine if the SWI handler returns
   quickly, but it diverges from the ARM-state SWI cost (3).
4. **`GBAMemoryStall`** (the name suggests stalls but it just returns the region waitstates)
   is applied to ROM/SRAM data accesses; it also folds in the waitstate-control register
   adjustments made by `GBAAdjustWaitstates` (`memory.c:1686+`).
5. mGBA's `cpu->cycles` is a *cycle counter*, not a clock simulator: it does not model
   pipeline interlocks, and the per-instruction numbers above are the complete model.

---

## 5. Common sequences (Q4)

Zero waitstates, code+data in IWRAM; mGBA model values with TRM cross-check:

| Sequence | mGBA | TRM | Notes |
|---|---|---|---|
| `LDR Rd,[Rn]` + `ADD Rd,Rd,#imm` + `STR Rd,[Rn]` | 3 + 1 + 2 = **6** | (1S+1N+1I) + 1S + 2N = 6 | ✓ identical |
| `LDMIA r0, {r1-r4}` (n=4) | 1 + 4 + 1 = **6** | 4S+1N+1I = 6 | ✓ identical |
| `LDMIA r0, {r1-r4, pc}` (n=5, ARM) | 1 + 5 + 16 + 1 = **23** | 5S+1N+1I+1S+1N = 9 | ✗ mGBA's flat +16 penalty (§4.4.2) |
| `STMIA r0, {r1-r4}` (n=4) | 1 + 4 = **5** | (4-1)S+2N = 5 | ✓ identical |
| Taken `B` (ARM, IWRAM code) | 1 + 2 = **3** | 2S+1N = 3 | ✓ |
| Taken `B` (Thumb, IWRAM code) | 1 + 2 = **3** | — | Thumb model-specific |
| Taken `BL` (Thumb, combined form) | 1 + 1 + 2 = **4** | 3S+1N = 4 | ✓ |

For code executing in ROM (the normal case), add the ROM waitstate deltas from §4.3 to each
row's fetch base: e.g. ARM `LDR+ADD+STR` in ROM WS0 with IWRAM data = 9 + 4 + 4 = 17
(fetch 4 each for the ALU/STR, LDR fetch 4 + data 2 + post 3 = 9).

---

## 6. Practical guidance for the GBAtoPy timing model

- The transpiler's per-scanline budget should count **instructions, not cycles** (current
  design: `instr_per_scanline`), which is robust to the model skews in §4.4. If a future phase
  moves to cycle-accurate scheduling, use the §4.3 table (mGBA's numbers) so that transpiled
  Python and mGBA reference runs agree, and treat TRM deltas as calibration notes.
- If cycle-level fidelity for 8/16-bit accesses is ever needed, the TRM column (§2) is the
  hardware-correct source; mGBA's lighter 16/8-bit model will then *undercount* relative to
  hardware.
- `ARMWaitstates` are runtime-configurable (waitstate control register,
  `GBAAdjustWaitstates` at `mgba/src/gba/memory.c:1686+`); a timing model keyed on
  WS0-only ROM is only valid while the ROM never changes waitstates. The per-ROM test harness
  should assert this (cheap: trace the WRITELONG to `0x03000200`).

---

## 7. Sources

mGBA (local, custom-patched tree at `/home/d.scasciafratte/gbatopy/mgba/`):
- `src/arm/isa-arm.c` — instruction handlers, `DEFINE_INSTRUCTION_ARM` (line 280),
  `ARMWritePC` (97-103), shift costs (21, 56, 91, 126), B/BL (1261-1265), BX (1498-1502),
  MRS (1513-1517), SWI (780), MUL/MLA family (1656-1665).
- `src/arm/isa-thumb.c` — `DEFINE_INSTRUCTION_THUMB` (48-51), `ThumbWritePC` (40-47),
  MUL (235), SWI/BX (232-260), offset load/store incl. LDRSB/LDRSH (280-291),
  LDMIA/STMIA (293-322), conditional B (324-330), BL second half (~278-285).
- `src/arm/arm.c` — decode loop, non-executed conditional cost (207-212).
- `include/mgba/internal/arm/isa-arm.h` — `ARM_PREFETCH_CYCLES` (13), `ARM_WAIT_MUL` (14-17).
- `src/gba/memory.c` — waitstate tables (1304-1370), `GBALoad32/16/8` (1564-1614),
  `GBAStore32/16/8` (1595-1614), `LDM_LOOP` (1450-1482), `GBALoadMultiple` (1484-1564),
  `STM_LOOP` (1568-1597), `GBAStoreMultiple` (1598-1684), `GBAAdjustWaitstates` (1686+),
  `GBAMemoryStall` (1779).

Reference documents:
- ARM7TDMI TRM, DDI 0029E (1996), "Instruction cycle timings" §4.1–4.13 — per-instruction
  ARM-state tables. (PDF via https://www.manualslib.com/manual/830846/Arm/Arm7Tdm-Core.html)
- ARM7TDMI TRM, DDI 0029G (current): §6.3 Thumb BL (Table 6-2), §6.23 Table 6-23 instruction
  speed summary (p. 171). (https://support.arm.com/documentation/ddi0029/g/...)
- GBATEK, "ARM CPU Instruction Cycle Times"
  (https://www.problemkaputt.de/gbatek-arm-cpu-instruction-cycle-times.htm) — cycle-type
  definitions, GBA waitstate context, code/data split rule, Thumb BL row.
