"""
GBA SRAM (Save RAM) handling module.

SRAM provides persistent storage for GBA games, typically 32KB-128KB.
This module handles file-based persistence with auto-save on game exit.
"""

import os
import json
from typing import Optional


class SRAM:
    """GBA SRAM with file-based persistence."""

    DEFAULT_SIZE = 0x8000  # 32KB default
    SRAM_ADDR_START = 0x0E000000
    SRAM_ADDR_END = 0x0E01FFFF

    def __init__(self, size: int = DEFAULT_SIZE, save_file: Optional[str] = None):
        """
        Initialize SRAM.

        Args:
            size: SRAM size in bytes (32KB-128KB recommended)
            save_file: Path to save file (auto-generated if None)
        """
        self.size = size
        self.data = bytearray(size)
        self.save_file = save_file
        self._dirty = False

        # Generate save file from ROM name if not provided
        if self.save_file is None:
            self.save_file = self._generate_save_filename()

    def _generate_save_filename(self) -> str:
        """Generate save filename from ROM name."""
        if not self.save_file:
            raise ValueError("No ROM name available for auto-generation")
        
        base, _ = os.path.splitext(self.save_file)
        return f"{base}.sav"

    def load(self) -> bool:
        """
        Load SRAM from file.

        Returns:
            True if load successful, False otherwise
        """
        if not os.path.exists(self.save_file):
            return True  # No existing save is fine

        try:
            with open(self.save_file, "rb") as f:
                data = f.read()

            if len(data) != self.size:
                print(f"Warning: Save file size mismatch. Expected {self.size}, got {len(data)}")
                # Pad or truncate as needed
                data = data[:self.size]
                if len(data) < self.size:
                    data = data + bytes(self.size - len(data))

            self.data = bytearray(data)
            self._dirty = False
            return True
        except Exception as e:
            print(f"Warning: Failed to load save file: {e}")
            return False

    def save(self) -> bool:
        """
        Save SRAM to file.

        Returns:
            True if save successful, False otherwise
        """
        try:
            os.makedirs(os.path.dirname(self.save_file) or ".", exist_ok=True)
            with open(self.save_file, "wb") as f:
                f.write(self.data)
            self._dirty = False
            return True
        except Exception as e:
            print(f"Error: Failed to save save file: {e}")
            return False

    def mark_dirty(self):
        """Mark SRAM as dirty (needs save)."""
        self._dirty = True

    def is_dirty(self) -> bool:
        """Check if SRAM has unsaved changes."""
        return self._dirty

    def read_u8(self, addr: int) -> int:
        """Read 8-bit value from SRAM."""
        addr &= 0xFFFF
        return self.data[addr]

    def read_u16(self, addr: int) -> int:
        """Read 16-bit value from SRAM (little-endian)."""
        addr &= 0xFFFF
        return self.data[addr] | (self.data[addr + 1] << 8)

    def write_u8(self, addr: int, value: int):
        """Write 8-bit value to SRAM."""
        addr &= 0xFFFF
        value &= 0xFF
        self.data[addr] = value
        self._dirty = True

    def write_u16(self, addr: int, value: int):
        """Write 16-bit value to SRAM (little-endian)."""
        addr &= 0xFFFF
        value &= 0xFFFF
        self.data[addr] = value & 0xFF
        self.data[addr + 1] = (value >> 8) & 0xFF
        self._dirty = True

    def get_memory_view(self) -> memoryview:
        """Get memoryview for efficient bulk operations."""
        return memoryview(self.data)

    def save_state(self, state_file: str) -> bool:
        """
        Save complete SRAM state to a file.
        
        Args:
            state_file: Path to save state file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import json
            os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
            
            state = {
                "data": list(self.data),
                "size": self.size,
                "save_file": self.save_file
            }
            
            with open(state_file, "w") as f:
                json.dump(state, f)
            
            return True
        except Exception as e:
            print(f"Error: Failed to save state: {e}")
            return False

    def load_state(self, state_file: str) -> bool:
        """
        Load complete SRAM state from a file.
        
        Args:
            state_file: Path to load state file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import json
            
            if not os.path.exists(state_file):
                return False  # No state file is fine
            
            with open(state_file, "r") as f:
                state = json.load(f)
            
            self.size = state.get("size", self.size)
            self.data = bytearray(state.get("data", list(self.data)))
            self.save_file = state.get("save_file", self.save_file)
            self._dirty = False
            
            return True
        except Exception as e:
            print(f"Error: Failed to load state: {e}")
            return False
