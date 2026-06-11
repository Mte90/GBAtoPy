#![allow(dead_code, unused_variables)]
use crate::asset_extractor::extract_assets;
use crate::codegen::generate_instruction_python;
#[allow(unused_imports)]
use crate::ppu::generate_ppu_code;
use gbatopy_disasm::{
    operand::AddressingMode, operand::Operand, operand::ShiftAmount, CfgBuilder, Disassembler,
};
use std::fs;
use std::path::Path;
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};

/// Feature flags for stripping unused hardware features
/// These can be auto-detected from ROM or manually overridden via CLI
#[derive(Default, Clone)]
pub struct FeatureFlags {
    /// Include audio (APU) - enabled by default
    pub audio: bool,
    /// Include IRQ/interrupt handling - enabled by default
    pub irq: bool,
    /// Include timer hardware - enabled by default
    pub timers: bool,
    /// Include DMA controller - enabled by default
    pub dma: bool,
    /// Enable numba JIT compilation - enabled by default
    pub numba: bool,
}

impl FeatureFlags {
    /// Create new feature flags with all features enabled
    pub fn all_enabled() -> Self {
        Self {
            audio: true,
            irq: true,
            timers: true,
            dma: true,
            numba: true,
        }
    }

    /// Detect which features are used by scanning the ROM for MMIO accesses
    /// This analyzes the disassembled instructions to find hardware register usage
    pub fn detect_from_instructions(instructions: &[gbatopy_disasm::DecodedInstruction]) -> Self {
        let mut flags = Self::all_enabled();

        // MMIO address ranges for different hardware features
        // Audio: 0x04000060-0x0400008F (SOUNDCNT_L, SOUNDCNT_H, SOUNDCNT_X, etc.)
        const AUDIO_START: u32 = 0x04000060;
        const AUDIO_END: u32 = 0x0400008F;

        // IRQ: 0x04000200-0x04000208 (IE, IF, IME)
        const IRQ_START: u32 = 0x04000200;
        const IRQ_END: u32 = 0x04000208;

        // Timers: 0x04000100-0x0400010F (TM0CNT_L, TM0CNT_H, TM1CNT_L, etc.)
        const TIMERS_START: u32 = 0x04000100;
        const TIMERS_END: u32 = 0x0400010F;

        // DMA: 0x040000B0-0x040000CF (DMA0SAD, DMA0DAD, DMA0CNT_L, etc.)
        const DMA_START: u32 = 0x040000B0;
        const DMA_END: u32 = 0x040000CF;

        // Scan all instructions for MMIO register accesses
        for inst in instructions {
            // Check all operands for immediate values in MMIO ranges
            for op in &inst.operands {
                match op {
                    Operand::Immediate(addr) => {
                        let addr = *addr;
                        // Check if address is in any MMIO range
                        if (AUDIO_START..=AUDIO_END).contains(&addr) {
                            flags.audio = true;
                        }
                        if (IRQ_START..=IRQ_END).contains(&addr) {
                            flags.irq = true;
                        }
                        if (TIMERS_START..=TIMERS_END).contains(&addr) {
                            flags.timers = true;
                        }
                        if (DMA_START..=DMA_END).contains(&addr) {
                            flags.dma = true;
                        }
                    }
                    // Also check memory addresses (base register + offset)
                    Operand::MemoryAddress { base: _, offset, .. } => {
                        if let AddressingMode::ImmediateOffset(off) = offset {
                            let addr = *off as u32;
                            if (AUDIO_START..=AUDIO_END).contains(&addr) {
                                flags.audio = true;
                            }
                            if (IRQ_START..=IRQ_END).contains(&addr) {
                                flags.irq = true;
                            }
                            if (TIMERS_START..=TIMERS_END).contains(&addr) {
                                flags.timers = true;
                            }
                            if (DMA_START..=DMA_END).contains(&addr) {
                                flags.dma = true;
                            }
                        }
                    }
                    _ => {}
                }
            }
        }

        // Also check for SWI calls that might indicate feature usage
        for inst in instructions {
            let opcode = inst.opcode.as_str();
            if opcode == "SWI" || opcode == "svc" {
                // SWI numbers can indicate BIOS function usage
                // Common SWI numbers: 0x00-0x1F are common, but we conservatively
                // don't assume they mean specific hardware is used
                // The MMIO scan above is more reliable
            }
        }

        flags
    }
}

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
    feature_flags: Option<FeatureFlags>,
    minify: bool,
) -> Result<(), String> {
    let rom = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    let reachable: Vec<u32>;
    let branch_targets: Vec<u32>;
    
    if rom.len() > 1024 * 1024 {
        eprintln!("Step 1: CFG-based Disassembly (large ROM)");
        let mut cfg = CfgBuilder::new();
        cfg.build_from_entry(&rom, 0x08000000);
        reachable = cfg.get_reachable_addresses().to_vec();
        branch_targets = cfg.branch_targets.clone();
        eprintln!("  CFG found {} reachable addresses", reachable.len());
    } else {
        eprintln!("Step 1: Full Disassembly (small ROM)");
        let mut disasm = Disassembler::new();
        reachable = disasm.disassemble(&rom, 0x08000000).into_iter().map(|i| i.address).collect();
        branch_targets = vec![];
        eprintln!("  Disassembled {} instructions", reachable.len());
    }
    
    if (reachable.len()) < 10 {
        eprintln!("  DEBUG: reachable addresses:");
        for a in reachable.iter().take(20) {
            eprintln!("    0x{:08X}", a);
        }
        eprintln!("  DEBUG: branch targets:");
        for t in branch_targets.iter().take(20) {
            eprintln!("    0x{:08X}", t);
        }
    }
    
    // Disassemble only reachable addresses (no linear sweep on large ROMs)
    let mut disasm = Disassembler::new();
    let instructions = disasm.selective_disassemble(&rom, &reachable);
    eprintln!("  Disassembled {} reachable instructions", instructions.len());

    // Detect or use provided feature flags
    let flags = feature_flags.unwrap_or_else(|| {
        eprintln!("  Auto-detecting features...");
        FeatureFlags::detect_from_instructions(&instructions)
    });
    eprintln!(
        "  Features: audio={}, irq={}, timers={}, dma={}",
        flags.audio, flags.irq, flags.timers, flags.dma
    );

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

    // EMBED RUNTIME CODE first (conditionally based on feature flags)
    eprintln!("  Embedding GBA runtime...");
    let mut code = String::new();

    // Core modules - always included
    let core_files = [
        "crates/gbatopy-cli/assets/templates/header.py",
        "crates/gbatopy-cli/assets/gba_runtime/memory.py",
        "crates/gbatopy-cli/assets/gba_runtime/ppu.py",
        "crates/gbatopy-cli/assets/gba_runtime/cpu.py",
        "crates/gbatopy-cli/assets/gba_runtime/arm7tdmi.py",
        "crates/gbatopy-cli/assets/gba_runtime/input.py",
        "crates/gbatopy-cli/assets/gba_runtime/bios.py",
    ];

    // Optional modules - included based on feature flags
    let mut optional_files = Vec::new();
    if flags.irq {
        optional_files.push("crates/gbatopy-cli/assets/gba_runtime/interrupts.py");
    }
    if flags.timers {
        optional_files.push("crates/gbatopy-cli/assets/gba_runtime/timer.py");
    }
    if flags.dma {
        optional_files.push("crates/gbatopy-cli/assets/gba_runtime/dma.py");
    }
    if flags.audio {
        optional_files.push("crates/gbatopy-cli/assets/gba_runtime/apu.py");
    }

    // Combine core and optional files
    let runtime_files: Vec<&str> = core_files.iter().chain(optional_files.iter()).copied().collect();

    code.push_str("# === GBA Runtime (embedded) ===\n\n");
    for file_path in &runtime_files {
        if let Ok(content) = std::fs::read_to_string(file_path) {
            let filtered: String = content
                .lines()
                .filter(|line| {
                    let trimmed = line.trim();
                    !trimmed.starts_with("from .")
                        && !trimmed.starts_with("from gba_runtime")
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
        // Runtime loader: ensure runtime modules are importable from any directory
        code.push_str("# === Runtime Loader ===\n");
        code.push_str("# Ensure runtime path is accessible to runtime modules\n");
        code.push_str("import sys\nimport os\nfrom pathlib import Path\n");
        code.push_str("if __file__:\n");
        code.push_str("    # Try multiple strategies to find gba_runtime\n");
        code.push_str("    script_dir = Path(__file__).resolve().parent\n");
        code.push_str("    # Strategy 1: gba_runtime in same directory as script\n");
        code.push_str("    runtime_dir = script_dir / 'gba_runtime'\n");
        code.push_str("    if runtime_dir.exists():\n");
        code.push_str("        sys.path.insert(0, str(script_dir))\n");
        code.push_str("    else:\n");
        code.push_str("        # Strategy 2: check parent directories for gba_runtime\n");
        code.push_str("        for parent in [script_dir] + list(script_dir.parents):\n");
        code.push_str("            runtime_dir = parent / 'gba_runtime'\n");
        code.push_str("            if runtime_dir.exists():\n");
        code.push_str("                sys.path.insert(0, str(parent))\n");
        code.push_str("                break\n");
        code.push_str("    # Strategy 3: use environment variable if set\n");
        code.push_str("    gba_runtime_env = os.environ.get('GBA_RUNTIME_PATH')\n");
        code.push_str("    if gba_runtime_env and Path(gba_runtime_env).exists():\n");
        code.push_str("        sys.path.insert(0, gba_runtime_env)\n");
        code.push_str("\n");
        code.push_str("# Initialize runtime objects\n");
        code.push_str("memory = Memory()\n");
        code.push_str("ppu_instance = PPU(memory)\n");

    if flags.audio {
        code.push_str("apu_instance = APU()\n");
    }
    if flags.irq {
        code.push_str("# IRQ handler available via interrupts module\n");
    }
    if flags.timers {
        code.push_str("# Timer module available\n");
    }
    if flags.dma {
        code.push_str("# DMA module available\n");
    }
    if !flags.numba {
        code.push_str("set_numba_enabled(False)\n");
    } else {
        code.push_str("set_numba_enabled(True)\n");
    }
    code.push_str("\n");

    // PPU mode is read from DISPCNT register at runtime, not hardcoded
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

    // Collect all branch targets
    for inst in &instructions {
        let addr = inst.address as u64;
        let opcode = inst.opcode.as_str();

        // Check if this is a branch instruction - extract target address from operands
        if opcode == "B" || opcode == "BL" || opcode == "BX" || opcode == "BLX" {
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
        "  Found {} branch targets",
        branch_targets.len()
    );

    // PASS 2: Group instructions into basic blocks
    let mut func_groups: std::collections::HashMap<u64, Vec<&gbatopy_disasm::DecodedInstruction>> =
        std::collections::HashMap::new();

    let mut current_block_start: Option<u64> = None;
    let mut prev_addr: Option<u64> = None;
    let mut prev_was_branch = false;

    for inst in &instructions {
        let addr = inst.address as u64;
        let is_thumb = addr % 2 == 1;
        let instr_size = if is_thumb { 2 } else { 4 };
        let next_expected = prev_addr.map(|a| a + instr_size);
        let opcode = inst.opcode.as_str();
        let is_branch = opcode == "B" || opcode == "BL" || opcode == "BX" || opcode == "BLX";

        // Start new block if:
        // 1. This is a branch target, OR
        // 2. Previous instruction was a branch, OR
        // 3. Gap in addresses (not sequential)
        let should_start_new_block = branch_targets.contains(&addr)
            || prev_addr.map_or(true, |pa| {
                let is_sequential = next_expected == Some(addr);
                prev_was_branch || !is_sequential
            });

        prev_was_branch = is_branch;

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
    if rom.len() > 1_048_576 {
        // Use base64 for large ROMs (>1MB)
        code.push_str("import base64\n");
        let encoded = BASE64.encode(&rom);
        code.push_str(&format!("ROM_DATA = bytearray(base64.b64decode(\"{}\"))\n\n", encoded));
    } else {
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
    }

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

    // Embed tilemap data (16-bit values)
    code.push_str("# Tilemap data for backgrounds\n");
    code.push_str("bg0_tilemap = [\n");
    for chunk in assets.tilemap_data.chunks(2) {
        if chunk.len() == 2 {
            let value = u16::from_le_bytes([chunk[0], chunk[1]]);
            code.push_str(&format!("    0x{:04X},\n", value));
        }
    }
    code.push_str("]\n\n");

    // Embed tile data (raw bytes)
    code.push_str("# Tile data for backgrounds\n");
    code.push_str("tile_data = bytearray([\n");
    for (i, &byte) in assets.tile_data.iter().enumerate() {
        if i > 0 {
            code.push_str(", ");
        }
        if i % 16 == 0 {
            code.push_str("\n    ");
        }
        code.push_str(&format!("0x{:02X}", byte));
    }
    code.push_str("\n])\n\n");

    // Embed palette data (16-bit RGB555 values)
    code.push_str("# Palette data for backgrounds and sprites\n");
    code.push_str("palette_data = [\n");
    for chunk in assets.palette_data.chunks(2) {
        if chunk.len() == 2 {
            let value = u16::from_le_bytes([chunk[0], chunk[1]]);
            code.push_str(&format!("    0x{:04X},\n", value));
        }
    }
    code.push_str("]\n\n");

    // Embed sample metadata (start_addr, length, format)
    code.push_str("# Sample metadata: (start_addr, length, format)\n");
    code.push_str("SAMPLES = [\n");
    for (_i, &(addr, len, fmt)) in assets.samples.iter().enumerate() {
        code.push_str(&format!("    (0x{:08X}, {}, {}),\n", addr, len, fmt));
    }
    code.push_str("]\n\n");

    // Copy extracted tilemap to VRAM (BG0 tilemap at 0x06000000 and 0x06008000)
    code.push_str("if bg0_tilemap:\n");
    code.push_str("    for i, v in enumerate(bg0_tilemap[:1024]):\n");
    code.push_str("        if i * 2 < len(memory.vram):\n");
    code.push_str("            memory.vram[i * 2] = v & 0xFF\n");
    code.push_str("            memory.vram[i * 2 + 1] = (v >> 8) & 0xFF\n");
    code.push_str("        if 0x8000 + i * 2 < len(memory.vram):\n");
    code.push_str("            memory.vram[0x8000 + i * 2] = v & 0xFF\n");
    code.push_str("            memory.vram[0x8000 + i * 2 + 1] = (v >> 8) & 0xFF\n");
    code.push_str("    ppu_instance.bg0_tilemap = bg0_tilemap[:1024]\n");
    
    // Copy extracted tile data to VRAM (multiple possible offsets)
    code.push_str("if tile_data:\n");
    code.push_str("    for i, b in enumerate(tile_data):\n");
    code.push_str("        if 0x4000 + i < len(memory.vram):\n");
    code.push_str("            memory.vram[0x4000 + i] = b\n");
    code.push_str("        if 0x6000 + i < len(memory.vram):\n");
    code.push_str("            memory.vram[0x6000 + i] = b\n");
    code.push_str("        if 0x10000 + i < len(memory.vram):\n");
    code.push_str("            memory.vram[0x10000 + i] = b\n");
    code.push_str("    ppu_instance.tiles_4bpp = list(tile_data)\n");
    
    // Copy extracted palette to Palette RAM (0x05000000)
    code.push_str("if palette_data:\n");
    code.push_str("    for i, c in enumerate(palette_data[:256]):\n");
    code.push_str("        if i * 2 < len(memory.palette):\n");
    code.push_str("            memory.palette[i * 2] = c & 0xFF\n");
    code.push_str("            memory.palette[i * 2 + 1] = (c >> 8) & 0xFF\n");
    code.push_str("    ppu_instance.palette_bg = [((c & 0x1F) * 8, ((c >> 5) & 0x1F) * 8, ((c >> 10) & 0x1F) * 8) for c in palette_data]\n");
    code.push_str("\n");

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

    // Memory is already initialized in runtime section (line ~6022)
    // Don't create duplicate - the runtime memory is shared with PPU
    // Just reference the existing memory object
    code.push_str("vram = memory.vram\n");
    code.push_str("palette_ram = memory.palette\n");
    code.push_str("oam = memory.oam\n");
    code.push_str("ewram = memory.ewram\n\n");

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
            // Indent ALL lines, not just the first one
            for line in py_stmt.lines() {
                body.push_str(&format!("    {}\n", line));
            }
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
            block_function_code.push_str("    global vram, palette_ram, oam, ewram, ROM_DATA\n");
            block_function_code.push_str(&body);
            non_nop_addrs.push(func_start);
        }
    }

    // Write all block functions
    code.push_str(&block_function_code);

    // Generate jump table dispatch (dict-based for memory efficiency)
    let base_addr = 0x08000000;
    code.push_str("func_table = {}\n");
    
    // Populate jump table entries (NOP blocks redirect to next non-NOP function)
    for &addr in &address_list {
        if non_nop_addrs.contains(&addr) {
            code.push_str(&format!("func_table[0x{:08X}] = func_{:08X}\n", addr, addr));
        } else {
            let target = non_nop_addrs.iter().find(|&&a| a > addr).copied();
            if let Some(target_addr) = target {
                code.push_str(&format!("func_table[0x{:08X}] = func_{:08X}\n", addr, target_addr));
            }
        }
    }
    code.push_str("\n");

    // Add game loop (from generate_game_loop in pipeline.rs)
    code.push_str(&generate_game_loop());

    // Apply minification if requested
    if minify {
        eprintln!("Step 3: Minifying output...");
        // Safe minification: remove blank lines and comment-only lines.
        // Preserves all code lines exactly - no whitespace compression that
        // would break Python syntax (e.g. array.array('B', ...), slices, etc.)
        let mut minified = String::new();
        for line in code.lines() {
            let trimmed = line.trim();
            // Skip empty lines and comment-only lines
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }
            // Keep the line as-is (preserves indentation, colons, parentheses, etc.)
            minified.push_str(line);
            minified.push('\n');
        }
        code = minified;
        eprintln!("  Minification complete");
    }

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
        func = func_table.get(pc)
        if func is None: print(f"Unknown PC: 0x{pc:08X}"); break
        func(); ic += 1
        if r[15] == pc: print(f"Loop at 0x{pc:08X}"); break
        if ic % 10000 == 0: print(f"{ic} instrs")
        if frame_limit and fc >= frame_limit: break
        if ic % 1000 == 0: fc += 1
    print(f"Done: {ic} instrs")
    return fc

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1, dump_memory=None, dump_region=None):
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
        # Execute instructions for this frame (max 200000 instrs per frame)
        for _ in range(200000):
            pc = r[15]
            func = func_table.get(pc)
            if func is None: break
            func(); ic += 1
            if r[15] == pc: break
        # Render frame and update APU
        ppu_instance.render_frame()
        # VBlank IRQ dispatch
        dispstat = memory.read_u16(0x04000004)
        vblank_flag = (dispstat & 0x01) != 0
        if vblank_flag:
            ie = memory.read_u16(0x04000200)
            ime = memory.read_u16(0x04000208)
            if ie & 0x01 and ime & 0x01:
                memory.write_u16(0x04000202, memory.read_u16(0x04000202) | 0x01)
                r[15] = memory.read_u32(0x03007FFC)
        apu_instance.update()
        surf = ppu_instance.get_surface()
        screen.blit(pygame.transform.scale(surf, (240 * scale, 160 * scale)), (0, 0))
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
