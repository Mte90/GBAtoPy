# Ghidra Static Analysis Oracle

> Extracted from `AGENTS.md`. Ghidra is used as a static analysis oracle for cross-validating the transpiler's static analysis.

Ghidra 12.1.4 is installed at `/opt/ghidra/ghidra_12.1.4_PUBLIC` and used as a **static analysis oracle** — ground truth for cross-validating the transpiler's static analysis (function discovery, basic-block boundaries, instruction decode).

## When to Use Ghidra

| Scenario | Command | Purpose |
|----------|---------|---------|
| Function discovery cross-check | `scripts/ghidra/ghidra_functions.sh <rom>` | Import ROM and compare Ghidra's symbol table vs our dispatch table — every missing function is a CFG bug |
| Instruction decode oracle | `scripts/ghidra/ghidra_decode.sh <rom> <addr>` | When debugging a bit-field extraction bug, compare our decode vs Ghidra's disassembly |
| Basic block cross-check | `scripts/ghidra/ghidra_blocks.sh <rom>` | Diff basic-block boundaries — catches fall-through and cross-mode bugs |
| Timeout/hang root cause | `scripts/ghidra/ghidra_decompile.sh <rom> <addr>` | Decompile the hang loop to understand what the ROM is waiting on |

## Ghidra Helper Scripts

All scripts in `scripts/ghidra/`:
- `ghidra_functions.sh <rom>` — imports ROM and provides instructions for symbol table extraction
- `ghidra_decode.sh <rom> <addr>` — provides guidance for disassembling at an address
- `ghidra_blocks.sh <rom>` — provides guidance for basic block analysis
- `ghidra_decompile.sh <rom> <addr>` — provides guidance for decompiling a function

See `scripts/ghidra/README.md` for detailed usage.

## GBA Processor Configuration

GBA uses ARM7TDMI (ARMv4T, big-endian byte order for ROM):
- **Processor:** `ARM:BE:32:v4t`
- **Base address:** `0x08000000`
- **Entry point:** `0x08000000`
- The GBA has mixed ARM/Thumb code — Ghidra tracks mode per function, which is exactly the cross-mode validation we need

## Cross-Validation Workflow

When debugging a static analysis bug (missing function, wrong basic block, instruction decode error):

1. **Import ROM with Ghidra:**
   ```bash
   ./scripts/ghidra/ghidra_functions.sh <rom_name>
   ```

2. **Open in Ghidra GUI:**
   ```bash
   ghidraRun
   # Open project at /tmp/ghidra-projects/gbatopy
   ```

3. **Compare Symbol Table vs transpiler's dispatch table:**
   - Ghidra: View > Symbol Table
   - Transpiler: `gbatopy transpile <rom> --print-dispatch 2>/dev/null | grep '^FUNC'`
   - Every symbol in Ghidra but not in ours is a missing function = CFG bug
   - Every symbol in ours but not in Ghidra's is a false positive = heuristic over-reach

4. **For instruction decode bugs:**
   - Navigate to address in Ghidra GUI
   - Compare Ghidra's disassembly with transpiler output
   - Identify bit-field extraction errors

This replaces manual disassembly and guesswork with ground-truth comparison.

## Installation

Ghidra is installed at `$GHIDRA_HOME/ghidra_12.1.4_PUBLIC` (or `/opt/ghidra` by default). Requires JDK 21+. The `analyzeHeadless` binary is at `$GHIDRA_HOME/ghidra_12.1.4_PUBLIC/support/analyzeHeadless`.

**Test verification:**
```bash
"${GHIDRA_HOME:-/opt/ghidra}"/ghidra_12.1.4_PUBLIC/support/analyzeHeadless /tmp/test testProj \
  -import "${PROJECT_ROOT:-$(pwd)}/test_roms/roms/hello.gba" \
  -processor ARM:BE:32:v4t \
  2>&1 | grep -E "Total Time|Analysis succeeded"
```

Expected output: `Total Time   1 secs` and `Analysis succeeded`.

**To reinstall:**
```bash
cd /tmp
wget https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/Ghidra_12.1.4_PUBLIC_20250205.zip
unzip Ghidra_12.1.4_PUBLIC_20250205.zip -d /opt/
ln -sf /opt/ghidra_12.1.4_PUBLIC /opt/ghidra
```

## Limitations

Ghidra's headless mode in version 12.1.4 has limited scripting support (PyGhidra/Jython not available). For full automation:
- Use the Ghidra GUI interactively
- Or port scripts to Java
- Or use alternative tools like `arm-none-eabi-objdump` for simple disassembly
