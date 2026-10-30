# GBA Hardware Reference

> Single source of truth for GBA hardware specs. Referenced by `AGENTS.md`.

**GBATEK — Authoritative Reference**
- 📚 **[GBATEK GBA Documentation](https://github.com/mgba-emu/gbatek/blob/gh-pages/gba.md)** — The definitive hardware reference for all GBA specifications

**Community Hardware References** (found via [awesome-gbadev](https://github.com/gbadev-org/awesome-gbadev)):
- 📖 **[Tonc](https://coranac.com/tonc/text/toc.htm)** — Comprehensive GBA tutorial by Jasper Vijn. Covers CPU, DMA, tiles, sprites, interrupts, timers, BIOS, audio.
- 📖 **[CowBite Spec](https://www.cs.rit.edu/~tjh8300/commodore/CowBite.htm)** — Hardware register reference by Tom Happ. Detailed MMIO register layout.
- 📖 **[copetti.org GBA Architecture](https://www.copetti.org/writings/consoles/game-boy-advanced/)** — System architecture overview with memory map, GPU pipeline, audio pipeline diagrams.
- 📖 **[stuij APU notes](https://github.com/gbadev-org/awesome-gbadev#sound)** — Audio hardware deep-dive linked from awesome-gbadev. Channel timing, FIFO, DMA sound routing.
- 📖 **[GBATEK GBA Sound](https://github.com/mgba-emu/gbatek/blob/gh-pages/gba.md#sound-controller)** — APU register and channel specifications.

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

## Sound Registers

| Address   | Name         | R/W | Width | Description                              |
|-----------|--------------|-----|-------|------------------------------------------|
| 0x04000060 | SOUND1CNT_L  | R/W | 16    | Channel 1 sweep                          |
| 0x04000062 | SOUND1CNT_H  | R/W | 16    | Channel 1 duty/length/envelope           |
| 0x04000064 | SOUND1CNT_X  | R/W | 16    | Channel 1 frequency/control              |
| 0x04000068 | SOUND2CNT_L  | R/W | 16    | Channel 2 duty/length/envelope           |
| 0x0400006C | SOUND2CNT_H  | R/W | 16    | Channel 2 frequency/control              |
| 0x04000070 | SOUND3CNT_L  | R/W | 16    | Channel 3 stop/wave select               |
| 0x04000072 | SOUND3CNT_H  | R/W | 16    | Channel 3 length/volume                  |
| 0x04000074 | SOUND3CNT_X  | R/W | 16    | Channel 3 frequency/control              |
| 0x04000078 | SOUND4CNT_L  | R/W | 16    | Channel 4 length/envelope                |
| 0x0400007C | SOUND4CNT_H  | R/W | 16    | Channel 4 frequency/control              |
| 0x04000080 | SOUNDCNT_L   | R/W | 16    | Master volume + ch1-4 output enables (bits 8-15) |
| 0x04000082 | SOUNDCNT_H   | R/W | 16    | FIFO A/B enables (bits 8/12), output ratio (bits 0-1) |
| 0x04000084 | SOUNDCNT_X   | R/W | 16    | Master enable (bit 7), ch1-4 active status (bits 0-3, read-only) |
| 0x04000088 | SOUNDBIAS    | R/W | 16    | Sound bias / volume control              |
| 0x0400008A | SOUNDSTEP    | R/W | 16    | PWM step (undocumented)                  |
| 0x04000090 | WAVE_RAM     | R/W | 2x32  | Wave pattern RAM (8 entries)             |
| 0x040000A0 | FIFO_A       | W   | 32    | Channel A FIFO                           |
| 0x040000A4 | FIFO_B       | W   | 32    | Channel B FIFO                           |

## PPU Rendering Modes

- Mode 0: 4BPP text tiles — VERIFIED (shades, hello, helloWorld, hello_world)
- Mode 1: affine BG2 + text BG0/1 — verified (F252, 5 unit tests PASS)
- Mode 2: affine BG2/3 — VERIFIED (mode2)
- Mode 3: 16-bit bitmap — VERIFIED (stripes, mode3, bgx)
- Mode 4: 8BPP bitmap — VERIFIED (mode4)
- Mode 5: 160x128 bitmap — implemented
- Windows, blend, mosaic: implemented and verified

### Mode 2 VRAM Layout

With `BG2CNT` char base block (bits 3-2) = 0 and screen base block (bits 12-8) = 1:

| Region | VRAM Offset | Contents |
|--------|-------------|----------|
| 0x06000000 | 0x0000 | Tile data (char block 0) |
| 0x06000800 | 0x0800 | Tilemap (screen block 1) |
| 0x06001000 | 0x1000 | Tilemap (screen block 2) |

When debugging Mode 2 rendering, probe the **tilemap** at `VRAM[screen_block × 0x800]`, not the tile data at `VRAM[0]`. The tilemap entry at the sampled texel coordinate determines which palette index is rendered. With zero affine (BG2PA=BG2PB=BG2PC=BG2PD=0), all pixels sample texel (0,0), so the tilemap entry at offset 0x800 determines the entire screen color.

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
