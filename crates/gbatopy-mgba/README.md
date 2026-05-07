# gbatopy-mgba

Runtime tracing for GBA ROMs using mGBA.

## What it does

Collects register values and memory access patterns while a ROM runs. Feeds type inference downstream.

## Build

```bash
cargo build --release
```

## Usage

```rust
use gbatopy_mgba::{MgbaConfig, MgbaOracle};

let config = MgbaConfig {
    rom_path: "game.gb".to_string(),
    max_instructions: 10000,
    timeout_seconds: 30,
    output_path: "/tmp/oracle.json".to_string(),
};

let oracle = MgbaOracle::new(config);
let trace = oracle.run()?;
```

## Lua script

`scripts/lua/oracle_trace.lua` runs inside mGBA to capture traces. JSON output at program exit.
