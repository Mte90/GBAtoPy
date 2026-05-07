# Appendix D: ARM/Thumb Instruction Quick Reference

## ARM Instruction Encoding (32-bit)

All ARM instructions are conditionally executed. Top 4 bits = condition code.

### Condition Codes (bits [31:28])

| Code | Suffix | Flags Tested            |
|------|--------|-------------------------|
| 0000 | EQ     | Z=1                     |
| 0001 | NE     | Z=0                     |
| 0010 | CS/HS  | C=1                     |
| 0011 | CC/LO  | C=0                     |
| 0100 | MI     | N=1                     |
| 0101 | PL     | N=0                     |
| 0110 | VS     | V=1                     |
| 0111 | VC     | V=0                     |
| 1000 | HI     | C=1 AND Z=0             |
| 1001 | LS     | C=0 OR Z=1              |
| 1010 | GE     | N=V                     |
| 1011 | LT     | N!=V                    |
| 1100 | GT     | Z=0 AND N=V             |
| 1101 | LE     | Z=1 OR N!=V             |
| 1110 | AL     | Always (default)        |
| 1111 | NV     | Never (reserved on ARM7TDMI) |

### Data Processing (bits [27:26] = 00)

```
[31:28] Condition
[27:26] 00
[25]    I = Immediate operand flag
[24:21] Opcode
[20]    S = Set condition codes
[19:16] Rn = First operand register
[15:12] Rd = Destination register
[11:0]  Operand 2 (shifted register or immediate)
```

### Branch (bits [27:25] = 101)

```
[31:28] Condition
[27:25] 101
[24]    L = Link (1=BL, 0=B)
[23:0]  Signed offset (shift left 2, add to PC+8)
```

### Single Load/Store (bits [27:26] = 01)

```
[31:28] Condition
[27:26] 01
[25]    I = Offset format (0=register, 1=immediate)
[24]    P = Pre/post indexing
[23]    U = Up/down (add/subtract offset)
[22]    B = Byte/word (1=byte)
[21]    W = Write-back
[20]    L = Load/store (1=load)
[19:16] Rn = Base register
[15:12] Rd = Source/Dest register
[11:0]  Offset
```

### Load/Store Multiple (bits [27:25] = 100)

```
[31:28] Condition
[27:25] 100
[24]    P = Pre/post
[23]    U = Up/down
[22]    S = PSR & force user bit
[21]    W = Write-back
[20]    L = Load/store
[19:16] Rn = Base register
[15:0]  Register list (bit per register)
```

### Software Interrupt (bits [27:24] = 1111)

```
[31:28] Condition
[27:24] 1111
[23:0]  Comment field (SWI number)
```

## ARM Data Processing Opcodes

| [24:21] | Mnemonic | Operation          | Rd Written | Flags (S=1) |
|---------|----------|--------------------|------------|-------------|
| 0000    | AND      | Rd = Rn AND Op2    | Yes        | N,Z,C,V     |
| 0001    | EOR      | Rd = Rn EOR Op2    | Yes        | N,Z,C       |
| 0010    | SUB      | Rd = Rn - Op2      | Yes        | N,Z,C,V     |
| 0011    | RSB      | Rd = Op2 - Rn      | Yes        | N,Z,C,V     |
| 0100    | ADD      | Rd = Rn + Op2      | Yes        | N,Z,C,V     |
| 0101    | ADC      | Rd = Rn + Op2 + C  | Yes        | N,Z,C,V     |
| 0110    | SBC      | Rd = Rn - Op2 - !C | Yes        | N,Z,C,V     |
| 0111    | RSC      | Rd = Op2 - Rn - !C | Yes        | N,Z,C,V     |
| 1000    | TST      | Rn AND Op2         | No         | N,Z,C       |
| 1001    | TEQ      | Rn EOR Op2         | No         | N,Z,C       |
| 1010    | CMP      | Rn - Op2           | No         | N,Z,C,V     |
| 1011    | CMN      | Rn + Op2           | No         | N,Z,C,V     |
| 1100    | ORR      | Rd = Rn OR Op2     | Yes        | N,Z,C       |
| 1101    | MOV      | Rd = Op2           | Yes        | N,Z,C       |
| 1110    | BIC      | Rd = Rn AND NOT Op2| Yes        | N,Z,C       |
| 1111    | MVN      | Rd = NOT Op2       | Yes        | N,Z,C       |

## ARM Barrel Shifter

Operand 2 (bits [11:0]) can be:
- **Immediate**: bit [25]=1, 8-bit value rotated right by 2 * rotate_imm (bits [11:8])
- **Register with shift**: bit [25]=0
  - Shift by immediate (bits [11:7]): 5-bit shift amount
  - Shift by register (bit [4]=1): bottom byte of Rs register

Shift types (bits [6:5]):
| [6:5] | Type | Operation                    |
|-------|------|------------------------------|
| 00    | LSL  | Logical Shift Left           |
| 01    | LSR  | Logical Shift Right          |
| 10    | ASR  | Arithmetic Shift Right       |
| 11    | ROR  | Rotate Right                 |

## Thumb Instruction Encoding (16-bit)

### Format 1: Move Shifted Register
```
[15:13] 000
[12:11] Shift type (00=LSL, 01=LSR, 10=ASR)
[10:6]  Offset5 (shift amount, 0-31)
[5:3]   Rs (source register)
[2:0]   Rd (dest register, r0-r7)
```

### Format 2: Add/Subtract
```
[15:13] 000
[12:11] 11
[10:9]  Operation (00=ADD reg, 01=SUB reg, 10=ADD imm3, 11=SUB imm3)
[8:6]   Rn/Offset3
[5:3]   Rs
[2:0]   Rd
```

### Format 3: Move/Compare/Add/Subtract Immediate
```
[15:11] 001xx (xx=opcode: 00=MOV, 01=CMP, 10=ADD, 11=SUB)
[10:8]  Rd (r0-r7)
[7:0]   Offset8 (immediate value)
```

### Format 4: ALU Operations
```
[15:10] 010000
[9:6]   Opcode (0x0-0xF, see table)
[5:3]   Rs
[2:0]   Rd
```

### Format 5: Hi Register Operations / BX
```
[15:10] 010001
[9]     High operand 1 (Rd extends to r8-r15)
[8:6]   Opcode (00=ADD, 01=CMP, 10=MOV, 11=BX)
[5:3]   Rs
[2]     High operand 2 (Rs extends to r8-r15)
```

### Format 6: PC-relative Load
```
[15:11] 01001
[10:8]  Rd
[7:0]   Word offset (x4)
```

### Format 7: Load/Store Register Offset
```
[15:12] 0101
[11]    L=1(6)  // 0=store, 1=load
[10:9]  Offset register Ro
[8]     Byte/Word (0=word, 1=byte for bit 11=0; 0=H, 1=SH/SB for bit 11=1)
[7:6]   Sub-opcode
[5:3]   Rb (base register)
[2:0]   Rd
```

### Format 8: Load/Store Immediate Offset
```
[15:13] 011 (word) / 100 (byte) / 1000 (halfword)
[12:11] L/B flags
[10:6]  Offset5
[5:3]   Rb
[2:0]   Rd
```

### Format 9: Load/Store SP-relative
```
[15:12] 1001
[11]    L (0=STR, 1=LDR)
[10:8]  Rd
[7:0]   Word offset (x4)
```

### Format 10: Load Address
```
[15:12] 1010
[11]    SP/PC (0=PC, 1=SP)
[10:8]  Rd
[7:0]   Word offset (x4)
```

### Format 11: Add Offset to SP
```
[15:12] 1011
[11]    0 (not push/pop)
[10]    S (0=add, 1=subtract)
[6:0]   Word offset (x4)
```

### Format 12: Push/Pop
```
Push: [15:8] 1011010x [7:0] register list (bit 8=LR)
Pop:  [15:8] 1011110x [7:0] register list (bit 8=PC)
```

### Format 13: Multiple Load/Store
```
[15:12] 1100
[11]    L (0=STMIA, 1=LDMIA)
[10:8]  Rb (base register, writeback)
[7:0]   Register list (r0-r7)
```

### Format 14: Conditional Branch
```
[15:12] 1101
[11]    0 (conditional)
[10:8]  Condition (same encoding as ARM)
[7:0]   Signed offset (x2, PC-relative)
```

### Format 15: SWI
```
[15:8]  11011111
[7:0]   Value8 (SWI number)
```

### Format 16: Unconditional Branch
```
[15:11] 11100
[10:0]  Signed offset (x2, PC-relative)
```

### Format 17: Long Branch with Link
```
First:  [15:11] 11110 [10:0] offset high bits
Second: [15:11] 11111 [10:0] offset low bits
LR = PC - 2 (address of second instruction)
Target = PC + (offset_high << 12) + (offset_low << 1)
```

## CPSR (Current Program Status Register)

| Bits  | Name      | Description                    |
|-------|-----------|--------------------------------|
| 31    | N         | Negative/less than             |
| 30    | Z         | Zero                           |
| 29    | C         | Carry/borrow/extend            |
| 28    | V         | Overflow                       |
| 27:8  | -         | Reserved (DO NOT modify)       |
| 7     | I         | IRQ disable (1=disabled)       |
| 6     | F         | FIQ disable (1=disabled)       |
| 5     | T         | Thumb state (1=Thumb)          |
| 4:0   | M[4:0]    | Mode bits (10000=user, 10011=SVC, 10001=FIQ, 10010=IRQ, etc.) |
