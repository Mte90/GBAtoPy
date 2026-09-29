# AGENTS.md — GBAtoPy Project Rules

> **Read this BEFORE making any changes.** Violating these rules wastes entire sessions.

## What Is This Project

GBAtoPy is a **transpiler** that converts GBA ROMs into standalone Python files playable with pygame.

**NOT an emulator.** The output is human-readable Python source code that, when executed, reproduces the game's behavior. The goal is a `.py` file you can open, read, and modify.

For detailed implementation status, see `docs/roadmap.md` and `docs/reference/test-roms.md`.

## Where Things Live

```
Project root:        /home/d.scasciafratte/gbatopy
Rust crates:         crates/
CLI:                 crates/gbatopy-cli/src/
Pipeline (active):   crates/gbatopy-cli/src/pipeline_cmd.rs
Codegen tree:        crates/gbatopy-cli/src/codegen/
Runtime source:      crates/gbatopy-cli/assets/gba_runtime/   (ppu.py, dma.py, memory.py, arm7tdmi.py)
Templates:           crates/gbatopy-cli/assets/templates/
Current work log:    WORKPLAN.md (todo.md superseded)
mGBA:                mgba/ (with custom patches, branch: extend-lua)
mGBA binary:         mgba/build/sdl/mgba
Scripts:             scripts/ — see scripts/README.md
Test framework:      crates/gbatopy-test/
Test config:         test-roms-config.toml
Test ROMs:           test_roms/roms/  (NOT in repo — run scripts/setup/download_test_roms.sh)
Transpiler output:   /tmp/<romname>.py  (NEVER in project dir)
```

## Companion Documents

| Document | Purpose |
|----------|---------|
| [RUNBOOK.md](RUNBOOK.md) | Build, test, verify, debug commands — copy-pasteable |
| [docs/hardware-reference.md](docs/hardware-reference.md) | CPU, display, memory map, PPU modes — single source of truth |
| [docs/runtime-architecture.md](docs/runtime-architecture.md) | PPU scanline & DMA architecture, `_map_address()` |
| [docs/how-debug.md](docs/how-debug.md) | Systematic debug workflow + known bug classes |
| [docs/codegen-pitfalls.md](docs/codegen-pitfalls.md) | 15 documented codegen bug classes |
| [docs/roadmap.md](docs/roadmap.md) | Full implementation status and strategy |
| [docs/reference/test-roms.md](docs/reference/test-roms.md) | Per-ROM pass/fail matrix |
| [WORKPLAN.md](WORKPLAN.md) | Source of truth for pending work — read at session start |

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
- Windows verified (window_midframe), mosaic implemented, blend working
- CPSR flag tracking, conditional execution, IRQ, DMA, Timers, Keypad, Sprites, BIOS SWI
- APU audio channels with pygame.mixer output

### Hardware Support (100% Coverage Required)
- All ARM/Thumb instructions (100% opcode coverage)
- PPU Mode 0, Mode 3, Mode 4 verified; Mode 1, 2, 5 implemented
- Memory regions: VRAM, Palette RAM, OAM, MMIO registers
- Memory mapping with relative address handling — see [docs/hardware-reference.md](docs/hardware-reference.md)

## Runtime Invariants (DO NOT VIOLATE)

Established after multi-session debugging. Violating reintroduces solved bugs. Full details in `docs/runtime-architecture.md` § "PPU Scanline & DMA Architecture".

1. **Fallback interpreter = pure CPU executor.** `_interp_fallback` in `pipeline_cmd.rs` executes CPU instructions only — NEVER calls `step_scanline()`. Violating causes DMA double-stepping.
2. **Main loop is instruction-counted.** PPU advances one scanline per `instr_per_scanline` CPU instructions.
3. **No step_scanline in memory reads.** `read_u16`/`read_u32`/`read_u64` must NEVER call `step_scanline()`.
4. **HBlank/VBlank DMA = full-count burst on first trigger.** `hblank_fire()` and `vblank_fire()` call `_do_transfer()`, NOT `_do_transfer_single()`.
5. **Per-scanline affine snapshots.** `step_scanline(capture_snapshot=True)` captures BG2PA/PB/PC/PD/X/Y BEFORE DMA fires. Fallback interpreter calls `step_scanline(capture_snapshot=False)`.
6. **All memory regions must be zero-initialized at construction.** `memory.py` must use `[0] * SIZE` for VRAM, Palette RAM, OAM, IWRAM, EWRAM. Debug patterns like `[(i%256) for i in range(SIZE)]` left in production cause uninitialized tiles to decode to non-zero palette indices → black screens.
7. **All instruction/SWI dispatch tables must be single-source.** Two SWI dispatchers existed (cpu.py:_arm_swi with 4 handlers, arm7tdmi.py:swi_handler with 24). The fast-path CPU silently dropped CpuSet/CpuFastSet. There must be ONE dispatch table for SWI instructions, shared by both the fast-path and fallback interpreters.
8. **PPU `forced_blank` must track DISPCNT bit 7 live.** `ppu.py` maintains `self.forced_blank` as the authoritative field; code that reads `self.dispcnt & 0x0080` uses a stale cached value (initialized to 0x0480 at line 519, never updated). This caused a GLOBAL white-screen regression — every ROM rendered blank. All forced-blank checks must read `self.forced_blank`, not `self.dispcnt`.

## Non-Negotiable Rules

## Non-Negotiable Rules

### Workflow
1. **Read `WORKPLAN.md` first** at session start — it is the source of truth for pending work. Reconcile against `docs/reference/test-roms.md` and the live codebase.
2. **Read `docs/roadmap.md`** for full status and strategy.
3. **Read `docs/how-debug.md`** for systematic debug workflow + known bug classes.
4. **One ROM at a time for fixing** — parallel root-cause *investigation* across multiple ROMs is allowed and encouraged (dispatch multiple @explorer in parallel). But apply fixes sequentially, one ROM at a time, verifying each before moving to the next. Never run the full 76-ROM suite during active debugging. Use `python3 scripts/run_tests.py --level 3 --rom <name>`.

### Verification
5. **Test with pixels** — "no crash" is not enough. Verify screenshot content against mGBA golden via `compare_screenshots.py`. See [RUNBOOK.md](RUNBOOK.md).
6. **Re-test all previously-passing ROMs after codegen/dispatch changes** — a fix that targets one ROM can regress others. The peephole `+4` fix for Thumb loops regressed start-delay from 1.75% PASS to 100% blank. After any change to shared dispatch, peephole optimizer, or codegen headers, run `python3 scripts/run_tests.py --level 3` on the last known-passing set before declaring done.
7. **One-shot verification** — `./scripts/verify/verify_rom.sh <rom> --no-golden` transpiles, runs, compares in one step.
8. **Verify subagent claims** — always check their work manually.

### Output Discipline
9. **Transpiled Python output goes to `/tmp/`** — NEVER inside the project directory. Project holds only source, templates, scripts, docs.
10. **Never modify .gba ROM files** — patch Python output first to verify, then fix Rust codegen permanently.
11. **No type error suppression** — never `as any`, `@ts-ignore`, or equivalent.
12. **Naming convention** — transpiled output uses ROM base name (`stripes.gba` → `stripes.py`).

### Debugging
13. **Debug workflow** — modify generated Python first to verify a fix, then apply to Rust codegen.
14. **Use built-in debug flags** — `--pc-trace=FILE`, `--trace-n=N`, `--max-instrs=N`. Do not inject `print(f"PC={...}")`. See [RUNBOOK.md](RUNBOOK.md) and `docs/how-debug.md`.
15. **Goldens must be validated before comparison** — a golden screenshot <1KB (typically 33 bytes) is a segfault artifact from mGBA, not a real golden. Always check `ls -la` on golden PNGs before running compare_screenshots.py. Correct mGBA headless setup: `export SDL_VIDEODRIVER=offscreen` + `export SDL_AUDIODRIVER=dummy` + `export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:$LD_LIBRARY_PATH"`. Do NOT use `SDL_VIDEODRIVER=dummy` (causes 33-byte segfault artifacts). Do NOT use `xvfb-run` alone (produces >1KB but all-black blank goldens). `SDL_VIDEODRIVER=offscreen` is the only proven working backend for mGBA screenshot generation on a headless server.
16. **Golden screenshots must be validated as >1KB before comparison** — a golden <1KB is a segfault artifact, not a real reference image. Comparing transpiled output against a broken golden produces meaningless results. Always `ls -la` the golden first.
17. **Debug probes must flush** — `print(..., flush=True)` BEFORE any `os._exit(0)`; the runtime exits hard, bypassing buffer flush.
18. **Never add step_scanline to memory reads** — see invariant #3. PPU stepping is exclusively in the main loop.
19. **Fallback interpreter is pure CPU** — see invariant #1.
20. **Check known bug classes first** — consult "Known Codegen Bug Classes" (5), "Known Runtime Bug Classes" (2), and "New Bug Classes" (3: SWI dispatch truncation, memory non-zero init, IRQ vector missing) in `docs/how-debug.md` before deep debugging. Run `python3 -m pytest crates/gbatopy-cli/assets/gba_runtime/tests/test_dispatch_audit.py` first.
21. **Check dispatch table completeness** — NOP block bug may skip initialization code.
22. **Verify STRH/LDRH offsets** — disassembler may use wrong bit field (bits 7-3 vs bits 3-0).
22a. **Verify explorer code-pattern claims by reading the cited line** — an explorer hallucinated a NOP-detection mask `(opcode & 0xFF000000) == 0xEA000000` at emitter_arm.rs:609; grep found no such pattern. Before acting on any subagent's claim about a code pattern, read the cited file:line with `read` or `aft_zoom` and confirm the pattern exists as described.

### Work Management
23. **Autonomous todo creation** — when you discover work (new bug, stale doc, missing test, done WORKPLAN item, regression risk, flagged follow-up), IMMEDIATELY create a `todowrite` entry. Review at every work boundary and prune irrelevant items.
24. **WORKPLAN.md is comprehensive** — must cover ALL pending work, not just ROM fixes: undocumented code fixes, architecture debt, doc staleness, feature gaps, verification gaps, performance issues. Every gap gets a `F<N>` entry before session end.
25. **Doc-sync rule** — any codegen/runtime fix that changes a ROM's pass/fail status MUST update `docs/reference/test-roms.md` in the same task. Summary counts, per-ROM rows, feature matrix, compatibility matrix must all reflect new state.
26. **Deduplicate before fixing** — if a bug is in duplicated code (two `_deliver_irq` functions, two main loops), deduplicate FIRST, then fix the single remaining copy. Check with `grep -c` before any multi-site fix.

26a. **One code fix at a time on shared code** — when applying fixes to shared code (PPU rendering, CFG builder, codegen dispatch, memory subsystem, DMA), apply ONE fix, build, and run a canary regression test BEFORE applying the next fix. Never batch multiple shared-code fixes in one commit. If a regression appears, you must be able to isolate it to a single change. The F171 regression (pong/combo/start-delay) was caused by applying OAM bit position + palette rejection + determinism fixes simultaneously — isolation took 3 sessions instead of 1 git revert.

### Autonomous Continuation
27. **Work discovery loop** — when the todo list is empty, do NOT stop and do NOT ask the user what to do next. Instead, discover more work by following this loop:
  1. Read `WORKPLAN.md` — find the next pending phase or task. Every `F<N>` entry is actionable work.
  2. Read `docs/reference/test-roms.md` — find any ROM marked FAIL or SKIP. Each one is a task.
  3. Run `python3 scripts/run_tests.py --level 3 --rom <name>` on a failing ROM to reproduce the issue.
  4. Check `docs/roadmap.md` for unverified features, missing modes, or architecture debt.
  5. Run `python3 -m pytest crates/gbatopy-cli/assets/gba_runtime/tests/` to find failing runtime tests.
  6. Audit `docs/how-debug.md` "Known Bug Classes" — each unresolved class is a task.
  7. Grep for `TODO`, `FIXME`, `unimplemented`, `stub`, `pass  #` in `crates/` and `crates/gbatopy-cli/assets/gba_runtime/` — each hit is a task.
  8. If still no work found, run the full 76-ROM regression suite (`python3 scripts/run_tests.py --level 3`) and investigate every FAIL/SKIP.
  Create a `todowrite` entry for each discovered gap, then resume execution. The session only ends when steps 1-8 yield zero new work.

28. **Keep at least 3 pending todos** — at any work boundary, if fewer than 3 pending todos remain, run the work discovery loop (27) before continuing. Always have a visible backlog of upcoming work.

### Context Management (Avoid Compaction Death Spirals)

29. **DELEGATE ALL EXECUTION** — orchestrator NEVER runs: `cargo build`, `gbatopy transpile`, `python3 <rom>.py`, `python3 -m pytest`, or any command producing >2KB output. These ALWAYS go to a fixer/explorer subagent. Orchestrator only runs: `git status`/`diff`/`log`, `ls`, `wc -l`, `grep -c`, `head -5`, `tail -5`, and context tools (`ctx_reduce`/`ctx_memory`/`todowrite`/`aft_safety`). If you need a build or transpile result, dispatch a subagent and read only the final summary via `task_result`. Violating this rule is the #1 cause of compaction death spirals.

30. **DROP AFTER EVERY EXTRACT** — after extracting info from any tool output, immediately call `ctx_reduce`. Pattern: read → extract → drop → act. Never: read → read → read → act → drop at end. After every 5th consecutive tool call, stop and drop all spent outputs before the next call.

31. **ONE-DROP RULE** — if ANY tool output is dropped/compacted even once, STOP. Do NOT retry the same call. Delegate all subsequent build/verify/diagnose work to a fresh subagent. One drop = death spiral already started. Subagent results survive compaction better than bash output.

32. **MEMORY UNDER 40** — deduplicate/merge/archive project memory at every work boundary (todo completion, session start, phase transition). Scan for: (1) duplicates → merge, (2) contradictions → resolve and archive one, (3) stale entries → archive. Known contradictions: #47 vs #51 (`max_inner_stalls` 10 vs 10000), #50 vs #61 (bgpd "never DMA" vs "can enable DMA"), #22 vs #23 (duplicate affine BG2 write dispatch), #30/#69/#70/#73/#75 (five entries all saying "snapshot before DMA" — merge to one). Every memory entry costs ~100 bytes on every turn — 80 entries = 8KB of permanent overhead.

33. **SUBAGENT HANDOFF** — subagents stop at ~70% context, write a summary of progress to `/tmp/<task-name>-handoff.txt` (what was done, what remains, files modified with line numbers, exact next step), and return it as their final message. Orchestrator launches a fresh subagent with the handoff as starting context. Never let a subagent run until its context is fully saturated.

### Parallelization
34. **Always use subagents** — GBA-specific routing:
  - Codebase recon → `@explorer` | External docs → `@librarian` | Architecture → `@oracle`
  - Bounded implementation → `@fixer` | Image analysis → `@observer` | Git/lint/test → `@fast-generic`
  - Track task IDs, reconcile on return, never block on a subagent.

### ROM Failure Policy
35. **ZERO-SKIP policy** — every ROM must PASS or FAIL, never SKIP. SKIP is forbidden. When a ROM would be skipped (timeout, OOM, missing golden), treat as FAIL and dispatch a subagent to root-cause and fix it.
36. **Timeout analysis is mandatory** — when a ROM times out, do NOT mark SKIP or move on. Dispatch a parallel `@explorer` with `--pc-trace=FILE --trace-n=N` to capture the hang point, identify the loop address, decode surrounding instructions, report root cause + proposed fix. Common root causes: (a) missing IRQ delivery, (b) SIO/serial poll with no clock, (c) audio subsystem waiting on FIFO space, (d) infinite reset loop. File a todo before moving on.
37. **Every FAIL/SKIP ROM gets a subagent** — do not batch-debug serially. Each failing ROM gets one `@explorer` in parallel. Each returns: (1) hang/spin address, (2) root cause category from `docs/how-debug.md`, (3) proposed fix with exact file + line, (4) verification command.

### Script Discipline
38. **Script placement** — generic reusable scripts go in `scripts/` and MUST be documented in `scripts/README.md`. Ad-hoc, one-off, or debug scripts go in `/tmp/`. Never create temporary scripts in the project root or `scripts/` without adding them to the README.

## Zero Tolerance for Stubs

Applies to **generated Python output** and **runtime templates** in `crates/gbatopy-cli/assets/gba_runtime/` and `templates/`. See global §30.1 for the full rule. Markers: `pass`, `return 0`, `return None`, `NotImplementedError`, `TODO:`, empty bodies, `print()`-only functions.

## Ghidra Static Analysis Oracle

Ghidra 12.1.4 is installed at `/opt/ghidra/ghidra_12.1.4_PUBLIC` and used as a **static analysis oracle** — ground truth for cross-validating the transpiler's static analysis (function discovery, basic-block boundaries, instruction decode).

### When to Use Ghidra

| Scenario | Command | Purpose |
|----------|---------|---------|
| Function discovery cross-check | `scripts/ghidra/ghidra_functions.sh <rom>` | Import ROM and compare Ghidra's symbol table vs our dispatch table — every missing function is a CFG bug |
| Instruction decode oracle | `scripts/ghidra/ghidra_decode.sh <rom> <addr>` | When debugging a bit-field extraction bug, compare our decode vs Ghidra's disassembly |
| Basic block cross-check | `scripts/ghidra/ghidra_blocks.sh <rom>` | Diff basic-block boundaries — catches fall-through and cross-mode bugs |
| Timeout/hang root cause | `scripts/ghidra/ghidra_decompile.sh <rom> <addr>` | Decompile the hang loop to understand what the ROM is waiting on |

### Ghidra Helper Scripts

All scripts in `scripts/ghidra/`:
- `ghidra_functions.sh <rom>` — imports ROM and provides instructions for symbol table extraction
- `ghidra_decode.sh <rom> <addr>` — provides guidance for disassembling at an address
- `ghidra_blocks.sh <rom>` — provides guidance for basic block analysis
- `ghidra_decompile.sh <rom> <addr>` — provides guidance for decompiling a function

See `scripts/ghidra/README.md` for detailed usage.

### GBA Processor Configuration

GBA uses ARM7TDMI (ARMv4T, big-endian byte order for ROM):
- **Processor:** `ARM:BE:32:v4t`
- **Base address:** `0x08000000`
- **Entry point:** `0x08000000`
- The GBA has mixed ARM/Thumb code — Ghidra tracks mode per function, which is exactly the cross-mode validation we need

### Cross-Validation Workflow

When debugging a static analysis bug (missing function, wrong basic block, instruction decode error):

1. **Import ROM with Ghidra:**
   ```bash
   ./scripts/ghidra/ghidra_functions.sh <rom_name>
   ```

2. **Open in Ghidra GUI:**
   ```bash
   ghidraRun
   # Open project at /tmp/ghidra-projects/gbatopy
   ```

3. **Compare Symbol Table vs transpiler's dispatch table:**
   - Ghidra: View > Symbol Table
   - Transpiler: `gbatopy transpile <rom> --print-dispatch 2>/dev/null | grep '^FUNC'`
   - Every symbol in Ghidra but not in ours is a missing function = CFG bug
   - Every symbol in ours but not in Ghidra's is a false positive = heuristic over-reach

4. **For instruction decode bugs:**
   - Navigate to address in Ghidra GUI
   - Compare Ghidra's disassembly with transpiler output
   - Identify bit-field extraction errors

This replaces manual disassembly and guesswork with ground-truth comparison.

### Installation

Ghidra is installed at `$GHIDRA_HOME/ghidra_12.1.4_PUBLIC` (or `/opt/ghidra` by default). Requires JDK 21+. The `analyzeHeadless` binary is at `$GHIDRA_HOME/ghidra_12.1.4_PUBLIC/support/analyzeHeadless`.

**Test verification:**
```bash
"${GHIDRA_HOME:-/opt/ghidra}"/ghidra_12.1.4_PUBLIC/support/analyzeHeadless /tmp/test testProj \
  -import "${PROJECT_ROOT:-$(pwd)}/test_roms/roms/hello.gba" \
  -processor ARM:BE:32:v4t \
  2>&1 | grep -E "Total Time|Analysis succeeded"
```

Expected output: `Total Time   1 secs` and `Analysis succeeded`.

**To reinstall:**
```bash
cd /tmp
wget https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/Ghidra_12.1.4_PUBLIC_20250205.zip
unzip Ghidra_12.1.4_PUBLIC_20250205.zip -d /opt/
ln -sf /opt/ghidra_12.1.4_PUBLIC /opt/ghidra
```

### Limitations

Ghidra's headless mode in version 12.1.4 has limited scripting support (PyGhidra/Jython not available). For full automation:
- Use the Ghidra GUI interactively
- Or port scripts to Java
- Or use alternative tools like `arm-none-eabi-objdump` for simple disassembly
