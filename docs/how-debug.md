# GBA ROM Debug Skill

## Overview

This skill helps debug GBA ROM transpilation issues by systematically comparing transpiled output against mGBA golden screenshots.

## Prerequisites

- mGBA built: `./mgba/build/sdl/mgba`
- Transpiler built: `cargo build --release`
- Python with pygame and PIL installed

## Debug Workflow

### Quick Fix Strategy (Python First)

When you find a bug in the transpiled output:

1. **Modify the generated Python first** to verify the fix
2. **Test immediately** without waiting for Rust rebuild
3. **Once confirmed**, apply the fix to the Rust source
4. **Regenerate** and verify the fix is permanent

Example workflow:
```bash
# 1. Find bug in transpiled Python (e.g., wrong offset)
grep -n "registers\[1\] + 22" /tmp/rom.py

# 2. Fix in Python directly
sed -i 's/registers\[1\] + 22/registers\[1\] + 0/g' /tmp/rom.py

# 3. Test immediately
python3 /tmp/rom.py --headless --frame=1 --screenshot=/tmp/rom_fixed.png

# 4. Compare with golden
python3 -c "from PIL import Image; ..."

# 5. Once confirmed, fix Rust source
# Edit: crates/gbatopy-disasm/src/arm/mod.rs

# 6. Rebuild and regenerate
cargo build --release
cargo run --release -p gbatopy-cli -- pipeline --rom ...
```

### 1. Generate Golden Screenshot (mGBA)

```bash
# Create screenshot script for specific ROM
cat > /tmp/rom_screenshot.lua << 'EOF'
local name = "/tmp/rom_mgba"
local target_frame = 60
callbacks:add("frame", function()
    local current = emu:currentFrame()
    if current >= target_frame then
        emu:screenshot(name .. ".png")
        print("Screenshot captured at frame " .. current)
        os.exit(0)
    end
end)
print("Starting mGBA, will capture frame " .. target_frame)
EOF

# Run mGBA with script
./mgba/build/sdl/mgba -S /tmp/rom_screenshot.lua test_roms/roms/ROM_NAME.gba
```

### 2. Transpile ROM

```bash
cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/ROM_NAME.gba --output /tmp/rom.py
```

### 3. Run Transpiled Code

```bash
cd /tmp && python3 rom.py --headless --frame=60 --screenshot=/tmp/rom_transpiled.png
```

### 4. Compare Screenshots

```python
from PIL import Image

golden = Image.open('/tmp/rom_mgba.png')
transpiled = Image.open('/tmp/rom_transpiled.png')

golden_pixels = list(golden.getdata())
transpiled_pixels = list(transpiled.getdata())

diff_count = sum(1 for g, t in zip(golden_pixels, transpiled_pixels) if g != t)
total = len(golden_pixels)
diff_pct = (diff_count / total) * 100

print(f'Different pixels: {diff_count}/{total} ({diff_pct:.1f}%)')

# Count non-black pixels
def count_non_black(pixels):
    return sum(1 for p in pixels if sum(p[:3]) > 3)

print(f'Golden non-black: {count_non_black(golden_pixels)}')
print(f'Transpiled non-black: {count_non_black(transpiled_pixels)}')
```

### 5. Analyze Disassembly

```bash
cargo run --release -p gbatopy-cli -- disasm --input test_roms/roms/ROM_NAME.gba --output /tmp/rom_disasm.txt
```

Parse JSON to check instruction operands:
```python
import json
with open('/tmp/rom_disasm.txt') as f:
    data = json.load(f)

for inst in data:
    if 'STRH' in inst.get('opcode', ''):
        print(f"Address: {inst['address']:#x}, Opcode: {inst['opcode']}")
        for i, op in enumerate(inst.get('operands', [])):
            print(f"  Operand {i}: {op}")
```

### 6. Check Binary Encoding

```python
with open('test_roms/roms/ROM_NAME.gba', 'rb') as f:
    f.seek(0xe4)  # Address in ROM
    word = int.from_bytes(f.read(4), 'little')
    print(f'Word: {word:#010x}')
    print(f'Bits 11-8: {(word >> 8) & 0xF}')
    print(f'Bits 3-0: {word & 0xF}')
```

### 7. Trace Execution

```python
import sys
sys.path.insert(0, '.')
import rom as rom_module

# Initialize
rom_module.registers = [0] * 20
rom_module.registers[15] = 0x08000000
rom_module.cpsr = {'n': 0, 'z': 0, 'c': 0, 'v': 0}
rom_module.ROM_DATA = rom_module.load_rom_data()
rom_module.memory = rom_module.Memory()
rom_module.memory.rom = rom_module.ROM_DATA

# Execute and trace
for i in range(10000):
    pc = rom_module.registers[15]
    idx = (pc - 0x08000000) >> 2
    func = rom_module.dispatch_table.get(idx)
    if func is None:
        print(f'Unknown PC: 0x{pc:08X}')
        break
    func(rom_module.registers, rom_module.cpsr)
    
    # Trace key addresses
    if i % 100 == 0 or pc in [0x080000E4, 0x080000F4]:
        print(f'Instr {i}: PC=0x{pc:08X}, R0={rom_module.registers[0]}, R1={rom_module.registers[1]}')

# Check memory
print(f'Palette: {[rom_module.memory.read_u8(0x05000000 + i) for i in range(8)]}')
print(f'VRAM: {[rom_module.memory.read_u8(0x06000000 + i) for i in range(8)]}')
```

## Systematic Spin Diagnosis Workflow

Use this workflow when a generated ROM hangs or spins. It is the procedure that found and fixed every spin bug in this project's history.

### Step 1: Enable PC tracing

The generated runtime has built-in trace flags. Transpile and run with tracing:

```bash
cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/ROM.gba --output /tmp/ROM.py
cd /tmp && python3 ROM.py --headless --frame=60 --pc-trace=/tmp/ROM_trace.txt --trace-n=200 --max-instrs=5000
```

- `--pc-trace=FILE`: writes `ic PC R0 R1 R2 R3` per instruction to a file (buffered).
- `--trace-n=N`: prints the first N PCs to stdout for quick inspection.
- `--max-instrs=N`: aborts after N instructions instead of hanging for 20s.

### Step 2: Find the spin address

```bash
# Look at the trace tail — the last repeated PC is the spin address
tail -50 /tmp/ROM_trace.txt
```

If the PC bounces between two addresses, it is a copy/clear loop that never exits. If the PC is stuck at one address, an instruction is not advancing the PC.

### Step 3: Decode the opcode at the spin address

Do NOT guess the instruction. Decode it from the ROM:

```python
with open('test_roms/roms/ROM.gba', 'rb') as f:
    addr_offset = SPIN_ADDR - 0x08000000
    f.seek(addr_offset)
    word = int.from_bytes(f.read(4), 'little')
    print(f'Word: {word:#010x}')
```

Then run it through the disassembler to see what the transpiler thinks it is:

```bash
cargo run --release -p gbatopy-cli -- disasm --input test_roms/roms/ROM.gba --output /tmp/ROM_disasm.json
python3 -c "
import json
data = json.load(open('/tmp/ROM_disasm.json'))
for inst in data:
    if inst['address'] == SPIN_ADDR:
        print(f\"opcode={inst['opcode']} condition={inst.get('condition')} operands={inst['operands']}\")
        break
"
```

Compare the disassembler output against the GBATEK reference. If the opcode/condition/operands are wrong, the bug is in `crates/gbatopy-disasm/`. If the decode is correct but the generated Python is wrong, the bug is in `crates/gbatopy-cli/src/codegen/`.

### Step 4: Check dispatch routing

Most spin bugs are an instruction dispatched to the wrong handler. Check `arm7tdmi.py`:

- `execute_arm`: the if-elif chain that routes opcodes. MSR/MRS must be checked **before** the generic data-processing branch (`(instr & 0x0C000000) == 0`), because MSR shares opcode class bits with TST/TEQ/CMP/CMN.
- `execute_thumb`: the format-based dispatch. STRH/LDRH (format 9) must route to the extra load/store handler, not the generic load/store path.

### Step 5: Check condition codes

For conditional branches (BXEQ, BNE, etc.), verify the condition is preserved end-to-end:

- Disassembler: `inst.condition` field (e.g., `Some(Condition::Eq)`).
- Codegen `branch.rs`: must read `inst.condition` and emit `cpsr_check('EQ')`, not drop to unconditional `cpsr_check('AL')`.
- The disassembler stores `opcode = "BX"` (no suffix) with the condition in a separate field. Do NOT parse the opcode string for the condition suffix.

### Step 6: Check PC-relative offsets

Any read of R15 must apply the ARM pipeline offset:

- ARM mode: R15 reads as `PC + 8` (two instructions ahead).
- Thumb mode: R15 reads as `PC + 4` (two half-words ahead).

This affects `MOV Rd, R15`, `LDR Rd, [PC, #imm]`, `ADD Rd, PC, #imm`, and any operand that references R15.

### Step 7: Fix and verify

1. Fix the Rust codegen or interpreter.
2. `cargo build --release`.
3. Re-transpile: `cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/ROM.gba --output /tmp/ROM.py`.
4. Verify with the one-shot script: `./scripts/verify/verify_rom.sh ROM --no-golden`.

## Known Codegen Bug Classes (CHECK FIRST)

Before deep debugging, verify these common failure modes. They have caused the majority of spin/hang bugs in this project.

### Class 1: Dispatch routing (opcode → wrong handler)

**Symptom**: PC stuck at one address, infinite spin.
**Root cause**: An instruction's opcode class bits match a broader branch in the dispatch chain before the specific handler is checked.
**Known instances**:
- MSR CPSR routed to `exec_data_processing` (treated as TEQ) → PC never advanced.
- Thumb STRH routed to generic load/store instead of extra load/store handler.
**Check**: `arm7tdmi.py` `execute_arm` / `execute_thumb` dispatch order. Specific handlers (MSR/MRS, extra load/store) must be checked **before** generic branches.
**Test**: `python3 -m pytest crates/gbatopy-cli/assets/gba_runtime/tests/test_dispatch_audit.py`

### Class 2: Condition codes dropped

**Symptom**: Conditional branch executes unconditionally, causing infinite loops (e.g., copy loop never exits).
**Root cause**: The codegen reads `inst.opcode` (which is "BX" without suffix) and parses for a condition suffix that isn't there, defaulting to unconditional AL.
**Known instances**: BXEQ emitted as unconditional BX → copy loop never terminates.
**Check**: `crates/gbatopy-cli/src/codegen/instruction_codegen/branch.rs` — must use `inst.condition` field, not string parsing.
**Test**: `test_dispatch_audit.py::TestARMDispatchAudit::test_bxeq_preserves_condition`

### Class 3: PC-relative offset missing

**Symptom**: Return addresses, branch targets, or PC-relative loads are off by 8 (ARM) or 4 (Thumb).
**Root cause**: R15 reads don't apply the pipeline offset.
**Known instances**: `MOV R14, R15` wrote PC without +8 → wrong return address; LDR PC-relative ignored immediate offset.
**Check**: Any codegen path that reads `registers[15]` must add the pipeline offset before use.

### Class 4: Thumb bit-field masks wrong width

**Symptom**: Branch targets truncated, immediate values wrong magnitude.
**Root cause**: Thumb instruction formats use specific bit widths that are easy to mask incorrectly.
**Known instances**: Thumb B (format 18) offset masked with `0x3FF` (10-bit) instead of `0x7FF` (11-bit).
**Check**: `crates/gbatopy-disasm/src/thumb/` against GBATEK format tables.
**Test**: `test_dispatch_audit.py::TestThumbDispatchAudit::test_branch_offset_uses_11bit_mask`

### Class 5: Banked registers on MSR mode switch

**Symptom**: Registers corrupted after mode switch, subtle state errors.
**Root cause**: MSR changes processor mode (USR/SVC/IRQ/FIQ/etc.), which banks R13/R14 and SPSR. If the runtime doesn't switch register banks, subsequent reads/writes hit the wrong physical registers.
**Check**: `arm7tdmi.py` MSR handler must update `self.mode` and swap banked registers.
**Test**: `test_dispatch_audit.py::TestARMDispatchAudit::test_msr_cpsr_routes_to_status_transfer`

## Known Runtime Bug Classes

Runtime bugs are defects in the Python runtime layer (`crates/gbatopy-cli/assets/gba_runtime/`) rather than the Rust codegen. They typically manifest as incorrect PPU/DMA timing or memory access behavior.

### Class 1: DMA double-stepping (fallback interpreter + main loop)

**Symptom**: DMA transfers fire twice per scanline, exhausting the DMA source table by scanline ~94. Affine background parameters (BG2PD) plateau at 159, producing a vertically stretched gradient (observed in bgpd.gba).
**Root cause**: Both the fallback interpreter (`_interp_fallback`) and the main execution loop called `step_scanline()`. Each scanline advanced the PPU twice, firing HBlank DMA twice per scanline.
**Fix**: The fallback interpreter is now a pure CPU executor — it must NEVER call `step_scanline()`. The main loop is instruction-counted: it advances the PPU by one scanline for each `instr_per_scanline` CPU instructions executed.
**Files**: `crates/gbatopy-cli/assets/gba_runtime/dma.py` (`_do_transfer_single`), `crates/gbatopy-cli/src/pipeline_cmd.rs` (fallback refactoring)

### Class 2: Fast-forward DISPSTAT read (memory read methods)

**Symptom**: Tight IWRAM poll loops reading DISPSTAT cause the DMA source table to exhaust prematurely. In bgpd.gba, the ROM polls DISPSTAT in a tight loop; each read called `step_scanline()` up to 228 times.
**Root cause**: `read_u16` and `read_u32` in `memory.py` had a fast-forward path that called `self._ppu.step_scanline()` during DISPSTAT/VCount reads. A tight poll loop fired HBlank DMA hundreds of times per scanline.
**Fix**: Removed the fast-forward DISPSTAT reads from `memory.py`. The `_last_vcount_read` and `_last_dispstat_read` attributes were also removed. PPU stepping is now exclusively in the main loop.
**Files**: `crates/gbatopy-cli/assets/gba_runtime/memory.py` (`read_u16`, `read_u32`)

## Common Issues

### Issue 1: Wrong Immediate Offsets in STRH/LDRH

**Symptom**: STRH/LDRH write to wrong addresses (e.g., `registers[1] + 22` instead of `registers[1] + 0`)
**Root Cause**: Disassembler combines wrong bit fields for half-word immediate offset
- **WRONG**: `let imm5 = (word >> 3) & 0x1F` (bits 7-3) 
- **CORRECT**: `let imm4l = word & 0xF` (bits 3-0)
**Check**: Disassembly shows `ImmediateOffset(22)` instead of `ImmediateOffset(0)`
**Fix**: Check `crates/gbatopy-disasm/src/arm/mod.rs` - STRH/LDRH use bits 11-8 (high 4) and bits 3-0 (low 4), NOT bits 7-3
**Verification**: Binary encoding check - bits 3-0 should match expected offset

### Issue 2: Missing Functions in Dispatch Table (NOP Block Bug)

**Symptom**: Code jumps over initialization, registers have wrong values, loops skipped
**Root Cause**: Pipeline marks blocks as "NOP" and skips them in dispatch table
**Check**: Search dispatch table for missing addresses - `grep -n "0x0000040" rom.py`
**Fix**: Check `pipeline_cmd.rs` NOP detection logic - blocks with only PC advances are wrongly marked as NOP
**Workaround**: Manually add missing functions to dispatch table in generated Python
**Verification**: Execution trace shows PC jumping over setup code

### Issue 3: Loop Not Executing (Stall Detection)

**Symptom**: Only first loop completes, VRAM/tiles not written, frame renders too early
**Root Cause**: `max_inner_stalls = 10` breaks loops after 10 iterations
**Check**: Execution trace shows `Stalled at PC=...` after few iterations
**Fix**: Increase `max_inner_stalls` in generated Python (e.g., to 10000)
**Permanent Fix**: Update game loop template in Rust codegen
**Verification**: Trace shows loop completing all iterations (e.g., 32 iterations for tile loop)

### Issue 4: Frame Rendering Too Early

**Symptom**: Frame renders before initialization complete, black screen or partial graphics
**Root Cause**: `target_cycles_per_frame // 4` executes too few instructions before first render
**Check**: Compare frame 1 vs frame 60 - should be identical for static ROMs
**Fix**: Increase instructions per frame multiplier (e.g., `target_cycles_per_frame * 10`)
**Verification**: Frame 1 screenshot should match golden screenshot for static ROMs

### Issue 5: Wrong Immediate Values in ADD/MOV

**Symptom**: VRAM/palette addresses are wrong, graphics appear in wrong location
**Root Cause**: Immediate rotation/parsing bug in disassembler
**Check**: ADD instructions show `Immediate(2048)` instead of `Immediate(16384)`
**Fix**: Check immediate rotation calculation in disassembler
**Verification**: Binary encoding shows `rotate = ((word >> 8) & 0xF) * 2`, value = `((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF`

### Issue 6: Branch Skips Setup Code

**Symptom**: Loop executes but with wrong register values (e.g., R0=0 instead of expected value)
**Root Cause**: Branch target calculation wrong, or dispatch table missing intermediate functions
**Check**: Trace shows PC jumping from 0xF4 to 0x108, skipping 0xF8-0x104
**Fix**: Verify branch offset calculation and dispatch table completeness
**Verification**: Full execution trace showing all PC values between branch source and target

## Verification Commands

```bash
# Quick syntax check
./scripts/run-all-tests.sh

# Full visual verification
python3 scripts/verify/compare_screenshots.py -s /tmp/rom_mgba.png /tmp/rom_transpiled.png --threshold 30
```

## Key Addresses

- `0x04000000`: DISPCNT (Display Control)
- `0x04000008`: BG0CNT (Background Control)
- `0x05000000`: Palette RAM
- `0x06000000`: VRAM
- `0x06004000`: VRAM Tile Data
- `0x06000800`: VRAM Tile Map

## Tips

1. Always compare against mGBA golden screenshot
2. Check pixel counts, not just visual appearance
3. Trace execution for first 100-1000 instructions
4. Verify memory contents after each loop
5. Check dispatch table has all required functions
6. Test with `--frame=1` first, then increase if needed
