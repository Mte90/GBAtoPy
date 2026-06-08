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

# ROM_DATA will be populated by the transpiler (Base64 or bytearray)
vram = None
palette_ram = None
oam = None
ewram = None
