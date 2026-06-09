/// Extracted assets from GBA ROM
#[derive(Default)]
pub struct ExtractedAssets {
    pub palette_data: Vec<u8>,
    pub tile_data: Vec<u8>,
    pub tilemap_data: Vec<u8>,
    pub wave_data: Vec<u8>,
    pub samples: Vec<(u32, usize, u8)>,
}
fn is_valid_rgb555(color: u16) -> bool {
    let r = color & 0x1F;
    let g = (color >> 5) & 0x1F;
    let b = (color >> 10) & 0x1F;
    r <= 0x1F && g <= 0x1F && b <= 0x1F && (color & 0x8000) == 0
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
    if data.len() < 4 || data.len() % 2 != 0 {
        return false;
    }
    let valid_entries = data
        .chunks_exact(2)
        .filter(|pair| {
            let entry = u16::from_le_bytes([pair[0], pair[1]]);
            (entry & 0x3FF) <= 1023
        })
        .count();
    valid_entries * 4 >= data.len() / 2
}
pub fn extract_assets(rom_data: &[u8]) -> ExtractedAssets {
    let mut assets = ExtractedAssets::default();
    let start_offset = 0x100;
    // Audio samples in IWRAM (0x03000000-0x03007FFF) at ROM offset 0x08000000+(IWRAM_OFFSET)
    let iwram_base = 0x03000000;
    let rom_base = 0x08000000;
    let sample_scan_start = (0x03007FFC - iwram_base) as usize + rom_base;
    let sample_scan_end = (0x03000000 - iwram_base) as usize + rom_base;
    assets.samples = Vec::new();
    let mut palette_candidates: std::collections::HashMap<usize, usize> =
        std::collections::HashMap::new();
    for offset in (start_offset..rom_data.len().saturating_sub(64)).step_by(2) {
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
        if consecutive_valid >= 8 {
            let count = palette_candidates.entry(offset).or_insert(0);
            *count = consecutive_valid;
        }
    }
    if let Some((best_offset, _)) = palette_candidates.iter().max_by_key(|(_, count)| *count) {
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
                if (entry & 0x3FF) <= 1023 {
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

    // Detect audio samples in IWRAM region (0x03007FFF to 0x03000000)
    eprintln!("  Scanning for audio samples in IWRAM...");
    let sample_region_end = sample_scan_end.min(rom_data.len());
    for sample_addr in (sample_region_end..=sample_scan_start).rev() {
        // GBA audio samples: up to 32 bytes total, 4-bit or 8-bit
        let max_samples = 32;
        if sample_addr + max_samples > rom_data.len() {
            continue;
        }

        let sample_data = &rom_data[sample_addr..sample_addr + max_samples];
        let mut detected = false;

        // Check if this looks like valid sample data (some non-zero bytes)
        let non_zero = sample_data.iter().filter(|&&b| b != 0).count();
        if non_zero > 0 && non_zero < max_samples {
            // Heuristic: sample bank starting point
            assets.samples.push((sample_addr as u32, max_samples, 0)); // format: 0 = 4-bit, 1 = 8-bit
            detected = true;
            break;
        }
    }

    if !assets.samples.is_empty() {
        eprintln!("  Found {} audio samples", assets.samples.len());
    } else {
        eprintln!("  No audio samples found");
    }

    assets
}
