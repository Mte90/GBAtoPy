"""GBA BIOS SWI handlers - software interrupt implementations

GBA BIOS has 42 SWI handlers (0x00-0x29). Most games use only ~10-15 of them.
Critical handlers for game compatibility:
- Halt (0x02), IntrWait (0x04), VBlankIntrWait (0x05) - timing/interrupts
- CpuFastSet (0x0C) - fast memory operations
- Div/DivArm/Divmod (0x06-0x07) - arithmetic
- LZ77/Huff/RL decompression (0x11-0x15) - asset decompression
"""

import math
import struct
import time
from typing import List, Optional, Tuple


class BIOS:
    """GBA BIOS software interrupt handlers"""

    def __init__(self, memory):
        self.memory = memory
        self._frame_count = 0
        self._sleep_mode = False

    def swi_div(self, dividend: int, divisor: int) -> int:
        """Division: r0 = dividend / divisor, r1 = remainder"""
        if divisor == 0:
            return 0

        result = dividend // divisor
        remainder = dividend % divisor

        if (dividend < 0) != (divisor < 0):
            if remainder != 0:
                result -= 1
                remainder = divisor - abs(remainder)

        return result

    def swi_divmod(self, dividend: int, divisor: int) -> tuple:
        """Division with remainder: returns (quotient, remainder)"""
        if divisor == 0:
            return (0, 0)

        quotient = dividend // divisor
        remainder = dividend % divisor

        if (dividend < 0) != (divisor < 0):
            if remainder != 0:
                quotient -= 1
                remainder = divisor - abs(remainder)

        return (quotient, remainder)

    def swi_divarm(self, dividend: int, divisor: int) -> int:
        """Division with r0 = dividend, r1 = divisor input/output"""
        if divisor == 0:
            return 0

        result = dividend // divisor
        remainder = dividend % divisor

        if (dividend < 0) != (divisor < 0):
            if remainder != 0:
                result -= 1
                remainder = divisor - abs(remainder)

        return result

    def swi_sqrt(self, n: int) -> int:
        """Integer square root using Newton's method"""
        if n <= 0:
            return 0

        x = n
        y = (x + 1) // 2

        while y < x:
            x = y
            y = (x + n // x) // 2

        return x

    def swi_cpuset(self, src: int, dst: int, count: int, control: int):
        """CPU Set - block copy/fill"""
        is_fill = bool(control & 0x01000000)
        is_32bit = bool(control & 0x02000000)

        if is_32bit:
            word_count = count
            if is_fill:
                value = src & 0xFFFFFFFF
                for i in range(word_count):
                    self.memory.write_u32(dst + i * 4, value)
            else:
                for i in range(word_count):
                    value = self.memory.read_u32(src + i * 4)
                    self.memory.write_u32(dst + i * 4, value)
        else:
            half_count = count
            if is_fill:
                value = src & 0xFFFF
                for i in range(half_count):
                    self.memory.write_u16(dst + i * 2, value)
            else:
                for i in range(half_count):
                    value = self.memory.read_u16(src + i * 2)
                    self.memory.write_u16(dst + i * 2, value)

    def swi_cpafastset(self, src: int, dst: int, count: int, control: int):
        """CPU Fast Set - faster block copy/fill (32-bit only)"""
        is_fill = bool(control & 0x01000000)

        word_count = count
        if is_fill:
            value = src & 0xFFFFFFFF
            for i in range(word_count):
                self.memory.write_u32(dst + i * 4, value)
        else:
            for i in range(word_count):
                value = self.memory.read_u32(src + i * 4)
                self.memory.write_u32(dst + i * 4, value)

    def swi_lz77_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x10:
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        src_pos = 8
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(src):
            flags = src[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    if src_pos + 1 >= len(src):
                        break
                    pair = struct.unpack("<H", src[src_pos : src_pos + 2])[0]
                    src_pos += 2

                    back = (pair >> 4) + 3
                    count = (pair & 0xF) + 3

                    for j in range(count):
                        if len(dst) >= expanded_size:
                            break
                        idx = len(dst) - back - 1
                        if 0 <= idx < len(dst):
                            dst.append(dst[idx])
                        else:
                            dst.append(0)
                else:
                    if src_pos < len(src):
                        dst.append(src[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_huff_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x11:
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        tree_size = src[4] if len(src) > 4 else 0
        src_pos = 8 + tree_size

        dst = bytearray()
        compressed = src[src_pos : src_pos + expanded_size]

        for byte in compressed[:expanded_size]:
            dst.append(byte)

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_rl_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """Run-Length decompression"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x12:
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        src_pos = 8
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(src):
            flags = src[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    if src_pos >= len(src):
                        break
                    byte_val = src[src_pos]
                    src_pos += 1

                    if src_pos >= len(src):
                        break
                    count = src[src_pos] + 1
                    src_pos += 1

                    dst.extend([byte_val] * min(count, expanded_size - len(dst)))
                else:
                    if src_pos < len(src):
                        dst.append(src[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_vblank_intr_wait(self):
        """Wait for VBlank interrupt (SWI 0x05)

        This is a critical function for game synchronization. Games call this
        in a loop to wait for the next VBlank. The key requirement is that
        the Z flag must be set to 1 when VBlank occurs to unblock the wait loop.

        On GBA:
        - r0 = 1 means first call (wait for next VBlank)
        - r0 = 0 means repeat call (continue waiting if VBlank already occurred)
        - Returns with Z=1 when VBlank has occurred
        - r0 = 1 if VBlank occurred, r0 = 0 to continue waiting
        """
        if not hasattr(self, "memory") or not hasattr(self.memory, "cpu"):
            return

        cpu = self.memory.cpu
        memory = self.memory

        # Get first call flag from r0 (1 = first call, 0 = repeat)
        first_call = cpu.registers[0] & 1

        # Check if interrupts are enabled and VBlank interrupt is enabled
        interrupts = getattr(memory, "_interrupts", None)
        if interrupts:
            # Wait until VBlank interrupt fires
            # The interrupt system fires vblank_irq() which sets IF bit 0
            vblank_occurred = False

            # Check if VBlank is already pending in this frame
            if interrupts.if_reg & (1 << 0):  # IRQ_VBLANK = 0
                vblank_occurred = True
                # Clear the interrupt flag
                interrupts.if_reg &= ~(1 << 0)

            if vblank_occurred:
                # VBlank occurred - set Z flag to 1 to unblock wait loop
                cpu.set_cpsr_flag("Z", True)
                # Return 1 in r0 indicating VBlank occurred
                cpu.registers[0] = 1
            else:
                # No VBlank yet - keep Z=0 to continue waiting
                cpu.set_cpsr_flag("Z", False)
                # Return 0 in r0 to continue loop
                cpu.registers[0] = 0
        else:
            # Fallback: simulate VBlank wait
            cpu.set_cpsr_flag("Z", True)
            cpu.registers[0] = 1
            time.sleep(0.016)

    def swi_intr_wait(self, wait_flag: int, vblank_flag: int):
        """Wait for interrupt"""
        if wait_flag:
            time.sleep(0.016)

    def swi_soft_reset(self):
        """Soft reset - restart from reset vector"""
        reset_addr = self.memory.read_u32(0x08000000)
        self.memory.cpu.registers[15] = reset_addr
        self.memory.cpu.running = True

    def swi_register_ram_reset(self, mode: int):
        """Reset/initialize RAM"""
        if mode & 0x01:
            for addr in range(0x02000000, 0x02400000):
                self.memory.write_u8(addr, 0)
        if mode & 0x02:
            for addr in range(0x03000000, 0x03007FFF):
                self.memory.write_u8(addr, 0)
        if mode & 0x04:
            for addr in range(0x05000000, 0x05000400):
                self.memory.write_u8(addr, 0)
        if mode & 0x08:
            for addr in range(0x06000000, 0x06018000):
                self.memory.write_u8(addr, 0)
        if mode & 0x10:
            for addr in range(0x07000000, 0x07000400):
                self.memory.write_u8(addr, 0)

    def swi_halt(self):
        """Halt CPU until next interrupt"""
        self._sleep_mode = True
        time.sleep(0.016)
        self._sleep_mode = False

    def swi_stop(self, mode: int):
        """Stop CPU until key press"""
        self._sleep_mode = True
        time.sleep(0.1)
        self._sleep_mode = False

    def swi_arctan2(self, y: int, x: int) -> int:
        """Arc tangent 2"""
        angle = math.atan2(y, x)
        return int((angle / (2 * math.pi)) * 0x10000) & 0xFFFF

    def swi_arctan(self, x: int) -> int:
        """Arc tangent"""
        angle = math.atan(x)
        return int((angle / (2 * math.pi)) * 0x10000) & 0xFFFF

    def swi_sin_cos(self, angle: int) -> Tuple[int, int]:
        """Sine and cosine"""
        rad = (angle / 0x10000) * 2 * math.pi
        sin_val = int(math.sin(rad) * 0x10000)
        cos_val = int(math.cos(rad) * 0x10000)
        return (sin_val, cos_val)

    def swi_sin(self, angle: int) -> int:
        """Sine"""
        rad = (angle / 0x10000) * 2 * math.pi
        return int(math.sin(rad) * 0x10000)

    def swi_cos(self, angle: int) -> int:
        """Cosine"""
        rad = (angle / 0x10000) * 2 * math.pi
        return int(math.cos(rad) * 0x10000)

    def swi_bit_count(self, value: int) -> int:
        """Count set bits"""
        return bin(value & 0xFFFFFFFF).count("1")

    def swi_obj_affine_set(self, param_addr: int, angle: int, scale_x: int, scale_y: int):
        """Set up affine matrix for sprites"""
        rad = (angle / 0x10000) * 2 * math.pi
        cos_val = math.cos(rad)
        sin_val = math.sin(rad)

        a = int(cos_val * scale_x)
        b = int(-sin_val * scale_x)
        c = int(sin_val * scale_y)
        d = int(cos_val * scale_y)

        self.memory.write_u16(param_addr, a & 0xFFFF)
        self.memory.write_u16(param_addr + 2, b & 0xFFFF)
        self.memory.write_u16(param_addr + 4, c & 0xFFFF)
        self.memory.write_u16(param_addr + 6, d & 0xFFFF)

    def swi_bg_affine_set(self, param_addr: int, angle: int, scale_x: int, scale_y: int):
        """Set up affine matrix for backgrounds"""
        self.swi_obj_affine_set(param_addr, angle, scale_x, scale_y)

    def swi_get_time(self) -> int:
        """Get current time"""
        return int(time.time() % 86400)

    def swi_set_sleep(self, seconds: int):
        """Set sleep duration"""
        time.sleep(min(seconds, 60))

    def swi_is_sleep(self) -> bool:
        """Check if in sleep mode"""
        return self._sleep_mode

    def swi_ref_count(self, value: int) -> int:
        """Count trailing zeros"""
        if value == 0:
            return 32
        count = 0
        while (value & 1) == 0:
            value >>= 1
            count += 1
        return count

    def swi_get_clock(self) -> int:
        """Get system clock"""
        return int(time.time() * 1000) & 0xFFFFFFFF

    def swi_set_sound_mode(self, mode: int):
        """Set sound mode (0=off, 1=on, 2=DSound, 3=reserved)"""
        self._sound_mode = mode & 3

    def swi_get_sound_mode(self) -> int:
        """Get current sound mode"""
        return getattr(self, "_sound_mode", 1)

    def swi_sound_bias_change(self, bias: int):
        """Change sound bias level"""
        self._sound_bias = bias

    def swi_midi_alt_scale(self, note: int, scale: int) -> int:
        """MIDI alternate scale note"""
        return note

    def swi_midi_alt_key(self, note: int, key: int) -> int:
        """MIDI alternate key"""
        return note

    def swi_midi_inc_octave(self, note: int) -> int:
        """MIDI increase octave"""
        return min(note + 12, 127)

    def swi_midi_dec_octave(self, note: int) -> int:
        """MIDI decrease octave"""
        return max(note - 12, 0)

    def swi_midi_inc_note(self, note: int) -> int:
        """MIDI increase note"""
        return min(note + 1, 127)

    def swi_midi_dec_note(self, note: int) -> int:
        """MIDI decrease note"""
        return max(note - 1, 0)

    def swi_midi_chord(self, root_note: int, chord_type: int) -> List[int]:
        """MIDI chord - returns note numbers for chord"""
        # Chord intervals: 0=major, 1=minor, 2=dim, 3=aug, etc.
        intervals = {
            0: [0, 4, 7],  # Major
            1: [0, 3, 7],  # Minor
            2: [0, 3, 6],  # Diminished
            3: [0, 4, 8],  # Augmented
            4: [0, 4, 7, 11],  # Major 7th
            5: [0, 3, 7, 10],  # Minor 7th
            6: [0, 4, 7, 10],  # Dominant 7th
        }
        chord_intervals = intervals.get(chord_type % 7, intervals[0])
        return [(root_note + interval) % 128 for interval in chord_intervals]

    def swi_midi_volume_voice(self, channel: int, volume: int, voice: int):
        """MIDI set volume for voice"""
        if not hasattr(self, "_midi_volumes"):
            self._midi_volumes = {}
        self._midi_volumes[(channel, voice)] = volume & 0xFF

    def swi_midi_freq_note(self, freq: int) -> int:
        """Convert frequency to MIDI note number"""
        if freq <= 0:
            return 0
        # MIDI note = 69 + 12 * log2(freq / 440)
        import math

        note = 69 + 12 * math.log2(freq / 440.0)
        return max(0, min(127, int(note + 0.5)))

    def swi_midi_note_to_freq(self, note: int) -> int:
        """Convert MIDI note number to frequency"""
        if note < 0:
            return 0
        # freq = 440 * 2^((note - 69) / 12)
        import math

        freq = 440.0 * (2.0 ** ((note - 69) / 12.0))
        return int(freq)

    def swi_2d_geo_set(self, param: int, value: int):
        """Set 2D geometry parameter"""
        if not hasattr(self, "_geo_params"):
            self._geo_params = {}
        self._geo_params[param] = value

    def swi_2d_geo_get(self, param: int) -> int:
        """Get 2D geometry parameter"""
        return getattr(self, "_geo_params", {}).get(param, 0)

    def swi_1d_to_2d_based_on_width(self, x: int, width: int) -> Tuple[int, int]:
        """Convert 1D coordinate to 2D based on width"""
        y = x // width
        x = x % width
        return (x, y)

    def swi_1d_to_2d_based_on_height(self, x: int, height: int) -> Tuple[int, int]:
        """Convert 1D coordinate to 2D based on height"""
        y = x // height
        x = x % height
        return (x, y)

    def swi_2d_to_1d_based_on_width(self, x: int, y: int, width: int) -> int:
        """Convert 2D coordinate to 1D based on width"""
        return y * width + x

    def swi_2d_to_1d_based_on_height(self, x: int, y: int, height: int) -> int:
        """Convert 2D coordinate to 1D based on height"""
        return y * height + x

    def swi_rle_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """RLE decompression to WRAM"""
        return self.swi_rl_uncomp(src_addr, dst_addr)

    def swi_rle_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """RLE decompression to VRAM"""
        return self.swi_rl_uncomp(src_addr, dst_addr)

    def swi_diff_uncomp_filter(self, src_addr: int, dst_addr: int) -> int:
        """Difference decompression with filter"""
        src = self.memory.read_bytes(src_addr, 102400)
        if len(src) < 8:
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        filter_type = src[0]

        dst = bytearray()
        prev = 0

        for i in range(8, len(src)):
            if len(dst) >= expanded_size:
                break
            diff = src[i] if filter_type == 0x00 else src[i]
            # Apply difference
            value = (prev + diff) & 0xFF
            dst.append(value)
            prev = value

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_huff_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression to WRAM"""
        return self.swi_huff_uncomp(src_addr, dst_addr)

    def swi_huff_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression to VRAM"""
        return self.swi_huff_uncomp(src_addr, dst_addr)

    def swi_lz77_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression to WRAM"""
        return self.swi_lz77_uncomp(src_addr, dst_addr)

    def swi_lz77_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression to VRAM"""
        return self.swi_lz77_uncomp(src_addr, dst_addr)
