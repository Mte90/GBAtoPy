use crate::asset_extractor::extract_assets;

#[allow(unused_imports)]
use crate::ppu::generate_ppu_code;
use gbatopy_disasm::{
    operand::AddressingMode, operand::Operand, CfgBuilder, Disassembler,
};
use std::fs;

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
    /// Detect which features are used by scanning the ROM for MMIO accesses
    /// This analyzes the disassembled instructions to find hardware register usage
    pub fn detect_from_instructions(instructions: &[gbatopy_disasm::DecodedInstruction]) -> Self {
        let mut flags = Self {
            audio: false,
            irq: false,
            timers: false,
            dma: false,
            numba: true, // numba enabled by default even in detection
        };

        // MMIO address ranges for different hardware features
        // Audio: 0x04000060-0x0400008F (SOUNDCNT_L, SOUNDCNT_H, SOUNDCNT_X, etc.)
        const AUDIO_START: u32 = 0x04000060;
        const AUDIO_END: u32 = 0x0400008F;

        // IRQ: IE (0x04000200), IF (0x04000202), IME (0x04000208)
        const IRQ_START: u32 = 0x04000200;
        const IRQ_END: u32 = 0x04000209;

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
                    #[allow(clippy::collapsible_match)]
                    Operand::MemoryAddress {
                        base: _, offset, ..
                    } => {
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

fn disassemble_rom(
    rom: &[u8],
    max_output_lines: u64,
) -> Result<(Vec<gbatopy_disasm::DecodedInstruction>, CfgBuilder), String> {
    let mut cfg = CfgBuilder::new();
    cfg.build_from_entry(rom, 0x08000000);
    let reachable: Vec<u32> = cfg.get_reachable_addresses().to_vec();
    eprintln!("  CFG found {} reachable addresses", reachable.len());

    const ESTIMATED_LINES_PER_INSTRUCTION: u64 = 15;
    let estimated_output_lines = reachable.len() as u64 * ESTIMATED_LINES_PER_INSTRUCTION;
    if estimated_output_lines > max_output_lines {
        return Err(format!(
            "Output would be ~{} lines ({} reachable addresses * ~{} lines each), exceeds limit of {}. The CFG likely misclassified audio/graphic data as code. Use --max-output-lines to raise the limit.",
            estimated_output_lines,
            reachable.len(),
            ESTIMATED_LINES_PER_INSTRUCTION,
            max_output_lines
        ));
    }

    let mut disasm = Disassembler::new();
    let mut instructions = disasm.selective_disassemble(rom, &reachable, &cfg.mode_map);
    let data_stats = disasm.mark_data_regions(&mut instructions);
    eprintln!(
        "  Disassembled {} instructions ({} marked as data in {} regions)",
        instructions.len(),
        data_stats.data_instructions_marked,
        data_stats.unknown_regions_found
    );

    Ok((instructions, cfg))
}

pub fn run_pipeline(
    rom_path: &str,
    output_path: &str,
    feature_flags: Option<FeatureFlags>,
    minify: bool,
    minify_aggressive: bool,
    max_output_lines: u64,
) -> Result<(), String> {
    let rom = fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    eprintln!("Step 1: CFG-based Disassembly");
    let (instructions, cfg) = disassemble_rom(&rom, max_output_lines)?;

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

    // Phase 3: Python Code Generation
    crate::codegen::generate_python_code(
        instructions,
        &cfg,
        &rom,
        &flags,
        &assets,
        output_path,
        minify,
        minify_aggressive,
        max_output_lines,
    )
}

