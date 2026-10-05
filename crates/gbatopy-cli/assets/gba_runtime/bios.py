"""GBA BIOS SWI handlers — software interrupt implementations.

Only the 13 handlers wired into the SWI dispatch tables (arm7tdmi.py,
templates/game_loop.py, cpu.py) are implemented here. Other SWI numbers
are handled inline in the dispatch tables themselves.
"""

import math
import struct


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

    def swi_arctan2(self, y: int, x: int) -> int:
        """Arc tangent 2"""
        angle = math.atan2(y, x)
        return int((angle / (2 * math.pi)) * 0x10000) & 0xFFFF

    def swi_arctan(self, x: int) -> int:
        """Arc tangent"""
        angle = math.atan(x)
        return int((angle / (2 * math.pi)) * 0x10000) & 0xFFFF

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