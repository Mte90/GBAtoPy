"""FLASH save memory support for GBA cartridges.

Supports both FLASH512 (512KB / 8Mbit) and FLASH1M (1MB / 16Mbit) save types.
Used by games like Pokemon Ruby/Sapphire/Emerald, Sonic Advance, etc.

The FLASH chip uses a command protocol for bank switching, erasing, and writing.
"""

import os
from typing import Optional


class FlashSave:
    """FLASH save memory handler for GBA cartridges.
    
    Supports:
    - FLASH512: 512KB (8Mbit) with 2 banks of 256KB
    - FLASH1M: 1MB (16Mbit) with 2 banks of 512KB
    
    Memory map:
    - FLASH512: 8 x 32KB sectors per bank, 2 banks
    - FLASH1M: 8 x 64KB sectors per bank, 2 banks
    """
    
    FLASH512_SIZE = 512 * 1024
    FLASH1M_SIZE = 1024 * 1024
    
    FLASH512_SECTOR_SIZE = 32 * 1024
    FLASH1M_SECTOR_SIZE = 64 * 1024
    
    SECTORS_PER_BANK = 8
    
    CMD_UNLOCK1 = 0xAA
    CMD_UNLOCK2 = 0x55
    CMD_READ_ID = 0x90
    CMD_READ_STATUS = 0xF0
    CMD_WRITE_BYTE = 0xA0
    CMD_ERASE_SETUP = 0x80
    CMD_ERASE_SECTOR = 0x30
    CMD_ERASE_CHIP = 0x10
    CMD_BANK_SWITCH = 0xB0
    CMD_ERASE_CONTINUE = 0xD0
    
    CMD_ADDR1 = 0x5555
    CMD_ADDR2 = 0x2AAA
    
    MANUFACTURER_ID_PANASONIC = 0x1B
    MANUFACTURER_ID_SANYO = 0x1C
    MANUFACTURER_ID_MACRONIX = 0x1C
    DEVICE_ID_FLASH512 = 0x09
    DEVICE_ID_FLASH1M = 0x1C
    
    def __init__(self, size: int = FLASH512_SIZE):
        self._size = size
        self._is_1m = (size == self.FLASH1M_SIZE)
        
        self._sector_size = self.FLASH1M_SECTOR_SIZE if self._is_1m else self.FLASH512_SECTOR_SIZE
        self._num_sectors = self.SECTORS_PER_BANK * 2
        
        self._data = bytearray(self._size)
        self._current_bank = 0
        
        self._command_state = 0
        self._pending_command = None
        self._erase_address = None
        
        self._filepath: Optional[str] = None
        self._dirty = False
    
    @property
    def size(self) -> int:
        return self._size
    
    @property
    def is_1m(self) -> bool:
        return self._is_1m
    
    @property
    def sector_size(self) -> int:
        return self._sector_size
    
    def _get_bank_offset(self, bank: int) -> int:
        if self._is_1m:
            return bank * (self.FLASH1M_SIZE // 2)
        return bank * (self.FLASH512_SIZE // 2)
    
    def _translate_address(self, addr: int) -> int:
        offset = addr & 0xFFFF
        
        if self._is_1m:
            if offset >= 0x8000:
                offset = (offset & 0x7FFF) | (self._current_bank << 15)
        else:
            if offset >= 0x8000:
                offset = (offset & 0x7FFF) | (self._current_bank << 15)
        
        return offset
    
    def read(self, addr: int, length: int = 1) -> bytes:
        result = bytearray()
        
        for i in range(length):
            offset = self._translate_address(addr + i)
            if offset < self._size:
                result.append(self._data[offset])
            else:
                result.append(0xFF)
        
        return bytes(result)
    
    def write(self, addr: int, data: bytes) -> None:
        for i, byte in enumerate(data):
            self._write_byte(addr + i, byte)
    
    def _write_byte(self, addr: int, value: int) -> None:
        offset = addr & 0xFFFF
        
        if offset == self.CMD_ADDR1:
            if value == self.CMD_UNLOCK1:
                self._command_state = 1
                return
            elif value == self.CMD_READ_ID:
                if self._command_state == 2:
                    self._pending_command = self.CMD_READ_ID
                    self._command_state = 0
                    return
            elif value == self.CMD_ERASE_SETUP:
                if self._command_state == 2:
                    self._pending_command = self.CMD_ERASE_SETUP
                    self._command_state = 0
                    return
            elif value == self.CMD_ERASE_CHIP:
                if self._command_state == 2 and self._pending_command == self.CMD_ERASE_SETUP:
                    self._erase_chip()
                    self._pending_command = None
                    self._command_state = 0
                    return
        
        elif offset == self.CMD_ADDR2:
            if value == self.CMD_UNLOCK2:
                if self._command_state == 1:
                    self._command_state = 2
                    return
            elif value == self.CMD_WRITE_BYTE:
                if self._command_state == 2:
                    self._pending_command = self.CMD_WRITE_BYTE
                    self._command_state = 0
                    return
            elif value == self.CMD_ERASE_SECTOR:
                if self._command_state == 2 and self._pending_command == self.CMD_ERASE_SETUP:
                    if self._erase_address is not None:
                        self._erase_sector(self._erase_address)
                    self._pending_command = None
                    self._erase_address = None
                    self._command_state = 0
                    return
            elif value == self.CMD_ERASE_CONTINUE:
                if self._command_state == 2 and self._pending_command == self.CMD_ERASE_SETUP:
                    if self._erase_address is not None:
                        self._erase_sector(self._erase_address)
                    self._pending_command = None
                    self._erase_address = None
                    self._command_state = 0
                    return
        
        elif offset == 0xAAA and value == self.CMD_BANK_SWITCH:
            self._pending_command = self.CMD_BANK_SWITCH
            self._command_state = 0
            return
        
        elif addr >= 0x0A000000 and addr <= 0x0A00FFFF:
            if self._pending_command == self.CMD_BANK_SWITCH:
                self._current_bank = 1 if (value & 0x1) else 0
                self._pending_command = None
                return
            
            if self._pending_command == self.CMD_WRITE_BYTE:
                flash_offset = self._translate_address(addr)
                if flash_offset < self._size:
                    self._data[flash_offset] = value
                    self._dirty = True
                self._pending_command = None
                return
            
            if self._pending_command == self.CMD_ERASE_SETUP:
                self._erase_address = addr & 0xFFFF
                return
        
        self._command_state = 0
        self._pending_command = None
        
        flash_offset = self._translate_address(addr)
        if flash_offset < self._size:
            self._data[flash_offset] = value
            self._dirty = True
    
    def _erase_sector(self, addr: int) -> None:
        offset = addr & 0xFFFF
        
        if self._is_1m:
            if offset >= 0x8000:
                bank = 1
                offset = offset & 0x7FFF
            else:
                bank = 0
            sector = offset // self.FLASH1M_SECTOR_SIZE
        else:
            if offset >= 0x8000:
                bank = 1
                offset = offset & 0x7FFF
            else:
                bank = 0
            sector = offset // self.FLASH512_SECTOR_SIZE
        
        sector_offset = (bank * (self.SECTORS_PER_BANK * self._sector_size)) + (sector * self._sector_size)
        
        if sector_offset + self._sector_size <= self._size:
            for i in range(self._sector_size):
                self._data[sector_offset + i] = 0xFF
            self._dirty = True
    
    def _erase_chip(self) -> None:
        for i in range(self._size):
            self._data[i] = 0xFF
        self._dirty = True
    
    def read_id(self) -> int:
        if self._is_1m:
            return self.MANUFACTURER_ID_MACRONIX
        return self.MANUFACTURER_ID_PANASONIC
    
    def read_device_id(self) -> int:
        if self._is_1m:
            return self.DEVICE_ID_FLASH1M
        return self.DEVICE_ID_FLASH512
    
    def get_status(self) -> int:
        return 0x80
    
    def set_bank(self, bank: int) -> None:
        self._current_bank = bank & 1
    
    def get_bank(self) -> int:
        return self._current_bank
    
    def load_from_file(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            
            if len(data) == self.FLASH1M_SIZE:
                self._data = bytearray(data)
                self._size = self.FLASH1M_SIZE
                self._is_1m = True
                self._sector_size = self.FLASH1M_SECTOR_SIZE
            elif len(data) == self.FLASH512_SIZE:
                self._data = bytearray(data)
                self._size = self.FLASH512_SIZE
                self._is_1m = False
                self._sector_size = self.FLASH512_SECTOR_SIZE
            else:
                self._data = bytearray(self._size)
                self._data[:len(data)] = data[:self._size]
            
            self._filepath = filepath
            self._dirty = False
            return True
        except Exception:
            return False
    
    def save_to_file(self, filepath: Optional[str] = None) -> bool:
        path = filepath or self._filepath
        if path is None:
            return False
        
        try:
            directory = os.path.dirname(path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            with open(path, "wb") as f:
                f.write(bytes(self._data))
            
            self._dirty = False
            self._filepath = path
            return True
        except Exception:
            return False
    
    def is_dirty(self) -> bool:
        return self._dirty
    
    def get_data(self) -> bytes:
        return bytes(self._data)
    
    def set_data(self, data: bytes) -> None:
        size = min(len(data), self._size)
        self._data[:size] = data[:size]
        if len(data) < self._size:
            self._data[size:] = b'\xFF' * (self._size - size)
        self._dirty = True


def create_flash_save(size: str = "512KB") -> FlashSave:
    if size == "1MB":
        return FlashSave(FlashSave.FLASH1M_SIZE)
    return FlashSave(FlashSave.FLASH512_SIZE)