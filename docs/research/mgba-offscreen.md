# mGBA Headless Screenshot Setup

Research notes for the GBAtoPy golden-screenshot pipeline (T3.1, 2026-11-16).
Every claim carries a `file:line` from this repository or a stated source; inferences are
marked as such.

---

## 1. Correct mGBA headless setup

### 1.1 The canonical environment

Three variables, plus the two GBAtoPy screenshot variables:

```sh
export SDL_VIDEODRIVER=offscreen
export SDL_AUDIODRIVER=dummy
export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:$LD_LIBRARY_PATH"
GBATOPY_SCREENSHOT_PATH=/tmp/golden GBATOPY_TARGET_FRAME=60 \
  ./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua <rom>.gba
```

Citations (all four project entry points use the identical env set):
- `AGENTS.md:120` (rule 15) — the canonical statement: "`SDL_VIDEODRIVER=offscreen` +
  `SDL_AUDIODRIVER=dummy` + `LD_LIBRARY_PATH=\"$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:...`".
- `scripts/generate_goldens.py:42-44` — `env["SDL_VIDEODRIVER"] = "offscreen"`,
  `env["SDL_AUDIODRIVER"] = "dummy"`,
  `env["LD_LIBRARY_PATH"] = f"{PROJECT_ROOT}/mgba/build:{PROJECT_ROOT}/mgba/build/sdl:..."`.
- `scripts/verify/verify_rom.sh:118-121` — same three exports immediately before the mGBA call.
- `scripts/generate_mgba_goldens.sh:95-97` and again per-capture at `:194-197`.

### 1.2 How the capture works

The mGBA binary is driven headlessly via a Lua script:

- `scripts/screenshot/screenshot.lua:10-11` — reads `GBATOPY_SCREENSHOT_PATH` (output path,
  no extension; default `/tmp/golden`) and `GBATOPY_TARGET_FRAME` (default 60).
- `scripts/screenshot/screenshot.lua:13-20` — registers a `frame` callback; when
  `emu:currentFrame() >= target_frame` it calls `emu:screenshot(name .. ".png")` and
  `os.exit(0)`. So the PNG is produced by mGBA itself, in-process, after the target frame has
  been rendered.
- Invocation: `mgba -S <lua> <rom>` — `scripts/generate_goldens.py:47-53`,
  `scripts/verify/verify_rom.sh:121`, `scripts/generate_mgba_goldens.sh:200`.
- Output naming: `golden_{rom_base}_frame_{frame}.png` under `test-reports/goldens/`
  (`scripts/generate_goldens.py:33-34`; `run_tests.py` lookup candidates at
  `scripts/run_tests.py:233-238`).

### 1.3 Why `SDL_VIDEODRIVER=offscreen` works

SDL2's **offscreen** driver is a real, in-memory video device: it allocates a framebuffer
(240×160 for the GBA window) and all blits land in that buffer. `emu:screenshot()` reads the
window's pixel buffer, so it reads *actual rendered pixels*. No display server, no X, no
window manager is involved. This is why it is the only driver the project trusts
(`AGENTS.md:120`: "Do NOT use `SDL_VIDEODRIVER=dummy` (causes 33-byte segfault artifacts)";
`docs/reference/test-roms.md:268`: goldens require
`SDL_VIDEODRIVER=offscreen SDL_AUDIODRIVER=dummy`).

### 1.4 Why `SDL_VIDEODRIVER=dummy` produces 33-byte artifacts

Observed behavior (documented in-repo): mGBA with the **dummy** video driver writes a
degenerate ~33-byte PNG (occasionally ~507B) instead of a real screenshot
(`AGENTS.md:120`; `scripts/verify/validate_golden.py:4-6`: "mGBA in offscreen mode can produce
tiny PNG files (33B, 507B) that are segfault artifacts, not real reference images").

Mechanism (inference — not documented in the repo; mGBA/SDL source not audited for this):
the **dummy** driver provides *no* pixel buffer at all. mGBA's screenshot path reads the
window surface that the dummy driver never allocates, so the capture degenerates to a
near-empty PNG (33 bytes ≈ a valid PNG signature + header with a 1×1 or empty image). The
project rule is absolute: never use `dummy` for screenshots.

`SDL_AUDIODRIVER=dummy` is fine and required — audio is irrelevant to visual goldens and there
is no audio device on a headless box (`scripts/generate_goldens.py:43`).

### 1.5 Why `LD_LIBRARY_PATH` is required

The mGBA binary links against the locally built SDL2/GBA libraries under
`mgba/build` and `mgba/build/sdl`. In a clean shell (CI, fresh login, a subagent that
doesn't inherit the build environment) those are not on the default loader path, and mGBA
fails to start — which has been misdiagnosed as ROM-specific segfaults before.

- Precedent: `docs/WORKFLOW_SPEEDUPS_2026-11-04.md:47` (FS-2026-11-04-08) — "verify_rom.sh
  didn't export `SDL_VIDEODRIVER=offscreen` + `LD_LIBRARY_PATH` for the mGBA call, causing
  mGBA to fail in clean shells. This was misdiagnosed as 'mGBA segfaults on
  proposal_proposal-demo' — the golden was actually valid all along."
- All four project entry points set it identically (§1.1 citations).

---

## 2. Golden-generation commands used by the project

### 2.1 `scripts/run_tests.py` — consumes goldens, does not create them

- `scripts/run_tests.py:40` — `GOLDEN_DIR = PROJECT_ROOT / "test-reports" / "goldens"`.
- `scripts/run_tests.py:42` — `COMPARE_SCRIPT = .../scripts/verify/compare_screenshots.py`.
- `scripts/run_tests.py:229-244` — `compare_screenshot()`: searches candidates
  (`{rom}.png`, `{rom}_f{frame}.png`, `{rom}_f10.png`, `golden_{rom}_frame_{frame}.png`,
  `golden_{rom}_frame_10.png`), then runs
  `python3 compare_screenshots.py -s <golden> <transpiled>`.
- `scripts/run_tests.py:240-241` — no candidate exists → status `"no_golden"`.
- `scripts/run_tests.py:349-351` — zero-SKIP policy: for visual test types, missing golden →
  FAIL with `level3_detail = "no golden screenshot for test_type=..."`, never SKIP.
- L3 gating: `scripts/run_tests.py:7` — "Level 3 (visual): Screenshot comparison with golden
  — runs if L2 passes"; `run_tests.py:509-519` — summary counts `no_golden` separately.

### 2.2 `scripts/generate_goldens.py` — the batch generator

- `scripts/generate_goldens.py:47-53` — the exact mGBA invocation:
  `subprocess.run([str(mgba_bin), "-S", str(LUA_SCRIPT), str(rom_path)], ...)` with the env
  of §1.1 (lines 39-44) and `GBATOPY_SCREENSHOT_PATH`/`GBATOPY_TARGET_FRAME` (lines 40-41).
- `scripts/generate_goldens.py:27` — `MGBA_BIN = PROJECT_ROOT / "mgba" / "build" / "sdl" / "mgba"`.
- `scripts/generate_goldens.py:34` — output: `golden_{rom_base}_frame_{frame}.png` (canonical
  name, matches `run_tests.py`'s first candidate at `:236`).
- `scripts/generate_goldens.py:72-78` — defaults: `--frames 60`, `--workers 2`, `--timeout 120`.
- `scripts/generate_goldens.py:56-61` — success = exit code 0 **and** the PNG exists.

### 2.3 `scripts/verify/verify_rom.sh` — one-shot generate + compare

- `scripts/verify/verify_rom.sh:118-121` — exports the three env vars, then runs
  `GBATOPY_SCREENSHOT_PATH="${TEMP_GOLDEN%.*}" "${MGBA_PATH}" -S "${SCREENSHOT_LUA}" "${ROM_PATH}"`.
- `scripts/verify/verify_rom.sh:183-195` — validates the produced golden with
  `validate_golden.py`; if invalid it tells the user to regenerate with
  `python3 scripts/generate_goldens.py --rom <rom>`.

### 2.4 `scripts/generate_mgba_goldens.sh` — shell variant

- `scripts/generate_mgba_goldens.sh:95-97` — the same three exports.
- `scripts/generate_mgba_goldens.sh:199-201` — same mGBA command, output
  `golden_${rom_base}_frame_${frame}.png` (`:191`).

**Exact command** (the one command that generates a frame-60 golden for `hello`):

```sh
cd /home/d.scasciafratte/gbatopy
export SDL_VIDEODRIVER=offscreen
export SDL_AUDIODRIVER=dummy
export LD_LIBRARY_PATH="$PWD/mgba/build:$PWD/mgba/build/sdl:$LD_LIBRARY_PATH"
GBATOPY_SCREENSHOT_PATH=test-reports/goldens/golden_hello_frame_60 \
GBATOPY_TARGET_FRAME=60 \
  ./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua test_roms/roms/hello.gba
# or simply: python3 scripts/generate_goldens.py --rom hello
```

---

## 3. Validating a golden PNG

The project has a dedicated validator plus a content guard in the comparator.

### 3.1 `scripts/verify/validate_golden.py` (primary validator)

- `scripts/verify/validate_golden.py:24` — `GOLDEN_SIZE_THRESHOLD = 200`; a PNG smaller than
  200 bytes is classified as a segfault artifact (check at `:52-56`).
  **Note on the task brief's "≥500B per project config #11449":** no 500B threshold exists in
  the current repo. The operative thresholds are **200B** here and **1KB** in
  `scripts/verify/verify_subagent_claim.py:20-21` (which re-checks subagent claims that a
  golden is ">1KB"). The 200B figure is also the one in `AGENTS.md:120`
  ("a golden screenshot <200B (typically 33 bytes) is a segfault artifact").
- `scripts/verify/validate_golden.py:67-72` — PNG signature check
  (`\x89PNG\r\n\x1a\n`).
- `scripts/verify/validate_golden.py:75-90` — IHDR check: must be a 13-byte IHDR and
  **240×160** (GBA screen dimensions).
- `scripts/verify/validate_golden.py:4-6` — documents the known artifact sizes: 33B and 507B.
- Exit codes: 0 valid, 1 invalid, 2 usage (`:11-15`).

Usage:

```sh
python3 scripts/verify/validate_golden.py test-reports/goldens/golden_hello_frame_60.png hello
python3 scripts/verify/validate_golden.py --batch test-reports/goldens/
```

### 3.2 Pixel-content guard in `scripts/verify/compare_screenshots.py`

The size check alone is not sufficient — a *valid-size* golden can still be all-black (the
xvfb-run failure mode, §4). The comparator therefore checks content:

- `scripts/verify/compare_screenshots.py:46-48` — `count_content_pixels` counts pixels with
  any channel > 0 (i.e. non-pure-black).
- `scripts/verify/compare_screenshots.py:92` — `MIN_CONTENT_PCT = 0.5` (% of pixels that must
  be non-black).
- `scripts/verify/compare_screenshots.py:96-100` — transpiled output 0% content while golden
  has content → `inconclusive`, reason "blank-screen regression".
- `scripts/verify/compare_screenshots.py:101-114` — golden < 0.5% content → if the images
  match, it still reports pass, but if they differ it is `inconclusive` ("cannot trust
  match"); golden nearly empty outright → `inconclusive` "golden screenshot may be bad".

### 3.3 What "valid" should mean (current coverage + gap)

| Check | Implemented? | Where |
|---|---|---|
| File size ≥ 200B | ✓ | `validate_golden.py:24,52` |
| Valid PNG signature | ✓ | `validate_golden.py:67` |
| 240×160 dimensions | ✓ | `validate_golden.py:77-90` |
| Not all-black (content ≥ 0.5%) | ✓ (in comparator) | `compare_screenshots.py:46-48,92` |
| Color-count check (e.g. not a single flat color) | ✗ **gap** | — |

The last row is the gap: `validate_golden.py` has no all-*white* (or any single flat-color)
check. An all-white 240×160 golden passes both `validate_golden.py` and the non-black content
check (white pixels are content). If a flat-color golden is ever observed, the fix belongs in
`validate_golden.py` (e.g. count distinct colors or require variance). Not implemented as of
2026-11-16.

---

## 4. The `xvfb-run` failure mode

### 4.1 Observed behavior (documented in-repo)

`AGENTS.md:120`: "Do NOT use `xvfb-run` alone (produces >200B but all-black blank goldens)."

So a golden produced under `xvfb-run` **passes** the size/signature/IHDR checks of
`validate_golden.py` (it is a real 240×160 PNG, well over 200B) but is **all black**. This is
why the project standardizes on `offscreen` and why `compare_screenshots.py` carries the
content check (§3.2) — a black golden compared against a blank transpiled output would
otherwise be a false PASS.

### 4.2 Why xvfb-run yields all-black images

Mechanism (inference — the repo documents only the symptom): `xvfb-run` starts a headless X
server and SDL2 uses its **X11** driver. The window's pixel storage lives in the X server's
pixmap, not in the process's memory. Two things conspire:

1. On a bare Xvfb with no window manager, the mGBA window is created but never reliably
   mapped/exposed, and the X11 driver's pixel readback is therefore undefined — typically
   zero-filled (black).
2. Unlike the offscreen driver, there is no synchronous in-process framebuffer the
   `emu:screenshot()` readback can rely on; it reads back whatever the X server happened to
   hold for that window, which before/without a real render pass is black.

The net effect: a structurally valid PNG whose pixels never carried the rendered frame.
Because the size check cannot distinguish it from a good golden, the project rule
(`AGENTS.md:120`) forbids `xvfb-run` for golden generation, and `compare_screenshots.py:96-114`
is the backstop that turns such a comparison into `inconclusive` instead of a silent PASS.

### 4.3 Checklist for any new golden pipeline

1. `SDL_VIDEODRIVER=offscreen` (never `dummy` for video; `dummy` OK for audio),
   `SDL_AUDIODRIVER=dummy`, `LD_LIBRARY_PATH` pointing at `mgba/build` + `mgba/build/sdl`.
2. Capture via `mgba -S scripts/screenshot/screenshot.lua <rom>` with
   `GBATOPY_SCREENSHOT_PATH` / `GBATOPY_TARGET_FRAME` set.
3. `python3 scripts/verify/validate_golden.py <golden.png>` → must print `VALID ... 240x160`.
4. Run the comparison through `compare_screenshots.py` (or `verify_rom.sh`), which enforces
   the ≥0.5% content rule on the golden.
5. Subagent-claimed goldens additionally re-verified via
   `scripts/verify/verify_subagent_claim.py` (>1KB + 240×160 + PNG header checks,
   `:13-31`).

---

## 5. Sources

Project (local):
- `AGENTS.md:120` (rule 15) — canonical headless env; dummy/xvfb-run failure modes.
- `scripts/generate_goldens.py` — batch golden generation (env `:39-44`, invocation `:47-53`,
  naming `:33-34`, defaults `:72-78`).
- `scripts/verify/verify_rom.sh` — one-shot verify (env `:118-121`, mGBA call `:121`,
  golden validation `:183-195`).
- `scripts/generate_mgba_goldens.sh` — shell batch generator (env `:95-97`, `:194-201`).
- `scripts/screenshot/screenshot.lua` — mGBA Lua capture script (`:10-20`).
- `scripts/verify/validate_golden.py` — golden validity checks (threshold `:24`, signature
  `:67`, IHDR 240×160 `:75-90`, artifact sizes `:4-6`).
- `scripts/verify/compare_screenshots.py` — pixel comparison + content guard
  (`:46-48`, `:92-114`).
- `scripts/run_tests.py` — golden lookup (`:40`, `:233-244`), zero-SKIP on missing golden
  (`:349-351`).
- `scripts/verify/verify_subagent_claim.py:13-31` — subagent claim re-verification (>1KB,
  240×160, PNG header).
- `docs/reference/test-roms.md:268` — offscreen/dummy env requirement for goldens.
- `docs/WORKFLOW_SPEEDUPS_2026-11-04.md:47` — LD_LIBRARY_PATH/self-containment precedent.

Background (inference, not repo-cited):
- SDL2 video driver behavior (offscreen = in-memory framebuffer; dummy = no pixel buffer;
  X11 = server-backed pixmap) — standard SDL2 architecture; specific mGBA screenshot code path
  not audited in this session.
