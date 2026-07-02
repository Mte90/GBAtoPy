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
