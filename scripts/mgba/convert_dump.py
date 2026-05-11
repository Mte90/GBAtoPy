#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Install PIL: pip install Pillow")
    exit(1)


def convert_vram_dump(input_path: Path, output_path: Path, mode: str = "mode4"):
    vram_data = input_path.read_bytes()
    
    if len(vram_data) != 0x18000:
        print(f"Error: Expected 96KB VRAM dump, got {len(vram_data)} bytes")
        return False
    
    pixels = []
    for y in range(160):
        row = []
        for x in range(240):
            offset = (y * 240 + x) * 2
            color = struct.unpack("<H", vram_data[offset:offset+2])[0]
            r = ((color >> 10) & 0x1F) * 8
            g = ((color >> 5) & 0x1F) * 8
            b = (color & 0x1F) * 8
            row.append((r, g, b))
        pixels.extend(row)
    
    img = Image.new("RGB", (240, 160))
    img.putdata(pixels)
    img.save(output_path)
    print(f"Saved: {output_path}")
    return True


def convert_palette_dump(input_path: Path, output_path: Path):
    palette_data = input_path.read_bytes()
    
    if len(palette_data) != 0x400:
        print(f"Error: Expected 1KB palette dump, got {len(palette_data)} bytes")
        return False
    
    pixels = []
    for i in range(256):
        color = struct.unpack("<H", palette_data[i*2:i*2+2])[0]
        r = ((color >> 10) & 0x1F) * 8
        g = ((color >> 5) & 0x1F) * 8
        b = (color & 0x1F) * 8
        pixels.append((r, g, b))
    
    img = Image.new("RGB", (16, 16))
    img.putdata(pixels)
    img.save(output_path)
    print(f"Saved palette: {output_path}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dump_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("."))
    parser.add_argument("--mode", choices=["mode3", "mode4"], default="mode4")
    
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    
    vram_files = list(args.dump_dir.glob("*_vram.bin"))
    palette_files = list(args.dump_dir.glob("*_palette.bin"))
    
    if not vram_files and not palette_files:
        print(f"No dump files found in {args.dump_dir}")
        return
    
    for vram_file in vram_files:
        rom_name = vram_file.name.replace("_vram.bin", "")
        output_file = args.output / f"{rom_name}_screenshot.png"
        convert_vram_dump(vram_file, output_file, args.mode)
    
    for palette_file in palette_files:
        rom_name = palette_file.name.replace("_palette.bin", "")
        output_file = args.output / f"{rom_name}_palette.png"
        convert_palette_dump(palette_file, output_file)
    
    print(f"Converted {len(vram_files)} VRAM dumps and {len(palette_files)} palette dumps")


if __name__ == "__main__":
    main()
