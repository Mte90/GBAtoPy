"""Asset extraction from GBA ROM - tiles, palette, sprites, tilemaps"""

import struct
import os
from typing import List, Dict, Tuple, Optional
from enum import Enum, auto


class AssetType(Enum):
    """Types of GBA assets"""

    TILE_4BPP = auto()  # 4 bits per pixel, 16 colors, 8x8 = 32 bytes
    TILE_8BPP = auto()  # 8 bits per pixel, 256 colors, 8x8 = 64 bytes
    PALETTE = auto()  # 15-bit BGR color palette
    TILEMAP = auto()  # Tilemap with tile indices and attributes
    SPRITE = auto()  # Sprite data
    COMPRESSED = auto()  # Compressed data (needs decompression)
    UNKNOWN = auto()


class AssetExtractor:
    """Extract and decompress GBA assets from ROM"""

    def __init__(self, memory):
        self.memory = memory

    def decompress_lz77(self, data: bytes) -> bytes:
        """Decompress LZ77 compressed data (method 0x10)

        GBA LZ77 format:
        - Byte 0: 0x10 (method identifier)
        - Bytes 1-3: 24-bit decompressed size (little-endian)
        - Byte 4: flags
        """
        if len(data) < 4 or data[0] != 0x10:
            return b""

        # GBA uses 24-bit expanded_size (3 bytes little-endian), NOT 32-bit
        expanded_size = data[1] | (data[2] << 8) | (data[3] << 16)
        src_pos = 8
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(data):
            flags = data[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    # Compressed block
                    if src_pos + 1 >= len(data):
                        break
                    pair = struct.unpack("<H", data[src_pos : src_pos + 2])[0]
                    src_pos += 2

                    back = (pair >> 4) + 3
                    count = (pair & 0xF) + 3

                    for j in range(count):
                        if len(dst) >= expanded_size:
                            break
                        if src_pos - back - len(data) < 0:
                            dst.append(0)
                        else:
                            idx = len(dst) - back - 1
                            if idx >= 0 and idx < len(dst):
                                dst.append(dst[idx])
                            else:
                                dst.append(0)
                else:
                    # Raw byte
                    if src_pos < len(data):
                        dst.append(data[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        return bytes(dst[:expanded_size])

    def decompress_huffman(self, data: bytes) -> bytes:
        """Decompress Huffman compressed data (method 0x11)

        GBA Huffman format:
        - Byte 0: 0x11 (method identifier)
        - Bytes 1-4: 32-bit decompressed size (little-endian)
        - Tree size byte at position 4 (or 5 depending on variant)
        - Tree data follows header
        - Compressed bitstream after tree
        """
        if len(data) < 4 or data[0] != 0x11:
            return b""

        # GBA uses 32-bit size at bytes 1-4 (unlike LZ77's 24-bit)
        expanded_size = struct.unpack("<I", data[1:5])[0]

        # Tree size is at byte 4 (size of tree table / 2 - 1)
        tree_size = data[4] if len(data) > 4 else 0
        tree_end = 8 + tree_size

        if len(data) <= tree_end:
            return b""

        # Build Huffman tree from tree data
        # Each node is 2 bytes: bits 0-7 of left child, bits 0-7 of right child
        # Special values: 0xFF means "no data", other values are data or node index
        tree = data[8:tree_end]

        # Number of nodes in tree
        num_nodes = len(tree) // 2

        # Build a lookup table for decoding
        # GBA Huffman uses a binary tree where:
        # - If node < 256, it's a leaf with that byte value
        # - If node >= 256, it's an internal node: node - 256 gives the table index
        decode_table = {}

        def build_decode_table(node_idx: int, bit_string: int, bits: int):
            """Recursively build decode table"""
            if node_idx >= num_nodes:
                return

            # Read node pair (2 bytes per node)
            if node_idx * 2 + 1 >= len(tree):
                return

            left = tree[node_idx * 2]
            right = tree[node_idx * 2 + 1]

            # Left child (bit 0)
            if left < 256:
                # Leaf node - data
                decode_table[bit_string] = (left, bits)
            elif left < 0xFF:
                # Internal node - continue tree
                build_decode_table(left, (bit_string << 1) | 0, bits + 1)

            # Right child (bit 1)
            if right < 256:
                decode_table[(bit_string << 1) | 1] = (right, bits)
            elif right < 0xFF:
                build_decode_table(right, (bit_string << 1) | 1, bits + 1)

        # Start from root node (0)
        build_decode_table(0, 0, 0)

        # Now decompress using the bitstream
        compressed = data[tree_end:]
        dst = bytearray()
        bit_pos = 0

        # Track current node state
        current_bits = 0
        current_bit_count = 0

        while len(dst) < expanded_size and bit_pos < len(compressed) * 8:
            # Read one bit
            byte_idx = bit_pos // 8
            bit_idx = 7 - (bit_pos % 8)

            if byte_idx >= len(compressed):
                break

            bit = (compressed[byte_idx] >> bit_idx) & 1
            bit_pos += 1

            current_bits = (current_bits << 1) | bit
            current_bit_count += 1

            # Look up in decode table
            if current_bits in decode_table:
                symbol, expected_bits = decode_table[current_bits]
                if expected_bits == current_bit_count:
                    dst.append(symbol)
                    current_bits = 0
                    current_bit_count = 0

                    if len(dst) >= expanded_size:
                        break

        return bytes(dst[:expanded_size])

    def decompress_rle(self, data: bytes) -> bytes:
        """Decompress Run-Length compressed data (method 0x12)"""
        if len(data) < 5 or data[0] != 0x12:
            return b""

        expanded_size = struct.unpack("<I", data[1:5])[0]
        src_pos = 5  # GBA RLE header: 0x12 (1 byte) + 32-bit size (4 bytes) = 5 bytes
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(data):
            flags = data[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    # Run-length block
                    if src_pos >= len(data):
                        break
                    byte_val = data[src_pos]
                    src_pos += 1

                    if src_pos >= len(data):
                        break
                    count = data[src_pos] + 1
                    src_pos += 1

                    dst.extend([byte_val] * min(count, expanded_size - len(dst)))
                else:
                    # Raw byte
                    if src_pos < len(data):
                        dst.append(data[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        return bytes(dst[:expanded_size])

    def extract_palette(self, addr: int, num_colors: int = 256) -> List[Tuple[int, int, int]]:
        """Extract 15-bit color palette from memory"""
        palette = []
        for i in range(num_colors):
            color16 = self.memory.read_u16(addr + i * 2)
            r = (color16 & 0x1F) * 8
            g = ((color16 >> 5) & 0x1F) * 8
            b = ((color16 >> 10) & 0x1F) * 8
            palette.append((r, g, b))
        return palette

    def extract_tile_4bpp(self, tile_addr: int, tile_num: int = 0) -> bytes:
        """Extract 4bpp (16-color) 8x8 tile"""
        addr = tile_addr + tile_num * 32  # 32 bytes per 4bpp tile
        return self.memory.read_bytes(addr, 32)

    def extract_tile_8bpp(self, tile_addr: int, tile_num: int = 0) -> bytes:
        """Extract 8bpp (256-color) 8x8 tile"""
        addr = tile_addr + tile_num * 64  # 64 bytes per 8bpp tile
        return self.memory.read_bytes(addr, 64)

    def scan_rom_for_assets(self, rom_data: bytes) -> Dict:
        """Scan ROM for potential asset regions with size validation"""
        assets = {
            "palettes": [],
            "compressed": [],
            "tiles_4bpp": [],
            "tiles_8bpp": [],
            "tilemaps": [],
        }

        MAX_COMPRESSED_SIZE = 10 * 1024 * 1024
        MIN_ASSET_SIZE = 16

        for offset in range(0, len(rom_data) - 512, 2):
            if offset + 32 < len(rom_data):
                sample = rom_data[offset : offset + 32]
                valid_colors = 0
                for i in range(0, min(32, len(sample)), 2):
                    if i + 1 < len(sample):
                        color = sample[i] | (sample[i + 1] << 8)
                        if (color & 0x7C00) == 0:
                            valid_colors += 1
                if valid_colors >= 10:
                    assets["palettes"].append(offset)

        for offset in range(0, len(rom_data) - 8):
            method = rom_data[offset]
            if method in [0x10, 0x11, 0x12]:
                if method == 0x10:
                    size = (
                        rom_data[offset + 1]
                        | (rom_data[offset + 2] << 8)
                        | (rom_data[offset + 3] << 16)
                    )
                else:
                    size = struct.unpack("<I", rom_data[offset + 1 : offset + 5])[0]

                if MIN_ASSET_SIZE <= size <= MAX_COMPRESSED_SIZE:
                    compressed_type = (
                        "lz77" if method == 0x10 else ("huffman" if method == 0x11 else "rle")
                    )

                    compressed_size_estimate = self._estimate_compressed_size(offset, size, method)

                    if compressed_size_estimate > 0:
                        assets["compressed"].append(
                            {
                                "offset": offset,
                                "type": compressed_type,
                                "decompressed_size": size,
                                "compressed_estimate": compressed_size_estimate,
                            }
                        )

        return assets

    def _estimate_compressed_size(
        self, offset: int, decompressed_size: int, method: int, rom_data: bytes = None
    ) -> int:
        """Estimate compressed data size for validation"""
        if method == 0x10:
            header_size = 4
            return header_size + (decompressed_size // 8) + 1
        elif method == 0x11:
            return 8 + (decompressed_size // 4)
        else:
            return 5 + (decompressed_size // 8)

    def detect_asset_type(self, data: bytes) -> AssetType:
        """Detect asset type from raw data"""
        if not data or len(data) < 4:
            return AssetType.UNKNOWN

        data_len = len(data)

        if data_len % 2 == 0:
            valid_colors = self._count_valid_15bit_colors(data[:64])
            if valid_colors >= data_len // 4:
                return AssetType.PALETTE

        if data_len % 64 == 0 and data_len >= 64:
            if self._is_likely_8bpp_tiles(data):
                return AssetType.TILE_8BPP

        if data_len % 32 == 0 and data_len >= 32:
            if self._is_likely_4bpp_tiles(data):
                return AssetType.TILE_4BPP

        if data_len % 2 == 0 and data_len >= 32:
            if self._is_likely_tilemap(data):
                return AssetType.TILEMAP

        return AssetType.UNKNOWN

    def _count_valid_15bit_colors(self, data: bytes) -> int:
        """Count valid 15-bit BGR colors in data"""
        valid = 0
        for i in range(0, min(len(data), 64), 2):
            if i + 1 >= len(data):
                break
            color = data[i] | (data[i + 1] << 8)
            r = color & 0x1F
            g = (color >> 5) & 0x1F
            b = (color >> 10) & 0x1F
            if r <= 31 and g <= 31 and b <= 31:
                valid += 1
        return valid

    def _is_likely_4bpp_tiles(self, data: bytes) -> bool:
        """Check if data looks like 4BPP tiles"""
        if len(data) % 32 != 0:
            return False

        unique_bytes = len(set(data[:64]))

        if unique_bytes > 16 and unique_bytes < 256:
            return True

        return False

    def _is_likely_8bpp_tiles(self, data: bytes) -> bool:
        """Check if data looks like 8BPP tiles"""
        if len(data) % 64 != 0:
            return False

        unique_bytes = len(set(data[:128]))

        if unique_bytes > 32:
            return True

        return False

    def _is_likely_tilemap(self, data: bytes) -> bool:
        """Check if data looks like tilemap"""
        if len(data) < 32:
            return False

        unique_indices = set()
        for i in range(0, min(len(data), 64), 2):
            if i + 1 >= len(data):
                break
            entry = data[i] | (data[i + 1] << 8)
            tile_idx = entry & 0x3FF
            unique_indices.add(tile_idx)

        if 2 <= len(unique_indices) <= 1024:
            return True

        return False

    def find_palette_in_rom(self, rom_data: bytes) -> Optional[int]:
        """Find palette data in ROM, returns offset or None"""
        if not rom_data or len(rom_data) < 512:
            return None

        best_offset = None
        best_score = 0

        for offset in range(0, min(len(rom_data) - 512, 1024 * 1024), 16):
            palette_size = min(512, len(rom_data) - offset)
            sample = rom_data[offset : offset + palette_size]

            score = self._score_palette_candidate(sample)

            if score > best_score:
                best_score = score
                best_offset = offset

        if best_score >= 10:
            return best_offset

        return None

    def _score_palette_candidate(self, data: bytes) -> int:
        """Score how likely data is a palette"""
        if len(data) < 32:
            return -1

        score = 0

        unique_colors = set()
        color_pairs = []

        for i in range(0, min(len(data), 512), 2):
            if i + 1 >= len(data):
                break
            color = data[i] | (data[i + 1] << 8)
            r = color & 0x1F
            g = (color >> 5) & 0x1F
            b = (color >> 10) & 0x1F

            if r <= 31 and g <= 31 and b <= 31:
                unique_colors.add((r, g, b))
                color_pairs.append((r, g, b))

        score += len(unique_colors)

        if len(unique_colors) >= 8:
            score += 5

        if len(color_pairs) >= 16:
            gradient_count = 0
            for i in range(1, len(color_pairs)):
                prev = color_pairs[i - 1]
                curr = color_pairs[i]
                if (
                    abs(curr[0] - prev[0]) <= 8
                    and abs(curr[1] - prev[1]) <= 8
                    and abs(curr[2] - prev[2]) <= 8
                ):
                    gradient_count += 1

            if gradient_count > len(color_pairs) // 3:
                score += 3

        return score

    def load_assets(self, assets_dir: str, ppu) -> bool:
        rom_path = None
        if os.path.isfile(assets_dir) and assets_dir.endswith(".gba"):
            rom_path = assets_dir
        elif os.path.isdir(assets_dir):
            for f in os.listdir(assets_dir):
                if f.endswith(".gba"):
                    rom_path = os.path.join(assets_dir, f)
                    break

        if not rom_path:
            for f in os.listdir("."):
                if f.endswith(".gba"):
                    rom_path = f
                    break

        if not rom_path or not os.path.exists(rom_path):
            return False

        with open(rom_path, "rb") as f:
            rom_data = f.read()

        if not rom_data or len(rom_data) < 512:
            return False

        extractor = AssetExtractor(self.memory)
        palette_offset = extractor.find_palette_in_rom(rom_data)
        if palette_offset:
            palette_data = rom_data[palette_offset : palette_offset + 512]
            ppu.palette_bg = []
            for i in range(0, min(len(palette_data), 512), 2):
                if i + 1 < len(palette_data):
                    color_val = palette_data[i] | (palette_data[i + 1] << 8)
                    r = ((color_val >> 0) & 0x1F) * 8
                    g = ((color_val >> 5) & 0x1F) * 8
                    b = ((color_val >> 10) & 0x1F) * 8
                    ppu.palette_bg.append((r, g, b))

        tile_data = []
        for offset in range(0, len(rom_data) - 32, 2):
            sample = rom_data[offset : offset + 32]
            unique_bytes = len(set(sample[:64]))
            if unique_bytes > 16 and unique_bytes < 256:
                tile_data.extend(sample)
                if len(tile_data) >= 8192:
                    break

        if tile_data:
            ppu.tiles_4bpp = list(tile_data)

        tilemap_data = []
        for offset in range(0, len(rom_data) - 2, 2):
            if len(tilemap_data) >= 1024 * 2:
                break
            if offset + 1 < len(rom_data):
                entry = rom_data[offset] | (rom_data[offset + 1] << 8)
                tilemap_data.append(entry)

        if tilemap_data:
            ppu.bg0_tilemap = tilemap_data[:1024]

        return True
