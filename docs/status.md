# Implementation Status

Honest assessment of what works and what doesn't.

## Pipeline

| Stage | Status | Notes |
|-------|--------|-------|
| Disassembler | Partial | Decodes basic ARM/Thumb instructions. Missing ~150 of ~220 ARMv4T opcodes. |
| Oracle | Partial | mGBA fork builds. Traces are collected but never consumed by downstream phases. |
| IR Lifter | Non-functional | Framework exists but produces empty `vec![]` statements. Covers ~8 ARM opcodes. |
| Type Recovery | Non-functional | Crate compiles but is not integrated into the pipeline. |
| Codegen | Broken | Generates individual Python functions but never builds `func_map` dispatch dictionary. 603 functions sit unused. |

## Python Runtime

| Module | Status | Notes |
|--------|--------|-------|
| Memory / MMIO | Partial | Handles immediate-address MMIO writes. Register-indirect access not supported. |
| PPU Backgrounds | Partial | Tile rendering produces solid colors. Mode 0-7 framework exists but output is wrong. |
| PPU Sprites | Missing | OAM processing completely unimplemented. No sprites render. |
| APU | Non-functional | `start()` is never called. Mixer init not lazy. Thread safety issues. |
| DMA | Broken | Pending flag never cleared after transfer. Stuck after first DMA. |
| BIOS SWI | Partial | Sqrt works. 4 other handlers stubbed with `pass` or `return 0`. |
| Input | Unverified | Keyboard maps to KEYINPUT but never tested against actual game state. |
| VBlank | Missing | DISPSTAT VBlank flag never set. Blocks all BIOS wait loops. |

## End-to-End

| Capability | Works? |
|------------|--------|
| ROM loads and disassembles | Yes |
| Python file generates | Yes |
| Python file runs without crash | Partially (errors on some ROMs) |
| Game renders graphics | No (black screen on all 41 test ROMs) |
| Game renders graphics | No (black screen on all 41 test ROMs) |
| Keyboard input affects game | Unverified |

## What Needs Fixing (Priority Order)

1. **Codegen func_map** — Without function dispatch, nothing else matters
2. **VBlank flag** — Games hang in infinite loops waiting for VBlank
3. **DMA pending flag** — DMA transfers break after first use
4. **Asset extraction** — Palette, tiles, sprites arrays stay empty
5. **PPU sprites** — No game can render characters/objects
6. **APU start()** — Audio never plays
7. **IR lifter population** — Empty IR means no optimization or type flow
8. **Oracle integration** — Traces collected but wasted
9. **Instruction coverage** — Missing ~150 opcodes cause unknown instruction warnings

## Test ROMs

41 ROMs across 18 suites. All generate Python. All produce black screen.

| Suite | ROMs | Status |
|-------|------|--------|
| jsmolka/gba-tests | 16 | Black screen |
| armwrestler-gba | 1 | Black screen |
| FuzzARM | 1 | Black screen |
| libbet | 1 | Black screen |
| GBA-Test-Collection | 1 | Black screen |
| destoer/gba_tests | 4 | Black screen |
| enhancedcontrolcheckerGBA | 1 | Black screen |
| gba-sound-demo | 1 | Black screen |
| hw-test | 3 | Black screen |
| FalseDiagonalTest | 1 | Black screen |
| gba-playground | 2 | Black screen |
| tonc | 1 | Black screen |
| blargg | 3 | Black screen |
| misc/custom | 4 | Black screen |
