# Ghidra Static Analysis Scripts

These scripts provide a **static analysis oracle** for cross-validating the GBAtoPy transpiler's analysis.

## Prerequisites

- Ghidra 12.1.4 installed at `$GHIDRA_HOME/ghidra_12.1.4_PUBLIC` (or set `GHIDRA_HOME` environment variable)
- JDK 21+ (already installed)
- Ghidra GUI (`ghidraRun`) for interactive work

## Scripts

### `ghidra_functions.sh <rom_name>`

Imports and analyzes a GBA ROM with Ghidra, then provides instructions for extracting the function list.

```bash
./ghidra_functions.sh hello
```

**Output:** ROM imported to `$PROJECT_DIR/gbatopy/hello.gba` (default: `/tmp/ghidra-projects/gbatopy/hello.gba`)

**To extract functions:**
1. Run `ghidraRun` to open Ghidra GUI
2. Open project at `$PROJECT_DIR/gbatopy` (default: `/tmp/ghidra-projects/gbatopy`)
3. Double-click `hello.gba`
4. View > Symbol Table to see all discovered functions

### `ghidra_decode.sh <rom_name> <hex_addr>`

Provides guidance for disassembling at a specific address.

```bash
./ghidra_decode.sh hello 0x08000000
```

### `ghidra_blocks.sh <rom_name>`

Provides guidance for analyzing basic block boundaries.

```bash
./ghidra_blocks.sh hello
```

### `ghidra_decompile.sh <rom_name> <hex_addr>`

Provides guidance for decompiling a function at a given address.

```bash
./ghidra_decompile.sh hello 0x08000000
```

## GBA Processor Configuration

GBA uses ARM7TDMI (ARMv4T, big-endian byte order for ROM):
- **Processor:** `ARM:BE:32:v4t`
- **Base address:** `0x08000000`
- **Entry point:** `0x08000000`
- **Code modes:** Mixed ARM/Thumb — Ghidra tracks mode per function

## Cross-Validation Workflow

When debugging a static analysis bug (missing function, wrong basic block, instruction decode error):

1. **Import ROM with Ghidra:**
   ```bash
   ./ghidra_functions.sh <rom_name>
   ```

2. **Open in Ghidra GUI and compare:**
   - Symbol Table vs transpiler's dispatch table
   - Basic blocks vs transpiler's CFG
   - Disassembly vs transpiler's decode

3. **Identify discrepancies:**
   - Missing function = CFG bug in transpiler
   - Extra function = false positive in transpiler
   - Wrong boundary = basic block detection bug

## Limitations

Ghidra's headless mode in version 12.1.4 has limited scripting support. For full automation, consider:
- Using the Ghidra GUI interactively
- Porting scripts to Java (PyGhidra not available in headless mode)
- Using alternative tools like `arm-none-eabi-objdump` for simple disassembly

## Reinstallation

```bash
cd /tmp
wget https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/Ghidra_12.1.4_PUBLIC_20250205.zip
unzip Ghidra_12.1.4_PUBLIC_20250205.zip -d /opt/
ln -sf /opt/ghidra_12.1.4_PUBLIC /opt/ghidra
```