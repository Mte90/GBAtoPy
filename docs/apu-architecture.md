# APU Architecture

> Source of truth for the GBAtoPy audio processing unit implementation.
> Runtime source: `crates/gbatopy-cli/assets/gba_runtime/apu.py`

## Overview

The APU emulates the GBA's 6-channel audio system using pygame.mixer for output.
It supports 4 PSG (Programmable Sound Generator) channels and 2 Direct Sound FIFO channels.
Audio is generated sample-by-sample in a background thread and buffered through a thread-safe queue.

## Channel Architecture

### PSG Channels

#### Channel 1 & 2 — Square Wave (`SquareWaveChannel`)

Duty-cycle square wave generators with envelope and sweep.

- **Duty patterns:** 12.5%, 25%, 50%, 75% (selected by 2-bit duty cycle field)
- **Envelope:** Volume sweeps up or down at a configurable rate (0-15 steps)
- **Sweep:** Frequency sweep with configurable shift and direction (CH1 only)
- **Length counter:** Automatic shutoff after a configurable duration
- **Timer period:** `2048 - frequency` (11-bit frequency value)
- **Output:** 0-15 volume level, toggled by duty pattern bit

#### Channel 3 — Wave Playback (`WaveChannel`)

Plays back 4-bit samples from wave RAM.

- **Wave RAM:** Two 32-byte banks, bank-selected at runtime
- **Sample format:** 4-bit nibbles (64 nibbles per bank), optional 8-bit mode flag
- **Volume scaling:** Mute (0), 100% (1), 50% (2), 25% (3)
- **Timer period:** `2048 - frequency` (10-bit frequency value)
- **Output:** 0-15 amplitude, scaled by volume setting

#### Channel 4 — Noise (`NoiseChannel`)

Pseudo-random noise generator using a linear feedback shift register (LFSR).

- **LFSR:** 15-bit or 7-bit mode (width selected by `width_7bit` flag)
- **Timer period:** `(1 << clock_shift) * max(1, clock_divider)`
- **Envelope:** Same as square channels (0-15 steps, up or down)
- **Output:** 0-15 volume level, modulated by LFSR output bit

### Direct Sound Channels

#### FIFO A & B (`FIFO`)

Direct sound channels for streaming PCM8 audio via DMA.

- **Buffer:** 8-byte deque (matches hardware FIFO depth)
- **DMA trigger:** When FIFO empties after a read, fires `fifo_a_empty_fire()` or `fifo_b_empty_fire()` on the DMA controller to request a refill
- **Timer:** Configurable period, set by DMA channel timing
- **Output:** 0-255 byte value (128 = silence)
- **Volume:** Per-channel left/right volume (0-7), set via SOUNDCNT_H

## Register Map

| Address | Register | Description |
|---------|----------|-------------|
| 0x04000060 | SOUND1CNT_SWEEP | CH1 sweep (shift, direction, steps) |
| 0x04000062 | SOUND1CNT_DUTY | CH1 duty cycle + length |
| 0x04000064 | SOUND1CNT_FREQ | CH1 frequency + envelope + trigger |
| 0x04000068 | SOUND2CNT_DUTY | CH2 duty cycle + length |
| 0x0400006A | SOUND2CNT_ENV | CH2 envelope |
| 0x0400006C | SOUND2CNT_FREQ | CH2 frequency + trigger |
| 0x04000070 | SOUND3CNT_BANK | CH3 wave bank select + enable |
| 0x04000072 | SOUND3CNT_LEN | CH3 length |
| 0x04000074 | SOUND3CNT_FREQ | CH3 volume + frequency + trigger |
| 0x04000078 | SOUND4CNT_LEN | CH4 length |
| 0x0400007A | SOUND4CNT_ENV | CH4 envelope |
| 0x0400007C | SOUND4CNT_FREQ | CH4 clock shift + divider + trigger |
| 0x04000080 | SOUNDCNT_L | Master volume (L/R) + channel output enables |
| 0x04000082 | SOUNDCNT_H | FIFO A/B enable, pan, timer select, reset |
| 0x04000084 | SOUNDCNT_X | Master enable (bit 7) + channel status (read-only) |
| 0x04000090–9F | WAVE_RAM | Wave RAM (bank-selected) |
| 0x040000A0–A3 | FIFO_A | FIFO A data port |
| 0x040000A4–A7 | FIFO_B | FIFO B data port |

All sound registers are **write-only**. `read_register()` returns 0 for all addresses, matching GBA hardware behavior where sound registers are not readable.

## Master Enable Gate

Audio output is gated by `master_enable` (SOUNDCNT_X bit 7). The APU stays silent until the ROM writes `0x80` to `0x04000084`. `get_sample()` returns `(0, 0)` when `master_enable` is `False`.

This matches hardware: the GBA BIOS leaves audio disabled at boot, and the game must explicitly enable it.

## Timing Model

The APU uses a **sample-based** timing model, not cycle-accurate:

- **Sample rate:** 44100 Hz
- **Per-frame synthesis:** 735 samples (44100 / 60) when audio capture is enabled
- **Buffered playback:** Background thread generates 4096-sample buffers (93ms) and queues up to 3 buffers ahead
- **Channel stepping:** Each channel's `step()` method advances its internal state by one sample period per call

This differs from real hardware, where PSG channels are clocked at 4.194304 MHz and Direct Sound at 65536 Hz (timer-driven). The sample-based model produces correct frequencies and envelopes but may have minor timing drift on long sweeps.

## Mixer Architecture

`get_sample()` returns a `(left, right)` stereo pair:

1. Each enabled PSG channel calls `step()` to produce a sample
2. PSG samples are multiplied by `master_volume_left` / `master_volume_right` (0-7)
3. FIFO samples are multiplied by their per-channel `volume_left` / `volume_right` (0-7)
4. Left and right channels are summed independently
5. Result is normalized: `min(255, max(0, sum // 7))`

The normalization divisor of 7 matches the maximum master volume (7), ensuring the output fits in an 8-bit range.

## Audio Threading

```
┌──────────────┐     ┌────────────────┐     ┌─────────────────┐
│  update()    │────▶│ _audio_worker  │────▶│ pygame.mixer    │
│  (main loop) │     │ (thread)       │     │ Channel(1)      │
└──────────────┘     └────────────────┘     └─────────────────┘
                            │
                     generates 4096-sample
                     buffers, puts into
                     Queue(maxsize=3)
```

- `update()` is called once per frame from the main loop
- On first call with audio enabled, it starts a daemon thread running `_audio_worker`
- The worker thread loops: generate samples → create `pygame.mixer.Sound` → put into queue (blocks if full)
- The main thread plays queued sounds on `Channel(1)` when the channel is free
- `stop()` sets a stop event, joins the thread (1s timeout), clears the queue, and stops the mixer

## Codegen Integration

The codegen (`crates/gbatopy-cli/src/codegen/mod.rs`) integrates the APU as follows:

1. `apu.py` is listed as an optional runtime file (line 85)
2. If `flags.audio` is true (line 135):
   - Emits `apu_instance = APU()` and `memory.attach_apu(apu_instance)` (lines 136-137)
3. If audio is disabled:
   - Emits `apu_instance = None` (line 139)
4. `apu_instance` is passed to the main loop function (line 202)
5. The main loop calls `apu_instance.update()` once per frame (template line 716)
6. When audio capture is enabled, `apu_instance._generate_samples(735)` is called per frame (template line 544)

The memory system routes sound register writes to `apu_instance.write_register(addr, value)` via `attach_apu()`.

## SWI Integration

Sound BIOS SWIs are handled by the runtime's SWI dispatch tables. See [docs/reference/swi-reference.md](reference/swi-reference.md) for the full SWI register clobber reference. The sound SWIs are:

- SWI 0x19–0x1F: SoundDriverInit through SoundVariableSet
- SWI 0x28: SoundDriverVSyncOff

Most sound SWIs are no-ops in the transpiler because pygame.mixer handles audio output directly. The exception is MidiKey2Freq (SWI 0x1E), which performs real frequency computation.

All three dispatch tables (cpu.py fast-path, arm7tdmi.py fallback, game_loop.py template) must handle the same set of SWI numbers. Verify with:

```bash
python3 scripts/check_swi_dispatch.py
```

## Known Limitations

- **No cycle-accurate timing.** PSG channels use sample-based stepping, not the 4.194304 MHz hardware clock. Long envelopes and sweeps may drift slightly.
- **Sound registers are write-only.** `read_register()` always returns 0. Channel status bits in SOUNDCNT_X are not tracked.
- **SOUNDCNT_H pan/ratio bits partially ignored.** FIFO pan and PSG/FIFO ratio fields are not fully implemented — FIFO channels get max volume on both L/R.
- **Duplicate `_audio_worker` method.** `apu.py` contains two identical `_audio_worker` definitions (lines 354-368 and 545-559). The second definition shadows the first. This is dead code that should be removed.
- **Numba JIT is optional.** The `njit` decorator falls back to pure Python if numba is not installed. No performance impact on correctness.
- **No BIOS wave RAM initialization.** The BIOS normally loads a default wave pattern; the transpiler starts with zeroed wave RAM.
