# GBAtoPy Documentation

Documentation for the GBA ROM-to-Python transpiler.

## Companion Docs (Project Root)

- **[RUNBOOK.md](../RUNBOOK.md)** — Build, test, verify, debug commands — copy-pasteable
- **[AGENTS.md](../AGENTS.md)** — Project rules, workflows, and non-negotiable constraints

## Getting Started

| File | Description |
|------|-------------|
| [quickstart.md](quickstart.md) | Build, run, and test the transpiler |
| [architecture.md](architecture.md) | How the pipeline works |
| [roadmap.md](roadmap.md) | Development roadmap and remaining work |

## Reference

Hardware specifications and consolidated technical reference.

| File | Description |
|------|-------------|
| [hardware-reference.md](hardware-reference.md) | CPU, display, memory map, PPU modes — consolidated reference |
| [reference/memory-map.md](reference/memory-map.md) | GBA memory map (BIOS, I/O, VRAM, etc.) |
| [reference/io-registers.md](reference/io-registers.md) | MMIO register reference |
| [reference/bios-swi.md](reference/bios-swi.md) | BIOS Software Interrupt handlers |
| [reference/arm-thumb-instructions.md](reference/arm-thumb-instructions.md) | ARM/Thumb instruction set reference |
| [reference/gba-ppu-reference.md](reference/gba-ppu-reference.md) | PPU detailed reference |
| [reference/mgba-lua-api.md](reference/mgba-lua-api.md) | mGBA Lua scripting API |

## Architecture

Runtime and transpiler design documents.

| File | Description |
|------|-------------|
| [runtime-architecture.md](runtime-architecture.md) | PPU scanline & DMA architecture, _map_address() |
| [codegen-pitfalls.md](codegen-pitfalls.md) | 13 documented codegen bug classes |
| [transpiler-reference.md](transpiler-reference.md) | Generated Python file structure and API reference |
| [vram-initialization.md](vram-initialization.md) | VRAM initialization patterns |
| [vram_rendering_verification.md](vram_rendering_verification.md) | PPU rendering verification results across ROMs |

## Debugging

Workflows and troubleshooting guides.

| File | Description |
|------|-------------|
| [how-debug.md](how-debug.md) | Systematic debug workflow for GBA ROMs (Python-first edit cycle) |

## Status

Test results, coverage matrices, and feature tracking.

| File | Description |
|------|-------------|
| [reference/test-roms.md](reference/test-roms.md) | Per-ROM pass/fail matrix |
| [reference/test-coverage.md](reference/test-coverage.md) | Test ROM coverage matrix |
| [reference/feature-coverage.md](reference/feature-coverage.md) | Feature coverage matrix |

## Testing

| File | Description |
|------|-------------|
| [testing-framework.md](testing-framework.md) | Automated testing strategy, test ROM classification, implementation plan |

## Design (Legacy)

> **⚠️ Note:** Design documents reference old crate names (`pygba-*`). Actual crate names are `gbatopy-*` (e.g. `gbatopy-disasm`, `gbatopy-codegen`). See `Cargo.toml` for current workspace configuration.

| File | Description |
|------|-------------|
| [design/disassembler.md](design/disassembler.md) | ARM/Thumb disassembler design |
| [design/ir-lifter.md](design/ir-lifter.md) | IR lifting and optimization |
| [design/interrupts.md](design/interrupts.md) | GBA interrupt handling design |
| [design/type-recovery.md](design/type-recovery.md) | Type inference from trace data |
| [design/codegen.md](design/codegen.md) | Python code generation |
| [design/transpilation-patterns.md](design/transpilation-patterns.md) | Advanced transpilation patterns from GB Recompiled |
| [feature-gaps.md](feature-gaps.md) | Known feature gaps and deferrals |


