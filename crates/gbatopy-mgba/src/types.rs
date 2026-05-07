use serde::{Deserialize, Serialize};

use gbatopy_disasm::{ArmMode, Condition};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AccessKind {
    Read,
    Write,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryAccess {
    pub kind: AccessKind,
    pub address: u32,
    pub size: u8,
    pub value: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegisterState {
    pub r0: u32,
    pub r1: u32,
    pub r2: u32,
    pub r3: u32,
    pub r4: u32,
    pub r5: u32,
    pub r6: u32,
    pub r7: u32,
    pub r8: u32,
    pub r9: u32,
    pub r10: u32,
    pub r11: u32,
    pub r12: u32,
    pub sp: u32,
    pub lr: u32,
    pub pc: u32,
    pub cpsr: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceEntry {
    pub address: u32,
    pub opcode: String,
    pub raw: u32,
    pub mode: ArmMode,
    pub condition: Option<Condition>,
    pub registers_before: RegisterState,
    pub registers_after: RegisterState,
    pub memory_accesses: Vec<MemoryAccess>,
    pub branch_taken: Option<bool>,
    pub frame_number: u64,
    pub cycle_count: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OracleMode {
    Runtime,
    StaticOnly,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceMetadata {
    pub timestamp: String,
    pub mgba_version: Option<String>,
    pub mode: OracleMode,
    pub instruction_count: u64,
    pub duration_ms: u64,
    pub mode_switches: Vec<(u32, ArmMode)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OracleTrace {
    pub rom_path: String,
    pub rom_size: usize,
    pub entries: Vec<TraceEntry>,
    pub metadata: TraceMetadata,
}

use std::collections::HashMap;

/// Insights extracted from oracle traces for downstream phases
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TraceInsights {
    /// Observed values per register (register index -> values)
    pub register_values: HashMap<u8, Vec<u32>>,
    /// Unique MMIO addresses accessed
    pub mmio_accesses: Vec<u32>,
    /// VRAM addresses written
    pub vram_writes: Vec<u32>,
}

/// Consume oracle trace entries and extract insights for type inference and asset extraction
pub fn consume_traces(entries: &[TraceEntry]) -> TraceInsights {
    let mut register_values: HashMap<u8, Vec<u32>> = HashMap::new();
    let mut mmio_accesses: Vec<u32> = Vec::new();
    let mut vram_writes: Vec<u32> = Vec::new();

    // GBA memory map constants
    const VRAM_START: u32 = 0x06000000;
    const VRAM_END: u32 = 0x07000000;
    const MMIO_START: u32 = 0x04000000;
    const MMIO_END: u32 = 0x05000000;

    for entry in entries {
        // Extract register values (r0-r12, sp, lr, pc)
        let regs = [
            (0, entry.registers_after.r0),
            (1, entry.registers_after.r1),
            (2, entry.registers_after.r2),
            (3, entry.registers_after.r3),
            (4, entry.registers_after.r4),
            (5, entry.registers_after.r5),
            (6, entry.registers_after.r6),
            (7, entry.registers_after.r7),
            (8, entry.registers_after.r8),
            (9, entry.registers_after.r9),
            (10, entry.registers_after.r10),
            (11, entry.registers_after.r11),
            (12, entry.registers_after.r12),
            (13, entry.registers_after.sp),
            (14, entry.registers_after.lr),
            (15, entry.registers_after.pc),
        ];

        for (idx, val) in regs {
            if val != 0 {
                register_values.entry(idx).or_default().push(val);
            }
        }

        // Analyze memory accesses
        for access in &entry.memory_accesses {
            let addr = access.address;

            // Check for MMIO region (I/O registers)
            if (MMIO_START..MMIO_END).contains(&addr) {
                if !mmio_accesses.contains(&addr) {
                    mmio_accesses.push(addr);
                }
            }

            // Check for VRAM writes
            if access.kind == AccessKind::Write && (VRAM_START..VRAM_END).contains(&addr) {
                if !vram_writes.contains(&addr) {
                    vram_writes.push(addr);
                }
            }
        }
    }

    // Sort for deterministic output
    mmio_accesses.sort();
    vram_writes.sort();

    TraceInsights {
        register_values,
        mmio_accesses,
        vram_writes,
    }
}

pub type Result<T> = std::result::Result<T, super::Error>;
