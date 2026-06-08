# Scripts

## Structure

```
scripts/
├── README.md                  ← This file
├── screenshot/                ← mGBA Lua scripts and golden screenshots
│   └── golden/                ← Golden screenshots for comparison
├── setup/
│   └── download_roms.sh       ← Downloads test ROMs from GitHub
└── verify/
    └── coverage_tracker.py    ← Tracks opcode coverage
```

## Transpilation Verification

```bash
# Single ROM
cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/arm.gba --output /tmp/arm.py
python3 -m py_compile /tmp/arm.py
```

## Setup

```bash
# Download test ROMs (first time only)
bash scripts/setup/download_roms.sh
```

## Notes

- **mGBA is not included in the repository** — see `../README.md` for build instructions
- Screenshot comparison and visual testing are now handled by the Rust test crate (`gbatopy-tests`)
- All old scripts in `verify_roms/`, `lua/`, `mgba/` and various duplicates have been removed
