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
            if inst.address >= 0x080000D8 && inst.address <= 0x080000E0 {
                eprintln!("DEBUG: Instruction at 0x{:08X}: opcode={}, operands={:?}", inst.address, opcode, inst.operands);
            }
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
    let branch_targets: Vec<u32>;
    
    let instructions: Vec<gbatopy_disasm::DecodedInstruction>;
    let is_large_rom = rom.len() > 1024 * 1024;

    if is_large_rom {
        eprintln!("Step 1: CFG-based Disassembly (large ROM)");
        let mut cfg = CfgBuilder::new();
        cfg.build_from_entry(&rom, 0x08000000);
        reachable = cfg.get_reachable_addresses().to_vec();
        branch_targets = cfg.branch_targets.clone();
        eprintln!("  CFG found {} reachable addresses", reachable.len());

        // For large ROMs, use selective disassembly (only reachable addresses)
        let mut disasm = Disassembler::new();
        instructions = disasm.selective_disassemble(&rom, &reachable);
    } else {
        eprintln!("Step 1: Full Disassembly (small ROM)");
        let mut disasm = Disassembler::new();
        let all_instructions = disasm.disassemble(&rom, 0x08000000);
        
        // Follow branch targets to find actual entry point
        // Some ROMs (like stripes.gba) start with a branch to the real code
        let mut reachable_set: std::collections::HashSet<u32> = all_instructions.iter().map(|i| i.address).collect();
        let mut branch_targets_set: std::collections::HashSet<u32> = std::collections::HashSet::new();
        
        // Check first instruction - if it's a branch, follow it
        if let Some(first_inst) = all_instructions.first() {
            if first_inst.opcode.starts_with('B') && !first_inst.opcode.starts_with("BX") {
                // Extract branch target from the instruction
                if let Some(target) = extract_branch_target(first_inst) {
                    eprintln!("  First instruction is branch to 0x{:08X}, following...", target);
                    reachable_set.insert(target);
                    branch_targets_set.insert(target);
                }
            }
        }
        
        reachable = reachable_set.into_iter().collect();
        branch_targets = branch_targets_set.into_iter().collect();
        eprintln!("  Disassembled {} instructions", reachable.len());

        // For small ROMs, use instructions directly from disassemble()
        // (which has correct ModeTracker-based ARM/Thumb detection)
        instructions = all_instructions;
    }
    
    if reachable.len() < 10 {
        eprintln!("  DEBUG: reachable addresses:");
        for a in reachable.iter().take(20) {
            eprintln!("    0x{:08X}", a);
        }
        eprintln!("  DEBUG: branch targets:");
        for t in branch_targets.iter().take(20) {
            eprintln!("    0x{:08X}", t);
        }
    }
    
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
        
        // Initialize runtime objects
        code.push_str("memory = Memory()\n");
        code.push_str("memory.load_rom_data(ROM_DATA)\n");
        code.push_str("ppu_instance = PPU(memory)\n");
        code.push_str("memory.attach_ppu(ppu_instance)\n");

    if flags.audio {
        code.push_str("apu_instance = APU()\n");
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
        if flags.irq {
            code.push_str("dma_instance.attach_interrupts(interrupts_instance)\n");
        }
    } else {
        code.push_str("dma_instance = None\n");
    }
    
    // Create input instance
    code.push_str("input_instance = Input()\n");
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

use gbatopy_disasm::Operand;

// Helper function to extract branch target from a branch instruction
fn extract_branch_target(inst: &gbatopy_disasm::DecodedInstruction) -> Option<u32> {
    // Branch instructions: B, BEQ, BNE, etc. have immediate offset
    if inst.opcode.starts_with('B') && !inst.opcode.starts_with("BX") {
        // Look for immediate operand
        for op in &inst.operands {
            if let gbatopy_disasm::Operand::Immediate(val) = op {
                return Some(*val);
            }
        }
    }
    None
}

// Generate Python from disassembled instructions (runtime already embedded above)

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
        let opcode = inst.opcode.as_str();

        // Check if this is a branch instruction - extract target address from operands
        // Include conditional branches (BEQ, BNE, BGT, BLT, etc.)
        let is_branch = opcode == "B" 
            || opcode == "BL" 
            || opcode == "BX" 
            || opcode == "BLX"
            || opcode.starts_with('B') && opcode.len() == 3; // Conditional branches: BEQ, BNE, etc.
        
        // Also check for instructions that write to R15 (PC)
        let writes_to_pc = opcode == "MOV" && inst.operands.iter().any(|op| {
            if let Operand::Register(15) = op { true } else { false }
        }) || opcode == "ADD" && inst.operands.iter().any(|op| {
            if let Operand::Register(15) = op { true } else { false }
        });
        
        if is_branch {
            for op in &inst.operands {
                if let Operand::Immediate(target) = op {
                    branch_targets.insert(*target as u64);
                    eprintln!("  Branch from 0x{:08X} -> target 0x{:08X}", addr, *target);
                }
            }
        }
        
        // Also add target if this instruction writes to PC with an immediate value
        if writes_to_pc {
            for op in &inst.operands {
                if let Operand::Immediate(target) = op {
                    branch_targets.insert(*target as u64);
                    eprintln!("  PC write from 0x{:08X} -> target 0x{:08X}", addr, *target);
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
        let instr_size = inst.width as u64;
        let next_expected = prev_addr.map(|a| a + instr_size);
        let opcode = inst.opcode.as_str();
        let is_branch = opcode == "B" 
            || opcode == "BL" 
            || opcode == "BX" 
            || opcode == "BLX"
            || (opcode.starts_with('B') && opcode.len() == 3); // Conditional branches

        // CRITICAL: Branch instructions ALWAYS start their own block and terminate it
        if is_branch {
            eprintln!("DEBUG: Branch at 0x{:08X} ({}) - new block and terminates it", addr, opcode);
            // Start a new block for this branch instruction
            current_block_start = Some(addr);
            // Add this instruction to its own block
            func_groups
                .entry(addr)
                .or_insert_with(Vec::new)
                .push(inst);
            // Terminate the block (don't add more instructions to it)
            // BUT keep current_block_start = Some(addr) so next instruction knows prev_was_branch
            prev_was_branch = true;
            prev_addr = Some(addr);
            continue;  // Skip the rest of the loop
        }
        
        // Start new block if:
        // 1. This is a branch target, OR
        // 2. Previous instruction was a branch, OR
        // 3. Gap in addresses (not sequential)
        let should_start_new_block = branch_targets.contains(&addr)
            || prev_addr.map_or(true, |pa| {
                let is_sequential = next_expected == Some(addr);
                prev_was_branch || !is_sequential
            });

        if should_start_new_block {
            eprintln!("DEBUG: 0x{:08X} ({}) - starting new block (branch_target={}, prev_was_branch={}, sequential={})", 
                addr, opcode, 
                branch_targets.contains(&addr), 
                prev_was_branch,
                next_expected == Some(addr));
            current_block_start = Some(addr);
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

    // ROM data will be loaded from external .bin file instead of embedded
    // This keeps the Python script smaller and cleaner
    let rom_basename = Path::new(&rom_path)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("rom");
    let rom_bin_path = format!("{}.bin", rom_basename);
    code.push_str(&format!(
        "# ROM data loaded from external file: {}\n",
        rom_bin_path
    ));
    code.push_str("def load_rom_data():\n");
    code.push_str("    \"\"\"Load ROM data from external .bin file\"\"\"\n");
    code.push_str(&format!("    with open('{}', 'rb') as f:\n", rom_bin_path));
    code.push_str("        return bytearray(f.read())\n\n");
    code.push_str("ROM_DATA = load_rom_data()\n\n");

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

    // GBA class removed - duplicates Memory from memory.py which is already embedded

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
        // Include ALL branch instructions: unconditional, conditional (BNE, BEQ, etc.), and BX/BLX
        matches!(op, "B" | "BL" | "BX" | "BLX" | "CBZ" | "CBNZ") 
            || op.starts_with('B') && op.len() == 3  // Conditional branches: BNE, BEQ, BGT, BLT, BGE, BLE
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
        let block_len = func_instructions.len();
        let instr_size: u64 = func_instructions[0].width as u64;

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
            non_nop_addrs.push(func_start);
        }
    }

    // Write all block functions
    code.push_str(&block_function_code);

    // Generate jump table dispatch (dict-based for sparse ROMs - reduces memory overhead)
    code.push_str("dispatch_table = {\n");
    
    // Populate jump table entries using dict (more compact for sparse ROMs)
    let base_addr: u64 = 0x08000000;
    for &addr in &non_nop_addrs {
        let idx = (addr - base_addr) >> 2;
        if idx >= 0x080000 {
            continue;
        }
        code.push_str(&format!("    0x{:07X}: func_{:08X},\n", idx, addr));
    }
    code.push_str("}\n\n");

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

    fs::write(output_path, &code).map_err(|e| format!("Failed to write output: {}", e))?;

    // Write ROM data to external .bin file
    let rom_basename = Path::new(&rom_path)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("rom");
    let rom_bin_path = format!("{}.bin", rom_basename);
    let output_dir = Path::new(&output_path).parent().unwrap_or(Path::new("."));
    let bin_full_path = output_dir.join(&rom_bin_path);
    fs::write(&bin_full_path, &rom)
        .map_err(|e| format!("Failed to write ROM data to {}: {}", rom_bin_path, e))?;

    println!(
        "Generated {} lines of Python to {}",
        code.lines().count(),
        output_path
    );
    println!("Wrote ROM data to {}", bin_full_path.display());
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

def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    speed_ratio, calibrated_delay, cycles_per_second, gba_hz = calibrate_gba_timing()
    def ror(v, a):
        a = a & 31
        return ((v >> a) | (v << (32 - a))) & 0xFFFFFFFF
    fc = 0; mi = 1000000; ic = 0
    while ic < mi:
        pc = registers[15]
        idx = (pc - 0x08000000) >> 2
        func = dispatch_table.get(idx)
        if func is None: 
            print(f"Unknown PC: 0x{pc:08X}")
            break
        func(registers, cpsr); ic += 1
        if registers[15] == pc: 
            break
    # print(f"Done: {ic} instrs")
        # if ic % 10000 == 0: print(f"{ic} instrs")
        if frame_limit and fc >= frame_limit: break
        if ic % 1000 == 0: fc += 1
    # print(f"Done: {ic} instrs")
    return fc

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1, dump_memory=None, dump_region=None, load_state=None, save_state=None, hook_file=None):
    # Initialize HookManager if hook file provided
    hook_manager = HookManager() if hook_file else None
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
    fc = 0; running = True; mi = 1000000; ic = 0
    loop_stall_count = 0
    max_loop_stalls = 10000
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
        # Execute instructions for this frame
        target_cycles_per_frame = int(gba_hz / 60.0)
        inner_loop_stalls = 0
        max_inner_stalls = 10  # Break inner loop after just 10 stalls - ROM is likely in a wait loop
        for _ in range(target_cycles_per_frame // 4):
            pc = registers[15]
            idx = (pc - 0x08000000) >> 2
            func = dispatch_table.get(idx)
            if func is None: 
                print(f"Unknown PC: 0x{pc:08X}")
                break
            func(registers, cpsr); ic += 1
            # Track stalls within inner loop - break if PC doesn't change
            if registers[15] == pc:
                inner_loop_stalls += 1
                if inner_loop_stalls > max_inner_stalls:
                    # PC is stuck, break inner loop to allow frame rendering
                    break
            else:
                inner_loop_stalls = 0
            # Check hooks (zero-overhead when no hooks registered)
            if hook_manager and hook_manager.has_hooks():
                if hook_manager.check_hooks(registers[15], 'instruction'):
                    # Breakpoint hit - pause execution
                    print("Execution paused at breakpoint")
                    break
        # Render frame (this sets VBlank flag and dispatches VBlank IRQ internally)
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
        hook_file=args.hook_file
    )
    print(f"{frames} frames")
"#
    .to_string()
}
// Force rebuild ven 1 mag 2026, 13:30:36, CEST
