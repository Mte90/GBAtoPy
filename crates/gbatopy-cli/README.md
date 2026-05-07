# gbatopy-cli

Main CLI binary for GBAtoPy - transpile Game Boy Advance ROMs to playable Python games.

## What it does

This crate provides the main binary that orchestrates Game Boy Advance ROM analysis and transpilation:

- **Disassemble** GBA ROM machine code to structured JSON
- **Lift** disassembly into intermediate representation (IR)
- **Generate** standalone Python files that run the ROM with pygame
- **Pipeline** runs the full workflow in one command

The CLI embeds the complete GBA hardware emulation runtime for Python, so generated files are self-contained.

## Build

```bash
cargo build --release
```

## Usage

```bash
# Full pipeline: ROM → Python (recommended)
cargo run --release -- generate --input <rom.gba> --output <output.py>

# Full pipeline with explicit ROM path
cargo run --release -- generate --input <rom.gba> --output <output.py> --rom <rom.gba>

# Differential mode (run alongside original ROM for verification)
cargo run --release -- generate --input <rom.gba> --output <output.py> --diff

# Step-by-step: Disassemble only
cargo run --release -- disasm --input <rom.gba> --output <disasm.json>

# Step-by-step: Lift to IR
cargo run --release -- lift --input <disasm.json> --output <ir.json>

# Run full pipeline (disasm → lift → generate)
cargo run --release -- pipeline --input <rom.gba> --output <output.py>

# Run feature tests
cargo run --release -- test sprite
cargo run --release -- test dma
cargo run --release -- test mode5
cargo run --release -- test bios
cargo run --release -- test all

# Verify output against reference
cargo run --release -- verify registers
cargo run --release -- verify memory
cargo run --release -- verify screenshot
cargo run --release -- verify regression

# Benchmark specific target or all
cargo run --release -- benchmark
cargo run --release -- benchmark sprite
```

## Output

The `generate` command produces a self-contained Python file that:

1. Embeds the transpiled GBA code as Python functions
2. Includes a complete GBA hardware emulator in pure Python
3. Loads assets from `.bin` files (palette, tiles, sprites, tilemap)
4. Provides a `pygame`-driven game loop with input handling
5. Supports headless mode (`--headless`), frame-limited runs (`--frame N`), benchmark mode (`--benchmark`), and screenshot capture (`--screenshot PATH`)

## Example Flow

```bash
# Transpile a ROM to Python
cargo run --release -- generate --input game.gba --output game.py

# Run the generated Python file
python3 game.py

# Run in headless mode (for CI/CD)
python3 game.py --headless --frame 100

# Take a screenshot
python3 game.py --screenshot final_frame.png
```

## Dependencies

- Rust toolchain (edition 2021)
- Python 3.x for runtime and generated output
- Pygame (for runtime execution of generated Python)

## Subcrates

| Crate | Purpose |
|-------|--------|
| `gbatopy-disasm` | ARM/Thumb disassembler for GBA ROMs |
| `gbatopy-ir` | Intermediate representation for transpilation |
| `gbatopy-codegen` | Python code generator from IR |
| `gbatopy-mgba` | Mgba emulator integration for branch/trace analysis |
| `gbatopy-types` | Shared type definitions |


- `gbatopy-disasm`: ARM/Thumb disassembler for GBA ROMs
- `gbatopy-ir`: Intermediate representation for transpilation
- `gbatopy-codegen`: Python code generator from IR
- `gbatopy-mgba`: Mgba emulator integration for branch/trace analysis
- `gbatopy-types`: Shared type definitions
