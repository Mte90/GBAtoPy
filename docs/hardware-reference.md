# GBA Hardware Reference

> Single source of truth for GBA hardware specs. Referenced by `AGENTS.md`.

**GBATEK — Authoritative Reference**
- 📚 **[GBATEK GBA Documentation](https://github.com/mgba-emu/gbatek/blob/gh-pages/gba.md)** — The definitive hardware reference for all GBA specifications

## mGBA as Reference Implementation

**If mGBA renders something correctly, GBAtoPy MUST render the same thing.**

This is a **transpiler**, not an emulator with approximate behavior. The generated Python must produce **pixel-perfect** output matching mGBA.

**Rules:**
1. **Never blame the ROM** — If mGBA shows graphics, the ROM is valid and the transpiler has a bug
2. **Test ROMs may use unconventional patterns** — STRH with post-increment, non-standard tilemap strides, partial tile writes — the runtime must handle ALL valid GBA code
3. **mGBA screenshots are gold standard** — Use `compare_screenshots.py` to verify output, not "does it run without crashing"
4. **Edge cases are not excuses** — If a ROM writes tilemap entries with 4-byte stride instead of 2, the renderer must still read them correctly

## CPU

- ARM7TDMI (ARMv4T)
- ARM mode: 32-bit instructions, ~160 unique opcodes
- Thumb mode: 16-bit instructions, ~60 unique opcodes

## Display

- 240×160 pixels, 60 fps
- Background modes: 0-5 (text, affine, bitmap)
- Frame = 228 scanlines (160 visible + 68 VBlank); VCount wraps at 228

## PPU Rendering Modes

- Mode 0: 4BPP text tiles — VERIFIED (shades, hello, helloWorld, hello_world)
- Mode 1: affine BG2 + text BG0/1 — implemented, not verified
- Mode 2: affine BG2/3 — VERIFIED (mode2)
- Mode 3: 16-bit bitmap — VERIFIED (stripes, mode3, bgx)
- Mode 4: 8BPP bitmap — VERIFIED (mode4)
- Mode 5: 160x128 bitmap — implemented, not verified
- Windows, blend, mosaic: register stubs only (not functional)

## Memory Map

| Region | Start | End | Size | Notes |
|--------|-------|-----|------|-------|
| BIOS ROM | 0x00000000 | 0x00003FFF | 16KB | |
| EWRAM | 0x02000000 | 0x0203FFFF | 256KB | |
| IWRAM | 0x03000000 | 0x03007FFF | 32KB | |
| MMIO | 0x04000000 | 0x040003FF | 1KB | Registers |
| Palette RAM | 0x05000000 | 0x050003FF | 1KB | |
| VRAM | 0x06000000 | 0x06017FFF | 96KB | |
| OAM | 0x07000000 | 0x070003FF | 1KB | Object attribute memory |
| Game Pak ROM | 0x08000000 | 0x09FFFFFF | 32MB | |
| Game Pak ROM WS1 | 0x0A000000 | 0x0BFFFFFF | 32MB | Wait state 1 |
| SRAM | 0x0E000000 | 0x0E00FFFF | 64KB | Save RAM |

## Address Mapping Constraint

- MUST handle both absolute addresses (e.g., `0x06000000`) and relative addresses correctly
- Memory regions include mirrors and aliases — verify correct mapping for all accesses
- See `docs/runtime-architecture.md` § "Address Mapping: `_map_address()`" for implementation details
