# Quickstart

## Prerequisites

- Rust toolchain (install via `rustup`)
- Python 3.10+ with pygame (`pip install pygame`)
- CMake, pkg-config, and development libraries for mGBA build
- GCC 15+ (for mGBA)

System packages (Debian/Ubuntu):

```bash
sudo apt install cmake pkg-config python3-pip liblua5.4-dev libsdl2-dev \
  libepoxy-dev libpng-dev libzip-dev libedit-dev libavcodec-dev \
  libavformat-dev libswscale-dev libswresample-dev libavutil-dev \
  libmagickwand-dev
```

## Build

### Rust pipeline

```bash
cargo build --release
```

This compiles all 6 crates: `gbatopy-disasm`, `gbatopy-mgba`, `gbatopy-ir`, `gbatopy-types`, `gbatopy-codegen`, `gbatopy-cli`.

### mGBA (for oracle tracing)

```bash
cd mgba
git checkout extend-lua
mkdir -p build && cd build
cmake .. -DBUILD_SDL=ON -DENABLE_LUA=ON
make -j$(nproc)
```

The binary lands at `mgba/build/sdl/mgba`.

## Usage

### Full pipeline: ROM to Python

```bash
cargo run --release -p gbatopy-cli -- pipeline --rom game.gba --output game.py
```

### Step-by-step

```bash
# Disassemble only
cargo run --release -p gbatopy-cli -- disasm --input game.gba --output disasm.json

# Lift to IR
cargo run --release -p gbatopy-cli -- lift --input disasm.json --output ir.json

# Generate Python from disassembly
cargo run --release -p gbatopy-cli -- generate --input game.gba --output game.py
```

### CLI commands

| Command | Description |
|---------|-------------|
| `disasm` | Disassemble ROM to JSON |
| `lift` | Lift disassembly to IR |
| `generate` | Generate Python from disassembly |
| `pipeline` | Run all stages end-to-end |
| `test` | Test a single ROM |
| `test-all` | Test all ROMs in a directory |
| `verify` | Verify output against reference |
| `benchmark` | Performance benchmarking |

### Test and verify

```bash
# Test a single ROM
cargo run --release -p gbatopy-cli -- test --rom test_roms/roms/arm.gba --frames 60 --screenshot /tmp/test.png

# Test all ROMs
cargo run --release -p gbatopy-cli -- test-all --rom-dir test_roms/roms --frames 10

# Verify against reference
cargo run --release -p gbatopy-cli -- verify --rom test_roms/roms/arm.gba --frames 100 --diff

# Benchmark
cargo run --release -p gbatopy-cli -- benchmark --rom test_roms/roms/arm.gba --frames 1000
```

### Run the generated Python

```bash
python3 game.py

# Headless mode (for CI)
python3 game.py --headless --frame 100

# Take a screenshot
python3 game.py --headless --frame 60 --screenshot output.png
```

The output file is self-contained. The only dependency is `pygame`. It loads asset files (`palette.bin`, `tiles.bin`, `sprites.bin`, `tilemap.bin`) from the same directory if they exist.

## Test ROMs

### Download

```bash
bash scripts/setup/download_and_organize_roms.sh
```

This downloads 18 test suites and organizes them:
- `test_roms/roms/` — 39 `.gba` files
- `test_roms/sources/` — source code and documentation

Test ROMs are not included in the repository. Use the download script to obtain them.

## Oracle Tracing

Oracle tracing uses mGBA with Lua scripts to capture execution data:

```bash
# Manual oracle trace
mgba/build/sdl/mgba -L scripts/lua/oracle_trace.lua test_roms/roms/arm.gba
```

Lua scripts in `scripts/lua/`:

| Script | Purpose |
|--------|---------|
| `oracle_trace.lua` | Captures register state, memory accesses, execution path |
| `screenshot.lua` | Captures frames for visual comparison |
| `test_api.lua` | Tests the extended Lua API surface |

## Project Layout

```
GBAtoPy/
├── Cargo.toml                    # Workspace definition
├── crates/
│   ├── gbatopy-cli/              # CLI driver + runtime assets
│   │   └── assets/
│   │       ├── gba_runtime/      # Python runtime modules (PPU, APU, Memory, etc.)
│   │       └── templates/        # Python code templates
│   ├── gbatopy-disasm/           # ARM/Thumb disassembler
│   ├── gbatopy-mgba/             # mGBA oracle interface
│   ├── gbatopy-ir/               # IR lifting + optimization
│   ├── gbatopy-types/            # Shared type definitions
│   └── gbatopy-codegen/          # Python code generation
├── scripts/
│   ├── lua/                      # mGBA Lua scripts
│   └── setup/                    # Download/organize scripts
├── test_roms/
│   ├── roms/                     # Test .gba files (downloaded)
│   └── sources/                  # Source code per suite
├── mgba/                         # mGBA fork (extend-lua branch)
└── docs/                         # Documentation
```

## Troubleshooting

**Build fails with "linker `cc` not found"**
Install gcc: `sudo apt install build-essential`

**mGBA build fails on Lua**
Ensure `liblua5.4-dev` is installed and cmake finds it: `cmake .. -DENABLE_LUA=ON -DLUA_INCLUDE_DIR=/usr/include/lua5.4`

**Generated Python shows black screen**
This is a known issue. The codegen does not yet strip condition code suffixes from instruction mnemonics, producing ~603 `pass` stubs. The PPU also needs fixes to read pixel data from shared memory instead of static arrays. See `docs/status.md` for details.

**`cargo run` says "no such command: pipeline"**
Make sure you're using `--` to separate cargo args from CLI args: `cargo run --release -p gbatopy-cli -- pipeline --rom ...`

**Python crashes on `import pygame`**
Install pygame: `pip install pygame`
