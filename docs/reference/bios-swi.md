# Appendix C: BIOS SWI Functions

## SWI Calling Convention

ARM SWI (Software Interrupt) instruction triggers a BIOS routine. On the GBA:

- **ARM mode**: `SWI #imm24` (imm24 = SWI number, bits [23:0] of instruction)
- **Thumb mode**: `SWI #imm8` (imm8 = SWI number, bits [7:0] of instruction)
- **Parameters**: Passed in registers r0-r3
- **Return value**: In r0 (sometimes r0-r1 for 64-bit values)
- **Caller-saved**: r0-r3, r12 may be modified. r4-r11, SP, LR preserved.

The SWI number is the instruction's immediate field. In ARM mode, the top 24 bits; in Thumb mode, the bottom 8 bits.

## Complete SWI Function Table

| SWI # | Name              | Parameters (r0-r3)                     | Return (r0)         | Notes                     |
|-------|-------------------|----------------------------------------|---------------------|---------------------------|
| 0x00  | SoftReset         | -                                      | -                   | Resets to startup         |
| 0x01  | RegisterRamReset  | r0=reset flags                         | -                   | Clears RAM regions        |
| 0x02  | Halt              | -                                      | -                   | Halts CPU until IRQ       |
| 0x03  | Stop              | r0=force flags                         | -                   | Low-power stop mode       |
| 0x04  | IntrWait          | r0=clear flag, r1=IRQ mask             | -                   | Wait for interrupt        |
| 0x05  | VBlankIntrWait    | r0=clear flag                          | -                   | Wait for VBlank IRQ       |
| 0x06  | Div               | r0=numerator, r1=denominator          | r0=result (s32)     | Signed 32-bit division    |
| 0x07  | DivArm            | r0=denominator, r1=numerator          | r0=result (s32)     | Reversed param order      |
| 0x08  | Sqrt              | r0=value (u32)                         | r0=result (u32)     | Integer square root       |
| 0x09  | ArcTan            | r0=angle param (s16, 0-65535=x/16384) | r0=result (s32)     | Arctangent                |
| 0x0A  | ArcTan2            | r0=x (s16), r1=y (s16)                | r0=angle (s16)      | Arctangent2               |
| 0x0B  | CpuSet            | r0=src, r1=dst, r2=mode/count          | -                   | Memory copy               |
| 0x0C  | CpuFastSet        | r0=src, r1=dst, r2=mode/count          | -                   | Fast 32-bit memory copy   |
| 0x0D  | GetBiosChecksum   | -                                      | r0=checksum (u32)   | BIOS checksum             |
| 0x0E  | BgAffineSet       | r0=src struct, r1=dst struct, r2=count | -                   | BG affine transformation  |
| 0x0F  | ObjAffineSet      | r0=src struct, r1=dst struct, r2=count, r3=type | -          | OAM affine transformation |
| 0x10  | BitUnPack         | r0=src, r1=dst, r2=header              | -                   | Bit depth expansion       |
| 0x11  | LZ77UnCompWram    | r0=src, r1=dst                         | -                   | LZ77 decompress to WRAM   |
| 0x12  | LZ77UnCompVram    | r0=src, r1=dst                         | -                   | LZ77 decompress to VRAM   |
| 0x13  | HuffUnComp        | r0=src, r1=dst                         | -                   | Huffman decompress        |
| 0x14  | RLUnCompWram      | r0=src, r1=dst                         | -                   | Run-length to WRAM        |
| 0x15  | RLUnCompVram      | r0=src, r1=dst                         | -                   | Run-length to VRAM        |
| 0x16  | Diff8bitUnFilterWram | r0=src, r1=dst                      | -                   | 8-bit delta filter        |
| 0x17  | Diff8bitUnFilterVram | r0=src, r1=dst                      | -                   | 8-bit delta to VRAM       |
| 0x18  | Diff16bitUnFilter  | r0=src, r1=dst                        | -                   | 16-bit delta filter       |
| 0x19  | SoundBias         | r0=level (0=reduce, 0x0001=normal)    | -                   | Sound bias level          |
| 0x1A  | SoundDriverInit   | r0=player workspace                   | -                   | Init music player         |
| 0x1B  | SoundDriverMode   | r0=mode flags                          | -                   | Music player mode         |
| 0x1C  | SoundDriverMain   | -                                      | -                   | Music player tick         |
| 0x1D  | SoundDriverVSync  | -                                      | -                   | VBlank music sync         |
| 0x1E  | SoundChannelClear  | -                                      | -                   | Clear sound channels      |
| 0x1F  | MidiKey2Freq      | r0=sample, r1=key, r2=fine adjust     | r0=frequency (u32)  | MIDI key to frequency     |
| 0x20  | MusicPlayerOpen   | r0=player, r1=work area               | -                   | Open music player         |
| 0x21  | MusicPlayerStart  | r0=player                              | -                   | Start playback            |
| 0x22  | MusicPlayerStop   | r0=player                              | -                   | Stop playback             |
| 0x23  | MusicPlayerContinue | r0=player                            | -                   | Continue playback         |
| 0x24  | SoundClearPCM     | r0=PSG channel mask                    | -                   | Clear PSG channels        |
| 0x25  | MultiBoot         | r0=multiboot struct, r1=mode, r2=count| r0=result           | Multiboot send            |
| 0x26  | HardReset         | -                                      | -                   | Full system reset         |
| 0x27  | SoundDriverVSyncOff | -                                    | -                   | Disable VSync sound sync  |
| 0x28  | SoundDriverJmpBuf  | -                                    | -                   | Jump buffer for sound     |

### Notes on Key Functions

**SWI 0x05 (VBlankIntrWait)**: Most commonly used SWI. Games call this in their main loop to wait for the next VBlank (60fps timing). Parameters: r0 should be 1 to clear IF register, r1 should be IRQ_VBLANK flag. The BIOS enters low-power halt until VBlank IRQ fires.

**SWI 0x06 (Div)**: Signed 32-bit integer division. r0/r1 = result in r0. Also returns remainder in r1, absolute value of quotient in r3.

**SWI 0x08 (Sqrt)**: Integer square root. Returns floor(sqrt(r0)). Fast hardware-assisted calculation.

**SWI 0x0B (CpuSet)**: Memory copy with options. r2 bit 26 = fill mode (copy r0 value repeatedly), bit 24 = 32-bit (0=16-bit). Bits 0-20 = word count.

**SWI 0x0C (CpuFastSet)**: Optimized 32-bit copy. Always 32-bit, count in words (not bytes). r2 bit 24 = fill mode.

**SWI 0x11/0x12 (LZ77)**: Decompress LZ77-compressed data. VRAM variant writes in 32-bit units (no byte writes to VRAM).

**SWI 0x0E (BgAffineSet)**: Calculates BG rotation/scaling parameters. Input: PA, PB, PC, PD, CX, CY. Output: PA, PB, PC, PD, X, Y (internal format).

**SWI 0x0F (ObjAffineSet)**: Calculates OAM affine parameters. Similar to BgAffineSet but outputs to OAM format.

**SWI 0x04 (IntrWait)**: General-purpose interrupt wait. r0=1 clears IF before waiting. r1=IRQ mask bits. Waits until any enabled interrupt in the mask fires.
