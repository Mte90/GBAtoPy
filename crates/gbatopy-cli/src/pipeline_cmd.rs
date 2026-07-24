#![allow(dead_code, unused_variables)]
use crate::asset_extractor::extract_assets;
use crate::codegen::generate_instruction_python;
#[allow(unused_imports)]
use crate::ppu::generate_ppu_code;
use gbatopy_disasm::{
    operand::AddressingMode, operand::Operand, operand::ShiftAmount, ArmMode, CfgBuilder,
    Disassembler,
};
use std::fs;
use std::path::Path;

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
        let mut flags = Self {
            audio: false,
            irq: false,
            timers: false,
            dma: false,
            numba: true,  // numba enabled by default even in detection
        };

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

// Helper function to strip inline comments from Python code
// Strips # comments but tries to avoid stripping # inside strings
fn strip_inline_comment(line: &str) -> String {
    let mut in_string = false;
    let mut string_char = '\0';
    let mut prev_char = '\0';
    
    for (i, ch) in line.chars().enumerate() {
        // Handle string delimiters (simple approach - doesn't handle all edge cases)
        if (ch == '"' || ch == '\'') && prev_char != '\\' {
            if !in_string {
                in_string = true;
                string_char = ch;
            } else if ch == string_char {
                in_string = false;
                string_char = '\0';
            }
        }
        
        // Found comment start outside of string
        if ch == '#' && !in_string {
            return line[..i].to_string();
        }
        
        prev_char = ch;
    }
    
    line.to_string()
}

pub fn run_pipeline(
    rom_path: &str,
    output_path: &str,
    _assets_dir: &Path,
    _use_ir: bool,
    feature_flags: Option<FeatureFlags>,
    minify: bool,
    minify_aggressive: bool,
) -> Result<(), String> {
    let rom = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    let reachable: Vec<u32>;
    
    let instructions: Vec<gbatopy_disasm::DecodedInstruction>;

    // Always use CFG-based disassembly to avoid decoding data sections as code
    eprintln!("Step 1: CFG-based Disassembly");
    let mut cfg = CfgBuilder::new();
    cfg.build_from_entry(&rom, 0x08000000);
    reachable = cfg.get_reachable_addresses().to_vec();
    eprintln!("  CFG found {} reachable addresses", reachable.len());

    let mut disasm = Disassembler::new();
    instructions = disasm.selective_disassemble(&rom, &reachable, &cfg.mode_map);
    
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
        "crates/gbatopy-cli/assets/gba_runtime/save_state.py",
        "crates/gbatopy-cli/assets/gba_runtime/hooks.py",
    ];

    // Optional modules - included based on feature flags
    let mut optional_files = Vec::new();
    if flags.irq {
        optional_files.push("crates/gbatopy-cli/assets/gba_runtime/interrupts.py");
    }
    if flags.timers {
        optional_files.push("crates/gbatopy-cli/assets/gba_runtime/timers.py");
    }
    if flags.dma {
        optional_files.push("crates/gbatopy-cli/assets/gba_runtime/dma.py");
    }
    if flags.audio {
        optional_files.push("crates/gbatopy-cli/assets/gba_runtime/apu.py");
    }

    // Combine core and optional files
    let runtime_files: Vec<&str> = core_files.iter().chain(optional_files.iter()).copied().collect();

    // Add shebang and make executable
    code.push_str("#!/usr/bin/env python3\n");
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
                        && !trimmed.starts_with("from bios")
                })
                .collect::<Vec<_>>()
                .join("\n");
            // Minify: remove only blank lines (preserve docstrings for syntax correctness)
            let minified: String = filtered
                .lines()
                .filter(|line| !line.trim().is_empty())
                .collect::<Vec<_>>()
                .join("\n");
            code.push_str(&minified);
            code.push_str("\n\n");
            eprintln!(
                "    Included: {} (minified)",
                file_path.split('/').last().unwrap_or("")
            );
        } else {
            eprintln!("    WARNING: Could not read {}", file_path);
        }
    }
        code.push_str("# === End of Runtime ===\n\n");
        
        // Initialize runtime objects (ROM_DATA loaded later, after definition)
        code.push_str("memory = Memory()\n");
        code.push_str("ppu_instance = PPU(memory)\n");
        code.push_str("memory.attach_ppu(ppu_instance)\n");

    if flags.audio {
        code.push_str("apu_instance = APU()\n");
        code.push_str("memory.attach_apu(apu_instance)\n");
    } else {
        code.push_str("apu_instance = None\n");
    }
    
    // Create CPU instance (arm7tdmi)
    code.push_str("arm7tdmi_instance = CPU(memory)\n");
    
    // Create interrupt controller if enabled
    if flags.irq {
        code.push_str("interrupts_instance = InterruptController()\n");
        // Attach interrupts to memory for MMIO-based IRQ handling
        code.push_str("memory.attach_interrupts(interrupts_instance)\n");
    } else {
        code.push_str("interrupts_instance = None\n");
    }
    
    // Create timer instance if enabled
    if flags.timers {
        code.push_str("timers_instance = Timers()\n");
        code.push_str("memory.attach_timers(timers_instance)\n");
        if flags.irq {
            code.push_str("timers_instance.attach_interrupts(interrupts_instance)\n");
        }
    } else {
        code.push_str("timers_instance = None\n");
    }
    
    // Create DMA instance if enabled
    if flags.dma {
        code.push_str("dma_instance = DMA()\n");
        code.push_str("dma_instance.attach_memory(memory)\n");
        code.push_str("memory.attach_dma(dma_instance)\n");
        if flags.irq {
            code.push_str("dma_instance.attach_interrupts(interrupts_instance)\n");
        }
    } else {
        code.push_str("dma_instance = None\n");
    }
    
    // Create input instance
    code.push_str("input_instance = Input()\n");
    code.push_str("memory.attach_input(input_instance)\n");
    if !flags.numba {
        code.push_str("set_numba_enabled(False)\n");
    } else {
        code.push_str("set_numba_enabled(True)\n");
    }
    
    // Initialize save state manager
    code.push_str("# Initialize save state manager\n");
    code.push_str("save_state_mgr = create_save_state(\n");
    code.push_str("    cpu=arm7tdmi_instance, memory=memory, ppu=ppu_instance,\n");
    if flags.audio {
        code.push_str("    apu=apu_instance,\n");
    } else {
        code.push_str("    apu=None,\n");
    }
    if flags.dma {
        code.push_str("    dma=dma_instance,\n");
    } else {
        code.push_str("    dma=None,\n");
    }
    if flags.timers {
        code.push_str("    timers=timers_instance,\n");
    } else {
        code.push_str("    timers=None,\n");
    }
    if flags.irq {
        code.push_str("    interrupts=interrupts_instance,\n");
    } else {
        code.push_str("    interrupts=None,\n");
    }
    code.push_str("    input_state=input_instance\n");
    code.push_str(")\n");
    code.push_str("\n");

    // PPU mode is read from DISPCNT register at runtime, not hardcoded
    code.push_str("\n");

    // Required imports
    code.push_str("import pygame\n");
    code.push_str("\n");

    code.push_str("registers[15] = 0x08000000\n");
    code.push_str("cpsr = {'n': 0, 'z': 0, 'c': 0, 'v': 0}\n");
    code.push_str("\ndef cpsr_check(cond):\n");
    code.push_str("    n = cpsr['n']\n");
    code.push_str("    z = cpsr['z']\n");
    code.push_str("    c = cpsr['c']\n");
    code.push_str("    v = cpsr['v']\n");
    code.push_str("    if cond == 'EQ': return z == 1\n");
    code.push_str("    if cond == 'NE': return z == 0\n");
    code.push_str("    if cond == 'CS' or cond == 'HS': return c == 1\n");
    code.push_str("    if cond == 'CC' or cond == 'LO': return c == 0\n");
    code.push_str("    if cond == 'MI': return n == 1\n");
    code.push_str("    if cond == 'PL': return n == 0\n");
    code.push_str("    if cond == 'VS': return v == 1\n");
    code.push_str("    if cond == 'VC': return v == 0\n");
    code.push_str("    if cond == 'HI': return c == 1 and z == 0\n");
    code.push_str("    if cond == 'LS': return c == 0 or z == 1\n");
    code.push_str("    if cond == 'GE': return n == v\n");
    code.push_str("    if cond == 'LT': return n != v\n");
    code.push_str("    if cond == 'GT': return z == 0 and n == v\n");
    code.push_str("    if cond == 'LE': return z == 1 or n != v\n");
    code.push_str("    return True\n\n");

    // PASS 1: Identify branch target addresses (basic block boundaries)
    let mut branch_targets: std::collections::HashSet<u64> = std::collections::HashSet::new();

    // Collect all branch targets
    for inst in &instructions {
        let addr = inst.address as u64;

        if writes_r15(inst) {
            for op in &inst.operands {
                if let Operand::Immediate(target) = op {
                    branch_targets.insert(*target as u64);
                }
            }
        }
    }
    // Merge CFG-computed branch targets. The CFG correctly handles Thumb BL
    // (BL_PREFIX/BL_SUFFIX) targets, which the operand-based extraction above
    // misses because the BL target is computed from LR + offset, not a single
    // immediate operand. Without this, BL return addresses don't start new
    // blocks and instructions after BL merge into the caller's block.
    for &t in &cfg.branch_targets {
        branch_targets.insert(t as u64);
    }
    // First instruction is always a block start
    branch_targets.insert(0x08000000);

    eprintln!(
        "  Found {} branch targets",
        branch_targets.len()
    );

    // PASS 2: Group instructions into basic blocks
    let mut func_groups: std::collections::HashMap<(u64, ArmMode), Vec<&gbatopy_disasm::DecodedInstruction>> =
        std::collections::HashMap::new();

    let mut current_block_start: Option<(u64, ArmMode)> = None;
    let mut prev_addr: Option<u64> = None;
    let mut prev_was_branch = false;

    for inst in &instructions {
        let addr = inst.address as u64;
        let mode = inst.mode;
        let instr_size = inst.width as u64;
        let next_expected = prev_addr.map(|a| a + instr_size);
        let is_branch = writes_r15(inst);

        // CRITICAL: Branch instructions ALWAYS start their own block and terminate it
        if is_branch {
            // Start a new block for this branch instruction
            current_block_start = Some((addr, mode));
            // Add this instruction to its own block
            func_groups
                .entry((addr, mode))
                .or_insert_with(Vec::new)
                .push(inst);
            // Terminate the block (don't add more instructions to it)
            // BUT keep current_block_start = Some((addr, mode)) so next instruction knows prev_was_branch
            prev_was_branch = true;
            prev_addr = Some(addr);
            continue;  // Skip the rest of the loop
        }
        
        // Start new block if:
        // 1. This is a branch target, OR
        // 2. Previous instruction was a branch, OR
        // 3. Gap in addresses (not sequential) OR mode change
        let should_start_new_block = branch_targets.contains(&addr)
            || prev_addr.map_or(true, |pa| {
                let is_sequential = next_expected == Some(addr);
                prev_was_branch || !is_sequential
            });

        if should_start_new_block {
            current_block_start = Some((addr, mode));
            prev_was_branch = false;  // Reset after starting new block
        }

        if let Some(block_start) = current_block_start {
            func_groups
                .entry(block_start)
                .or_insert_with(Vec::new)
                .push(inst);
        }
        
        // Update prev_was_branch: true only for the instruction immediately after a branch
        if is_branch {
            prev_was_branch = true;
        } else if prev_was_branch {
            // Reset after using it for the next instruction
            prev_was_branch = false;
        }
        
        prev_addr = Some(addr);
    }

    eprintln!(
        "  Generated {} basic blocks (merged from {} instructions)",
        func_groups.len(),
        instructions.len()
    );

    // Helper function to generate Python from ARM instruction

    // Embed ROM data inline as base64 so the generated .py is fully standalone
    // (per AGENTS.md: "Standalone — zero external imports except pygame").
    // base64 keeps the source ~1.33x the ROM size, vs ~5x for a bytearray literal.
    use base64::Engine;
    let rom_b64 = base64::engine::general_purpose::STANDARD.encode(&rom);
    code.push_str("# ROM data (base64-encoded; decoded at runtime via stdlib base64)\n");
    code.push_str("import base64 as _b64\n");
    code.push_str(&format!(
        "ROM_DATA = bytearray(_b64.b64decode({:?}))\n",
        rom_b64
    ));
    code.push_str("memory.load_rom_data(ROM_DATA)\n\n");

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

    // ROM manages its own VRAM/palette writes at runtime; do not pre-load extracted assets

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

    // GBA class removed - duplicates Memory from memory.py which is already embedded

    // Memory is already initialized in runtime section (line ~6022)
    // Don't create duplicate - the runtime memory is shared with PPU
    // Just reference the existing memory object
    code.push_str("vram = memory.vram\n");
    code.push_str("palette_ram = memory.palette\n");
    code.push_str("oam = memory.oam\n");
    code.push_str("ewram = memory.ewram\n\n");

    // Helper: check if instruction writes to r[15]
    // Any instruction that modifies PC changes control flow and must suppress the
    // automatic fall-through PC advance that the codegen emits between blocks.
    // This includes:
    //   - Branch instructions (B, BL, BX, BLX, CBZ, CBNZ and conditional variants)
    //   - LDM/STM with PC (R15) in the register list (function return / long jump)
    //   - LDR with Rd = PC (PC-relative load into the program counter)
    //   - Data-processing instructions with Rd = PC (e.g. MOV PC, R14)

    /// Returns true for ARM conditional branch mnemonics (BEQ, BNE, BCS, etc.).
    /// Uses an explicit set instead of a prefix+length heuristic to avoid
    /// false positives like BIC (bit-clear) which also starts with 'B' and
    /// has length 3.
    fn is_conditional_branch(op: &str) -> bool {
        matches!(
            op,
            "BEQ" | "BNE" | "BCS" | "BCC" | "BMI" | "BPL" | "BVS" | "BVC"
                | "BHI" | "BLS" | "BGE" | "BLT" | "BGT" | "BLE" | "BAL" | "BNV"
        )
    }

    fn writes_r15(inst: &gbatopy_disasm::DecodedInstruction) -> bool {
        let op = inst.opcode.as_str();

        // Branch family: unconditional (B/BL/BX/BLX/CBZ/CBNZ) and conditional (BEQ, BNE, ...).
        // BL_SUFFIX is the Thumb BL branch half that writes PC.
        if matches!(op, "B" | "BL" | "BX" | "BLX" | "CBZ" | "CBNZ" | "BL_SUFFIX")
            || is_conditional_branch(op)
        {
            return true;
        }

        // Store instructions: first operand is a source, not a destination.
        // STM* covers STMFD, STMIA, STMDB, STMDA, STMEA, STMED, STMFA, STMIB,
        // and their '!' (writeback) variants. PUSH is the Thumb alias.
        let is_store = matches!(
            op,
            "STR" | "STRH" | "STRB" | "STRD" | "PUSH"
        ) || op.starts_with("STM");
        // Comparison instructions: only set flags, no Rd write.
        let is_comparison = matches!(op, "CMP" | "CMN" | "TST" | "TEQ");

        // Only the FIRST operand is the destination for data-processing and loads.
        if !is_store && !is_comparison {
            if let Some(Operand::Register(r)) = inst.operands.first() {
                if *r == 15 {
                    return true;
                }
            }
        }

        // LDM: the register list (MemoryAddress.offset = Multi) holds destinations.
        if !is_store {
            for operand in &inst.operands {
                if let Operand::MemoryAddress { offset, .. } = operand {
                    if let AddressingMode::Multi { registers, .. } = offset {
                        if registers.contains(&15) {
                            return true;
                        }
                    }
                }
            }
        }

        false
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
    let mut non_nop_addrs: Vec<(u64, ArmMode)> = Vec::new();
    let mut block_function_code = String::new();
    let address_list: Vec<(u64, ArmMode)> = func_groups.keys().copied().collect();

    for (&(func_start, func_mode_key), func_instructions) in &func_groups {
        let mode_suffix = if func_mode_key == ArmMode::Arm { "a" } else { "t" };
        let func_name = format!("func_{:08X}_{}", func_start, mode_suffix);
        let block_len = func_instructions.len();
        let instr_size: u64 = func_instructions[0].width as u64;
        let func_mode = func_instructions[0].mode;

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
                        body.push_str(&format!("    registers[15] = 0x{:08X}\n", next_addr));
                    }
                }
            }
        }
        // End of block: always advance PC for dispatch loop
        let last_addr = func_instructions.last().unwrap().address as u64;
        if !writes_r15(func_instructions.last().unwrap()) {
            let end_addr = last_addr + instr_size;
            body.push_str(&format!("    registers[15] = 0x{:08X}\n", end_addr));
        }

        // Check if block is pure NOP (only comments and sequential PC advances)
        // A NOP block has no real register/memory operations AND only advances PC sequentially
        let is_nop = body.lines().all(|l| {
            let t = l.trim();
            if t.is_empty() || t.starts_with('#') {
                return true;
            }
            // Check if this is a PC advance that matches the next sequential address
            if t.starts_with("registers[15] = 0x") {
                // Extract the target address
                if let Some(hex_str) = t.split("0x").nth(1).and_then(|s| s.split('\n').next()) {
                    // If it's just advancing to the next instruction, it's a NOP
                    // We need to check if this is a branch (non-sequential jump)
                    // For now, treat ANY registers[15] assignment as non-NOP to be safe
                    return false;
                }
            }
            false
        });

        if is_nop {
            // NOP block: skip generating function, will redirect func_map
            // NOP blocks are implicitly handled by chaining
        } else {
            block_function_code.push_str(&format!("\ndef {}(registers, cpsr):\n", func_name));
            block_function_code.push_str(&body);
            non_nop_addrs.push((func_start, func_mode_key));
        }
    }

    // Write all block functions
    code.push_str(&block_function_code);

    // Generate mode-aware jump table dispatch (dict-based for sparse ROMs - reduces memory overhead)
    // Two separate tables so ARM and Thumb functions at the same address don't collide.
    // The disassembler uses linear sweep and may decode the same address as ARM when the
    // CPU is actually in Thumb mode at runtime; separate tables prevent calling the wrong function.
    let base_addr: u64 = 0x08000000;
    
    code.push_str("dispatch_table_arm = {\n");
    for &(addr, mode) in &non_nop_addrs {
        if mode != ArmMode::Arm { continue; }
        let idx = (addr - base_addr) >> 1;
        if idx >= 0x100000 { continue; }
        code.push_str(&format!("    0x{:07X}: func_{:08X}_a,\n", idx, addr));
    }
    code.push_str("}\n\n");
    
    code.push_str("dispatch_table_thumb = {\n");
    for &(addr, mode) in &non_nop_addrs {
        if mode != ArmMode::Thumb { continue; }
        let idx = (addr - base_addr) >> 1;
        if idx >= 0x100000 { continue; }
        code.push_str(&format!("    0x{:07X}: func_{:08X}_t,\n", idx, addr));
    }
    code.push_str("}\n\n");

    // Merged table for _interp_fallback boundary checks (mode-agnostic membership test)
    code.push_str("dispatch_table = {**dispatch_table_arm, **dispatch_table_thumb}\n\n");

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

    // Apply aggressive minification if requested
    if minify_aggressive {
        eprintln!("Step 3b: Aggressive minification...");
        // Aggressive minification: strip docstrings, inline comments, and collapse blanks
        let mut aggressive = String::new();
        let mut in_docstring = false;
        let mut docstring_delimiter = "";
        
        for line in code.lines() {
            let trimmed = line.trim();
            
            // Skip empty lines
            if trimmed.is_empty() {
                continue;
            }
            
            // Handle docstrings
            if in_docstring {
                // Check if docstring ends on this line
                if line.contains(docstring_delimiter) {
                    in_docstring = false;
                }
                continue;
            }
            
            // Check for docstring start
            if trimmed.starts_with("\"\"\"") || trimmed.starts_with("'''") {
                let delimiter = if trimmed.starts_with("\"\"\"") { "\"\"\"" } else { "'''" };
                // Check if docstring ends on same line
                let after_start = &trimmed[3..];
                if after_start.contains(delimiter) {
                    // Single-line docstring - skip entirely
                    continue;
                }
                in_docstring = true;
                docstring_delimiter = delimiter;
                continue;
            }
            
            // Strip inline comments (but not in strings)
            let stripped_line = strip_inline_comment(line);
            
            aggressive.push_str(&stripped_line);
            aggressive.push('\n');
        }
        code = aggressive;
        eprintln!("  Aggressive minification complete");
    }

    let cpu_class_count = code.matches("class CPU").count();
    if cpu_class_count > 1 {
        return Err(format!(
            "Assertion failed: 'class CPU' defined {} times in generated output — duplicate runtime module detected. \
             Check runtime_files list in pipeline_cmd.rs for duplicates (e.g., arm7tdmi.py vs cpu.py both defining CPU).",
            cpu_class_count
        ));
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
import time

def calibrate_gba_timing(measure_cycles=100000):
    """Calibrate Python execution speed to match GBA 16.79 MHz."""
    loop_start = time.perf_counter()
    cal_cycles = 0
    cal_x = 0
    while cal_cycles < measure_cycles:
        cal_x = cal_x + 1
        cal_cycles += 1
    loop_end = time.perf_counter()
    elapsed = loop_end - loop_start
    cycles_per_second = cal_cycles / elapsed if elapsed > 0 else measure_cycles
    gba_hz = 16789800  # GBA clock speed (16.79 MHz)
    speed_ratio = cycles_per_second / gba_hz
    target_cycles_per_frame = gba_hz / 60.0
    calibrated_delay = 1.0 / cycles_per_second * target_cycles_per_frame
    return speed_ratio, calibrated_delay, cycles_per_second, gba_hz

_interp_cpu = None

def swi_handler(swi_field):
    """Handle BIOS SWI calls using the global registers/memory.
    The GBA BIOS uses the low 8 bits of the 24-bit SWI comment field
    as the function number. Upper bits are ignored (comment/checksum)."""
    global _cpu_halted
    swi_num = swi_field & 0xFF
    if swi_num == 0x00:  # SoftReset
        registers[0] = 0
        registers[13] = 0x03007F00
        registers[14] = 0x00000000
        registers[15] = 0x08000000
    elif swi_num == 0x01:  # RegisterRamReset
        flags = registers[0] & 0xFF
        if flags & 0x01:
            for addr in range(0x02000000, 0x02040000, 4):
                memory.write_u32(addr, 0)
        if flags & 0x02:
            for addr in range(0x03000000, 0x03008000, 4):
                memory.write_u32(addr, 0)
        if flags & 0x04:
            for addr in range(0x05000000, 0x05000400, 2):
                memory.write_u16(addr, 0)
        if flags & 0x08:
            for addr in range(0x06000000, 0x06018000, 2):
                memory.write_u16(addr, 0)
        if flags & 0x10:
            for addr in range(0x07000000, 0x07000400, 2):
                memory.write_u16(addr, 0)
    elif swi_num == 0x02:  # Halt
        _cpu_halted = True
        return
    elif swi_num == 0x03 or swi_num == 0x04:  # IntrWait
        _cpu_halted = True
        return
    elif swi_num == 0x05:  # VBlankIntrWait
        _cpu_halted = True
        return
    elif swi_num == 0x06:  # Div (signed)
        dividend = registers[0]
        divisor = registers[1]
        if divisor != 0:
            # Interpret as signed 32-bit
            sd = dividend - 0x100000000 if dividend & 0x80000000 else dividend
            sv = divisor - 0x100000000 if divisor & 0x80000000 else divisor
            q = int(sd / sv) if sv != 0 else 0
            r = sd - q * sv
            registers[0] = q & 0xFFFFFFFF
            registers[1] = r & 0xFFFFFFFF
            registers[3] = abs(sd) & 0xFFFFFFFF
    elif swi_num == 0x07:  # DivArm (unsigned)
        dividend = registers[0] & 0xFFFFFFFF
        divisor = registers[1] & 0xFFFFFFFF
        if divisor != 0:
            registers[0] = (dividend // divisor) & 0xFFFFFFFF
            registers[1] = (dividend % divisor) & 0xFFFFFFFF
            registers[3] = dividend & 0xFFFFFFFF
    elif swi_num == 0x08:  # Sqrt
        val = registers[0] & 0xFFFFFFFF
        registers[0] = int(val ** 0.5) & 0xFFFFFFFF
    elif swi_num == 0x0B:  # CpuSet
        src = registers[0]
        dst = registers[1]
        n = registers[2] & 0x1FFFFF
        units = (registers[2] >> 26) & 1  # 0=16-bit, 1=32-bit
        if units:
            for i in range(n):
                memory.write_u32(dst + i*4, memory.read_u32(src + i*4))
        else:
            for i in range(n):
                memory.write_u16(dst + i*2, memory.read_u16(src + i*2))
    elif swi_num == 0x0C:  # CpuFastSet
        src = registers[0]
        dst = registers[1]
        n = registers[2] & 0x1FFFFF
        for i in range(n):
            memory.write_u32(dst + i*4, memory.read_u32(src + i*4))
    # Other SWIs (0x09 ArcTan, 0x0A ArcTan2, 0x0E BgAffineSet,
    # 0x0F ObjAffineSet, 0x11/0x12 LZ77) are not commonly needed for
    # ROM startup; left as no-ops.

def _interp_fallback(registers, cpsr):
    global _interp_cpu
    if _interp_cpu is None:
        _interp_cpu = ARM7TDMI(memory)
    for i in range(16):
        _interp_cpu.registers[i] = registers[i]
    _cpsr_val = 0
    if cpsr.get('n', 0): _cpsr_val |= 0x80000000
    if cpsr.get('z', 0): _cpsr_val |= 0x40000000
    if cpsr.get('c', 0): _cpsr_val |= 0x20000000
    if cpsr.get('v', 0): _cpsr_val |= 0x10000000
    _interp_cpu.cpsr = _cpsr_val
    _interp_cpu.thumb_mode = bool(cpsr.get('t', 0))
    _step_count = 0
    _trace = []
    while _step_count < 10000000:
        _pc = _interp_cpu.registers[15]
        if 0x08000000 <= _pc < 0x0A000000:
            _idx = (_pc - 0x08000000) >> 1
            if _idx in dispatch_table:
                # Correct mode: if PC is only in ARM table, switch to ARM;
                # if only in Thumb, switch to Thumb. If in both, keep current.
                if _idx in dispatch_table_arm and _idx not in dispatch_table_thumb:
                    _interp_cpu.thumb_mode = False
                elif _idx in dispatch_table_thumb and _idx not in dispatch_table_arm:
                    _interp_cpu.thumb_mode = True
                break
            # PC in ROM but not in dispatch table (e.g., return from IWRAM code).
            # Break only after stepping at least once to avoid tight loop.
            if _step_count > 0:
                break
        if _pc == 0x03000128:
            irq = memory._interrupts
            if irq is not None:
                ie = irq.ie_reg
                iff = irq.if_reg
                ime = irq.ime_reg
            else:
                ie = iff = ime = 0
            if not getattr(_interp_fallback, '_irq_dumped', False):
                _interp_fallback._irq_dumped = True
                iw = [memory.read_u32(0x03000128 + i*4) for i in range(8)]
                print(f"  [irq] IE=0x{ie:04X} IF=0x{iff:04X} IME=0x{ime:04X} R14=0x{_interp_cpu.registers[14]:08X}")
                print(f"  [irq] IWRAM@0x03000128: {' '.join(f'{w:08X}' for w in iw)}")
                vt = memory.read_u32(0x03007FFC)
                print(f"  [irq] vector@0x03007FFC=0x{vt:08X}")
            pending = ie & iff
            if pending and ime:
                handler_addr = memory.read_u32(0x03007FFC)
                if 0x08000000 <= handler_addr < 0x0A000000:
                    irq.if_reg &= ~pending
                    _interp_cpu.registers[15] = handler_addr & 0xFFFFFFFE
                    _interp_cpu.thumb_mode = bool(handler_addr & 1)
                    _step_count += 1
                    continue
            _ret = _interp_cpu.registers[14]
            if 0x08000000 <= _ret < 0x0A000000:
                _interp_cpu.registers[15] = _ret & 0xFFFFFFFE
                _interp_cpu.thumb_mode = bool(_ret & 1)
            else:
                _interp_cpu.registers[15] = 0x08000000
                _interp_cpu.thumb_mode = False
            _step_count += 1
            continue
        if _step_count < 100:
            _trace.append(f"  step {_step_count}: PC=0x{_pc:08X} R13=0x{_interp_cpu.registers[13]:08X} R14=0x{_interp_cpu.registers[14]:08X}")
        _interp_cpu.step()
        _step_count += 1
    if _step_count >= 10000000:
        print(f"  [interp] exhausted 10000000 steps, final PC=0x{_interp_cpu.registers[15]:08X}")
        for line in _trace:
            print(line)
    for i in range(16):
        registers[i] = _interp_cpu.registers[i]
    _cpsr_val = _interp_cpu.cpsr
    cpsr['n'] = (_cpsr_val >> 31) & 1
    cpsr['z'] = (_cpsr_val >> 30) & 1
    cpsr['c'] = (_cpsr_val >> 29) & 1
    cpsr['v'] = (_cpsr_val >> 28) & 1
    cpsr['t'] = 1 if _interp_cpu.thumb_mode else 0

def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    global _cpu_halted
    speed_ratio, calibrated_delay, cycles_per_second, gba_hz = calibrate_gba_timing()
    def ror(v, a):
        a = a & 31
        return ((v >> a) | (v << (32 - a))) & 0xFFFFFFFF
    fc = 0; mi = 1000000; ic = 0
    _vblank_irq_delivered = False
    instr_per_scanline = max(50, (int(gba_hz / 60.0) // 4) // 160)
    def _deliver_vblank_irq():
        nonlocal _vblank_irq_delivered
        global _cpu_halted
        _cpu_halted = False
        if not _vblank_irq_delivered:
            _irq = getattr(memory, '_interrupts', None)
            if _irq is not None and (_irq.ime_reg & 0x0001):
                _pending = _irq.if_reg & _irq.ie_reg
                if _pending:
                    _handler = memory.read_u32(0x03007FFC)
                    if 0x02000000 <= _handler < 0x0A000000:
                        registers[14] = registers[15]
                        registers[15] = _handler & 0xFFFFFFFE
                        cpsr['t'] = 1 if (_handler & 1) else 0
                        _vblank_irq_delivered = True
    while ic < mi:
        if _cpu_halted:
            for _ in range(228):
                ppu_instance.step_scanline()
                if ppu_instance.vblank:
                    _deliver_vblank_irq()
                    break
            continue
        pc = registers[15]
        idx = (pc - 0x08000000) >> 1
        _dt = dispatch_table_thumb if cpsr.get('t', 0) else dispatch_table_arm
        func = _dt.get(idx)
        if func is None:
            _interp_fallback(registers, cpsr); ic += 1
        else:
            func(registers, cpsr); ic += 1
            if registers[15] == pc:
                # B . idle loop — step PPU immediately for responsiveness
                ppu_instance.step_scanline()
                if ppu_instance.vblank:
                    _deliver_vblank_irq()
                else:
                    _vblank_irq_delivered = False
                continue
        # Step PPU periodically (covers fallback-only execution paths
        # where the dispatch table is never hit)
        if ic % instr_per_scanline == 0:
            ppu_instance.step_scanline()
            if ppu_instance.vblank:
                _deliver_vblank_irq()
            else:
                _vblank_irq_delivered = False
        if frame_limit and fc >= frame_limit: break
        if ic % 1000 == 0: fc += 1
    return fc

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1, dump_memory=None, dump_region=None, load_state=None, save_state=None, hook_file=None, pc_trace=None, trace_n=0, max_instrs=1000000):
    global _cpu_halted
    # Initialize HookManager if hook file provided
    hook_manager = HookManager() if hook_file else None
    trace_file = None
    if pc_trace:
        trace_file = open(pc_trace, "w")
    trace_count = 0
    if hook_file:
        # Load and execute hook script
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("hook_script", hook_file)
            hook_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(hook_module)
            # Call setup_hooks if it exists
            if hasattr(hook_module, 'setup_hooks'):
                hook_module.setup_hooks(hook_manager)
                print(f"Hooks loaded from: {hook_file}")
        except Exception as e:
            print(f"Warning: Failed to load hook file {hook_file}: {e}", file=sys.stderr)
    speed_ratio, calibrated_delay, cycles_per_second, gba_hz = calibrate_gba_timing()
    
    # Load state if requested
    if load_state and save_state_mgr:
        print(f"Loading state from: {load_state}")
        if not save_state_mgr.load(load_state):
            print(f"Warning: Failed to load state from {load_state}", file=sys.stderr)
    
    pygame.init()
    if not headless:
        screen = pygame.display.set_mode((240 * scale, 160 * scale))
        pygame.display.set_caption("GBAtoPy")
    else:
        screen = pygame.Surface((240 * scale, 160 * scale))
    clock = pygame.time.Clock()
    fc = 0; running = True; mi = max_instrs; ic = 0
    loop_stall_count = 0
    max_loop_stalls = 10000
    _vblank_irq_delivered = False
    # print(f"PC=0x{registers[15]:08X}")
    while running and ic < mi and fc < (frame_limit or 10000):
        for e in pygame.event.get():
            if e.type == pygame.QUIT: running = False
            # Handle save state hotkeys: F5=save, F8=load
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_F5 and save_state_mgr:
                    # Save state to default file or provided path
                    save_path = save_state if save_state else "save_state.json"
                    print(f"Saving state to: {save_path}")
                    if save_state_mgr.save(save_path):
                        print(f"State saved successfully")
                    else:
                        print(f"Warning: Failed to save state to {save_path}", file=sys.stderr)
                elif e.key == pygame.K_F8 and save_state_mgr:
                    # Load state from default file or provided path
                    load_path = load_state if load_state else "save_state.json"
                    print(f"Loading state from: {load_path}")
                    if save_state_mgr.load(load_path):
                        print(f"State loaded successfully")
                    else:
                        print(f"Warning: Failed to load state from {load_path}", file=sys.stderr)
        # Execute instructions for this frame, stepping PPU scanlines
        # Each scanline: run a batch of instructions, then advance VCount + fire HBlank DMA
        target_cycles_per_frame = int(gba_hz / 60.0)
        instr_per_scanline = max(50, (target_cycles_per_frame // 4) // 160)
        max_inner_stalls = 10
        for _scanline in range(160):
            inner_loop_stalls = 0
            for _ in range(instr_per_scanline):
                if _cpu_halted:
                    break
                pc = registers[15]
                idx = (pc - 0x08000000) >> 1
                _dt = dispatch_table_thumb if cpsr.get('t', 0) else dispatch_table_arm
                func = _dt.get(idx)
                if func is None:
                    _interp_fallback(registers, cpsr); ic += 1
                    continue
                func(registers, cpsr); ic += 1
                if pc_trace and trace_file:
                    trace_file.write(f"{ic:08d} PC=0x{registers[15]:08X} R0={registers[0]:08X} R1={registers[1]:08X} R2={registers[2]:08X} R3={registers[3]:08X} R14={registers[14]:08X}\n")
                if trace_n > 0 and trace_count < trace_n:
                    print(f"{ic:08d} PC=0x{registers[15]:08X} R0={registers[0]:08X} R1={registers[1]:08X} R2={registers[2]:08X} R3={registers[3]:08X}")
                    trace_count += 1
                if registers[15] == pc:
                    inner_loop_stalls += 1
                    if inner_loop_stalls > max_inner_stalls:
                        break
                else:
                    inner_loop_stalls = 0
                if hook_manager and hook_manager.has_hooks():
                    if hook_manager.check_hooks(registers[15], 'instruction'):
                        print("Execution paused at breakpoint")
                        break
            ppu_instance.step_scanline()
            if ppu_instance.vblank:
                _cpu_halted = False
                if not _vblank_irq_delivered:
                    _irq = getattr(memory, '_interrupts', None)
                    if _irq is not None and (_irq.ime_reg & 0x0001):
                        _pending = _irq.if_reg & _irq.ie_reg
                        if _pending:
                            _handler = memory.read_u32(0x03007FFC)
                            if 0x02000000 <= _handler < 0x0A000000:
                                registers[14] = registers[15]
                                registers[15] = _handler & 0xFFFFFFFE
                                cpsr['t'] = 1 if (_handler & 1) else 0
                                _vblank_irq_delivered = True
            else:
                _vblank_irq_delivered = False
        # Render the completed frame
        ppu_instance.render_frame()
        # Update APU audio
        if apu_instance: apu_instance.update()
        surf = ppu_instance.get_surface()
        screen.blit(pygame.transform.scale(surf, (240 * scale, 160 * scale)), (0, 0))
        if not headless: pygame.display.flip()
        clock.tick(60); fc += 1
        # Notify frame hooks
        if hook_manager and hook_manager.has_hooks():
            hook_manager.notify_frame(fc)
        if frame_limit and fc >= frame_limit: break
    if screenshot_path:
        pygame.image.save(screen, screenshot_path)
        print(f"Screenshot: {screenshot_path}")
    
    # Save state if requested
    if save_state and save_state_mgr:
        print(f"Saving state to: {save_state}")
        if save_state_mgr.save(save_state):
            print(f"State saved successfully")
        else:
            print(f"Warning: Failed to save state to {save_state}", file=sys.stderr)
    
    pygame.mixer.quit()
    pygame.quit()
    
    # Dump memory if requested
    if dump_memory:
        with open(dump_memory, 'wb') as f:
            if dump_region:
                # Map region name to memory array
                regions = {
                    'ewram': ewram,
                    'iwram': iwram,
                    'vram': vram,
                    'palette': palette,
                    'oam': oam
                }
                region_data = regions.get(dump_region, ewram)
                f.write(bytes(region_data))
            else:
                # Default: dump full EWRAM (256KB)
                f.write(bytes(ewram))
        print(f"Memory dump written to: {dump_memory}")
    
    if trace_file:
        trace_file.close()
        print(f"PC trace written to: {pc_trace} ({ic} instructions)")
    
    return fc

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--screenshot", type=str)
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--dump-memory", type=str, help="Dump memory to binary file")
    parser.add_argument("--dump-region", type=str, help="Specific region to dump (ewram/iwram/vram/palette/oam)")
    parser.add_argument("--save-state", type=str, help="Save state to JSON file after execution")
    parser.add_argument("--load-state", type=str, help="Load state from JSON file before execution")
    parser.add_argument("--hook-file", type=str, help="Python script with debugging hooks (breakpoints, tracing, etc.)")
    parser.add_argument("--pc-trace", type=str, help="Log PC + registers each step to a file")
    parser.add_argument("--trace-n", type=int, default=0, help="Print first N PCs to stdout then stop tracing")
    parser.add_argument("--max-instrs", type=int, default=1000000, help="Maximum instructions before aborting (default 1M)")
    args = parser.parse_args()
    frames = run_with_pygame(
        headless=args.headless, 
        frame_limit=args.frame, 
        screenshot_path=args.screenshot, 
        scale=args.scale,
        dump_memory=args.dump_memory,
        dump_region=args.dump_region,
        load_state=args.load_state,
        save_state=args.save_state,
        hook_file=args.hook_file,
        pc_trace=args.pc_trace,
        trace_n=args.trace_n,
        max_instrs=args.max_instrs
    )
    print(f"{frames} frames")
    import os; os._exit(0)
"#
    .to_string()
}
// Force rebuild ven 1 mag 2026, 13:30:36, CEST
