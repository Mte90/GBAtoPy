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

### Workflow
1. **Read `WORKPLAN.md` first** at session start — it is the source of truth for pending work. Reconcile against `docs/reference/test-roms.md` and the live codebase.
2. **Read `docs/roadmap.md`** for full status and strategy.
3. **Read `docs/how-debug.md`** for systematic debug workflow + known bug classes.
4. **One ROM at a time for fixing** — parallel root-cause *investigation* across multiple ROMs is allowed and encouraged (dispatch multiple @explorer in parallel). But apply fixes sequentially, one ROM at a time, verifying each before moving to the next. Never run the full 76-ROM suite during active debugging. Use `python3 scripts/run_tests.py --level 3 --rom <name>`.
5. **Always respond in English** — even if the user writes in other languages.

### Verification
6. **Test with pixels** — "no crash" is not enough. Verify screenshot content against mGBA golden via `compare_screenshots.py`. See [RUNBOOK.md](RUNBOOK.md).
6a. **Re-test all previously-passing ROMs after codegen/dispatch changes** — a fix that targets one ROM can regress others. The peephole `+4` fix for Thumb loops regressed start-delay from 1.75% PASS to 100% blank. After any change to shared dispatch, peephole optimizer, or codegen headers, run `python3 scripts/run_tests.py --level 3` on the last known-passing set before declaring done.
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
17. **Never add step_scanline to memory reads** — see invariant #3. PPU stepping is exclusively in the main loop.
18. **Fallback interpreter is pure CPU** — see invariant #1.
19. **Check known bug classes first** — consult "Known Codegen Bug Classes" (5), "Known Runtime Bug Classes" (2), and "New Bug Classes" (3: SWI dispatch truncation, memory non-zero init, IRQ vector missing) in `docs/how-debug.md` before deep debugging. Run `python3 -m pytest crates/gbatopy-cli/assets/gba_runtime/tests/test_dispatch_audit.py` first.
20. **Check dispatch table completeness** — NOP block bug may skip initialization code.
21. **Verify STRH/LDRH offsets** — disassembler may use wrong bit field (bits 7-3 vs bits 3-0).
21a. **Verify explorer code-pattern claims by reading the cited line** — an explorer hallucinated a NOP-detection mask `(opcode & 0xFF000000) == 0xEA000000` at emitter_arm.rs:609; grep found no such pattern. Before acting on any subagent's claim about a code pattern, read the cited file:line with `read` or `aft_zoom` and confirm the pattern exists as described.

### Work Management
21. **Autonomous todo creation** — when you discover work (new bug, stale doc, missing test, done WORKPLAN item, regression risk, flagged follow-up), IMMEDIATELY create a `todowrite` entry. Review at every work boundary and prune irrelevant items.
22. **WORKPLAN.md is comprehensive** — must cover ALL pending work, not just ROM fixes: undocumented code fixes, architecture debt, doc staleness, feature gaps, verification gaps, performance issues. Every gap gets a `F<N>` entry before session end.
23. **Doc-sync rule** — any codegen/runtime fix that changes a ROM's pass/fail status MUST update `docs/reference/test-roms.md` in the same task. Summary counts, per-ROM rows, feature matrix, compatibility matrix must all reflect new state.
24. **Deduplicate before fixing** — if a bug is in duplicated code (two `_deliver_irq` functions, two main loops), deduplicate FIRST, then fix the single remaining copy. Check with `grep -c` before any multi-site fix.

### Autonomous Continuation
0a. **Never stop until done** — work autonomously and continuously until ALL pending work is complete. Do not pause to ask permission for the next step when the path forward is clear from the current state. Do not stop after one fix if more fixes are queued. Do not end the session with pending todos. If a fix reveals a deeper issue, follow it immediately. The only valid reasons to stop are: (a) all todos complete, (b) a genuine blocker requiring user input, (c) 3 failed attempts on the same task (escalate). Loop on: diagnose → fix → verify → next item, until the todo list is empty.

0b. **Work discovery loop** — when the todo list is empty, do NOT stop and do NOT ask the user what to do next. Instead, discover more work by following this loop:
  1. Read `WORKPLAN.md` — find the next pending phase or task. Every `F<N>` entry is actionable work.
  2. Read `docs/reference/test-roms.md` — find any ROM marked FAIL or SKIP. Each one is a task.
  3. Run `python3 scripts/run_tests.py --level 3 --rom <name>` on a failing ROM to reproduce the issue.
  4. Check `docs/roadmap.md` for unverified features, missing modes, or architecture debt.
  5. Run `python3 -m pytest crates/gbatopy-cli/assets/gba_runtime/tests/` to find failing runtime tests.
  6. Audit `docs/how-debug.md` "Known Bug Classes" — each unresolved class is a task.
  7. Grep for `TODO`, `FIXME`, `unimplemented`, `stub`, `pass  #` in `crates/` and `crates/gbatopy-cli/assets/gba_runtime/` — each hit is a task.
  8. If still no work found, run the full 76-ROM regression suite (`python3 scripts/run_tests.py --level 3`) and investigate every FAIL/SKIP.
  Create a `todowrite` entry for each discovered gap, then resume execution. The session only ends when steps 1-8 yield zero new work.

0c. **Keep at least 3 pending todos** — at any work boundary, if fewer than 3 pending todos remain, run the work discovery loop (0b) before continuing. Always have a visible backlog of upcoming work.

### Context Management (Avoid Compaction Death Spirals)

0d. **Delegate when context is saturated** — if tool outputs are being compacted before they can be read, STOP running bash commands yourself. Delegate ALL build/verify/diagnose work to a fresh subagent (fixer or explorer) which has its own clean context. Only retrieve the subagent's final text result via `task_result`.

0e. **One all-in-one script over many small commands** — when running multi-step verification (build + transpile + run + compare), write ONE self-contained shell script to /tmp/, run it in the background, and read the tiny result file. Do not chain 10+ bash calls serially — each output fills context and triggers compaction.

0f. **Write results to files, not stdout** — long-running commands must write their result to a tiny file (e.g. /tmp/result.txt) as a one-line summary. Read the file with the `read` tool, not `cat` via bash. The `read` tool is cheaper than bash output.

0g. **Aggressively drop spent tool outputs** — after extracting what you need from a tool output, immediately mark it discardable with `ctx_reduce`. Do not hoard outputs until end of turn. Large file reads, grep results, and build logs are the primary cause of context saturation.

0h. **Do not retry the same failing command** — if a bash command's output gets compacted 3 times in a row, STOP. The context is too saturated to read bash output. Delegate to a subagent instead. Retrying the same command wastes context budget without progress.

0i. **Subagent results survive compaction better than bash output** — `task_result` returns the subagent's final assistant message as text, which is cheaper in context than raw bash output. When context is tight, prefer delegation over direct bash execution.

0j. **Detect saturation early** — if a bash command's output gets dropped/compacted before you can read it TWICE in a row, STOP running bash commands yourself immediately. You are in a compaction death spiral. Delegate ALL subsequent build/verify/diagnose work to a fresh subagent (fixer or explorer) which has its own clean context.

0k. **Massive context reduction is sometimes necessary** — if context is critically saturated (even `echo X` output gets dropped), use `ctx_reduce` with a large range like "1-100" to drop old tool outputs. This is destructive but necessary to escape a death spiral.

0l. **Never run the same build command more than twice** — if `cargo build --release` output gets compacted twice in a row, STOP running bash commands. Delegate ALL build/verify/diagnose work to a fresh subagent (fixer or explorer) which has its own clean context. Retrieve only the final text result via `task_result`.

0m. **Checkpoint before risky multi-file changes** — before any change touching >3 files or critical paths (auth, data layer, config, codegen, runtime templates), create a checkpoint with `aft_safety checkpoint`. This is the plan-level rollback point.

0n. **Use `read` tool over `cat` in bash** — when you need to read a file's contents, use the `read` tool, not `cat`/`head`/`tail` via bash. The `read` tool is cheaper in context than bash output and survives compaction better.

0o. **Delegate build+verify cycles to subagents** — when you need to build, transpile, and verify a ROM, delegate the ENTIRE cycle to ONE fixer subagent. The subagent has its own clean context and can run all the commands without filling your context. Retrieve only the final text result via `task_result`.

0p. **End turn after spawning background tasks** — after spawning independent background tasks, end your turn immediately with a brief status message. Do NOT poll for status. The system notifies you automatically when tasks finish. Polling wastes context.

0q. **PROACTIVE context budget enforcement** — the rules above (0d-0p) are reactive; they fire after saturation. The following rules are PROACTIVE and must be followed before saturation occurs:
  1. **Drop after every extract** — after extracting information from any tool output >2KB, immediately call `ctx_reduce` to mark it discardable. Do not wait for "end of turn". The pattern is: read → extract → drop → act. NOT: read → read → read → act → drop at end.
  2. **One-drop rule** — if ANY tool output is dropped/compacted even once, IMMEDIATELY delegate all subsequent build/verify/diagnose work to a fresh subagent. Do NOT retry the same call in the orchestrator context. One drop = death spiral already started.
  3. **5-call checkpoint** — after every 5th consecutive tool call, stop and drop all spent outputs before making the next call. If you cannot drop anything because everything is still needed, delegate to a subagent instead of continuing.
  4. **No retry on drop** — never retry a tool call whose output was dropped. The context is too saturated to read it. Delegate to a subagent with clean context instead.
  5. **Pre-flight check before long sequences** — before starting a sequence of 3+ tool calls (build + verify + compare), drop all currently-held spent outputs first. A 3-call sequence against a full context will fail.

0r. **Check context budget before each new tool call** — if the last 3 tool outputs were large (>2KB each) and you haven't dropped anything in the last 5 tool calls, STOP and drop spent outputs BEFORE making the next call (see proactive rule 0q). Do not wait for saturation. Think of it as garbage collection after each logical step, not at end of turn.

0s. **Prefer small targeted reads over full file dumps** — use `read` with `startLine`/`endLine` or `offset`/`limit` instead of reading entire files. Use `aft_zoom` for specific symbols instead of `read` for whole files. Use `aft_search` instead of `grep` through bash. Every full-file read is a context bomb — if you need 20 lines from a 500-line file, read 20 lines, not 500.
### Parallelization
25. **Always use subagents when possible** — subagents are the DEFAULT, not the exception. Any non-trivial work (multiple steps, multiple files, research, investigation, implementation >20 lines) MUST be delegated to a subagent. The orchestrator coordinates, plans, dispatches, reconciles, and verifies — it does not implement serially when a specialist can do the work in parallel.

  **Mandatory delegation triggers:**
  - 2+ independent parts → dispatch parallel subagents in ONE message
  - Codebase recon / file discovery → `@explorer`
  - External docs / library research → `@librarian`
  - Architecture decisions / risk analysis / code review → `@oracle`
  - Bounded implementation (well-defined spec, clear scope) → `@fixer`
  - UI/UX / visual polish / responsive layout → `@designer`
  - Image / screenshot / PDF analysis → `@observer`
  - Routine git commands / lint / typecheck / test runs → `@fast-generic`

  **Rules:**
  - Track task IDs, keep working on non-overlapping lanes, reconcile results when they return
  - Dispatch independent lanes in the background; do NOT wait serially
  - One trivial one-file edit (<20 lines, no design) is the ONLY exception for direct execution
  - If you find yourself doing multi-step implementation work directly, STOP and delegate
  - Never block on a subagent — dispatch it, do other work, reconcile when it returns

### ROM Failure Policy
26. **ZERO-SKIP policy** — every ROM must PASS or FAIL, never SKIP. SKIP is forbidden. When a ROM would be skipped (timeout, OOM, missing golden), treat as FAIL and dispatch a subagent to root-cause and fix it.
27. **Timeout analysis is mandatory** — when a ROM times out, do NOT mark SKIP or move on. Dispatch a parallel `@explorer` with `--pc-trace=FILE --trace-n=N` to capture the hang point, identify the loop address, decode surrounding instructions, report root cause + proposed fix. Common root causes: (a) missing IRQ delivery, (b) SIO/serial poll with no clock, (c) audio subsystem waiting on FIFO space, (d) infinite reset loop. File a todo before moving on.
28. **Every FAIL/SKIP ROM gets a subagent** — do not batch-debug serially. Each failing ROM gets one `@explorer` in parallel. Each returns: (1) hang/spin address, (2) root cause category from `docs/how-debug.md`, (3) proposed fix with exact file + line, (4) verification command.

### Script Discipline
29. **Script placement** — generic reusable scripts go in `scripts/` and MUST be documented in `scripts/README.md`. Ad-hoc, one-off, or debug scripts go in `/tmp/`. Never create temporary scripts in the project root or `scripts/` without adding them to the README.

## Zero Tolerance for Stubs

**Scope:** This rule applies to **generated Python output** (the transpiler's product) and the **runtime templates** in `crates/gbatopy-cli/assets/gba_runtime/` and `crates/gbatopy-cli/assets/templates/`. Rust codegen stubs are tracked separately as codegen-incomplete markers, not runtime stubs — they do not leak into the generated Python.

These ALL count as unimplemented in generated Python:
- `pass`
- `return 0`
- `return None`
- `NotImplementedError`
- `TODO:` comments
- Empty function bodies
- Functions that only contain `print()` debug statements
