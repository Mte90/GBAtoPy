"""ROM loader and header parser tests for GBAtoPy.

Tests cover ROM file loading, header parsing (title, game code, maker code,
entry point), size validation, and data access methods.
"""
import os, sys
import pytest
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from rom import ROM


def _make_minimal_rom_header(
    title: bytes = b"TEST GAME     ",
    game_code: bytes = b"TEST",
    maker_code: bytes = b"00",
    entry_point: bytes = b"\xea\xff\xff\xff",  # ARM branch: 0xFFFFFFEA in little-endian
    rom_size_code: int = 0x18,
) -> bytes:
    """Create a minimal valid GBA ROM header (0xC0 bytes).
    
    Args:
        title: 12 bytes for game title (null-padded)
        game_code: 4 bytes for game code
        maker_code: 2 bytes for maker code
        entry_point: 4 bytes for ARM branch instruction
        rom_size_code: 1 byte ROM size code
        
    Returns:
        0xC0 byte header with padding to minimum ROM size
    """
    # Build header structure
    header = bytearray(0xC0)
    
    # Entry point at 0x00 (4 bytes)
    header[0x00:0x04] = entry_point
    
    # Nintendo logo at 0x04 (156 bytes) - fill with zeros
    # In real ROMs this is a specific compressed image
    header[0x04:0xA0] = b"\x00" * 0x9C
    
    # Title at 0xA0 (12 bytes)
    header[0xA0:0xAC] = title[:12].ljust(12, b"\x00")
    
    # Game code at 0xAC (4 bytes)
    header[0xAC:0xB0] = game_code[:4].ljust(4, b"\x00")
    
    # Maker code at 0xB0 (2 bytes)
    header[0xB0:0xB2] = maker_code[:2].ljust(2, b"\x00")
    
    # ROM size code at 0xB4 (1 byte)
    header[0xB4] = rom_size_code
    
    # Fill rest with zeros to reach 0xC0 bytes
    # (header is already 0xC0 bytes)
    
    return bytes(header)


class TestROMConstruction:
    """Test ROM class construction and basic initialization."""
    
    def test_empty_rom_construction(self):
        """ROM instance created with empty data and header dict."""
        rom = ROM()
        
        assert rom._data == b""
        assert rom._header == {}
        
        print("✓ test_empty_rom_construction passed")
    
    def test_load_nonexistent_file(self):
        """Loading nonexistent file raises FileNotFoundError."""
        rom = ROM()
        
        with pytest.raises(FileNotFoundError):
            rom.load("/nonexistent/path/rom.gba")
        
        print("✓ test_load_nonexistent_file passed")
    
    def test_file_too_small(self, tmp_path):
        """ROM file smaller than 0xC0 bytes raises ValueError."""
        # Create file with only 0x50 bytes
        test_file = tmp_path / "small.gba"
        test_file.write_bytes(b"\x00" * 0x50)
        
        rom = ROM()
        
        with pytest.raises(ValueError, match="ROM file too small"):
            rom.load(str(test_file))
        
        print("✓ test_file_too_small passed")
    
    def test_file_exactly_minimum_size(self, tmp_path):
        """ROM file exactly 0xC0 bytes loads successfully."""
        header = _make_minimal_rom_header()
        
        test_file = tmp_path / "exact.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        assert len(rom.data) == 0xC0
        assert rom.get_header() is not None
        
        print("✓ test_file_exactly_minimum_size passed")


class TestHeaderParsing:
    """Test GBA ROM header field parsing."""
    
    def test_title_parsing(self, tmp_path):
        """Title field (12 bytes at 0xA0) is correctly parsed."""
        title = b"SUPER GAME\x00\x00"  # Null-padded, not space-padded
        header = _make_minimal_rom_header(title=title)
        
        test_file = tmp_path / "title.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        assert rom.title == "SUPER GAME"
        assert len(rom.title) <= 12
        
        print("✓ test_title_parsing passed")
    
    def test_title_null_padding(self, tmp_path):
        """Title with null padding is stripped correctly."""
        title = b"SHORT"  # Only 5 bytes, rest should be null-padded
        header = _make_minimal_rom_header(title=title)
        
        test_file = tmp_path / "short_title.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        assert rom.title == "SHORT"
        
        print("✓ test_title_null_padding passed")
    
    def test_title_full_length(self, tmp_path):
        """Title with full 12 bytes is parsed correctly."""
        title = b"FULLLENGTH12\x00"  # Exactly 12 bytes
        header = _make_minimal_rom_header(title=title)
        
        test_file = tmp_path / "full_title.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        assert rom.title == "FULLLENGTH12"
        assert len(rom.title) == 12
        
        print("✓ test_title_full_length passed")
    
    def test_game_code_parsing(self, tmp_path):
        """Game code (4 bytes at 0xAC) is correctly parsed."""
        game_code = b"AGBE"
        header = _make_minimal_rom_header(game_code=game_code)
        
        test_file = tmp_path / "gamecode.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        assert rom.game_code == "AGBE"
        
        print("✓ test_game_code_parsing passed")
    
    def test_maker_code_parsing(self, tmp_path):
        """Maker code (2 bytes at 0xB0) is correctly parsed."""
        maker_code = b"00"
        header = _make_minimal_rom_header(maker_code=maker_code)
        
        test_file = tmp_path / "maker.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        assert rom.maker_code == "00"
        
        print("✓ test_maker_code_parsing passed")
    
    def test_entry_point_parsing(self, tmp_path):
        """Entry point (4 bytes at 0x00) is correctly parsed."""
        # ARM branch instruction: 0xFFFFFFEA in little-endian
        entry_point = b"\xea\xff\xff\xff"
        header = _make_minimal_rom_header(entry_point=entry_point)
        
        test_file = tmp_path / "entry.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        assert rom.entry_point == 0xFFFFFFEA
        
        print("✓ test_entry_point_parsing passed")
    
    def test_entry_point_various_values(self, tmp_path):
        """Entry point with various values is correctly parsed."""
        test_cases = [
            (b"\x00\x00\x00\x00", 0x00000000),
            (b"\x00\x00\x00\x08", 0x08000000),  # Little-endian
            (b"\xff\xff\xff\xff", 0xFFFFFFFF),
            (b"\x12\x34\x56\x78", 0x78563412),  # Little-endian
        ]
        
        for entry_bytes, expected in test_cases:
            header = _make_minimal_rom_header(entry_point=entry_bytes)
            
            test_file = tmp_path / f"entry_{expected:08X}.gba"
            test_file.write_bytes(header)
            
            rom = ROM()
            rom.load(str(test_file))
            
            assert rom.entry_point == expected, f"Expected 0x{expected:08X}, got 0x{rom.entry_point:08X}"
        
        print("✓ test_entry_point_various_values passed")


class TestROMSize:
    """Test ROM size code parsing."""
    
    def test_rom_size_code_0x17(self, tmp_path):
        """ROM size code 0x17 results in calculated size."""
        header = _make_minimal_rom_header(rom_size_code=0x17)
        
        test_file = tmp_path / "size17.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        # Size code 0x17: shift = 0x17 & 0x0F = 7, rom_size = 0x80000 << 7
        expected_size = 0x80000 << 7
        assert rom.rom_size == expected_size
        
        print("✓ test_rom_size_code_0x18 passed")
    
    def test_rom_size_code_0x10(self, tmp_path):
        """ROM size code 0x10 results in calculated size."""
        header = _make_minimal_rom_header(rom_size_code=0x10)
        
        test_file = tmp_path / "size10.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        # Size code 0x10: shift = 0x10 & 0x0F = 0, rom_size = 0x80000 << 0
        expected_size = 0x80000 << 0
        assert rom.rom_size == expected_size
        
        print("✓ test_rom_size_code_0x10 passed")
    
    def test_rom_size_fallback_to_actual(self, tmp_path):
        """ROM size falls back to actual file size when code is invalid."""
        # Create a larger ROM file
        header = _make_minimal_rom_header(rom_size_code=0xFF)
        full_rom = header + b"\x00" * (0x100000 - 0xC0)  # 1MB total
        
        test_file = tmp_path / "large.gba"
        test_file.write_bytes(full_rom)
        
        rom = ROM()
        rom.load(str(test_file))
        
        # Size code 0xFF is invalid, should fall back to actual size
        assert rom.rom_size == len(full_rom)
        
        print("✓ test_rom_size_fallback_to_actual passed")


class TestROMDataAccess:
    """Test ROM data access methods."""
    
    def test_read_bytes_at_offset(self, tmp_path):
        """read_bytes reads correct data at given offset."""
        header = _make_minimal_rom_header()
        
        test_file = tmp_path / "read.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        # Read entry point bytes (ARM branch: 0xFFFFFFEA in little-endian)
        entry_bytes = rom.read_bytes(0x00, 4)
        assert entry_bytes == b"\xea\xff\xff\xff"
        
        print("✓ test_read_bytes_at_offset passed")
    
    def test_read_bytes_title_region(self, tmp_path):
        """read_bytes reads title region correctly."""
        title = b"MY GAME     "
        header = _make_minimal_rom_header(title=title)
        
        test_file = tmp_path / "read_title.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        # Read title bytes
        title_bytes = rom.read_bytes(0xA0, 12)
        assert title_bytes == b"MY GAME     "
        
        print("✓ test_read_bytes_title_region passed")
    
    def test_read_bytes_cross_boundary(self, tmp_path):
        """read_bytes handles reads crossing region boundaries."""
        header = _make_minimal_rom_header()
        
        test_file = tmp_path / "boundary.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        # Read from 0xBE to 0xC2 (crosses 0xC0 boundary)
        # Should return only available bytes
        data = rom.read_bytes(0xBE, 10)
        assert len(data) == 2  # Only 2 bytes available
        
        print("✓ test_read_bytes_cross_boundary passed")
    
    def test_read_bytes_empty_range(self, tmp_path):
        """read_bytes with length=0 returns empty bytes."""
        header = _make_minimal_rom_header()
        
        test_file = tmp_path / "empty.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        data = rom.read_bytes(0x00, 0)
        assert data == b""
        assert len(data) == 0
        
        print("✓ test_read_bytes_empty_range passed")
    
    def test_read_bytes_past_end(self, tmp_path):
        """read_bytes at offset past end returns empty bytes."""
        header = _make_minimal_rom_header()
        
        test_file = tmp_path / "past_end.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        # Read well past end of 0xC0 byte ROM
        data = rom.read_bytes(0x1000, 4)
        assert data == b""
        
        print("✓ test_read_bytes_past_end passed")


class TestHeaderDictionary:
    """Test get_header() dictionary output."""
    
    def test_header_dict_keys(self, tmp_path):
        """get_header() returns dict with all expected keys."""
        header = _make_minimal_rom_header()
        
        test_file = tmp_path / "dict.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        header_dict = rom.get_header()
        
        assert "entry_point" in header_dict
        assert "title" in header_dict
        assert "game_code" in header_dict
        assert "maker_code" in header_dict
        assert "rom_size" in header_dict
        
        print("✓ test_header_dict_keys passed")
    
    def test_header_dict_is_copy(self, tmp_path):
        """get_header() returns a copy, not the internal dict."""
        header = _make_minimal_rom_header()
        
        test_file = tmp_path / "copy.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        h1 = rom.get_header()
        h2 = rom.get_header()
        
        assert h1 is not h2  # Different objects
        assert h1 == h2      # Same content
        
        print("✓ test_header_dict_is_copy passed")
    
    def test_header_dict_values_match_properties(self, tmp_path):
        """get_header() values match property accessors."""
        header = _make_minimal_rom_header(
            title=b"TEST    ",
            game_code=b"ABCD",
            maker_code=b"XY",
            entry_point=b"\xea\x00\x00\x00",
        )
        
        test_file = tmp_path / "match.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        h = rom.get_header()
        
        assert h["title"] == rom.title
        assert h["game_code"] == rom.game_code
        assert h["maker_code"] == rom.maker_code
        assert h["entry_point"] == rom.entry_point
        
        print("✓ test_header_dict_values_match_properties passed")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_file(self, tmp_path):
        """Empty file (0 bytes) raises ValueError."""
        test_file = tmp_path / "empty.gba"
        test_file.write_bytes(b"")
        
        rom = ROM()
        
        with pytest.raises(ValueError, match="ROM file too small"):
            rom.load(str(test_file))
        
        print("✓ test_empty_file passed")
    
    def test_large_rom_file(self, tmp_path):
        """Large ROM file (several MB) loads successfully."""
        header = _make_minimal_rom_header()
        # Create a 4MB ROM
        large_rom = header + b"\x00" * (4 * 1024 * 1024 - 0xC0)
        
        test_file = tmp_path / "large.gba"
        test_file.write_bytes(large_rom)
        
        rom = ROM()
        rom.load(str(test_file))
        
        assert len(rom.data) == 4 * 1024 * 1024
        
        print("✓ test_large_rom_file passed")
    
    def test_special_characters_in_title(self, tmp_path):
        """Title with non-ASCII characters is handled gracefully."""
        # Use bytes that aren't valid ASCII
        title = b"TEST\xFF\xFE\xFD\xFC\xFB\xFA"
        header = _make_minimal_rom_header(title=title)
        
        test_file = tmp_path / "special.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        # Should decode with replacement characters
        assert len(rom.title) <= 12
        
        print("✓ test_special_characters_in_title passed")
    
    def test_data_property_immutability(self, tmp_path):
        """ROM data property returns data that can be read."""
        header = _make_minimal_rom_header()
        
        test_file = tmp_path / "data.gba"
        test_file.write_bytes(header)
        
        rom = ROM()
        rom.load(str(test_file))
        
        data = rom.data
        assert isinstance(data, bytes)
        assert len(data) == 0xC0
        
        print("✓ test_data_property_immutability passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])