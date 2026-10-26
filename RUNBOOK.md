# RUNBOOK — Build, Test, Verify, Debug

> Copy-pasteable commands for daily work. Referenced by `AGENTS.md`.

## Build

```bash
cargo build --release
```
Must produce 0 errors, 0 warnings.

## Transpile a Single ROM

```bash
cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py
```
Transpiled `.py` files go to `/tmp/`, never the project directory.

## Test Levels

| Test Level | Command | What It Verifies | What It Does NOT Verify |
|------------|---------|------------------|-------------------------|
| **Syntax Only** | `./scripts/run-all-tests.sh` | ✅ Python compiles | ❌ Graphics, ❌ Audio, ❌ Execution |
| **Execution** | `python3 stripes.py --headless --frame=60` | ✅ Script runs | ❌ Correct graphics/audio |
| **Visual** | `compare_screenshots.py` | ✅ Pixel-perfect match with mGBA | Requires manual golden screenshot |

**Key Rule:** `run-all-tests.sh` only checks Python syntax. For full graphics/audio verification, use `compare_screenshots.py`.

## One-Shot ROM Verification

```bash
./scripts/verify/verify_rom.sh <rom> --no-golden
```
Transpiles, runs, and compares against a golden screenshot in one step.

## Full Verification (Manual Steps)

⚠️ **mGBA Golden Generation Warning**: Never use `SDL_VIDEODRIVER=dummy` or `xvfb-run` — they produce segfault artifacts or all-black goldens. Only `SDL_VIDEODRIVER=offscreen` works.

```bash
# Step A: Set up mGBA environment (REQUIRED for headless screenshot generation)
export SDL_VIDEODRIVER=offscreen
export SDL_AUDIODRIVER=dummy
export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:$LD_LIBRARY_PATH"

# Step B: Generate golden screenshot with mGBA
GBATOPY_SCREENSHOT_PATH=/tmp/stripes GBATOPY_TARGET_FRAME=60 \
  ./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua test_roms/roms/stripes.gba

# Step C: Generate transpiled screenshot
cd /tmp && python3 stripes.py --headless --frame=60 --screenshot /tmp/stripes_transpiled.png

# Step D: Compare (PASS if <30% difference)
python3 scripts/verify/compare_screenshots.py -s /tmp/stripes.png /tmp/stripes_transpiled.png --threshold 30
```

## Debug Flags (Generated Runtime)

The generated runtime supports these flags — use them, do not inject `print()` probes:

| Flag | Purpose |
|------|---------|
| `--pc-trace=FILE` | Write PC trace to file |
| `--trace-n=N` | Trace N instructions |
| `--max-instrs=N` | Max instructions (default 1M; use `--max-instrs=10000000` for tight IWRAM poll loops like bgpd) |
| `--headless` | No window |
| `--frame=N` | Run N frames then exit |
| `--screenshot=PATH` | Save screenshot to PATH |

See `docs/how-debug.md` § "Systematic Spin Diagnosis Workflow" for usage patterns.

## Transpiled ROM CLI Flags

The transpiled `.py` files accept these CLI flags:

```
python3 <rom>.py [OPTIONS]

Options:
  --headless              Run without pygame window (for CI/headless servers)
  --frame N               Run N frames then exit
  --screenshot PATH       Save screenshot to PATH
  --scale N               Window scale factor (default: 1)
  --dump-memory PATH      Dump memory to binary file
  --dump-region NAME      Specific region to dump (ewram/iwram/vram/palette/oam)
  --save-state PATH       Save state to JSON file after execution
  --load-state PATH       Load state from JSON file before execution
  --hook-file PATH        Python script with debugging hooks (breakpoints, tracing, etc.)
  --pc-trace PATH         Log PC + registers each step to a file
  --trace-n N             Print first N PCs to stdout then stop tracing (default: 0)
  --max-instrs N          Maximum instructions before aborting (default: 10000000)
  --watch-reg REG         Filter PC trace to only lines where this register changes (e.g. SP, R0, LR)
  --dump-at 0xPC[:region] Dump memory region when PC first hits target (e.g. 0x080182CC:iwram)
  --audio-capture PATH    Capture audio to WAV file (stereo, 16-bit signed, 44100 Hz)
  --profile PATH          Dump cProfile stats to file
```

### Common usage

```bash
# Headless screenshot (most common for testing)
python3 /tmp/stripes.py --headless --frame=60 --screenshot /tmp/stripes.png

# Debug hang with PC trace
python3 /tmp/stripes.py --headless --max-instrs=50000 --pc-trace=/tmp/trace.txt

# Dump IWRAM at a specific PC
python3 /tmp/stripes.py --headless --dump-at=0x08004BF0:iwram
```

**NOTE:** There is no `--no-input` flag. Use `--headless` for headless mode.

## Single-ROM Testing

```bash
python3 scripts/run_tests.py --level 3 --rom stripes
```
Never run the full 91-ROM suite during active debugging — always test one ROM at a time with `--rom <name>`.

## mGBA on Headless Server

```bash
export SDL_VIDEODRIVER=offscreen
export SDL_AUDIODRIVER=dummy
export LD_LIBRARY_PATH="$PROJECT_ROOT/mgba/build:$PROJECT_ROOT/mgba/build/sdl:$LD_LIBRARY_PATH"
./mgba/build/sdl/mgba ...
```
All three env settings required. **DO NOT use** `SDL_VIDEODRIVER=dummy` (produces 33-byte segfault artifacts). **DO NOT use** `xvfb-run` alone (produces >1KB but all-black blank goldens). `SDL_VIDEODRIVER=offscreen` is the ONLY proven working backend for mGBA screenshot generation on a headless server. ALSA errors are harmless.

**Golden validation**: Before comparing screenshots, verify golden PNGs are >1KB. Goldens <1KB are segfault artifacts from broken mGBA setup, not valid reference images.

## Setup on New Machine

1. **Read `WORKPLAN.md` first** — pending work tracker and session reconciliation
2. **Read `docs/runtime-architecture.md` § "PPU Scanline & DMA Architecture"** — the 8 runtime invariants
3. **Read `docs/how-debug.md` "Known Runtime Bug Classes"** — DMA double-stepping and fast-forward DISPSTAT bugs
4. **Build:** `cargo build --release` (0 errors, 0 warnings)
5. **Verify one ROM:** `cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py && python3 /tmp/stripes.py --headless --frame=60 --screenshot /tmp/stripes.png`
6. **Fetch test ROMs:** `scripts/setup/download_test_roms.sh` (not in repo)
7. **Build mGBA:** see `README.md` (apply `mgba-custom-patches.diff` to upstream mGBA 0.11)
