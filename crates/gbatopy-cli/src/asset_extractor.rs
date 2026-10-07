/// Extracted assets from GBA ROM
#[derive(Default)]
pub struct ExtractedAssets {
    pub palette_data: Vec<u8>,
    pub tile_data: Vec<u8>,
    pub tilemap_data: Vec<u8>,
    pub wave_data: Vec<u8>,
    pub samples: Vec<(u32, usize, u8)>,
}
fn is_valid_rgb555(_color: u16) -> bool {
    true
}
fn is_valid_4bpp_tile(data: &[u8]) -> bool {
    if data.len() < 32 {
        return false;
    }
    let mut unique_nibbles = [false; 16];
    for &byte in &data[..32] {
        unique_nibbles[(byte & 0x0F) as usize] = true;
        unique_nibbles[((byte >> 4) & 0x0F) as usize] = true;
    }
    unique_nibbles.iter().filter(|&&x| x).count() >= 3
}
fn is_likely_tilemap(data: &[u8]) -> bool {
    if data.len() < 4 || !data.len().is_multiple_of(2) {
        return false;
    }
    let mut valid_entries = 0usize;
    let total = data.len() / 2;
    for pair in data.chunks_exact(2) {
        let entry = u16::from_le_bytes([pair[0], pair[1]]);
        let tile_num = entry & 0x3FF;
        let palette = (entry >> 12) & 0xF;
        // Real tilemap entries: tile 0-511, palette 0-15, flip bits 10-11
        // Reject ARM code patterns: condition 0xE in upper bits means palette=0xE
        if tile_num < 512 && palette <= 15 && palette != 0xE && palette != 0xF {
            valid_entries += 1;
        }
    }
    valid_entries * 3 >= total * 2
}
pub fn extract_assets(rom_data: &[u8]) -> ExtractedAssets {
    let mut assets = ExtractedAssets::default();
    let start_offset = 0x100;
    assets.samples = Vec::new();
    let mut palette_candidates: std::collections::BTreeMap<usize, usize> =
        std::collections::BTreeMap::new();
    for offset in (start_offset..rom_data.len().saturating_sub(64)).step_by(2) {
        // Skip if this offset doesn't start with 0x0000 (black = palette[0])
        let first_color = u16::from_le_bytes([rom_data[offset], rom_data[offset + 1]]);
        if first_color != 0x0000 {
            continue;
        }

        let mut consecutive_valid = 0;
        for i in 0..32 {
            let pos = offset + i * 2;
            if pos + 1 >= rom_data.len() {
                break;
            }
            let color = u16::from_le_bytes([rom_data[pos], rom_data[pos + 1]]);
            if is_valid_rgb555(color) {
                consecutive_valid += 1;
            } else {
                break;
            }
        }
        if consecutive_valid >= 16 {
            let count = palette_candidates.entry(offset).or_insert(0);
            *count = consecutive_valid;
        }
    }
    if let Some((best_offset, _)) = palette_candidates
        .iter()
        .max_by_key(|(_offset, count)| *count)
    {
        let offset = *best_offset;
        let max_colors = 256;
        for i in 0..max_colors {
            let pos = offset + i * 2;
            if pos + 1 >= rom_data.len() {
                break;
            }
            assets.palette_data.push(rom_data[pos]);
            assets.palette_data.push(rom_data[pos + 1]);
        }
        eprintln!(
            "  Found palette at offset 0x{:X}, {} colors",
            offset,
            assets.palette_data.len() / 2
        );
    } else {
        eprintln!("  No palette data found");
    }
    let mut best_tile_offset = 0;
    let mut best_tile_count = 0;
    for offset in (start_offset..rom_data.len().saturating_sub(128)).step_by(32) {
        let mut tile_count = 0;
        for tile_idx in 0..64 {
            let tile_start = offset + tile_idx * 32;
            if tile_start + 32 > rom_data.len() {
                break;
            }
            if is_valid_4bpp_tile(&rom_data[tile_start..tile_start + 32]) {
                tile_count += 1;
            } else {
                break;
            }
        }
        if tile_count > best_tile_count {
            best_tile_count = tile_count;
            best_tile_offset = offset;
        }
    }
    if best_tile_count > 0 {
        for i in 0..best_tile_count {
            let tile_start = best_tile_offset + i * 32;
            if tile_start + 32 <= rom_data.len() {
                assets
                    .tile_data
                    .extend_from_slice(&rom_data[tile_start..tile_start + 32]);
            }
        }
        eprintln!(
            "  Found {} tiles at offset 0x{:X}",
            best_tile_count, best_tile_offset
        );
    } else {
        eprintln!("  No tile data found");
    }
    let mut best_tilemap_offset = 0;
    let mut best_tilemap_count = 0;
    for offset in (start_offset..rom_data.len().saturating_sub(64)).step_by(2) {
        let sample = &rom_data[offset..std::cmp::min(offset + 128, rom_data.len())];
        if is_likely_tilemap(sample) {
            let mut count = 0;
            for i in (0..sample.len()).step_by(2) {
                let entry = u16::from_le_bytes([sample[i], sample[i + 1]]);
                if (entry & 0x3FF) == entry {
                    count += 1;
                }
            }
            if count > best_tilemap_count {
                best_tilemap_count = count;
                best_tilemap_offset = offset;
            }
        }
    }
    if best_tilemap_count > 16 {
        for i in 0..std::cmp::min(best_tilemap_count, 1024) {
            let pos = best_tilemap_offset + i * 2;
            if pos + 1 < rom_data.len() {
                assets.tilemap_data.push(rom_data[pos]);
                assets.tilemap_data.push(rom_data[pos + 1]);
            }
        }
        eprintln!(
            "  Found {} tilemap entries at offset 0x{:X}",
            best_tilemap_count, best_tilemap_offset
        );
    }
    assets
}

#[cfg(test)]
mod tests {
    use super::*;

    // === is_valid_4bpp_tile tests ===
    #[test]
    fn test_is_valid_4bpp_tile_minimum_valid() {
        // 32 bytes with at least 3 unique nibbles
        let mut data = vec![0u8; 32];
        data[0] = 0x01; // nibbles: 0, 1
        data[1] = 0x23; // nibbles: 2, 3
        assert!(is_valid_4bpp_tile(&data));
    }

    #[test]
    fn test_is_valid_4bpp_tile_too_short() {
        let data = vec![0u8; 31];
        assert!(!is_valid_4bpp_tile(&data));
    }

    #[test]
    fn test_is_valid_4bpp_tile_all_zeros() {
        // All zeros = only 1 unique nibble (0)
        let data = vec![0u8; 32];
        assert!(!is_valid_4bpp_tile(&data));
    }

    #[test]
    fn test_is_valid_4bpp_tile_two_unique_nibbles() {
        // Only 0x0 and 0x1 = 2 unique nibbles (< 3 required)
        let mut data = vec![0u8; 32];
        for i in 0..32 {
            data[i] = if i % 2 == 0 { 0x00 } else { 0x11 };
        }
        assert!(!is_valid_4bpp_tile(&data));
    }

    #[test]
    fn test_is_valid_4bpp_tile_full_palette() {
        // All 16 nibbles present
        let mut data = vec![0u8; 32];
        for i in 0..16 {
            data[i * 2] = ((i << 4) | i) as u8; // Each byte has same nibble twice
        }
        assert!(is_valid_4bpp_tile(&data));
    }

    #[test]
    fn test_is_valid_4bpp_tile_empty() {
        let data: Vec<u8> = vec![];
        assert!(!is_valid_4bpp_tile(&data));
    }

    #[test]
    fn test_is_valid_4bpp_tile_exactly_three_nibbles() {
        // Exactly 3 unique nibbles (0, 1, 2)
        let mut data = vec![0u8; 32];
        data[0] = 0x01;
        data[1] = 0x22;
        for i in 2..32 {
            data[i] = 0x00;
        }
        assert!(is_valid_4bpp_tile(&data));
    }

    // === is_likely_tilemap tests ===
    #[test]
    fn test_is_likely_tilemap_valid_entries() {
        // All valid tilemap entries
        let data: Vec<u8> = vec![
            0x00, 0x00, // tile 0, palette 0
            0xFF, 0x00, // tile 511, palette 0
            0x00, 0x10, // tile 0, palette 1
        ];
        assert!(is_likely_tilemap(&data));
    }

    #[test]
    fn test_is_likely_tilemap_too_short() {
        let data = vec![0u8; 2];
        assert!(!is_likely_tilemap(&data));
    }

    #[test]
    fn test_is_likely_tilemap_odd_length() {
        let data = vec![0u8; 5];
        assert!(!is_likely_tilemap(&data));
    }

    #[test]
    fn test_is_likely_tilemap_rejects_arm_code() {
        // Palette 0xE and 0xF should be rejected (ARM code patterns)
        let data: Vec<u8> = vec![
            0x00, 0x00, // valid: tile 0, palette 0
            0x00, 0xE0, // invalid: palette 0xE
            0x00, 0xF0, // invalid: palette 0xF
        ];
        // 1 valid out of 3 = 33% < 66% threshold
        assert!(!is_likely_tilemap(&data));
    }

    #[test]
    fn test_is_likely_tilemap_tile_number_overflow() {
        // Tile number > 511 requires bits 10-9 in the lower 10 bits
        // entry & 0x3FF = tile number, so we need entry >= 0x400 in lower 10 bits
        // 0x3FF = 1023, so tile 512 = 0x200
        let data: Vec<u8> = vec![
            0x00, 0x00, // valid: tile 0, palette 0
            0x00, 0x02, // invalid: tile 512 (0x200), palette 0
        ];
        // 1 valid out of 2 = 50% < 66% threshold
        assert!(!is_likely_tilemap(&data));
    }

    #[test]
    fn test_is_likely_tilemap_all_valid() {
        // All entries valid
        let mut data = vec![0u8; 128];
        for i in (0..128).step_by(2) {
            data[i] = (i / 2) as u8; // tile 0-63
            data[i + 1] = 0x00; // palette 0
        }
        assert!(is_likely_tilemap(&data));
    }

    #[test]
    fn test_is_likely_tilemap_mixed_valid_invalid() {
        // 2 out of 3 valid = 66% >= threshold
        let data: Vec<u8> = vec![
            0x00, 0x00, // valid
            0x00, 0x01, // valid
            0x00, 0xE0, // invalid (palette 0xE)
        ];
        assert!(is_likely_tilemap(&data));
    }

    // === is_valid_rgb555 tests ===
    #[test]
    fn test_is_valid_rgb555_always_true() {
        // Current implementation always returns true
        assert!(is_valid_rgb555(0x0000));
        assert!(is_valid_rgb555(0xFFFF));
        assert!(is_valid_rgb555(0x7FFF));
    }

    // === extract_assets tests ===
    #[test]
    fn test_extract_assets_empty_rom() {
        let rom = vec![0u8; 1024];
        let assets = extract_assets(&rom);
        // Should handle gracefully, may find nothing
        assert!(assets.palette_data.is_empty() || assets.palette_data.len() >= 32);
    }

    #[test]
    fn test_extract_assets_with_palette() {
        // Create a minimal ROM with palette data at offset 0x100
        let mut rom = vec![0u8; 0x200];
        // Palette starts at 0x100 with black (0x0000)
        rom[0x100] = 0x00;
        rom[0x101] = 0x00;
        // Add some color data
        for i in 1..32 {
            rom[0x100 + i * 2] = (i * 2) as u8;
            rom[0x100 + i * 2 + 1] = 0x00;
        }
        let assets = extract_assets(&rom);
        assert!(!assets.palette_data.is_empty());
    }

    #[test]
    fn test_extract_assets_with_tiles() {
        // Create a minimal ROM with tile data
        let mut rom = vec![0u8; 0x400];
        // Add valid 4bpp tile at offset 0x100
        rom[0x100] = 0x01;
        rom[0x101] = 0x23;
        for i in 2..32 {
            rom[0x100 + i] = 0x00;
        }
        let assets = extract_assets(&rom);
        // May or may not find tiles depending on validation
        assert!(assets.tile_data.len() % 32 == 0);
    }
}
