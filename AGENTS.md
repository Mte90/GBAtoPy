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
Current work log:    todo.md
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
| [docs/codegen-pitfalls.md](docs/codegen-pitfalls.md) | 13 documented codegen bug classes |
| [docs/roadmap.md](docs/roadmap.md) | Full implementation status and strategy |
| [docs/reference/test-roms.md](docs/reference/test-roms.md) | Per-ROM pass/fail matrix |
| [WORKPLAN.md](WORKPLAN.md) | Source of truth for pending work — read at session start |
| [todo.md](todo.md) | Migration knowledge transfer — read before resuming debug |

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
- Windows, blends, mosaic = register stubs only (not functional)
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

## Non-Negotiable Rules

### Workflow
1. **Read `WORKPLAN.md` first** at session start — it is the source of truth for pending work. Reconcile against `docs/reference/test-roms.md` and the live codebase.
2. **Read `docs/roadmap.md`** for full status and strategy.
3. **Read `docs/how-debug.md`** for systematic debug workflow + known bug classes.
4. **One ROM at a time** — never run the full 66-ROM suite during active debugging. Use `python3 scripts/run_tests.py --level 3 --rom <name>`.
5. **Always respond in English** — even if the user writes in other languages.

### Verification
6. **Test with pixels** — "no crash" is not enough. Verify screenshot content against mGBA golden via `compare_screenshots.py`. See [RUNBOOK.md](RUNBOOK.md).
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
15. **Debug probes must flush** — `print(..., flush=True)` BEFORE any `os._exit(0)`; the runtime exits hard, bypassing buffer flush.
16. **Never add step_scanline to memory reads** — see invariant #3. PPU stepping is exclusively in the main loop.
17. **Fallback interpreter is pure CPU** — see invariant #1.
18. **Check known bug classes first** — consult "Known Codegen Bug Classes" (5) and "Known Runtime Bug Classes" (2) in `docs/how-debug.md` before deep debugging. Run `python3 -m pytest crates/gbatopy-cli/assets/gba_runtime/tests/test_dispatch_audit.py` first.
19. **Check dispatch table completeness** — NOP block bug may skip initialization code.
20. **Verify STRH/LDRH offsets** — disassembler may use wrong bit field (bits 7-3 vs bits 3-0).

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
  8. If still no work found, run the full 66-ROM regression suite (`python3 scripts/run_tests.py --level 3`) and investigate every FAIL/SKIP.
  Create a `todowrite` entry for each discovered gap, then resume execution. The session only ends when steps 1-8 yield zero new work.

0c. **Keep at least 3 pending todos** — at any work boundary, if fewer than 3 pending todos remain, run the work discovery loop (0b) before continuing. Always have a visible backlog of upcoming work.

### Parallelization
25. **Parallelize with subagents** — when work has 2+ independent parts, dispatch parallel subagents in one message. Use `@explorer` for codebase recon, `@librarian` for external docs, `@oracle` for architecture/risk, `@fixer` for bounded implementation, `@designer` for UI/UX. Track task IDs, keep working on non-overlapping lanes, reconcile results. Exception: single trivial one-file edit (<20 lines) is faster done directly.

### ROM Failure Policy
26. **ZERO-SKIP policy** — every ROM must PASS or FAIL, never SKIP. SKIP is forbidden. When a ROM would be skipped (timeout, OOM, missing golden), treat as FAIL and dispatch a subagent to root-cause and fix it.
27. **Timeout analysis is mandatory** — when a ROM times out, do NOT mark SKIP or move on. Dispatch a parallel `@explorer` with `--pc-trace=FILE --trace-n=N` to capture the hang point, identify the loop address, decode surrounding instructions, report root cause + proposed fix. Common root causes: (a) missing IRQ delivery, (b) SIO/serial poll with no clock, (c) audio subsystem waiting on FIFO space, (d) infinite reset loop. File a todo before moving on.
28. **Every FAIL/SKIP ROM gets a subagent** — do not batch-debug serially. Each failing ROM gets one `@explorer` in parallel. Each returns: (1) hang/spin address, (2) root cause category from `docs/how-debug.md`, (3) proposed fix with exact file + line, (4) verification command.

### Script Discipline
29. **Script placement** — generic reusable scripts go in `scripts/` and MUST be documented in `scripts/README.md`. Ad-hoc, one-off, or debug scripts go in `/tmp/`. Never create temporary scripts in the project root or `scripts/` without adding them to the README.

## Zero Tolerance for Stubs

**Scope:** This rule applies to **generated Python output** (the transpiler's product) and the **runtime templates** in `crates/gbatopy-cli/assets/gba_runtime/` and `crates/gbatopy-cli/assets/templates/`. Rust codegen stubs (e.g. `ppu/mode1.rs`) are tracked separately as codegen-incomplete markers, not runtime stubs — they do not leak into the generated Python.

These ALL count as unimplemented in generated Python:
- `pass`
- `return 0`
- `return None`
- `NotImplementedError`
- `TODO:` comments
- Empty function bodies
- Functions that only contain `print()` debug statements
