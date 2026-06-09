use crate::error::Error;
use crate::Result;

/// GBA ROM header structure
/// See: https://problemkaputt.de/gbatek.htm#gbaheader
pub struct RomHeader {
    /// Game title (12 bytes, ASCII)
    pub game_title: String,
    /// Game code (4 bytes, ASCII)
    pub game_code: String,
    /// Maker code (2 bytes, ASCII)
    pub maker_code: String,
    /// Unit code (0 = standard GBA cartridge)
    pub unit_code: u8,
    /// Device size in powers of 2 (e.g., 0x18 = 2^24 bytes = 16MB)
    pub device_size: u8,
    /// Reserved bytes (107 bytes)
    pub reserved: [u8; 107],
    /// Nintendo logo (252 bytes, must match exactly)
    pub logo: [u8; 252],
    /// Logo checksum (2 bytes)
    pub logo_checksum: u16,
    /// Header checksum (2 bytes)
    pub header_checksum: u16,
    /// Entry point (4 bytes, ARM or Thumb address)
    pub entry_point: u32,
}

impl RomHeader {
    /// Parse GBA ROM header from raw ROM data
    pub fn parse(rom: &[u8]) -> Result<Self> {
        if rom.len() < 0x180 {
            return Err(Error::InvalidRom("ROM too small for header".to_string()));
        }

        // Extract game title (12 bytes at offset 0x00)
        let game_title = String::from_utf8_lossy(&rom[0x00..0x0C]).trim_end_matches('\0').to_string();
        
        // Extract game code (4 bytes at offset 0x0C)
        let game_code = String::from_utf8_lossy(&rom[0x0C..0x10]).trim_end_matches('\0').to_string();
        
        // Extract maker code (2 bytes at offset 0x10)
        let maker_code = String::from_utf8_lossy(&rom[0x10..0x12]).trim_end_matches('\0').to_string();
        
        // Unit code (1 byte at offset 0x12)
        let unit_code = rom[0x12];
        
        // Reserved (1 byte at offset 0x13)
        let _reserved1 = rom[0x13];
        
        // Device size (1 byte at offset 0x14)
        let device_size = rom[0x14];
        
        // Reserved (107 bytes at offset 0x15)
        let mut reserved = [0u8; 107];
        reserved.copy_from_slice(&rom[0x15..0x80]);
        
        // Logo (252 bytes at offset 0x80)
        let mut logo = [0u8; 252];
        logo.copy_from_slice(&rom[0x80..0x17C]);
        
        // Logo checksum (2 bytes at offset 0x17C)
        let logo_checksum = u16::from_le_bytes([rom[0x17C], rom[0x17D]]);
        
        // Header checksum (2 bytes at offset 0x17E)
        let header_checksum = u16::from_le_bytes([rom[0x17E], rom[0x17F]]);
        
        // Entry point (4 bytes at offset 0x180)
        let entry_point = u32::from_le_bytes([rom[0x180], rom[0x181], rom[0x182], rom[0x183]]);

        Ok(Self {
            game_title,
            game_code,
            maker_code,
            unit_code,
            device_size,
            reserved,
            logo,
            logo_checksum,
            header_checksum,
            entry_point,
        })
    }

    /// Get the actual entry point address (relative to ROM base 0x08000000)
    pub fn get_entry_address(&self) -> u32 {
        // Entry point is already an absolute address (0x08000000 + offset)
        self.entry_point
    }

    /// Check if entry point is Thumb mode (bit 0 set)
    pub fn is_thumb_entry(&self) -> bool {
        self.entry_point & 0x1 != 0
    }

    /// Get ROM size from device_size field
    pub fn get_rom_size(&self) -> u32 {
        1 << self.device_size
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_stripes_header() {
        // Read stripes.gba header
        let rom = std::fs::read("test_roms/roms/stripes.gba").unwrap();
        let header = RomHeader::parse(&rom).unwrap();
        
        assert_eq!(header.game_title, "STRIPES");
        assert_eq!(header.entry_point, 0x08000000);
        assert!(!header.is_thumb_entry());
    }
}

/// Convenience function to parse ROM header and return entry point
pub fn parse_rom_header(rom: &[u8]) -> Result<RomHeader> {
    RomHeader::parse(rom)
}
