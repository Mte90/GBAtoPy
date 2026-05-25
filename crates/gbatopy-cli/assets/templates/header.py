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

# Registers as array for zero-overhead access
r = [0] * 16
r[15] = 0x08000000  # PC - GBA ROM entry point

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
