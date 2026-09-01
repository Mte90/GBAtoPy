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

```bash
# Step A: Generate golden screenshot with mGBA
./mgba/build/sdl/mgba -S scripts/screenshot/screenshot.lua test_roms/roms/stripes.gba

# Step B: Generate transpiled screenshot
cd /tmp && python3 stripes.py --headless --frame=60 --screenshot /tmp/stripes_transpiled.png

# Step C: Compare (PASS if <30% difference)
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

## Single-ROM Testing

```bash
python3 scripts/run_tests.py --level 3 --rom stripes
```
Never run the full 66-ROM suite during active debugging — always test one ROM at a time with `--rom <name>`.

## mGBA on Headless Server

```bash
export LD_LIBRARY_PATH="/home/d.scasciafratte/gbatopy/mgba/build:/home/d.scasciafratte/gbatopy/mgba/build/sdl:$LD_LIBRARY_PATH"
export SDL_AUDIODRIVER=dummy
xvfb-run -a -s "-screen 0 640x480x24" ./mgba/build/sdl/mgba ...
```
All three env settings required. `SDL_VIDEODRIVER=dummy` alone produces empty 33-byte PNGs. ALSA errors are harmless.

## Setup on New Machine

1. **Read `todo.md` first** — current debug state, architecture changes, knowledge not in code comments
2. **Read `docs/runtime-architecture.md` § "PPU Scanline & DMA Architecture"** — the 5 runtime invariants
3. **Read `docs/how-debug.md` "Known Runtime Bug Classes"** — DMA double-stepping and fast-forward DISPSTAT bugs
4. **Build:** `cargo build --release` (0 errors, 0 warnings)
5. **Verify one ROM:** `cargo run -p gbatopy-cli -- pipeline --rom test_roms/roms/stripes.gba --output /tmp/stripes.py && python3 /tmp/stripes.py --headless --frame=60 --screenshot /tmp/stripes.png`
6. **Fetch test ROMs:** `scripts/setup/download_test_roms.sh` (not in repo)
7. **Build mGBA:** see `README.md` (branch: extend-lua)
