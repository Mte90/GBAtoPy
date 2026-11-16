# IRQ Entry Latency and Instruction Timing

Research for T3.1. Answers the four questions needed to model real-hardware IRQ
latency against the transpiler's **instruction-counted** main loop. Read-only
research; no code changes.

Citation key:
- **TRM** = ARM7TDMI Technical Reference Manual, Revision 3 (DDI0029G). Sections
  cited: *Interrupt request* (2.8.5), *Software interrupt and exception entry*,
  *Exception vectors* (Table 2-4), *Maximum interrupt latencies* (2.9.1),
  *Minimum interrupt latencies* (2.9.2).
- **GBATEK** = https://problemkaputt.de/gbatek.htm (local copy at `/tmp/gbatek.htm`).
  Sections cited: *ARM CPU Instruction Cycle Times* (`#armcpuinstructioncycletimes`),
  *LCD Dimensions and Timings* (`#lcddimensionsandtimings`).
- **mGBA** = local source at `mgba/`. Every mGBA claim is cited as `file:line`.

---

## Q1 — IRQ entry latency on real ARM7TDMI hardware

**Short answer: minimum 5 CPU cycles from IRQ assertion to the first handler
instruction, but the interrupt is only sampled at the end of an instruction, so
real-world latency is "end of current instruction + 5 cycles".**

The TRM gives an explicit minimum and a worst case:

- **Minimum latency = 5 cycles.** TRM §2.9.2 *Minimum interrupt latencies*:
  > "The minimum latency for FIQ or IRQ is the shortest time the request can take
  > through the synchronizer, Tsyncmin, plus Tfiq, a total of **five processor
  > cycles**."
- **Sampling point.** TRM §2.8.5 *Interrupt request*:
  > "the ARM7TDMI processor **checks for a LOW level on the output of the IRQ
  > synchronizer at the end of each instruction**."
  So an IRQ asserted mid-instruction cannot be taken until that instruction
  finishes; the 5-cycle entry then begins.
- **Worst case.** TRM §2.9.1 *Maximum interrupt latencies*: the FIQ worst case is
  Tsyncmax (4) + Tldm (20, an LDM that loads the PC) + Texc (3) + Tfiq (2) =
  **29 cycles**. The IRQ worst case is the same calculation, except a
  higher-priority FIQ can delay IRQ entry for an arbitrary time.
- **Entry mechanics (3 cycles).** TRM *Software interrupt and exception entry* /
  Table 6.15: forcing the PC to the vector takes 3 cycles — (1) build the forced
  address, change mode, save return address to R14 and CPSR to SPSR; (2) modify
  the return address; (3) refill the instruction pipeline.
- **Vector address.** TRM Table 2-4 *Exception vectors*: `0x00000018` = IRQ,
  entered in IRQ mode with the I flag **set**. (This is the GBA's `BASE_IRQ`.)

**Implication for our lazy model.** Our transpiler defers restoring
CPSR/mode/R0-R3/R12 until scanline boundaries. The hardware's *floor* is 5
cycles (≈ 5/1232 ≈ 0.4% of one scanline), so a scanline-boundary deferral is a
coarse approximation that is fine for frame-level synchronization but cannot
represent sub-scanline IRQ timing (e.g. HBlank-triggered DMA mid-line).

---

## Q2 — How mGBA models IRQ latency

**Yes — mGBA adds a fixed 7-cycle delay for IRQ entry, measured in the same
cycle domain as instruction costs. mGBA is a cycle-counted model.**

The full path, with line numbers:

1. **Detection.** `GBATestIRQ(gba, cyclesLate)` is called from three places:
   - Register writes to `IE`/`IF`/`IME` → `GBATestIRQ(gba, 1)`
     (`mgba/src/gba/io.c:516`, `io.c:521`, `io.c:525`).
   - Every CPSR read, via the hook `irqh->readCPSR = GBATestIRQNoDelay`
     (`mgba/src/gba/gba.c:228`), which calls `GBATestIRQ(gba, 0)`
     (`gba.c:589-592`). This is the "end-of-instruction" re-check, matching the
     TRM's end-of-instruction sampling.
   - Hardware sources (VBlank/HBlank, keypad, gamepak) set the IF bit via
     `GBARaiseIRQ` (`gba.c:584-587`), which also calls `GBATestIRQ`.
2. **Scheduling.** `GBATestIRQ` (`gba.c:594-600`): if `IE & IF` is non-zero and
   no IRQ event is already scheduled, it schedules the `irqEvent` at
   **`GBA_IRQ_DELAY - cyclesLate`** cycles in the future (`gba.c:597`).
   `#define GBA_IRQ_DELAY 7` (`gba.c:28`). So the delay is a **fixed 7 cycles**
   from detection.
3. **Firing.** After the delay elapses, `_triggerIRQ` (`gba.c:1038-1050`)
   re-checks `IE & IF`, and if `IME` is set and `cpsr.i` is clear, calls
   `ARMRaiseIRQ` (`gba.c:1048`).
4. **Entry.** `ARMRaiseIRQ` (`mgba/src/arm/arm.c:124-144`): switches to
   `MODE_IRQ`, sets `LR = PC - width + 4` (`arm.c:137`), sets `PC = BASE_IRQ`
   (`arm.c:138`; `BASE_IRQ = 0x00000018` at `arm.h:47`), charges
   `ARMWritePC(cpu)` cycles (`arm.c:140`), saves `cpsr→spsr` and sets
   `cpsr.i = 1` (`arm.c:142`).

**Model comparison.** mGBA counts **cycles**: every instruction adds its real
cycle cost to `cpu->cycles` (`DEFINE_INSTRUCTION_ARM`, `mgba/src/arm/isa-arm.c:278-283`
— `currentCycles = ARM_PREFETCH_CYCLES` plus memory-access and PC-write costs),
and `ARMRunLoop` executes instructions until `cpu->cycles >= cpu->nextEvent`,
where timing events (IRQ, DMA, VBlank) fire (`arm.c:243-254`). The 7-cycle IRQ
delay lives in that same cycle domain. Our transpiler instead counts
**instructions** (each instruction = 1, PPU advances every `instr_per_scanline`
instructions) — a different timing model that only agrees with mGBA when every
instruction costs exactly 1 cycle (see Q3/Q4).

**Accuracy note.** mGBA's fixed 7-cycle delay is a simplification of the
hardware's 5-cycle minimum (slightly more conservative) and does not model the
29-cycle worst case or the 3-cycle pipeline refill as separate phases — it just
forces the PC and charges the PC-write cost.

---

## Q3 — Per-instruction cycle cost (ARM7TDMI)

GBATEK *ARM CPU Instruction Cycle Times* (the ARM7TDMI table):

| Instruction | Cycles | Additional |
|---|---|---|
| ALU | `1S` | `+1S+1N` if R15 loaded, `+1I` if SHIFT(Rs) |
| LDR | `1S+1N+1I` | `+1S+1N` if R15 loaded |
| STR | `2N` | — |
| LDM | `nS+1N+1I` | `+1S+1N` if R15 loaded |
| STM | `(n-1)S+2N` | — |
| B, BL | `2S+1N` | — |
| SWI, trap | `2S+1N` | — |
| `{cond}` false | `1S` | — |

Legend (GBATEK, immediately after the table):
- **N** — non-sequential ("1st access") cycle = **1 clock + non-sequential waitstates**
- **S** — sequential ("2nd access") cycle = **1 clock + sequential waitstates**
- **I** — internal cycle = **1 clock, no waitstates**

The task prompt's shorthand ("LDR/STR = 1S+N, ADD = 1S, B = 2S+N, STM/LDM") is
close; the exact GBATEK rows are `LDR = 1S+1N+1I`, `STR = 2N`, `B = 2S+1N`,
`LDM = nS+1N+1I`, `STM = (n-1)S+2N`, `ALU = 1S`.

**Effective cost on the GBA depends on where the code lives** (waitstates):

- **Code in IWRAM/EWRAM (0 waitstates):** `1S = 1N = 1I = 1` cycle.
  - ALU (ADD/SUB/AND/...) = **1 cycle**
  - LDR = 1S+1N+1I = **3 cycles**
  - STR = 2N = **2 cycles**
  - LDM (n words) = **n+2**
  - STM (n words) = **n+1**
  - B/BL = 2S+1N = **3 cycles**
- **Code in ROM (16-bit bus, waitstates apply):** the `S`/`N` components include
  ROM waitstates (default bank N=4, S=2; N=3, S=1 with prefetch via WAITCNT), so
  every memory instruction and every instruction *fetch* costs several extra
  cycles. (GBATEK *Memory Areas and Bank Select* / WAITCNT.)

**Mapping to our instruction-counted model (1 instruction = 1 cycle).**
Our model counts each instruction as 1 and advances one scanline per
`instr_per_scanline` instructions. That is exact **only** for pure-ALU code in
zero-waitstate RAM (ALU = 1 cycle). For any code with memory operations, real
instructions cost 2–3+ cycles (in RAM) or more (in ROM), so the 1:1 model
**under-counts elapsed cycles** — i.e. it assumes the CPU executes more
instructions per scanline than real hardware does. To model real timing you must
weight each instruction by its GBATEK cycle cost, which is precisely what mGBA
does with its cycle-counted loop.

---

## Q4 — Scanline budget on real hardware

**Clock.** GBATEK *System Clock*: "The system clock is 16.78 MHz (16*1024*1024
Hz), one cycle is thus approx. 59.59 ns." → **16,777,216 Hz**.

**Per scanline** (GBATEK *LCD Dimensions and Timings*, *Horizontal Dimensions*;
1 dot = 4 CPU cycles):

| Phase | Dots | Cycles | % |
|---|---|---|---|
| Visible | 240 | 960 | 78% |
| H-Blanking | 68 | 272 | 22% |
| **Total** | 308 | **1232** | ≈13.620 kHz |

**Per frame** (GBATEK *Vertical Dimensions*): 228 lines (160 visible + 68
V-Blank) = **280,896 cycles** ≈ 59.737 Hz. Note `280896 / 228 = 1232` — the
per-line figure is self-consistent.

**How many instructions fit in one scanline?** It depends on the instruction
mix; at 1232 cycles/scanline:
- All-ALU code (1 cycle each) → **1232 instructions**.
- Memory-heavy code (LDR=3, STR=2, B=3 in RAM) → **fewer** (a ~1.7-cycle average
  → ~720 instructions).

**Our current setting vs real hardware.**

```python
# crates/gbatopy-cli/assets/templates/game_loop.py:17
gba_hz = 16789800  # GBA clock speed (16.79 MHz)
# crates/gbatopy-cli/assets/templates/game_loop.py:454
instr_per_scanline = max(50, int(gba_hz / 60.0) // 228)
```

- `16789800 / 60 = 279830`; `279830 // 228 = **1227**` → our
  `instr_per_scanline = 1227`.
- Our `gba_hz` (16,789,800 Hz) is slightly above GBATEK's 16,777,216 Hz (16 MiHz).
- Our budget of **1227 instructions ≈ 1232 cycles/scanline**, i.e. the model
  treats 1 instruction ≈ 1 cycle and uses a ~1232-cycle scanline. So our
  "instruction budget" is numerically equal to the real "cycle budget."
- **Consequence:** our fixed 1227-instruction budget matches real hardware only
  in the all-ALU case. Real hardware executes ≤1232 instructions in a 1232-cycle
  scanline (fewer for memory-heavy code), so for code with many LDR/STR the
  transpiled program advances a scanline slightly *early* relative to real
  hardware. For frame-level (VBlank) synchronization this is within noise; for
  HBlank/mid-line DMA timing it is a systematic drift.

---

## Bottom line for the timing model

- **IRQ entry:** hardware floor is 5 cycles, sampled at instruction boundaries,
  worst case 29 cycles (TRM). mGBA approximates this with a fixed **7-cycle**
  delay from an instruction-boundary detection point, in a cycle-counted
  domain. Our lazy scanline-boundary restore is a coarser, frame-level
  approximation — acceptable for VBlank sync, not for sub-scanline timing.
- **Instruction cost:** 1 instruction = 1 cycle is exact only for ALU code in
  zero-waitstate RAM; memory instructions cost 2–3+ cycles (RAM) or more (ROM).
  Our instruction-counted model therefore over-estimates instructions-per-scanline
  for memory-heavy code.
- **Scanline budget:** real = 1232 cycles/line (16.78 MHz, 228 lines/frame);
  ours = 1227 instructions/line. The two coincide only under the 1:1 assumption.
