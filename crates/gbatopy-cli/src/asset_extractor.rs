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
