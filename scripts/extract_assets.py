#!/usr/bin/env python3
"""Dynamic asset extraction tool for GBAtoPy."""

import sys
from pathlib import Path


def is_valid_rgb555(color: int) -> bool:
    r = color & 0x1F
    g = (color >> 5) & 0x1F
    b = (color >> 10) & 0x1F
    return r <= 0x1F and g <= 0x1F and b <= 0x1F and (color & 0x8000) == 0


def is_valid_4bpp_tile(data: bytes) -> bool:
    if len(data) < 32:
        return False
    unique_nibbles = set()
    for byte in data:
        unique_nibbles.add(byte & 0x0F)
        unique_nibbles.add((byte >> 4) & 0x0F)
    return len(unique_nibbles) >= 3


def is_valid_8bpp_tile(data: bytes) -> bool:
    if len(data) < 64:
        return False
    return len(set(data)) >= 5


class AssetExtractor:
    def __init__(self, rom_data: bytes):
        self.rom = rom_data
    
    def scan_for_palette(self) -> bytes:
        for offset in range(0x100, len(self.rom) - 512, 2):
            valid = sum(1 for i in range(0, 512, 2) 
                       if is_valid_rgb555(self.rom[offset + i] | (self.rom[offset + i + 1] << 8)))
            if valid >= 204:
                return self.rom[offset:offset+512]
        return bytes(512)
    
    def scan_for_tiles(self) -> bytes:
        for offset in range(0x100, len(self.rom) - 32, 32):
            if is_valid_4bpp_tile(self.rom[offset:offset+32]):
                total = 0
                while offset + total + 32 <= len(self.rom) and is_valid_4bpp_tile(self.rom[offset+total:offset+total+32]):
                    total += 32
                if total >= 128:
                    return self.rom[offset:offset+total]
        
        for offset in range(0x100, len(self.rom) - 64, 64):
            if is_valid_8bpp_tile(self.rom[offset:offset+64]):
                total = 0
                while offset + total + 64 <= len(self.rom) and is_valid_8bpp_tile(self.rom[offset+total:offset+total+64]):
                    total += 64
                if total >= 256:
                    return self.rom[offset:offset+total]
        return bytes(1024)
    
    def scan_for_tilemap(self) -> bytes:
        for offset in range(0x100, len(self.rom) - 1024, 2):
            valid = 0
            total = 0
            while offset + total + 2 <= len(self.rom):
                entry = self.rom[offset + total] | (self.rom[offset + total + 1] << 8)
                if entry <= 1023:
                    valid += 1
                    total += 2
                else:
                    break
            if valid >= 512 and valid * 2 >= total * 0.8:
                return self.rom[offset:offset+total]
        return bytes(1024)
    
    def extract(self):
        print("Scanning ROM for assets...", file=sys.stderr)
        palette = self.scan_for_palette()
        tiles = self.scan_for_tiles()
        tilemap = self.scan_for_tilemap()
        print(f"  Palette: {len(palette)} bytes ({len(palette)//2} colors)", file=sys.stderr)
        print(f"  Tiles: {len(tiles)} bytes", file=sys.stderr)
        print(f"  Tilemap: {len(tilemap)} bytes", file=sys.stderr)
        return {'palette': palette, 'tiles': tiles, 'tilemap': tilemap}


def generate_python_output(assets: dict) -> str:
    lines = ["# === Extracted Assets ===", ""]
    
    lines.append("PALETTE_BG = bytearray([")
    for i in range(0, len(assets['palette']), 16):
        chunk = assets['palette'][i:i+16]
        lines.append("    " + ', '.join(f'{b:02x}' for b in chunk) + ",")
    lines.append("])")
    lines.append("")
    
    lines.append("TILES_4BPP = bytearray([")
    for i in range(0, len(assets['tiles']), 16):
        chunk = assets['tiles'][i:i+16]
        lines.append("    " + ', '.join(f'{b:02x}' for b in chunk) + ",")
    lines.append("])")
    lines.append("")
    
    lines.append("TILEMAP_BG0 = bytearray([")
    for i in range(0, len(assets['tilemap']), 16):
        chunk = assets['tilemap'][i:i+16]
        lines.append("    " + ', '.join(f'{b:02x}' for b in chunk) + ",")
    lines.append("])")
    lines.append("")
    
    return '\n'.join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_assets.py <rom.gba>", file=sys.stderr)
        sys.exit(1)
    
    rom_path = Path(sys.argv[1])
    if not rom_path.exists():
        print(f"ERROR: ROM not found: {rom_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(rom_path, 'rb') as f:
        rom_data = f.read()
    
    assets = AssetExtractor(rom_data).extract()
    print(generate_python_output(assets))


if __name__ == "__main__":
    main()
