import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "rom", os.path.join(os.path.dirname(__file__), "..", "gba_runtime", "rom.py")
)
rom_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rom_module)
ROM = rom_module.ROM


TEST_ROM_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "test_roms", "gba-tests-master", "arm", "arm.gba"
)


class TestROM:
    def test_load_rom(self):
        rom = ROM()
        rom.load(TEST_ROM_PATH)
        assert len(rom.data) > 0

    def test_get_header(self):
        rom = ROM()
        rom.load(TEST_ROM_PATH)
        header = rom.get_header()
        assert "entry_point" in header
        assert "title" in header
        assert "game_code" in header
        assert "maker_code" in header
        assert "rom_size" in header

    def test_title_property(self):
        rom = ROM()
        rom.load(TEST_ROM_PATH)
        assert len(rom.title) > 0

    def test_entry_point_property(self):
        rom = ROM()
        rom.load(TEST_ROM_PATH)
        assert rom.entry_point != 0

    def test_game_code_property(self):
        rom = ROM()
        rom.load(TEST_ROM_PATH)
        assert len(rom.game_code) > 0

    def test_maker_code_property(self):
        rom = ROM()
        rom.load(TEST_ROM_PATH)
        assert len(rom.maker_code) > 0

    def test_rom_size_property(self):
        rom = ROM()
        rom.load(TEST_ROM_PATH)
        assert rom.rom_size > 0

    def test_read_bytes(self):
        rom = ROM()
        rom.load(TEST_ROM_PATH)
        first_4 = rom.read_bytes(0, 4)
        assert len(first_4) == 4

    def test_file_not_found(self):
        rom = ROM()
        with pytest.raises(FileNotFoundError):
            rom.load("nonexistent.gba")

    def test_file_too_small(self):
        import tempfile

        rom = ROM()
        with tempfile.NamedTemporaryFile(suffix=".gba", delete=False) as f:
            f.write(b"\x00" * 10)
            temp_path = f.name
        try:
            with pytest.raises(ValueError):
                rom.load(temp_path)
        finally:
            os.unlink(temp_path)
