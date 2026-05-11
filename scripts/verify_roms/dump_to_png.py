#!/usr/bin/env python3
import struct
import sys
from PIL import Image

def read_palette(path):
    palette = []
    with open(path, 'rb') as f:
        while True:
            data = f.read(3)
            if not data:
                break
            r, g, b = struct.unpack('BBB', data)
            palette.append((r, g, b))
    return palette

def read_vram(path, size=38400):
    with open(path, 'rb') as f:
        return f.read(size)

def vram_to_pixels(vram_data, palette):
    pixels = []
    for byte in vram_data:
        idx = byte & 0xFF
        if idx < len(palette):
            pixels.append(palette[idx])
        else:
            pixels.append((0, 0, 0))
    return pixels

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <vram.bin> <palette.bin> [output.png]")
        sys.exit(1)
    
    vram_path = sys.argv[1]
    palette_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "screenshot.png"
    
    palette = read_palette(palette_path)
    vram = read_vram(vram_path)
    pixels = vram_to_pixels(vram, palette)
    
    img = Image.new('RGB', (240, 160))
    img.putdata(pixels)
    img.save(output_path)
    print(f"Saved {output_path}")

if __name__ == '__main__':
    main()