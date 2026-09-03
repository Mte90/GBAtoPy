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
            # GBA ARM7TDMI: division by zero returns 0 (no exception)
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
        """CPU Set - block copy (bit 24 = 16-bit flag, no fill mode)"""
        is_16bit = bool(control & 0x01000000)
        word_count = count & 0x001FFFFF

        if is_16bit:
            for i in range(word_count):
                value = self.memory.read_u16(src + i * 2)
                self.memory.write_u16(dst + i * 2, value)
        else:
            for i in range(word_count):
                value = self.memory.read_u32(src + i * 4)
                self.memory.write_u32(dst + i * 4, value)

    def swi_cpufastset(self, src: int, dst: int, count: int, control: int):
        """CPU Fast Set - faster block copy/fill (32-bit only)"""
        is_fill = bool(control & 0x01000000)

        word_count = count & 0x001FFFFF
        if is_fill:
            value = self.memory.read_u32(src)
            for i in range(word_count):
                self.memory.write_u32(dst + i * 4, value)
        else:
            for i in range(word_count):
                value = self.memory.read_u32(src + i * 4)
                self.memory.write_u32(dst + i * 4, value)

    def swi_lz77_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression (SWI 0x11/0x12). Header: [0x10][size:u24].

        Algorithm matches mGBA's _unLz77: 8-bit flag byte, MSB first.
        Compressed pairs are big-endian: bits 15-12 = count-3, bits 11-0 = displacement-1.
        """
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 4 or src[0] != 0x10:
            return 0

        remaining = src[1] | (src[2] << 8) | (src[3] << 16)
        src_pos = 4
        dst = bytearray()

        while remaining > 0 and src_pos < len(src):
            blockheader = src[src_pos]
            src_pos += 1

            for _ in range(8):
                if remaining <= 0:
                    break

                if blockheader & 0x80:
                    if src_pos + 1 >= len(src):
                        break
                    block = (src[src_pos] << 8) | src[src_pos + 1]
                    src_pos += 2

                    displacement = (block & 0x0FFF) + 1
                    count = (block >> 12) + 3
                    start = len(dst) - displacement

                    for _ in range(count):
                        if remaining <= 0:
                            break
                        dst.append(dst[start])
                        start += 1
                        remaining -= 1
                else:
                    if src_pos >= len(src):
                        break
                    dst.append(src[src_pos])
                    src_pos += 1
                    remaining -= 1

                blockheader = (blockheader << 1) & 0xFF

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)


    def swi_huff_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression (SWI 0x13). Header: [0x20][size:u24][bits:4].

        Algorithm matches mGBA's _unHuffman:
        - Source 4-byte aligned.
        - 4-byte header: magic(0x20) + 24-bit size (bits 31-8) + bits-per-symbol (bits 3-0).
        - Tree info byte at offset 4: treesize = (byte << 1) + 1.
        - Tree at offset 5, data at offset 5 + treesize.
        - Node format: [LTerm:7][RTerm:6][Offset:5-0].
        - 32-bit bitstream reads, MSB first.
        - 32-bit block accumulation, stored when full.
        """
        src_base = src_addr & 0xFFFFFFFC
        src = self.memory.read_bytes(src_base, 102400)

        # mGBA assumes the 0x20 signature is correct; only validate length.
        # Header byte is 0x20 | (bits & 0xF), so src[0] is e.g. 0x28 for 8-bit symbols.
        if len(src) < 5:
            return 0

        header = src[0] | (src[1] << 8) | (src[2] << 16) | (src[3] << 24)
        remaining = header >> 8
        bits = header & 0xF
        if bits == 0:
            bits = 8
        if 32 % bits or bits == 1:
            return 0

        tree_size = (src[4] << 1) + 1
        tree_nodes = src[5:5 + tree_size]
        if len(tree_nodes) == 0:
            return 0

        data_start = 5 + tree_size
        src_pos = data_start

        output = bytearray()
        block = 0
        bits_seen = 0
        n_pointer = 0
        node = tree_nodes[0]

        while remaining > 0 and src_pos + 3 < len(src):
            bitstream = src[src_pos] | (src[src_pos + 1] << 8) | (src[src_pos + 2] << 16) | (src[src_pos + 3] << 24)
            src_pos += 4

            for _ in range(32):
                if remaining <= 0:
                    break

                offset = node & 0x3F
                next_ptr = (n_pointer & ~1) + offset * 2 + 2
                is_right = bitstream & 0x80000000

                if is_right:
                    is_terminal = node & 0x40
                    terminal_idx = next_ptr + 1
                else:
                    is_terminal = node & 0x80
                    terminal_idx = next_ptr

                if is_terminal:
                    if terminal_idx >= len(tree_nodes):
                        return 0
                    read_bits = tree_nodes[terminal_idx]
                    block |= (read_bits & ((1 << bits) - 1)) << bits_seen
                    bits_seen += bits
                    n_pointer = 0
                    node = tree_nodes[0]
                    if bits_seen == 32:
                        bits_seen = 0
                        output.append(block & 0xFF)
                        output.append((block >> 8) & 0xFF)
                        output.append((block >> 16) & 0xFF)
                        output.append((block >> 24) & 0xFF)
                        remaining -= 4
                        block = 0
                else:
                    n_pointer = next_ptr + (1 if is_right else 0)
                    if n_pointer >= len(tree_nodes):
                        return 0
                    node = tree_nodes[n_pointer]

                bitstream = (bitstream << 1) & 0xFFFFFFFF

        for i, byte in enumerate(output):
            self.memory.write_u8(dst_addr + i, byte)

        return len(output)

    def swi_rl_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """Run-Length decompression (SWI 0x14/0x15). Header: [0x30][size:u24]."""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 4 or src[0] != 0x30:
            return 0

        expanded_size = src[1] | (src[2] << 8) | (src[3] << 16)
        src_pos = 4
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(src):
            flags = src[src_pos]
            src_pos += 1

            if flags & 0x80:
                count = (flags & 0x7F) + 3
                if src_pos >= len(src):
                    break
                byte_val = src[src_pos]
                src_pos += 1
                for _ in range(count):
                    if len(dst) >= expanded_size:
                        break
                    dst.append(byte_val)
            else:
                count = (flags & 0x7F) + 1
                for _ in range(count):
                    if src_pos >= len(src) or len(dst) >= expanded_size:
                        break
                    dst.append(src[src_pos])
                    src_pos += 1

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_vblank_intr_wait(self):
        cpu = self.memory.cpu
        cpu._halted = True

    def swi_intr_wait(self, wait_flag: int, vblank_flag: int):
        """Wait for interrupt. Check IF first (R0=1), then halt."""
        cpu = getattr(getattr(self, "memory", None), "cpu", None)
        memory = getattr(self, "memory", None)
        interrupts = getattr(memory, "_interrupts", None) if memory is not None else None
        if wait_flag & 0x01 and interrupts is not None and cpu is not None:
            flag_mask = vblank_flag & 0xFFFF
            pending = interrupts.if_reg & flag_mask
            if pending:
                interrupts.if_reg &= ~pending
                cpu.registers[0] = 1
                cpu.cpsr |= (1 << 30)
                return
        if cpu is not None:
            cpu._halted = True
            cpu._halt_reason = 'any'

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
        """Halt CPU until any enabled interrupt fires.

        Sets the halt flag only — the main loop owns all PPU timing.
        The _deliver_irq routine in the main loop checks _cpu_halted and
        wakes the CPU when an enabled interrupt becomes pending.
        """
        cpu = getattr(self, "cpu", None) or getattr(getattr(self, "memory", None), "cpu", None)
        if cpu is not None:
            cpu._halted = True
            cpu._halt_reason = 'any'
        else:
            self._sleep_mode = True

    def swi_vsync(self):
        """Trigger a VBlank interrupt."""
        interrupts = getattr(self.memory, "_interrupts", None)
        if interrupts is not None:
            interrupts.vblank_irq()

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

    def swi_bit_unpack(self, src_addr: int, dst_addr: int, params_addr: int) -> int:
        """Bit unpack (SWI 0x10/0x16)"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8:
            return 0

        source_length = struct.unpack("<I", src[0:4])[0]
        dest_length = struct.unpack("<I", src[4:8])[0]

        data_length_bits = self.memory.read_u16(params_addr)
        unk = self.memory.read_u16(params_addr + 2)
        data_length_bytes = self.memory.read_u32(params_addr + 4)
        rev_zero = self.memory.read_u32(params_addr + 8)
        zero_length = self.memory.read_u32(params_addr + 12)
        repeat_width = self.memory.read_u32(params_addr + 16)

        if data_length_bits == 4 and data_length_bytes == 1 and zero_length == 0 and repeat_width == 0 and unk == 0:
            output = bytearray()
            bit_buffer = 0
            bits_in_buffer = 0
            src_pos = 8

            while len(output) < dest_length and src_pos < 8 + source_length:
                if bits_in_buffer == 0:
                    bit_buffer = self.memory.read_u8(src_addr + src_pos)
                    src_pos += 1
                    bits_in_buffer = 8

                value = 0
                for _ in range(data_length_bits):
                    if bits_in_buffer == 0:
                        break
                    value = (value << 1) | ((bit_buffer >> (bits_in_buffer - 1)) & 1)
                    bits_in_buffer -= 1

                output.append(value)

            for i, byte in enumerate(output):
                if i >= dest_length:
                    break
                self.memory.write_u8(dst_addr + i, byte)

            return len(output)
        else:
            return 0

    def swi_rle_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """RLE decompression to WRAM"""
        return self.swi_rl_uncomp(src_addr, dst_addr)

    def swi_rle_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """RLE decompression to VRAM"""
        return self.swi_rl_uncomp(src_addr, dst_addr)

    def swi_diff_uncomp_filter(self, src_addr: int, dst_addr: int) -> int:
        """Difference decompression with filter (SWI 0x18). Header: [0x81][size:u24]."""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 4 or src[0] != 0x81:
            return 0

        expanded_size = src[1] | (src[2] << 8) | (src[3] << 16)
        src_pos = 4
        temp = bytearray()

        while len(temp) < expanded_size and src_pos < len(src):
            flags = src[src_pos]
            src_pos += 1

            count = (flags & 0x7F) + 1

            if flags & 0x80:
                if src_pos >= len(src):
                    break
                byte_val = src[src_pos]
                src_pos += 1
                for _ in range(count):
                    if len(temp) >= expanded_size:
                        break
                    temp.append(byte_val)
            else:
                for _ in range(count):
                    if src_pos >= len(src) or len(temp) >= expanded_size:
                        break
                    temp.append(src[src_pos])
                    src_pos += 1

        prev = 0
        for i, raw_byte in enumerate(temp):
            if i >= expanded_size:
                break
            value = (prev + raw_byte) & 0xFF
            self.memory.write_u8(dst_addr + i, value)
            prev = value

        return len(temp)

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
