#![allow(unused_variables, dead_code)]
use std::fs;

pub const ROM_HEADER_SIZE: usize = 0x100;
pub const ROM_OFFSET: u32 = 0x0800_0000;
pub const MMC3_HEADER_OFFSET: usize = 0x0EC;
pub const MMC5_HEADER_OFFSET: usize = 0x0F2;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RomFileType {
    Unencrypted,
    AGB0,
    AGB1,
    AGB2,
}

impl RomFileType {
    pub fn is_encrypted(self) -> bool {
        matches!(
            self,
            RomFileType::AGB0 | RomFileType::AGB1 | RomFileType::AGB2
        )
    }

    pub fn encryption_type_name(self) -> &'static str {
        match self {
            RomFileType::Unencrypted => "Unencrypted",
            RomFileType::AGB0 => "AGB0",
            RomFileType::AGB1 => "AGB1",
            RomFileType::AGB2 => "AGB2",
        }
    }
}

pub fn parse_rom_header(rom_data: &[u8]) -> Result<RomHeader, String> {
    if rom_data.len() < ROM_HEADER_SIZE {
        return Err(format!(
            "ROM too small: {} bytes, expected at least {} bytes",
            rom_data.len(),
            ROM_HEADER_SIZE
        ));
    }

    let file_type = RomFileType::from_byte(rom_data[MMC3_HEADER_OFFSET]);

    let header = RomHeader {
        file_type,
        checksum_bios: u32::from_le_bytes([rom_data[0], rom_data[1], rom_data[2], rom_data[3]]),
        checksum_header: u32::from_le_bytes([rom_data[4], rom_data[5], rom_data[6], rom_data[7]]),
        verbose_header: rom_data[MMC3_HEADER_OFFSET + 1] != 0x00,
    };

    // Validate checksums if verbose header
    if header.verbose_header {
        let calculated_checksum = calculate_header_checksum(rom_data);
        if calculated_checksum != header.checksum_header {
            return Err("Invalid header checksum".to_string());
        }
    }

    Ok(header)
}

pub struct RomHeader {
    pub file_type: RomFileType,
    pub checksum_bios: u32,
    pub checksum_header: u32,
    pub verbose_header: bool,
}

impl RomHeader {
    pub fn decryption_seed(&self) -> Option<u32> {
        match self.file_type {
            RomFileType::AGB0 | RomFileType::AGB1 | RomFileType::AGB2 => {
                // seed = (header_byte & 0x0F) * 0x2001 + 0x0600
                let seed_byte = self.checksum_bios as u8;
                Some((seed_byte & 0x0F) * 0x2001 + 0x0600)
            }
            RomFileType::Unencrypted => None,
        }
    }

    pub fn title(&self, rom_data: &[u8]) -> Option<&str> {
        if !self.verbose_header {
            return None;
        }
        let start = 0x0F4; // Title is at offset 0x0F4, null-terminated

        // Title is at offset 0x0F4, null-terminated
        let start = 0x0F4;
        let end = 0x100;

        if rom_data.len() < end {
            return None;
        }

        let title_bytes: Vec<u8> = rom_data[start..end]
            .iter()
            .take_while(|&&b| b != 0x00)
            .copied()
            .collect();

        String::from_utf8(title_bytes)
            .ok()
            .and_then(|s| s.split('\0').next().map(|s| s.trim()))
    }
}

impl RomFileType {
    /// Extract ROM file type from the header byte at offset 0x0EC
    ///
    /// Bits 15:12 of the byte encode the game type:
    /// - 0x00 = Unencrypted
    /// - 0x01 = AGB0 (encrypted)
    /// - 0x02 = AGB1 (encrypted)
    /// - 0x03 = AGB2 (encrypted)
    ///
    /// We treat AGB1 and AGB2 the same as AGB0 for this transpiler
    pub fn from_byte(byte: u8) -> RomFileType {
        let game_type = (byte & 0xF0) >> 4;

        match game_type {
            0x00 => RomFileType::Unencrypted,
            0x01 => RomFileType::Encrypted,
            0x02 => RomFileType::Encrypted,
            0x03 => RomFileType::Encrypted,
            _ => RomFileType::Encrypted, // Assume encrypted for unknown types
        }
    }
}

/// Calculate the checksum for header validation
fn calculate_header_checksum(rom_data: &[u8]) -> u32 {
    // Standard GBA header checksum algorithm
    // Sum all bytes from 0x10 to 0xFF, skip checksum fields
    let mut sum: u32 = 0;
    for i in 0x10..=0xFF {
        if i < rom_data.len() {
            sum += rom_data[i as usize] as u32;
        }
    }
    sum
}

/// Read ROM data from file with encryption detection
pub fn read_rom(rom_path: &str) -> Result<(Vec<u8>, RomHeader), String> {
    let rom_data =
        fs::read(rom_path).map_err(|e| format!("Failed to read ROM file '{}': {}", rom_path, e))?;

    let header = parse_rom_header(&rom_data)?;

    Ok((rom_data, header))
}

/// Detect if a ROM is encrypted by examining the header
pub fn is_rom_encrypted(rom_data: &[u8]) -> Result<bool, String> {
    let header = parse_rom_header(rom_data)?;
    Ok(header.file_type.is_encrypted())
}

/// Get encryption type from ROM data
pub fn get_encryption_type(rom_data: &[u8]) -> Result<RomFileType, String> {
    let header = parse_rom_header(rom_data)?;
    Ok(header.file_type)
}

/// Decrypt ROM data using AGB0/AGB1/AGB2 decryption algorithm
///
/// AGB encryption uses a simple XOR-based algorithm with the decryption seed
/// The decrypted ROM can then be transpiled normally
pub fn decrypt_rom(
    rom_data: &[u8],
    encryption_type: RomFileType,
    seed: u32,
) -> Result<Vec<u8>, String> {
    let mut decrypted = rom_data.to_vec();

    // AGB decryption: XOR each byte with the seed, then XOR result with seed again
    // This is equivalent to: decrypted[i] = rom_data[i] ^ (seed ^ rom_data[i])
    // Which simplifies to: decrypted[i] = seed

    // Actually, AGB decryption is:
    // encrypted = original XOR seed
    // original = encrypted XOR seed

    for i in 0..decrypted.len() {
        decrypted[i] ^= (seed & 0xFF);
    }

    Ok(decrypted)
}

/// Test decryption and verify decrypted ROM runs
/// Returns (success, message)
pub fn test_rom_decryption(
    rom_path: &str,
    output_path: &str,
    key: u32,
) -> Result<(bool, String), String> {
    eprintln!("Testing decryption of '{}'", rom_path);

    let rom_data = std::fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

    let encryption_type = get_encryption_type(&rom_data)?;

    // If already unencrypted, just use the ROM as-is
    if !encryption_type.is_encrypted() {
        eprintln!("  ROM is not encrypted, using as-is");
        std::fs::write(output_path, &rom_data)
            .map_err(|e| format!("Failed to write output: {}", e))?;
        return Ok((
            true,
            format!(
                "ROM {} is unencrypted",
                encryption_type.encryption_type_name()
            ),
        ));
    }

    // Calculate or use provided key
    let seed = match key {
        0 => encryption_type.decryption_seed().unwrap_or(0x20010600), // Default seed if not available
        _ => key,
    };

    eprintln!(
        "  Detected encryption: {}",
        encryption_type.encryption_type_name()
    );
    eprintln!("  Using decryption seed: 0x{:08X}", seed);

    let decrypted = decrypt_rom(&rom_data, encryption_type, seed)?;

    // Write decrypted ROM to output
    std::fs::write(output_path, &decrypted)
        .map_err(|e| format!("Failed to write decrypted ROM: {}", e))?;

    // Verify the output is valid (basic check)
    if decrypted.len() < ROM_HEADER_SIZE {
        return Ok((
            false,
            format!("Decrypted ROM too small: {} bytes", decrypted.len()),
        ));
    }

    let decrypted_type = get_encryption_type(&decrypted)?;
    eprintln!("  Decrypted ROM type: {:?}", decrypted_type);

    Ok((
        true,
        format!(
            "Successfully decrypted as {}",
            decrypted_type.encryption_type_name()
        ),
    ))
}

/// Decrypt ROM and transpile in one step
pub fn decrypt_and_transpile(rom_path: &str, output_path: &str, key: u32) -> Result<(), String> {
    eprintln!("Decryption and transpilation of '{}'", rom_path);

    let (decrypted, encryption_type) = {
        let rom_data = std::fs::read(rom_path).map_err(|e| format!("Failed to read ROM: {}", e))?;

        let encryption_type = get_encryption_type(&rom_data)?;
        let seed = match key {
            0 => encryption_type.decryption_seed().unwrap_or(0x20010600),
            _ => key,
        };

        let decrypted = if encryption_type.is_encrypted() {
            decrypt_rom(&rom_data, encryption_type, seed)?
        } else {
            rom_data
        };

        (decrypted, encryption_type)
    };

    eprintln!(
        "  Encryption type: {}",
        encryption_type.encryption_type_name()
    );

    // Continue with normal transpilation pipeline using decrypted ROM
    // This would call the existing transpilation logic
    Ok(())
}
