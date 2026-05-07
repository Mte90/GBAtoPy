# Appendix B: I/O Register Reference

## Display Registers (0x04000000-0x0400005F)

| Address   | Name       | R/W | Width | Description                     |
|-----------|------------|-----|-------|---------------------------------|
| 0x04000000 | DISPCNT    | R/W | 16    | LCD Control                     |
| 0x04000002 | GREENSWAP  | R/W | 16    | Green swap (undocumented)       |
| 0x04000004 | DISPSTAT   | R/W | 16    | General LCD status              |
| 0x04000006 | VCOUNT     | R   | 16    | Vertical counter                |
| 0x04000008 | BG0CNT     | R/W | 16    | BG0 control                     |
| 0x0400000A | BG1CNT     | R/W | 16    | BG1 control                     |
| 0x0400000C | BG2CNT     | R/W | 16    | BG2 control                     |
| 0x0400000E | BG3CNT     | R/W | 16    | BG3 control                     |
| 0x04000010 | BG0HOFS    | W   | 16    | BG0 horizontal offset           |
| 0x04000012 | BG0VOFS    | W   | 16    | BG0 vertical offset             |
| 0x04000014 | BG1HOFS    | W   | 16    | BG1 horizontal offset           |
| 0x04000016 | BG1VOFS    | W   | 16    | BG1 vertical offset             |
| 0x04000018 | BG2HOFS    | W   | 16    | BG2 horizontal offset           |
| 0x0400001A | BG2VOFS    | W   | 16    | BG2 vertical offset             |
| 0x0400001C | BG3HOFS    | W   | 16    | BG3 horizontal offset           |
| 0x0400001E | BG3VOFS    | W   | 16    | BG3 vertical offset             |
| 0x04000020 | BG2PA      | W   | 16    | BG2 rotation/scaling A          |
| 0x04000022 | BG2PB      | W   | 16    | BG2 rotation/scaling B          |
| 0x04000024 | BG2PC      | W   | 16    | BG2 rotation/scaling C          |
| 0x04000026 | BG2PD      | W   | 16    | BG2 rotation/scaling D          |
| 0x04000028 | BG2X       | W   | 32    | BG2 reference X (two writes)    |
| 0x0400002C | BG2Y       | W   | 32    | BG2 reference Y (two writes)    |
| 0x04000030 | BG3PA      | W   | 16    | BG3 rotation/scaling A          |
| 0x04000032 | BG3PB      | W   | 16    | BG3 rotation/scaling B          |
| 0x04000034 | BG3PC      | W   | 16    | BG3 rotation/scaling C          |
| 0x04000036 | BG3PD      | W   | 16    | BG3 rotation/scaling D          |
| 0x04000038 | BG3X       | W   | 32    | BG3 reference X (two writes)    |
| 0x0400003C | BG3Y       | W   | 32    | BG3 reference Y (two writes)    |
| 0x04000040 | WIN0H      | W   | 16    | Window 0 horizontal dims        |
| 0x04000042 | WIN1H      | W   | 16    | Window 1 horizontal dims        |
| 0x04000044 | WIN0V      | W   | 16    | Window 0 vertical dims          |
| 0x04000046 | WIN1V      | W   | 16    | Window 1 vertical dims          |
| 0x04000048 | WININ      | R/W | 16    | Window 0/1 control              |
| 0x0400004A | WINOUT     | R/W | 16    | Window outside control          |
| 0x0400004C | MOSAIC     | W   | 16    | Mosaic size                     |
| 0x04000050 | BLDCNT     | R/W | 16    | Color effect selection          |
| 0x04000052 | BLDALPHA   | R/W | 16    | Alpha blending coefficients     |
| 0x04000054 | BLDY       | W   | 16    | Brightness coefficient          |

### DISPCNT Bit Fields

| Bits  | Name            | Description                        |
|-------|-----------------|------------------------------------|
| 0-2   | BG Mode         | 0=text, 1=text+rot, 2=rot, 3=bmp1, 4=bmp2, 5=bmp3 |
| 3     | CGB Mode        | 0=GBA, 1=CGB compatible            |
| 4     | Frame Select    | Bitmap mode frame (0 or 1)         |
| 5     | H-Blank Free    | Allow OAM access during H-Blank    |
| 6     | OBJ VRAM 1D     | 0=2D mapping, 1=1D mapping         |
| 7     | Forced Blank    | Force blank screen (white)         |
| 8     | BG0 Enable      | Show BG0 layer                     |
| 9     | BG1 Enable      | Show BG1 layer                     |
| 10    | BG2 Enable      | Show BG2 layer                     |
| 11    | BG3 Enable      | Show BG3 layer                     |
| 12    | OBJ Enable      | Show sprites                       |
| 13    | Win0 Enable     | Show Window 0                      |
| 14    | Win1 Enable     | Show Window 1                      |
| 15    | ObjWin Enable   | Show Object Window                 |

### BGCNT Bit Fields (per BG layer)

| Bits  | Name            | Description                        |
|-------|-----------------|------------------------------------|
| 0-1   | Priority        | 0=highest, 3=lowest                |
| 2-3   | Char Base       | Tile data block (0-3, x16KB)       |
| 4-5   | Reserved        | -                                  |
| 6     | Mosaic          | Mosaic effect enable               |
| 7     | Color Mode      | 0=16 colors, 1=256 colors          |
| 8-12  | Screen Base     | Map data block (0-31, x2KB)        |
| 13    | Display Overflow| Wrap-around behavior               |
| 14-15 | Screen Size     | 0=256x256, 1=512x256, 2=256x512, 3=512x512 |

## Sound Registers (0x04000060-0x040000A5)

| Address   | Name         | R/W | Width | Description                   |
|-----------|--------------|-----|-------|-------------------------------|
| 0x04000060 | SOUND1CNT_L  | R/W | 16    | Channel 1 sweep               |
| 0x04000062 | SOUND1CNT_H  | R/W | 16    | Channel 1 duty/length/envelope|
| 0x04000064 | SOUND1CNT_X  | R/W | 16    | Channel 1 frequency/control   |
| 0x04000068 | SOUND2CNT_L  | R/W | 16    | Channel 2 duty/length/envelope|
| 0x0400006C | SOUND2CNT_H  | R/W | 16    | Channel 2 frequency/control   |
| 0x04000070 | SOUND3CNT_L  | R/W | 16    | Channel 3 stop/wave select    |
| 0x04000072 | SOUND3CNT_H  | R/W | 16    | Channel 3 length/volume       |
| 0x04000074 | SOUND3CNT_X  | R/W | 16    | Channel 3 frequency/control   |
| 0x04000078 | SOUND4CNT_L  | R/W | 16    | Channel 4 length/envelope     |
| 0x0400007C | SOUND4CNT_H  | R/W | 16    | Channel 4 frequency/control   |
| 0x04000080 | SOUNDCNT_L   | R/W | 16    | Stereo/volume/enable          |
| 0x04000082 | SOUNDCNT_H   | R/W | 16    | Mixing/DMA control            |
| 0x04000084 | SOUNDCNT_X   | R/W | 16    | Sound master on/off           |
| 0x04000090 | WAVE_RAM     | R/W | 2x32  | Wave pattern RAM (8 entries)  |
| 0x040000A0 | FIFO_A       | W   | 32    | Channel A FIFO                |
| 0x040000A4 | FIFO_B       | W   | 32    | Channel B FIFO                |

## DMA Registers (0x040000B0-0x040000DE)

| Address   | Name       | R/W | Width | Description             |
|-----------|------------|-----|-------|-------------------------|
| 0x040000B0 | DMA0SAD    | R/W | 32    | DMA0 source address     |
| 0x040000B4 | DMA0DAD    | R/W | 32    | DMA0 dest address       |
| 0x040000B8 | DMA0CNT_L  | R/W | 16    | DMA0 word count         |
| 0x040000BA | DMA0CNT_H  | R/W | 16    | DMA0 control            |
| 0x040000BC | DMA1SAD    | R/W | 32    | DMA1 source address     |
| 0x040000C0 | DMA1DAD    | R/W | 32    | DMA1 dest address       |
| 0x040000C4 | DMA1CNT_L  | R/W | 16    | DMA1 word count         |
| 0x040000C6 | DMA1CNT_H  | R/W | 16    | DMA1 control            |
| 0x040000C8 | DMA2SAD    | R/W | 32    | DMA2 source address     |
| 0x040000CC | DMA2DAD    | R/W | 32    | DMA2 dest address       |
| 0x040000D0 | DMA2CNT_L  | R/W | 16    | DMA2 word count         |
| 0x040000D2 | DMA2CNT_H  | R/W | 16    | DMA2 control            |
| 0x040000D4 | DMA3SAD    | R/W | 32    | DMA3 source address     |
| 0x040000D8 | DMA3DAD    | R/W | 32    | DMA3 dest address       |
| 0x040000DC | DMA3CNT_L  | R/W | 16    | DMA3 word count         |
| 0x040000DE | DMA3CNT_H  | R/W | 16    | DMA3 control            |

### DMA Control Bit Fields (CNT_H)

| Bits  | Name           | Description                             |
|-------|----------------|-----------------------------------------|
| 5     | Repeat         | Repeat at next VBlank/HBlank/special    |
| 6     | Word Size      | 0=16-bit, 1=32-bit                      |
| 7     | -              | -                                       |
| 8-9   | DMA Source     | 00=increment, 01=decrement, 10=fixed, 11=prohibited |
| 10-11 | DMA Dest       | 00=increment, 01=decrement, 10=fixed, 11=increment-reload |
| 12-13 | Trigger Mode   | 00=immediate, 01=VBlank, 10=HBlank, 11=special |
| 14    | IRQ            | Fire IRQ on completion                  |
| 15    | Enable         | DMA enable                              |

### DMA Special Trigger Modes

| Channel | Special Trigger                   |
|---------|-----------------------------------|
| DMA0    | Prohibited                        |
| DMA1    | Sound FIFO A (FIFO timer)         |
| DMA2    | Sound FIFO B (FIFO timer)         |
| DMA3    | ROM start (GBA multiboot transfer)|

## Timer Registers (0x04000100-0x0400010E)

| Address   | Name      | R/W | Width | Description            |
|-----------|-----------|-----|-------|------------------------|
| 0x04000100 | TM0CNT_L  | R/W | 16    | Timer 0 count/reload   |
| 0x04000102 | TM0CNT_H  | R/W | 16    | Timer 0 control        |
| 0x04000104 | TM1CNT_L  | R/W | 16    | Timer 1 count/reload   |
| 0x04000106 | TM1CNT_H  | R/W | 16    | Timer 1 control        |
| 0x04000108 | TM2CNT_L  | R/W | 16    | Timer 2 count/reload   |
| 0x0400010A | TM2CNT_H  | R/W | 16    | Timer 2 control        |
| 0x0400010C | TM3CNT_L  | R/W | 16    | Timer 3 count/reload   |
| 0x0400010E | TM3CNT_H  | R/W | 16    | Timer 3 control        |

### Timer Control Bit Fields (CNT_H)

| Bits | Name       | Description                          |
|------|------------|--------------------------------------|
| 0-1  | Prescaler  | 00=/1, 01=/64, 10=/256, 11=/1024    |
| 2    | Cascade    | Count on previous timer overflow     |
| 5    | -          | -                                    |
| 6    | IRQ        | Fire IRQ on overflow                 |
| 7    | Enable     | Timer enable                         |

### Timer Overflow Frequencies

| Prescaler | Frequency      | Overflow Period (16-bit count) |
|-----------|----------------|---------------------------------|
| /1        | 16.78 MHz      | ~3.91 us (count 0xFFFF)         |
| /64       | 262.21 kHz     | ~250 us                         |
| /256      | 65.536 kHz     | ~1.0 ms                         |
| /1024     | 16.384 kHz     | ~4.0 ms                         |

## Keypad Registers (0x04000130-0x04000132)

| Address   | Name      | R/W | Width | Description             |
|-----------|-----------|-----|-------|-------------------------|
| 0x04000130 | KEYINPUT  | R   | 16    | Key state (active LOW)  |
| 0x04000132 | KEYCNT    | R/W | 16    | Key interrupt control   |

### KEYINPUT Bit Mapping

| Bit | Button  | Bit | Button  |
|-----|---------|-----|---------|
| 0   | A       | 5   | LEFT    |
| 1   | B       | 6   | UP      |
| 2   | SELECT  | 7   | DOWN    |
| 3   | START   | 8   | R       |
| 4   | RIGHT   | 9   | L       |

## Interrupt Registers (0x04000200-0x04000208)

| Address   | Name  | R/W | Width | Description               |
|-----------|-------|-----|-------|---------------------------|
| 0x04000200 | IE    | R/W | 16    | Interrupt enable          |
| 0x04000202 | IF    | R/W | 16    | Interrupt flags (write 1 clear) |
| 0x04000208 | IME   | R/W | 16    | Interrupt master enable   |

### Interrupt Source Bits

| Bit | Source   | Bit | Source   |
|-----|----------|-----|----------|
| 0   | VBlank   | 7   | Serial   |
| 1   | HBlank   | 8   | DMA0     |
| 2   | VCounter | 9   | DMA1     |
| 3   | Timer0   | 10  | DMA2     |
| 4   | Timer1   | 11  | DMA3     |
| 5   | Timer2   | 12  | Keypad   |
| 6   | Timer3   | 13  | Game Pak |

## System Registers

| Address   | Name    | R/W | Width | Description           |
|-----------|---------|-----|-------|-----------------------|
| 0x04000204 | WAITCNT | R/W | 16    | Wait state control    |
| 0x04000300 | POSTFLG | R/W | 8     | Post-boot flag        |
| 0x04000301 | HALTCNT | W   | 8     | Halt/stop control     |

### WAITCNT Bit Fields

| Bits  | Name     | Description                          |
|-------|----------|--------------------------------------|
| 0-1   | SRAM WS  | SRAM wait state (0-3)                |
| 2-3   | ROM WS0 N| ROM first access WS0 (0-3)           |
| 4     | ROM WS0 S| ROM second access WS0 (0-1)          |
| 5-6   | ROM WS1 N| ROM first access WS1 (0-3)           |
| 7     | ROM WS1 S| ROM second access WS1 (0-1)          |
| 8-9   | ROM WS2 N| ROM first access WS2 (0-3)           |
| 10    | ROM WS2 S| ROM second access WS2 (0-1)          |
| 11    | PHI Term | PHI terminal pin output (0=disable)  |
| 12    | -        | -                                    |
| 13    | Prefetch | Game Pak prefetch buffer enable      |
| 14    | CGB      | Game Pak type flag (0=GBA, 1=CGB)   |
| 15    | -        | -                                    |

## Serial Registers (0x04000120-0x0400015A)

| Address   | Name          | R/W | Width | Description              |
|-----------|---------------|-----|-------|--------------------------|
| 0x04000120 | SIODATA32     | R/W | 32    | SIO data (32-bit mode)   |
| 0x04000120 | SIOMULTI0     | R/W | 16    | Multiplayer data 0       |
| 0x04000122 | SIOMULTI1     | R   | 16    | Multiplayer data 1       |
| 0x04000124 | SIOMULTI2     | R   | 16    | Multiplayer data 2       |
| 0x04000126 | SIOMULTI3     | R   | 16    | Multiplayer data 3       |
| 0x04000128 | SIOCNT        | R/W | 16    | SIO control              |
| 0x0400012A | SIOMLT_SEND   | R/W | 16    | Multiplayer send data    |
| 0x04000134 | RCNT          | R/W | 16    | SIO mode / GPIO          |
| 0x04000140 | JOYCNT        | R/W | 16    | JOY bus control          |
| 0x04000150 | JOY_RECV      | R/W | 32    | JOY bus receive          |
| 0x04000154 | JOY_TRANS     | R/W | 32    | JOY bus transmit         |
| 0x04000158 | JOYSTAT       | R   | 16    | JOY bus status           |
