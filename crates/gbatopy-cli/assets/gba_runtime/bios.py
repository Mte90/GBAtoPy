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
        """BitUnPack BIOS function (SWI 0x10).
        
        Decompresses bit-packed data from source to destination.
        
        Header structure at params_addr (8 bytes total):
            +0    u16   sourceLen    - source length in bytes
            +2    u8    sourceWidth  - source bit depth (1, 2, 4, or 8)
            +3    u8    destWidth    - destination bit depth (1, 2, 4, 8, 16, or 32)
            +4    u32   bias         - bit 31: add base to zero-values too
                                      bits 0-30: base offset added to non-zero values
        
        Args:
            src_addr: Source address (points to packed data, not header)
            dst_addr: Destination address
            params_addr: Address of 8-byte header
        
        Returns:
            Number of bytes written to destination, or 0 on error
        """
        # Read the 8-byte header
        source_len = self.memory.read_u16(params_addr)
        source_width = self.memory.read_u8(params_addr + 2)
        dest_width = self.memory.read_u8(params_addr + 3)
        bias = self.memory.read_u32(params_addr + 4)
        
        # Validate source width (must be 1, 2, 4, or 8)
        if source_width not in (1, 2, 4, 8):
            raise ValueError(f"Invalid BitUnPack sourceWidth: {source_width} (must be 1, 2, 4, or 8)")
        
        # Validate destination width (must be 1, 2, 4, 8, 16, or 32)
        if dest_width not in (1, 2, 4, 8, 16, 32):
            raise ValueError(f"Invalid BitUnPack destWidth: {dest_width} (must be 1, 2, 4, 8, 16, or 32)")
        
        # Read source data
        src_data = self.memory.read_bytes(src_addr, source_len)
        if len(src_data) < source_len:
            raise ValueError(f"BitUnPack source data too short: got {len(src_data)}, need {source_len}")
        
        # Extract bias base value and flag
        bias_base = bias & 0x7FFFFFFF
        bias_add_zero = bool(bias & 0x80000000)
        
        # Source bit buffer (for reading source bits)
        src_buffer = 0
        src_bits_remaining = 0
        src_pos = 0

        # Destination bit buffer (for packing output bits)
        dst_buffer = 0
        dst_bits_accumulated = 0
        dst_pos = 0

        while source_len > 0 or src_bits_remaining >= source_width:
            if src_bits_remaining < source_width:
                if source_len == 0:
                    break
                src_buffer = src_data[src_pos]
                src_pos += 1
                source_len -= 1
                src_bits_remaining = 8

            value = src_buffer & ((1 << source_width) - 1)
            src_buffer >>= source_width
            src_bits_remaining -= source_width

            if value != 0 or bias_add_zero:
                value += bias_base

            dst_buffer = (dst_buffer << dest_width) | value
            dst_bits_accumulated += dest_width

            while dst_bits_accumulated >= 8:
                dst_bits_accumulated -= 8
                byte = (dst_buffer >> dst_bits_accumulated) & 0xFF
                self.memory.write_u8(dst_addr + dst_pos, byte)
                dst_pos += 1
            dst_buffer &= (1 << dst_bits_accumulated) - 1 if dst_bits_accumulated > 0 else 0

        if dst_bits_accumulated > 0:
            byte = (dst_buffer << (8 - dst_bits_accumulated)) & 0xFF
            self.memory.write_u8(dst_addr + dst_pos, byte)
            dst_pos += 1

        return dst_pos

    def swi_diff_unfilter(self, src_addr: int, dst_addr: int, is_16bit: bool = False) -> int:
        """Diff8bitUnFilter / Diff16bitUnFilter BIOS function (SWI 0x16/0x17/0x18).
        
        Reconstructs data from difference-encoded input.
        
        Header structure at src_addr (4 bytes):
            +0    u32   header    - bits 31-8: remaining byte count, bits 7-0: type signature
        
        Args:
            src_addr: Source address (points to header + encoded data)
            dst_addr: Destination address
            is_16bit: If True, process as 16-bit input (Diff16bitUnFilter)
                     If False, process as 8-bit input (Diff8bitUnFilter)
        
        Returns:
            Number of bytes written to destination
        """
        # Read header
        header = self.memory.read_u32(src_addr)
        remaining = header >> 8
        src_pos = src_addr + 4
        dst_pos = dst_addr
        bytes_written = 0
        
        old_value = 0
        
        while remaining > 0:
            # Read new value (8-bit or 16-bit)
            if is_16bit:
                new_value = self.memory.read_u16(src_pos)
                src_pos += 2
            else:
                new_value = self.memory.read_u8(src_pos)
                src_pos += 1
            
            # Add previous value (reconstruct difference encoding)
            new_value += old_value
            
            # Write to destination based on width
            if is_16bit:
                self.memory.write_u16(dst_pos, new_value)
                dst_pos += 2
                remaining -= 2
            else:
                self.memory.write_u8(dst_pos, new_value)
                dst_pos += 1
                remaining -= 1
            
            old_value = new_value
            bytes_written += (2 if is_16bit else 1)
        
        return bytes_written