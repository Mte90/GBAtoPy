# GBAtoPy Documentation

Documentation for the GBA ROM-to-Python transpiler.

## Getting Started

- **[quickstart.md](quickstart.md)** — Build, run, and test the transpiler
- **[architecture.md](architecture.md)** — How the pipeline works
- **[status.md](status.md)** — Current implementation status per component

## Design Documents

Per-component design specifications. These describe what each pipeline stage *should* do.

| File | Description |
|------|-------------|
| [design/disassembler.md](design/disassembler.md) | ARM/Thumb disassembler design |
| [design/oracle.md](design/oracle.md) | mGBA oracle trace collection |
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
| [reference/test-coverage.md](reference/test-coverage.md) | Test ROM coverage matrix |

## Architecture



## Roadmap

- **[roadmap.md](roadmap.md)** — Development roadmap and remaining work

## Attribution

The Python runtime is derived from [PyBoyAdvance](https://github.com/williamckha/PyBoyAdvance) (MIT licensed).
