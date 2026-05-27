use crate::asset_extractor::extract_assets;
use crate::codegen::generate_instruction_python;
use crate::codegen::ppu::mode1::generate_mode1_rendering;
#[allow(unused_imports)]
use crate::ppu::generate_ppu_code;
use gbatopy_disasm::{
    operand::AddressingMode, operand::Operand, operand::ShiftAmount, Disassembler,
};
use std::fs;
use std::path::Path;

/// Convert ARM shift operator to Python operator
/// Returns the full expression like "r5 << 2" or "(r5 >> 2) | (r5 << 30) & 0xFFFFFFFF"
fn shift_to_python(
    reg: u8,
    shift_type: &gbatopy_disasm::operand::ShiftType,
    amount: &ShiftAmount,
) -> String {
    let amt = match amount {
        ShiftAmount::Immediate(n) => *n,
        _ => 0,
    };

    match shift_type {
        gbatopy_disasm::operand::ShiftType::Lsl => format!("r{} << {}", reg, amt),
        gbatopy_disasm::operand::ShiftType::Lsr => format!("r{} >> {}", reg, amt),
        gbatopy_disasm::operand::ShiftType::Asr => format!("r{} >> {}", reg, amt),
        gbatopy_disasm::operand::ShiftType::Ror => {
            format!(
                "(r{} >> {}) | (r{} << (32 - {})) & 0xFFFFFFFF",
                reg, amt, reg, amt
            )
        }
    }
}

pub fn run_pipeline(
    rom_path: &str,
    output_path: &str,
    _assets_dir: &Path,
    _use_ir: bool,
) -> Result<(), String> {
    let rom = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    eprintln!("Step 1: Disassembly");
    let mut disasm = Disassembler::new();
    let instructions = disasm.disassemble(&rom, 0x08000000);
    eprintln!("  Disassembled {} instructions", instructions.len());

    eprintln!("Step 2: Asset Extraction");
    let assets = extract_assets(&rom);
    eprintln!(
        "  Extracted {} colors, {} tiles, {} tilemap entries, {} wave bytes",
        assets.palette_data.len() / 2,
        assets.tile_data.len() / 32,
        assets.tilemap_data.len() / 2,
        assets.wave_data.len()
    );

    eprintln!("Step 3: Python Code Generation (direct from disassembly)");

    // EMBED RUNTIME CODE first
    eprintln!("  Embedding GBA runtime...");
    let mut code = String::new();
    let runtime_files = [
        "crates/gbatopy-cli/assets/templates/header.py",
        "crates/gbatopy-cli/assets/gba_runtime/memory.py",
        "crates/gbatopy-cli/assets/gba_runtime/ppu.py",
        "crates/gbatopy-cli/assets/gba_runtime/cpu.py",
        "crates/gbatopy-cli/assets/gba_runtime/interrupts.py",
        "crates/gbatopy-cli/assets/gba_runtime/timer.py",
        "crates/gbatopy-cli/assets/gba_runtime/dma.py",
        "crates/gbatopy-cli/assets/gba_runtime/input.py",
        "crates/gbatopy-cli/assets/gba_runtime/apu.py",
        "crates/gbatopy-cli/assets/gba_runtime/bios.py",
    ];

    code.push_str("# === GBA Runtime (embedded) ===\n\n");
    for file_path in &runtime_files {
        if let Ok(content) = std::fs::read_to_string(file_path) {
            // Filter out relative imports
            let filtered: String = content
                .lines()
                .filter(|line| {
                    let trimmed = line.trim();
                    !trimmed.starts_with("from .")
                        && !trimmed.starts_with("from gba_runtime.")
                        && !trimmed.starts_with("import gba_runtime")
                })
                .collect::<Vec<_>>()
                .join("\n");
            code.push_str(&filtered);
            code.push_str("\n\n");
            eprintln!(
                "    Included: {}",
                file_path.split('/').last().unwrap_or("")
            );
        } else {
            eprintln!("    WARNING: Could not read {}", file_path);
        }
    }
    code.push_str("# === End of Runtime ===\n\n");
    code.push_str("# Initialize runtime objects\n");
    code.push_str("memory = Memory()\n");
    code.push_str("ppu_instance = PPU(memory)\n");
    code.push_str("apu_instance = APU()\n\n");

    code.push_str(&generate_mode1_rendering());
    code.push_str("\n");

    use gbatopy_disasm::Operand;

    // Generate Python from disassembled instructions (runtime already embedded above)

    // Required imports
    code.push_str("import pygame\n");
    code.push_str("\n");

    code.push_str("# Global ARM registers (r0-r15, cpsr_n, cpsr_z, cpsr_c, cpsr_v, cpsr, spsr)\n");
    code.push_str("r0 = r1 = r2 = r3 = r4 = r5 = r6 = r7 = 0\n");
    code.push_str("r8 = r9 = r10 = r11 = r12 = r13 = r14 = 0\n");
    // r15 (PC) is set by header.py to 0x08000000 - do NOT reset here
    code.push_str("cpsr_n = 0  # Negative flag\n");
    code.push_str("cpsr_z = 0  # Zero flag\n");
    code.push_str("cpsr_c = 0  # Carry flag\n");
    code.push_str("cpsr_v = 0  # Overflow flag\n");
    code.push_str("cpsr = 0  # Current Program Status Register\n");
    code.push_str("spsr = 0  # Saved Program Status Register\n\n");

    // PASS 1: Identify branch target addresses (basic block boundaries)
    let mut branch_targets: std::collections::HashSet<u64> = std::collections::HashSet::new();
    let mut branch_addresses: std::collections::HashSet<u64> = std::collections::HashSet::new();

    // Collect all branch targets and branch instruction addresses
    for inst in &instructions {
        let addr = inst.address as u64;
        let opcode = inst.opcode.as_str();

        // Check if this is a branch instruction
        if opcode == "B" || opcode == "BL" || opcode == "BX" || opcode == "BLX" {
            branch_addresses.insert(addr);
            // Extract target address from operands
            for op in &inst.operands {
                if let Operand::Immediate(target) = op {
                    branch_targets.insert(*target as u64);
                }
            }
        }
    }
    // First instruction is always a block start
    branch_targets.insert(0x08000000);

    eprintln!(
        "  Found {} branch targets, {} branch instructions",
        branch_targets.len(),
        branch_addresses.len()
    );

    // PASS 2: Group instructions into basic blocks
    let mut func_groups: std::collections::BTreeMap<u64, Vec<&gbatopy_disasm::DecodedInstruction>> =
        std::collections::BTreeMap::new();

    let mut current_block_start: Option<u64> = None;
    let mut prev_addr: Option<u64> = None;

    for inst in &instructions {
        let addr = inst.address as u64;
        let is_thumb = addr % 2 == 1;
        let instr_size = if is_thumb { 2 } else { 4 };
        let next_expected = prev_addr.map(|a| a + instr_size);

        // Start new block if:
        // 1. This is a branch target, OR
        // 2. Previous instruction was a branch, OR
        // 3. Gap in addresses (not sequential)
        let should_start_new_block = branch_targets.contains(&addr)
            || prev_addr.map_or(true, |pa| {
                let is_branch = branch_addresses.contains(&pa);
                let is_sequential = next_expected == Some(addr);
                is_branch || !is_sequential
            });

        if should_start_new_block {
            current_block_start = Some(addr);
        }

        if let Some(block_start) = current_block_start {
            func_groups
                .entry(block_start)
                .or_insert_with(Vec::new)
                .push(inst);
        }

        prev_addr = Some(addr);
    }

    eprintln!(
        "  Generated {} basic blocks (merged from {} instructions)",
        func_groups.len(),
        instructions.len()
    );

    // Helper function to generate Python from ARM instruction

    // Embed ROM data FIRST (before GBA class needs it)
    code.push_str("# Full ROM data\n");
    code.push_str("ROM_DATA = bytearray([\n");
    for (i, byte) in rom.iter().enumerate() {
        if i > 0 {
            code.push_str(", ");
        }
        if i % 16 == 0 {
            code.push_str("\n    ");
        }
        code.push_str(&format!("0x{:02X}", byte));
    }
    code.push_str("\n])\n\n");

    // Embed wave data (audio samples)
    code.push_str("# Wave data for APU CH3\n");
    code.push_str("WAVE_DATA = bytearray([\n");
    for (i, &byte) in assets.wave_data.iter().enumerate() {
        if i > 0 {
            code.push_str(", ");
        }
        if i % 16 == 0 {
            code.push_str("\n    ");
        }
        code.push_str(&format!("0x{:02X}", byte));
    }
    code.push_str("\n])\n\n");

    // Embed sample metadata (start_addr, length, format)
    code.push_str("# Sample metadata: (start_addr, length, format)\n");
    code.push_str("SAMPLES = [\n");
    for (i, &(addr, len, fmt)) in assets.samples.iter().enumerate() {
        code.push_str(&format!("    (0x{:08X}, {}, {}),\n", addr, len, fmt));
    }
    code.push_str("]\n\n");

    // Generate sample playback function
    code.push_str("# Sample playback helper\n");
    code.push_str("def play_sample(addr):\n");
    code.push_str("    \"\"\"Play audio sample starting at given address in ROM_DATA\n");
    code.push_str("    Args: addr - address in ROM_DATA where sample starts\n");
    code.push_str("    \"\"\"\n");
    code.push_str("    if not SAMPLES: return\n");
    code.push_str("    for sample_addr, length, fmt in SAMPLES:\n");
    code.push_str("        if sample_addr == addr:\n");
    code.push_str("            # Extract sample data from ROM\n");
    code.push_str("            sample_bytes = ROM_DATA[sample_addr:sample_addr + length]\n");
    code.push_str("            # Convert 4-bit samples to 8-bit audio\n");
    code.push_str("            if fmt == 0:  # 4-bit format\n");
    code.push_str("                audio = bytearray()\n");
    code.push_str("                for i in range(0, length, 2):\n");
    code.push_str("                    if i + 1 < length:\n");
    code.push_str("                        lo, hi = sample_bytes[i], sample_bytes[i+1]\n");
    code.push_str("                        combined = (lo & 0x0F) | ((hi & 0x0F) << 4)\n");
    code.push_str("                        audio.extend([combined, combined >> 4])\n");
    code.push_str("            else:  # 8-bit format\n");
    code.push_str("                audio = sample_bytes\n");
    code.push_str("            # Generate audio stream (repeat sample)\n");
    code.push_str("            sample_rate = 32768\n");
    code.push_str("            duration = 0.1\n");
    code.push_str("            num_samples = int(sample_rate * duration)\n");
    code.push_str("            if audio:\n");
    code.push_str("                repeat_len = num_samples // len(audio)\n");
    code.push_str("                audio_stream = bytearray()\n");
    code.push_str("                for _ in range(repeat_len):\n");
    code.push_str("                    audio_stream.extend(audio)\n");
    code.push_str("                import array\n");
    code.push_str("                # Convert to signed 16-bit stereo\n");
    code.push_str("                samples = array.array('h')\n");
    code.push_str("                for b in audio_stream:\n");
    code.push_str("                    samples.append(int((b - 128) / 127.0 * 32767))\n");
    code.push_str("                    samples.append(int((b - 128) / 127.0 * 32767))\n");
    code.push_str("                # Play via pygame\n");
    code.push_str("                import pygame\n");
    code.push_str("                try:\n");
    code.push_str("                    sound = pygame.mixer.Sound(buffer=samples)\n");
    code.push_str("                    channel = pygame.mixer.Channel(2)\n");
    code.push_str("                    channel.play(sound)\n");
    code.push_str("                except:\n");
    code.push_str("                    pass\n");
    code.push_str("            break\n");
    code.push_str("\n");

    // Embed GBA memory class (Python version)
    code.push_str(
        r#"# GBA Memory Map Implementation
# Memory layout:
# - 0x00000000-0x00003FFF: BIOS ROM (16KB)
# - 0x02000000-0x0203FFFF: EWRAM (256KB)
# - 0x03000000-0x03007FFF: IWRAM (32KB)
# - 0x04000000-0x040003FF: MMIO registers
# - 0x05000000-0x050003FF: Palette RAM (1KB)
# - 0x06000000-0x06017FFF: VRAM (96KB)
# - 0x07000000-0x070003FF: OAM (1KB)
# - 0x08000000-0x09FFFFFF: ROM (up to 32MB)

class GBA:
    def __init__(self, rom_data):
        self.bios = bytearray(0x4000)       # 16KB
        self.ewram = bytearray(0x40000)     # 256KB
        self.iwram = bytearray(0x8000)      # 32KB
        self.mmio = {}                      # MMIO registers
        self.palette = bytearray(0x400)     # 1KB
        self.vram = bytearray(0x18000)      # 96KB
        self.oam = bytearray(0x400)         # 1KB
        self.rom = rom_data                 # up to 32MB

    def read_8(self, addr):
        if 0x00000000 <= addr <= 0x00003FFF:
            offset = addr - 0x00000000
            return self.bios[offset] if offset < len(self.bios) else 0
        elif 0x02000000 <= addr <= 0x0203FFFF:
            offset = addr - 0x02000000
            return self.ewram[offset] if offset < len(self.ewram) else 0
        elif 0x03000000 <= addr <= 0x03007FFF:
            offset = addr - 0x03000000
            return self.iwram[offset] if offset < len(self.iwram) else 0
        elif 0x04000000 <= addr <= 0x040003FF:
            offset = addr - 0x04000000
            return self.mmio.get(offset, 0)
        elif 0x05000000 <= addr <= 0x050003FF:
            offset = addr - 0x05000000
            return self.palette[offset] if offset < len(self.palette) else 0
        elif 0x06000000 <= addr <= 0x06017FFF:
            offset = addr - 0x06000000
            return self.vram[offset] if offset < len(self.vram) else 0
        elif 0x07000000 <= addr <= 0x070003FF:
            offset = addr - 0x07000000
            return self.oam[offset] if offset < len(self.oam) else 0
        elif 0x08000000 <= addr <= 0x09FFFFFF:
            offset = addr - 0x08000000
            return self.rom[offset] if offset < len(self.rom) else 0
        return 0

    def read_32(self, addr):
        b0 = self.read_8(addr)
        b1 = self.read_8(addr + 1)
        b2 = self.read_8(addr + 2)
        b3 = self.read_8(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)

    def write_8(self, addr, value):
        # Handle MMIO DMA control writes (detect FIFO C mode for DMA3)
        if 0x040000EC <= addr <= 0x040000EC:
            # DMA3 control register - check for FIFO C mode
            offset = addr - 0x04000000
            dma3_control = self.mmio.get(offset, 0)
            if dma3_control & 0x05000000:  # FIFO C trigger (bit 16)
                # Trigger FIFO C transfer for DMA3
                pass  # Handler in dma.py processes this
        
        if 0x02000000 <= addr <= 0x0203FFFF:
            offset = addr - 0x02000000
            if offset < len(self.ewram): self.ewram[offset] = value
        elif 0x03000000 <= addr <= 0x03007FFF:
            offset = addr - 0x03000000
            if offset < len(self.iwram): self.iwram[offset] = value
        elif 0x04000000 <= addr <= 0x040003FF:
            offset = addr - 0x04000000
            self.mmio[offset] = value  # MMIO side effects would be handled here
        elif 0x05000000 <= addr <= 0x050003FF:
            offset = addr - 0x05000000
            if offset < len(self.palette): self.palette[offset] = value
        elif 0x06000000 <= addr <= 0x06017FFF:
            offset = addr - 0x06000000
            if offset < len(self.vram): self.vram[offset] = value
        elif 0x07000000 <= addr <= 0x070003FF:
            offset = addr - 0x07000000
            if offset < len(self.oam): self.oam[offset] = value

    def write_32(self, addr, value):
        self.write_8(addr, value & 0xFF)
        self.write_8(addr + 1, (value >> 8) & 0xFF)
        self.write_8(addr + 2, (value >> 16) & 0xFF)
        self.write_8(addr + 3, (value >> 24) & 0xFF)

"#,
    );

    code.push_str("# Initialize Memory object for runtime\n");
    code.push_str("memory = Memory()\n\n");

    // Helper: check if instruction writes to r[15]
    fn writes_r15(inst: &gbatopy_disasm::DecodedInstruction) -> bool {
        let op = inst.opcode.as_str();
        // Only actual branch instructions change control flow via r15
        // (LDR/STR r15 are DATA writes to PC, not control flow changes)
        matches!(op, "B" | "BL" | "BX" | "BLX" | "CBZ" | "CBNZ")
    }

    // Helper: check if instruction reads r[15]
    // Used to decide if PC advance is needed before this instruction
    fn reads_r15(inst: &gbatopy_disasm::DecodedInstruction) -> bool {
        let op = inst.opcode.as_str();
        // Branches implicitly read PC
        if matches!(op, "B" | "BL" | "BX" | "BLX" | "CBZ" | "CBNZ") {
            return true;
        }
        // Check ALL operands for r15 references
        for op in &inst.operands {
            match op {
                Operand::Register(r) if *r == 15 => return true,
                Operand::ShiftedRegister { reg: r, .. } if *r == 15 => return true,
                Operand::MemoryAddress {
                    base: r, offset, ..
                } if *r == 15 => return true,
                _ => {}
            }
        }
        false
    }

    // Generate functions for each branch target, skip pure NOP blocks
    let mut non_nop_addrs: Vec<u64> = Vec::new();
    let mut block_function_code = String::new();
    let address_list: Vec<u64> = func_groups.keys().copied().collect();

    for (&func_start, func_instructions) in &func_groups {
        let func_name = format!("func_{:08X}", func_start);
        let is_thumb = func_start % 2 == 1;
        let block_len = func_instructions.len();
        let instr_size: u64 = if is_thumb { 2 } else { 4 };

        // Generate function body into a temp buffer
        let mut body = String::new();
        for (idx, inst) in func_instructions.iter().enumerate() {
            let py_stmt = generate_instruction_python(inst);
            body.push_str(&format!("    {}\n", py_stmt));
            let is_last = idx == block_len - 1;

            // Emit PC advance only when needed
            if !is_last && !writes_r15(inst) {
                if let Some(next_inst) = func_instructions.get(idx + 1) {
                    if reads_r15(next_inst) {
                        let next_addr = inst.address as u64 + instr_size;
                        body.push_str(&format!("    r[15] = 0x{:08X}\n", next_addr));
                    }
                }
            }
        }
        // End of block: always advance PC for dispatch loop
        let last_addr = func_instructions.last().unwrap().address as u64;
        if !writes_r15(func_instructions.last().unwrap()) {
            let end_addr = last_addr + instr_size;
            body.push_str(&format!("    r[15] = 0x{:08X}\n", end_addr));
        }

        // Check if block is pure NOP (only comments and PC advances)
        // A NOP block has no real register/memory operations
        let is_nop = body.lines().all(|l| {
            let t = l.trim();
            t.is_empty() || t.starts_with('#') || t.starts_with("r[15] = 0x")
        });

        if is_nop {
            // NOP block: skip generating function, will redirect func_map
            // NOP blocks are implicitly handled by chaining
        } else {
            block_function_code.push_str(&format!("\ndef {}():\n", func_name));
            block_function_code.push_str(&body);
            non_nop_addrs.push(func_start);
        }
    }

    // Write all block functions
    code.push_str(&block_function_code);

    // Generate func_map with NOP redirects
    code.push_str("func_map = {");
    for &func_start in &address_list {
        // Skip if this address is beyond ROM bounds (invalid branch target)
        if func_start >= 0x08000000 + 0x00FFFFFF {
            // Sanity check: within 16MB cartridge space
            // Find next non-NOP address at or after this address
            let target = non_nop_addrs.iter().find(|&&a| a >= func_start).copied();
            if let Some(target_addr) = target {
                code.push_str(&format!("0x{:08X}:func_{:08X},", func_start, target_addr));
            }
            // If no target found, skip this entry (invalid/out-of-bounds branch target)
        } else {
            let target = non_nop_addrs.iter().find(|&&a| a >= func_start).copied();
            if let Some(target_addr) = target {
                code.push_str(&format!("0x{:08X}:func_{:08X},", func_start, target_addr));
            }
            // If no target found, skip (this branch target has no valid function)
        }
    }
    code.push_str("}\n\n");

    // Add game loop (from generate_game_loop in pipeline.rs)
    code.push_str(&generate_game_loop());

    fs::write(output_path, &code).map_err(|e| format!("Failed to write output: {}", e))?;

    println!(
        "Generated {} lines of Python to {}",
        code.lines().count(),
        output_path
    );
    Ok(())
}

// Helper function to generate game loop (copied from cmds/pipeline.rs)
fn generate_game_loop() -> String {
    r#"
def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    def ror(v, a):
        a = a & 31
        return ((v >> a) | (v << (32 - a))) & 0xFFFFFFFF
    fc = 0; mi = 1000000; ic = 0
    print(f"PC=0x{r[15]:08X}")
    while ic < mi:
        pc = r[15]
        if pc not in func_map: print(f"Unknown PC: 0x{pc:08X}"); break
        func_map[pc](); ic += 1
        if r[15] == pc: print(f"Loop at 0x{pc:08X}"); break
        if ic % 10000 == 0: print(f"{ic} instrs")
        if frame_limit and fc >= frame_limit: break
        if ic % 1000 == 0: fc += 1
    print(f"Done: {ic} instrs")
    return fc

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    pygame.init()
    if not headless:
        screen = pygame.display.set_mode((240 * scale, 160 * scale))
        pygame.display.set_caption("GBAtoPy")
    else:
        screen = pygame.Surface((240 * scale, 160 * scale))
    clock = pygame.time.Clock()
    fc = 0; running = True; mi = 1000000; ic = 0
    print(f"PC=0x{r[15]:08X}")
    while running and fc < 10000:
        for e in pygame.event.get():
            if e.type == pygame.QUIT: running = False
        # Execute instructions for this frame (max 50000 instrs per frame)
        for _ in range(50000):
            pc = r[15]
            if pc not in func_map: break
            func_map[pc](); ic += 1
            if r[15] == pc: break
        # Always render frame and update APU
        # VBlank IRQ dispatch
        dispcnt = memory.read_u16(0x04000004)
        vblank_int_enabled = (dispcnt & 0x08) != 0
        if vblank_int_enabled:
            ie = memory.read_u16(0x04000200)
            if ie & 0x01:
                if (memory.read_u16(0x04000202) & 0x01) == 0:
                    memory.write_u16(0x04000202, memory.read_u16(0x04000202) | 0x01)
                    r[15] = memory.read_u32(0x03007FFC)
        apu_instance.update()
        fb = ppu_instance.framebuffer
        arr = np.array(fb, dtype=np.uint8).transpose(1, 0, 2)
        pygame.surfarray.blit_array(screen, arr)
        if not headless: pygame.display.flip()
        clock.tick(60); fc += 1
        if frame_limit and fc >= frame_limit: break
    if screenshot_path:
        pygame.image.save(screen, screenshot_path)
        print(f"Screenshot: {screenshot_path}")
    pygame.quit()
    return fc

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--screenshot", type=str)
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args()
    frames = run_with_pygame(headless=args.headless, frame_limit=args.frame, screenshot_path=args.screenshot, scale=args.scale)
    print(f"{frames} frames")
"#
    .to_string()
}
// Force rebuild ven 1 mag 2026, 13:30:36, CEST
