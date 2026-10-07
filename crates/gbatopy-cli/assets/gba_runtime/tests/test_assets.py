"""Asset extraction unit tests for GBAtoPy."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from assets import AssetExtractor, AssetType
from memory import Memory


class MockMemory:
    """Mock memory for testing asset extraction."""
    
    def __init__(self, data=None):
        self.data = data if data else bytearray(0x10000)
    
    def read_u16(self, addr):
        """Read 16-bit value from memory."""
        if addr + 2 > len(self.data):
            return 0
        return self.data[addr] | (self.data[addr + 1] << 8)
    
    def read_bytes(self, addr, size):
        """Read bytes from memory."""
        if addr >= len(self.data):
            return b""
        end = min(addr + size, len(self.data))
        return bytes(self.data[addr:end])


def test_decompress_lz77_invalid_header():
    """LZ77 decompression: invalid header returns empty bytes."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = b"\x11\x00\x00\x10\x00"
    result = extractor.decompress_lz77(data)
    assert result == b""
    
    data = b"\x10\x00\x00"
    result = extractor.decompress_lz77(data)
    assert result == b""
    
    print("✓ test_decompress_lz77_invalid_header passed")


def test_decompress_lz77_simple():
    """LZ77 decompression: simple raw bytes."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytes([0x10, 0x08, 0x00, 0x00,  # header: size = 8
                  0x00, 0x00, 0x00, 0x00,  # padding
                  0x00,                     # flags: all raw
                  0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48])
    result = extractor.decompress_lz77(data)
    assert result == b"ABCDEFGH"
    
    print("✓ test_decompress_lz77_simple passed")


def test_decompress_huffman_invalid_header():
    """Huffman decompression: invalid header returns empty bytes."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = b"\x10\x00\x00\x00\x00"
    result = extractor.decompress_huffman(data)
    assert result == b""
    
    data = b"\x11\x00\x00"
    result = extractor.decompress_huffman(data)
    assert result == b""
    
    print("✓ test_decompress_huffman_invalid_header passed")


def test_decompress_rle_invalid_header():
    """RLE decompression: invalid header returns empty bytes."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = b"\x10\x00\x00\x00\x00"
    result = extractor.decompress_rle(data)
    assert result == b""
    
    data = b"\x12\x00\x00"
    result = extractor.decompress_rle(data)
    assert result == b""
    
    print("✓ test_decompress_rle_invalid_header passed")


def test_decompress_rle_simple():
    """RLE decompression: simple run-length encoding."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytes([
        0x12, 0x01, 0x00, 0x00, 0x00,  # header: size = 1
        0x80,                           # flag: run-length
        0x41, 0x00                      # byte = 'A', count = 1
    ])
    result = extractor.decompress_rle(data)
    assert result == b"A"
    
    print("✓ test_decompress_rle_simple passed")


def test_extract_palette():
    """Palette extraction: 4-color palette with known values."""
    memory = MockMemory()
    memory.data = bytearray(512)
    
    # Color 0: R=0, G=0, B=0 -> 0x0000
    memory.data[0] = 0x00
    memory.data[1] = 0x00
    # Color 1: R=1, G=0, B=0 -> 0x0001
    memory.data[2] = 0x01
    memory.data[3] = 0x00
    # Color 2: R=0, G=1, B=0 -> 0x0020
    memory.data[4] = 0x20
    memory.data[5] = 0x00
    # Color 3: R=0, G=0, B=1 -> 0x0400
    memory.data[6] = 0x00
    memory.data[7] = 0x04
    
    extractor = AssetExtractor(memory)
    palette = extractor.extract_palette(0, num_colors=4)
    
    assert len(palette) == 4
    assert palette[0] == (0, 0, 0)
    assert palette[1] == (8, 0, 0)
    assert palette[2] == (0, 8, 0)
    assert palette[3] == (0, 0, 8)
    
    print("✓ test_extract_palette passed")


def test_extract_palette_256_colors():
    """Palette extraction: full 256-color palette."""
    memory = MockMemory()
    memory.data = bytearray(1024)
    
    for i in range(256):
        color = i & 0x7FFF
        memory.data[i * 2] = color & 0xFF
        memory.data[i * 2 + 1] = (color >> 8) & 0xFF
    
    extractor = AssetExtractor(memory)
    palette = extractor.extract_palette(0, num_colors=256)
    
    assert len(palette) == 256
    assert palette[0] == (0, 0, 0)
    assert palette[1] == (8, 0, 0)
    
    print("✓ test_extract_palette_256_colors passed")


def test_extract_tile_4bpp():
    """4BPP tile extraction: 8x8 tile = 32 bytes."""
    memory = MockMemory()
    memory.data = bytearray(0x10000)
    
    expected = bytes(range(32))
    memory.data[0:32] = expected
    
    extractor = AssetExtractor(memory)
    tile = extractor.extract_tile_4bpp(0, tile_num=0)
    
    assert len(tile) == 32
    assert tile == expected
    
    print("✓ test_extract_tile_4bpp passed")


def test_extract_tile_4bpp_multiple():
    """4BPP tile extraction: multiple tiles."""
    memory = MockMemory()
    memory.data = bytearray(0x10000)
    
    for i in range(64):
        memory.data[i] = i
    
    extractor = AssetExtractor(memory)
    tile0 = extractor.extract_tile_4bpp(0, tile_num=0)
    tile1 = extractor.extract_tile_4bpp(0, tile_num=1)
    
    assert tile0 == bytes(range(32))
    assert tile1 == bytes(range(32, 64))
    
    print("✓ test_extract_tile_4bpp_multiple passed")


def test_extract_tile_8bpp():
    """8BPP tile extraction: 8x8 tile = 64 bytes."""
    memory = MockMemory()
    memory.data = bytearray(0x10000)
    
    expected = bytes(range(64))
    memory.data[0:64] = expected
    
    extractor = AssetExtractor(memory)
    tile = extractor.extract_tile_8bpp(0, tile_num=0)
    
    assert len(tile) == 64
    assert tile == expected
    
    print("✓ test_extract_tile_8bpp passed")


def test_extract_tile_8bpp_multiple():
    """8BPP tile extraction: multiple tiles."""
    memory = MockMemory()
    memory.data = bytearray(0x10000)
    
    for i in range(128):
        memory.data[i] = i & 0xFF
    
    extractor = AssetExtractor(memory)
    tile0 = extractor.extract_tile_8bpp(0, tile_num=0)
    tile1 = extractor.extract_tile_8bpp(0, tile_num=1)
    
    assert tile0 == bytes(range(64))
    assert tile1 == bytes(range(64, 128))
    
    print("✓ test_extract_tile_8bpp_multiple passed")


def test_scan_rom_for_assets_empty():
    """ROM scanning: empty ROM returns empty asset lists."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    assets = extractor.scan_rom_for_assets(b"")
    
    assert assets["palettes"] == []
    assert assets["compressed"] == []
    assert assets["tiles_4bpp"] == []
    assert assets["tiles_8bpp"] == []
    assert assets["tilemaps"] == []
    
    print("✓ test_scan_rom_for_assets_empty passed")


def test_scan_rom_for_assets_compressed():
    """ROM scanning: detect compressed data."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    rom_data = bytes([0x10, 0x00, 0x04, 0x00] + [0x00] * 10)
    assets = extractor.scan_rom_for_assets(rom_data)
    
    assert isinstance(assets, dict)
    assert "compressed" in assets
    
    print("✓ test_scan_rom_for_assets_compressed passed")


def test_detect_asset_type_palette():
    """Asset detection: valid palette data."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytearray()
    for i in range(32):
        color = i & 0x7FFF
        data.append(color & 0xFF)
        data.append((color >> 8) & 0xFF)
    
    asset_type = extractor.detect_asset_type(bytes(data))
    assert asset_type == AssetType.PALETTE
    
    print("✓ test_detect_asset_type_palette passed")


def test_detect_asset_type_unknown():
    """Asset detection: unknown/invalid data."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytes([0xFF, 0xFF, 0xFF])
    asset_type = extractor.detect_asset_type(data)
    assert asset_type == AssetType.UNKNOWN
    
    print("✓ test_detect_asset_type_unknown passed")


def test_find_palette_in_rom_empty():
    """Palette finding: empty ROM returns None."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    result = extractor.find_palette_in_rom(b"")
    assert result is None
    
    print("✓ test_find_palette_in_rom_empty passed")


def test_find_palette_in_rom_not_found():
    """Palette finding: ROM without palette returns None."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    rom_data = bytes([0xFF] * 1024)
    result = extractor.find_palette_in_rom(rom_data)
    assert result is None
    
    print("✓ test_find_palette_in_rom_not_found passed")


def test_count_valid_15bit_colors():
    """Palette scoring: count valid 15-bit colors."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytearray()
    for i in range(8):
        color = i & 0x7FFF
        data.append(color & 0xFF)
        data.append((color >> 8) & 0xFF)
    data.append(0xFF)
    data.append(0xFF)
    
    count = extractor._count_valid_15bit_colors(bytes(data))
    assert count == 9  # 0xFFFF is valid white (31,31,31)
    
    print("✓ test_count_valid_15bit_colors passed")


def test_score_palette_candidate_valid():
    """Palette scoring: valid palette gets high score."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytearray()
    for i in range(16):
        color = i & 0x7FFF
        data.append(color & 0xFF)
        data.append((color >> 8) & 0xFF)
    
    score = extractor._score_palette_candidate(bytes(data))
    assert score >= 10
    
    print("✓ test_score_palette_candidate_valid passed")


def test_score_palette_candidate_invalid():
    """Palette scoring: invalid data gets low score."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytes([0xFF] * 32)
    score = extractor._score_palette_candidate(data)
    assert score < 10
    
    print("✓ test_score_palette_candidate_invalid passed")


def test_estimate_compressed_size_lz77():
    """Size estimation: LZ77 compressed size."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    size = extractor._estimate_compressed_size(0, 1024, 0x10)
    expected = 4 + (1024 // 8) + 1
    assert size == expected
    
    print("✓ test_estimate_compressed_size_lz77 passed")


def test_estimate_compressed_size_huffman():
    """Size estimation: Huffman compressed size."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    size = extractor._estimate_compressed_size(0, 1024, 0x11)
    expected = 8 + (1024 // 4)
    assert size == expected
    
    print("✓ test_estimate_compressed_size_huffman passed")


def test_estimate_compressed_size_rle():
    """Size estimation: RLE compressed size."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    size = extractor._estimate_compressed_size(0, 1024, 0x12)
    expected = 5 + (1024 // 8)
    assert size == expected
    
    print("✓ test_estimate_compressed_size_rle passed")


def test_is_likely_4bpp_tiles_valid():
    """Tile detection: valid 4BPP tile data."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytearray()
    for i in range(64):
        data.append((i * 7) % 32)
    
    result = extractor._is_likely_4bpp_tiles(bytes(data))
    assert result == True
    
    print("✓ test_is_likely_4bpp_tiles_valid passed")


def test_is_likely_4bpp_tiles_wrong_size():
    """Tile detection: non-32-aligned data."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytes([0x00] * 30)
    result = extractor._is_likely_4bpp_tiles(data)
    assert result == False
    
    print("✓ test_is_likely_4bpp_tiles_wrong_size passed")


def test_is_likely_8bpp_tiles_valid():
    """Tile detection: valid 8BPP tile data."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytearray()
    for i in range(128):
        data.append(i % 256)
    
    result = extractor._is_likely_8bpp_tiles(bytes(data))
    assert result == True
    
    print("✓ test_is_likely_8bpp_tiles_valid passed")


def test_is_likely_8bpp_tiles_wrong_size():
    """Tile detection: non-64-aligned data."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytes([0x00] * 60)
    result = extractor._is_likely_8bpp_tiles(data)
    assert result == False
    
    print("✓ test_is_likely_8bpp_tiles_wrong_size passed")


def test_is_likely_tilemap_valid():
    """Tilemap detection: valid tilemap data."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytearray()
    for i in range(32):
        entry = i & 0x3FF
        data.append(entry & 0xFF)
        data.append((entry >> 8) & 0xFF)
    
    result = extractor._is_likely_tilemap(bytes(data))
    assert result == True
    
    print("✓ test_is_likely_tilemap_valid passed")


def test_is_likely_tilemap_too_small():
    """Tilemap detection: data too small."""
    memory = Memory()
    extractor = AssetExtractor(memory)
    
    data = bytes([0x00] * 16)
    result = extractor._is_likely_tilemap(data)
    assert result == False
    
    print("✓ test_is_likely_tilemap_too_small passed")


if __name__ == "__main__":
    test_decompress_lz77_invalid_header()
    test_decompress_lz77_simple()
    test_decompress_huffman_invalid_header()
    test_decompress_rle_invalid_header()
    test_decompress_rle_simple()
    test_extract_palette()
    test_extract_palette_256_colors()
    test_extract_tile_4bpp()
    test_extract_tile_4bpp_multiple()
    test_extract_tile_8bpp()
    test_extract_tile_8bpp_multiple()
    test_scan_rom_for_assets_empty()
    test_scan_rom_for_assets_compressed()
    test_detect_asset_type_palette()
    test_detect_asset_type_unknown()
    test_find_palette_in_rom_empty()
    test_find_palette_in_rom_not_found()
    test_count_valid_15bit_colors()
    test_score_palette_candidate_valid()
    test_score_palette_candidate_invalid()
    test_estimate_compressed_size_lz77()
    test_estimate_compressed_size_huffman()
    test_estimate_compressed_size_rle()
    test_is_likely_4bpp_tiles_valid()
    test_is_likely_4bpp_tiles_wrong_size()
    test_is_likely_8bpp_tiles_valid()
    test_is_likely_8bpp_tiles_wrong_size()
    test_is_likely_tilemap_valid()
    test_is_likely_tilemap_too_small()
    
    print("\nAll 30 asset tests passed!")