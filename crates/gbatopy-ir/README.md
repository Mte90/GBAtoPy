# gbatopy-ir

IR (Intermediate Representation) lifter for Game Boy Advance binaries.

Converts ARM/Thumb disassembled instructions into a structured IR with:

- **SSA form**: Single Static Assignment with versioned variables
- **Type inference engine**: Deduces register and variable types from observed values (MMIO pointers, VRAM, ROM addresses, etc.)
- **IR expression types**: Operations (arithmetic, logical, shifts, comparisons), constants, registers, variables, conditionals, phi functions
- **IR statement types**: Assignments, memory loads/stores, branches, calls, returns, phi nodes, mode switches, SWI

## Build

```bash
cargo build --release
```

## Architecture

- `lifter/`: ARM/Thumb to IR conversion
- `ops/`: IR operation codes (add, sub, and, or, shifts, comparisons, extensions)
- `types/`: GBA type system (I8, I16, I32, U8, U16, U32, Bool, Ptr, Array, Struct, Function, Void)
- `values/`: IR values (constants, variables, registers, flags)
- `ssa/`: SSA utility functions
- `optimize/`: IR optimization passes
- `inference/`: Type inference from oracle traces
- `module/`: Complete IR module (functions + globals)
