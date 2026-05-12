# Scripts

## Struttura

```
scripts/
├── README.md                  ← Questo file
├── screenshot/                ← Cattura e confronto screenshot
│   ├── screenshot.lua         ← Lua script per mGBA
│   └── compare_screenshots.py ← Cattura golden + transpila + confronta
├── verify_all_roms.py         ← Verifica transpilazione tutti i ROM
├── setup/
│   └── download_roms.sh       ← Scarica i test ROM da GitHub
└── verify/
    └── coverage_tracker.py    ← Traccia copertura opcode
```

## Confronto Screenshot

```bash
# Singolo ROM (cattura golden via mGBA + transpila + confronta)
python3 scripts/screenshot/compare_screenshots.py test_roms/roms/stripes.gba

# Se mGBA è in un path diverso
MGBA=/path/to/mgba python3 scripts/screenshot/compare_screenshots.py test_roms/roms/stripes.gba

# Manuale (solo golden)
./mgba/build/sdl/mgba --script scripts/screenshot/screenshot.lua test_roms/roms/stripes.gba
```

Lo script Lua cattura frame 1, 10, 20, 30 usando `callbacks:add("frame", ...)` e `emu:screenshot()`.

`compare_screenshots.py` fa tutto:
1. Esegue mGBA col Lua script per catturare golden screenshot
2. Transpila il ROM con GBAtoPy
3. Esegue il Python generato per catturare output screenshot
4. Confronta pixel per pixel (gestisce risoluzioni diverse)
5. Genera diff immagini e report

## Verifica transpilazione

```bash
# Tutti i ROM
python3 scripts/verify_all_roms.py

# Singolo
cargo run --release -p gbatopy-cli -- pipeline --rom test_roms/roms/arm.gba --output /tmp/test.py
python3 -m py_compile /tmp/test.py
```

## Setup

```bash
# Scarica test ROM (prima volta)
bash scripts/setup/download_roms.sh
```

## Note

- **mGBA non è incluso nel repository** - vedi `../README.md` per istruzioni build
- Gli script Lua usano l'API `emu:currentFrame()`, `emu:runFrame()`, `emu:screenshot()`, `callbacks:add("frame", fn)`
- Tutti gli script vecchi in `verify_roms/`, `lua/`, `mgba/` e vari duplicati sono stati rimossi
