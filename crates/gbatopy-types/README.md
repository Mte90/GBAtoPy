# gbatopy-types

Shared type definitions used across all GBAtoPy pipeline crates.

## Overview

This crate provides the core type system for the GBA transpiler:

- **GbaType**: Type representations (I8, I16, I32, U8, U16, U32, Bool, Ptr, Array, Struct, Function, Void, Unknown)
- **TypeSource**: Origin tracking (Static, Oracle, Heuristic)
- **TypeInfo**: Type metadata with confidence scores
- **TypedIr**: IR combined with type information
- **ArmMode**: Processor mode (Arm, Thumb)
- **Condition**: ARM condition codes
- **IrValue**: IR values (constants, variables, registers, flags)
- **IrStatement**: IR operations (assign, store, load, branch, call, return, phi, nop, mode-switch)
- **IrBlock**: Basic blocks with statements and control flow
- **IrFunction**: Functions with blocks and mode switching
- **IrGlobal**: Global symbols with address and size
- **IrModule**: Module container (functions + globals)

## Build

```bash
cargo build --release
```

## Dependencies

- `serde` - Serialization/deserialization
- `serde_json` - JSON support
- `thiserror` - Error types
- `anyhow` - Error handling
- `log` - Logging
