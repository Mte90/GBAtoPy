"""EEPROM save memory support for GBA cartridges.

Supports both 4Kbit (512 bytes) and 16Kbit (2KB) EEPROM save types.
Used by games like Zelda Minish Cap, Metroid Fusion, Mario Kart, etc.

The EEPROM uses a serial communication protocol with address wrapping.
"""

import os
from typing import Optional


class EepromSave:
    """EEPROM save memory handler for GBA cartridges.
    
    Supports:
    - EEPROM4K: 4Kbit (512 bytes) with 10-bit addressing
    - EEPROM16K: 16Kbit (2KB) with 14-bit addressing
    
    The EEPROM uses a serial-like protocol:
    - Commands: READ (0x03), WRITE (0x02), WREN (0x06), WRDI (0x04)
    - Address is sent MSB first
    - Data is read/written sequentially
    """
    
    EEPROM4K_SIZE = 512
    EEPROM16K_SIZE = 2048
    
    EEPROM4K_ADDR_BITS = 10
    EEPROM16K_ADDR_BITS = 14
    
    CMD_READ = 0x03
    CMD_WRITE = 0x02
    CMD_WREN = 0x06
    CMD_WRDI = 0x04
    CMD_RDSR = 0x05
    CMD_WRSR = 0x01
    
    STATUS_WIP = 0x01
    STATUS_WEL = 0x02
    
    def __init__(self, size: int = EEPROM4K_SIZE):
        self._size = size
        self._is_16k = (size == self.EEPROM16K_SIZE)
        
        self._addr_bits = self.EEPROM16K_ADDR_BITS if self._is_16k else self.EEPROM4K_ADDR_BITS
        
        self._data = bytearray(self._size)
        
        self._write_enabled = False
        self._command_buffer = []
        self._command_state = 0
        
        self._filepath: Optional[str] = None
        self._dirty = False
    
    @property
    def size(self) -> int:
        return self._size
    
    @property
    def is_16k(self) -> bool:
        return self._is_16k
    
    @property
    def addr_bits(self) -> int:
        return self._addr_bits
    
    def _translate_address(self, addr: int) -> int:
        return addr % self._size
    
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
        if not self._write_enabled:
            return
        
        for i, byte in enumerate(data):
            offset = self._translate_address(addr + i)
            if offset < self._size:
                self._data[offset] = byte
                self._dirty = True
    
    def send_command(self, value: int) -> Optional[int]:
        self._command_buffer.append(value)
        
        if self._command_state == 0:
            cmd = value
            
            if cmd == self.CMD_WREN:
                self._write_enabled = True
                self._command_buffer = []
                self._command_state = 0
                return None
            
            elif cmd == self.CMD_WRDI:
                self._write_enabled = False
                self._command_buffer = []
                self._command_state = 0
                return None
            
            elif cmd == self.CMD_RDSR:
                self._command_state = 1
                status = 0x00
                if self._write_enabled:
                    status |= self.STATUS_WEL
                return status
            
            elif cmd == self.CMD_READ:
                self._command_state = 2
                return None
            
            elif cmd == self.CMD_WRITE:
                self._command_state = 3
                return None
            
            else:
                self._command_buffer = []
                return None
        
        elif self._command_state == 1:
            self._command_buffer = []
            self._command_state = 0
            return 0x00
        
        elif self._command_state == 2:
            if len(self._command_buffer) >= 2:
                addr_bytes = self._command_buffer[-2:]
                addr = ((addr_bytes[0] << 8) | addr_bytes[1]) & ((1 << self._addr_bits) - 1)
                
                offset = self._translate_address(addr)
                if offset < self._size:
                    value = self._data[offset]
                    addr = (addr + 1) % self._size
                    return value
        
        elif self._command_state == 3:
            if len(self._command_buffer) >= 2:
                addr_bytes = self._command_buffer[-2:]
                addr = ((addr_bytes[0] << 8) | addr_bytes[1]) & ((1 << self._addr_bits) - 1)
                
                if len(self._command_buffer) >= 3:
                    data_byte = self._command_buffer[-1]
                    offset = self._translate_address(addr)
                    if offset < self._size:
                        self._data[offset] = data_byte
                        self._dirty = True
        
        return None
    
    def read_id(self) -> int:
        return 0x00
    
    def get_status(self) -> int:
        status = 0x00
        if self._write_enabled:
            status |= self.STATUS_WEL
        return status
    
    def enable_write(self, enabled: bool = True) -> None:
        self._write_enabled = enabled
    
    def load_from_file(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            
            if len(data) == self.EEPROM16K_SIZE:
                self._data = bytearray(data)
                self._size = self.EEPROM16K_SIZE
                self._is_16k = True
                self._addr_bits = self.EEPROM16K_ADDR_BITS
            elif len(data) == self.EEPROM4K_SIZE:
                self._data = bytearray(data)
                self._size = self.EEPROM4K_SIZE
                self._is_16k = False
                self._addr_bits = self.EEPROM4K_ADDR_BITS
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


def create_eeprom_save(size: str = "4K") -> EepromSave:
    if size == "16K":
        return EepromSave(EepromSave.EEPROM16K_SIZE)
    return EepromSave(EepromSave.EEPROM4K_SIZE)