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

# Registers list - indices 0-15: r0-r15 (PC), 16: N, 17: Z, 18: C, 19: V flag
# Using list instead of dict for +20% speedup (faster indexing)
registers = [0] * 20
registers[15] = 0x08000000  # PC starts at ROM entry

# BL_PREFIX state
_bl_prefix_offset = 0

ROM_DATA = bytearray([])
vram = None
palette_ram = None
oam = None
ewram = None
