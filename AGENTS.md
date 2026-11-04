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
mGBA:                mgba/ (custom patches in mgba-custom-patches.diff, not a git repo)
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
| [docs/apu-architecture.md](docs/apu-architecture.md) | APU channels, registers, mixer, threading, codegen integration |
| [docs/how-debug.md](docs/how-debug.md) | Systematic debug workflow + known bug classes |
| [docs/codegen-pitfalls.md](docs/codegen-pitfalls.md) | Documented codegen bug classes (see file for count) |
| [docs/roadmap.md](docs/roadmap.md) | Full implementation status and strategy |
| [docs/reference/test-roms.md](docs/reference/test-roms.md) | Per-ROM pass/fail matrix |
| [WORKPLAN.md](WORKPLAN.md) | Source of truth for pending work — read at session start |
| [docs/ghidra-reference.md](docs/ghidra-reference.md) | Ghidra static analysis oracle — cross-validation workflow |

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
   **Codegen:** the fallback interpreter budget for IWRAM code must NOT exceed `instr_per_scanline` — a large budget (e.g., 100000) blocks VBlank IRQ delivery by running too long without returning to the main loop.
2. **Main loop is instruction-counted.** PPU advances one scanline per `instr_per_scanline` CPU instructions.
   **Codegen:** the dispatch loop template must use the same per-scanline budget for IWRAM code as for ROM code. No special-casing IWRAM with a larger budget.
3. **No step_scanline in memory reads.** `read_u16`/`read_u32`/`read_u64` must NEVER call `step_scanline()`.
4. **HBlank/VBlank DMA = full-count burst on first trigger.** `hblank_fire()` and `vblank_fire()` call `_do_transfer()`, NOT `_do_transfer_single()`.
5. **Per-scanline affine snapshots.** `step_scanline(capture_snapshot=True)` captures BG2PA/PB/PC/PD/X/Y BEFORE DMA fires. Fallback interpreter calls `step_scanline(capture_snapshot=False)`.
6. **All memory regions must be zero-initialized at construction.** `memory.py` must use `[0] * SIZE` for VRAM, Palette RAM, OAM, IWRAM, EWRAM. Debug patterns like `[(i%256) for i in range(SIZE)]` left in production cause uninitialized tiles to decode to non-zero palette indices → black screens.
   **Codegen:** must NOT emit pre-loading code that writes ROM-extracted data into VRAM/palette at init. The asset extractor's `is_valid_4bpp_tile` heuristic is too loose (accepts ARM code as tiles) — do not trust it. VRAM/palette start zeroed on real hardware.
7. **All instruction/SWI dispatch tables must be single-source.** Two SWI dispatchers existed (cpu.py:_arm_swi with 4 handlers, arm7tdmi.py:swi_handler with 24). The fast-path CPU silently dropped CpuSet/CpuFastSet. There must be ONE dispatch table for SWI instructions, shared by both the fast-path and fallback interpreters.
8. **PPU `forced_blank` must track DISPCNT bit 7 live.** `ppu.py` maintains `self.forced_blank` as the authoritative field; code that reads `self.dispcnt & 0x0080` uses a stale cached value (initialized to 0x0480 and never updated). This caused a GLOBAL white-screen regression — every ROM rendered blank. All forced-blank checks must read `self.forced_blank`, not `self.dispcnt`.

## Non-Negotiable Rules

### Workflow
1. **Read `WORKPLAN.md` first** at session start — it is the source of truth for pending work. Reconcile against `docs/reference/test-roms.md` and the live codebase.
2. **Read `docs/roadmap.md`** for full status and strategy.
3. **Read `docs/how-debug.md`** for systematic debug workflow + known bug classes.
4. **One ROM at a time for fixing** — parallel root-cause *investigation* across multiple ROMs is allowed and encouraged (dispatch multiple @explorer in parallel). But apply fixes sequentially, one ROM at a time, verifying each before moving to the next. Never run the full 91-ROM suite during active debugging. Use `python3 scripts/run_tests.py --level 3 --rom <name>`.
4a. **Codegen proceeds autonomously** — no user approval gate needed for codegen changes. Apply fix → build → canary regression (one ROM) → full L3 suite → commit. Do not stall waiting for an OK on codegen work.
4b. **No ad-hoc code for a single ROM** — never special-case codegen to make one ROM pass without fixing the root cause. No stubs, no `if rom_name == X` workarounds, no hardcoded values tuned to one ROM's golden screenshot. A fix must address the structural bug so all affected ROMs benefit. If a fix only works for one ROM, it is a hack — find the real cause.

### Verification
5. **Test with pixels, specify level** — "no crash" is not enough. Verify screenshot content against mGBA golden via `compare_screenshots.py`. Every PASS claim MUST specify verification level: L1 (smoke/syntax), L2 (execution), L3 (visual comparison). "PASS" without a level is meaningless. See [RUNBOOK.md](RUNBOOK.md).
6. **Re-test all previously-passing ROMs after codegen/dispatch changes** — a fix that targets one ROM can regress others. The peephole `+4` fix for Thumb loops regressed start-delay from 1.75% PASS to 100% blank. After any change to shared dispatch, peephole optimizer, or codegen headers, run `python3 scripts/run_tests.py --level 3` on the last known-passing set before declaring done.
7. **One-shot verification** — `./scripts/verify/verify_rom.sh <rom> --no-golden` transpiles, runs, compares in one step.
8. **Verify subagent claims** — always check their work manually.
8a. **Commit messages for codegen/runtime fixes must include verification evidence** — a commit that claims "X now works" must show the exact command and output that proves it. Format: `Verified: <command> → <result>`. Example: `Verified: python3 /tmp/pong.py --headless --screenshot /tmp/pong.png → 2424 bytes, 44.79% diff`. A commit without evidence is an unverified claim — do not trust it, re-verify before building on it.
8b. **PASS status expires and must cite evidence** — a ROM marked PASS in `docs/reference/test-roms.md` is only valid if verified with the current binary. (1) After any fix to shared code (dispatch, PPU, DMA, memory, codegen, IRQ handling), run the full 91-ROM L3 sweep (`python3 scripts/run_tests.py --level 3 --parallel 4`) before declaring the session's work done — a canary on one ROM is necessary but not sufficient. (2) Even with no shared-code change, re-run the full sweep if the last one was more than 5 sessions ago; document the last sweep date in the test-roms.md header. (3) Each PASS row must cite the last verification date or commit hash; a PASS with no recent evidence is INCONCLUSIVE.
8c. **Verify subagent code-pattern claims by reading the cited line** — before acting on any subagent's claim about a code pattern, read the cited file:line with `read` or `aft_zoom` and confirm the pattern exists as described. (Explorers have hallucinated code patterns that don't exist at the cited locations.)
8d. **ROM regression testing MUST use the test script** — never run manual transpile+execute with custom `--max-instrs`/`--timeout` for regression testing. The script `scripts/run_tests.py --level 3 --rom <name>` has correct parameters baked in (10M instructions, 90s timeout, correct golden paths at `test-reports/goldens/`). Subagents fabricating pixel-diff results with wrong parameters (e.g., 210K instructions instead of 10M) is a recurring failure mode. Goldens are at `test-reports/goldens/golden_{rom_base}_frame_{N}.png` (typically frame 60), NOT `test_roms/goldens/`.

### Output Discipline
9. **Transpiled Python output goes to `/tmp/`** — NEVER inside the project directory. Project holds only source, templates, scripts, docs.
10. **Never modify .gba ROM files** — patch Python output first to verify, then fix Rust codegen permanently.
11. **No type error suppression** — never `as any`, `@ts-ignore`, or equivalent.
12. **Naming convention** — transpiled output uses ROM base name (`stripes.gba` → `stripes.py`).

### Debugging
13. **Debug workflow** — modify generated Python first to verify a fix, then apply to Rust codegen.
14. **Use built-in debug flags** — `--pc-trace=FILE`, `--trace-n=N`, `--max-instrs=N`. Do not inject `print(f"PC={...}")`. See [RUNBOOK.md](RUNBOOK.md) and `docs/how-debug.md`.
15. **Goldens must be validated before comparison** — a golden screenshot <200B (typically 33 bytes) is a segfault artifact from mGBA, not a real golden. Always check `ls -la` on golden PNGs before running compare_screenshots.py. Correct mGBA headless setup: `export SDL_VIDEODRIVER=offscreen` + `export SDL_AUDIODRIVER=dummy` + `export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:$LD_LIBRARY_PATH"`. Do NOT use `SDL_VIDEODRIVER=dummy` (causes 33-byte segfault artifacts). Do NOT use `xvfb-run` alone (produces >200B but all-black blank goldens). `SDL_VIDEODRIVER=offscreen` is the only proven working backend for mGBA screenshot generation on a headless server.
17. **Debug probes must flush** — `print(..., flush=True)` BEFORE any `os._exit(0)`; the runtime exits hard, bypassing buffer flush.
20. **Check known bug classes first** — consult the known bug classes in `docs/how-debug.md` (codegen, runtime, and Thumb-disassembler/codegen-mismatch classes). Run `python3 -m pytest crates/gbatopy-cli/assets/gba_runtime/tests/test_dispatch_audit.py` first.
21. **Check dispatch table completeness** — NOP block bug may skip initialization code.
22. **Verify STRH/LDRH offsets** — disassembler may use wrong bit field (bits 7-3 vs bits 3-0).

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
  8. Count codegen stubs: transpile a failing ROM and grep stderr for "unhandled" — every stub line is an instruction the codegen can't handle. `gbatopy transpile <rom> --output /tmp/<rom>.py 2>&1 | grep -c unhandled`. Every stub is a task.
  9. If still no work found, run the full 91-ROM regression suite (`python3 scripts/run_tests.py --level 3`) and investigate every FAIL/SKIP.
  Create a `todowrite` entry for each discovered gap, then resume execution. The session only ends when steps 1-9 yield zero new work.

28. **Keep at least 3 pending todos** — at any work boundary, if fewer than 3 pending todos remain, run the work discovery loop (27) before continuing. Always have a visible backlog of upcoming work.

---

## AI Orchestrator Operating Rules

> Rules 29-40 govern how the orchestrator agent operates (context management, delegation, parallelization). They are not GBA project rules.

### Context Management (Avoid Compaction Death Spirals)

29. **DELEGATE ALL EXECUTION** — orchestrator NEVER runs: `cargo build`, `gbatopy transpile`, `python3 <rom>.py`, `python3 -m pytest`, or any command producing >2KB output. These ALWAYS go to a fixer/explorer subagent. Orchestrator only runs: `git status`/`diff`/`log`, `ls`, `wc -l`, `grep -c`, `head -5`, `tail -5`, and context tools (`ctx_reduce`/`ctx_memory`/`todowrite`/`aft_safety`). If you need a build or transpile result, dispatch a subagent and read only the final summary via `task_result`. Violating this rule is the #1 cause of compaction death spirals.

30. **DROP AFTER EVERY EXTRACT** — after extracting info from any tool output, immediately call `ctx_reduce`. Pattern: read → extract → drop → act. Never: read → read → read → act → drop at end. After every 5th consecutive tool call, stop and drop all spent outputs before the next call.

31. **ONE-DROP RULE** — if ANY tool output is dropped/compacted even once, STOP. Do NOT retry the same call. Delegate all subsequent build/verify/diagnose work to a fresh subagent. One drop = death spiral already started. Subagent results survive compaction better than bash output.

32. **MEMORY UNDER 40** — deduplicate/merge/archive project memory at every work boundary (todo completion, session start, phase transition). Scan for: (1) duplicates → merge, (2) contradictions → resolve and archive one, (3) stale entries → archive. Every memory entry costs ~100 bytes on every turn — 80 entries = 8KB of permanent overhead.

33. **SUBAGENT HANDOFF** — subagents stop at ~70% context, write a summary of progress to `/tmp/<task-name>-handoff.txt` (what was done, what remains, files modified with line numbers, exact next step), and return it as their final message. Orchestrator launches a fresh subagent with the handoff as starting context. Never let a subagent run until its context is fully saturated.

### Parallelization
34. **Always use subagents** — GBA-specific routing:
  - Codebase recon → `@explorer` | External docs → `@librarian` | Architecture → `@oracle`
  - Bounded implementation → `@fixer` | Image analysis → `@observer` | Git/lint/test → `@fast-generic`
  - Track task IDs, reconcile on return, never block on a subagent.

34a. **Parallel investigation is the default, not the exception** — when two or more problems need investigation (failing ROMs, codegen bugs, rendering issues, root-cause analysis), dispatch ALL of them as parallel subagent lanes in a SINGLE message. Do NOT serialize investigations one after another. Do NOT wait for one investigation to finish before launching the next. The orchestrator's operating premise is maximum parallelism: every independent problem gets its own subagent, fired simultaneously. Serializing investigations wastes wall-clock time and is a process error, not a style choice. If the problems are independent (no shared write scope), they MUST be dispatched in parallel. Only serialize when one investigation's result is a precondition for the next.

### ROM Failure Policy
35. **ZERO-SKIP policy** — every ROM must PASS or FAIL, never SKIP. SKIP is forbidden. When a ROM would be skipped (timeout, OOM, missing golden), treat as FAIL and dispatch a subagent to root-cause and fix it.
36. **Timeout analysis is mandatory** — when a ROM times out, do NOT mark SKIP or move on. Dispatch a parallel `@explorer` with `--pc-trace=FILE --trace-n=N` to capture the hang point, identify the loop address, decode surrounding instructions, report root cause + proposed fix. Common root causes: (a) missing IRQ delivery, (b) SIO/serial poll with no clock, (c) audio subsystem waiting on FIFO space, (d) infinite reset loop. File a todo before moving on.
37. **Every FAIL/SKIP ROM gets a subagent** — do not batch-debug serially. Each failing ROM gets one `@explorer` in parallel. Each returns: (1) hang/spin address, (2) root cause category from `docs/how-debug.md`, (3) proposed fix with exact file + line, (4) verification command.

### Script Discipline
38. **Script placement** — generic reusable scripts go in `scripts/` and MUST be documented in `scripts/README.md`. Ad-hoc, one-off, or debug scripts go in `/tmp/`. Never create temporary scripts in the project root or `scripts/` without adding them to the README.

### Workflow Improvement (Commit-Gated Friction Analysis)

39. **Friction analysis at every commit** — BEFORE creating any commit, run a friction analysis on the work that led to it. For each friction point encountered this cycle (fabricated subagent results, stale docs, invalid goldens, missing baselines, repeated manual steps, wrong CLI flags, silent fallbacks), record a concrete speedup entry in `docs/WORKFLOW_SPEEDUPS_<YYYY-MM-DD>.md` with: ID, title, problem it kills, effort estimate, ROI. This is NOT optional — a commit without a friction analysis checkpoint is incomplete. The analysis lives in the repo, not chat, so a session dying right after the commit does not lose it.

40. **Implement P0 speedups before resuming feature work** — after the friction analysis, if any P0 speedup item (≤2hr effort, prevents a failure mode observed this cycle) is unimplemented, implement it BEFORE moving to the next feature/bug work. The session does not end while unimplemented P0 speedups remain from the current commit's friction analysis. A friction point observed twice across sessions becomes a structural fix (script, lint rule, or AGENTS.md rule), not a repeated manual workaround — promote it per global §17.

### Autonomous Continuation Enforcement

> Rules 41-46 are MECHANICAL rules, not guidelines. They have explicit violation signals. The operational checklist form is in `RUNBOOK.md` § "Orchestrator Decision Flow" — run that checklist at every work boundary. These rules exist because rules 27-28 were being ignored in practice.

41. **NO permission-seeking when work is queued** — if the todo list has ≥1 pending item, dispatch it. Never ask "Continue?" / "anything else?" / "should I proceed?" / "let me know" when there is queued work. Valid pause reasons are ONLY: (a) a destructive operation needing confirmation (global §2), (b) genuine ambiguity requiring one clarifying question (global §6), (c) ALL todos are genuinely blocked and rule 27 yielded zero new work. "Waiting for inspiration" is not a valid pause. **Violation signal:** any reply containing "Continue?" / "anything else?" / "should I proceed?" while ≥1 pending todo exists.

42. **Batch dispatch all independent ready todos** — when ≥2 todos are ready-to-dispatch (no shared write scope, no dependency on each other's results), emit ALL `task` calls in a SINGLE message. Never dispatch one, wait for it, then dispatch the next. If only 1 todo is ready but 3 are pending, dispatch the 1 and use the wait time to run rule 27 and refill the queue. **Violation signal:** a partial dispatch (1 of N ready todos) in a single turn, followed later by another dispatch of an independent todo.

43. **Codegen changes need zero user approval** — rule 4a means literally: apply fix → build → canary regression (one ROM) → full L3 sweep (91 ROMs) → commit, ALL in one autonomous cycle. No "should I apply this codegen fix?" checkpoint. The canary result is the only gate: pass → proceed to full sweep; fail → debug. The full sweep result is the next gate: pass → commit; fail → debug. Never ask the user to approve a codegen change mid-cycle. **Violation signal:** any "should I proceed with this codegen fix?" / "ok to apply?" message for a codegen change.

44. **Never idle-wait on a subagent** — when a subagent is running and you have other ready work, dispatch it in parallel. If you have NO other ready work, use the wait time to: (a) run rule 27 work discovery, (b) read code/docs to prepare the next dispatch brief, (c) reconcile completed subagent results, (d) update WORKPLAN.md/test-roms.md. Stopping to "wait for results" when there is preparable work is a process error. **Violation signal:** a reply that says "waiting for subagent X" while ≥1 ready todo exists undisturbed.

45. **One comprehensive probe per investigation round, never incremental serial probes** — when investigating a runtime bug (blank screen, hang, wrong render), the first probe dispatched must capture ALL relevant signals in a single run: registers at the decision point, DMA channel configurations (all 4 channels: source/dest/count/control), VRAM/palette/OAM write counts, IRQ delivery (VBlank/HBlank), HALT enter/exit transitions, and the specific register or flag the bug hypothesis depends on. Do NOT dispatch a probe that captures one signal, read the result, then dispatch a second probe for the next signal — each probe round is minutes of wall-clock. If two probe angles are independent, dispatch them as parallel subagent lanes in ONE message per rule 34a; never run probe-1, read result, then probe-2. A probe that returns "need to also check X" is a defective probe — the brief must enumerate every signal to capture up front. **Violation signal:** three or more sequential fixer/explorer calls on the same ROM, each adding one new probe, when one call with a comprehensive probe brief would have surfaced the root cause.

46. **Refresh queue every 4 completed todos** — after every 4 todos marked completed in the opencode `todowrite`, run the rule 27 work discovery loop, then import any new tasks discovered into `todowrite` and add new `F<N>` entries to `WORKPLAN.md`. This keeps the backlog from running dry mid-session and ensures WORKPLAN.md and todowrite stay synchronized. **Violation signal:** fewer than 3 pending todos remain in `todowrite` without a fresh work-discovery pass having run, OR a work-discovery pass that finds new work but does not import it into `todowrite`.

## Zero Tolerance for Stubs

Applies to **generated Python output** and **runtime templates** in `crates/gbatopy-cli/assets/gba_runtime/` and `templates/`. See global §30.1 for the full rule. Markers: `pass`, `return 0`, `return None`, `NotImplementedError`, `TODO:`, empty bodies, `print()`-only functions.

## Ghidra Static Analysis Oracle

Ghidra is used as a static analysis oracle for cross-validating the transpiler's static analysis. See [docs/ghidra-reference.md](docs/ghidra-reference.md) for setup, helper scripts, and cross-validation workflow.
