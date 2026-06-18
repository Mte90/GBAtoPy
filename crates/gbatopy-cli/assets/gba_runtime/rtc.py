"""
Real-Time Clock (RTC) support for GBAtoPy.

Implements the S-3511A RTC chip used in Pokemon Gold/Silver, Mario Artist, and other GBA games.
3-wire serial interface: SCK (clock), SI (serial in), SO (serial out).

RTC Registers:
- Status 1 (0x00): Control register
- Status 2 (0x02): Flag register  
- Time (0x04): Seconds, Minutes, Hours
- Date (0x08): Day, Month, Year

Commands:
- 0x6E: Read status register 1
- 0x6A: Read status register 2
- 0x66: Read time data (seconds/minutes/hours)
- 0x62: Read date data (day/month/year)
- 0x80: Write time data
- 0x82: Write date data
- 0xA0: Write status register
"""

import json
import os
import time
from datetime import datetime
from typing import Optional


class RTC:
    """Real-Time Clock implementation for GBA games."""
    
    # MMIO register addresses
    REG_RTC_SI = 0x04000134  # Serial input data
    REG_RTC_SO = 0x04000136  # Serial output data  
    REG_RTC_SCK = 0x04000138  # Serial clock
    REG_RTC_CS = 0x0400013C  # Chip select
    
    # RTC commands
    CMD_READ_STATUS1 = 0x6E
    CMD_READ_STATUS2 = 0x6A
    CMD_READ_TIME = 0x66
    CMD_READ_DATE = 0x62
    CMD_WRITE_TIME = 0x80
    CMD_WRITE_DATE = 0x82
    CMD_WRITE_STATUS = 0xA0
    
    # Status register bits
    STATUS1_24H = 0x40  # 24-hour mode
    STATUS1_POWER = 0x20  # Power on
    STATUS1_RESET = 0x10  # Reset
    STATUS1_STOP = 0x08  # Stop oscillator
    
    def __init__(self, memory, state_file: str = "rtc_state.json"):
        self.memory = memory
        self.state_file = state_file
        
        # RTC state
        self.seconds = 0
        self.minutes = 0
        self.hours = 0
        self.day = 1
        self.month = 1
        self.year = 0  # 00-99 (2000-2099)
        
        # Status registers
        self.status1 = self.STATUS1_POWER | self.STATUS1_24H
        self.status2 = 0x00
        
        # Serial communication state
        self.bit_count = 0
        self.command = 0
        self.data_buffer = 0
        self.transfer_count = 0
        self.current_operation = None  # 'read' or 'write'
        self.read_data = 0
        
        # Base time for calculating elapsed time (stored as offset from epoch)
        self.base_timestamp: float = 0.0
        self.base_realtime: float = 0.0
        self.so_value: int = 0
        
        # Load persisted state
        self._load_state()
        
        # Register MMIO handlers
        self._register_mmio()
    
    def _register_mmio(self):
        """Register RTC MMIO handlers with memory system."""
        self.memory.register_mmio_read(self.REG_RTC_SI - 0x04000000, self._read_si)
        self.memory.register_mmio_read(self.REG_RTC_SO - 0x04000000, self._read_so)
        self.memory.register_mmio_read(self.REG_RTC_SCK - 0x04000000, self._read_sck)
        self.memory.register_mmio_read(self.REG_RTC_CS - 0x04000000, self._read_cs)
        
        self.memory.register_mmio_write(self.REG_RTC_SI - 0x04000000, self._write_si)
        self.memory.register_mmio_write(self.REG_RTC_SO - 0x04000000, self._write_so)
        self.memory.register_mmio_write(self.REG_RTC_SCK - 0x04000000, self._write_sck)
        self.memory.register_mmio_write(self.REG_RTC_CS - 0x04000000, self._write_cs)
    
    def _read_si(self, addr: int) -> int:
        """Read from SI register."""
        return 0
    
    def _read_so(self, addr: int) -> int:
        """Read from SO register - returns serial output data."""
        if self.bit_count > 0 and self.bit_count <= 8:
            # Return the MSB of read_data
            return (self.read_data >> (8 - self.bit_count)) & 1
        return 0
    
    def _read_sck(self, addr: int) -> int:
        """Read from SCK register."""
        return 0
    
    def _read_cs(self, addr: int) -> int:
        """Read from CS register."""
        return 0
    
    def _write_si(self, addr: int, value: int):
        """Write to SI register - serial input."""
        si_bit = value & 1
        
        if self.bit_count == 0:
            # First bit of command
            self.command = si_bit << 7
            self.bit_count = 1
        elif self.bit_count < 8:
            # Continue building command
            self.command |= si_bit << (7 - self.bit_count)
            self.bit_count += 1
            
            if self.bit_count == 8:
                self._process_command()
    
    def _write_so(self, addr: int, value: int):
        """Write to SO register - no operation (SO is output only)."""
        # SO is a read-only output pin, writes are ignored
        # But we track the value for debugging/logging purposes
        self.so_value = value
    
    def _write_sck(self, addr: int, value: int):
        """Write to SCK register - clock pulse."""
        # SCK rising edge triggers data transfer
        if value & 1:
            # Rising edge - process data
            if self.bit_count > 0:
                self._clock_tick()
    
    def _write_cs(self, addr: int, value: int):
        """Write to CS register - chip select."""
        if value & 1:
            # CS high - reset transfer
            self._reset_transfer()
    
    def _clock_tick(self):
        """Process a clock tick for data transfer."""
        if self.current_operation == 'read' and self.transfer_count < 8:
            # Shift read_data left and add 0 (SO is pulled high internally)
            self.read_data = (self.read_data << 1) & 0xFF
            self.transfer_count += 1
        elif self.current_operation == 'write' and self.transfer_count < 8:
            # Collect write data - SI bit is already in self.command LSB during write
            # We need to read the SI bit from the SI register
            si_bit = (self.memory.read_u16(self.REG_RTC_SI - 0x04000000) & 1)
            self.data_buffer = (self.data_buffer << 1) | si_bit
            self.transfer_count += 1
            
            # Check if we've received a complete byte
            if self.transfer_count == 8:
                self._handle_write_byte()
    
    def _process_command(self):
        """Process the received RTC command."""
        cmd = self.command
        
        if cmd == self.CMD_READ_STATUS1:
            self.read_data = self.status1
            self.current_operation = 'read'
            self.transfer_count = 0
        elif cmd == self.CMD_READ_STATUS2:
            self.read_data = self.status2
            self.current_operation = 'read'
            self.transfer_count = 0
        elif cmd == self.CMD_READ_TIME:
            # Pack time: seconds, minutes, hours (BCD format)
            self.read_data = self._pack_time()
            self.current_operation = 'read'
            self.transfer_count = 0
        elif cmd == self.CMD_READ_DATE:
            # Pack date: day, month, year (BCD format)
            self.read_data = self._pack_date()
            self.current_operation = 'read'
            self.transfer_count = 0
        elif (cmd & 0xF0) == self.CMD_WRITE_TIME:
            # Write time command - prepare to receive 3 bytes (seconds, minutes, hours)
            self.current_operation = 'write'
            self.data_buffer = 0
            self.transfer_count = 0
            self.write_buffer = []
            self.write_command = cmd
        elif (cmd & 0xF0) == self.CMD_WRITE_DATE:
            # Write date command - prepare to receive 3 bytes (day, month, year)
            self.current_operation = 'write'
            self.data_buffer = 0
            self.transfer_count = 0
            self.write_buffer = []
            self.write_command = cmd
        elif cmd == self.CMD_WRITE_STATUS:
            # Write status register - receive 1 byte
            self.current_operation = 'write'
            self.data_buffer = 0
            self.transfer_count = 0
            self.write_buffer = []
            self.write_command = cmd
        else:
            # Unknown command - reset
            self._reset_transfer()
    
    def _pack_time(self) -> int:
        """Pack time data into byte (seconds | minutes | hours in BCD)."""
        sec_bcd = self._int_to_bcd(self.seconds)
        min_bcd = self._int_to_bcd(self.minutes)
        hour_bcd = self._int_to_bcd(self.hours)
        return ((hour_bcd & 0x3F) << 8) | ((min_bcd & 0x7F) << 4) | (sec_bcd & 0x7F)
    
    def _pack_date(self) -> int:
        """Pack date data into byte (day | month | year in BCD)."""
        day_bcd = self._int_to_bcd(self.day)
        month_bcd = self._int_to_bcd(self.month)
        year_bcd = self._int_to_bcd(self.year)
        return ((year_bcd & 0xFF) << 8) | ((month_bcd & 0x1F) << 4) | (day_bcd & 0x3F)
    
    def _unpack_time(self, data: int):
        """Unpack time data from byte."""
        self.seconds = self._bcd_to_int(data & 0x7F)
        self.minutes = self._bcd_to_int((data >> 4) & 0x7F)
        self.hours = self._bcd_to_int((data >> 8) & 0x3F)
    
    def _unpack_date(self, data: int):
        """Unpack date data from byte."""
        self.day = self._bcd_to_int(data & 0x3F)
        self.month = self._bcd_to_int((data >> 4) & 0x1F)
        self.year = self._bcd_to_int((data >> 8) & 0xFF)
    
    def _int_to_bcd(self, value: int) -> int:
        """Convert integer to BCD format."""
        tens = value // 10
        ones = value % 10
        return (tens << 4) | ones
    
    def _bcd_to_int(self, bcd: int) -> int:
        """Convert BCD to integer."""
        tens = (bcd >> 4) & 0x0F
        ones = bcd & 0x0F
        return tens * 10 + ones
    
    def _reset_transfer(self):
        """Reset transfer state machine."""
        self.bit_count = 0
        self.command = 0
        self.data_buffer = 0
        self.transfer_count = 0
        self.current_operation = None
        self.read_data = 0
        self.write_buffer = []
        self.write_command = 0
    
    def _is_leap_year(self, year: int) -> bool:
        """Check if a year is a leap year."""
        full_year = 2000 + year
        if full_year % 400 == 0:
            return True
        if full_year % 100 == 0:
            return False
        return full_year % 4 == 0
    
    def _get_days_in_month(self, month: int, year: int) -> int:
        """Get number of days in a given month."""
        days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        if month == 2 and self._is_leap_year(year):
            return 29
        return days[month - 1]
    
    def update_time(self):
        """Update RTC time based on elapsed real time."""
        if self.base_timestamp == 0.0:
            # First call - initialize
            self.base_timestamp = time.time()
            self.base_realtime = time.time()
            self._sync_from_system()
            return
        
        # Calculate elapsed time since base
        current_time = time.time()
        elapsed = current_time - self.base_realtime
        
        if elapsed > 0:
            # Add elapsed time to stored timestamp
            self.base_timestamp += elapsed
            self.base_realtime = current_time
            self._sync_from_timestamp()
    
    def _sync_from_system(self):
        """Sync RTC time from system time."""
        now = datetime.now()
        self.seconds = now.second
        self.minutes = now.minute
        self.hours = now.hour
        self.day = now.day
        self.month = now.month
        self.year = now.year % 100
        
        # Store current system time as base
        self.base_timestamp = now.timestamp()
        self.base_realtime = time.time()
    
    def _sync_from_timestamp(self):
        """Sync RTC time from stored timestamp."""
        dt = datetime.fromtimestamp(self.base_timestamp)
        self.seconds = dt.second
        self.minutes = dt.minute
        self.hours = dt.hour
        self.day = dt.day
        self.month = dt.month
        self.year = dt.year % 100
    
    def _handle_write_byte(self):
        """Handle a complete byte received during write operation."""
        # Store the byte in write buffer
        self.write_buffer.append(self.data_buffer)
        
        # Determine how many bytes we need based on command
        if self.write_command == self.CMD_WRITE_STATUS:
            # Status register: 1 byte
            if len(self.write_buffer) >= 1:
                self._apply_write_status()
        elif self.write_command == self.CMD_WRITE_TIME:
            # Time: 3 bytes (seconds, minutes, hours)
            if len(self.write_buffer) >= 3:
                self._apply_write_time()
        elif self.write_command == self.CMD_WRITE_DATE:
            # Date: 3 bytes (day, month, year)
            if len(self.write_buffer) >= 3:
                self._apply_write_date()
        
        # Reset for next byte
        self.data_buffer = 0
        self.transfer_count = 0
    
    def _apply_write_status(self):
        """Apply written status register value."""
        if len(self.write_buffer) >= 1:
            status = self.write_buffer[0]
            # Update status1 register
            self.status1 = status
            
            # Handle STOP bit (bit 3)
            if status & self.STATUS1_STOP:
                # Clock stopped - don't update time
                pass
            else:
                # Clock running - time updates normally
                pass
            
            # Handle RESET bit (bit 4)
            if status & self.STATUS1_RESET:
                # Reset time to initial values
                self.seconds = 0
                self.minutes = 0
                self.hours = 0
                self.day = 1
                self.month = 1
                self.year = 0
                # Clear reset bit after reset
                self.status1 &= ~self.STATUS1_RESET
    
    def _apply_write_time(self):
        """Apply written time values."""
        if len(self.write_buffer) >= 3:
            # Bytes are: seconds, minutes, hours
            self._unpack_time(self.write_buffer[0])
            self._unpack_time((self.write_buffer[1] << 8) | self.write_buffer[0])  # Reuse unpack logic
            
            # Actually unpack properly
            self.seconds = self._bcd_to_int(self.write_buffer[0] & 0x7F)
            self.minutes = self._bcd_to_int(self.write_buffer[1] & 0x7F)
            self.hours = self._bcd_to_int(self.write_buffer[2] & 0x3F)
            
            # Reset base timestamp to match new time
            now = time.time()
            dt = datetime.now()
            dt = dt.replace(hour=self.hours, minute=self.minutes, second=self.seconds, microsecond=0)
            self.base_timestamp = dt.timestamp()
            self.base_realtime = now
    
    def _apply_write_date(self):
        """Apply written date values."""
        if len(self.write_buffer) >= 3:
            # Bytes are: day, month, year
            self.day = self._bcd_to_int(self.write_buffer[0] & 0x3F)
            self.month = self._bcd_to_int(self.write_buffer[1] & 0x1F)
            self.year = self._bcd_to_int(self.write_buffer[2] & 0xFF)
            
            # Reset base timestamp to match new date
            now = time.time()
            dt = datetime.now()
            dt = dt.replace(year=2000 + self.year, month=self.month, day=self.day, microsecond=0)
            self.base_timestamp = dt.timestamp()
            self.base_realtime = now
    
    def _load_state(self):
        """Load RTC state from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.base_timestamp = state.get('base_timestamp', 0.0)
                    self.seconds = state.get('seconds', 0)
                    self.minutes = state.get('minutes', 0)
                    self.hours = state.get('hours', 0)
                    self.day = state.get('day', 1)
                    self.month = state.get('month', 1)
                    self.year = state.get('year', 0)
                    self.status1 = state.get('status1', self.STATUS1_POWER | self.STATUS1_24H)
                    self.status2 = state.get('status2', 0)
                    
                    # Sync from stored timestamp
                    if self.base_timestamp > 0:
                        self._sync_from_timestamp()
                    else:
                        self._sync_from_system()
            except (json.JSONDecodeError, IOError):
                self._sync_from_system()
        else:
            self._sync_from_system()
    
    def save_state(self):
        """Save RTC state to file."""
        # Update time before saving
        self.update_time()
        
        state = {
            'base_timestamp': self.base_timestamp,
            'seconds': self.seconds,
            'minutes': self.minutes,
            'hours': self.hours,
            'day': self.day,
            'month': self.month,
            'year': self.year,
            'status1': self.status1,
            'status2': self.status2
        }
        
        with open(self.state_file, 'w') as f:
            json.dump(state, f)
    
    def get_time_string(self) -> str:
        """Get current RTC time as string."""
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}"
    
    def get_date_string(self) -> str:
        """Get current RTC date as string."""
        return f"20{self.year:02d}-{self.month:02d}-{self.day:02d}"


def detect_rtc(rom_data: bytes) -> bool:
    """
    Auto-detect if ROM uses RTC.
    
    Checks for known RTC game identifiers in ROM header or game code.
    Common RTC games: Pokemon Gold/Silver, Mario Artist, Boktai, etc.
    """
    if rom_data is None or len(rom_data) < 0x100:
        return False
    
    # Check for known RTC game identifiers
    rtc_identifiers = [
        b'GOLD',      # Pokemon Gold
        b'SILVER',    # Pokemon Silver
        b'POKEMON',   # Pokemon (various)
        b'MARIO ARTIST',  # Mario Artist
        b'BOKTAI',    # Boktai
        b'KAGUYA',    # Kaguya
        b'MOON',      # Kaguya
    ]
    
    # Search in ROM header and game title area
    search_area = rom_data[:0x100000]  # Search first 1MB
    
    for identifier in rtc_identifiers:
        if identifier in search_area:
            return True
    
    # Check for RTC hardware detection code patterns
    # Games that use RTC typically access 0x04000134-0x0400013F
    # This is a heuristic check
    
    return False


def create_rtc(memory, rom_data: Optional[bytes] = None, state_file: str = "rtc_state.json") -> Optional[RTC]:
    """
    Create and initialize RTC if needed.
    
    Args:
        memory: Memory object for MMIO registration
        rom_data: ROM data for auto-detection
        state_file: Path to state file
        
    Returns:
        RTC instance if RTC detected or forced, None otherwise
    """
    if rom_data is not None and not detect_rtc(rom_data):
        return None
    
    return RTC(memory, state_file)