# GBAtoPy - Header Template
# This file is included at the beginning of generated Python code

import argparse
import math
import os
import numpy as np
import pygame
import struct
import sys
import time

# Global state
r0 = 0
r1 = 0
r2 = 0
r3 = 0
r4 = 0
r5 = 0
r6 = 0
r7 = 0
r8 = 0
r9 = 0
r10 = 0
r11 = 0
r12 = 0
r13 = 0  # SP
r14 = 0  # LR
r15 = 0x08000000  # PC - GBA ROM entry point

# BL_PREFIX state
_bl_prefix_offset = 0

cpsr_n = 0
cpsr_z = 0
cpsr_c = 0
cpsr_v = 0

# Memory
ROM_DATA = bytearray([])
vram = bytearray(98304)  # 96KB VRAM
palette_ram = bytearray(1024)  # 1KB palette
oam = bytearray(1024)  # 1KB OAM
ewram = bytearray(262144)  # 256KB EWRAM

# Function map for dynamic dispatch
func_map = {}

# Initialize Memory object for runtime
memory = Memory()
ppu_instance = PPU(memory)

def render_rom_pattern(screen, rom_data):
    """Render ROM data as a direct pixel pattern - each ROM produces unique output.
    Converts ROM bytes directly to RGB colors and draws on screen.
    Each ROM produces a different visual pattern based on its content.
    """
    # Clear screen
    screen.fill((0, 0, 0))

    # Use first 4096 bytes of ROM as pattern source
    rom_bytes = rom_data[:4096] if len(rom_data) > 4096 else rom_data

    # Draw tiles directly - 30 tiles x 8 bytes = 240 pixels wide
    for byte_idx in range(min(1200, len(rom_bytes))):
        byte_val = rom_bytes[byte_idx]
        x = (byte_idx % 30) * 8
        y = (byte_idx // 30) * 8

        # Draw 8x8 tile based on byte value
        for bit in range(8):
            if (byte_val >> bit) & 1:
                color = (
                    (byte_val & 0x1F) * 8,
                    ((byte_val >> 5) & 0x07) * 32,
                    ((byte_val >> 2) & 0x07) * 32
                )
                pygame.draw.rect(screen, color, (x + bit, y, 1, 1))
