pub mod instruction_codegen;

#[allow(unused_imports)]
pub use instruction_codegen::generate_instruction_python;
use crate::analysis::{detect_memset_loop_pattern, detect_memset_loop_pattern_across_blocks, extract_bl_targets, is_conditional_non_branch, reads_r15, writes_r15};
use crate::asset_extractor::ExtractedAssets;
use gbatopy_disasm::{operand::Operand, ArmMode, CfgBuilder, DecodedInstruction};

use std::fs;

/// Helper function to strip inline comments from Python code
fn strip_inline_comment(line: &str) -> String {
    let mut in_string = false;
    let mut string_char = '\0';
    let mut prev_char = '\0';

    for (i, ch) in line.char_indices() {
        if (ch == '"' || ch == '\'') && prev_char != '\\' {
            if !in_string {
                in_string = true;
                string_char = ch;
            } else if ch == string_char {
                in_string = false;
                string_char = '\0';
            }
        }

        if ch == '#' && !in_string {
            return line[..i].to_string();
        }

        prev_char = ch;
    }

    line.to_string()
}

/// Phase 3: Python Code Generation
/// Extracts the Python code generation logic from the pipeline
#[allow(clippy::too_many_arguments)]
pub fn generate_python_code(
    instructions: Vec<DecodedInstruction>,
    cfg: &CfgBuilder,
    rom: &[u8],
    flags: &crate::pipeline_cmd::FeatureFlags,
    assets: &ExtractedAssets,
    output_path: &str,
    minify: bool,
    minify_aggressive: bool,
    max_output_lines: u64,
) -> Result<(), String> {
    eprintln!("Step 3: Python Code Generation (direct from disassembly)");

    // EMBED RUNTIME CODE first (conditionally based on feature flags)
    eprintln!("  Embedding GBA runtime...");
    let mut code = String::new();

    // Core modules - always included (CARGO_MANIFEST_DIR ensures binary works from any CWD)
    let manifest_dir = env!("CARGO_MANIFEST_DIR");
    let core_files = [
        &format!("{}/assets/templates/header.py", manifest_dir),
        &format!("{}/assets/gba_runtime/memory.py", manifest_dir),
        &format!("{}/assets/gba_runtime/ppu.py", manifest_dir),
        &format!("{}/assets/gba_runtime/cpu.py", manifest_dir),
        &format!("{}/assets/gba_runtime/arm7tdmi.py", manifest_dir),
        &format!("{}/assets/gba_runtime/input.py", manifest_dir),
        &format!("{}/assets/gba_runtime/bios.py", manifest_dir),
        &format!("{}/assets/gba_runtime/save_state.py", manifest_dir),
        &format!("{}/assets/gba_runtime/hooks.py", manifest_dir),
    ];

    // Optional modules - included based on feature flags (using manifest_dir from above)
    let mut optional_files = Vec::new();
    if flags.irq {
        optional_files.push(format!("{}/assets/gba_runtime/interrupts.py", manifest_dir));
    }
    if flags.timers {
        optional_files.push(format!("{}/assets/gba_runtime/timers.py", manifest_dir));
    }
    if flags.dma {
        optional_files.push(format!("{}/assets/gba_runtime/dma.py", manifest_dir));
    }
    if flags.audio {
        optional_files.push(format!("{}/assets/gba_runtime/apu.py", manifest_dir));
    }
    if flags.numba {
        optional_files.push(format!("{}/assets/gba_runtime/numba.py", manifest_dir));
    }

    // Combine core and optional files
    let runtime_files: Vec<String> = core_files
        .iter()
        .map(|s| s.to_string())
        .chain(optional_files)
        .collect();

    // Add shebang and make executable
    code.push_str("#!/usr/bin/env python3\n");
    code.push_str("# === GBA Runtime (embedded) ===\n\n");
    for file_path in &runtime_files {
        let content = std::fs::read_to_string(file_path)
            .map_err(|e| format!("Failed to read runtime asset {}: {}", file_path, e))?;
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
            file_path.split('/').next_back().unwrap_or("")
        );
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
        // Link irq._io to live MMIO for write-through
        code.push_str("interrupts_instance._io = memory.io\n");
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
    code.push('\n');

    // PPU mode is read from DISPCNT register at runtime, not hardcoded
    code.push('\n');

    // Required imports
    code.push_str("import pygame\n");
    code.push('\n');

    code.push_str("registers[15] = 0x08000000\n");
    code.push_str("cpsr = {'n': 0, 'z': 0, 'c': 0, 'v': 0, 't': 0, 'mode': 0x13, 'i': 1, 'f': 1, 'spsr_irq': 0, 'spsr_svc': 0, 'spsr_abt': 0, 'spsr_und': 0, 'spsr_sys': 0}\n");
    code.push_str("_user_sys_bank = {'sp': 0x03007F00, 'lr': 0}\n");
    code.push_str("banked_sp_lr = {0x10: {'sp': 0x03007FA0, 'lr': 0}, 0x1F: _user_sys_bank, 0x11: {'sp': 0x03007F00, 'lr': 0, 'r8': 0, 'r9': 0, 'r10': 0, 'r11': 0, 'r12': 0}, 0x12: {'sp': 0x03007FE0, 'lr': 0}, 0x13: {'sp': 0x03007FE0, 'lr': 0}, 0x17: {'sp': 0x03007FE0, 'lr': 0}, 0x1B: {'sp': 0x03007F00, 'lr': 0}}\n");
    code.push_str("\ndef _switch_mode(new_mode):\n");
    code.push_str("    old_mode = cpsr.get('mode', 0x1F)\n");
    code.push_str("    if new_mode == old_mode:\n");
    code.push_str("        return\n");
    code.push_str("    if old_mode in banked_sp_lr:\n");
    code.push_str("        _b = banked_sp_lr[old_mode]\n");
    code.push_str("        _b['sp'] = registers[13]; _b['lr'] = registers[14]\n");
    code.push_str("        if old_mode == 0x11:\n");
    code.push_str("            _b['r8'] = registers[8]; _b['r9'] = registers[9]; _b['r10'] = registers[10]; _b['r11'] = registers[11]; _b['r12'] = registers[12]\n");
    code.push_str("    if new_mode in banked_sp_lr:\n");
    code.push_str("        _b = banked_sp_lr[new_mode]\n");
    code.push_str("        registers[13] = _b['sp']; registers[14] = _b['lr']\n");
    code.push_str("        if new_mode == 0x11:\n");
    code.push_str("            registers[8] = _b['r8']; registers[9] = _b['r9']; registers[10] = _b['r10']; registers[11] = _b['r11']; registers[12] = _b['r12']\n");
    code.push_str("    cpsr['mode'] = new_mode\n");
    code.push_str("\ndef _spsr_for_mode(mode):\n");
    code.push_str("    _m = {0x11: 'spsr_fiq', 0x12: 'spsr_irq', 0x13: 'spsr_svc', 0x17: 'spsr_abt', 0x1B: 'spsr_und', 0x1F: 'spsr_sys'}\n");
    code.push_str("    return cpsr.get(_m.get(mode, 'spsr_irq'), 0) & 0xFFFFFFFF\n");
    code.push_str("\ndef _cpsr_to_int(c):\n");
    code.push_str("    return ((c['n'] & 1) << 31) | ((c['z'] & 1) << 30) | ((c['c'] & 1) << 29) | ((c['v'] & 1) << 28) | ((c['i'] & 1) << 7) | ((c['f'] & 1) << 6) | ((c['t'] & 1) << 5) | (c['mode'] & 0x1F)\n");
    code.push_str("\ndef _cpsr_from_int(c, val):\n");
    code.push_str("    c['n'] = (val >> 31) & 1; c['z'] = (val >> 30) & 1; c['c'] = (val >> 29) & 1; c['v'] = (val >> 28) & 1; c['i'] = (val >> 7) & 1; c['f'] = (val >> 6) & 1; c['t'] = (val >> 5) & 1; c['mode'] = val & 0x1F\n");
    code.push_str(
        "\n_MODE_TO_SPSR_IDX = {0x10: 0, 0x1F: 1, 0x13: 2, 0x17: 3, 0x1B: 4, 0x11: 5, 0x12: 6}\n",
    );
    code.push_str("_MODES_WITH_SPSR = frozenset({0x11, 0x12, 0x13, 0x17, 0x1B})\n");
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
        let _addr = inst.address as u64;

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

    eprintln!("  Found {} branch targets", branch_targets.len());

    // PASS 2: Group instructions into basic blocks
    let mut func_groups: std::collections::HashMap<
        (u64, ArmMode),
        Vec<&gbatopy_disasm::DecodedInstruction>,
    > = std::collections::HashMap::new();

    let mut current_block_start: Option<(u64, ArmMode)> = None;
    let mut prev_addr: Option<u64> = None;
    let mut prev_was_branch = false;

    for inst in &instructions {
        let addr = inst.address as u64;
        if (0x08000100..=0x08000120).contains(&addr) {
            eprintln!(
                "PASS2: instr at 0x{:08X}: {} mode={:?}",
                addr, inst.opcode, inst.mode
            );
        }
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
            func_groups.entry((addr, mode)).or_default().push(inst);
            // Terminate the block (don't add more instructions to it)
            // BUT keep current_block_start = Some((addr, mode)) so next instruction knows prev_was_branch
            prev_was_branch = true;
            prev_addr = Some(addr);
            continue; // Skip the rest of the loop
        }

        // Start new block if:
        // 1. This is a branch target, OR
        // 2. Previous instruction was a branch, OR
        // 3. Gap in addresses (not sequential) OR mode change
        let should_start_new_block = branch_targets.contains(&addr)
            || prev_addr.is_none_or(|_pa| {
                let is_sequential = next_expected == Some(addr);
                prev_was_branch || !is_sequential
            });

        if should_start_new_block {
            current_block_start = Some((addr, mode));
            prev_was_branch = false; // Reset after starting new block
        }

        if let Some(block_start) = current_block_start {
            func_groups.entry(block_start).or_default().push(inst);
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
    let rom_b64 = base64::engine::general_purpose::STANDARD.encode(rom);
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
    for &(addr, len, fmt) in assets.samples.iter() {
        code.push_str(&format!("    (0x{:08X}, {}, {}),\n", addr, len, fmt));
    }
    code.push_str("]\n\n");

    // Copy extracted tile/palette data to VRAM at initialization
    code.push_str("# Copy extracted assets to VRAM/palette at initialization\n");
    code.push_str("if tile_data:\n");
    code.push_str("    for i, b in enumerate(tile_data):\n");
    code.push_str("        memory.vram[i] = b\n");
    code.push_str("if palette_data:\n");
    code.push_str("    for i, val in enumerate(palette_data):\n");
    code.push_str("        memory.palette[i*2] = val & 0xFF\n");
    code.push_str("        memory.palette[i*2+1] = (val >> 8) & 0xFF\n");
    code.push('\n');

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
    code.push('\n');

    // GBA class removed - duplicates Memory from memory.py which is already embedded

    // Memory is already initialized in runtime section (line ~6022)
    // Don't create duplicate - the runtime memory is shared with PPU
    // Just reference the existing memory object
    code.push_str("vram = memory.vram\n");
    code.push_str("palette_ram = memory.palette\n");
    code.push_str("oam = memory.oam\n");
    code.push_str("ewram = memory.ewram\n\n");

    // Generate functions for each branch target, skip pure NOP blocks
    // Detect memset loop patterns across basic blocks
    let memset_loop_starts = detect_memset_loop_pattern_across_blocks(&func_groups);
    eprintln!(
        "  Peephole optimization: detected {} memset loop patterns",
        memset_loop_starts.len() / 3
    );

    let mut non_nop_addrs: Vec<(u64, ArmMode)> = Vec::new();
    let mut block_function_code = String::new();
    let mut address_list: Vec<(u64, ArmMode)> = func_groups.keys().copied().collect();
    address_list.sort();
    let mut current_line_count = code.lines().count() as u64;

    // Worklist algorithm: recursively follow BL targets to ensure all called functions
    // are included in the dispatch table. Without this, BL targets route to _interp_fallback
    // causing severe performance degradation (10-100x slower).
    let mut dispatch_worklist: Vec<(u64, ArmMode)> = address_list.clone();
    let mut dispatch_table_set: std::collections::HashSet<(u64, ArmMode)> =
        std::collections::HashSet::new();

    // Worklist algorithm: process functions and recursively follow BL targets
    let mut processed_funcs: std::collections::HashSet<(u64, ArmMode)> =
        std::collections::HashSet::new();



    while let Some(&(func_start, func_mode_key)) = dispatch_worklist.first() {
        // Remove from worklist
        dispatch_worklist.remove(0);

        // Skip if already processed or already in dispatch table
        if processed_funcs.contains(&(func_start, func_mode_key)) {
            continue;
        }
        if dispatch_table_set.contains(&(func_start, func_mode_key)) {
            continue;
        }

        // Get function instructions
        let func_key = (func_start, func_mode_key);
        let func_instructions = match func_groups.get(&func_key) {
            Some(instrs) => instrs,
            None => continue, // Not a valid function start
        };

        // Mark as being processed (to avoid infinite loops)
        processed_funcs.insert(func_key);

        // Extract BL targets BEFORE generating the function, so we can add them to worklist
        let bl_targets = extract_bl_targets(func_instructions);
        for target in bl_targets {
            if !dispatch_table_set.contains(&target) && !processed_funcs.contains(&target) {
                dispatch_worklist.push(target);
            }
        }

        // Check if this block is part of a memset loop pattern (and is the first block)
        let is_memset_loop_start = memset_loop_starts.contains(&func_start);

        // Skip generating functions for the 2nd and 3rd blocks of memset loops
        // They will be handled by the optimized first block
        if is_memset_loop_start && func_instructions.len() == 1 {
            let inst = func_instructions[0];
            if inst.opcode == "STMIA" {
                let stmia_uses = &inst.operands;
                if stmia_uses.len() == 2 {
                    if let (Operand::Register(rb), Operand::Register(rs)) =
                        (&stmia_uses[0], &stmia_uses[1])
                    {
                        // This is the start of a memset loop - generate optimized code
                        let mode_suffix = if func_mode_key == ArmMode::Arm {
                            "a"
                        } else {
                            "t"
                        };
                        let func_name = format!("func_{:08X}_{}", func_start, mode_suffix);

                        // Get the counter register from the next block
                        let next_addr = (inst.address + 2) as u64;
                        let next_key = (next_addr, func_mode_key);
                        if let Some(next_block) = func_groups.get(&next_key) {
                            if next_block.len() == 1 && next_block[0].opcode == "SUB" {
                                let sub_uses = &next_block[0].operands;
                                if sub_uses.len() >= 2 {
                                    if let Operand::Register(rc) = sub_uses[0] {
                                        // Get fallthrough address from the BNE block
                                        let next2_addr = (next_block[0].address + 2) as u64;
                                        let next2_key = (next2_addr, func_mode_key);
                                        let fallthrough_addr = if let Some(next2_block) =
                                            func_groups.get(&next2_key)
                                        {
                                            if next2_block.len() == 1
                                                && next2_block[0].opcode == "BNE"
                                            {
                                                next2_block[0].address as u64
                                                    + next2_block[0].width as u64
                                            } else {
                                                next2_addr
                                            }
                                        } else {
                                            next2_addr
                                        };

                                        // Generate optimized bulk loop
                                        let mut body = String::new();
                                        body.push_str(
                                            "    # Peephole optimization: memset loop detected\n",
                                        );
                                        body.push_str(&format!(
                                            "    _count = (registers[{}] // 4) & 0xFFFFFFFF\n",
                                            rc
                                        ));
                                        body.push_str(&format!("    _base = registers[{}]\n", rb));
                                        body.push_str(&format!(
                                            "    _val = registers[{}] & 0xFFFFFFFF\n",
                                            rs
                                        ));
                                        body.push_str("    for _i in range(_count):\n");
                                        body.push_str(
                                            "        memory.write_u32(_base + _i * 4, _val)\n",
                                        );
                                        body.push_str(&format!("    registers[{}] = (_base + _count * 4) & 0xFFFFFFFF\n", rb));
                                        body.push_str(&format!("    registers[{}] = 0\n", rc));
                                        body.push_str("    cpsr['z'] = 1\n");
                                        body.push_str("    cpsr['n'] = 0\n");
                                        body.push_str("    cpsr['c'] = 1\n");
                                        body.push_str("    cpsr['v'] = 0\n");
                                        body.push_str(&format!(
                                            "    registers[15] = 0x{:08X}\n",
                                            fallthrough_addr
                                        ));

                                        let func_code =
                                            format!("\ndef {}(registers, cpsr):\n", func_name)
                                                + &body;
                                        let lines_to_add = func_code.lines().count() as u64;

                                        if current_line_count + lines_to_add > max_output_lines {
                                            return Err(format!(
                                                "Output exceeded {} lines, aborting. ROM may be too large or data is being misclassified as code.",
                                                max_output_lines
                                            ));
                                        }

                                        block_function_code.push_str(&func_code);
                                        current_line_count += lines_to_add;
                                        non_nop_addrs.push((func_start, func_mode_key));

                                        // Skip to next block - the 2nd and 3rd blocks will be skipped
                                        continue;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Skip blocks that are part of memset loops but not the first block
        if memset_loop_starts.contains(&func_start) && !is_memset_loop_start {
            // This is the 2nd or 3rd block of a memset loop - skip it
            continue;
        }

        let mode_suffix = if func_mode_key == ArmMode::Arm {
            "a"
        } else {
            "t"
        };
        let func_name = format!("func_{:08X}_{}", func_start, mode_suffix);
        let block_len = func_instructions.len();
        let instr_size: u64 = func_instructions[0].width as u64;
        let _func_mode = func_instructions[0].mode;

        // Generate function body into a temp buffer
        let mut body = String::new();

        // Check for memset loop pattern within a single block (for completeness)
        let memset_optimized = detect_memset_loop_pattern(func_instructions);

        if let Some((rb, rs, rc, fallthrough_addr)) = memset_optimized {
            // Emit optimized bulk loop instead of 3 individual instructions
            body.push_str("    # PEephole optimization: memset loop detected\n");
            body.push_str(&format!(
                "    _count = (registers[{}] // 4) & 0xFFFFFFFF\n",
                rc
            ));
            body.push_str(&format!("    _base = registers[{}]\n", rb));
            body.push_str(&format!("    _val = registers[{}] & 0xFFFFFFFF\n", rs));
            body.push_str("    for _i in range(_count):\n");
            body.push_str("        memory.write_u32(_base + _i * 4, _val)\n");
            body.push_str(&format!(
                "    registers[{}] = (_base + _count * 4) & 0xFFFFFFFF\n",
                rb
            ));
            body.push_str(&format!("    registers[{}] = 0\n", rc));
            body.push_str("    cpsr['z'] = 1\n");
            body.push_str("    cpsr['n'] = 0\n");
            body.push_str("    cpsr['c'] = 1\n");
            body.push_str("    cpsr['v'] = 0\n");
            body.push_str(&format!("    registers[15] = 0x{:08X}\n", fallthrough_addr));
        } else {
            // Normal code generation for each instruction
            for (idx, inst) in func_instructions.iter().enumerate() {
                if inst.is_data {
                    continue;
                }
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
        }
        // End of block: always advance PC for dispatch loop (unless memset optimization was applied)
        if memset_optimized.is_none() {
            let last_inst = func_instructions.last().unwrap();
            let last_addr = last_inst.address as u64;
            if !writes_r15(last_inst) {
                let end_addr = last_addr + instr_size;
                body.push_str(&format!("    registers[15] = 0x{:08X}\n", end_addr));
            } else if is_conditional_non_branch(last_inst) {
                // Conditional non-branch that writes R15 (e.g. LDRLS PC, [PC, Rn, LSL #2])
                // sets PC only when the condition is true. When false, PC must still
                // advance to the fall-through address or the interpreter stalls.
                let end_addr = last_addr + instr_size;
                body.push_str("    else:\n");
                body.push_str(&format!("        registers[15] = 0x{:08X}\n", end_addr));
            }
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
                if let Some(_hex_str) = t.split("0x").nth(1).and_then(|s| s.split('\n').next()) {
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
            let func_code = format!("\ndef {}(registers, cpsr):\n", func_name) + &body;
            let lines_to_add = func_code.lines().count() as u64;

            if current_line_count + lines_to_add > max_output_lines {
                return Err(format!(
                    "Output exceeded {} lines, aborting. ROM may be too large or data is being misclassified as code.",
                    max_output_lines
                ));
            }

            block_function_code.push_str(&func_code);
            current_line_count += lines_to_add;
            non_nop_addrs.push((func_start, func_mode_key));
            dispatch_table_set.insert((func_start, func_mode_key));
        }
    }

    // Write all block functions
    code.push_str(&block_function_code);

    // Emit data sections as readable Python hex tables for human inspection.
    // Instructions marked is_data are skipped from codegen above; collect
    // contiguous runs and emit them as named constant tables so the output
    // file documents what data lives where, instead of silently dropping it.
    {
        let mut data_sections: Vec<(u64, Vec<&gbatopy_disasm::DecodedInstruction>)> = Vec::new();
        let mut current_run: Vec<&gbatopy_disasm::DecodedInstruction> = Vec::new();
        let mut run_start: Option<u64> = None;
        let mut prev_data_end: Option<u64> = None;

        for inst in &instructions {
            if inst.is_data {
                let addr = inst.address as u64;
                let end = addr + inst.width as u64;
                if prev_data_end == Some(addr) || prev_data_end.is_none() {
                    if run_start.is_none() {
                        run_start = Some(addr);
                    }
                    current_run.push(inst);
                } else {
                    if !current_run.is_empty() {
                        data_sections.push((run_start.unwrap(), std::mem::take(&mut current_run)));
                    }
                    run_start = Some(addr);
                    current_run.push(inst);
                }
                prev_data_end = Some(end);
            } else {
                if !current_run.is_empty() {
                    data_sections.push((run_start.unwrap(), std::mem::take(&mut current_run)));
                    run_start = None;
                }
                prev_data_end = None;
            }
        }
        if !current_run.is_empty() {
            data_sections.push((run_start.unwrap(), current_run));
        }

        if !data_sections.is_empty() {
            code.push_str("\n# === Data sections (readable hex tables) ===\n");
            for (start, run) in &data_sections {
                let last = run.last().unwrap();
                let end = last.address as u64 + last.width as u64;
                let size = end - start;
                code.push_str(&format!(
                    "# Data at 0x{:08X} ({} bytes, {} entries)\n",
                    start,
                    size,
                    run.len()
                ));
                code.push_str(&format!("data_{:08X} = [\n", start));
                for inst in run {
                    if inst.width == 2 {
                        code.push_str(&format!("    0x{:04X},\n", inst.raw & 0xFFFF));
                    } else {
                        code.push_str(&format!("    0x{:08X},\n", inst.raw));
                    }
                }
                code.push_str("]\n\n");
            }
        }
    }

    // Generate mode-aware jump table dispatch (dict-based for sparse ROMs - reduces memory overhead)
    // Two separate tables so ARM and Thumb functions at the same address don't collide.
    // The disassembler uses linear sweep and may decode the same address as ARM when the
    // CPU is actually in Thumb mode at runtime; separate tables prevent calling the wrong function.
    let base_addr: u64 = 0x08000000;

    code.push_str("dispatch_table_arm = {\n");
    for &(addr, mode) in &non_nop_addrs {
        if mode != ArmMode::Arm {
            continue;
        }
        let idx = (addr - base_addr) >> 2;
        if idx >= 0x100000 {
            continue;
        }
        code.push_str(&format!("    0x{:07X}: func_{:08X}_a,\n", idx, addr));
    }
    code.push_str("}\n\n");

    // Thumb codegen is not yet implemented (instruction_codegen/mod.rs short-circuits
    // all Thumb instructions to `pass`). Registering these stubs in the dispatch table
    // shadows the fallback interpreter, which has full Thumb coverage. Empty the table
    // so the main loop falls through to the fallback interpreter for all Thumb code.
    code.push_str("dispatch_table_thumb = {}\n\n");

    // Add game loop (from generate_game_loop in pipeline.rs)
    code.push_str(&generate_game_loop());

    // Apply minification if requested
    if minify {
        eprintln!("Step 3: Minifying output...");
        // Safe minification: remove blank lines and comment-only lines.
        // Preserves all code lines exactly - no whitespace compression that
        // would break Python syntax (e.g. array.array('B', ...), slices, etc.)
        let mut minified = String::new();
        let mut is_first_line = true;
        for line in code.lines() {
            let trimmed = line.trim();
            // Preserve the shebang on the first line
            if is_first_line && trimmed.starts_with("#!") {
                is_first_line = false;
                minified.push_str(line);
                minified.push('\n');
                continue;
            }
            is_first_line = false;
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
        let mut is_first_line = true;
        let mut in_docstring = false;
        let mut docstring_delimiter = "";

        for line in code.lines() {
            let trimmed = line.trim();

            if is_first_line && trimmed.starts_with("#!") {
                is_first_line = false;
                aggressive.push_str(line);
                aggressive.push('\n');
                continue;
            }
            is_first_line = false;

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
                let delimiter = if trimmed.starts_with("\"\"\"") {
                    "\"\"\""
                } else {
                    "'''"
                };
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
const DELIVER_IRQ_BODY: &str = include_str!("../../assets/templates/deliver_irq_body.py");

fn generate_game_loop() -> String {
    include_str!("../../assets/templates/game_loop.py")
        .replace("__DELIVER_IRQ_BODY__", DELIVER_IRQ_BODY)
        .to_string()
}