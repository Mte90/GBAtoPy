# GBA BIOS SWI Reference

Reference for SWI (software interrupt) handlers in the GBAtoPy transpiler.
Each entry documents input registers, output register clobbers, and implementation
status. This doc exists to prevent multi-session debugging of register clobber
bugs (the CpuSet r3=0x170 clobber took 3 sessions to root-cause).

## Source of Truth

| Source | File | Authority |
|--------|------|-----------|
| Official BIOS disassembly | mGBA HLE BIOS | `mgba/src/gba/hle-bios.s` |
| mGBA C HLE wrappers | mGBA BIOS | `mgba/src/gba/bios.c` |
| GBATEK spec | gbatek (nocash) | Register behavior specification |
| Our runtime handlers | `crates/gbatopy-cli/assets/gba_runtime/bios.py` | Python implementation |
| Codegen dispatch | `crates/gbatopy-cli/assets/templates/game_loop.py` | Generated Python SWI dispatch |
| Fast-path CPU | `crates/gbatopy-cli/assets/gba_runtime/cpu.py` | Interpreter SWI handler |
| Fallback interpreter | `crates/gbatopy-cli/assets/gba_runtime/arm7tdmi.py` | Fallback SWI handler |
| Rust codegen | `crates/gbatopy-cli/src/codegen/instruction_codegen/coprocessor.rs` | SWI codegen entry point |

## SWI Table (0x00–0x2A)

| SWI | Name | Input Registers | Output Clobbers | Implemented |
|-----|------|-----------------|-----------------|-------------|
| 0x00 | SoftReset | r0=reset flag, r1=IE/IF clear flag | r0–r3, r12, SP, LR, PC | Partial (inline) |
| 0x01 | RegisterRamReset | r0=reset flags | r0 | Yes (`bios.py`) |
| 0x02 | Halt | none | none (writes HALTCNT) | Yes (inline) |
| 0x03 | Stop | none | none (writes STOPCNT) | Stub (no-op) |
| 0x04 | IntrWait | r0=force flag, r1=IRQ mask | r0, r1 | Yes (inline) |
| 0x05 | VBlankIntrWait | none | r0, r1 | Yes (inline) |
| 0x06 | Div | r0=dividend, r1=divisor | r0=quotient, r1=remainder, r3=quotient | Yes (`bios.py`) |
| 0x07 | DivArm | r0=dividend, r1=divisor | r0=quotient, r1=remainder, r3=quotient | Yes (`bios.py`) |
| 0x08 | Sqrt | r0=value | r0=result | Yes (`bios.py`) |
| 0x09 | ArcTan | r0=tan (fixed-point) | r0=angle (0x0000–0xFFFF) | Yes (`bios.py`) |
| 0x0A | ArcTan2 | r0=y, r1=x (fixed-point) | r0=angle, r1=clobbered, r3=0x170 | Yes (`bios.py`) |
| 0x0B | CpuSet | r0=src, r1=dst, r2=count\|flags | r3=0x170, r0/r1 path-dependent | Yes (`bios.py`) |
| 0x0C | CpuFastSet | r0=src, r1=dst, r2=count\|flags | r2, r3 path-dependent | Yes (`bios.py`) |
| 0x0D | GetBiosChecksum | none | r0=checksum | Stub (returns 0) |
| 0x0E | BgAffineSet | r0=src, r1=dst, r2=num, r3=inc | r0–r3 | Yes (`bios.py`) |
| 0x0F | ObjAffineSet | r0=src, r1=dst, r2=num, r3=type | r0–r3 | Yes (`bios.py`) |
| 0x10 | BitUnPack | r0=src, r1=dst, r2=params | r0–r3 | Yes (`bios.py`) |
| 0x11 | Lz77UnCompWram | r0=src, r1=dst | r0–r3 | Yes (`bios.py`) |
| 0x12 | Lz77UnCompVram | r0=src, r1=dst | r0–r3 | Yes (`bios.py`) |
| 0x13 | HuffmanUnComp | r0=src, r1=dst | r0–r3 | Yes (`bios.py`) |
| 0x14 | RlUnCompWram | r0=src, r1=dst | r0–r3 | Yes (`bios.py`) |
| 0x15 | RlUnCompVram | r0=src, r1=dst | r0–r3 | Yes (`bios.py`) |
| 0x16 | Diff8BitUnFilterWram | r0=src, r1=dst | r0–r3 | Yes (`bios.py`) |
| 0x17 | Diff8BitUnFilterVram | r0=src, r1=dst | r0–r3 | Yes (`bios.py`) |
| 0x18 | Diff16BitUnFilter | r0=src, r1=dst | r0–r3 | Yes (`bios.py`) |
| 0x19 | SoundBias | r0=bias | none | Stub (no-op) |
| 0x1A | SoundDriverInit | r0=work area | r0–r3 | Stub (`bios.py`) |
| 0x1B | SoundDriverMode | r0=mode | r0–r3 | Stub (`bios.py`) |
| 0x1C | SoundDriverMain | none | r0–r3 | Stub (`bios.py`) |
| 0x1D | SoundDriverVsync | none | r0–r3 | Stub (`bios.py`) |
| 0x1E | SoundChannelClear | none | r0–r3 | Stub (`bios.py`) |
| 0x1F | MidiKey2Freq | r0=voice, r1=key | r0=freq, r1–r3 | Yes (`bios.py`) |
| 0x20 | MusicPlayerOpen | r0=player | r0–r3 | Stub (returns 0) |
| 0x21 | MusicPlayerStart | r0=player | r0–r3 | Stub (no-op) |
| 0x22 | MusicPlayerStop | r0=player | r0–r3 | Stub (no-op) |
| 0x23 | MusicPlayerContinue | r0=player | r0–r3 | Stub (no-op) |
| 0x24 | MusicPlayerFadeOut | r0=frame, r1=vol | r0–r3 | Stub (no-op) |
| 0x25 | MultiBoot | r0=src, r1=dst, r2=len | r0–r3 | Stub (returns 0) |
| 0x26 | HardReset | none | all | Stub (no-op) |
| 0x27 | CustomHalt | r0=flag | none | Stub (no-op) |
| 0x28 | SoundDriverVsyncOff | none | r0–r3 | Yes (`bios.py`) |
| 0x29 | SoundDriverVsyncOn | none | r0–r3 | Stub (no-op) |
| 0x2A | SoundDriverGetJumpList | r0=dst | r0, r1, r3–r10 | Stub (no-op) |

## CpuSet (SWI 0x0B) — Detailed Register Behavior

This SWI has four code paths depending on bit 24 (fill) and bit 26 (32-bit width)
of r2. The register clobber behavior differs per path.

**r2 encoding:** bits 0–20 = count, bit 24 = fill mode, bit 26 = 32-bit width.

### Word Copy (bit 26 set, bit 24 clear)

| Register | Before | After |
|----------|--------|-------|
| r0 | src | src + count × 4 |
| r1 | dst | dst + count × 4 |
| r3 | — | 0x170 |
| r12 | — | original r0 (set but not used further) |

### Word Fill (bit 26 set, bit 24 set)

| Register | Before | After |
|----------|--------|-------|
| r0 | src | src + 4 (one word loaded) |
| r1 | dst | dst + count × 4 |
| r3 | — | 0x170 (fill value overwritten) |
| r12 | — | original r0 |

### Halfword Copy (bit 26 clear, bit 24 clear)

| Register | Before | After |
|----------|--------|-------|
| r0 | src | unchanged |
| r1 | dst | unchanged |
| r3 | — | 0x170 |
| r12 | — | src + count × 2 (post-incremented) |

### Halfword Fill (bit 26 clear, bit 24 set)

| Register | Before | After |
|----------|--------|-------|
| r0 | src | unchanged |
| r1 | dst | unchanged |
| r3 | — | 0x170 |
| r12 | — | original r0 (aligned) |

### Implementation Notes

- **r3 = 0x170** is set unconditionally (`mgba/src/gba/hle-bios.s:249`).
- **r0/r1 post-increment** only in 32-bit paths. Halfword paths use r12/r5 as
  working registers and leave r0/r1 unchanged.
- **r12** is always clobbered to at least `original r0` (set at `hle-bios.s:202`).
- Our `bios.py:swi_cpuset` performs the copy but does NOT modify CPU registers
  (it receives plain integers). The r0/r1 post-increment and r3=0x170 are applied
  at the SWI dispatch call site in `game_loop.py`, `cpu.py`, and `arm7tdmi.py`.
- **Committed fix:** r3=0x170 clobber (commit `abf990b`), r0/r1 post-increment
  for word paths (commit `404516d`).

## CpuFastSet (SWI 0x0C) — Detailed Register Behavior

Always operates on 32-bit words. Copies 8 words (32 bytes) per iteration using
r3–r10. r4–r10 are saved/restored; r3 is NOT restored.

**r2 encoding:** bits 0–20 = count, bit 24 = fill mode.

### Copy Path (bit 24 clear)

| Register | Before | After |
|----------|--------|-------|
| r0 | src | src + count × 4 (post-incremented) |
| r1 | dst | dst + count × 4 (post-incremented) |
| r2 | count\|flags | dst + count × 4 (end pointer) |
| r3 | — | last word read |

### Fill Path (bit 24 set)

| Register | Before | After |
|----------|--------|-------|
| r0 | src | unchanged |
| r1 | dst | dst + count × 4 (post-incremented) |
| r2 | count\|flags | dst + count × 4 (end pointer) |
| r3 | — | fill value |

### Implementation Notes

- **r3 is NOT set to 0x170** in CpuFastSet (unlike CpuSet). It holds either the
  last word copied or the fill value.
- **r0 is only post-incremented in Copy mode.** Fill mode leaves r0 unchanged.
- **r2 is always clobbered** (used as the end pointer).
- **Committed fix:** r0/r1 post-increment (commit `404516d`).

## ArcTan2 (SWI 0x0A) — Register Behavior

| Register | Before | After |
|----------|--------|-------|
| r0 | y | angle (0x0000–0xFFFF) |
| r1 | x | clobbered |
| r3 | — | 0x170 |

Verified from `mgba/src/gba/bios.c:467`.

## Div / DivArm (SWI 0x06 / 0x07) — Register Behavior

| Register | Before | After |
|----------|--------|-------|
| r0 | dividend | quotient |
| r1 | divisor | remainder |
| r3 | — | quotient (same as r0) |

Division by zero returns 0 (no exception on ARM7TDMI).

## Dispatch Architecture

The SWI dispatch is single-sourced per invariant #7. There is one SWI dispatch
table shared by the fast-path and fallback interpreters.

### Codegen path (generated Python)

`coprocessor.rs:86-95` generates:
```python
registers[15] = <addr>
swi_handler(<swi_num>)
if _cpu_halted:
    return
```

`swi_handler()` is defined in `game_loop.py` and dispatches to either `bios.py`
methods or inline handlers for Halt, IntrWait, etc.

### Fast-path CPU

`cpu.py` has its own `swi_handler` that mirrors the codegen dispatch.

### Fallback interpreter

`arm7tdmi.py` has its own SWI handler for the fallback interpreter path.

### Critical: all three paths must agree

Any register clobber fix must be applied to all three dispatch sites:
1. `crates/gbatopy-cli/assets/templates/game_loop.py` (codegen)
2. `crates/gbatopy-cli/assets/gba_runtime/cpu.py` (fast-path)
3. `crates/gbatopy-cli/assets/gba_runtime/arm7tdmi.py` (fallback)

The CpuSet r3=0x170 bug (commit `abf990b`) was missed in one path for 3 sessions
because only one dispatch site was updated.

## Known Gaps

| Gap | Impact | Status |
|-----|--------|--------|
| CpuSet r12 clobber | r12 = original r0 after CpuSet | Not implemented (no known ROM affected) |
| CpuSet halfword path r0/r1 unchanged | ROMs reading r0/r1 after halfword CpuSet | Not implemented (no known ROM affected) |
| Sound SWIs (0x19–0x1E, 0x20–0x2A) | Audio subsystem non-functional | Stubs return 0 |
| MultiBoot (0x25) | Multi-boot download not supported | Stub returns 0 |
| HardReset (0x26) | Hard reset not supported | Stub no-op |

## Verification Cross-Reference

| SWI | mGBA source | Our source | Verification |
|-----|-------------|-----------|-------------|
| CpuSet | `hle-bios.s:199-250` | `bios.py:54-77` | r3=0x170 verified at `hle-bios.s:249` |
| CpuFastSet | `hle-bios.s:252-279` | `bios.py:79-91` | r3 NOT set to 0x170 (no `mov r3, #0x170` in asm) |
| ArcTan2 | `bios.c:467` | `bios.py:306-309` | r3=0x170 verified at `bios.c:467` |
| Div/DivArm | `hle-bios.s:302-303` | `bios.py:24-38` | r3=quotient verified from GBATEK |
| Halt | `hle-bios.s:165-169` | inline in dispatch | Writes HALTCNT at 0x04000301 |
