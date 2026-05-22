# Plan 2: Dynamic Oracle Analysis (mGBA + Lua + Rust)

## 2.1 Objective

Use mGBA as an oracle to collect runtime data that static analysis cannot determine. The oracle provides ground truth about execution paths, memory access patterns, register values, DMA transfers, and interrupt timing.

## 2.2 Architecture

```
ROM ──> mGBA (with Lua scripts) ──> JSONL traces ──> Rust parser ──> Oracle database
```

The oracle pipeline runs the ROM inside mGBA with instrumentation scripts. The scripts output structured data (JSONL/JSON/binary) that the Rust crate `pygba-oracle` parses into a queryable database.

## 2.3 Oracle Data Collection (Lua Scripts)

All Lua scripts live in `scripts/screenshot/` and run inside mGBA's scripting console.

### tracer.lua - Execution Tracer

Logs every instruction executed for N frames.

**Configuration** (global variables at top of file):
```lua
TRACE_FRAMES = 60            -- how many frames to record
TRACE_START_PC = 0x08000000  -- start address filter (0 = disabled)
TRACE_END_PC = 0x08010000    -- end address filter (0 = disabled)
TRACE_LOG_MEMORY = true      -- include memory read/write logs
```

**Output format** (JSONL, one entry per instruction):
```json
{
  "frame": 1,
  "scanline": 45,
  "pc": "0x08000124",
  "opcode": "0xE3A00005",
  "mode": "arm",
  "r0": "0x00000005", "r1": "0x02000000", ... "r13": "0x03007F00", "r14": "0x08000130", "r15": "0x08000128",
  "cpsr": "0x6000001F",
  "flags": {"N": false, "Z": true, "C": false, "V": false},
  "memory": [
    {"address": "0x02000000", "value": "0x00000042", "size": 4, "type": "read"},
    {"address": "0x04000000", "value": "0x00000400", "size": 2, "type": "write"}
  ]
}
```

### memory_profiler.lua - Memory Access Profiler

Tracks which memory regions are accessed and identifies struct candidates.

**Output** (JSON):
```json
{
  "histograms": {
    "BIOS": 120,
    "EWRAM": 45230,
    "IWRAM": 12340,
    "IO": 890,
    "PALRAM": 64,
    "VRAM": 2340,
    "OAM": 128,
    "ROM": 98700,
    "SRAM": 0
  },
  "structs": [
    {"region": "IO", "base": "0x04000000", "size": 4, "accesses": 340, "likely_name": "DISPCNT"},
    {"region": "IO", "base": "0x04000100", "size": 4, "accesses": 120, "likely_name": "TM0CNT"}
  ]
}
```

### vram_dumper.lua - VRAM State Dumper

Periodic snapshots of the display subsystem state.

**Output**: Binary files + JSON metadata every N frames.
- `vram_dump_NNNN.bin`: palette (1KB) + VRAM (96KB) + OAM (1KB)
- `vram_meta_NNNN.json`: frame number, DISPCNT value, display mode

### register_monitor.lua - I/O Register Change Tracker

Monitors all I/O registers (0x04000000-0x040003FE) and logs changes.

**Output** (JSON):
```json
[
  {"frame": 1, "address": "0x04000006", "old": "0x0000", "new": "0x00A0", "register": "VCOUNT"},
  {"frame": 1, "address": "0x040000B0", "old": "0x0000", "new": "0x02000000", "register": "DMA0SAD"}
]
```

### oracle.lua - Master Orchestrator

Loads all scripts and runs a complete analysis session.

```lua
-- Configuration
TRACING_FRAMES = 300
INPUT_SEQUENCE = {"A", "LEFT", "RIGHT", "START"}  -- simulated button presses per frame
DUMP_INTERVAL = 30  -- VRAM dump frequency

-- Loads tracer, memory_profiler, vram_dumper, register_monitor
-- Simulates input at configured intervals
-- Produces complete trace package in output directory
```

## 2.4 Rust Oracle Interface (pygba-oracle)

### Data Structures

```rust
use serde::{Serialize, Deserialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct OracleDB {
    pub traces: Vec<TraceEntry>,
    pub memory_profile: MemoryProfile,
    pub vram_snapshots: Vec<VramSnapshot>,
    pub register_changes: Vec<RegisterChange>,
    pub metadata: OracleMetadata,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct OracleMetadata {
    pub rom_hash: String,
    pub total_frames: u32,
    pub total_instructions: u64,
    pub input_sequence: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TraceEntry {
    pub frame: u32,
    pub scanline: u32,
    pub pc: u32,
    pub opcode: u32,
    pub is_thumb: bool,
    pub registers: [u32; 16],
    pub cpsr: u32,
    pub flags: CpuFlags,
    pub memory_accesses: Vec<MemoryAccess>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct CpuFlags {
    pub negative: bool,
    pub zero: bool,
    pub carry: bool,
    pub overflow: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct MemoryAccess {
    pub address: u32,
    pub value: u32,
    pub size: u8,        // 1, 2, or 4 bytes
    pub access_type: AccessType,
}

#[derive(Debug, Serialize, Deserialize)]
pub enum AccessType { Read, Write }

#[derive(Debug, Serialize, Deserialize)]
pub struct MemoryProfile {
    pub histograms: HashMap<String, u64>,
    pub struct_candidates: Vec<StructCandidate>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct StructCandidate {
    pub region: String,
    pub base: u32,
    pub size: u32,
    pub access_count: u64,
    pub likely_name: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct VramSnapshot {
    pub frame: u32,
    pub palette: Vec<u8>,   // 1KB
    pub vram: Vec<u8>,      // 96KB
    pub oam: Vec<u8>,       // 1KB
    pub dispcnt: u32,
    pub display_mode: u8,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct RegisterChange {
    pub frame: u32,
    pub scanline: u32,
    pub address: u32,
    pub old_value: u32,
    pub new_value: u32,
    pub register_name: Option<String>,
}
```

### API

```rust
pub struct OracleLoader;

impl OracleLoader {
    /// Load oracle data from a directory of JSONL/JSON/binary files
    pub fn load_from_dir(path: &Path) -> Result<OracleDB, OracleError>;

    /// Load from a single JSONL trace file
    pub fn load_traces(path: &Path) -> Result<Vec<TraceEntry>, OracleError>;

    /// Load memory profile JSON
    pub fn load_memory_profile(path: &Path) -> Result<MemoryProfile, OracleError>;
}

pub struct OracleQuery<'a> {
    db: &'a OracleDB,
}

impl<'a> OracleQuery<'a> {
    pub fn new(db: &'a OracleDB) -> Self;

    /// Get all trace entries for a specific address
    pub fn traces_at(&self, address: u32) -> Vec<&TraceEntry>;

    /// Get all memory accesses to a specific address
    pub fn memory_accesses_at(&self, address: u32) -> Vec<&MemoryAccess>;

    /// Get register state at a specific frame
    pub fn registers_at_frame(&self, frame: u32) -> Option<[u32; 16]>;

    /// Get all DMA transfers (detected from register changes)
    pub fn dma_transfers(&self) -> Vec<DmaTransfer>;

    /// Get all interrupt events
    pub fn interrupt_events(&self) -> Vec<InterruptEvent>;

    /// Check if an address was ever executed
    pub fn was_executed(&self, address: u32) -> bool;

    /// Get all unique addresses executed
    pub fn executed_addresses(&self) -> BTreeSet<u32>;

    /// Compare static disassembly coverage vs oracle
    pub fn coverage_report(&self, disasm: &Disassembly) -> CoverageReport;
}

#[derive(Debug)]
pub struct DmaTransfer {
    pub frame: u32,
    pub channel: u8,
    pub source: u32,
    pub destination: u32,
    pub count: u32,
    pub control: u32,
}

#[derive(Debug)]
pub struct InterruptEvent {
    pub frame: u32,
    pub source: String,
    pub handler_address: u32,
}

#[derive(Debug)]
pub struct CoverageReport {
    pub static_blocks: u32,
    pub oracle_blocks: u32,
    pub covered_by_both: u32,
    pub only_static: u32,
    pub only_oracle: u32,
    pub coverage_percent: f64,
}
```

## 2.5 Oracle-Guided Analysis

### Path Validation

Compare the static disassembly's reachable blocks against the oracle's executed addresses:
- Blocks in static but never executed: might be dead code or data misidentified as code
- Blocks executed but not in static: missed code (indirect jumps, computed branches)

### Data Type Inference

The oracle reveals the actual values in registers at each instruction:
- If r0 always holds values 0x02000000-0x0203FFFF: it is an EWRAM pointer
- If r1 always holds small integers 0-255: it is likely a U8
- If r2 holds I/O addresses (0x04000000+): it is a hardware register pointer

### Function Signature Recovery

At each BL call site, the oracle shows:
- r0-r3 values before the call = function parameters
- r0 value after return = return value
- Multiple calls with different values = parameter type hints

### Struct Field Mapping

The memory profiler identifies struct candidates by adjacent access patterns:
- Consecutive accesses to 0x04000100, 0x04000102, 0x04000104 = Timer 0 registers
- Repeated accesses to 0x0200XXXX with stride 4 = array of 32-bit values

### DMA Analysis

Register changes reveal actual DMA configurations:
- DMA0SAD/DAD/CNT writes = DMA transfer setup
- Pattern: write source, write dest, write count+enable = single transfer
- Audio FIFO: DMA1/DMA2 targeting 0x040000A0/A4 = sound FIFO fill

### Interrupt Handler Mapping

When an IRQ fires:
- CPU vectors to 0x03007FFC (IRQ handler pointer)
- The handler address reveals which interrupt routines exist
- Oracle trace shows the full ISR execution path

## 2.6 Multi-Scenario Coverage

Run the oracle with multiple input patterns to maximize code path coverage:

| Scenario | Input | Purpose |
|---|---|---|
| Idle | None | Title screen, initialization code |
| Random | Random buttons per frame | Menu navigation, general gameplay |
| All held | All buttons pressed | Edge cases, input handling |
| Sequence 1 | START, A, A, START | Menu flow |
| Sequence 2 | UP, A, DOWN, A | Menu selection |
| Stress | Rapid alternating | Timing-sensitive code |

Each scenario produces its own trace package. The OracleDB merges all traces for maximum coverage.

## 2.7 Testing

### Lua Script Tests
- Run each script on mGBA with a known ROM
- Verify JSONL output is valid JSON
- Verify expected register values at known checkpoints

### Rust Parser Tests
- Parse sample JSONL files, verify deserialization
- Query API returns correct results for known data
- Coverage report correctly identifies gaps

### Integration Tests
- Run full oracle pipeline on test ROMs
- Compare oracle execution addresses against disassembler output
- Validate that oracle covers >95% of statically reachable code for simple ROMs

## 2.8 Acceptance Criteria

Plan 2 is complete when:
- [ ] All Lua scripts run without errors in mGBA on any test ROM
- [ ] Trace captures >99% of executed instructions (validated against mGBA frame count)
- [ ] Memory profile correctly identifies all hardware register accesses
- [ ] VRAM dumps can be decoded back to valid palette/VRAM/OAM data
- [ ] Oracle database loads and queries in <1 second for 300 frames of trace data
- [ ] Coverage report identifies gaps in static disassembly
- [ ] DMA transfer detection correctly identifies all 4 DMA channels
- [ ] `cargo test -p pygba-oracle` passes all tests
