# gbatopy-disasm

ARM/Thumb instruction decoder for Game Boy Advance ROM analysis.

## Purpose

Decodes GBA ROM binaries into human-readable ARM and Thumb instructions. Takes raw binary input and produces a structured list of decoded instructions with operands, conditions, and flags.

## Input

- ROM binary data (`&[u8]`)
- Base address (typically `0x08000000` for GBA)

## Output

- `DecodedInstruction` - Each instruction contains:
  - `address`: Memory location
  - `opcode`: Mneumonic (e.g. `ADD`, `LDR`, `B`, `BL`)
  - `operands`: Instruction operands (registers, immediates, memory addresses)
  - `condition`: ARM condition code (Thumb is always `None`)
  - `mode`: `ArmMode::Arm` or `ArmMode::Thumb`
  - `raw`: Original opcode value
  - `sets_flags`: Whether instruction updates CPSR flags
  - `width`: Instruction width (4 bytes for ARM, 2 bytes for Thumb)
  - `is_data`: Marker for data regions

## Key Types

- `DecodedInstruction` - Decoded instruction structure
- `ArmDecoder` - ARM 32-bit instruction decoder
- `ThumbDecoder` - Thumb 16-bit instruction decoder
- `Disassembler` - Main entry point with `disassemble()` and `detect_functions()`

## Build

```bash
cargo build --release
```
