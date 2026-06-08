"""Cartridge save type detection and management for GBA."""

import os
from typing import Optional, Union

from flash_save import FlashSave, create_flash_save
from eeprom_save import EepromSave, create_eeprom_save


class SaveType:
    NONE = 0
    SRAM = 1
    FLASH512 = 2
    FLASH1M = 3
    EEPROM4K = 4
    EEPROM16K = 5


SAVE_TYPE_NAMES = {
    SaveType.NONE: "None",
    SaveType.SRAM: "SRAM (64KB)",
    SaveType.FLASH512: "FLASH512 (512KB)",
    SaveType.FLASH1M: "FLASH1M (1MB)",
    SaveType.EEPROM4K: "EEPROM4K (512 bytes)",
    SaveType.EEPROM16K: "EEPROM16K (2KB)",
}


ROM_OFFSET_SAVE_TYPE = 0x1A4


SAVE_TYPE_DETECTION = {
    0x00: SaveType.NONE,
    0x01: SaveType.SRAM,
    0x02: SaveType.FLASH512,
    0x03: SaveType.FLASH1M,
    0x04: SaveType.EEPROM4K,
    0x05: SaveType.EEPROM16K,
    0x12: SaveType.FLASH512,
    0x13: SaveType.FLASH1M,
}


KNOWN_GAME_SAVE_TYPES = {
    "POKEMON RUBY": SaveType.FLASH1M,
    "POKEMON SAPPHIRE": SaveType.FLASH1M,
    "POKEMON EMERALD": SaveType.FLASH1M,
    "POKEMON FIRE RED": SaveType.FLASH1M,
    "POKEMON LEAF GREEN": SaveType.FLASH1M,
    "SONIC ADVANCE": SaveType.FLASH512,
    "SONIC ADVANCE 2": SaveType.FLASH512,
    "SONIC ADVANCE 3": SaveType.FLASH512,
    "MARIO KART": SaveType.EEPROM16K,
    "ZELDA MINISH CAP": SaveType.EEPROM4K,
    "METROID FUSION": SaveType.EEPROM4K,
    "METROID ZERO MISSION": SaveType.EEPROM4K,
    "SUPER MARIO ADVANCE": SaveType.EEPROM4K,
    "SUPER MARIO ADVANCE 2": SaveType.EEPROM4K,
    "SUPER MARIO ADVANCE 3": SaveType.EEPROM4K,
    "SUPER MARIO ADVANCE 4": SaveType.EEPROM4K,
}


class SramHandler:
    SRAM_SIZE = 64 * 1024
    
    def __init__(self):
        self._data = bytearray(self.SRAM_SIZE)
        self._filepath = None
        self._dirty = False
    
    @property
    def size(self):
        return self.SRAM_SIZE
    
    def read(self, addr, length=1):
        result = []
        for i in range(length):
            offset = (addr - 0x0A000000 + i) % self.SRAM_SIZE
            result.append(self._data[offset])
        return bytes(result)
    
    def write(self, addr, data):
        for i, byte in enumerate(data):
            offset = (addr - 0x0A000000 + i) % self.SRAM_SIZE
            self._data[offset] = byte
            self._dirty = True
    
    def load_from_file(self, filepath):
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, "rb") as f:
                self._data = bytearray(f.read())
            self._filepath = filepath
            self._dirty = False
            return True
        except:
            return False
    
    def save_to_file(self, filepath=None):
        path = filepath or self._filepath
        if path is None:
            return False
        try:
            d = os.path.dirname(path)
            if d and not os.path.exists(d):
                os.makedirs(d)
            with open(path, "wb") as f:
                f.write(bytes(self._data))
            self._dirty = False
            self._filepath = path
            return True
        except:
            return False
    
    def is_dirty(self):
        return self._dirty
    
    def get_data(self):
        return bytes(self._data)
    
    def set_data(self, data):
        self._data[:len(data)] = data[:self.SRAM_SIZE]
        self._dirty = True


class Cartridge:
    def __init__(self):
        self._save_type = SaveType.NONE
        self._save_handler = None
        self._rom_data = None
        self._game_title = ""
        self._game_code = ""
    
    def load_rom(self, rom_path: str) -> bool:
        try:
            with open(rom_path, "rb") as f:
                self._rom_data = f.read()
            
            if len(self._rom_data) < 0x1A5:
                return False
            
            self._game_title = self._rom_data[0xA0:0xAC].rstrip(b"\x00").decode("ascii", errors="replace")
            self._game_code = self._rom_data[0xAC:0xB0].decode("ascii", errors="replace")
            
            self._detect_save_type()
            self._create_save_handler()
            
            return True
        except Exception:
            return False
    
    def load_rom_data(self, data: bytes) -> bool:
        try:
            self._rom_data = data
            
            if len(self._rom_data) < 0x1A5:
                return False
            
            self._game_title = self._rom_data[0xA0:0xAC].rstrip(b"\x00").decode("ascii", errors="replace")
            self._game_code = self._rom_data[0xAC:0xB0].decode("ascii", errors="replace")
            
            self._detect_save_type()
            self._create_save_handler()
            
            return True
        except Exception:
            return False
    
    def _detect_save_type(self) -> None:
        if self._rom_data is None or len(self._rom_data) < 0x1A5:
            self._save_type = SaveType.NONE
            return
        
        save_type_byte = self._rom_data[ROM_OFFSET_SAVE_TYPE]
        
        self._save_type = SAVE_TYPE_DETECTION.get(save_type_byte, SaveType.NONE)
        
        if self._save_type == SaveType.NONE:
            title_upper = self._game_title.upper()
            for game_pattern, save_type in KNOWN_GAME_SAVE_TYPES.items():
                if game_pattern in title_upper:
                    self._save_type = save_type
                    break
    
    def _create_save_handler(self) -> None:
        if self._save_type == SaveType.NONE:
            self._save_handler = None
        elif self._save_type == SaveType.SRAM:
            self._save_handler = SramHandler()
        elif self._save_type == SaveType.FLASH512:
            self._save_handler = create_flash_save("512KB")
        elif self._save_type == SaveType.FLASH1M:
            self._save_handler = create_flash_save("1MB")
        elif self._save_type == SaveType.EEPROM4K:
            self._save_handler = create_eeprom_save("4K")
        elif self._save_type == SaveType.EEPROM16K:
            self._save_handler = create_eeprom_save("16K")
    
    @property
    def save_type(self) -> int:
        return self._save_type
    
    @property
    def save_type_name(self) -> str:
        return SAVE_TYPE_NAMES.get(self._save_type, "Unknown")
    
    @property
    def game_title(self) -> str:
        return self._game_title
    
    @property
    def game_code(self) -> str:
        return self._game_code
    
    @property
    def has_save(self) -> bool:
        return self._save_handler is not None
    
    def get_save_handler(self):
        return self._save_handler
    
    def read_save(self, addr: int, length: int = 1) -> bytes:
        if self._save_handler is None:
            return bytes([0xFF] * length)
        return self._save_handler.read(addr, length)
    
    def write_save(self, addr: int, data: bytes) -> None:
        if self._save_handler is not None:
            self._save_handler.write(addr, data)
    
    def load_save_file(self, filepath: str) -> bool:
        if self._save_handler is None:
            return False
        return self._save_handler.load_from_file(filepath)
    
    def save_to_file(self, filepath: str) -> bool:
        if self._save_handler is None:
            return False
        return self._save_handler.save_to_file(filepath)
    
    def is_dirty(self) -> bool:
        if self._save_handler is None:
            return False
        return self._save_handler.is_dirty()


def detect_save_type(rom_data: bytes) -> int:
    if rom_data is None or len(rom_data) < 0x1A5:
        return SaveType.NONE
    
    save_type_byte = rom_data[ROM_OFFSET_SAVE_TYPE]
    return SAVE_TYPE_DETECTION.get(save_type_byte, SaveType.NONE)


def create_cartridge(rom_path: str = None) -> Cartridge:
    cartridge = Cartridge()
    if rom_path and os.path.exists(rom_path):
        cartridge.load_rom(rom_path)
    return cartridge
