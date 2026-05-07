# Appendix A: GBA Memory Map

## Complete Memory Map (GBATEK Reference)

| Start Address  | End Address    | Size    | Name        | Bus Width | Wait States | Notes                          |
|----------------|----------------|---------|-------------|-----------|-------------|--------------------------------|
| 0x00000000     | 0x00003FFF     | 16 KB   | BIOS ROM    | 32-bit    | 1 cycle     | Read-only, protected after boot |
| 0x02000000     | 0x0203FFFF     | 256 KB  | EWRAM       | 16-bit    | 3/6 cycles  | External work RAM              |
| 0x03000000     | 0x03007FFF     | 32 KB   | IWRAM       | 32-bit    | 1 cycle     | Internal work RAM              |
| 0x04000000     | 0x040003FF     | 1 KB    | I/O         | 32-bit    | 1 cycle     | Memory-mapped I/O registers    |
| 0x05000000     | 0x050003FF     | 1 KB    | Palette RAM | 16-bit    | 1/2 cycles  | Background + sprite palettes   |
| 0x06000000     | 0x06017FFF     | 96 KB   | VRAM        | 16-bit    | 1/2 cycles  | Video RAM                      |
| 0x07000000     | 0x070003FF     | 1 KB    | OAM         | 32-bit    | 1/2 cycles  | Object Attribute Memory        |
| 0x08000000     | 0x09FFFFFF     | 32 MB   | ROM WS0     | 16-bit    | 5/8 cycles  | Game Pak ROM, wait state 0     |
| 0x0A000000     | 0x0BFFFFFF     | 32 MB   | ROM WS1     | 16-bit    | 5/8 cycles  | Game Pak ROM, wait state 1     |
| 0x0C000000     | 0x0DFFFFFF     | 32 MB   | ROM WS2     | 16-bit    | 5/8 cycles  | Game Pak ROM, wait state 2     |
| 0x0E000000     | 0x0E00FFFF     | 64 KB   | SRAM        | 8-bit     | 5 cycles    | Save memory (battery-backed)   |

## Mirror Addresses

Most memory regions are mirrored at higher addresses:

| Region   | Physical Range      | Mirror Pattern                                       |
|----------|----------------------|-------------------------------------------------------|
| BIOS     | 0x00000000-3FFF     | Mirrored at 0x01-0x1FFFxxxx (upper address bits ignored) |
| EWRAM    | 0x02000000-3FFFFF   | Mirrored at 0x024-0x02F (only 0x020-0x023 valid)         |
| IWRAM    | 0x03000000-07FFFF   | Mirrored at 0x031-0x03F (only 0x030 valid)               |
| I/O      | 0x04000000-03FF     | Mirrored at 0x041-0x04F                                  |
| VRAM     | 0x06000000-17FFF    | Mirrored at 0x062-0x06F (only 0x060-0x061 valid)         |
| ROM      | 0x08000000-FFFFFF   | Repeated every 32MB: 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D  |

## Memory Access Sizes

| Region   | 8-bit Read | 16-bit Read | 32-bit Read | 8-bit Write | 16-bit Write | 32-bit Write |
|----------|------------|-------------|-------------|-------------|--------------|--------------|
| BIOS     | Yes        | Yes         | Yes         | No          | No           | No           |
| EWRAM    | Yes        | Yes         | Yes         | Yes         | Yes          | Yes          |
| IWRAM    | Yes        | Yes         | Yes         | Yes         | Yes          | Yes          |
| I/O      | Yes        | Yes         | Yes         | Yes         | Yes          | Yes          |
| Palette  | No         | Yes         | Yes         | No          | Yes          | Yes          |
| VRAM     | No         | Yes         | Yes         | No          | Yes          | Yes          |
| OAM      | No         | Yes         | Yes         | No          | Yes          | Yes          |
| ROM      | Yes        | Yes         | Yes         | No          | No           | No           |
| SRAM     | Yes        | No          | No          | Yes         | No           | No           |

## GBA Byte-Write Quirks (from GBATEK)

When writing a byte to a 16-bit or 32-bit bus region, the GBA does NOT simply write that byte. Instead:

- **16-bit bus (EWRAM, Palette, VRAM, OAM)**: Writing to odd address writes the upper byte of the halfword. Writing to even address writes the lower byte. Both modify the full halfword.
- **32-bit bus (IWRAM, I/O)**: Writing a byte actually writes all 4 bytes of the word, each with the same value.

This is critical for the runtime to emulate correctly.

## DMA Access Restrictions

| DMA Channel | Can Read From          | Can Write To           |
|-------------|------------------------|------------------------|
| DMA0        | EWRAM, IWRAM, I/O      | EWRAM, IWRAM, I/O      |
| DMA1        | All + ROM + Audio FIFO | All + Audio FIFO       |
| DMA2        | All + ROM + Audio FIFO | All + Audio FIFO       |
| DMA3        | All + ROM + SRAM       | All + SRAM             |

DMA0 cannot access ROM or SRAM. DMA3 is the only channel that can write to SRAM.

## ROM Header Structure (at 0x08000000)

| Offset | Size | Field                    |
|--------|------|--------------------------|
| 0x000  | 4    | ARM branch instruction   |
| 0x004  | 156  | Nintendo logo data       |
| 0x0A0  | 12   | Game title (ASCII)       |
| 0x0AC  | 4    | Game code (ASCII)        |
| 0x0B0  | 2    | Maker code               |
| 0x0B2  | 1    | Fixed value (0x96)       |
| 0x0B3  | 1    | Main unit code (0x00)    |
| 0x0B4  | 1    | Device type (0x00)       |
| 0x0B5  | 7    | Reserved                 |
| 0x0BC  | 1    | Software version         |
| 0x0BD  | 1    | Complement check         |
| 0x0BE  | 2    | Reserved                 |
| 0x0C0  | 4    | ARM branch (entry point) |

## ARM Exception Vectors (at 0x00000000 in BIOS, mirrored at ROM base)

| Address   | Exception          | Notes                          |
|-----------|--------------------|--------------------------------|
| 0x000000  | Reset              | Jumps to 0x08000000           |
| 0x000004  | Undefined Instr    | Jumps to 0x08000004           |
| 0x000008  | SWI                | Jumps to 0x08000008           |
| 0x00000C  | Prefetch Abort     | Jumps to 0x0800000C           |
| 0x000010  | Data Abort         | Jumps to 0x08000010           |
| 0x000014  | Reserved           | -                              |
| 0x000018  | IRQ                | Jumps to 0x08000018           |
| 0x00001C  | FIQ                | Jumps to 0x0800001C           |
