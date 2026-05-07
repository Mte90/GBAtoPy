#!/usr/bin/env python3
"""Oracle-guided asset extraction - monitors runtime VRAM/OAM writes during execution"""

import json
from typing import List, Dict, Set, Tuple
from pathlib import Path


class OracleAssetTracker:
    """Track asset writes during runtime execution via oracle traces"""

    def __init__(self):
        self.vram_tile_writes: Dict[int, bytes] = {}
        self.vram_palette_writes: Dict[int, bytes] = {}
        self.oam_writes: List[Dict] = []
        self.vram_tilemap_writes: Dict[int, bytes] = {}

        self.tile_write_addrs: Set[int] = set()
        self.palette_write_addrs: Set[int] = set()
        self.tilemap_write_addrs: Set[int] = set()

    def track_vram_write(self, addr: int, data: bytes, size: int):
        """Track a VRAM write - determine if it's tiles, palette, or tilemap"""

        # VRAM layout:
        # 0x06000000-0x06003FFF: Tile data (16KB)
        # 0x06004000-0x06007FFF: Tile data (16KB)
        # 0x06008000-0x0600BFFF: BG0/1 tilemaps
        # 0x0600C000-0x0600FFFF: BG2/3 tilemaps
        # 0x06010000-0x06017FFF: Bitmap modes framebuffer

        offset = addr - 0x06000000

        if offset < 0x8000:  # Tile data region
            self.tile_write_addrs.add(addr)
            self.vram_tile_writes[addr] = data[:size]

        elif offset >= 0x8000 and offset < 0x10000:  # Tilemap region
            self.tilemap_write_addrs.add(addr)
            self.vram_tilemap_writes[addr] = data[:size]

    def track_palette_write(self, addr: int, data: bytes, size: int):
        """Track a palette write"""
        # Palette RAM: 0x05000000-0x050003FF (512 colors)
        offset = addr - 0x05000000

        if 0 <= offset < 0x400:
            self.palette_write_addrs.add(addr)
            self.vram_palette_writes[addr] = data[:size]

    def track_oam_write(self, addr: int, data: bytes):
        """Track OAM (sprite) write"""
        # OAM: 0x07000000-0x070003FF
        offset = addr - 0x07000000

        if 0 <= offset < 0x400 and len(data) >= 8:
            # Parse sprite attributes
            attr0 = int.from_bytes(data[0:2], "little")
            attr1 = int.from_bytes(data[2:4], "little")
            attr2 = int.from_bytes(data[4:6], "little")

            sprite = {
                "addr": addr,
                "attr0": attr0,
                "attr1": attr1,
                "attr2": attr2,
                "y": attr0 & 0xFF,
                "x": attr1 & 0x1FF,
                "tile": attr2 & 0x3FF,
            }
            self.oam_writes.append(sprite)

    def load_oracle_trace(self, trace_path: str):
        """Load oracle trace JSON and extract asset writes"""
        with open(trace_path, "r") as f:
            trace = json.load(f)

        # Look for memory write events
        if "events" in trace:
            for event in trace["events"]:
                if event.get("type") == "memory_write":
                    addr = event.get("addr", 0)
                    data = bytes(event.get("data", []))
                    size = event.get("size", len(data))

                    # Categorize by address region
                    if 0x05000000 <= addr < 0x05000400:  # Palette
                        self.track_palette_write(addr, data, size)
                    elif 0x06000000 <= addr < 0x06018000:  # VRAM
                        self.track_vram_write(addr, data, size)
                    elif 0x07000000 <= addr < 0x07000400:  # OAM
                        self.track_oam_write(addr, data)

        print(f"Loaded oracle trace: {trace_path}")
        print(f"  Tile writes: {len(self.tile_write_addrs)}")
        print(f"  Palette writes: {len(self.palette_write_addrs)}")
        print(f"  Tilemap writes: {len(self.tilemap_write_addrs)}")
        print(f"  OAM writes: {len(self.oam_writes)}")

    def extract_assets_from_trace(self) -> Dict:
        """Extract complete asset data from tracked writes"""
        assets = {
            "tiles": [],
            "palettes": {
                "bg": [],
                "obj": [],
            },
            "tilemaps": {
                "bg0": [],
                "bg1": [],
                "bg2": [],
                "bg3": [],
            },
            "sprites": [],
        }

        # Extract palette data
        for addr in sorted(self.palette_write_addrs):
            data = self.vram_palette_writes[addr]
            # Convert BGR555 to RGB
            palette = []
            for i in range(0, len(data), 2):
                if i + 1 < len(data):
                    value = int.from_bytes(data[i : i + 2], "little")
                    blue = (value & 0x7C00) >> 10
                    green = (value & 0x03E0) >> 5
                    red = value & 0x001F
                    red = (red << 3) | (red >> 2)
                    green = (green << 3) | (green >> 2)
                    blue = (blue << 3) | (blue >> 2)
                    palette.append((red, green, blue))

            # Determine if BG or OBJ palette
            if addr < 0x05000200:
                assets["palettes"]["bg"].extend(palette)
            else:
                assets["palettes"]["obj"].extend(palette)

        # Extract tile data
        for addr in sorted(self.tile_write_addrs):
            data = self.vram_tile_writes.get(addr, b"")
            if len(data) >= 64:  # At least one 8x8 4bpp tile
                # Extract as 4bpp tile
                tile = []
                for y in range(8):
                    for byte_idx in range(4):
                        base = y * 8 + byte_idx * 4
                        if base + 3 < len(data):
                            for bit in range(4):
                                value = data[base + bit]
                                color_idx = (value >> (bit * 4)) & 0x0F
                                tile.append(color_idx)
                assets["tiles"].append(tile)

        # Extract OAM sprites
        for sprite in self.oam_writes:
            assets["sprites"].append(
                {
                    "x": sprite["x"],
                    "y": sprite["y"],
                    "tile": sprite["tile"],
                    "attr0": sprite["attr0"],
                    "attr1": sprite["attr1"],
                    "attr2": sprite["attr2"],
                }
            )

        return assets

    def generate_python_assets(self, output_path: str, assets: Dict):
        """Generate Python file with extracted assets"""
        with open(output_path, "w") as f:
            f.write("#!/usr/bin/env python3\n")
            f.write('"""Assets extracted via oracle-guided runtime tracking"""\n\n')

            # Write palette
            f.write("# Background Palette\n")
            f.write("PALETTE_BG = [\n")
            for color in assets["palettes"]["bg"][:256]:
                f.write(f"    {color},\n")
            f.write("]\n\n")

            f.write("# Object Palette\n")
            f.write("PALETTE_OBJ = [\n")
            for color in assets["palettes"]["obj"][:256]:
                f.write(f"    {color},\n")
            f.write("]\n\n")

            # Write tiles
            f.write("# 4bpp Tiles\n")
            f.write("TILES_4BPP = [\n")
            for i, tile in enumerate(assets["tiles"][:64]):
                f.write(f"    {tile},  # Tile {i}\n")
            f.write("]\n\n")

            # Write sprites
            f.write("# Sprites\n")
            f.write("SPRITES = [\n")
            for sprite in assets["sprites"][:128]:
                f.write(f"    {sprite},\n")
            f.write("]\n\n")

            f.write("# Metadata\n")
            f.write(f"PALETTE_BG_COLORS = {len(assets['palettes']['bg'])}\n")
            f.write(f"PALETTE_OBJ_COLORS = {len(assets['palettes']['obj'])}\n")
            f.write(f"TILES_EXTRACTED = {len(assets['tiles'])}\n")
            f.write(f"SPRITES_EXTRACTED = {len(assets['sprites'])}\n")

        print(f"Generated {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extract assets from oracle trace")
    parser.add_argument("--trace", "-t", required=True, help="Oracle trace JSON file")
    parser.add_argument("--output", "-o", required=True, help="Output Python assets file")

    args = parser.parse_args()

    tracker = OracleAssetTracker()
    tracker.load_oracle_trace(args.trace)
    assets = tracker.extract_assets_from_trace()
    tracker.generate_python_assets(args.output, assets)


if __name__ == "__main__":
    main()
