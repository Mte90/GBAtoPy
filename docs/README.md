# GBAtoPy Documentation

Documentation for the GBA ROM-to-Python transpiler.

## Getting Started

- **[quickstart.md](quickstart.md)** — Build, run, and test the transpiler
- **[architecture.md](architecture.md)** — How the pipeline works
- **[reference/test-roms.md](reference/test-roms.md)** — Per-ROM verification matrix and summary counts
- **[roadmap.md](roadmap.md)** — Development roadmap and remaining work

## Debugging & Runtime

Read these when actively debugging a transpiled ROM or tracing PPU/memory behavior.

- **[how-debug.md](how-debug.md)** — Systematic debug workflow for GBA ROMs (Python-first edit cycle)
- **[runtime-architecture.md](runtime-architecture.md)** — Runtime architecture, memory management, address mapping (CRITICAL for codegen debugging)
- **[transpiler-reference.md](transpiler-reference.md)** — Generated Python file structure and API reference
- **[vram-initialization.md](vram-initialization.md)** — VRAM initialization patterns
- **[vram_rendering_verification.md](vram_rendering_verification.md)** — PPU rendering verification results across ROMs
- **[README_AUTO.md](README_AUTO.md)** — Auto-generated project overview (do not edit by hand)

## Design Documents

Per-component design specifications. These describe what each pipeline stage *should* do.

> **⚠️ Note:** Design documents reference old crate names (`pygba-*`). Actual crate names are `gbatopy-*` (e.g. `gbatopy-disasm`, `gbatopy-codegen`). See `Cargo.toml` for current workspace configuration.

| File | Description |
|------|-------------|
| [design/disassembler.md](design/disassembler.md) | ARM/Thumb disassembler design |
| [design/ir-lifter.md](design/ir-lifter.md) | IR lifting and optimization |
| [design/interrupts.md](design/interrupts.md) | GBA interrupt handling design |
| [design/type-recovery.md](design/type-recovery.md) | Type inference from trace data |
| [design/codegen.md](design/codegen.md) | Python code generation |
| [design/transpilation-patterns.md](design/transpilation-patterns.md) | Advanced transpilation patterns from GB Recompiled |

## Reference

Hardware specifications, instruction sets, and test ROM catalogs.

| File | Description |
|------|-------------|
| [reference/memory-map.md](reference/memory-map.md) | GBA memory map (BIOS, I/O, VRAM, etc.) |
| [reference/io-registers.md](reference/io-registers.md) | MMIO register reference |
| [reference/bios-swi.md](reference/bios-swi.md) | BIOS Software Interrupt handlers |
| [reference/arm-thumb-instructions.md](reference/arm-thumb-instructions.md) | ARM/Thumb instruction set reference |
| [reference/mgba-lua-api.md](reference/mgba-lua-api.md) | mGBA Lua scripting API |
| [reference/test-roms.md](reference/test-roms.md) | Test ROM catalog and descriptions |
| [reference/feature-coverage.md](reference/feature-coverage.md) | Feature coverage matrix |
| [reference/test-coverage.md](reference/test-coverage.md) | Test ROM coverage matrix |

## Testing

- **[testing-framework.md](testing-framework.md)** — Automated testing strategy, test ROM classification, implementation plan


