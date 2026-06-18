# === GBA Runtime (embedded) ===

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

# Registers dict - indices 0-15: r0-r15 (PC), 16: N, 17: Z, 18: C, 19: V flag
registers = {i: 0 for i in range(20)}
registers[15] = 0x08000000  # PC starts at ROM entry

# BL_PREFIX state
_bl_prefix_offset = 0

ROM_DATA = bytearray([])
vram = None
palette_ram = None
oam = None
ewram = None

import array as _array
from typing import Callable, Optional


class MemoryMap:
    BIOS_START = 0x00000000
    BIOS_END = 0x00003FFF
    BIOS_SIZE = 0x4000

    EWRAM_START = 0x02000000
    EWRAM_END = 0x0203FFFF
    EWRAM_SIZE = 0x40000

    IWRAM_START = 0x03000000
    IWRAM_END = 0x03007FFF
    IWRAM_SIZE = 0x8000

    IO_START = 0x04000000
    IO_END = 0x040003FF
    IO_SIZE = 0x400

    PALETTE_START = 0x05000000
    PALETTE_END = 0x050003FF
    PALETTE_SIZE = 0x400

    VRAM_START = 0x06000000
    VRAM_END = 0x06017FFF
    VRAM_SIZE = 0x18000

    OAM_START = 0x07000000
    OAM_END = 0x070003FF
    OAM_SIZE = 0x400

    ROM_START = 0x08000000
    ROM_END = 0x09FFFFFF
    ROM_MAX_SIZE = 0x2000000

    SRAM_START = 0x0A000000
    SRAM_END = 0x0A00FFFF
    SRAM_SIZE = 0x10000


class Memory:
    def __init__(self):
        # Use array.array('B') for faster memory access
        self.bios = _array.array('B', [0] * MemoryMap.BIOS_SIZE)
        self.ewram = _array.array('B', [0] * MemoryMap.EWRAM_SIZE)
        self.iwram = _array.array('B', [0] * MemoryMap.IWRAM_SIZE)
        self.io = _array.array('B', [0] * MemoryMap.IO_SIZE)
        self.palette = _array.array('B', [0] * MemoryMap.PALETTE_SIZE)
        self.vram = _array.array('B', [0] * MemoryMap.VRAM_SIZE)
        self.oam = _array.array('B', [0] * MemoryMap.OAM_SIZE)
        self.sram = _array.array('B', [0] * MemoryMap.SRAM_SIZE)

        self._affine_params = _array.array('B', [0] * 16)

        self.rom: Optional[bytearray] = None
        self.rom_size: int = 0
        self.open_bus: int = 0

        self._mmio_write_handlers: dict[int, Callable[[int, int], None]] = {}
        self._mmio_read_handlers: dict[int, Callable[[int], int]] = {}
        # GBA hardware default: DISPCNT = 0x80 (display enabled)
        self.io[0x00] = 0x80
        self.io[0x01] = 0x00

        self._ppu: Optional[object] = None
        self._dma: Optional[object] = None
        self._apu: Optional[object] = None
        self._timers: Optional[object] = None
        self._input: Optional[object] = None
        self._interrupts: Optional[object] = None

        self.bios[0x00] = 0xEA
        self.bios[0x01] = 0x00
        self.bios[0x02] = 0x00
        self.bios[0x03] = 0x00
        self._isr_handler = None

    def setup_isr_handler(self, handler):
        self._isr_handler = handler
        isr_addr = id(handler)
        self.iwram[0x7FFC] = isr_addr & 0xFF
        self.iwram[0x7FFD] = (isr_addr >> 8) & 0xFF
        self.iwram[0x7FFE] = (isr_addr >> 16) & 0xFF
        self.iwram[0x7FFF] = (isr_addr >> 24) & 0xFF

    def get_isr_address(self) -> int:
        offset = 0x7FFC - 0x03000000
        return (self.iwram[offset] | 
                (self.iwram[offset + 1] << 8) | 
                (self.iwram[offset + 2] << 16) | 
                (self.iwram[offset + 3] << 24))

    def attach_ppu(self, ppu):        self._ppu = ppu

    def attach_dma(self, dma):
        self._dma = dma

    def attach_apu(self, apu):
        self._apu = apu

    def attach_timers(self, timers):
        self._timers = timers

    def attach_input(self, inp):
        self._input = inp

    def attach_interrupts(self, irq):
        self._interrupts = irq

    def register_mmio_write(self, offset: int, handler: Callable[[int, int], None]):
        if 0 <= offset < MemoryMap.IO_SIZE:
            self._mmio_write_handlers[offset] = handler

    def register_mmio_read(self, offset: int, handler: Callable[[int], int]):
        if 0 <= offset < MemoryMap.IO_SIZE:
            self._mmio_read_handlers[offset] = handler

    def _dispatch_mmio_write(self, addr: int, value: int):
        offset = addr - MemoryMap.IO_START
        if offset in self._mmio_write_handlers:
            self._mmio_write_handlers[offset](addr, value)
        self._dispatch_hal_write(addr, value)

    def _dispatch_mmio_read(self, addr: int) -> Optional[int]:
        offset = addr - MemoryMap.IO_START
        if offset in self._mmio_read_handlers:
            return self._mmio_read_handlers[offset](addr)
        hal_result = self._dispatch_hal_read(addr)
        if hal_result is not None:
            return hal_result
        return None

    def _dispatch_hal_write(self, addr: int, value: int):
        if 0x04000000 <= addr <= 0x0400005F:
            if self._ppu:
                self._ppu.write_register(addr, value)
        if 0x04000048 <= addr <= 0x0400004F:
            self._handle_window_write(addr, value)
        if 0x04000020 <= addr <= 0x0400003C:
            self._handle_affine_bg_write(addr, value)
        if 0x04000060 <= addr <= 0x0400007F:
            self._handle_sound_write(addr, value)
        if 0x04000090 <= addr <= 0x040000A7:
            if self._apu:
                self._apu.write_register(addr, value)
        if 0x040000B0 <= addr <= 0x040000EF:
            if self._dma:
                self._handle_dma_write(addr, value)
        if 0x04000100 <= addr <= 0x0400010F:
            if self._timers:
                self._handle_timer_write(addr, value)
        if 0x04000200 <= addr <= 0x04000208:
            if self._interrupts:
                self._handle_interrupt_write(addr, value)

    def _dispatch_hal_read(self, addr: int) -> Optional[int]:
        # Window registers (0x04000048-0x0400004F)
        if 0x04000048 <= addr <= 0x0400004F:
            return self._handle_window_read(addr)
        if 0x04000020 <= addr <= 0x0400003C:
            return self._handle_affine_bg_read(addr)
        # Sound registers (0x04000060-0x0400008F, exclusive of affine range)
        if 0x04000060 <= addr <= 0x0400008F:
            return self._handle_sound_read(addr)
        if 0x04000100 <= addr <= 0x0400010F:
            if self._timers:
                return self._handle_timer_read(addr)
        if 0x040000B0 <= addr <= 0x040000EF:
            if self._dma:
                return self._handle_dma_read(addr)
        # KEYINPUT (0x04000130) - current key states, active low
        if addr == 0x04000130:
            if self._input:
                return self._input.get_keys() & 0xFF
        # KEYINPUT high byte (0x04000131)
        if addr == 0x04000131:
            if self._input:
                return (self._input.get_keys() >> 8) & 0xFF
        # KEYCNT (0x04000132) - key interrupt control register
        if addr == 0x04000132:
            offset = addr - MemoryMap.IO_START
            return self.io[offset]
        # KEYCNT high byte (0x04000133)
        if addr == 0x04000133:
            offset = addr - MemoryMap.IO_START
            return self.io[offset]
        return None

    def _handle_dma_read(self, addr: int) -> int:
        channel = (addr - 0x040000B0) // 0x10
        reg_offset = (addr - 0x040000B0) % 0x10
        if channel < 0 or channel > 3:
            return 0
        ch = self._dma.channels[channel]
        ch.read_from_memory()
        if reg_offset == 0:
            return ch.src_addr
        elif reg_offset == 4:
            return ch.dst_addr
        elif reg_offset == 8:
            return ch.count
        elif reg_offset == 12:
            return ch.control
        return 0

    def _handle_dma_write(self, addr: int, value: int):
        channel = (addr - 0x040000B0) // 0x10
        reg_offset = (addr - 0x040000B0) % 0x10
        if channel < 0 or channel > 3:
            return
        if reg_offset == 0:
            self._dma.channels[channel].src_addr = value
        elif reg_offset == 4:
            self._dma.channels[channel].dst_addr = value
        elif reg_offset == 8:
            self._dma.channels[channel].count = value
        elif reg_offset == 12:
            self._dma.channels[channel].control = value
            was_enabled = self._dma.channels[channel].enabled
            self._dma.channels[channel].enabled = (value & 0x80000000) != 0
            # Trigger immediate DMA transfer when enabled
            if self._dma.channels[channel].enabled and not was_enabled:
                if self._dma.channels[channel].is_immediate():
                    self._dma.start_transfer(channel)

    def _handle_timer_write(self, addr: int, value: int):
        base = 0x04000100
        if addr < base or addr > 0x0400010F:
            return
        timer_idx = (addr - base) // 4
        reg_offset = (addr - base) % 4
        if timer_idx < 0 or timer_idx > 3:
            return
        if reg_offset == 0:
            # CNT_L: 16-bit, both counter and reload value
            self._timers.set_reload(timer_idx, value & 0xFFFF)
            # If timer not started, also set initial count
            if not self._timers.channels[timer_idx].enabled:
                self._timers.set_timer(timer_idx, value & 0xFFFF)
        elif reg_offset == 2:
            # CNT_H: 16-bit control register
            self._timers.set_control(timer_idx, value & 0xFFFF)

    def _handle_timer_read(self, addr: int) -> Optional[int]:
        base = 0x04000100
        if addr < base or addr > 0x0400010F:
            return None
        timer_idx = (addr - base) // 4
        reg_offset = (addr - base) % 4
        if timer_idx < 0 or timer_idx > 3:
            return None
        if reg_offset == 0:
            # CNT_L: current count value
            return self._timers.get_timer(timer_idx)
        elif reg_offset == 2:
            # CNT_H: control register
            return self._timers.get_control(timer_idx)
        return None

    def _handle_interrupt_write(self, addr: int, value: int):
        if addr == 0x04000200:
            self._interrupts.write_ie(value)
        elif addr == 0x04000204:
            self._interrupts.write_if(value)
        elif addr == 0x04000208:
            self._interrupts.write_ime(value)

    def _handle_sound_read(self, addr: int) -> int:
        """Read sound register - route to APU."""
        if self._apu is not None and 0x04000060 <= addr <= 0x040000A5:
            return self._apu.read_register(addr)
        return 0

    def _handle_window_read(self, addr: int) -> int:
        offset = addr - MemoryMap.IO_START
        return self.io[offset]

    def _handle_window_write(self, addr: int, value: int):
        offset = addr - MemoryMap.IO_START
        if 0 <= offset < MemoryMap.IO_SIZE:
            self.io[offset] = value & 0xFF

    def _handle_affine_bg_read(self, addr: int) -> int:
        """Read affine background parameter (byte read - 8-bit only)."""
        # Each affine param is 16-bit across two consecutive bytes
        base = MemoryMap.IO_START + 0x80
        byte_offset = addr - base
        byte_idx = byte_offset % 2  # 0 = low byte, 1 = high byte
        param_idx = byte_offset // 2
        return self._affine_params[param_idx * 2 + byte_idx]

    def _handle_affine_bg_write(self, addr: int, value: int):
        """Write affine background parameter (16-bit)."""
        # BG2PA/BG2PB/BG2PC/BG2PD at offsets 0x80, 0x82, 0x84, 0x86
        # BG3PA/BG3PB/BG3PC/BG3PD at offsets 0x88, 0x8A, 0x8C, 0x8E (from IO_START)
        base = MemoryMap.IO_START + 0x80
        byte_offset = addr - base
        param_idx = byte_offset // 2
        self._affine_params[param_idx * 2] = value & 0xFF
        self._affine_params[param_idx * 2 + 1] = (value >> 8) & 0xFF

    def _handle_sound_write(self, addr: int, value: int):
        """Write sound register - route to APU."""
        if self._apu is not None and 0x04000060 <= addr <= 0x040000A5:
            self._apu.write_register(addr, value)

    def _get_rom_addr(self, addr: int) -> int:
        if addr < MemoryMap.ROM_START or addr > 0x0EFFFFFF:
            return -1

        offset = (addr - MemoryMap.ROM_START) % MemoryMap.ROM_MAX_SIZE
        if offset >= self.rom_size:
            return -1
        return offset

    def _map_address(self, addr: int) -> int:
        if 0x00000000 <= addr <= 0x01FFFFFF:
            return addr & 0x00003FFF

        if 0x02000000 <= addr <= 0x02FFFFFF:
            return (addr & 0x0003FFFF) | 0x02000000

        if 0x03000000 <= addr <= 0x03FFFFFF:
            return (addr & 0x00007FFF) | 0x03000000

        if 0x04000000 <= addr <= 0x04FFFFFF:
            return (addr & 0x000003FF) | 0x04000000

        if 0x05000000 <= addr <= 0x05FFFFFF:
            return (addr & 0x000003FF) | 0x05000000

        if 0x06000000 <= addr <= 0x06FFFFFF:
            return (addr & 0x00017FFF) | 0x06000000

        if 0x07000000 <= addr <= 0x07FFFFFF:
            return (addr & 0x000003FF) | 0x07000000

        return addr

    def read_u8(self, addr: int) -> int:
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)

        if MemoryMap.BIOS_START <= addr <= MemoryMap.BIOS_END:
            offset = addr - MemoryMap.BIOS_START
            value = self.bios[offset]
            self.open_bus = value
            return value

        if MemoryMap.EWRAM_START <= addr <= MemoryMap.EWRAM_END:
            offset = addr - MemoryMap.EWRAM_START
            value = self.ewram[offset]
            self.open_bus = value
            return value

        if MemoryMap.IWRAM_START <= addr <= MemoryMap.IWRAM_END:
            offset = addr - MemoryMap.IWRAM_START
            value = self.iwram[offset]
            self.open_bus = value
            return value

        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            offset = addr - MemoryMap.IO_START
            result = self._dispatch_mmio_read(addr)
            if result is not None:
                self.open_bus = result & 0xFF
                return result
            value = self.io[offset]
            self.open_bus = value
            return value

        if MemoryMap.PALETTE_START <= addr <= MemoryMap.PALETTE_END:
            offset = addr - MemoryMap.PALETTE_START
            value = self.palette[offset]
            self.open_bus = value
            return value

        if MemoryMap.VRAM_START <= addr <= MemoryMap.VRAM_END:
            offset = addr - MemoryMap.VRAM_START
            value = self.vram[offset]
            self.open_bus = value
            return value

        if MemoryMap.OAM_START <= addr <= MemoryMap.OAM_END:
            offset = addr - MemoryMap.OAM_START
            value = self.oam[offset]
            self.open_bus = value
            return value

        if MemoryMap.ROM_START <= addr <= 0x0EFFFFFF:
            rom_addr = self._get_rom_addr(addr)
            if rom_addr >= 0 and self.rom:
                value = self.rom[rom_addr]
                self.open_bus = value
                return value

        if MemoryMap.SRAM_START <= addr <= MemoryMap.SRAM_END:
            offset = addr - MemoryMap.SRAM_START
            if offset < len(self.sram):
                value = self.sram[offset]
                self.open_bus = value
                return value

        return self.open_bus & 0xFF

    def _buffer_for_addr(self, addr: int) -> tuple[bytearray, int]:
        addr = self._map_address(addr)
        if MemoryMap.ROM_START <= addr <= 0x0EFFFFFF:
            rom_addr = self._get_rom_addr(addr)
            if 0 <= rom_addr < self.rom_size:
                return self.rom, rom_addr
        if MemoryMap.EWRAM_START <= addr <= MemoryMap.EWRAM_END:
            return self.ewram, addr - MemoryMap.EWRAM_START
        if MemoryMap.IWRAM_START <= addr <= MemoryMap.IWRAM_END:
            return self.iwram, addr - MemoryMap.IWRAM_START
        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            return self.io, addr - MemoryMap.IO_START
        if MemoryMap.PALETTE_START <= addr <= MemoryMap.PALETTE_END:
            return self.palette, addr - MemoryMap.PALETTE_START
        if MemoryMap.VRAM_START <= addr <= MemoryMap.VRAM_END:
            return self.vram, addr - MemoryMap.VRAM_START
        if MemoryMap.OAM_START <= addr <= MemoryMap.OAM_END:
            return self.oam, addr - MemoryMap.OAM_START
        if MemoryMap.SRAM_START <= addr <= MemoryMap.SRAM_END:
            return self.sram, addr - MemoryMap.SRAM_START
        return None, 0

    def read_u16(self, addr: int) -> int:
        buf, start = self._buffer_for_addr(addr & 0xFFFFFFFF)
        if buf:
            return int.from_bytes(buf[start:start + 2], 'little')
        return int.from_bytes(self.rom[addr - 0x08000000:(addr - 0x08000000) + 2], 'little')
    
    def read_32(self, addr: int) -> int:
        """Read 32-bit unsigned value"""
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)
        buf, off = self._buffer_for_addr(addr)
        if buf is not None and off + 4 <= len(buf):
            return int.from_bytes(buf[off:off + 4], 'little')
        b0 = self.read_u8(addr)
        b1 = self.read_u8(addr + 1)
        b2 = self.read_u8(addr + 2)
        b3 = self.read_u8(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
    def read_u32(self, addr: int) -> int:
        """Read 32-bit unsigned value"""
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)
        buf, off = self._buffer_for_addr(addr)
        if buf is not None and off + 4 <= len(buf):
            return int.from_bytes(buf[off:off + 4], 'little')
        b0 = self.read_u8(addr)
        b1 = self.read_u8(addr + 1)
        b2 = self.read_u8(addr + 2)
        b3 = self.read_u8(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
    def write_u8(self, addr: int, value: int):
        addr &= 0xFFFFFFFF
        value &= 0xFF
        addr = self._map_address(addr)

        if MemoryMap.BIOS_START <= addr <= MemoryMap.BIOS_END:
            return

        if MemoryMap.EWRAM_START <= addr <= MemoryMap.EWRAM_END:
            offset = addr - MemoryMap.EWRAM_START
            self.ewram[offset] = value
            self.open_bus = value
            return

        if MemoryMap.IWRAM_START <= addr <= MemoryMap.IWRAM_END:
            offset = addr - MemoryMap.IWRAM_START
            self.iwram[offset] = value
            self.open_bus = value
            if offset + 1 < len(self.iwram):
                self.iwram[offset + 1] = value
            if offset + 2 < len(self.iwram):
                self.iwram[offset + 2] = value
            if offset + 3 < len(self.iwram):
                self.iwram[offset + 3] = value
            return

        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            offset = addr - MemoryMap.IO_START
            self.io[offset] = value
            self.open_bus = value
            return

        if MemoryMap.PALETTE_START <= addr <= MemoryMap.PALETTE_END:
            offset = addr - MemoryMap.PALETTE_START
            self.palette[offset] = value
            self.open_bus = value
            return

        if MemoryMap.VRAM_START <= addr <= MemoryMap.VRAM_END:
            offset = addr - MemoryMap.VRAM_START
            self.vram[offset] = value
            self.open_bus = value
            return

        if MemoryMap.OAM_START <= addr <= MemoryMap.OAM_END:
            offset = addr - MemoryMap.OAM_START
            self.oam[offset] = value
            self.open_bus = value
            return

        if MemoryMap.ROM_START <= addr <= 0x0EFFFFFF:
            return

        if MemoryMap.SRAM_START <= addr <= MemoryMap.SRAM_END:
            offset = addr - MemoryMap.SRAM_START
            if offset < len(self.sram):
                self.sram[offset] = value
                self.open_bus = value

    def write_u16(self, addr: int, value: int):
        addr &= 0xFFFFFFFF
        value &= 0xFFFF
        addr = self._map_address(addr)

        # Handle affine parameters directly to avoid split across two addresses
        # Affine params are at even offsets: 0x80, 0x82, 0x84, 0x86, 0x88, 0x8A, 0x8C, 0x8E
        # Each is 16-bit, so we write both bytes to the dedicated storage
        if 0x04000080 <= addr <= 0x0400008E and addr % 2 == 0:
            base = MemoryMap.IO_START + 0x80
            byte_offset = addr - base
            param_idx = byte_offset // 2
            self._affine_params[param_idx * 2] = value & 0xFF
            self._affine_params[param_idx * 2 + 1] = (value >> 8) & 0xFF
            return

        self.write_u8(addr, value & 0xFF)
        self.write_u8(addr + 1, (value >> 8) & 0xFF)

        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            self._dispatch_hal_write(addr, value)

    def write_u32(self, addr: int, value: int):
        addr &= 0xFFFFFFFF
        value &= 0xFFFFFFFF
        addr = self._map_address(addr)

        self.write_u8(addr, value & 0xFF)
        self.write_u8(addr + 1, (value >> 8) & 0xFF)
        self.write_u8(addr + 2, (value >> 16) & 0xFF)
        self.write_u8(addr + 3, (value >> 24) & 0xFF)

        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            self._dispatch_hal_write(addr, value)

    def load_rom(self, path: str):
        with open(path, "rb") as f:
            rom_data = f.read()

        self.load_rom_data(rom_data)

    def load_rom_data(self, data):
        if isinstance(data, str):
            data = data.encode("latin-1")
        self.rom = _array.array('B', data)
        self.rom_size = len(data)

        if self.rom_size >= 4:
            self.iwram[0:4] = self.rom[0:4]

    def get_io_register(self, offset: int) -> int:
        if 0 <= offset < MemoryMap.IO_SIZE:
            return self.io[offset]
        return 0

    def set_io_register(self, offset: int, value: int):
        if 0 <= offset < MemoryMap.IO_SIZE:
            self.io[offset] = value & 0xFF


class MemoryDump:
    """Utility for dumping and comparing memory state."""

    def __init__(self, memory: "Memory"):
        self.memory = memory
        self.dump_dir = None

    def set_dump_directory(self, directory: str):
        """Set the output directory for dump files."""
        self.dump_dir = directory

    def dump_all_memory(self, frame: int = None) -> dict:
        """
        Dump all memory regions to a dictionary.

        Returns:
            dict containing all memory regions
        """
        dump = {
            "timestamp": frame if frame is not None else "unknown",
            "bios": list(self.memory.bios),
            "ewram": list(self.memory.ewram),
            "iwram": list(self.memory.iwram),
            "palette": list(self.memory.palette),
            "vram": list(self.memory.vram),
            "oam": list(self.memory.oam),
            "sram": list(self.memory.sram),
            "affine_params": list(self.memory._affine_params),
            "open_bus": self.memory.open_bus,
        }

        # Add ROM if loaded
        if self.memory.rom:
            dump["rom"] = list(self.memory.rom)

        return dump

    def dump_memory_regions(self, regions: list[str], frame: int = None) -> dict:
        """
        Dump specific memory regions.

        Args:
            regions: List of region names to dump (bios, ewram, iwram, palette, vram, oam, sram)
            frame: Optional frame number for timestamp
        """
        dump = {"timestamp": frame if frame is not None else "unknown"}

        for region in regions:
            if region == "bios":
                dump["bios"] = list(self.memory.bios)
            elif region == "ewram":
                dump["ewram"] = list(self.memory.ewram)
            elif region == "iwram":
                dump["iwram"] = list(self.memory.iwram)
            elif region == "palette":
                dump["palette"] = list(self.memory.palette)
            elif region == "vram":
                dump["vram"] = list(self.memory.vram)
            elif region == "oam":
                dump["oam"] = list(self.memory.oam)
            elif region == "sram":
                dump["sram"] = list(self.memory.sram)

        return dump

    def save_memory_dump(self, dump: dict, filename: str = None) -> str:
        """
        Save memory dump to JSON file.

        Args:
            dump: Memory dump dictionary
            filename: Optional filename (without extension)

        Returns:
            Path to saved file
        """
        import json

        if self.dump_dir is None:
            raise ValueError("No dump directory set. Call set_dump_directory() first.")

        if filename is None:
            filename = f"memory_dump_{dump.get('timestamp', 'unknown')}"

        # Ensure directory exists
        import os
        os.makedirs(self.dump_dir, exist_ok=True)

        filepath = os.path.join(self.dump_dir, f"{filename}.json")
        with open(filepath, "w") as f:
            json.dump(dump, f, indent=2)

        return filepath

    def diff_memory(self, dump1: dict, dump2: dict, threshold: float = 0.0) -> dict:
        """
        Compare two memory dumps and find differences.

        Args:
            dump1: First memory dump
            dump2: Second memory dump
            threshold: Byte value threshold for comparison (0 = exact match)

        Returns:
            dict with difference summary
        """
        differences = []

        # Regions to compare (exclude ROM which may be large)
        regions = ["bios", "ewram", "iwram", "palette", "vram", "oam", "sram", "affine_params"]

        for region in regions:
            if region not in dump1 or region not in dump2:
                continue

            data1 = dump1[region]
            data2 = dump2[region]

            if len(data1) != len(data2):
                differences.append({
                    "region": region,
                    "type": "size_mismatch",
                    "data1_size": len(data1),
                    "data2_size": len(data2),
                })
                continue

            diff_count = 0
            for i, (b1, b2) in enumerate(zip(data1, data2)):
                if b1 != b2:
                    diff_count += 1

            if diff_count > 0:
                diff_pct = (diff_count / len(data1)) * 100
                differences.append({
                    "region": region,
                    "diff_count": diff_count,
                    "total_bytes": len(data1),
                    "diff_percentage": round(diff_pct, 2),
                })

        return {
            "total_regions_compared": len(regions),
            "differences_found": len(differences),
            "differences": differences,
        }

    def save_diff_report(self, diff_result: dict, filename: str = None) -> str:
        """
        Save memory diff report to text file.

        Args:
            diff_result: Result of diff_memory()
            filename: Optional filename (without extension)
        """
        import os
        if self.dump_dir is None:
            raise ValueError("No dump directory set.")

        if filename is None:
            filename = "memory_diff_report"

        filepath = os.path.join(self.dump_dir, f"{filename}.txt")
        with open(filepath, "w") as f:
            f.write("Memory Comparison Report\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Total regions compared: {diff_result['total_regions_compared']}\n")
            f.write(f"Differences found: {diff_result['differences_found']}\n\n")

            if diff_result["differences"]:
                f.write("Differences:\n")
                f.write("-" * 60 + "\n")
                for diff in diff_result["differences"]:
                    f.write(f"\nRegion: {diff['region']}\n")
                    if diff.get("type") == "size_mismatch":
                        f.write(f"  - Size mismatch: {diff['data1_size']} vs {diff['data2_size']}\n")
                    else:
                        f.write(f"  - Different bytes: {diff['diff_count']}/{diff['total_bytes']}\n")
                        f.write(f"  - Difference: {diff['diff_percentage']}%\n")
            else:
                f.write("\nNo differences found.\n")

        return filepath

"""GBA PPU (Pixel Processing Unit) - Graphics rendering"""

import struct
import os
from typing import Optional, List, Tuple

# Numba JIT compilation support
try:
    import numba
    from numba import njit, prange
    _HAS_NUMBA = True
except ImportError:
    numba = None
    njit = None
    prange = None
    _HAS_NUMBA = False

_NUMBA_ENABLED = True
_NUMBA_PPU_ENABLED = True  # Separate flag for PPU JIT


def _try_enable_numba_jit() -> bool:
    """Attempt to enable Numba JIT for PPU functions.

    Returns the enabled state. Falls back gracefully if numba is not installed."""
    global _NUMBA_PPU_ENABLED, _HAS_NUMBA
    try:
        import numba  # noqa: F401
        if numba is not None:
            _HAS_NUMBA = True
            _NUMBA_PPU_ENABLED = True
            return True
    except ImportError:
        pass

    _HAS_NUMBA = False
    _NUMBA_PPU_ENABLED = False
    print("  Warning: numba not installed, PPU JIT disabled")
    return False


def jit_compile(func):
    """Decorator to JIT-compile a function with numba when available."""
    if not _HAS_NUMBA or not _NUMBA_ENABLED:
        return func
    try:
        return njit(func)
    except Exception as e:
        print(f"  Warning: JIT compilation failed for {func.__name__}: {e}")
        return func


def jit_compile_ppu(func):
    """Decorator to JIT-compile PPU functions with numba when enabled."""
    if not _HAS_NUMBA or not _NUMBA_PPU_ENABLED:
        return func
    try:
        return njit(func, parallel=True)
    except Exception as e:
        print(f"  Warning: PPU JIT compilation failed for {func.__name__}: {e}")
        return func


def set_numba_enabled(enabled: bool):
    """Enable or disable all numba JIT compilation."""
    global _NUMBA_ENABLED
    if not _HAS_NUMBA and enabled:
        print("  Warning: numba not installed, JIT compilation unavailable")
    _NUMBA_ENABLED = enabled and _HAS_NUMBA


def set_numba_ppu_enabled(enabled: bool):
    """Enable or disable PPU-specific numba JIT compilation."""
    global _NUMBA_PPU_ENABLED
    if not _HAS_NUMBA and enabled:
        print("  Warning: numba not installed, PPU JIT compilation unavailable")
    _NUMBA_PPU_ENABLED = enabled and _HAS_NUMBA


def is_numba_available() -> bool:
    """Check if numba is available."""
    return _HAS_NUMBA


def is_numba_ppu_enabled() -> bool:
    """Check if PPU JIT is enabled."""
    return _NUMBA_PPU_ENABLED and _HAS_NUMBA


@jit_compile
def _c5to8_jit(c):
    if not isinstance(c, int):
        c = int(c)
    val = c & 0x1F
    return ((val << 3) | (val >> 2)) & 0xFF


@jit_compile
def _read_color_jit(vram_data, addr):
    if addr >= 0 and addr + 1 < len(vram_data):
        return int(vram_data[addr] | (vram_data[addr + 1] << 8))
    return 0


@jit_compile
def _read_palette_jit(palette_data, addr):
    if addr >= 0 and addr + 1 < len(palette_data):
        return int(palette_data[addr] | (palette_data[addr + 1] << 8))
    return 0


@jit_compile
def _convert_color_jit(color_val):
    r = int((color_val >> 0) & 0x1F)
    g = int((color_val >> 5) & 0x1F)
    b = int((color_val >> 10) & 0x1F)
    r8 = int((r << 3) | (r >> 2))
    g8 = int((g << 3) | (g >> 2))
    b8 = int((b << 3) | (b >> 2))
    return int(0xFF000000 | (b8 << 16) | (g8 << 8) | r8)


@jit_compile
def _decode_tile_4bpp_jit(vram_data, tile_offset):
    result = [0] * 64
    for row in range(8):
        for col in range(8):
            byte_offset = row * 4 + (col // 2)
            addr = tile_offset + byte_offset
            if addr >= 0 and addr < len(vram_data):
                byte_val = vram_data[addr]
                if col % 2 == 0:
                    color_idx = int((byte_val >> 4) & 0x0F)
                else:
                    color_idx = int(byte_val & 0x0F)
                result[row * 8 + col] = color_idx
            else:
                result[row * 8 + col] = 0
    return result


@jit_compile
def _decode_tile_8bpp_jit(vram_data, tile_offset):
    result = [0] * 64
    for row in range(8):
        for col in range(8):
            addr = tile_offset + (row * 8) + col
            if addr >= 0 and addr < len(vram_data):
                result[row * 8 + col] = int(vram_data[addr])
            else:
                result[row * 8 + col] = 0
    return result


# ========================================================================
# Numba JIT-compiled rendering helpers (cache=True for performance)
# ========================================================================

@jit_compile
def _get_palette_color_jit(palette_data, palette_idx):
    addr = palette_idx * 2
    if addr + 1 >= len(palette_data):
        return (0, 0, 0)

    color_val = palette_data[addr] | (palette_data[addr + 1] << 8)

    if color_val == 0 and palette_idx > 0:
        intensity = min(255, (palette_idx * 17))
        return (intensity, intensity, intensity)

    r = int((color_val >> 0) & 0x1F)
    g = int((color_val >> 5) & 0x1F)
    b = int((color_val >> 10) & 0x1F)
    r8 = int((r << 3) | (r >> 2))
    g8 = int((g << 3) | (g >> 2))
    b8 = int((b << 3) | (b >> 2))
    return (r8, g8, b8)


@jit_compile
def _get_palette_color_256_jit(palette_data, color_idx):
    addr = color_idx * 2
    if addr + 1 >= len(palette_data):
        return (0, 0, 0)

    color_val = palette_data[addr] | (palette_data[addr + 1] << 8)

    if color_val == 0 and color_idx > 0:
        intensity = min(255, (color_idx * 17))
        return (intensity, intensity, intensity)

    r = int((color_val >> 0) & 0x1F)
    g = int((color_val >> 5) & 0x1F)
    b = int((color_val >> 10) & 0x1F)
    r8 = int((r << 3) | (r >> 2))
    g8 = int((g << 3) | (g >> 2))
    b8 = int((b << 3) | (b >> 2))
    return (r8, g8, b8)


def _get_vram_bytes(memory, start: int, size: int) -> bytes:
    """Extract VRAM bytes for JIT functions."""
    data = bytearray(size)
    for i in range(size):
        try:
            data[i] = memory.read_u8(start + i)
        except:
            data[i] = 0
    return bytes(data)


def _get_palette_bytes(memory, start: int = 0x05000000, size: int = 512) -> bytes:
    """Extract palette RAM bytes for JIT functions."""
    data = bytearray(size)
    for i in range(size):
        try:
            data[i] = memory.read_u8(start + i)
        except:
            data[i] = 0
    return bytes(data)


def compute_flags(result: int, width: int) -> int:
    """Compute ARM7TDMI CPSR flags from arithmetic result.
    
    Args:
        result: 32-bit arithmetic result
        width: Bit width (32 for ARM, 16 for Thumb)
    
    Returns:
        CPSR flags: N (bit 31), Z (bit 30), C (bit 29), V (bit 28)
    """
    # N (Negative): bit 31
    n = 1 if result < 0 else 0
    
    # Z (Zero): bit 30
    z = 1 if result == 0 else 0
    
    # C (Carry): bit 29
    # For add/sub, C=1 if result < operand (unsigned overflow)
    c = 0
    
    # V (Overflow): bit 28 - for signed overflow
    # This is complex to compute generically, default to 0
    v = 0
    
    return (n << 31) | (z << 30) | (c << 29) | (v << 28)


def _c5to8(c: int) -> int:
    """Convert 5-bit GBA color to 8-bit. Formula: (c << 3) | (c >> 2)"""
    return (c << 3) | (c >> 2)


class PPU:
    """Game Boy Advance Pixel Processing Unit"""


# ========================================================================
    # OAM (Object Attribute Memory) - Sprite rendering
    # ========================================================================
# OAM at 0x07000000-0x070003FF (1KB, 128 sprites × 8 bytes)
    #
    # Each sprite has 3 attributes (8 bytes total per sprite):
    #   Attribute 0 (offset 0): Y position (bits 0-7), various flags
    #   Attribute 1 (offset 2): X position (bits 8-0 of word), size, affine
    #   Attribute 2 (offset 4): Tile number (bits 0-9), priority, palette
    #
    # GBATEK Reference:
    #   Attr0 bits: 0-7=Y, 8-9=mode, 10=mosaic, 11=color mode(0=4bpp,1=8bpp), 12-13=shape
    #   Attr1 bits: 0-8=X, 9=affine/flip, 10=double-size, 11=rotate/scale, 12=color mode, 13=mosaic, 14-15=size
    #   Attr2 bits: 0-9=tile#, 10-11=priority, 12-15=palette (4bpp only)
    # ========================================================================

    # Sprite size lookup table: [shape][size] = (width, height)
    SPRITE_SIZES = {
        # Square shapes (shape 0)
        0: {0: (8, 8), 1: (16, 16), 2: (32, 32), 3: (64, 64)},
        # Rectangular shapes (shape 1: 8x16, 16x8, etc)
        1: {0: (8, 16), 1: (16, 8), 2: (32, 16), 3: (16, 32)},
        # Rectangular shapes (shape 2)
        2: {0: (8, 32), 1: (16, 16), 2: (32, 8), 3: (8, 8)},
        # Reserved shape 3 - treat as 8x8
        3: {0: (8, 8), 1: (8, 8), 2: (8, 8), 3: (8, 8)},
    }

    # OAM affine matrix parameter addresses (32 bytes per matrix)
    # Matrix 0: 0x07000000 + 0x20 = 0x07000020
    # Matrix 1: 0x07000000 + 0x28 = 0x07000028
    # etc. Each matrix is 32 bytes (8 u16 values)
    OAM_AFFINE_BASE = 0x07000000
    OAM_AFFINE_STRIDE = 32  # 32 bytes between matrices

    def parse_oam(self):
        """Parse OAM to build sprite display list.
        
        Reads all 128 sprite entries from OAM at 0x07000000-0x070003FF.
        Filters out sprites with Y=224+ (off-screen vertically).
        Returns list of sprite dictionaries with parsed attributes.
        """
        self.sprites = []
        
        for i in range(128):
            oam_addr = 0x07000000 + (i * 8)
            attr0 = self.memory.read_u16(oam_addr)
            attr1 = self.memory.read_u16(oam_addr + 2)
            attr2 = self.memory.read_u16(oam_addr + 4)
            
            # Extract Attribute 0 fields (GBATEK reference)
            y = attr0 & 0xFF  # Y position (0-255, 224+ = offscreen)
            mode = (attr0 >> 8) & 0x3  # 0=normal, 1=affine, 2=hidden, 3=affine+alt
            mosaic = (attr0 >> 10) & 0x1
            color_mode = (attr0 >> 11) & 0x1  # 0=4BPP, 1=8BPP
            shape = (attr0 >> 12) & 0x3  # 0=square, 1=wide, 2=tall, 3=reserved
            
            # Extract Attribute 1 fields
            x = (attr1 >> 8) & 0x1FF  # X position (0-511, wraps at 256 for display)
            flip_h = (attr1 >> 9) & 0x1  # Horizontal flip (when not affine)
            flip_v = (attr1 >> 10) & 0x1  # Vertical flip (when not affine)
            double_size = (attr1 >> 10) & 0x1  # Double size (when affine)
            rotate_scale = (attr1 >> 11) & 0x1  # Enable rotation/scaling
            size = (attr1 >> 14) & 0x3  # Size index
            
            # Extract Attribute 2 fields
            tile_num = attr2 & 0x3FF  # Tile number (0-1023)
            priority = (attr2 >> 10) & 0x3  # Priority (0-3, 0=highest)
            palette_num = (attr2 >> 12) & 0xF  # Palette number (0-15, 4BPP only)
            
            # Filter: Y >= 224 means sprite is off-screen vertically
            # X is 9-bit (0-511) but displayable range is 0-239
            if y >= 224:
                continue
            
            # Get sprite dimensions based on shape and size
            if shape in self.SPRITE_SIZES and size in self.SPRITE_SIZES[shape]:
                width, height = self.SPRITE_SIZES[shape][size]
            else:
                width, height = 8, 8  # Default fallback
            
            # Calculate affine matrix index (0-31, 4 groups of 8)
            matrix_idx = (i // 4) % 32
            
            self.sprite_list.append({
                "y": y,
                "x": x,
                "width": width,
                "height": height,
                "attr0": attr0,
                "attr1": attr1,
                "attr2": attr2,
                "mode": mode,
                "shape": shape,
                "size": size,
                "color_mode": color_mode,
                "rotate_scale": rotate_scale,
                "double_size": double_size,
                "flip_h": flip_h,
                "flip_v": flip_v,
                "tile_num": tile_num,
                "priority": priority,
                "palette_num": palette_num,
                "matrix_idx": matrix_idx,
            })

    def _render_sprites(self):
        """Render all sprites from OAM after background layers.
        
        Called from render_frame() after backgrounds are rendered.
        Handles:
        - 4BPP color mode (index 0 = transparent)
        - Sprite priority (higher priority sprites draw on top)
        - Basic rotation/scaling if affine mode enabled
        
        Note: 8BPP sprites use 256-color palette at 0x05000200 with direct color index lookup.
        """
        # Parse OAM to build sprite list
        self.parse_oam()
        
        # Sort sprites by priority (0=highest, 3=lowest)
        # Lower priority value = draw on top of higher priority
        self.sprite_list.sort(key=lambda s: s["priority"])
        
        for sprite in self.sprite_list:
            self._render_single_sprite(sprite)

    def _render_single_sprite(self, sprite: dict):
        """Render a single sprite to the framebuffer.
        
        Args:
            sprite: Sprite dictionary from parse_oam()
        """
        # Skip hidden sprites (mode 2)
        if sprite["mode"] == 2:
            return
        
        y = sprite["y"]
        x = sprite["x"]
        width = sprite["width"]
        height = sprite["height"]
        tile_num = sprite["tile_num"]
        palette_num = sprite["palette_num"]
        color_mode = sprite["color_mode"]

        # Apply rotation/scaling if enabled
        if sprite["rotate_scale"]:
            self._render_affine_sprite(sprite)
            return
        
        # Render normal (non-rotated) sprite
        # Calculate base tile address in VRAM
        # 4BPP tiles: 32 bytes each (8x8 pixels × 4 bits)
        # 8BPP tiles: 64 bytes each (8x8 pixels × 8 bits)
        vram_base = 0x06000000
        tile_size = 32 if color_mode == 0 else 64
        
        # VRAM tile addressing - DISPCNT bit 6 controls OBJ character VRAM mapping
        #   1D mapping (bit 6 == 1): stride 32, no VRAM offset
        #   2D mapping (bit 6 == 0): stride 32, BG2 VRAM offset (4K = 128 tiles for 32B, 64 for 64B)
        tiles_per_row = 32
        vram_offset = 0
        if not self.obj_character_vram_mapping:
            # 2D mode: OBJ characters use BG2 character VRAM region (4K offset)
            vram_offset = 128 if color_mode == 0 else 64
        
        for py in range(height):
            for px in range(width):
                # Calculate tile coordinates within sprite
                tile_x = px // 8
                tile_y = py // 8
                
                # Calculate local pixel within tile
                local_x = px % 8
                local_y = py % 8
                
                # Handle horizontal flip
                if sprite["flip_h"]:
                    local_x = 7 - local_x
                
                # Handle vertical flip
                if sprite["flip_v"]:
                    local_y = 7 - local_y
                
                # Calculate global tile number (with 2D mode offset if applicable)
                global_tile = tile_num + vram_offset + tile_y * tiles_per_row + tile_x
                
                # Calculate address in VRAM
                tile_addr = vram_base + global_tile * tile_size
                
                # Read pixel from tile
                if color_mode == 0:
                    # 4BPP: 2 pixels packed in 1 byte
                    byte_offset = local_y * 4 + (local_x // 2)
                    byte_val = self.memory.read_u8(tile_addr + byte_offset)
                    if local_x % 2 == 0:
                        color_idx = (byte_val >> 4) & 0x0F
                    else:
                        color_idx = byte_val & 0x0F
                else:
                    # 8BPP: 1 byte per pixel
                    byte_offset = local_y * 8 + local_x
                    color_idx = self.memory.read_u8(tile_addr + byte_offset)

                # Skip transparent pixels
                if color_idx == 0:
                    continue
                
                # Calculate screen position
                screen_x = x + px
                screen_y = y + py
                
                # Check bounds
                if not (0 <= screen_x < self.screen_width and 
                        0 <= screen_y < self.screen_height):
                    continue
                
                # Get color from sprite palette
                if color_mode == 0:
                    # 4BPP: 16-color sprite palette
                    sprite_palette_base = 0x05000200
                    palette_addr = sprite_palette_base + (sprite["palette_num"] * 32) + (color_idx * 2)
                else:
                    # 8BPP: 256-color sprite palette at 0x05000200
                    palette_addr = 0x05000200 + (color_idx * 2)
                
                try:
                    color_val = self.memory.read_u16(palette_addr)
                    r = _c5to8((color_val >> 0) & 0x1F)
                    g = _c5to8((color_val >> 5) & 0x1F)
                    b = _c5to8((color_val >> 10) & 0x1F)
                    
                    # Draw pixel directly to framebuffer
                    self.framebuffer[screen_y][screen_x] = (r, g, b)
                except Exception as e:
                    # Invalid palette entry - skip this pixel silently
                    # This can happen with corrupted VRAM or uninitialized palette data
                    continue

    def _render_affine_sprite(self, sprite: dict):
        """Render a sprite with rotation/scaling transformation.
        
        Reads affine transformation matrix from OAM and applies
        rotation and scaling to sprite pixels.
        
        Args:
            sprite: Sprite dictionary with rotate_scale=True
        """
        y = sprite["y"]
        x = sprite["x"]
        width = sprite["width"]
        height = sprite["height"]
        tile_num = sprite["tile_num"]
        matrix_idx = sprite["matrix_idx"]
        
        # Read affine matrix parameters from OAM
        # Matrix format: PA, PB, PC, PD (4 × s16.8 = 8 bytes)
        # Followed by X, Y position (2 × s19.8 = 4 bytes) - not used for sprites
        matrix_base = self.OAM_AFFINE_BASE + 0x20 + (matrix_idx * self.OAM_AFFINE_STRIDE)
        
        try:
            pa = self._read_oam_fixed16_8(matrix_base + 0)
            pb = self._read_oam_fixed16_8(matrix_base + 2)
            pc = self._read_oam_fixed16_8(matrix_base + 4)
            pd = self._read_oam_fixed16_8(matrix_base + 6)
        except:
            # Default to identity if read fails
            pa, pb, pc, pd = 1.0, 0.0, 0.0, 1.0
        
        # Center of sprite for rotation
        cx = width / 2
        cy = height / 2
        
        # VRAM tile addressing - check DISPCNT bit 6 (obj_character_vram_mapping)
        vram_base = 0x06000000
        tile_size = 32
        tiles_per_row = 32
        vram_offset = 0
        if not self.obj_character_vram_mapping:
            vram_offset = 128
        
        # Render sprite with affine transformation
        for py in range(height):
            for px in range(width):
                # Calculate position relative to center
                rel_x = px - cx
                rel_y = py - cy
                
                # Apply inverse affine transformation
                src_x = pa * rel_x + pb * rel_y + cx
                src_y = pc * rel_x + pd * rel_y + cy
                
                # Check if source pixel is within sprite bounds
                if not (0 <= src_x < width and 0 <= src_y < height):
                    continue
                
                # Calculate source tile and pixel
                tile_x = int(src_x) // 8
                tile_y = int(src_y) // 8
                local_x = int(src_x) % 8
                local_y = int(src_y) % 8
                
                # Calculate global tile number (with 2D mode offset if applicable)
                global_tile = tile_num + vram_offset + tile_y * tiles_per_row + tile_x
                tile_addr = vram_base + global_tile * tile_size
                
                # Read pixel from tile
                byte_offset = local_y * 4 + (local_x // 2)
                byte_val = self.memory.read_u8(tile_addr + byte_offset)
                
                if local_x % 2 == 0:
                    color_idx = (byte_val >> 4) & 0x0F
                else:
                    color_idx = byte_val & 0x0F
                
                # Skip transparent
                if color_idx == 0:
                    continue
                
                # Calculate screen position
                screen_x = x + px
                screen_y = y + py
                
                if not (0 <= screen_x < self.screen_width and 
                        0 <= screen_y < self.screen_height):
                    continue
                
                # Get color from sprite palette
                sprite_palette_base = 0x05000200
                palette_addr = sprite_palette_base + (sprite["palette_num"] * 32) + (color_idx * 2)
                
                try:
                    color_val = self.memory.read_u16(palette_addr)
                    r = _c5to8((color_val >> 0) & 0x1F)
                    g = _c5to8((color_val >> 5) & 0x1F)
                    b = _c5to8((color_val >> 10) & 0x1F)
                    self.framebuffer[screen_y][screen_x] = (r, g, b)
                except Exception as e:
                    # Error reading palette - skip this pixel
                    continue

    def _read_oam_fixed16_8(self, addr: int) -> float:
        """Read a s1.7.8 fixed-point value from OAM.
        
        Args:
            addr: Memory address to read from
            
        Returns:
            Float value representing the fixed-point number
        """
        value = self.memory.read_u16(addr)
        # Convert from s1.7.8 to float
        if value & 0x8000:
            value = value - 0x10000
        return value / 256.0
    # MMIO Register addresses
    REG_DISPCNT = 0x04000000
    REG_GREENSWP = 0x04000002
    REG_DISPSTAT = 0x04000004
    REG_VCOUNT = 0x04000006

    # BG Control registers
    REG_BG0CNT = 0x04000008
    REG_BG1CNT = 0x0400000A
    REG_BG2CNT = 0x0400000C
    REG_BG3CNT = 0x0400000E

    # BG Scroll registers
    REG_BG0HOFS = 0x04000010
    REG_BG0VOFS = 0x04000012
    REG_BG1HOFS = 0x04000014
    REG_BG1VOFS = 0x04000016
    REG_BG2HOFS = 0x04000018
    REG_BG2VOFS = 0x0400001A
    REG_BG3HOFS = 0x0400001C
    REG_BG3VOFS = 0x0400001E

    # BG2 Affine parameters
    REG_BG2PA = 0x04000020  # 16.16 fixed point
    REG_BG2PB = 0x04000022
    REG_BG2PC = 0x04000024
    REG_BG2PD = 0x04000026
    REG_BG2X = 0x04000028  # 8.8 fixed point
    REG_BG2Y = 0x0400002C

    # BG3 Affine parameters
    REG_BG3PA = 0x04000030  # 16.16 fixed point
    REG_BG3PB = 0x04000032
    REG_BG3PC = 0x04000034
    REG_BG3PD = 0x04000036
    REG_BG3X = 0x04000038  # 8.8 fixed point
    REG_BG3Y = 0x0400003C

    # Window registers
    REG_WIN0H = 0x04000040
    REG_WIN1H = 0x04000041
    REG_WIN0V = 0x04000042
    REG_WIN1V = 0x04000043
    REG_WININ = 0x04000048
    REG_WINOUT = 0x0400004A
    REG_WINOBJ = 0x0400004C

    # Mosaic register
    REG_MOSAIC = 0x0400004E  # Actually at 0x0400004E or 0x040000F4

    # Blending registers
    REG_BLDCNT = 0x04000050
    REG_BLDALPHA = 0x04000052
    REG_BLDY = 0x04000054
    REG_BLDWIN = 0x04000056
    REG_BLDWIN = 0x04000056  # Window blend settings (bits 0-3=win0_alpha, 4-7=win0_y, 8-11=win1_alpha, 12-15=win1_y)

    # Sprite/OBJ registers
    REG_DISPSTAT2 = 0x04000056

    # Additional MMIO for mosaic (correct address)
    REG_MOSAIC_EXT = 0x040000F4

    def __init__(self, memory):
        self.memory = memory

        # Asset storage (for runtime tilemap/palette/sprite data)
        self.palette_bg = []
        self.tiles_4bpp = []
        self.bg0_tilemap = [0] * 1024
        self.bg1_tilemap = [0] * 1024
        self.bg2_tilemap = [0] * 1024
        self.bg3_tilemap = [0] * 1024
        self.sprites = []

        # Display control - use sensible defaults (mode 3, all BGs)
        self.mode = 3
        self.display_frame_select = 0
        self.hblank_interval_free = False
        self.obj_character_vram_mapping = False
        self.forced_blank = False
        self.bg0_enable = True
        self.bg1_enable = True
        self.bg2_enable = True
        self.bg3_enable = True
        self.obj_enable = True
        self.win0_enable = False
        self.win1_enable = False
        self.obj_window_enable = False
        self.dispcnt = 0x0403
        
        # Numba JIT control for PPU
        self.numba_ppu_enabled = is_numba_ppu_enabled()
        
        # Cache for VRAM/palette data (updated each frame for JIT)
        self._vram_cache = None
        self._palette_cache = None
        
        # Screen dimensions
        self.screen_width = 240
        self.screen_height = 160

        # BG configurations (per layer)
        self.bg_priority = [0] * 4
        self.bg_char_block = [0] * 4
        self.bg_mosaic = [False] * 4
        self.bg256 = [False] * 4
        self.bg_screen_block = [0] * 4
        self.bg_affine = [False] * 4
        self.bg_size = [0] * 4  # 0=256x256, 1=512x256, 2=256x512, 3=512x512

        # BG scroll offsets
        self.bg_hofs = [0] * 4
        self.bg_vofs = [0] * 4

        # BG2 affine transformation parameters (read from MMIO)
        self.bg2_pa = 256  # 1.0 in 16.16 fixed point
        self.bg2_pb = 0
        self.bg2_pc = 0
        self.bg2_pd = 256  # 1.0 in 16.16 fixed point
        self.bg2_x = 0
        self.bg2_y = 0

        # BG3 affine transformation parameters (read from MMIO)
        self.bg3_pa = 256  # 1.0 in 16.16 fixed point
        self.bg3_pb = 0
        self.bg3_pc = 0
        self.bg3_pd = 256  # 1.0 in 16.16 fixed point
        self.bg3_x = 0
        self.bg3_y = 0

        # Blending configuration
        self.bldcnt = 0
        self.bldalpha_eva = 0
        self.bldalpha_evb = 0
        self.bldy = 0
        # Window blend configuration (from BLDWIN)
        self.bldwin_alpha_win0 = 0
        self.bldwin_y_win0 = 0
        self.bldwin_alpha_win1 = 0
        self.bldwin_y_win1 = 0

        # Window configuration
        self.win0_left = 0
        self.win0_right = 240
        self.win0_top = 0
        self.win0_bottom = 160
        self.win1_left = 0
        self.win1_right = 240
        self.win1_top = 0
        self.win1_bottom = 160

        # Window control bits (which layers enabled in each window)
        self.win0_in_enable = 0  # Bits: 0-3 = BG0-3, 4 = OBJ, 5 = Blend
        self.win0_out_enable = 0
        self.win1_in_enable = 0
        self.win1_out_enable = 0
        self.win_obj_enable = 0
        # WINOUT OBJ enable bit (OBJ displayed outside window area)
        self.winout_obj_enable = False

        # Mosaic configuration
        self.bg_mosaic_h = 1  # Horizontal size (1-16 pixels)
        self.bg_mosaic_v = 1  # Vertical size (1-16 pixels)
        self.obj_mosaic_h = 1
        self.obj_mosaic_v = 1
        self.mosaic_enabled = False

        # Display status
        self.vcount = 0
        self.vblank = False
        self.hblank = False
        self.vcount_trigger = False
        self.lyc = 0  # LY Compare register (bits 8-15 of DISPSTAT)
        self.vblank_irq_enable = False
        self.hblank_irq_enable = False
        self.vcount_irq_enable = False

        # Framebuffer
        self.framebuffer: List[List[Tuple[int, int, int]]] = []
        self._init_framebuffer()

    def get_surface(self) -> "pygame.Surface":
        """Convert framebuffer to pygame Surface for screenshot.

        Uses surfarray.blit_array() for bulk pixel transfer (~100x faster than set_at)."""
        import pygame

        try:
            import numpy as np

            arr = np.array(self.framebuffer, dtype=np.uint8)
            surf = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
            pygame.surfarray.blit_array(surf, arr)
            return surf
        except ImportError:
            # Fallback: per-pixel set_at if numpy not available
            surf = pygame.Surface((self.screen_width, self.screen_height))
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    color = self.framebuffer[y][x]
                    surf.set_at((x, y), color)
            return surf
    def _init_framebuffer(self):
        """Initialize the framebuffer"""
        self.framebuffer = [
            [(0, 0, 0) for _ in range(self.screen_width)] for _ in range(self.screen_height)
        ]

    def _get_vram_data(self) -> bytes:
        """Get VRAM data as bytes for JIT functions.

        Returns 128KB = 96KB VRAM + 16KB copy of start for double buffering.
        Mode 3/5 page 1 (0x0600A000 + 0x18000 max) reads contiguously at 0xA000-0x1BFFF.
        """
        vram_start = 0x06000000
        vram_size = 0x18000  # 96KB
        pad_size = 0x4000    # 16KB
        try:
            raw = bytearray(self.memory.read_range(vram_start, vram_size))
            raw.extend(raw[:pad_size])
            return bytes(raw)
        except:
            return b'\x00' * (vram_size + pad_size)

    def _get_palette_data(self) -> bytes:
        """Get palette RAM data as bytes for JIT functions."""
        palette_start = 0x05000000
        palette_end = 0x05000400
        try:
            return bytes(self.memory.read_range(palette_start, palette_end - palette_start))
        except:
            return b'\x00' * (palette_end - palette_start)

    def _decode_tile_4bpp_jit_wrapper(self, tile_index: int, char_block_base: int) -> List[int]:
        """JIT-accelerated 4BPP tile decoding."""
        vram_data = self._get_vram_data()
        char_block = char_block_base * 0x4000
        tile_offset = tile_index * 32
        return _decode_tile_4bpp_jit(vram_data, char_block + tile_offset)

    def _decode_tile_8bpp_jit_wrapper(self, tile_index: int, char_block_base: int) -> List[int]:
        """JIT-accelerated 8BPP tile decoding."""
        vram_data = self._get_vram_data()
        char_block = char_block_base * 0x4000
        tile_offset = tile_index * 64
        return _decode_tile_8bpp_jit(vram_data, char_block + tile_offset)

    def _get_palette_color_jit(self, palette_idx: int) -> Tuple[int, int, int]:
        """JIT-accelerated palette color lookup."""
        palette_data = self._get_palette_data()
        addr = palette_idx * 2
        color_val = _read_palette_jit(palette_data, addr)
        if color_val == 0 and palette_idx > 0:
            intensity = min(255, palette_idx * 17)
            return (intensity, intensity, intensity)
        r = _c5to8_jit((color_val >> 0) & 0x1F)
        g = _c5to8_jit((color_val >> 5) & 0x1F)
        b = _c5to8_jit((color_val >> 10) & 0x1F)
        return (r, g, b)

    def _get_palette_color_256_jit(self, palette_idx: int) -> Tuple[int, int, int]:
        """JIT-accelerated 256-color palette lookup."""
        palette_data = self._get_palette_data()
        addr = palette_idx * 2
        color_val = _read_palette_jit(palette_data, addr)
        if color_val == 0:
            return (palette_idx, palette_idx, palette_idx)
        r = _c5to8_jit((color_val >> 0) & 0x1F)
        g = _c5to8_jit((color_val >> 5) & 0x1F)
        b = _c5to8_jit((color_val >> 10) & 0x1F)
        return (r, g, b)

    def write_register(self, addr: int, value: int):
        """Handle MMIO writes to PPU registers"""

        # Handle affine matrix registers for BG2
        if addr == self.REG_BG2PA:
            self.bg2_pa = value
        elif addr == self.REG_BG2PB:
            self.bg2_pb = value
        elif addr == self.REG_BG2PC:
            self.bg2_pc = value
        elif addr == self.REG_BG2PD:
            self.bg2_pd = value
        elif addr == self.REG_BG2X:
            self.bg2_x = value & 0x0FFFFFFF  # 28-bit
        elif addr == self.REG_BG2Y:
            self.bg2_y = value & 0x0FFFFFFF

        # Handle affine matrix registers for BG3
        elif addr == self.REG_BG3PA:
            self.bg3_pa = value
        elif addr == self.REG_BG3PB:
            self.bg3_pb = value
        elif addr == self.REG_BG3PC:
            self.bg3_pc = value
        elif addr == self.REG_BG3PD:
            self.bg3_pd = value
        elif addr == self.REG_BG3X:
            self.bg3_x = value & 0x0FFFFFFF
        elif addr == self.REG_BG3Y:
            self.bg3_y = value & 0x0FFFFFFF

        # Window registers
        elif addr == self.REG_WIN0H:
            # WIN0H: bits 0-7 = left, bits 8-15 = right
            self.win0_left = (value >> 0) & 0xFF
            self.win0_right = (value >> 8) & 0xFF
        elif addr == self.REG_WIN1H:
            self.win1_left = (value >> 0) & 0xFF
            self.win1_right = (value >> 8) & 0xFF
        elif addr == self.REG_WIN0V:
            self.win0_top = (value >> 0) & 0xFF
            self.win0_bottom = (value >> 8) & 0xFF
        elif addr == self.REG_WIN1V:
            self.win1_top = (value >> 0) & 0xFF
            self.win1_bottom = (value >> 8) & 0xFF
        elif addr == self.REG_WININ:
            # WININ: bits 0-5 = window 0 in, bits 8-13 = window 1 in
            self.win0_in_enable = value & 0x3F
            self.win1_in_enable = (value >> 8) & 0x3F
        elif addr == self.REG_WINOUT:
            # WINOUT: bits 0-3 = BG0-3 out, bit 4 = OBJ out, bit 5 = Blend out
            self.win0_out_enable = value & 0x1F
            self.win1_out_enable = (value >> 8) & 0x1F
            self.winout_obj_enable = bool((value >> 4) & 1)
        elif addr == self.REG_WINOBJ:
            # WINOBJ: bits 0-5 = OBJ window enable
            self.win_obj_enable = value & 0x3F

        # Mosaic register
        elif addr == self.REG_MOSAIC or addr == self.REG_MOSAIC_EXT:
            self.bg_mosaic_h = ((value >> 0) & 0xF) + 1
            self.bg_mosaic_v = ((value >> 4) & 0xF) + 1
            self.obj_mosaic_h = ((value >> 8) & 0xF) + 1
            self.obj_mosaic_v = ((value >> 12) & 0xF) + 1
            self.mosaic_enabled = value != 0

        elif addr == self.REG_BLDCNT:
            self.bldcnt = value & 0x3FFF
        elif addr == self.REG_BLDALPHA:
            self.bldalpha_eva = value & 0x1F
            self.bldalpha_evb = (value >> 8) & 0x1F
        elif addr == self.REG_BLDY:
            self.bldy = value & 0x1F

        # DISPCNT - Display Control
        elif addr == self.REG_DISPCNT:
            mode = value & 0x7
            if mode > 5:
                mode = 5  # Invalid mode, prefer Mode 5 (bitmapped) for visibility
            self.mode = mode
            self.display_frame_select = (value >> 4) & 1
            self.hblank_interval_free = bool((value >> 5) & 1)
            self.obj_character_vram_mapping = bool((value >> 6) & 1)
            self.forced_blank = bool((value >> 7) & 1)
            self.bg0_enable = bool((value >> 8) & 1)
            self.bg1_enable = bool((value >> 9) & 1)
            self.bg2_enable = bool((value >> 10) & 1)
            self.bg3_enable = bool((value >> 11) & 1)
            self.obj_enable = bool((value >> 12) & 1)
            self.win0_enable = bool((value >> 13) & 1)
            self.win1_enable = bool((value >> 14) & 1)
            self.obj_window_enable = bool((value >> 15) & 1)

        # DISPSTAT - Display Status (write LYC and IRQ enables)
        elif addr == self.REG_DISPSTAT:
            self.lyc = (value >> 8) & 0xFF
            self.vblank_irq_enable = bool((value >> 3) & 1)
            self.hblank_irq_enable = bool((value >> 4) & 1)
            self.vcount_irq_enable = bool((value >> 5) & 1)

        # BG Control registers
        elif addr == self.REG_BG0CNT:
            self._write_bg_control(0, value)
        elif addr == self.REG_BG1CNT:
            self._write_bg_control(1, value)
        elif addr == self.REG_BG2CNT:
            self._write_bg_control(2, value)
        elif addr == self.REG_BG3CNT:
            self._write_bg_control(3, value)

        # BG Scroll registers
        elif addr == self.REG_BG0HOFS:
            self.bg_hofs[0] = value & 0x1FF
        elif addr == self.REG_BG0VOFS:
            self.bg_vofs[0] = value & 0x1FF
        elif addr == self.REG_BG1HOFS:
            self.bg_hofs[1] = value & 0x1FF
        elif addr == self.REG_BG1VOFS:
            self.bg_vofs[1] = value & 0x1FF
        elif addr == self.REG_BG2HOFS:
            self.bg_hofs[2] = value & 0x1FF
        elif addr == self.REG_BG2VOFS:
            self.bg_vofs[2] = value & 0x1FF
        elif addr == self.REG_BG3HOFS:
            self.bg_hofs[3] = value & 0x1FF
        elif addr == self.REG_BG3VOFS:
            self.bg_vofs[3] = value & 0x1FF

    def _write_bg_control(self, bg_num: int, value: int):
        """Write to BG control register"""
        if bg_num < 0 or bg_num > 3:
            return
        self.bg_priority[bg_num] = value & 0x3
        self.bg_char_block[bg_num] = (value >> 2) & 0x3
        self.bg_mosaic[bg_num] = bool((value >> 6) & 1)
        self.bg256[bg_num] = bool((value >> 7) & 1)
        self.bg_screen_block[bg_num] = (value >> 8) & 0x1F
        self.bg_affine[bg_num] = bool((value >> 13) & 1)
        self.bg_size[bg_num] = (value >> 14) & 0x3

    def read_register(self, addr: int) -> int:
        """Handle MMIO reads from PPU registers - returns 16-bit values"""

        # Handle affine matrix registers for BG2 (read as signed 16-bit)
        if addr == self.REG_BG2PA:
            return self.bg2_pa & 0xFFFF
        elif addr == self.REG_BG2PB:
            return self.bg2_pb & 0xFFFF
        elif addr == self.REG_BG2PC:
            return self.bg2_pc & 0xFFFF
        elif addr == self.REG_BG2PD:
            return self.bg2_pd & 0xFFFF

        # Handle affine matrix registers for BG3 (read as signed 16-bit)
        elif addr == self.REG_BG3PA:
            return self.bg3_pa & 0xFFFF
        elif addr == self.REG_BG3PB:
            return self.bg3_pb & 0xFFFF
        elif addr == self.REG_BG3PC:
            return self.bg3_pc & 0xFFFF
        elif addr == self.REG_BG3PD:
            return self.bg3_pd & 0xFFFF

        # Window registers
        elif addr == self.REG_WIN0H:
            return self.win0_left | (self.win0_right << 8)
        elif addr == self.REG_WIN1H:
            return self.win1_left | (self.win1_right << 8)
        elif addr == self.REG_WIN0V:
            return self.win0_top | (self.win0_bottom << 8)
        elif addr == self.REG_WIN1V:
            return self.win1_top | (self.win1_bottom << 8)
        elif addr == self.REG_WININ:
            return self.win0_in_enable | (self.win1_in_enable << 8)
        elif addr == self.REG_WINOUT:
            return self.win0_out_enable | ((1 if self.winout_obj_enable else 0) << 4) | (self.win1_out_enable << 8)
        elif addr == self.REG_WINOBJ:
            return self.win_obj_enable

        # Mosaic register
        elif addr == self.REG_MOSAIC or addr == self.REG_MOSAIC_EXT:
            mosaic = 0
            mosaic |= ((self.bg_mosaic_h - 1) & 0xF) << 0
            mosaic |= ((self.bg_mosaic_v - 1) & 0xF) << 4
            mosaic |= ((self.obj_mosaic_h - 1) & 0xF) << 8
            mosaic |= ((self.obj_mosaic_v - 1) & 0xF) << 12
            return mosaic

        elif addr == self.REG_BLDCNT:
            return self.bldcnt
        elif addr == self.REG_BLDALPHA:
            return self.bldalpha_eva | (self.bldalpha_evb << 8)
        elif addr == self.REG_BLDY:
            return self.bldy

        # DISPCNT read
        elif addr == self.REG_DISPCNT:
            dispcnt = 0
            dispcnt |= self.mode & 0x7
            dispcnt |= (self.display_frame_select & 1) << 4
            dispcnt |= (self.hblank_interval_free & 1) << 5
            dispcnt |= (self.obj_character_vram_mapping & 1) << 6
            dispcnt |= (self.forced_blank & 1) << 7
            dispcnt |= (self.bg0_enable & 1) << 8
            dispcnt |= (self.bg1_enable & 1) << 9
            dispcnt |= (self.bg2_enable & 1) << 10
            dispcnt |= (self.bg3_enable & 1) << 11
            dispcnt |= (self.obj_enable & 1) << 12
            dispcnt |= (self.win0_enable & 1) << 13
            dispcnt |= (self.win1_enable & 1) << 14
            dispcnt |= (self.obj_window_enable & 1) << 15
            return dispcnt

        # VCOUNT read
        elif addr == self.REG_VCOUNT:
            return self.vcount

        # DISPSTAT read
        elif addr == self.REG_DISPSTAT:
            dispstat = 0
            dispstat |= (self.vblank & 1) << 0
            dispstat |= (self.hblank & 1) << 1
            dispstat |= (self.vcount_trigger & 1) << 2
            dispstat |= (self.vblank_irq_enable & 1) << 3
            dispstat |= (self.hblank_irq_enable & 1) << 4
            dispstat |= (self.vcount_irq_enable & 1) << 5
            dispstat |= (self.lyc & 0xFF) << 8
            return dispstat

        # BG Control registers read
        elif addr == self.REG_BG0CNT:
            return self._read_bg_control(0)
        elif addr == self.REG_BG1CNT:
            return self._read_bg_control(1)
        elif addr == self.REG_BG2CNT:
            return self._read_bg_control(2)
        elif addr == self.REG_BG3CNT:
            return self._read_bg_control(3)

        # BG Scroll read
        elif addr == self.REG_BG0HOFS:
            return self.bg_hofs[0]
        elif addr == self.REG_BG0VOFS:
            return self.bg_vofs[0]
        elif addr == self.REG_BG1HOFS:
            return self.bg_hofs[1]
        elif addr == self.REG_BG1VOFS:
            return self.bg_vofs[1]
        elif addr == self.REG_BG2HOFS:
            return self.bg_hofs[2]
        elif addr == self.REG_BG2VOFS:
            return self.bg_vofs[2]
        elif addr == self.REG_BG3HOFS:
            return self.bg_hofs[3]
        elif addr == self.REG_BG3VOFS:
            return self.bg_vofs[3]

        # BG2 affine X/Y read
        elif addr == self.REG_BG2X:
            return self.bg2_x & 0xFFFF
        elif addr == self.REG_BG2X + 2:
            return (self.bg2_x >> 16) & 0xFFFF
        elif addr == self.REG_BG2Y:
            return self.bg2_y & 0xFFFF
        elif addr == self.REG_BG2Y + 2:
            return (self.bg2_y >> 16) & 0xFFFF

        # BG3 affine X/Y read
        elif addr == self.REG_BG3X:
            return self.bg3_x & 0xFFFF
        elif addr == self.REG_BG3X + 2:
            return (self.bg3_x >> 16) & 0xFFFF
        elif addr == self.REG_BG3Y:
            return self.bg3_y & 0xFFFF
        elif addr == self.REG_BG3Y + 2:
            return (self.bg3_y >> 16) & 0xFFFF

        # Unmapped MMIO register — standard GBA behavior returns 0 for undefined addresses
        return 0

    def _read_bg_control(self, bg_num: int) -> int:
        """Read BG control register"""
        if bg_num < 0 or bg_num > 3:
            # Invalid BG number - return 0
            return 0
        value = 0
        value |= self.bg_priority[bg_num] & 0x3
        value |= (self.bg_char_block[bg_num] & 0x3) << 2
        value |= (self.bg_mosaic[bg_num] & 1) << 6
        value |= (self.bg256[bg_num] & 1) << 7
        value |= (self.bg_screen_block[bg_num] & 0x1F) << 8
        value |= (self.bg_affine[bg_num] & 1) << 13
        value |= (self.bg_size[bg_num] & 0x3) << 14
        return value

    def _decode_tile_4bpp(
    self,
    tile_index: int,
     char_block_base: int) -> List[int]:
        """Decode a 4bpp tile into 64 palette indices (8x8 pixels).

        Args:
            tile_index: Tile number (0-511 for 4bpp mode)
            char_block_base: Character Block Base Address (0-3)

        Returns:
            List of 64 palette indices (0-15) for each pixel in row-major order
        """
        # GBA VRAM structure for 4bpp tiles:
        # Each tile is 64 bytes (512 bits), storing 8x8 pixels with 4 bits per pixel
        # Each row of 8 pixels requires 4 bytes (32 bits)
        # Total: 8 rows * 4 bytes = 32 bytes per tile in standard mapping

        # VRAM address calculation
        vram_base = 0x06000000
        char_block = char_block_base * 0x4000  # Each block is 16KB
        # 32 bytes per 4bpp tile (lower resolution mapping)
        tile_offset = tile_index * 32

        addr = vram_base + char_block + tile_offset

        palette_indices = []

        for row in range(8):
            for col in range(8):
                byte_offset = row * 4 + (col // 2)
                byte_addr = addr + byte_offset

                try:
                    byte_val = self.memory.read_u8(byte_addr)

                    if col % 2 == 0:
                        color_idx = (byte_val >> 4) & 0x0F
                    else:
                        color_idx = byte_val & 0x0F

                    palette_indices.append(color_idx)
                except:
                    palette_indices.append(0)

        return palette_indices

    
    def _decode_tile_8bpp(
        self,
        tile_index: int,
        char_block_base: int) -> List[int]:
        """Decode an 8BPP tile into 64 palette indices (8x8 pixels).

        Args:
            tile_index: Tile number (0-255 for 8bpp mode)
            char_block_base: Character Block Base Address (0-1 for 8bpp)

        Returns:
            List of 64 palette indices (0-255) for each pixel in row-major order
        """
        # GBA VRAM structure for 8BPP tiles:
        # Each tile is 64 bytes, storing 8x8 pixels with 8 bits per pixel
        # Each row of 8 pixels requires 8 bytes (1 byte per pixel)
        # Total: 8 rows * 8 bytes = 64 bytes per tile

        # VRAM address calculation
        vram_base = 0x06000000
        char_block = char_block_base * 0x4000  # Each block is 16KB
        tile_offset = tile_index * 64  # 64 bytes per 8BPP tile

        addr = vram_base + char_block + tile_offset

        palette_indices = []

        for row in range(8):
            for col in range(8):
                byte_addr = addr + (row * 8) + col

                try:
                    color_idx = self.memory.read_u8(byte_addr)
                    palette_indices.append(color_idx)
                except:
                    palette_indices.append(0)

        return palette_indices

    def _get_palette_color(self, palette_idx: int) -> Tuple[int, int, int]:
        """Get RGB color from background palette.

        Args:
            palette_idx: Palette entry index (0-15 for BG palettes)

        Returns:
            Tuple of (R, G, B) values (0-255 each)
        """
        # GBA background palettes start at 0x05000000
        # Each palette entry is 2 bytes (15-bit RGB555)
        # Total: 256 entries = 512 bytes (16 palettes * 16 entries * 2 bytes)

        palette_addr = 0x05000000 + (palette_idx * 2)

        try:
            color_val = self.memory.read_u16(palette_addr)
            
            # If palette RAM is uninitialized (all zeros), generate default grayscale
            # This handles ROMs that don't explicitly initialize palette RAM
            if color_val == 0 and palette_idx > 0:
                # Generate grayscale gradient: index 1 = dark, index 15 = bright
                intensity = min(255, (palette_idx * 17))
                return (intensity, intensity, intensity)
            
            r = _c5to8((color_val >> 0) & 0x1F)
            g = _c5to8((color_val >> 5) & 0x1F)
            b = _c5to8((color_val >> 10) & 0x1F)
            return (r, g, b)
        except:
            return (255, 255, 255)  # White fallback for debugging

    def _apply_affine_transform(
        self, bg_num: int, x: int, y: int) -> Tuple[int, int]:
        """Apply affine transformation to coordinates using MMIO register values"""

        if bg_num == 2:
            pa = self._fixed_to_float(self.bg2_pa)
            pb = self._fixed_to_float(self.bg2_pb)
            pc = self._fixed_to_float(self.bg2_pc)
            pd = self._fixed_to_float(self.bg2_pd)
            offset_x = self._fixed_8_8_to_float(self.bg2_x)
            offset_y = self._fixed_8_8_to_float(self.bg2_y)
        elif bg_num == 3:
            pa = self._fixed_to_float(self.bg3_pa)
            pb = self._fixed_to_float(self.bg3_pb)
            pc = self._fixed_to_float(self.bg3_pc)
            pd = self._fixed_to_float(self.bg3_pd)
            offset_x = self._fixed_8_8_to_float(self.bg3_x)
            offset_y = self._fixed_8_8_to_float(self.bg3_y)
        else:
            return x, y

        # Apply transformation matrix
        new_x = pa * x + pb * y + offset_x
        new_y = pc * x + pd * y + offset_y

        return int(new_x), int(new_y)

    def _fixed_to_float(self, value: int) -> float:
        """Convert 16.16 fixed point to float"""
        # Handle signed value
        if value & 0x8000:
            value = value - 0x10000
        return value / 65536.0

    def _fixed_8_8_to_float(self, value: int) -> float:
        """Convert 8.8 fixed point to float"""
        if value & 0x800000:
            value = value - 0x1000000
        return value / 256.0

    def _is_in_window(self, x: int, y: int, win_num: int) -> bool:
        """Check if coordinate is inside specified window"""
        if win_num == 0:
            left, right = self.win0_left, self.win0_right
            top, bottom = self.win0_top, self.win0_bottom
        elif win_num == 1:
            left, right = self.win1_left, self.win1_right
            top, bottom = self.win1_top, self.win1_bottom
        else:
            return False

        # Handle edge cases
        if left <= right:
            in_h = left <= x <= right
        else:
            in_h = x >= left or x <= right

        if top <= bottom:
            in_v = top <= y <= bottom
        else:
            in_v = y >= top or y <= bottom

        return in_h and in_v

    def _is_in_obj_window(self, x: int, y: int) -> bool:
        OAM_BASE = 0x07000000
        NUM_SPRITES = 128

        for sprite_idx in range(NUM_SPRITES):
            sprite_addr = OAM_BASE + (sprite_idx * 8)
            try:
                attr0 = self.memory.read_u16(sprite_addr + 0)
                attr1 = self.memory.read_u16(sprite_addr + 2)
            except:
                continue

            obj_mode = (attr0 >> 10) & 3
            if obj_mode != 3:
                continue

            sprite_y = attr0 & 0xFF
            sprite_x = attr1 & 0x1FF
            height = ((attr0 >> 12) & 7) * 8 + 8
            width = ((attr1 >> 8) & 0x3) * 8 + 8

            if width > 64:
                width = 64
            if height > 64:
                height = 64

            if sprite_y <= y < sprite_y + height:
                if sprite_x <= x < sprite_x + width:
                    return True

        return False

    def _get_window_layer_enable(self, x: int, y: int) -> int:
        """Get which layers are enabled at the given coordinate based on windows"""
        # Check WIN0 first
        if self.win0_enable and self._is_in_window(x, y, 0):
            return self.win0_in_enable

        # Check WIN1
        if self.win1_enable and self._is_in_window(x, y, 1):
            return self.win1_in_enable

        if self.obj_window_enable:
            if self._is_in_obj_window(x, y):
                return 0x10 if self.winout_obj_enable else 0
            else:
                return 0x10 if (self.win0_out_enable & 0x10) else 0

        # Default to out enables
        if self.win0_enable or self.win1_enable:
            return self.win0_out_enable

        return 0x3F  # All enabled by default (BG0-3 + OBJ + Blend)

    def _apply_mosaic(self, x: int, y: int,
                      is_obj: bool = False) -> Tuple[int, int]:
        """Apply mosaic effect to pixel coordinates"""
        if not self.mosaic_enabled:
            return x, y

        if is_obj:
            h_size = self.obj_mosaic_h
            v_size = self.obj_mosaic_v
        else:
            h_size = self.bg_mosaic_h
            v_size = self.bg_mosaic_v

        # Snap coordinates to block boundaries
        mosaic_x = (x // h_size) * h_size
        mosaic_y = (y // v_size) * v_size

        return mosaic_x, mosaic_y

    def render_frame(self):
        import sys
        print(
    f"DEBUG: render_frame called, frame_count={
        getattr(
            self,
            '_debug_frame',
            0)}",
             file=sys.stderr)
        """Render one frame of graphics with Windows, Mosaic, and all effects"""
        # Update VCOUNT
        self.vcount = (self.vcount + 1) % self.screen_height
        self.vblank = self.vcount >= self.screen_height

        # VCount compare: check if VCOUNT == LYC
        was_trigger = self.vcount_trigger
        self.vcount_trigger = (self.vcount == self.lyc)

        # Fire VCount interrupt if enabled and trigger just occurred
        if self.vcount_trigger and not was_trigger and self.vcount_irq_enable:
            dispstat_addr = 0x04000004
            current_dispstat = self.memory.read_u16(dispstat_addr)
            self.memory.write_u16(dispstat_addr, current_dispstat | 0x0004)
            if hasattr(self.memory, '_interrupts') and self.memory._interrupts is not None:
                self.memory._interrupts.vcounter_irq()

        # VBlank interrupt: Set z=1 to unblock VBlank wait loops in generated code
        # This simulates the VBlank interrupt flag that BIOS checks
        import sys

        if "generated_rom" in sys.modules:
            generated = sys.modules["generated_rom"]
            if hasattr(generated, "z"):
                generated.z = 1  # Signal VBlank
            else:
                # Create z variable if it doesn't exist
                generated.z = 1

        # Also set via MMIO at DISPSTAT (0x04000004) bit 0
        # Read current DISPSTAT, set VBlank flag, write back
        dispstat_addr = 0x04000004
        current_dispstat = self.memory.read_u16(dispstat_addr)
        if self.vblank:
            self.memory.write_u16(dispstat_addr, (current_dispstat | 0x0001) & ~0x0002)
            if hasattr(self.memory, '_interrupts') and self.memory._interrupts is not None:
                self.memory._interrupts.vblank_irq()
            # Fire DMA VBlank triggers (DMA with timing=VBlank starts at VBlank)
            if hasattr(self.memory, '_dma') and self.memory._dma is not None:
                self.memory._dma.vblank_fire()
        else:
            self.memory.write_u16(dispstat_addr, (current_dispstat & ~0x0001) | 0x0002)
            if self.hblank_irq_enable:
                if hasattr(self.memory, '_interrupts') and self.memory._interrupts is not None:
                    self.memory._interrupts.hblank_irq()
            # Fire DMA HBlank triggers (DMA with timing=HBlank starts at HBlank)
            if hasattr(self.memory, '_dma') and self.memory._dma is not None:
                self.memory._dma.hblank_fire()

        # Note: forced_blank is a display control flag but we still render
        # Don't return early - let rendering proceed even if forced_blank is set
        # This ensures framebuffer gets populated for screenshots

        # Clear framebuffer
        self._init_framebuffer()

        # Get current display mode
        mode = self.mode

        # Render based on mode
        if mode == 0:
            self._render_mode0()
        elif mode == 1:
            self._render_mode1()
        elif mode == 2:
            self._render_mode2()
        elif mode == 3:
            self._render_mode3()
        elif mode == 4:
            self._render_mode4()
        elif mode == 5:
            self._render_mode5()

        # Apply blending if enabled
        if self._blending_enabled():
            self._apply_blending_to_framebuffer()

    def _render_mode0(self):
        """Render Mode 0: Text backgrounds (BG0-3) with priority-based compositing"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                # Check window enable
                layer_enable = self._get_window_layer_enable(x, y)

                # Collect candidate pixels from all backgrounds
                candidates = []  # (priority, color) - lower priority number = higher priority

                for bg in range(4):
                    if not getattr(self, f"bg{bg}_enable"):
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    # Apply mosaic if enabled
                    mx, my = self._apply_mosaic(x, y, is_obj=False)

                    # Calculate tile coordinates
                    tile_x = (mx + self.bg_hofs[bg]) % 256
                    tile_y = (my + self.bg_vofs[bg]) % 256

                    tilemap = getattr(self, f"bg{bg}_tilemap")
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x

                    if tilemap_index >= 0 and tilemap_index < len(tilemap):
                        tilemap_entry = tilemap[tilemap_index]
                        tile_index = tilemap_entry & 0x03FF
                        palette_num = (tilemap_entry >> 12) & 0x0F

                        # Calculate pixel offset within tile
                        pixel_x = tile_x % 8
                        pixel_y = tile_y % 8

                        # Decode tile using _decode_tile_4bpp
                        char_block_base = self.bg_char_block[bg]
                        # Check if BG is in 8BPP mode (bits 2-3 of BGxCNT)
                        bg_cnt_addr = 0x04000008 + bg * 2  # BG0CNT=0x04000008, BG1CNT=0x0400000A, etc.
                        bg_cnt = self.memory.read_u16(bg_cnt_addr)
                        bpp_mode = (bg_cnt >> 2) & 0x03  # Bits 2-3: 00=4BPP, 01=8BPP

                        if bpp_mode == 1:  # 8BPP mode
                            if is_numba_ppu_enabled():
                                palette_indices = self._decode_tile_8bpp_jit_wrapper(tile_index, char_block_base)
                            else:
                                palette_indices = self._decode_tile_8bpp(tile_index, char_block_base)
                        else:  # 4BPP mode
                            if is_numba_ppu_enabled():
                                palette_indices = self._decode_tile_4bpp_jit_wrapper(tile_index, char_block_base)
                            else:
                                palette_indices = self._decode_tile_4bpp(tile_index, char_block_base)

                        # Calculate linear index in 8x8 tile
                        pixel_index = pixel_y * 8 + pixel_x

                        if pixel_index < len(palette_indices):
                            color_idx = palette_indices[pixel_index]

                            # Get color from palette using JIT-accelerated lookup
                            if is_numba_ppu_enabled():
                                color = self._get_palette_color_jit(color_idx)
                            else:
                                color = self._get_palette_color(color_idx)
                            # Only add non-transparent pixels (color_idx != 0)
                            if color_idx != 0:
                                # Get priority from BGxCNT (bits 0-1)
                                priority = bg_cnt & 0x03
                                candidates.append((priority, color))

                # Render highest priority non-transparent pixel
                if candidates:
                    candidates.sort(key=lambda c: c[0])
                    self.framebuffer[y][x] = candidates[0][1]

        # Render sprites from OAM at 0x07000000 AFTER all BG layers
        if self.obj_enable:
            self._render_sprites(0x3F)

    def _render_mode1(self):
        """Render Mode 1: Text BG0/1 + Affine BG2/3"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                # Render BG layers in priority order (0, 1, 2, 3)
                for bg in range(4):
                    if not getattr(
    self, f"bg{bg}_enable"):  # DISABLED: render even if bg disabled
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    if bg in [0, 1]:
                        # Text mode: direct tile lookup from tilemap
                        mx, my = self._apply_mosaic(x, y, is_obj=False)
                        tile_x = (mx + self.bg_hofs[bg]) % 256
                        tile_y = (my + self.bg_vofs[bg]) % 256

                        # Calculate tile index and pixel offset
                        tilemap = getattr(self, f"bg{bg}_tilemap")
                        tilemap_x = tile_x // 8
                        tilemap_y = tile_y // 8
                        tilemap_index = tilemap_y * 32 + tilemap_x

                        if tilemap_index >= 0 and tilemap_index < len(tilemap):
                            tilemap_entry = tilemap[tilemap_index]
                            tile_index = tilemap_entry & 0x03FF
                            palette_num = (tilemap_entry >> 12) & 0x0F

                            # Get tile data
                            pixel_x = tile_x % 8
                            pixel_y = tile_y % 8

                            # Check BGxCNT bit 7 for 8BPP mode
                            if self.bg256[bg]:
                                palette_indices = self._decode_tile_8bpp(tile_index, self.bg_char_block[bg])
                            else:
                                palette_indices = self._decode_tile_4bpp(tile_index, self.bg_char_block[bg])
                            color_idx = palette_indices[pixel_y * 8 + pixel_x]
                            if color_idx > 0:
                                if self.bg256[bg]:
                                    color = self._get_palette_color_256(color_idx)
                                else:
                                    color = self._get_palette_color(palette_num * 16 + color_idx)
                                if color != (0, 0, 0):
                                    self.framebuffer[y][x] = color
                else:
                    # Affine mode (BG2, BG3)
                        aff_x, aff_y = self._apply_affine_transform(bg, x, y)
                        mx, my = self._apply_mosaic(
    int(aff_x), int(aff_y), is_obj=False)

                        tile_x = mx % 256
                        tile_y = my % 256

                        tilemap = getattr(self, f"bg{bg}_tilemap")
                        tilemap_x = tile_x // 8
                        tilemap_y = tile_y // 8
                        tilemap_index = tilemap_y * 32 + tilemap_x

                        if tilemap_index >= 0 and tilemap_index < len(tilemap):
                            tilemap_entry = tilemap[tilemap_index]
                            tile_index = tilemap_entry & 0x03FF
                            palette_num = (tilemap_entry >> 12) & 0x0F

                            pixel_x = tile_x % 8
                            pixel_y = tile_y % 8

                            # Check bg256[bg] to determine 8BPP vs 4BPP mode
                            if self.bg256[bg]:
                                palette_indices = self._decode_tile_8bpp(tile_index, self.bg_char_block[bg])
                            else:
                                palette_indices = self._decode_tile_4bpp(tile_index, self.bg_char_block[bg])
                            color_idx = palette_indices[pixel_y * 8 + pixel_x]
                            if color_idx > 0:
                                if self.bg256[bg]:
                                    color = self._get_palette_color_256(color_idx)
                                else:
                                    color = self._get_palette_color(palette_num * 16 + color_idx)
                                if color != (0, 0, 0):
                                    self.framebuffer[y][x] = color
                # print(f"DEBUG: Wrote color {color} at ({x}, {y})", file=sys.stderr)

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _render_mode2(self):
        """Render Mode 2: Affine BG2/3 only"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                for bg in range(4):
                    if not getattr(self, f"bg{bg}_enable"):  # DISABLED: render even if bg disabled
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    aff_x, aff_y = self._apply_affine_transform(bg, x, y)
                    mx, my = self._apply_mosaic(int(aff_x), int(aff_y), is_obj=False)

                    tile_x = mx % 256
                    tile_y = my % 256

                    tilemap = getattr(self, f"bg{bg}_tilemap")
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x

                    if tilemap_index >= 0 and tilemap_index < len(tilemap):
                        tilemap_entry = tilemap[tilemap_index]
                        tile_index = tilemap_entry & 0x03FF
                        palette_num = (tilemap_entry >> 12) & 0x0F

                        pixel_x = tile_x % 8
                        pixel_y = tile_y % 8

                        if self.bg256[bg]:
                            palette_indices = self._decode_tile_8bpp(tile_index, self.bg_char_block[bg])
                        else:
                            palette_indices = self._decode_tile_4bpp(tile_index, self.bg_char_block[bg])
                        color_idx = palette_indices[pixel_y * 8 + pixel_x]
                        if color_idx > 0:
                            if self.bg256[bg]:
                                color = self._get_palette_color_256(color_idx)
                            else:
                                color = self._get_palette_color(palette_num * 16 + color_idx)
                            if color != (0, 0, 0):
                                self.framebuffer[y][x] = color
                # print(f"DEBUG: Wrote color {color} at ({x}, {y})", file=sys.stderr)

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _render_mode3(self):
        """Render Mode 3: 240x160 bitmap mode with double buffering and mosaic support"""
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        if is_numba_ppu_enabled():
            vram_data = self._get_vram_data()
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    mosaic_x, mosaic_y = self._apply_mosaic(x, y, is_obj=False)
                    offset = (mosaic_y * 240 + mosaic_x) * 2
                    color_val = _read_color_jit(vram_data, vram_base + offset)
                    r = _c5to8_jit((color_val >> 0) & 0x1F)
                    g = _c5to8_jit((color_val >> 5) & 0x1F)
                    b = _c5to8_jit((color_val >> 10) & 0x1F)
                    self.framebuffer[y][x] = (r, g, b)
        else:
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    mosaic_x, mosaic_y = self._apply_mosaic(x, y, is_obj=False)
                    offset = (mosaic_y * 240 + mosaic_x) * 2
                    addr = vram_base + offset
                    try:
                        color_val = self.memory.read_u16(addr)
                        r = _c5to8((color_val >> 0) & 0x1F)
                        g = _c5to8((color_val >> 5) & 0x1F)
                        b = _c5to8((color_val >> 10) & 0x1F)
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _render_mode4(self):
        """Render Mode 4: 240x160 8BPP bitmap with double buffering and mosaic support"""
        # Mode 4: 8BPP bitmap, each pixel = 1 byte palette index
        # Page 0: 0x06000000 (0x6000 bytes = 240*160)
        # Page 1: 0x0600A000
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                # Apply mosaic if enabled (snap to mosaic block)
                mosaic_x, mosaic_y = self._apply_mosaic(x, y, is_obj=False)

                # Mode 4: 1 byte per pixel (8-bit palette index)
                offset = mosaic_y * 240 + mosaic_x
                addr = vram_base + offset

                try:
                    palette_idx = self.memory.read_u8(addr)
                    if is_numba_ppu_enabled():
                        color = self._get_palette_color_256_jit(palette_idx)
                    else:
                        color = self._get_palette_color_256(palette_idx)
                    self.framebuffer[y][x] = color
                except:
                    self.framebuffer[y][x] = (0, 0, 0)

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _get_palette_color_256(self, palette_idx: int) -> Tuple[int, int, int]:
        """Get RGB color from 256-color palette (Mode 4)."""
        palette_addr = 0x05000000 + (palette_idx * 2)

        try:
            color_val = self.memory.read_u16(palette_addr)
            
            # If palette RAM is uninitialized (all zeros), generate default grayscale
            if color_val == 0:
                intensity = palette_idx
                return (intensity, intensity, intensity)
            
            r = _c5to8((color_val >> 0) & 0x1F)
            g = _c5to8((color_val >> 5) & 0x1F)
            b = _c5to8((color_val >> 10) & 0x1F)
            return (r, g, b)
        except:
            return (0, 0, 0)

    def _render_mode5(self):
        """Render Mode 5: 160x128 bitmap mode with double buffering and mosaic support"""
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        for y in range(128):
            for x in range(160):
                layer_enable = self._get_window_layer_enable(x, y)

                # Apply mosaic if enabled (snap to mosaic block)
                mosaic_x, mosaic_y = self._apply_mosaic(x, y, is_obj=False)

                if True:  # Bitmap Mode 5 renders regardless
                    offset = (mosaic_y * 160 + mosaic_x) * 2
                    addr = vram_base + offset

                    try:
                        color_val = self.memory.read_u16(addr)
                        r = _c5to8((color_val >> 0) & 0x1F)
                        g = _c5to8((color_val >> 5) & 0x1F)
                        b = _c5to8((color_val >> 10) & 0x1F)
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _blending_enabled(self) -> bool:
        return (self.bldcnt & 0x3FFF) != 0

    def _apply_blending_to_framebuffer(self):
        blend_mode = (self.bldcnt >> 6) & 0x3
        
        if blend_mode == 1:
            eva = min(self.bldalpha_eva, 16)
            evb = min(self.bldalpha_evb, 16)
            if eva > 0 or evb > 0:
                # Read backdrop color from BDCNT register (bits 12-15 = BG backdrop, bits 0-3 = OBJ backdrop)
                bldcnt = self.bldcnt
                bg_backdrop_idx = (bldcnt >> 12) & 0xF
                bg_backdrop_r = 31  # Default
                bg_backdrop_g = 31
                bg_backdrop_b = 31
                if 0 <= bg_backdrop_idx < 16:
                    # Read backdrop color from palette RAM (0x05000000)
                    try:
                        backdrop_color_val = self.memory.read_u16(0x05000000 + (bg_backdrop_idx * 2))
                        bg_backdrop_r = _c5to8((backdrop_color_val >> 0) & 0x1F)
                        bg_backdrop_g = _c5to8((backdrop_color_val >> 5) & 0x1F)
                        bg_backdrop_b = _c5to8((backdrop_color_val >> 10) & 0x1F)
                    except:
                        pass
                
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        r, g, b = self.framebuffer[y][x]
                        bg_r = bg_backdrop_r
                        bg_g = bg_backdrop_g
                        bg_b = bg_backdrop_b
                        r = (r * eva + bg_r * evb) // 16
                        g = (g * eva + bg_g * evb) // 16
                        b = (b * eva + bg_b * evb) // 16
                        self.framebuffer[y][x] = (r, g, b)
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    r = min(int(r + (255 - r) * factor), 255)
                    g = min(int(g + (255 - g) * factor), 255)
                    b = min(int(b + (255 - b) * factor), 255)
                    self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 3:
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    r = int(r * (1 - factor))
                    g = int(g * (1 - factor))
                    b = int(b * (1 - factor))
                    self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 2:
            # Brightness increase: (src * (16 - Evy)) / 16
            evy = min(self.bldy, 16)
            factor = evy / 16.0
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    r = int(r * (1.0 - factor))
                    g = int(g * (1.0 - factor))
                    b = int(b * (1.0 - factor))
                    self.framebuffer[y][x] = (r, g, b)

    def save_screenshot(self, path: str):
        """Save current framebuffer as screenshot"""
        try:
            import PIL.Image

            img = PIL.Image.new("RGB", (self.screen_width, self.screen_height))
            pixels = img.load()
            for y in range(self.screen_height):
                for x in range(self.screen_width):
                    r, g, b = self.framebuffer[y][x]
                    pixels[x, y] = (r, g, b)
            img.save(path)
        except ImportError:
            # Fallback if PIL not available - create PPM file
            with open(path.replace(".png", ".ppm"), "wb") as f:
                f.write(f"P6 {self.screen_width} {self.screen_height} 255\n".encode())
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        r, g, b = self.framebuffer[y][x]
                        f.write(bytes([r, g, b]))

    def _is_affine_sprite(self, attr1: int) -> bool:
        """Check if sprite uses affine transformation (attr1 bit 11)"""
        return bool((attr1 >> 11) & 1)

    def _get_sprite_affine_params(self, sprite_index: int) -> Tuple[int, int, int, int, int, int]:
        affine_index = (sprite_index >> 1) & 0x1F
        affine_base = 0x07000020 + (affine_index * 8)
        pa = self.memory.read_u16(affine_base + 0)
        pb = self.memory.read_u16(affine_base + 2)
        pc = self.memory.read_u16(affine_base + 4)
        pd = self.memory.read_u16(affine_base + 6)
        center_x = 0
        center_y = 0
        return pa, pb, pc, pd, center_x, center_y

    def _apply_affine_transform_sprite(
        self, x: int, y: int, pa: int, pb: int, pc: int, pd: int, center_x: int, center_y: int
    ) -> Tuple[int, int]:
        pa_float = self._fixed_8_8_to_float(pa)
        pb_float = self._fixed_8_8_to_float(pb)
        pc_float = self._fixed_8_8_to_float(pc)
        pd_float = self._fixed_8_8_to_float(pd)
        new_x = pa_float * (x - center_x) + pb_float * (y - center_y) + center_x
        new_y = pc_float * (x - center_x) + pd_float * (y - center_y) + center_y
        return int(new_x), int(new_y)

    def _render_sprite_line(
        self,
        sprite_x: int,
        sprite_y: int,
        line: int,
        width: int,
        height: int,
        attr0: int,
        attr1: int,
    ) -> List[Tuple[int, int, int]]:
        colors = []

        if self._is_affine_sprite(attr1):
            pa, pb, pc, pd, _, _ = self._get_sprite_affine_params(attr1)
            sprite_width = ((attr1 >> 8) & 0x3) * 8 + 8 if width > 8 else 8
            center_x = sprite_width // 2
            center_y = height // 2

            local_line = line - sprite_y
            for px in range(width):
                local_x = px
                src_x, src_y = self._apply_affine_transform_sprite(
                    local_x, local_line, pa, pb, pc, pd, center_x, center_y
                )

                if 0 <= src_x < sprite_width and 0 <= src_y < height:
                    vram_addr = 0x06014000 + (src_y * sprite_width + src_x) * 2
                    try:
                        color_val = self.memory.read_u16(vram_addr)
                        r = _c5to8((color_val >> 0) & 0x1F)
                        g = _c5to8((color_val >> 5) & 0x1F)
                        b = _c5to8((color_val >> 10) & 0x1F)
                        if color_val & 0x8000:
                            colors.append((r, g, b))
                        else:
                            colors.append(None)
                    except:
                        colors.append(None)
                else:
                    colors.append(None)
        else:
            for px in range(width):
                if sprite_x + px < 0 or sprite_x + px >= self.screen_width:
                    colors.append(None)
                    continue
                if line < 0 or line >= self.screen_height:
                    colors.append(None)
                    continue
                vram_addr = 0x06014000 + (line * width + px) * 2
                try:
                    color_val = self.memory.read_u16(vram_addr)
                    if color_val & 0x8000:
                        r = _c5to8((color_val >> 0) & 0x1F)
                        g = _c5to8((color_val >> 5) & 0x1F)
                        b = _c5to8((color_val >> 10) & 0x1F)
                        colors.append((r, g, b))
                    else:
                        colors.append(None)
                except:
                    colors.append(None)

        return colors

    def _render_sprites(self, layer_enable: int = 0x3F):
        OAM_BASE = 0x07000000
        NUM_SPRITES = 128

        for sprite_idx in range(NUM_SPRITES):
            sprite_addr = OAM_BASE + (sprite_idx * 8)

            try:
                attr0 = self.memory.read_u16(sprite_addr + 0)
                attr1 = self.memory.read_u16(sprite_addr + 2)
                attr2 = self.memory.read_u16(sprite_addr + 4)
            except:
                continue

            if attr0 == 0 and attr1 == 0 and attr2 == 0:
                continue

            obj_mode = (attr0 >> 10) & 3
            if obj_mode == 2:
                continue

            sprite_y = attr0 & 0xFF
            sprite_x = attr1 & 0x1FF
            height = ((attr0 >> 12) & 7) * 8 + 8
            width = ((attr1 >> 8) & 0x3) * 8 + 8

            if width > 64:
                width = 64
            if height > 64:
                height = 64

            tile_num = attr2 & 0x3FF
            palette_num = (attr2 >> 12) & 0xF
            vflip = bool(attr1 & 0x1000)
            hflip = bool(attr1 & 0x0800)
            affine = self._is_affine_sprite(attr1)

            for dy in range(height):
                screen_y = sprite_y + dy
                if screen_y < 0 or screen_y >= self.screen_height:
                    continue

                pixel_y = dy
                if vflip:
                    pixel_y = height - 1 - dy

                for dx in range(width):
                    screen_x = sprite_x + dx
                    if screen_x < 0 or screen_x >= self.screen_width:
                        continue

                    pixel_x = dx
                    if hflip:
                        pixel_x = width - 1 - dx

                    tile_row = pixel_y // 8
                    tile_col = pixel_x // 8
                    tile_pixel_y = pixel_y % 8
                    tile_pixel_x = pixel_x % 8

                    tile_addr = tile_num + tile_row * (width // 8) + tile_col

                    tile_indices = self._decode_tile_4bpp(tile_addr, 4)

                    tile_pixel_idx = tile_pixel_y * 8 + tile_pixel_x
                    if tile_pixel_idx < len(tile_indices):
                        color_idx = tile_indices[tile_pixel_idx]
                        if color_idx != 0:
                            if self.win0_enable or self.win1_enable:
                                pixel_layer_enable = self._get_window_layer_enable(screen_x, screen_y)
                                if not (pixel_layer_enable & 0x10):
                                    continue

                            palette_idx = palette_num * 16 + color_idx
                            color = self._get_palette_color(palette_idx)
                            self.framebuffer[screen_y][screen_x] = color

    def _render_sprites_line(self, y: int, x: int, layer_enable: int):
        OAM_BASE = 0x07000000
        NUM_SPRITES = 128

        for sprite_idx in range(NUM_SPRITES):
            sprite_addr = OAM_BASE + (sprite_idx * 8)

            try:
                attr0 = self.memory.read_u16(sprite_addr + 0)
                attr1 = self.memory.read_u16(sprite_addr + 2)
                attr2 = self.memory.read_u16(sprite_addr + 4)
            except:
                continue

            sprite_y = attr0 & 0xFF
            sprite_x = attr1 & 0x1FF

            if sprite_y == 0 and sprite_x == 0 and attr2 == 0:
                continue

            obj_mode = (attr0 >> 10) & 3
            if obj_mode == 2:
                continue

            height = ((attr0 >> 12) & 7) * 8 + 8
            width = ((attr1 >> 8) & 0x3) * 8 + 8

            if width > 64:
                width = 64
            if height > 64:
                height = 64

            if y < sprite_y or y >= sprite_y + height:
                continue
            if x < sprite_x or x >= sprite_x + width:
                continue

            tile_num = attr2 & 0x3FF
            palette_num = (attr2 >> 12) & 0xF
            vflip = bool(attr1 & 0x1000)
            hflip = bool(attr1 & 0x0800)

            pixel_y = y - sprite_y
            if vflip:
                pixel_y = height - 1 - pixel_y

            pixel_x = x - sprite_x
            if hflip:
                pixel_x = width - 1 - pixel_x

            tile_w = 8
            tile_h = 8
            tile_row = pixel_y // tile_h
            tile_col = pixel_x // tile_w
            tile_pixel_y = pixel_y % tile_h
            tile_pixel_x = pixel_x % tile_w

            vram_addr = (
                0x06010000
                + (tile_num * 64)
                + (tile_row * 2 * tile_w // 8)
                + tile_row * tile_w
                + tile_pixel_y * tile_w // 8
                + tile_pixel_x // 8 * 2
                + tile_pixel_y % 2
            )

            try:
                char_data = self.memory.read_u16(vram_addr & 0x0601FFFF)

                bit_pos = 7 - (tile_pixel_x % 8)
                color_idx = (char_data >> (bit_pos * 2)) & 3

                if color_idx != 0 or (attr0 & 0x2000):
                    palette_addr = 0x05000200 + (palette_num * 32) + (color_idx * 2)
                    palette_val = self.memory.read_u16(palette_addr)

                    r = _c5to8((palette_val >> 0) & 0x1F)
                    g = _c5to8((palette_val >> 5) & 0x1F)
                    b = _c5to8((palette_val >> 10) & 0x1F)

                    self.framebuffer[y][x] = (r, g, b)
            except Exception:
                ...

"""GBA CPU (ARM7TDMI) implementation"""

from typing import Any, Literal

_CONDITION = (
    # Each entry: (flag_key_bitmask, invert) for simple flags, or a 16-entry tuple for compound
    # Index 0-14: condition code, 15: flag key (z<<3|c<<2|n<<1|v)
    #  0:EQ  (=Z)
    tuple(1 if bool(k >> 3 & 1) else 0 for k in range(16)),
    #  1:NE (!Z)
    tuple(1 if not bool(k >> 3 & 1) else 0 for k in range(16)),
    #  2:CS  (=C)
    tuple(1 if bool(k >> 2 & 1) else 0 for k in range(16)),
    #  3:CC (!C)
    tuple(1 if not bool(k >> 2 & 1) else 0 for k in range(16)),
    #  4:MI  (=N)
    tuple(1 if bool(k >> 1 & 1) else 0 for k in range(16)),
    #  5:PL (!N)
    tuple(1 if not bool(k >> 1 & 1) else 0 for k in range(16)),
    #  6:VS  (=V)
    tuple(1 if bool(k & 1) else 0 for k in range(16)),
    #  7:VC (!V)
    tuple(1 if not bool(k & 1) else 0 for k in range(16)),
    #  8:HI (C & !Z)
    tuple(1 if bool(k >> 2 & 1) and not bool(k >> 3 & 1) else 0 for k in range(16)),
    #  9:LS (!C | Z)
    tuple(1 if (not bool(k >> 2 & 1)) or bool(k >> 3 & 1) else 0 for k in range(16)),
    # 10:GE (N == V)
    tuple(1 if bool(k >> 1 & 1) == bool(k & 1) else 0 for k in range(16)),
    # 11:LT (N != V)
    tuple(1 if bool(k >> 1 & 1) != bool(k & 1) else 0 for k in range(16)),
    # 12:GT (!Z & N==V)
    tuple(1 if (not bool(k >> 3 & 1)) and (bool(k >> 1 & 1) == bool(k & 1)) else 0 for k in range(16)),
    # 13:LE (Z | N!=V)
    tuple(1 if bool(k >> 3 & 1) or (bool(k >> 1 & 1) != bool(k & 1)) else 0 for k in range(16)),
    # 14:AL (always true)
    tuple(1 for _ in range(16)),
    # 15:NV (never true)
    tuple(0 for _ in range(16)),
)
class CPU:
    """ARM7TDMI CPU emulator state"""

    # Register names
    SP = 13  # Stack Pointer
    LR = 14  # Link Register
    PC = 15  # Program Counter

    # CPSR flag positions
    FLAG_N = 31  # Negative/Less than
    FLAG_Z = 30  # Zero
    FLAG_C = 29  # Carry/Borrow
    FLAG_V = 28  # Overflow
    FLAG_T = 5  # Thumb mode

    def __init__(self, memory=None):
        """Initialize CPU state"""
        self.registers: list[int] = [0] * 16
        self.memory = memory

        # CPSR flags as individual booleans
        self.flag_n: bool = False  # Negative
        self.flag_z: bool = False  # Zero
        self.flag_c: bool = False  # Carry
        self.flag_v: bool = False  # Overflow
        self.thumb_mode: bool = False  # T bit - Thumb mode

        # Cycle counter for interrupt-driven execution
        self.cycle_count: int = 0
        self.instruction_cycles: int = 1  # Default: 1 cycle per instruction (simplified)

    def reset(self, entry_point: int) -> None:
        """
        Reset CPU to initial state

        Args:
            entry_point: Initial PC value (typically 0x08000000 for GBA)
        """
        # Clear all registers
        for i in range(16):
            self.registers[i] = 0

        # Set stack pointer to IWRAM top (GBA convention)
        self.registers[self.SP] = 0x03007F00

        # Set PC to entry point
        self.registers[self.PC] = entry_point & 0xFFFFFFFF

        # Clear all CPSR flags
        self.flag_n = False
        self.flag_z = False
        self.flag_c = False
        self.flag_v = False
        self.thumb_mode = False

    def get_register(self, index: int) -> int:
        """
        Get value of register

        Args:
            index: Register index (0-15)

        Returns:
            32-bit register value
        """
        if 0 <= index <= 15:
            return self.registers[index]
        raise ValueError(f"Invalid register index: {index}")

    def set_register(self, index: int, value: int) -> None:
        """
        Set value of register

        Args:
            index: Register index (0-15)
            value: Value to set (will be masked to 32 bits)
        """
        if 0 <= index <= 15:
            self.registers[index] = value & 0xFFFFFFFF
        else:
            raise ValueError(f"Invalid register index: {index}")

    def get_cpsr_flag(self, flag: Literal["N", "Z", "C", "V"]) -> bool:
        """
        Get CPSR flag value

        Args:
            flag: Flag name (N, Z, C, or V)

        Returns:
            Flag boolean value
        """
        flag = flag.upper()
        if flag == "N":
            return self.flag_n
        elif flag == "Z":
            return self.flag_z
        elif flag == "C":
            return self.flag_c
        elif flag == "V":
            return self.flag_v
        else:
            raise ValueError(f"Invalid CPSR flag: {flag}. Must be N, Z, C, or V")

    def set_cpsr_flag(self, flag: Literal["N", "Z", "C", "V"], value: bool) -> None:
        """
        Set CPSR flag value

        Args:
            flag: Flag name (N, Z, C, or V)
            value: Boolean value to set
        """
        flag = flag.upper()
        if flag == "N":
            self.flag_n = bool(value)
        elif flag == "Z":
            self.flag_z = bool(value)
        elif flag == "C":
            self.flag_c = bool(value)
        elif flag == "V":
            self.flag_v = bool(value)
        else:
            raise ValueError(f"Invalid CPSR flag: {flag}. Must be N, Z, C, or V")

    def check_condition(self, cond: int) -> bool:
        """Check if ARM condition is satisfied (cond: 0-15) — O(1) lookup"""
        if cond < 0 or cond > 15:
            raise ValueError(f"Invalid condition code: {cond}. Must be 0-15")
        entry = CONDITIONS[cond]
        src, op = entry
        if src is True or src is False:
            return src
        flag = getattr(self, f"flag_{src}")
        if op is None:
            return flag
        if op == "not":
            return not flag
        if op == "&":
            return flag and not self.flag_z
        if op == "|":
            return not flag or self.flag_z
        if op == "eq":
            return self.flag_n == self.flag_v
        if op == "ne":
            return self.flag_n != self.flag_v
        if op == "gt":
            return not self.flag_z and self.flag_n == self.flag_v
        if op == "le":
            return self.flag_z or self.flag_n != self.flag_v
        return False

    def step(self) -> int:
        """Execute one ARM or Thumb instruction"""
        if not self.memory:
            return 1

        # Fetch instruction
        pc = self.registers[self.PC]
        if self.thumb_mode:
            # Thumb mode (16-bit)
            opcode = self.memory.read_u16(pc & 0xFFFFFFFE)
            self.registers[self.PC] = (pc + 2) & 0xFFFFFFFF
            self._execute_thumb(opcode)
            return 1
        else:
            # ARM mode (32-bit)
            opcode = self.memory.read_u32(pc & 0xFFFFFFFC)
            self.registers[self.PC] = (pc + 4) & 0xFFFFFFFF
            self._execute_arm(opcode)
            return 1

    def _execute_arm(self, opcode: int) -> bool:
        """Execute one ARM instruction. Returns False to halt."""
        if opcode == 0 or opcode == 0xE1200070:  # NOP / reserved
            return True

        cond = (opcode >> 28) & 0xF
        if not self.check_condition(cond):
            return True

        # Check for B/BL
        if (opcode & 0xE000000) == 0xA000000:
            offset = opcode & 0xFFFFFF
            if offset & 0x800000:
                offset = -((~offset + 1) & 0xFFFFFF)
            target = self.registers[self.PC] + 4 + (offset << 2)
            if opcode & 0x01000000:  # BL
                self.registers[self.LR] = self.registers[self.PC]
            self.registers[self.PC] = target & 0xFFFFFFFF
            return True

        # Check for BX
        if (opcode & 0xFFFFFFF) == 0xE12FFF10:
            target = self.registers[opcode & 0xF]
            self.thumb_mode = bool(target & 1)
            self.registers[self.PC] = target & 0xFFFFFFFE
            return True

        # Data processing: bits 27-26 = 00
        if (opcode >> 26) & 3 == 0:
            return self._arm_data_processing(opcode)

        # Load/Store
        if (opcode >> 26) & 0x3 == 1:
            return self._arm_load_store(opcode)

        # Multiply
        if (opcode & 0xFC000F0) == 0x0:
            return self._arm_multiply(opcode)

        return True

    def _arm_data_processing(self, opcode: int) -> bool:
        """Execute ARM data processing instruction"""
        rn = (opcode >> 16) & 0xF
        rd = (opcode >> 12) & 0xF
        imm = (opcode >> 25) & 1

        # Get operands
        # Handle register shift (bit 4 = 1 means register shift)
        if imm:
            operand2 = opcode & 0xFF
            rotate = ((opcode >> 8) & 0xF) * 2
            operand2 = ((operand2 >> rotate) | (operand2 << (32 - rotate))) & 0xFFFFFFFF
        elif (opcode >> 4) & 1:  # Register shift
            rm = opcode & 0xF
            rs = (opcode >> 8) & 0xF  # Shift amount register
            shift_imm = self.registers[rs] & 0xFF
            operand2 = self.registers[rm]
            shift_type = (opcode >> 5) & 3
            if shift_imm:
                if shift_type == 0:  # LSL
                    operand2 = (operand2 << shift_imm) & 0xFFFFFFFF
                elif shift_type == 1:  # LSR
                    operand2 = operand2 >> shift_imm
                elif shift_type == 2:  # ASR
                    operand2 = (operand2 >> shift_imm) | (
                        (operand2 & 0x80000000) * (0xFFFFFFFF >> (32 - shift_imm))
                    )
                elif shift_type == 3:  # ROR
                    operand2 = (
                        (operand2 >> shift_imm) | (operand2 << (32 - shift_imm))
                    ) & 0xFFFFFFFF
        else:
            rm = opcode & 0xF
            operand2 = self.registers[rm]
            shift_type = (opcode >> 5) & 3
            shift_imm = (opcode >> 7) & 0x1F
            if shift_imm:
                if shift_type == 0:  # LSL
                    operand2 = (operand2 << shift_imm) & 0xFFFFFFFF
                elif shift_type == 1:  # LSR
                    operand2 = operand2 >> shift_imm
                elif shift_type == 2:  # ASR
                    operand2 = (operand2 >> shift_imm) | (
                        (operand2 & 0x80000000) * (0xFFFFFFFF >> (32 - shift_imm))
                    )
                elif shift_type == 3:  # ROR
                    operand2 = (
                        (operand2 >> shift_imm) | (operand2 << (32 - shift_imm))
                    ) & 0xFFFFFFFF

        op = (opcode >> 21) & 0xF
        s = (opcode >> 20) & 1

        if rn == 15:
            operand1 = self.registers[self.PC] + 4
        else:
            operand1 = self.registers[rn]

        result = 0
        update_flags = s == 1 and rd != 15

        # Opcode mapping
        if op == 0:  # AND
            result = operand1 & operand2
            self.registers[rd] = result
        elif op == 1:  # EOR
            result = operand1 ^ operand2
            self.registers[rd] = result
        elif op == 2:  # SUB
            result = (operand1 - operand2) & 0xFFFFFFFF
            self.registers[rd] = result
            if update_flags:
                self.flag_c = operand1 >= operand2
        elif op == 3:  # RSB
            result = (operand2 - operand1) & 0xFFFFFFFF
            self.registers[rd] = result
        elif op == 4:  # ADD
            result = (operand1 + operand2) & 0xFFFFFFFF
            self.registers[rd] = result
            if update_flags:
                self.flag_c = result < operand1
        elif op == 5:  # ADC
            c = 1 if self.flag_c else 0
            result = (operand1 + operand2 + c) & 0xFFFFFFFF
            self.registers[rd] = result
        elif op == 6:  # SBC
            c = 1 if self.flag_c else 0
            result = (operand1 - operand2 - c + 0x100000000) & 0xFFFFFFFF
            self.registers[rd] = result
        elif op == 8:  # TST
            result = operand1 & operand2
            update_flags = True
        elif op == 9:  # TEQ
            result = operand1 ^ operand2
            update_flags = True
        elif op == 10:  # CMP
            result = (operand1 - operand2) & 0xFFFFFFFF
            update_flags = True
            if update_flags:
                self.flag_c = operand1 >= operand2
        elif op == 11:  # CMN
            result = (operand1 + operand2) & 0xFFFFFFFF
            update_flags = True
        elif op == 12:  # ORR
            result = operand1 | operand2
            self.registers[rd] = result
        elif op == 13:  # MOV
            result = operand2
            self.registers[rd] = result
        elif op == 14:  # BIC
            result = operand1 & ~operand2
            self.registers[rd] = result
        elif op == 15:  # MVN
            result = (~operand2) & 0xFFFFFFFF
            self.registers[rd] = result

        if update_flags:
            self.flag_n = bool(result & 0x80000000)
            self.flag_z = result == 0

        return True

    def _arm_load_store(self, opcode: int) -> bool:
        """Execute ARM load/store instruction"""
        rd = (opcode >> 12) & 0xF
        rn = (opcode >> 16) & 0xF
        imm = (opcode >> 25) & 1
        load = (opcode >> 20) & 1
        byte = (opcode >> 22) & 1

        # Calculate address
        if imm:
            offset = opcode & 0xFFF
        elif (opcode >> 4) & 1:  # Register shift (bit 4 = 1)
            rm = opcode & 0xF
            offset = self.registers[rm]
        elif (opcode & 0xF) == 0:  # No register specified = no offset
            offset = 0
        else:
            rm = opcode & 0xF
            offset = self.registers[rm]

        addr = self.registers[rn]

        # Pre/post indexing
        add = (opcode >> 23) & 1
        write_back = (opcode >> 21) & 1

        if add:
            addr = (addr + offset) & 0xFFFFFFFF
        else:
            addr = (addr - offset) & 0xFFFFFFFF

        if load:
            if byte:
                val = self.memory.read_u8(addr)
            else:
                val = self.memory.read_u32(addr)
            self.registers[rd] = val
        else:
            val = self.registers[rd]
            if byte:
                self.memory.write_u8(addr, val & 0xFF)
            else:
                self.memory.write_u32(addr, val)

        if write_back:
            if add:
                self.registers[rn] = (self.registers[rn] + offset) & 0xFFFFFFFF
            else:
                self.registers[rn] = (self.registers[rn] - offset) & 0xFFFFFFFF

        return True

    def _arm_multiply(self, opcode: int) -> bool:
        """Execute ARM multiply instruction"""
        rd = (opcode >> 16) & 0xF
        rn = (opcode >> 12) & 0xF
        rs = (opcode >> 8) & 0xF
        rm = opcode & 0xF
        s = (opcode >> 20) & 1

        result = (self.registers[rm] * self.registers[rs]) & 0xFFFFFFFF

        if rn != 0:
            result = (result + self.registers[rn]) & 0xFFFFFFFF
            self.registers[rn] = result

        self.registers[rd] = result

        if s:
            self.flag_n = bool(result & 0x80000000)
            self.flag_z = result == 0

        return True

    def _execute_thumb(self, opcode: int) -> bool:
        """Execute one Thumb instruction"""
        # Check condition for branch
        if (opcode & 0xF000) == 0xD000:
            cond = (opcode >> 8) & 0xF
            if not self.check_condition(cond):
                return True
            offset = opcode & 0xFF
            if offset & 0x80:
                offset = -((~offset + 1) & 0xFF)
            self.registers[self.PC] = (self.registers[self.PC] + (offset << 1)) & 0xFFFFFFFF
            return True

        # Unconditional branch
        if (opcode & 0xF800) == 0xE000:
            offset = opcode & 0x7FF
            if offset & 0x400:
                offset = -((~offset + 1) & 0x7FF)
            self.registers[self.PC] = (self.registers[self.PC] + (offset << 1)) & 0xFFFFFFFF
            return True

        # BL/BLX (high word)
        if (opcode & 0xF000) == 0xF000:
            return True  # Simplified: just return

        # MOV immediate
        if (opcode & 0xF800) == 0x2000:
            rd = (opcode >> 8) & 0x7
            imm = opcode & 0xFF
            self.registers[rd] = imm
            return True

        # ADD register
        if (opcode & 0xFC00) == 0x1800:
            rd = (opcode >> 6) & 0x7
            rn = (opcode >> 3) & 0x7
            rm = opcode & 0x7
            self.registers[rd] = (self.registers[rn] + self.registers[rm]) & 0xFFFFFFFF
            return True

        # SUB immediate
        if (opcode & 0xFC00) == 0x1C00:
            rd = (opcode >> 6) & 0x7
            rn = (opcode >> 3) & 0x7
            imm = opcode & 0x7
            self.registers[rd] = (self.registers[rn] - imm) & 0xFFFFFFFF
            return True

        # LDR
        if (opcode & 0xF800) == 0x6800:
            rd = (opcode >> 8) & 0x7
            rn = (opcode >> 3) & 0x7
            offset = (opcode & 0x7) * 4
            addr = (self.registers[rn] + offset) & 0xFFFFFFFF
            self.registers[rd] = self.memory.read_u32(addr)
            return True

        # STR
        if (opcode & 0xF800) == 0x6000:
            rd = (opcode >> 8) & 0x7
            rn = (opcode >> 3) & 0x7
            offset = (opcode & 0x7) * 4
            addr = (self.registers[rn] + offset) & 0xFFFFFFFF
            self.memory.write_u32(addr, self.registers[rd])
            return True

        # CMP
        if (opcode & 0xF800) == 0x2800:
            rd = (opcode >> 8) & 0x7
            imm = opcode & 0xFF
            result = (self.registers[rd] - imm) & 0xFFFFFFFF
            self.flag_z = result == 0
            self.flag_n = bool(result & 0x80000000)
            return True

        # BX
        if (opcode & 0xFF00) == 0x4700:
            rm = (opcode >> 3) & 0xF
            target = self.registers[rm]
            self.thumb_mode = bool(target & 1)
            self.registers[self.PC] = target & 0xFFFFFFFE
            return True

        return True

    # DEAD CODE: SWI handlers not used by runtime (runtime uses ARM7TDMI class from arm7tdmi.py)
    def dump_registers(self, frame: int = None) -> dict:
        """
        Dump CPU register state to a dictionary.

        Returns:
            dict containing register values
        """
        return {
            "timestamp": frame if frame is not None else "unknown",
            "registers": [self.registers[i] for i in range(16)],
            "cpsr_flags": {
                "N": self.flag_n,
                "Z": self.flag_z,
                "C": self.flag_c,
                "V": self.flag_v,
                "T": self.thumb_mode,
            },
        }

    def save_register_dump(self, dump: dict, filename: str = None) -> str:
        """
        Save register dump to JSON file.

        Args:
            dump: Register dump dictionary
            filename: Optional filename (without extension)

        Returns:
            Path to saved file
        """
        import json
        import os

        dump_dir = os.environ.get("GBATOPY_DUMP_DIR", ".")
        os.makedirs(dump_dir, exist_ok=True)

        if filename is None:
            filename = f"registers_{dump.get('timestamp', 'unknown')}"

        filepath = os.path.join(dump_dir, f"{filename}.json")
        with open(filepath, "w") as f:
            json.dump(dump, f, indent=2)

        return filepath


class RegisterDump:
    """Utility for dumping and comparing CPU register state."""

    def __init__(self, cpu: "CPU"):
        self.cpu = cpu
        self.dump_dir = None

    def set_dump_directory(self, directory: str):
        """Set the output directory for dump files."""
        self.dump_dir = directory

    def dump_registers(self, frame: int = None) -> dict:
        """
        Dump CPU registers to a dictionary.

        Returns:
            dict containing register values
        """
        return self.cpu.dump_registers(frame)

    def save_register_dump(self, dump: dict, filename: str = None) -> str:
        """
        Save register dump to JSON file.

        Args:
            dump: Register dump dictionary
            filename: Optional filename (without extension)

        Returns:
            Path to saved file
        """
        import json
        import os

        if self.dump_dir is None:
            raise ValueError("No dump directory set.")

        if filename is None:
            filename = f"registers_{dump.get('timestamp', 'unknown')}"

        os.makedirs(self.dump_dir, exist_ok=True)

        filepath = os.path.join(self.dump_dir, f"{filename}.json")
        with open(filepath, "w") as f:
            json.dump(dump, f, indent=2)

        return filepath

    def compare_registers(self, regs1: dict, regs2: dict) -> dict:
        """
        Compare two register dumps.

        Args:
            regs1: First register dump
            regs2: Second register dump

        Returns:
            dict with comparison results
        """
        differences = []

        if "registers" in regs1 and "registers" in regs2:
            for i in range(len(regs1["registers"])):
                if regs1["registers"][i] != regs2["registers"][i]:
                    differences.append({
                        "register": f"R{i}",
                        "value1": regs1["registers"][i],
                        "value2": regs2["registers"][i],
                    })

        if "cpsr_flags" in regs1 and "cpsr_flags" in regs2:
            for flag in ["N", "Z", "C", "V", "T"]:
                val1 = regs1["cpsr_flags"].get(flag, False)
                val2 = regs2["cpsr_flags"].get(flag, False)
                if val1 != val2:
                    differences.append({
                        "register": f"CPSR.{flag}",
                        "value1": val1,
                        "value2": val2,
                    })

        return {
            "differences_found": len(differences),
            "differences": differences,
        }

    def save_diff_report(self, comparison: dict, filename: str = None) -> str:
        """
        Save register comparison report to text file.

        Args:
            comparison: Result of compare_registers()
            filename: Optional filename (without extension)
        """
        import os
        if self.dump_dir is None:
            raise ValueError("No dump directory set.")

        if filename is None:
            filename = "register_comparison"

        filepath = os.path.join(self.dump_dir, f"{filename}.txt")
        with open(filepath, "w") as f:
            f.write("Register Comparison Report\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Differences found: {comparison['differences_found']}\n\n")

            if comparison["differences"]:
                f.write("Differences:\n")
                f.write("-" * 60 + "\n")
                for diff in comparison["differences"]:
                    f.write(f"\n{diff['register']}:\n")
                    f.write(f"  - Value 1: {diff['value1']}\n")
                    f.write(f"  - Value 2: {diff['value2']}\n")
            else:
                f.write("\nNo differences found.\n")

        return filepath

"""ARM7TDMI CPU Interpreter for GBA"""

from typing import Optional, Callable, List, Tuple
from bios import BIOS

try:
    import numba
    from numba import njit
    _HAS_NUMBA = True
except ImportError:
    numba = None
    # Create a no-op decorator when numba is not available
    def njit(*args, **kwargs):
        """No-op decorator when numba is not available."""
        def decorator(func):
            return func
        # Handle @njit() with no arguments
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator
    _HAS_NUMBA = False

_NUMBA_ENABLED = True


def jit_compile(func):
    """Decorator to optionally compile functions with numba for 10x speedup."""
    if not _HAS_NUMBA or not _NUMBA_ENABLED:
        return func
    try:
        return njit(func)
    except Exception as e:
        print(f"  Warning: JIT compilation failed for {func.__name__}: {e}")
        return func


def set_numba_enabled(enabled: bool):
    global _NUMBA_ENABLED
    if not _HAS_NUMBA and enabled:
        print("  Warning: numba not installed, JIT compilation unavailable")
    _NUMBA_ENABLED = enabled and _HAS_NUMBA


def is_numba_available() -> bool:
    return _HAS_NUMBA


@jit_compile
def _check_condition_fast(cond: int, n: int, z: int, c: int, v: int) -> bool:
    if cond == 0xE or cond == 0xF:
        return True
    if cond == 0x0:
        return z == 1
    if cond == 1:
        return z == 0
    if cond == 0x2:
        return c == 1
    if cond == 0x3:
        return c == 0
    if cond == 0x4:
        return n == 1
    if cond == 0x5:
        return n == 0
    if cond == 0x6:
        return v == 1
    if cond == 0x7:
        return v == 0
    if cond == 0x8:
        return c == 1 and z == 0
    if cond == 0x9:
        return c == 0 or z == 1
    if cond == 0xA:
        return n == v
    if cond == 0xB:
        return n != v
    if cond == 0xC:
        return z == 0 and n == v
    if cond == 0xD:
        return z == 1 or n != v
    return True


@jit_compile
def _update_flags_fast(result: int, carry: int, overflow: int) -> int:
    n = (result >> 31) & 1
    z = 1 if result == 0 else 0
    c = carry & 1
    v = overflow & 1
    return (n << 31) | (z << 30) | (c << 29) | (v << 28)


class ARM7TDMI:
    """ARM7TDMI CPU interpreter with full instruction execution."""

    def __init__(self, memory):
        self.memory = memory
        self.registers = [0] * 16  # r0-r15
        self.cpsr = 0  # Current Program Status Register
        self.spsr = [0] * 6  # Saved PSR for each mode

        # ARM condition codes
        self.COND_EQ = 0x0  # Z set
        self.COND_NE = 0x1  # Z clear
        self.COND_CS = 0x2  # C set
        self.COND_CC = 0x3  # C clear
        self.COND_MI = 0x4  # N set
        self.COND_PL = 0x5  # N clear
        self.COND_VS = 0x6  # V set
        self.COND_VC = 0x7  # V clear
        self.COND_HI = 0x8  # C set and Z clear
        self.COND_LS = 0x9  # C clear or Z set
        self.COND_GE = 0xA  # N == V
        self.COND_LT = 0xB  # N != V
        self.COND_GT = 0xC  # Z clear and N == V
        self.COND_LE = 0xD  # Z set or N != V
        self.COND_AL = 0xE  # Always
        self.COND_NV = 0xF  # Never

        self.mode = 0x1F  # User mode
        self.thumb_mode = False
        self.running = True
        self.cycles = 0

        # Initialize BIOS for SWI handlers
        self.bios = BIOS(self.memory)

    @property
    def r(self):
        return self.registers

    @property
    def pc(self) -> int:
        return self.registers[15]

    @pc.setter
    def pc(self, value: int):
        self.registers[15] = value & 0xFFFFFFFC
        if self.thumb_mode:
            self.registers[15] = value & 0xFFFFFFFE

    @property
    def lr(self) -> int:
        return self.registers[14]

    @lr.setter
    def lr(self, value: int):
        self.registers[14] = value

    @property
    def sp(self) -> int:
        return self.registers[13]

    @sp.setter
    def sp(self, value: int):
        self.registers[13] = value

    @property
    def nzcv(self) -> Tuple[int, int, int, int]:
        n = (self.cpsr >> 31) & 1
        z = (self.cpsr >> 30) & 1
        c = (self.cpsr >> 29) & 1
        v = (self.cpsr >> 28) & 1
        return (n, z, c, v)

    def _update_flags_nzcv(self, result: int, carry: int = 0, overflow: int = 0) -> int:
        """Update CPSR N, Z, C, V flags based on result.
        
        Args:
            result: The computation result (32-bit value)
            carry: Carry flag value (optional, defaults to 0)
            overflow: Overflow flag value (optional, defaults to 0)
            
        Returns:
            New CPSR value with updated flags
        """
        # N: Negative flag (bit 31)
        n = (result >> 31) & 1
        # Z: Zero flag (bit 30)
        z = 1 if result == 0 else 0
        # C: Carry flag (use provided value or 0)
        c = carry & 1
        # V: Overflow flag (use provided value or 0)
        v = overflow & 1
        
        # Clear old flags and set new ones
        self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        return self.cpsr

    @jit_compile
    def check_condition(self, cond: int) -> bool:
        if cond == 0xE or cond == 0xF:
            return True
        n, z, c, v = self.nzcv
        if cond == 0x0:
            return z
        if cond == 0x1:
            return not z
        if cond == 0x2:
            return c
        if cond == 0x3:
            return not c
        if cond == 0x4:
            return n
        if cond == 0x5:
            return not n
        if cond == 0x6:
            return v
        if cond == 0x7:
            return not v
        if cond == 0x8:
            return c and not z
        if cond == 0x9:
            return not c or z
        if cond == 0xA:
            return n == v
        if cond == 0xB:
            return n != v
        if cond == 0xC:
            return not z and n == v
        if cond == 0xD:
            return z or n != v
        return True

    @jit_compile
    def read_register(self, reg: int) -> int:
        return self.registers[reg & 0xF]

    @jit_compile
    def write_register(self, reg: int, value: int):
        value &= 0xFFFFFFFF
        self.registers[reg & 0xF] = value
        if (reg & 0xF) == 15:
            self.registers[15] = value & (0xFFFFFFFE if self.thumb_mode else 0xFFFFFFFC)

    @jit_compile
    def step(self) -> int:
        if self.thumb_mode:
            return self.step_thumb()
        return self.step_arm()

    @jit_compile
    def step_arm(self) -> int:
        pc = self.pc
        if pc >= 0x08000000:
            pc = (pc - 0x08000000) + len(self.memory.rom)

        instr = self.memory.read_u32(pc)
        cond = (instr >> 28) & 0xF

        if not self.check_condition(cond):
            self.registers[15] += 4
            return 1

        return self.execute_arm(instr)

    @jit_compile
    def step_thumb(self) -> int:
        pc = self.pc
        if pc >= 0x08000000:
            pc = (pc - 0x08000000) + len(self.memory.rom)

        instr = self.memory.read_u16(pc)
        return self.execute_thumb(instr)

    @jit_compile
    def execute_arm(self, instr: int) -> int:
        opcode = (instr >> 21) & 0xF
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        rm = instr & 0xF

        if (instr & 0xC0000000) == 0 and (instr & 0x08000000) == 0:
            return self.exec_data_processing(instr)

        if (instr & 0xC000000) == 0x4000000:
            return self.exec_load_store(instr)

        if (instr & 0xE000000) == 0xA000000:
            return self.exec_branch(instr)

        if (instr & 0xFFFFFF0) == 0x12FFF10:
            return self.exec_bx(instr)

        if (instr & 0xE000000) == 0x8000000:
            return self.exec_block_transfer(instr)

        if (instr & 0xFC000F0) == 0x0:
            return self.exec_mul(instr)

        if (instr & 0xF000000) == 0xF000000:
            return self.exec_swi(instr)

        return 1

    @jit_compile
    def exec_data_processing(self, instr: int) -> int:
        """Execute ARM data processing instruction."""
        opcode = (instr >> 21) & 0xF
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        rm = instr & 0xF

        # Check for immediate
        imm = (instr >> 25) & 1
        if imm:
            imm_val = instr & 0xFF
            rot = ((instr >> 8) & 0xF) * 2
            if rot:
                imm_val = ((imm_val >> rot) | (imm_val << (32 - rot))) & 0xFFFFFFFF
            operand2 = imm_val
        else:
            shift_type = (instr >> 5) & 3
            shift_imm = (instr >> 7) & 0x1F
            operand2 = self.registers[rm]
            if shift_imm:
                if shift_type == 0:  # LSL
                    operand2 = (operand2 << shift_imm) & 0xFFFFFFFF
                elif shift_type == 1:  # LSR
                    operand2 = operand2 >> shift_imm
                elif shift_type == 2:  # ASR
                    operand2 = (operand2 >> shift_imm) | ((operand2 & 0x80000000) * shift_imm)
                elif shift_type == 3:  # ROR
                    operand2 = (
                        (operand2 >> shift_imm) | (operand2 << (32 - shift_imm))
                    ) & 0xFFFFFFFF

        operand1 = self.registers[rn]

        if opcode == 0:  # AND
            result = operand1 & operand2
            self.write_register(rd, result)
        elif opcode == 1:  # EOR
            result = operand1 ^ operand2
            self.write_register(rd, result)
        elif opcode == 2:  # SUB
            result = (operand1 - operand2) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 3:  # RSB
            result = (operand2 - operand1) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 4:  # ADD
            result = (operand1 + operand2) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 5:  # ADC
            c = (self.cpsr >> 29) & 1
            result = (operand1 + operand2 + c) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 6:  # SBC
            c = (self.cpsr >> 29) & 1
            result = (operand1 - operand2 - (1 - c)) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 7:  # RSC
            c = (self.cpsr >> 29) & 1
            result = (operand2 - operand1 - (1 - c)) & 0xFFFFFFFF
            self.write_register(rd, result)
        elif opcode == 8:  # TST
            result = operand1 & operand2
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif opcode == 9:  # TEQ
            result = operand1 ^ operand2
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif opcode == 0xA:  # CMP
            result = (operand1 - operand2) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif opcode == 0xB:  # CMN
            result = (operand1 + operand2) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif opcode == 0xC:  # ORR
            result = operand1 | operand2
            self.write_register(rd, result)
        elif opcode == 0xD:  # MOV
            self.write_register(rd, operand2)
        elif opcode == 0xE:  # BIC
            result = operand1 & ~operand2
            self.write_register(rd, result)
        elif opcode == 0xF:  # MVN
            self.write_register(rd, (~operand2) & 0xFFFFFFFF)

        if rd != 15:
            self.registers[15] += 4

        return 1

    @jit_compile
    def exec_load_store(self, instr: int) -> int:
        is_load = (instr >> 20) & 1
        is_byte = (instr >> 22) & 1
        is_up = (instr >> 23) & 1
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        offset = instr & 0xFFF

        base = self.registers[rn]
        addr = base + offset if is_up else base - offset

        if is_load:
            if is_byte:
                val = self.memory.read_u8(addr)
            else:
                val = self.memory.read_u32(addr)
            self.write_register(rd, val)
        else:
            val = self.registers[rd]
            if is_byte:
                self.memory.write_u8(addr, val & 0xFF)
            else:
                self.memory.write_u32(addr, val)

        return 2

    @jit_compile
    def exec_branch(self, instr: int) -> int:
        """Execute B/BL instruction."""
        is_link = (instr >> 24) & 1
        offset = instr & 0xFFFFFF
        if offset & 0x800000:
            offset |= 0xFF000000
        offset <<= 2

        if is_link:
            self.registers[14] = self.registers[15] + 4

        self.registers[15] = (self.registers[15] + offset) & 0xFFFFFFFF
        return 3

    def exec_bx(self, instr: int) -> int:
        """Execute BX instruction."""
        rm = instr & 0xF
        target = self.registers[rm]
        self.thumb_mode = (target & 1) != 0
        self.registers[15] = target & 0xFFFFFFFE
        return 3

    def exec_block_transfer(self, instr: int) -> int:
        """Execute LDM/STM instruction."""
        is_load = (instr >> 20) & 1
        is_up = (instr >> 23) & 1
        rn = (instr >> 16) & 0xF
        reg_list = instr & 0xFFFF

        base = self.registers[rn]
        addr = base

        if is_load:
            for i in range(16):
                if reg_list & (1 << i):
                    if is_up:
                        val = self.memory.read_u32(addr)
                        addr += 4
                    else:
                        addr -= 4
                        val = self.memory.read_u32(addr)
                    self.write_register(i, val)
        else:
            for i in range(16):
                if reg_list & (1 << i):
                    if is_up:
                        self.memory.write_u32(addr, self.registers[i])
                        addr += 4
                    else:
                        addr -= 4
                        self.memory.write_u32(addr, self.registers[i])

        return 2 + (reg_list.bit_count() * 2)

    @jit_compile
    def exec_mul(self, instr: int) -> int:
        rm = instr & 0xF
        rs = (instr >> 8) & 0xF
        rd = (instr >> 16) & 0xF
        result = (self.registers[rm] * self.registers[rs]) & 0xFFFFFFFF
        self.write_register(rd, result)
        return 2

    def exec_swi(self, instr: int) -> int:
        """Execute SWI (software interrupt)."""
        swi_num = instr & 0xFFFFFF
        self.swi_handler(swi_num)
        return 2

    def swi_handler(self, num: int):
        """Handle BIOS SWI calls.
        
        GBA SWI numbers (from bios.h):
        0x00: SoftReset
        0x01: RegisterRamReset
        0x02: Halt
        0x03: Stop
        0x04: IntrWait
        0x05: VBlankIntrWait
        0x06: Div
        0x07: DivArm
        0x08: Sqrt
        0x09: ArcTan
        0x0A: ArcTan2
        0x0B: CpuSet
        0x0C: CpuFastSet
        0x0E: BgAffineSet
        0x0F: ObjAffineSet
        0x11: LZ77UnCompWram
        0x12: LZ77UnCompVram
        """
        if num == 0x00:  # SoftReset
            for i in range(13):
                self.registers[i] = 0
            self.registers[13] = 0x03007F00
            self.registers[15] = 0x08000000
        elif num == 0x01:  # RegisterRamReset
            flags = self.registers[0]
            # Reset EWRAM
            if flags & 0x01:
                for addr in range(0x02000000, 0x02040000, 4):
                    self.memory.write_u32(addr, 0)
            # Reset IWRAM
            if flags & 0x02:
                for addr in range(0x03000000, 0x03008000, 4):
                    self.memory.write_u32(addr, 0)
            # Reset Palette
            if flags & 0x04:
                for addr in range(0x05000000, 0x05000400, 2):
                    self.memory.write_u16(addr, 0)
            # Reset VRAM
            if flags & 0x08:
                for addr in range(0x06000000, 0x06018000, 2):
                    self.memory.write_u16(addr, 0)
            # Reset OAM
            if flags & 0x10:
                for addr in range(0x07000000, 0x07000400, 2):
                    self.memory.write_u16(addr, 0)
        elif num == 0x02:  # Halt
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_halt()
        elif num == 0x03:  # Stop
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_stop(self.registers[0])
        elif num == 0x04:  # IntrWait
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_intr_wait(self.registers[0], self.registers[1])
        elif num == 0x05:  # VBlankIntrWait
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_vblank_intr_wait()
        elif num == 0x06:  # Div
            if hasattr(self, 'bios') and self.bios is not None:
                result = self.bios.swi_div(self.registers[0], self.registers[1])
                remainder = self.registers[0] % self.registers[1] if self.registers[1] != 0 else 0
                self.registers[0] = result & 0xFFFFFFFF
                self.registers[1] = remainder & 0xFFFFFFFF
        elif num == 0x07:  # DivArm (unsigned division)
            if hasattr(self, 'bios') and self.bios is not None:
                dividend = self.registers[0] & 0xFFFFFFFF
                divisor = self.registers[1] & 0xFFFFFFFF
                if divisor == 0:
                    self.registers[0] = 0
                else:
                    result = dividend // divisor
                    self.registers[0] = result & 0xFFFFFFFF
        elif num == 0x08:  # Sqrt
            if hasattr(self, 'bios') and self.bios is not None:
                result = self.bios.swi_sqrt(self.registers[0])
                self.registers[0] = result & 0xFFFFFFFF
        elif num == 0x09:  # ArcTan
            if hasattr(self, 'bios') and self.bios is not None:
                result = self.bios.swi_arctan(self.registers[0])
                self.registers[0] = result & 0xFFFF
        elif num == 0x0A:  # ArcTan2
            if hasattr(self, 'bios') and self.bios is not None:
                result = self.bios.swi_arctan2(self.registers[0], self.registers[1])
                self.registers[0] = result & 0xFFFF
        elif num == 0x0B:  # CpuSet
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_cpuset(self.registers[0], self.registers[1], self.registers[2], self.registers[2])
        elif num == 0x0C:  # CpuFastSet
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_cpufastset(self.registers[0], self.registers[1], self.registers[2], self.registers[3])
        elif num == 0x0E:  # BgAffineSet
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_bg_affine_set(self.registers[0], self.registers[1], self.registers[2], self.registers[3])
        elif num == 0x0F:  # ObjAffineSet
            if hasattr(self, 'bios') and self.bios is not None:
                data = self.registers[0]
                param_table = self.registers[1]
                num_objects = self.registers[2]
                increment = self.registers[3]
                for i in range(num_objects):
                    offset = i * increment
                    self.bios.swi_obj_affine_set(
                        param_table + offset,
                        self.memory.read_u16(data + offset * 2),
                        self.memory.read_u16(data + offset * 2 + 2),
                        self.memory.read_u16(data + offset * 2 + 4)
                    )
        elif num == 0x11:  # LZ77UnCompWram
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_lz77_uncomp(self.registers[0], self.registers[1])
        elif num == 0x12:  # LZ77UnCompVram
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_lz77_uncomp(self.registers[0], self.registers[1])

    def execute_thumb(self, instr: int) -> int:
        """Execute Thumb instruction."""
        op = (instr >> 13) & 7

        if op == 0:  # Move shifted/ADD/SUB
            return self.exec_thumb_move_shift(instr)
        elif op == 1:  # Add/Sub
            return self.exec_thumb_add_sub(instr)
        elif op == 2:  # MOV/CMP/ADD/SUB immediate
            return self.exec_thumb_imm(instr)
        elif op == 3:  # ALU operations
            return self.exec_thumb_alu(instr)
        elif op == 4:  # Hi register operations/BX
            return self.exec_thumb_hi(instr)
        elif op == 5:  # PC-relative load
            return self.exec_thumb_pc_rel(instr)
        elif op == 6:  # LDR/STR
            return self.exec_thumb_load_store(instr)
        elif op == 7:  # LDRH/STRH
            return self.exec_thumb_hword(instr)

        return 1

    def exec_thumb_move_shift(self, instr: int) -> int:
        """Thumb move shifted."""
        op = (instr >> 11) & 3
        offset = (instr >> 6) & 0x1F
        rs = (instr >> 3) & 7
        rd = instr & 7

        val = self.registers[rs]
        if op == 0:  # LSL
            val = (val << offset) & 0xFFFFFFFF
        elif op == 1:  # LSR
            val = val >> offset
        elif op == 2:  # ASR
            val = (val >> offset) | ((val & 0x80000000) * offset)

        self.write_register(rd, val)
        self.registers[15] += 2
        return 1

    def exec_thumb_add_sub(self, instr: int) -> int:
        """Thumb ADD/SUB."""
        is_imm = (instr >> 10) & 1
        is_sub = (instr >> 9) & 1
        rs = (instr >> 6) & 7
        rn = (instr >> 3) & 7
        rd = instr & 7

        if is_imm:
            offset = rs
        else:
            offset = self.registers[rs]

        op1 = self.registers[rn]
        if is_sub:
            result = (op1 - offset) & 0xFFFFFFFF
        else:
            result = (op1 + offset) & 0xFFFFFFFF

        self.write_register(rd, result)
        self.registers[15] += 2
        return 1

    def exec_thumb_imm(self, instr: int) -> int:
        """Thumb MOV/CMP/ADD/SUB immediate."""
        op = (instr >> 11) & 3
        offset = (instr >> 6) & 0x1F
        rn = (instr >> 3) & 7
        rd = instr & 7

        if op == 0:  # MOV
            self.write_register(rd, offset)
        elif op == 1:  # CMP
            result = (self.registers[rn] - offset) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif op == 2:  # ADD
            self.write_register(rd, (self.registers[rn] + offset) & 0xFFFFFFFF)
        elif op == 3:  # SUB
            self.write_register(rd, (self.registers[rn] - offset) & 0xFFFFFFFF)

        self.registers[15] += 2
        return 1

    def exec_thumb_alu(self, instr: int) -> int:
        """Thumb ALU operations."""
        op = (instr >> 6) & 0xF
        rs = (instr >> 3) & 7
        rd = instr & 7

        val = self.registers[rs]

        if op == 0:  # AND
            result = self.registers[rd] & val
        elif op == 1:  # EOR
            result = self.registers[rd] ^ val
        elif op == 2:  # LSL
            result = (self.registers[rd] << (val & 0xFF)) & 0xFFFFFFFF
        elif op == 3:  # LSR
            result = self.registers[rd] >> (val & 0xFF)
        elif op == 4:  # ASR
            result = (self.registers[rd] >> (val & 0xFF)) | (
                (self.registers[rd] & 0x80000000) * (val & 0xFF)
            )
        elif op == 5:  # ADC
            c = (self.cpsr >> 29) & 1
            result = (self.registers[rd] + val + c) & 0xFFFFFFFF
        elif op == 6:  # SBC
            c = (self.cpsr >> 29) & 1
            result = (self.registers[rd] - val - (1 - c)) & 0xFFFFFFFF
        elif op == 7:  # ROR
            shift = val & 0x1F
            result = (
                (self.registers[rd] >> shift) | (self.registers[rd] << (32 - shift))
            ) & 0xFFFFFFFF
        elif op == 8:  # TST
            result = self.registers[rd] & val
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
            return 1
        elif op == 9:  # NEG
            result = (0 - val) & 0xFFFFFFFF
        elif op == 0xA:  # CMP
            result = (self.registers[rd] - val) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
            return 1
        elif op == 0xB:  # CMN
            result = (self.registers[rd] + val) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
            return 1
        elif op == 0xC:  # ORR
            result = self.registers[rd] | val
        elif op == 0xD:  # MUL
            result = (self.registers[rd] * val) & 0xFFFFFFFF
        elif op == 0xE:  # BIC
            result = self.registers[rd] & ~val
        elif op == 0xF:  # MVN
            result = (~val) & 0xFFFFFFFF

        self.write_register(rd, result)
        self.registers[15] += 2
        return 1

    def exec_thumb_hi(self, instr: int) -> int:
        """Thumb hi register operations/BX."""
        op = (instr >> 8) & 3
        rs = (instr >> 3) & 7
        rd = (instr >> 0) & 7
        h1 = (instr >> 7) & 1
        h2 = (instr >> 6) & 1

        if op == 3 and h1 == 0 and h2 == 1:  # BX
            target = self.registers[rs + (h1 << 3)]
            self.thumb_mode = (target & 1) != 0
            self.registers[15] = target & 0xFFFFFFFE
        else:
            rdn = rd + (h1 << 3)
            rm = rs + (h2 << 3)

            if op == 0:  # ADD
                result = (self.registers[rdn] + self.registers[rm]) & 0xFFFFFFFF
                self.write_register(rdn, result)
            elif op == 1:  # CMP
                result = (self.registers[rdn] - self.registers[rm]) & 0xFFFFFFFF
                self.cpsr = (
                    (self.cpsr & 0x0FFFFFFF)
                    | ((result >> 31) << 28)
                    | (0 if result == 0 else (1 << 30))
                )
            elif op == 2:  # MOV
                self.write_register(rdn, self.registers[rm])

        self.registers[15] += 2
        return 1

    def exec_thumb_pc_rel(self, instr: int) -> int:
        """Thumb PC-relative load."""
        rd = (instr >> 8) & 7
        offset = (instr & 0xFF) * 4
        addr = (self.registers[15] & 0xFFFFFFFC) + offset
        val = self.memory.read_u32(addr)
        self.write_register(rd, val)
        self.registers[15] += 2
        return 2

    def exec_thumb_load_store(self, instr: int) -> int:
        """Thumb LDR/STR."""
        is_load = (instr >> 11) & 1
        is_byte = (instr >> 10) & 1
        is_up = (instr >> 9) & 1
        rn = (instr >> 3) & 7
        rd = instr & 7
        offset = self.registers[rn & 7]

        if is_up:
            addr = offset + 0
        else:
            addr = offset - 0

        if is_load:
            val = self.memory.read_u32(addr)
            self.write_register(rd, val)
        else:
            self.memory.write_u32(addr, self.registers[rd])

        self.registers[15] += 2
        return 2

    def exec_thumb_hword(self, instr: int) -> int:
        """Thumb LDRH/STRH."""
        is_load = (instr >> 11) & 1
        is_up = (instr >> 9) & 1
        rn = (instr >> 3) & 7
        rd = instr & 7
        offset = ((instr >> 6) & 0x1F) * 2

        if is_up:
            addr = self.registers[rn] + offset
        else:
            addr = self.registers[rn] - offset

        if is_load:
            val = self.memory.read_u16(addr)
            self.write_register(rd, val)
        else:
            self.memory.write_u16(addr, self.registers[rd] & 0xFFFF)

        self.registers[15] += 2
        return 2


class ISRHandler:
    """Default ISR handler placed at 0x03007FFC in IWRAM."""

    def __init__(self, memory, interrupts):
        self.memory = memory
        self.interrupts = interrupts
        self._handlers = {}
    
    def register_handler(self, irq_id: int, callback):
        self._handlers[irq_id] = callback
    
    def handle_irq(self):
        if_reg = self.interrupts.if_reg
        ie_reg = self.interrupts.ie_reg
        pending = if_reg & ie_reg & 0xFFFF
        
        if pending == 0:
            return
        
        current_cpsr = self.cpsr
        thumb_mode_before = self.thumb_mode
        
        irq_bit = 0
        while irq_bit < 14:
            if pending & (1 << irq_bit):
                if irq_bit in self._handlers:
                    try:
                        self._handlers[irq_bit]()
                    except Exception as e:
                        print(f"  WARNING: ISR handler {irq_bit} raised exception: {e}")
                self.interrupts.if_reg &= ~(1 << irq_bit)
                
                if 8 <= irq_bit <= 11:
                    ch = irq_bit - 8
                    if hasattr(self.memory, 'dma') and self.memory.dma:
                        self.memory.dma.channels[ch].pending = False
                
                self.cpsr = current_cpsr
                self.thumb_mode = thumb_mode_before
                break
            irq_bit += 1
    
    def handle_vblank(self):
        if InterruptController.IRQ_VBLANK in self._handlers:
            self._handlers[InterruptController.IRQ_VBLANK]()
    
    def handle_hblank(self):
        if InterruptController.IRQ_HBLANK in self._handlers:
            self._handlers[InterruptController.IRQ_HBLANK]()
    
    def handle_vcounter(self):
        if InterruptController.IRQ_VCOUNTER in self._handlers:
            self._handlers[InterruptController.IRQ_VCOUNTER]()
    
    def handle_timer(self, channel: int):
        irq_id = InterruptController.IRQ_TIMER0 + channel
        if irq_id in self._handlers:
            self._handlers[irq_id]()
    
    def handle_dma(self, channel: int):
        irq_id = InterruptController.IRQ_DMA0 + channel
        if irq_id in self._handlers:
            self._handlers[irq_id]()
    
    def handle_keypad(self):
        if InterruptController.IRQ_KEYPAD in self._handlers:
            self._handlers[InterruptController.IRQ_KEYPAD]()
    
    def handle_gamepak(self):
        if InterruptController.IRQ_GAMEPAK in self._handlers:
            self._handlers[InterruptController.IRQ_GAMEPAK]()



"""GBA Input - Keyboard to GBA input register mapping"""

# GBA button bit positions in KEYINPUT register (0x04000130)
# Active low: 0 = pressed, 1 = released
GBA_KEYS = {
    "A": 0x01,  # bit 0
    "B": 0x02,  # bit 1
    "SELECT": 0x04,  # bit 2
    "START": 0x08,  # bit 3
    "RIGHT": 0x100,  # bit 8
    "LEFT": 0x200,  # bit 9
    "UP": 0x400,  # bit 10
    "DOWN": 0x800,  # bit 11
    "R": 0x1000,  # bit 12
    "L": 0x2000,  # bit 13
}

# Keyboard to GBA button mapping
# Arrow keys -> DPAD (bits 8-11), Z -> A, S -> B, Enter -> Start, Space -> Select
KEYBOARD_MAP = {
    "z": "A",
    "s": "B",
    "return": "START",
    "space": "SELECT",
    "right": "RIGHT",
    "left": "LEFT",
    "up": "UP",
    "down": "DOWN",
    "a": "L",
    "x": "R",
}

# Default value when no keys pressed (all bits = 1, meaning released)
# 14 bits (0-13) = 0x3FFF
DEFAULT_KEYS = 0x3FFF


class Input:
    """Handles keyboard to GBA input mapping.

    Maps keyboard keys to GBA KEYINPUT register (0x04000130).
    Uses lazy import of pygame to avoid dependency at import time.
    """

    def __init__(self):
        self._keys_pressed = DEFAULT_KEYS
        self._pygame = None
        self._pygame_available = None

    @property
    def _pygame_module(self):
        """Lazy import of pygame to avoid dependency at import time."""
        if self._pygame_available is None:
            try:
                import pygame

                # Initialize video subsystem for keyboard support
                pygame.display.init()
                pygame.key.set_repeat(100, 50)

                self._pygame = pygame
                self._pygame_available = True
            except ImportError:
                self._pygame = None
                self._pygame_available = False
        return self._pygame

    @property
    def pygame_available(self) -> bool:
        """Check if pygame is available."""
        if self._pygame_available is None:
            _ = self._pygame_module  # Trigger lazy import
        return self._pygame_available

    def poll(self) -> bool:
        """Poll keyboard state and update internal key state.

        Returns:
            True if polling successful, False if quit event received.
            Returns True even if pygame is not available (no-op).
        """
        if not self.pygame_available:
            # pygame not installed, return default (no keys pressed)
            self._keys_pressed = DEFAULT_KEYS
            return True

        pygame = self._pygame_module

        # Process events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False

        # Get current key states
        keys = pygame.key.get_pressed()

        # Start with all keys released (bits = 1)
        key_state = DEFAULT_KEYS  # 0x3FFF = all released

        # Check each mapped key
        for py_key_name, gba_key_name in KEYBOARD_MAP.items():
            py_key = getattr(pygame, f"K_{py_key_name}", None)
            if py_key is not None and keys[py_key]:
                # Key is pressed, clear the bit (active low)
                key_state &= ~GBA_KEYS[gba_key_name]

        self._keys_pressed = key_state
        return True

    def get_keys(self) -> int:
        """Get current key state as 16-bit mask.

        Returns:
            16-bit integer representing GBA KEYINPUT register.
            Bits are active low: 0 = pressed, 1 = released.
            0x3FFF (14 bits) = no keys pressed
        """
        return self._keys_pressed

    def update_from_pygame(self, keys) -> None:
        """Update GBA input state from pygame key state.

        Args:
            keys: pygame key state from pygame.key.get_pressed()
        """
        # Lazy import pygame if not already loaded
        if self._pygame is None:
            _ = self._pygame_module  # Trigger lazy import

        if not self.pygame_available:
            self._keys_pressed = DEFAULT_KEYS
            return

        pygame = self._pygame
        key_state = DEFAULT_KEYS
        for py_key_name, gba_key_name in KEYBOARD_MAP.items():
            py_key = getattr(pygame, f"K_{py_key_name}", None)
            if py_key is not None and keys[py_key]:
                key_state &= ~GBA_KEYS[gba_key_name]
        self._keys_pressed = key_state

    def update_keys(
        self,
        a=False,
        b=False,
        start=False,
        select=False,
        right=False,
        left=False,
        up=False,
        down=False,
        r=False,
        l=False,
    ):
        """Update GBA input from boolean arguments."""
        self._keys_pressed = 0x3FFF  # All not pressed
        if a:
            self._keys_pressed &= ~GBA_KEYS["A"]
        if b:
            self._keys_pressed &= ~GBA_KEYS["B"]
        if start:
            self._keys_pressed &= ~GBA_KEYS["START"]
        if select:
            self._keys_pressed &= ~GBA_KEYS["SELECT"]
        if right:
            self._keys_pressed &= ~GBA_KEYS["RIGHT"]
        if left:
            self._keys_pressed &= ~GBA_KEYS["LEFT"]
        if up:
            self._keys_pressed &= ~GBA_KEYS["UP"]
        if down:
            self._keys_pressed &= ~GBA_KEYS["DOWN"]
        if r:
            self._keys_pressed &= ~GBA_KEYS["R"]
        if l:
            self._keys_pressed &= ~GBA_KEYS["L"]


# Export constants for generated code
KEY_A = 0x01  # bit 0
KEY_B = 0x02  # bit 1
KEY_SELECT = 0x04  # bit 2
KEY_START = 0x08  # bit 3
KEY_RIGHT = 0x100  # bit 8
KEY_LEFT = 0x200  # bit 9
KEY_UP = 0x400  # bit 10
KEY_DOWN = 0x800  # bit 11
KEY_R = 0x1000  # bit 12
KEY_L = 0x2000  # bit 13

"""GBA BIOS SWI handlers - software interrupt implementations

GBA BIOS has 42 SWI handlers (0x00-0x29). Most games use only ~10-15 of them.
Critical handlers for game compatibility:
- Halt (0x02), IntrWait (0x04), VBlankIntrWait (0x05) - timing/interrupts
- CpuFastSet (0x0C) - fast memory operations
- Div/DivArm/Divmod (0x06-0x07) - arithmetic
- LZ77/Huff/RL decompression (0x11-0x15) - asset decompression
"""

import math
import struct
import time
from typing import List, Optional, Tuple


class BIOS:
    """GBA BIOS software interrupt handlers"""

    def __init__(self, memory):
        self.memory = memory
        self._frame_count = 0
        self._sleep_mode = False

    def swi_div(self, dividend: int, divisor: int) -> int:
        """Division: r0 = dividend / divisor, r1 = remainder"""
        if divisor == 0:
            # GBA ARM7TDMI: division by zero returns 0 (no exception)
            return 0

        result = dividend // divisor
        remainder = dividend % divisor

        if (dividend < 0) != (divisor < 0):
            if remainder != 0:
                result -= 1
                remainder = divisor - abs(remainder)

        return result

    def swi_divmod(self, dividend: int, divisor: int) -> tuple:
        """Division with remainder: returns (quotient, remainder)"""
        if divisor == 0:
            return (0, 0)

        quotient = dividend // divisor
        remainder = dividend % divisor

        if (dividend < 0) != (divisor < 0):
            if remainder != 0:
                quotient -= 1
                remainder = divisor - abs(remainder)

        return (quotient, remainder)

    def swi_divarm(self, dividend: int, divisor: int) -> int:
        """Division with r0 = dividend, r1 = divisor input/output"""
        if divisor == 0:
            return 0

        result = dividend // divisor
        remainder = dividend % divisor

        if (dividend < 0) != (divisor < 0):
            if remainder != 0:
                result -= 1
                remainder = divisor - abs(remainder)

        return result

    def swi_sqrt(self, n: int) -> int:
        """Integer square root using Newton's method"""
        if n <= 0:
            return 0

        x = n
        y = (x + 1) // 2

        while y < x:
            x = y
            y = (x + n // x) // 2

        return x

    def swi_cpuset(self, src: int, dst: int, count: int, control: int):
        """CPU Set - block copy/fill"""
        is_fill = bool(control & 0x01000000)
        is_32bit = bool(control & 0x02000000)

        if is_32bit:
            word_count = count
            if is_fill:
                value = src & 0xFFFFFFFF
                for i in range(word_count):
                    self.memory.write_u32(dst + i * 4, value)
            else:
                for i in range(word_count):
                    value = self.memory.read_u32(src + i * 4)
                    self.memory.write_u32(dst + i * 4, value)
        else:
            half_count = count
            if is_fill:
                value = src & 0xFFFF
                for i in range(half_count):
                    self.memory.write_u16(dst + i * 2, value)
            else:
                for i in range(half_count):
                    value = self.memory.read_u16(src + i * 2)
                    self.memory.write_u16(dst + i * 2, value)

    def swi_cpafastset(self, src: int, dst: int, count: int, control: int):
        """CPU Fast Set - faster block copy/fill (32-bit only)"""
        is_fill = bool(control & 0x01000000)

        word_count = count
        if is_fill:
            value = src & 0xFFFFFFFF
            for i in range(word_count):
                self.memory.write_u32(dst + i * 4, value)
        else:
            for i in range(word_count):
                value = self.memory.read_u32(src + i * 4)
                self.memory.write_u32(dst + i * 4, value)

    def swi_lz77_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x10:
            # Invalid header - return 0 bytes decompressed (graceful fallback)
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        src_pos = 8
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(src):
            flags = src[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    if src_pos + 1 >= len(src):
                        break
                    pair = struct.unpack("<H", src[src_pos : src_pos + 2])[0]
                    src_pos += 2

                    back = (pair >> 4) + 3
                    count = (pair & 0xF) + 3

                    for j in range(count):
                        if len(dst) >= expanded_size:
                            break
                        idx = len(dst) - back - 1
                        if 0 <= idx < len(dst):
                            dst.append(dst[idx])
                        else:
                            dst.append(0)
                else:
                    if src_pos < len(src):
                        dst.append(src[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_huff_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x11:
            # Invalid header - return 0 bytes decompressed (graceful fallback)
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        tree_size = src[4] if len(src) > 4 else 0
        src_pos = 8 + tree_size

        dst = bytearray()
        compressed = src[src_pos : src_pos + expanded_size]

        for byte in compressed[:expanded_size]:
            dst.append(byte)

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_rl_uncomp(self, src_addr: int, dst_addr: int) -> int:
        """Run-Length decompression"""
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x12:
            # Invalid header - return 0 bytes decompressed (graceful fallback)
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        src_pos = 8
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(src):
            flags = src[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    if src_pos >= len(src):
                        break
                    byte_val = src[src_pos]
                    src_pos += 1

                    if src_pos >= len(src):
                        break
                    count = src[src_pos] + 1
                    src_pos += 1

                    dst.extend([byte_val] * min(count, expanded_size - len(dst)))
                else:
                    if src_pos < len(src):
                        dst.append(src[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_huffman(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression - stub for now (no test ROMs use it)"""
        # Read Huffman header
        src = bytearray()
        for i in range(512):  # Read up to 512 bytes
            src.append(self.memory.read_u8(src_addr + i))
        
        # Check header (0x10 = Huffman)
        if len(src) < 8 or src[0] != 0x10:
            return 0
        
        expanded_size = struct.unpack("<I", src[1:5])[0]
        # TODO: Implement full Huffman decompression
        # For now, return 0 (no data decompressed)
        return 0

    def swi_vblank_intr_wait(self):
        if not hasattr(self, "memory") or not hasattr(self.memory, "cpu"):
            return
        
        cpu = self.memory.cpu
        memory = self.memory
        interrupts = getattr(memory, "_interrupts", None)
        
        first_call = cpu.registers[0] & 1
        
        if interrupts:
            vblank_occurred = False
            
            if first_call:
                # Wait for VBlank interrupt flag
                # In real GBA, CPU would halt here until interrupt occurs
                # We poll the IF register with minimal yield
                import time
                while not (interrupts.if_reg & (1 << 0)):
                    time.sleep(0.0001)  # Yield CPU briefly
                
                vblank_occurred = True
                interrupts.if_reg &= ~(1 << 0)
            
            if vblank_occurred:
                cpu.set_cpsr_flag("Z", True)
                cpu.registers[0] = 1
            else:
                cpu.set_cpsr_flag("Z", False)
                cpu.registers[0] = 0
        else:
            cpu.set_cpsr_flag("Z", True)
            cpu.registers[0] = 1
            time.sleep(0.016)
    def swi_intr_wait(self, wait_flag: int, vblank_flag: int):
        """Wait for interrupt"""
        if wait_flag:
            time.sleep(0.016)

    def swi_soft_reset(self):
        """Soft reset - restart from reset vector"""
        reset_addr = self.memory.read_u32(0x08000000)
        self.memory.cpu.registers[15] = reset_addr
        self.memory.cpu.running = True

    def swi_register_ram_reset(self, mode: int):
        """Reset/initialize RAM"""
        if mode & 0x01:
            for addr in range(0x02000000, 0x02400000):
                self.memory.write_u8(addr, 0)
        if mode & 0x02:
            for addr in range(0x03000000, 0x03007FFF):
                self.memory.write_u8(addr, 0)
        if mode & 0x04:
            for addr in range(0x05000000, 0x05000400):
                self.memory.write_u8(addr, 0)
        if mode & 0x08:
            for addr in range(0x06000000, 0x06018000):
                self.memory.write_u8(addr, 0)
        if mode & 0x10:
            for addr in range(0x07000000, 0x07000400):
                self.memory.write_u8(addr, 0)

    def swi_halt(self):
        """Halt CPU until next interrupt fires.

        Busy-waits on the IF register instead of sleeping — the interrupt
        controller sets bits when IRQ sources (VBlank, HBlank, timers, DMA,
        keypad) fire.  Clears all pending flags so the next Halt cycle starts
        from scratch.
        """
        self._sleep_mode = True
        interrupts = getattr(self.memory, "_interrupts", None)
        if interrupts is not None:
            # Spin until an enabled IRQ is pending
            while not interrupts.has_pending_interrupt():
                pass
            # Consume the pending bits so repeated calls don't short-circuit
            interrupts.clear_if()
        self._sleep_mode = False

    def swi_vsync(self):
        """Trigger a VBlank interrupt."""
        interrupts = getattr(self.memory, "_interrupts", None)
        if interrupts is not None:
            interrupts.vblank_irq()

    def swi_stop(self, mode: int):
        """Stop CPU until key press"""
        self._sleep_mode = True
        time.sleep(0.1)
        self._sleep_mode = False

    def swi_arctan2(self, y: int, x: int) -> int:
        """Arc tangent 2"""
        angle = math.atan2(y, x)
        return int((angle / (2 * math.pi)) * 0x10000) & 0xFFFF

    def swi_arctan(self, x: int) -> int:
        """Arc tangent"""
        angle = math.atan(x)
        return int((angle / (2 * math.pi)) * 0x10000) & 0xFFFF

    def swi_sin_cos(self, angle: int) -> Tuple[int, int]:
        """Sine and cosine"""
        rad = (angle / 0x10000) * 2 * math.pi
        sin_val = int(math.sin(rad) * 0x10000)
        cos_val = int(math.cos(rad) * 0x10000)
        return (sin_val, cos_val)

    def swi_sin(self, angle: int) -> int:
        """Sine"""
        rad = (angle / 0x10000) * 2 * math.pi
        return int(math.sin(rad) * 0x10000)

    def swi_cos(self, angle: int) -> int:
        """Cosine"""
        rad = (angle / 0x10000) * 2 * math.pi
        return int(math.cos(rad) * 0x10000)

    def swi_bit_count(self, value: int) -> int:
        """Count set bits"""
        return bin(value & 0xFFFFFFFF).count("1")

    def swi_obj_affine_set(self, param_addr: int, angle: int, scale_x: int, scale_y: int):
        """Set up affine matrix for sprites"""
        rad = (angle / 0x10000) * 2 * math.pi
        cos_val = math.cos(rad)
        sin_val = math.sin(rad)

        a = int(cos_val * scale_x)
        b = int(-sin_val * scale_x)
        c = int(sin_val * scale_y)
        d = int(cos_val * scale_y)

        self.memory.write_u16(param_addr, a & 0xFFFF)
        self.memory.write_u16(param_addr + 2, b & 0xFFFF)
        self.memory.write_u16(param_addr + 4, c & 0xFFFF)
        self.memory.write_u16(param_addr + 6, d & 0xFFFF)

    def swi_bg_affine_set(self, param_addr: int, angle: int, scale_x: int, scale_y: int):
        """Set up affine matrix for backgrounds"""
        self.swi_obj_affine_set(param_addr, angle, scale_x, scale_y)

    def swi_get_time(self) -> int:
        """Get current time"""
        return int(time.time() % 86400)

    def swi_set_sleep(self, seconds: int):
        """Set sleep duration"""
        time.sleep(min(seconds, 60))

    def swi_is_sleep(self) -> bool:
        """Check if in sleep mode"""
        return self._sleep_mode

    def swi_ref_count(self, value: int) -> int:
        """Count trailing zeros"""
        if value == 0:
            return 32
        count = 0
        while (value & 1) == 0:
            value >>= 1
            count += 1
        return count

    def swi_get_clock(self) -> int:
        """Get system clock"""
        return int(time.time() * 1000) & 0xFFFFFFFF

    def swi_set_sound_mode(self, mode: int):
        """Set sound mode (0=off, 1=on, 2=DSound, 3=reserved)"""
        self._sound_mode = mode & 3

    def swi_get_sound_mode(self) -> int:
        """Get current sound mode"""
        return getattr(self, "_sound_mode", 1)

    def swi_sound_bias_change(self, bias: int):
        """Change sound bias level"""
        self._sound_bias = bias

    def swi_midi_alt_scale(self, note: int, scale: int) -> int:
        """MIDI alternate scale note"""
        return note

    def swi_midi_alt_key(self, note: int, key: int) -> int:
        """MIDI alternate key"""
        return note

    def swi_midi_inc_octave(self, note: int) -> int:
        """MIDI increase octave"""
        return min(note + 12, 127)

    def swi_midi_dec_octave(self, note: int) -> int:
        """MIDI decrease octave"""
        return max(note - 12, 0)

    def swi_midi_inc_note(self, note: int) -> int:
        """MIDI increase note"""
        return min(note + 1, 127)

    def swi_midi_dec_note(self, note: int) -> int:
        """MIDI decrease note"""
        return max(note - 1, 0)

    def swi_midi_chord(self, root_note: int, chord_type: int) -> List[int]:
        """MIDI chord - returns note numbers for chord"""
        # Chord intervals: 0=major, 1=minor, 2=dim, 3=aug, etc.
        intervals = {
            0: [0, 4, 7],  # Major
            1: [0, 3, 7],  # Minor
            2: [0, 3, 6],  # Diminished
            3: [0, 4, 8],  # Augmented
            4: [0, 4, 7, 11],  # Major 7th
            5: [0, 3, 7, 10],  # Minor 7th
            6: [0, 4, 7, 10],  # Dominant 7th
        }
        chord_intervals = intervals.get(chord_type % 7, intervals[0])
        return [(root_note + interval) % 128 for interval in chord_intervals]

    def swi_midi_volume_voice(self, channel: int, volume: int, voice: int):
        """MIDI set volume for voice"""
        if not hasattr(self, "_midi_volumes"):
            self._midi_volumes = {}
        self._midi_volumes[(channel, voice)] = volume & 0xFF

    def swi_midi_freq_note(self, freq: int) -> int:
        """Convert frequency to MIDI note number"""
        if freq <= 0:
            return 0
        # MIDI note = 69 + 12 * log2(freq / 440)
        import math

        note = 69 + 12 * math.log2(freq / 440.0)
        return max(0, min(127, int(note + 0.5)))

    def swi_midi_note_to_freq(self, note: int) -> int:
        """Convert MIDI note number to frequency"""
        if note < 0:
            return 0
        # freq = 440 * 2^((note - 69) / 12)
        import math

        freq = 440.0 * (2.0 ** ((note - 69) / 12.0))
        return int(freq)

    def swi_2d_geo_set(self, param: int, value: int):
        """Set 2D geometry parameter"""
        if not hasattr(self, "_geo_params"):
            self._geo_params = {}
        self._geo_params[param] = value

    def swi_2d_geo_get(self, param: int) -> int:
        """Get 2D geometry parameter"""
        return getattr(self, "_geo_params", {}).get(param, 0)

    def swi_1d_to_2d_based_on_width(self, x: int, width: int) -> Tuple[int, int]:
        """Convert 1D coordinate to 2D based on width"""
        y = x // width
        x = x % width
        return (x, y)

    def swi_1d_to_2d_based_on_height(self, x: int, height: int) -> Tuple[int, int]:
        """Convert 1D coordinate to 2D based on height"""
        y = x // height
        x = x % height
        return (x, y)

    def swi_2d_to_1d_based_on_width(self, x: int, y: int, width: int) -> int:
        """Convert 2D coordinate to 1D based on width"""
        return y * width + x

    def swi_2d_to_1d_based_on_height(self, x: int, y: int, height: int) -> int:
        """Convert 2D coordinate to 1D based on height"""
        return y * height + x

    def swi_rle_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """RLE decompression to WRAM"""
        return self.swi_rl_uncomp(src_addr, dst_addr)

    def swi_rle_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """RLE decompression to VRAM"""
        return self.swi_rl_uncomp(src_addr, dst_addr)

    def swi_diff_uncomp_filter(self, src_addr: int, dst_addr: int) -> int:
        """Difference decompression with filter"""
        src = self.memory.read_bytes(src_addr, 102400)
        if len(src) < 8:
            # Invalid header - return 0 bytes decompressed (graceful fallback)
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        filter_type = src[0]

        dst = bytearray()
        prev = 0

        for i in range(8, len(src)):
            if len(dst) >= expanded_size:
                break
            diff = src[i] if filter_type == 0x00 else src[i]
            # Apply difference
            value = (prev + diff) & 0xFF
            dst.append(value)
            prev = value

        for i, byte in enumerate(dst):
            self.memory.write_u8(dst_addr + i, byte)

        return len(dst)

    def swi_huff_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression to WRAM"""
        return self.swi_huff_uncomp(src_addr, dst_addr)

    def swi_huff_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """Huffman decompression to VRAM"""
        return self.swi_huff_uncomp(src_addr, dst_addr)

    def swi_lz77_uncomp_wram(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression to WRAM"""
        return self.swi_lz77_uncomp(src_addr, dst_addr)

    def swi_lz77_uncomp_vram(self, src_addr: int, dst_addr: int) -> int:
        """LZ77 decompression to VRAM"""
        return self.swi_lz77_uncomp(src_addr, dst_addr)

"""GBA Interrupt Controller"""


class InterruptController:
    """Interrupt controller managing IE, IF, and IME registers.

    Interrupt sources (bit positions):
        - VBlank: 0
        - HBlank: 1
        - VCounter: 2
        - Timer0-3: 3-6
        - DMA0-3: 8-11
        - KeyPad: 12
        - GamePak: 13
    """

    # Interrupt source bit positions
    IRQ_VBLANK = 0
    IRQ_HBLANK = 1
    IRQ_VCOUNTER = 2
    IRQ_TIMER0 = 3
    IRQ_TIMER1 = 4
    IRQ_TIMER2 = 5
    IRQ_TIMER3 = 6
    IRQ_DMA0 = 8
    IRQ_DMA1 = 9
    IRQ_DMA2 = 10
    IRQ_DMA3 = 11
    IRQ_KEYPAD = 12
    IRQ_GAMEPAK = 13

    def __init__(self):
        # IE: Interrupt Enable register (16-bit) - enables per-interrupt sources
        self.ie_reg = 0x0000
        # IF: Interrupt Flags register (16-bit) - raised interrupts, write 1 to clear
        self.if_reg = 0x0000
        # IME: Interrupt Master Enable register (1-bit)
        self.ime_reg = 0x0000
        # Handlers stored by interrupt source bit position
        self._handlers = {}
        # Optimized: pre-compute enabled interrupt mask
        self._enabled_mask = 0
        # Batch processing: collect pending interrupts
        self._pending_batch = []
        # IRQ check frequency (every N calls)
        self._irq_check_counter = 0
        self._irq_check_interval = 1  # Check every frame (can be increased for performance)

    def register_handler(self, irq_id: int, callback):
        """Register a callback for a specific interrupt source.

        Args:
            irq_id: Interrupt source bit position (0-13)
            callback: Function to call when interrupt fires and is enabled
        """
        self._handlers[irq_id] = callback

    def fire(self, irq_id: int):
        """Fire an interrupt - set the IF flag and call handler if enabled.

        Args:
            irq_id: Interrupt source bit position (0-13)
        """
        # Set the interrupt flag in IF register
        self.if_reg |= 1 << irq_id

        # Check if interrupt is enabled (IME=1 and IE bit for this irq is set)
        if self.ime_reg & 0x0001 and (self.ie_reg & (1 << irq_id)):
            # Call the handler if registered
            if irq_id in self._handlers:
                self._handlers[irq_id]()

    def vblank_irq(self):
        """Convenience method to fire a VBlank interrupt (IRQ 0)."""
        self.fire(self.IRQ_VBLANK)

    def hblank_irq(self):
        """Convenience method to fire a HBlank interrupt (IRQ 1)."""
        self.fire(self.IRQ_HBLANK)

    def vcounter_irq(self):
        """Convenience method to fire a VCounter interrupt (IRQ 2)."""
        self.fire(self.IRQ_VCOUNTER)

    def timer_irq(self, channel: int):
        """Convenience method to fire a timer interrupt.

        Args:
            channel: Timer channel (0-3), maps to IRQ 3-6
        """
        if 0 <= channel <= 3:
            self.fire(self.IRQ_TIMER0 + channel)

    def dma_irq(self, channel: int):
        """Convenience method to fire a DMA interrupt.

        Args:
            channel: DMA channel (0-3), maps to IRQ 8-11
        """
        if 0 <= channel <= 3:
            self.fire(self.IRQ_DMA0 + channel)

    def keypad_irq(self):
        """Convenience method to fire a KeyPad interrupt (IRQ 12)."""
        self.fire(self.IRQ_KEYPAD)

    def gamepak_irq(self):
        """Convenience method to fire a GamePak interrupt (IRQ 13)."""
        self.fire(self.IRQ_GAMEPAK)

    def write_ie(self, val: int):
        """Write to IE (Interrupt Enable) register.

        Args:
            val: 16-bit value to write
        """
        self.ie_reg = val & 0xFFFF
        # Optimized: pre-compute enabled interrupt mask
        self._enabled_mask = self.ie_reg if self.ime_reg & 0x0001 else 0

    def write_if(self, val: int):
        """Write to IF (Interrupt Flags) register.

        Writing 1 to a bit clears that interrupt flag.

        Args:
            val: 16-bit value to write
        """
        # Clear bits where val has 1s (write-1-to-clear behavior)
        self.if_reg &= ~(val & 0xFFFF)

    def write_ime(self, val: int):
        """Write to IME (Interrupt Master Enable) register.

        Args:
            val: 16-bit value (only bit 0 is significant)
        """
        self.ime_reg = val & 0x0001
        # Optimized: update enabled mask
        self._enabled_mask = self.ie_reg if self.ime_reg & 0x0001 else 0

    def read_ie(self) -> int:
        """Read IE register."""
        return self.ie_reg

    def read_if(self) -> int:
        """Read IF register."""
        return self.if_reg

    def read_ime(self) -> int:
        """Read IME register."""
        return self.ime_reg

    def get_pending_interrupts(self) -> int:
        """Get bitmask of pending and enabled interrupts."""
        return self.if_reg & self.ie_reg

    def has_pending_interrupt(self) -> bool:
        """Check if any enabled interrupt is pending (optimized with bitfield)."""
        # Optimized: single bitwise operation instead of multiple checks
        return (self.if_reg & self._enabled_mask) != 0
    
    def process_pending_interrupts(self) -> int:
        """Process all pending interrupts in batch. Returns count of interrupts processed.
        
        This is an optimized method that processes all pending interrupts at once
        instead of checking one by one.
        """
        if not (self.ime_reg & 0x0001):
            return 0
        
        # Get pending and enabled interrupts as a bitmask
        pending = self.if_reg & self.ie_reg
        if pending == 0:
            return 0
        
        count = 0
        # Process each pending interrupt
        for irq_id in range(14):
            if pending & (1 << irq_id):
                if irq_id in self._handlers:
                    self._handlers[irq_id]()
                    count += 1
        
        return count

    def clear_if(self):
        """Clear all interrupt flags."""
        self.if_reg = 0x0000


def set_vblank_flag():
    interrupts.fire(InterruptController.IRQ_VBLANK)

    def set_ime(self, enabled: bool):
        """Set IME register.

        Args:
            enabled: True to enable interrupts, False to disable
        """
        self.ime_reg = 0x0001 if enabled else 0x0000

"""GBA DMA Controller"""

from typing import List, Optional


# DMA Control Register Bits
DMA_ENABLE = 0x80000000
DMA_TIMING_MASK = 0x30000000
DMA_TIMING_IMMEDIATE = 0x30000000  # 0b11
DMA_TIMING_VBLANK = 0x20000000     # 0b10
DMA_TIMING_HBLANK = 0x10000000     # 0b01
DMA_TIMING_CUSTOM = 0x00000000
DMA3_TRIGGER_MASK = 0x0F000000
DMA3_TRIGGER_IMMEDIATE = 0x00000000
DMA3_TRIGGER_VBLANK = 0x01000000
DMA3_TRIGGER_HBLANK = 0x02000000
DMA3_TRIGGER_FIFO_A = 0x03000000
DMA3_TRIGGER_FIFO_B = 0x04000000

DMA_SRC_INCREMENT = 0x00000000
DMA_SRC_DECREMENT = 0x00100000
DMA_SRC_FIXED = 0x00200000

DMA_DST_INCREMENT = 0x00000000
DMA_DST_DECREMENT = 0x00001000
DMA_DST_FIXED = 0x00002000

DMA_REPEAT = 0x00000010
DMA_16BIT = 0x00000000
DMA_32BIT = 0x04000000
DMA_GAMEPAK_DRQ = 0x08000000

# MMIO Register Addresses
DMA0_SRC_ADDR = 0x040000B0
DMA0_DST_ADDR = 0x040000B4
DMA0_COUNT = 0x040000B8
DMA0_CONTROL = 0x040000BC

DMA1_SRC_ADDR = 0x040000C0
DMA1_DST_ADDR = 0x040000C4
DMA1_COUNT = 0x040000C8
DMA1_CONTROL = 0x040000CC

DMA2_SRC_ADDR = 0x040000D0
DMA2_DST_ADDR = 0x040000D4
DMA2_COUNT = 0x040000D8
DMA2_CONTROL = 0x040000DC

DMA3_SRC_ADDR = 0x040000E0
DMA3_DST_ADDR = 0x040000E4
DMA3_COUNT = 0x040000E8
DMA3_CONTROL = 0x040000EC


class DMAChannel:
    """Individual DMA channel (0-3)"""
    
    def __init__(self, channel_id: int, mem):
        self.channel_id = channel_id
        self.mem = mem
        self.src_addr: int = 0
        self.dst_addr: int = 0
        self.count: int = 0
        self.control: int = 0
        self.enabled: bool = False
        self.busy: bool = False
        self.pending: bool = False
        self._interrupts = None
        self._irq_enabled: bool = False

    def attach_interrupts(self, interrupts):
        """Attach interrupt controller for DMA completion IRQs"""
        self._interrupts = interrupts

    @property
    def irq_enabled(self) -> bool:
        """Check if IRQ on completion is enabled (bit 14)"""
        return (self.control & 0x40000000) != 0

    def get_timing_bits(self) -> int:
        """Extract timing mode bits (bits 29-28)"""
        return self.control & DMA_TIMING_MASK

    def is_immediate(self) -> bool:
        """Check if timing is immediate (start right away)"""
        return self.get_timing_bits() == DMA_TIMING_IMMEDIATE

    def is_vblank(self) -> bool:
        """Check if timing is VBlank"""
        return self.get_timing_bits() == DMA_TIMING_VBLANK

    def is_hblank(self) -> bool:
        """Check if timing is HBlank"""
        return self.get_timing_bits() == DMA_TIMING_HBLANK

    def is_custom(self) -> bool:
        return self.get_timing_bits() == DMA_TIMING_CUSTOM

    def get_dma3_trigger_bits(self) -> int:
        if self.channel_id != 3:
            return 0
        return self.control & DMA3_TRIGGER_MASK

    def is_fifo_a_trigger(self) -> bool:
        if self.channel_id != 3:
            return False
        return self.get_dma3_trigger_bits() == DMA3_TRIGGER_FIFO_A

    def is_fifo_b_trigger(self) -> bool:
        if self.channel_id != 3:
            return False
        return self.get_dma3_trigger_bits() == DMA3_TRIGGER_FIFO_B

    def get_src_increment(self) -> int:
        """Get source increment mode (bits 21-20)"""
        return (self.control >> 20) & 0x3

    def get_dst_increment(self) -> int:
        """Get destination increment mode (bits 13-12)"""
        return (self.control >> 12) & 0x3

    def is_32bit(self) -> bool:
        """Check if transfer is 32-bit"""
        return (self.control & DMA_32BIT) != 0

    def is_repeat(self) -> bool:
        """Check if repeat mode is enabled"""
        return (self.control & DMA_REPEAT) != 0

    def get_transfer_size(self) -> int:
        """Get transfer size in bytes"""
        return 4 if self.is_32bit() else 2

    def read_from_memory(self):
        """Read DMA registers from memory"""
        base = 0x040000B0 + (self.channel_id * 0x10)
        self.src_addr = self.mem.read_u32(base)
        self.dst_addr = self.mem.read_u32(base + 4)
        self.count = self.mem.read_u32(base + 8)
        self.control = self.mem.read_u32(base + 12)
        self.enabled = (self.control & DMA_ENABLE) != 0

    def write_to_memory(self):
        """Write DMA registers to memory"""
        base = 0x040000B0 + (self.channel_id * 0x10)
        self.mem.write_u32(base, self.src_addr)
        self.mem.write_u32(base + 4, self.dst_addr)
        self.mem.write_u32(base + 8, self.count)
        self.mem.write_u32(base + 12, self.control)

    def get_count_value(self) -> int:
        """Get actual transfer count (0 = 0x10000 or 0x4000)"""
        if self.count == 0:
            return 0x10000 if self.is_32bit() else 0x4000
        return self.count


class DMA:
    """GBA DMA Controller with 4 channels"""
    
    # FIFO addresses for sound DMA
    FIFO_A_ADDR = 0x040000A0
    FIFO_B_ADDR = 0x040000A4
    
    def __init__(self):
        self.mem = None  # Set by attach_memory
        self._interrupts = None
        self._apu = None  # Set by attach_apu for FIFO support
        self.channels: List[DMAChannel] = [
            DMAChannel(0, None),
            DMAChannel(1, None),
            DMAChannel(2, None),
            DMAChannel(3, None),
        ]
        # self._setup_mmio() - called after memory is attached

    def attach_memory(self, mem):
        """Attach memory for DMA transfers"""
        self.mem = mem
        for ch in self.channels:
            ch.mem = mem

    def attach_apu(self, apu):
        """Attach APU for FIFO trigger support"""
        self._apu = apu

    def fifo_a_is_empty(self) -> bool:
        """Check if FIFO A is empty (trigger condition)"""
        if self._apu is None:
            return False
        return len(self._apu.fifo_a.data) == 0

    def fifo_b_is_empty(self) -> bool:
        """Check if FIFO B is empty (trigger condition)"""
        if self._apu is None:
            return False
        return len(self._apu.fifo_b.data) == 0

    def attach_interrupts(self, interrupts):
        """Attach interrupt controller for DMA completion IRQs"""
        self._interrupts = interrupts
        for ch in self.channels:
            ch.attach_interrupts(interrupts)

    def _setup_mmio(self):
        """Setup MMIO write handlers for DMA control registers"""
        # DMA control registers at 0x040000B0, 0x040000B8, 0x040000C0, 0x040000C8
        # Each DMA channel has a control register that triggers the transfer
        for i in range(4):
            dma_ctrl_addr = 0x040000B0 + (i * 8)
            self.memory.set_write_handler(
                dma_ctrl_addr,
                lambda addr, value, channel=i: self._dma_control_handler(channel, addr, value)
            )

    def _make_mmio_handler(self, channel: int):
        """Create MMIO handler for channel control register"""
        def handler(addr: int, value: int):
            ch = self.channels[channel]
            ch.control = value
            ch.enabled = (value & DMA_ENABLE) != 0
            
            # Immediate DMA starts immediately when enabled
            if ch.enabled and ch.is_immediate():
                ch.pending = True
                
            # Custom trigger (VCount/timer) starts when trigger fires
            if ch.enabled and ch.is_custom():
                ch.pending = True

        return handler

    def start_transfer(self, channel: int):
        """Manually start a DMA transfer"""
        if channel < 0 or channel > 3:
            return

        ch = self.channels[channel]
        ch.read_from_memory()

        if not ch.enabled:
            return

        self._do_transfer(ch)

    def _do_transfer(self, ch: DMAChannel):
        """Execute DMA transfer for a channel"""
        if ch.busy:
            return

        ch.busy = True

        src_inc = ch.get_src_increment()
        dst_inc = ch.get_dst_increment()
        count = ch.get_count_value()
        transfer_size = ch.get_transfer_size()

        src = ch.src_addr
        dst = ch.dst_addr

        # Perform the actual memory transfer
        for _ in range(count):
            if transfer_size == 4:
                value = self.mem.read_u32(src)
                # Handle FIFO destinations specially
                if dst == DMA.FIFO_A_ADDR and self._apu:
                    self._apu.fifo_a.write(value & 0xFF)
                    if count > 1:
                        self._apu.fifo_a.write((value >> 8) & 0xFF)
                        self._apu.fifo_a.write((value >> 16) & 0xFF)
                        self._apu.fifo_a.write((value >> 24) & 0xFF)
                elif dst == DMA.FIFO_B_ADDR and self._apu:
                    self._apu.fifo_b.write(value & 0xFF)
                    if count > 1:
                        self._apu.fifo_b.write((value >> 8) & 0xFF)
                        self._apu.fifo_b.write((value >> 16) & 0xFF)
                        self._apu.fifo_b.write((value >> 24) & 0xFF)
                else:
                    self.mem.write_u32(dst, value)
                src += 4
                dst += 4
            else:  # 16-bit
                value = self.mem.read_u16(src)
                if dst == DMA.FIFO_A_ADDR and self._apu:
                    self._apu.fifo_a.write(value & 0xFF)
                    self._apu.fifo_a.write((value >> 8) & 0xFF)
                elif dst == DMA.FIFO_B_ADDR and self._apu:
                    self._apu.fifo_b.write(value & 0xFF)
                    self._apu.fifo_b.write((value >> 8) & 0xFF)
                else:
                    self.mem.write_u16(dst, value)
                src += 2
                dst += 2

        # Update addresses based on increment mode
        ch.src_addr = self._adjust_address(ch.src_addr, src_inc, count * transfer_size)
        ch.dst_addr = self._adjust_address(ch.dst_addr, dst_inc, count * transfer_size)

        # Handle repeat mode
        if ch.is_repeat():
            ch.count = ch.get_count_value()  # Reload count
        else:
            # Disable DMA after transfer (clear enable bit)
            ch.control &= ~DMA_ENABLE
            ch.enabled = False

        # Write back updated values
        ch.write_to_memory()
        
        ch.busy = False
        ch.pending = False  # Clear pending flag after transfer completes
        
        # Fire DMA completion interrupt if enabled
        if ch.irq_enabled and self._interrupts:
            self._interrupts.dma_irq(ch.channel_id)

    def _adjust_address(self, addr: int, increment_mode: int, transfer_bytes: int) -> int:
        """Adjust address based on increment mode"""
        if increment_mode == 0:  # Increment
            return addr + transfer_bytes
        elif increment_mode == 1:  # Decrement
            return addr - transfer_bytes
        else:  # Fixed (2) or reserved (3)
            return addr

    def step(self):
        """Process DMA step (called every frame for immediate DMA)"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            # Handle immediate DMA (should have already fired, but check pending)
            if ch.is_immediate():
                if ch.pending:
                    ch.pending = False
                    self._do_transfer(ch)

    def vblank_fire(self):
        """Process VBlank-triggered DMA transfers"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_vblank():
                self._do_transfer(ch)
                ch.pending = False

    def hblank_fire(self):
        """Process HBlank-triggered DMA transfers"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_hblank():
                self._do_transfer(ch)
                ch.pending = False

    def custom_fire(self):
        """Process custom-triggered DMA (VCount/timer)"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_custom() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def timer_trigger(self, timer_index: int):
        """Trigger DMA from timer overflow (DMA1/2 only for sound)"""
        # DMA channel 1 and 2 can be triggered by timer
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            # Custom timing means triggered by VCount or timer
            if ch.is_custom() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False
    
    def attach_apu(self, apu):
        """Attach APU for FIFO support - DMA1/2 write to FIFO A/B for audio"""
        self._apu = apu
    
    def _fifo_dma_transfer(self, channel: int):
        """
        DMA to FIFO transfer for audio channels 1 and 2.
        
        GBA DMA FIFO behavior:
        - DMA1 writes to FIFO A (0x040000A0) - Square wave channel
        - DMA2 writes to FIFO B (0x040000A4) - Triangle/noise channel
        - 16-bit DMA count transfers 16-bit values (samples)
        - DMA reads 16-bit samples from WAVE_RAM (0x04000090)
        """
        if channel < 0 or channel > 2:
            return
        
        ch = self.channels[channel]
        
        # Get DMA timer period from SOUNDCNT register (bits 2-5)
        timer_period = ch.timer_period if ch.timer_period > 0 else 0
        
        # Read 16-bit samples from WAVE_RAM and write to FIFO
        fifo_addr = self.FIFO_A_ADDR if channel == 1 else self.FIFO_B_ADDR
        base = (channel - 1) * 0x200  # WAVE_RAM: CH1=0x0, CH2=0x200
        
        for _ in range(ch.get_count_value()):
            if not ch.enabled or ch.busy:
                break
            
            # Read 16-bit sample from WAVE_RAM (little-endian)
            sample = self.mem.read_u16(base)
            
            # Write to FIFO (16-bit read becomes 8-bit byte for FIFO)
            if sample & 0x8000:  # MSB indicates next byte is high byte
                self.mem.write_u8(fifo_addr, (sample & 0xFF) >> 4)  # Scale by 1/16
                fifo_addr += 1
                self.mem.write_u8(fifo_addr, (sample >> 12) & 0x0F)  # Scale high byte
                fifo_addr += 1
            else:
                self.mem.write_u8(fifo_addr, (sample >> 4) & 0x0F)  # Scale by 1/16
                fifo_addr += 1
        
        ch.busy = False
    
    def fifo_a_step(self):
        """Step FIFO A - processes audio samples from DMA"""
        if not self._apu:
            return
        self._apu.fifo_a.timer += 1
        
        if self._apu.fifo_a.timer >= self._apu.fifo_a.timer_period:
            self._apu.fifo_a.timer = 0
            self._apu.fifo_a.read()  # Generate sample for audio channel

    def fifo_a_empty_fire(self):
        """Process FIFO A empty trigger for DMA3"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_fifo_a_trigger() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def fifo_b_empty_fire(self):
        """Process FIFO B empty trigger for DMA3"""
        for ch in self.channels:
            ch.read_from_memory()

            if not ch.enabled or ch.busy:
                continue

            if ch.is_fifo_b_trigger() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def _fifo_dma_write(self, channel: int, fifo_addr: int):
        """DMA write to FIFO A/B for audio data (16-bit to 8-bit scaling)"""
        if channel < 0 or channel > 2:
            return
        
        ch = self.channels[channel]
        if not ch.enabled or ch.busy:
            return
        
        # Get timer period for this DMA channel (used for audio timing)
        # In real hardware, SOUNDCNT_H bits 2-5 control timer period
        period = ch.timer_period if ch.timer_period > 0 else 0
        ch.timer_period = period
        
        # Transfer from source to FIFO
        count = ch.get_count_value()
        src = ch.src_addr
        
        for _ in range(count):
            if not ch.enabled or ch.busy:
                break
            
            # Read 16-bit sample (little-endian)
            sample = self.mem.read_u16(src)
            
            # Write to FIFO: scale 16-bit sample to 8-bit (shift right by 4)
            # GBA DMA FIFO takes 8-bit values for audio
            scaled = (sample >> 4) & 0x0F  # Scale by 1/16
            self.mem.write_u8(fifo_addr, scaled)
            src += 2
            fifo_addr += 1
        
        # Mark busy/done
        if ch.control & DMA_ENABLE:  # Still enabled
            ch.busy = True
        else:
            ch.busy = False

    def get_channel(self, channel: int) -> Optional[DMAChannel]:
        """Get DMA channel by index"""
        if 0 <= channel <= 3:
            return self.channels[channel]
        return None


def clear_dma_pending(dma_instance):
    """Clear pending flags on all DMA channels"""
    for ch in dma_instance.channels:
        ch.pending = False

"""GBA APU (Audio Processing Unit) - Optimized Implementation"""

import pygame
import threading
from collections import deque
import array

# Optional Numba JIT support
try:
    from numba import njit
    numba_available = True
except ImportError:
    numba_available = False
    def njit(f=None, **kwargs):
        return f if f else lambda x: x


class SquareWaveChannel:
    """Square wave sound channel (CH1/CH2)"""

    DUTY_PATTERNS = [
        0b00000001,  # 12.5%
        0b00000011,  # 25%
        0b00001111,  # 50%
        0b11111111,  # 75%
    ]

    def __init__(self):
        self.enabled = False
        self.volume = 0
        self.frequency = 0
        self.duty_cycle = 0
        self.envelope_volume = 0
        self.envelope_steps = 0
        self.envelope_increase = False
        self.length = 0
        self.length_enable = False
        self.length_counter = 0
        self.envelope_counter = 0
        self.envelope_volume_current = 0
        self.sweep_shift = 0
        self.sweep_decrease = False
        self.sweep_steps = 0
        self.sweep_counter = 0
        self.timer = 0
        self.timer_period = 0
        self.output_bit = 0

    def step(self, sample_rate: int) -> int:
        """Generate one sample. Returns volume level (0-15)."""
        if not self.enabled:
            return 0

        # Length counter
        if self.length_enable and self.length > 0:
            self.length_counter += 1
            if self.length_counter >= (256 - self.length):
                self.enabled = False
                return 0

        # Envelope
        if self.envelope_steps > 0:
            self.envelope_counter += 1
            if self.envelope_counter >= self.envelope_steps:
                self.envelope_counter = 0
                if self.envelope_increase:
                    self.envelope_volume_current = min(15, self.envelope_volume_current + 1)
                else:
                    self.envelope_volume_current = max(0, self.envelope_volume_current - 1)
                if self.envelope_volume_current == 0:
                    self.enabled = False
                    return 0
        else:
            self.envelope_volume_current = self.envelope_volume

        # Timer/frequency
        if self.frequency > 0:
            self.timer_period = 2048 - self.frequency
        else:
            self.timer_period = 2048

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            self.output_bit = 1 - self.output_bit

            # Sweep
            if self.sweep_steps > 0:
                self.sweep_counter -= 1
                if self.sweep_counter <= 0:
                    self.sweep_counter = self.sweep_steps
                    if self.sweep_decrease:
                        self.frequency -= self.frequency >> self.sweep_shift
                    else:
                        self.frequency += self.frequency >> self.sweep_shift
                    if self.frequency > 2047:
                        self.enabled = False
                        return 0

        return self.output_bit * self.envelope_volume_current

    def trigger(self):
        """Trigger the channel (key on)"""
        self.timer = 0
        self.output_bit = 0
        self.envelope_counter = 0
        self.envelope_volume_current = self.envelope_volume
        self.length_counter = 0
        self.sweep_counter = self.sweep_steps
        self.enabled = True


class WaveChannel:
    """Wave playback channel (CH3)"""

    def __init__(self):
        self.enabled = False
        self.volume = 0
        self.frequency = 0
        self.wave_ram = [0] * 32
        self.wave_bank = 0
        self.length = 0
        self.length_enable = False
        self.length_counter = 0
        self.timer = 0
        self.timer_period = 0
        self.counter = 0
        self.format_8bit = False

    def step(self, sample_rate: int, wave_ram: list, wave_bank: int) -> int:
        """Generate one sample."""
        if not self.enabled:
            return 0

        # Length counter
        if self.length_enable and self.length > 0:
            self.length_counter += 1
            if self.length_counter >= 256:
                self.enabled = False
                return 0

        # Frequency timer
        if self.frequency > 0:
            self.timer_period = 2048 - self.frequency
        else:
            self.timer_period = 2048

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0
            self.counter += 1

        # Read from wave RAM — select bank based on wave_bank register
        nibble_index = self.counter % 64
        byte_index = nibble_index // 2
        wave_value = wave_ram[wave_bank][byte_index % 32]

        if nibble_index % 2 == 0:
            sample = wave_value & 0x0F
        else:
            sample = (wave_value >> 4) & 0x0F

        # Apply volume
        if self.volume == 0:
            return 0
        elif self.volume == 1:
            return sample
        elif self.volume == 2:
            return sample // 2
        else:  # volume == 3
            return sample // 4

    def trigger(self):
        """Trigger the channel"""
        self.timer = 0
        self.counter = 0
        self.length_counter = 0
        self.enabled = True


class NoiseChannel:
    """Noise channel (CH4)"""

    def __init__(self):
        self.enabled = False
        self.volume = 0
        self.envelope_volume = 0
        self.envelope_steps = 0
        self.envelope_increase = False
        self.length = 0
        self.length_enable = False
        self.length_counter = 0
        self.lfsr = 0x7FFF
        self.width_7bit = False
        self.clock_shift = 0
        self.clock_divider = 0
        self.envelope_counter = 0
        self.envelope_volume_current = 0
        self.timer = 0
        self.timer_period = 0
        self.output_bit = 0

    def step(self, sample_rate: int) -> int:
        """Generate one sample."""
        if not self.enabled:
            return 0

        # Length counter
        if self.length_enable and self.length > 0:
            self.length_counter += 1
            if self.length_counter >= (256 - self.length):
                self.enabled = False
                return 0

        # Envelope
        if self.envelope_steps > 0:
            self.envelope_counter += 1
            if self.envelope_counter >= self.envelope_steps:
                self.envelope_counter = 0
                if self.envelope_increase:
                    self.envelope_volume_current = min(15, self.envelope_volume_current + 1)
                else:
                    self.envelope_volume_current = max(0, self.envelope_volume_current - 1)
                if self.envelope_volume_current == 0:
                    self.enabled = False
                    return 0
        else:
            self.envelope_volume_current = self.envelope_volume

        # Timer
        divisor = max(1, self.clock_divider)
        self.timer_period = (1 << self.clock_shift) * divisor
        if self.timer_period == 0:
            self.timer_period = 1

        self.timer += 1
        if self.timer >= self.timer_period:
            self.timer = 0

            # LFSR step
            if self.width_7bit:
                bit0 = self.lfsr & 1
                bit1 = (self.lfsr >> 1) & 1
                new_bit = bit0 ^ bit1
                self.lfsr = (self.lfsr >> 1) | (new_bit << 6)
                self.lfsr &= 0x7F
            else:
                bit0 = self.lfsr & 1
                bit14 = (self.lfsr >> 14) & 1
                new_bit = bit0 ^ bit14
                self.lfsr = (self.lfsr >> 1) | (new_bit << 14)

            self.output_bit = self.lfsr & 1

        return self.output_bit * self.envelope_volume_current

    def trigger(self):
        """Trigger the channel"""
        self.lfsr = 0x7FFF
        self.timer = 0
        self.output_bit = 0
        self.envelope_counter = 0
        self.envelope_volume_current = self.envelope_volume
        self.length_counter = 0
        self.enabled = True


class FIFO:
    """Direct Sound FIFO buffer"""

    def __init__(self):
        self.data = deque(maxlen=8)
        self.timer = 0
        self.timer_period = 1  # Will be set by DMA
        self.enabled = False
        self.volume_left = 0
        self.volume_right = 0

    def write(self, value: int):
        """Write a byte to FIFO"""
        self.data.append(value & 0xFF)

    def read(self) -> int:
        """Read a byte from FIFO"""
        if self.data:
            return self.data.popleft()
        return 128  # Silence

    def step(self, sample_rate: int) -> int:
        """Generate one sample from FIFO."""
        if not self.enabled:
            return 0

        self.timer += 1
        if self.timer >= self.timer_period and self.data:
            self.timer = 0
            return self.read()

        return 0


class APU:
    """GBA Audio Processing Unit"""

    SAMPLE_RATE = 44100

    def __init__(self):
        self.ch1 = SquareWaveChannel()
        self.ch2 = SquareWaveChannel()
        self.ch3 = WaveChannel()
        self.ch4 = NoiseChannel()
        self.fifo_a = FIFO()
        self.fifo_b = FIFO()
        self.wave_ram = [[0] * 32, [0] * 32]
        self.wave_bank = 0
        self.master_volume_left = 0
        self.master_volume_right = 0
        self.ch1_enabled = False
        self.ch2_enabled = False
        self.ch3_enabled = False
        self.ch4_enabled = False
        self.fifo_a_enabled = False
        self.fifo_b_enabled = False
        self._audio_output = None
        self._sound_buffer_a = None
        self._sound_buffer_b = None
        self._current_buffer = 'a'
        self._channel = None
        self._audio_channel = None  # Dedicated channel for continuous playback
        self._buffer_queue = deque(maxlen=4)  # Queue buffers for seamless playback

    def start(self):
        """Start audio playback"""
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=self.SAMPLE_RATE, size=-8, channels=2, buffer=512)

    def stop(self):
        """Stop audio playback"""
        try:
            pygame.mixer.stop()
        except pygame.error:
            pass

    def write_register(self, addr: int, value: int):
        """Handle MMIO writes to sound registers"""
        if addr == 0x04000060:
            self.ch1.sweep_shift = (value >> 4) & 0x07
            self.ch1.sweep_decrease = bool(value & 0x08)
            self.ch1.sweep_steps = value & 0x07
        elif addr == 0x04000062:
            self.ch1.duty_cycle = (value >> 6) & 0x03
            self.ch1.length = value & 0x3F
        elif addr == 0x04000064:
            self.ch1.frequency = value & 0x7FF
            self.ch1.envelope_volume = (value >> 12) & 0x0F
            self.ch1.envelope_steps = (value >> 8) & 0x07
            self.ch1.envelope_increase = bool(value & 0x0800)
            if value & 0x8000:
                self.ch1.trigger()
        elif addr == 0x04000068:
            self.ch2.duty_cycle = (value >> 6) & 0x03
            self.ch2.length = value & 0x3F
        elif addr == 0x0400006A:
            self.ch2.envelope_volume = (value >> 12) & 0x0F
            self.ch2.envelope_steps = (value >> 8) & 0x07
            self.ch2.envelope_increase = bool(value & 0x0800)
        elif addr == 0x0400006C:
            self.ch2.frequency = value & 0x7FF
            if value & 0x8000:
                self.ch2.trigger()
        elif addr == 0x04000070:
            self.ch3.wave_bank = (value >> 5) & 0x01
            self.wave_bank = self.ch3.wave_bank
            self.ch3.enabled = bool(value & 0x80)
        elif addr == 0x04000072:
            self.ch3.length = value & 0xFF
        elif addr == 0x04000074:
            volume_shift = (value >> 8) & 0x03
            self.ch3.volume = 0 if volume_shift == 0 else (1 if volume_shift == 1 else (2 if volume_shift == 2 else 3))
            self.ch3.format_8bit = bool(value & 0x0400)
            self.ch3.frequency = value & 0x3FF
            if value & 0x8000:
                self.ch3.trigger()
        elif addr == 0x04000078:
            self.ch4.length = value & 0x3F
        elif addr == 0x0400007A:
            self.ch4.envelope_volume = (value >> 12) & 0x0F
            self.ch4.envelope_steps = (value >> 8) & 0x07
            self.ch4.envelope_increase = bool(value & 0x0800)
        elif addr == 0x0400007C:
            self.ch4.clock_shift = (value >> 4) & 0x0F
            self.ch4.clock_divider = value & 0x07
            self.ch4.width_7bit = bool(value & 0x08)
            if value & 0x8000:
                self.ch4.trigger()
        elif addr == 0x04000080:
            self.master_volume_right = (value >> 4) & 0x07
            self.master_volume_left = value & 0x07
        elif addr == 0x04000082:
            self.fifo_a.volume_right = (value >> 4) & 0x0F
            self.fifo_a.volume_left = value & 0x0F
            self.fifo_a.enabled = bool(value & 0x0200)
            self.ch1_enabled = bool(value & 0x0001)
            self.ch2_enabled = bool(value & 0x0002)
        elif addr == 0x04000084:
            self.fifo_b.volume_right = (value >> 4) & 0x0F
            self.fifo_b.volume_left = value & 0x0F
            self.fifo_b.enabled = bool(value & 0x0200)
            self.ch3_enabled = bool(value & 0x0004)
            self.ch4_enabled = bool(value & 0x0008)
        elif 0x040000A0 <= addr <= 0x040000A3:
            self.fifo_a.write(value & 0xFF)
        elif 0x040000A4 <= addr <= 0x040000A7:
            self.fifo_b.write(value & 0xFF)
        elif 0x04000090 <= addr <= 0x040000AF:
            offset = addr - 0x04000090
            self.wave_ram[self.wave_bank][offset % 32] = value & 0xFF

    def get_sample(self) -> tuple:
        """Return mixed stereo sample (left, right)"""
        # Mix channels
        left = 0
        right = 0

        if self.ch1_enabled:
            sample = self.ch1.step(self.SAMPLE_RATE)
            left += sample * self.master_volume_left
            right += sample * self.master_volume_right

        if self.ch2_enabled:
            sample = self.ch2.step(self.SAMPLE_RATE)
            left += sample * self.master_volume_left
            right += sample * self.master_volume_right

        if self.ch3_enabled:
            sample = self.ch3.step(self.SAMPLE_RATE, self.wave_ram, self.wave_bank)
            left += sample * self.master_volume_left
            right += sample * self.master_volume_right

        if self.ch4_enabled:
            sample = self.ch4.step(self.SAMPLE_RATE)
            left += sample * self.master_volume_left
            right += sample * self.master_volume_right

        if self.fifo_a_enabled:
            sample = self.fifo_a.step(self.SAMPLE_RATE)
            left += sample * self.fifo_a.volume_left
            right += sample * self.fifo_a.volume_right

        if self.fifo_b_enabled:
            sample = self.fifo_b.step(self.SAMPLE_RATE)
            left += sample * self.fifo_b.volume_left
            right += sample * self.fifo_b.volume_right

        # Normalize to 0-255 range
        left = min(255, max(0, left // 7))
        right = min(255, max(0, right // 7))

        return (left, right)

    def update(self):
        if not pygame.mixer.get_init():
            return

        if not (self.ch1_enabled or self.ch2_enabled or
                self.ch3_enabled or self.ch4_enabled or
                self.fifo_a_enabled or self.fifo_b_enabled):
            return

        # Use dedicated FIFO channel (channel 1) for continuous playback
        # Channel 0 is reserved for regular audio channels
        if self._audio_channel is None:
            try:
                # Use channel 1 for FIFO to avoid conflict
                if pygame.mixer.get_num_channels() < 2:
                    pygame.mixer.set_num_channels(2)
                self._audio_channel = pygame.mixer.Channel(1)
                self._fifo_buffer_queue = deque(maxlen=8)
                self._fifo_initial_buffers_queued = False
            except pygame.error:
                return

        # Only process FIFO audio if either FIFO is enabled
        if not (self.fifo_a_enabled or self.fifo_b_enabled):
            return

        BUFFER_SIZE = 2048  # Larger buffer for smoother playback

        try:
            if not self._fifo_initial_buffers_queued:
                samples = array.array('B')
                for _ in range(BUFFER_SIZE):
                    left, right = self.get_sample()
                    samples.append(left)
                    samples.append(right)

                if len(samples) == 0:
                    return

                sound = pygame.mixer.Sound(buffer=samples.tobytes())
                self._audio_channel.play(sound)

                for _ in range(3):
                    samples = array.array('B')
                    for _ in range(BUFFER_SIZE):
                        left, right = self.get_sample()
                        samples.append(left)
                        samples.append(right)
                    if samples:
                        buf_sound = pygame.mixer.Sound(buffer=samples.tobytes())
                        self._audio_channel.queue(buf_sound)

                self._fifo_initial_buffers_queued = True

            else:
                if self._audio_channel.get_busy():
                    samples = array.array('B')
                    for _ in range(BUFFER_SIZE):
                        left, right = self.get_sample()
                        samples.append(left)
                        samples.append(right)

                    if samples:
                        sound = pygame.mixer.Sound(buffer=samples.tobytes())
                        self._audio_channel.queue(sound)
                else:
                    self._fifo_initial_buffers_queued = False

        except pygame.error:
            pass

# === End of Runtime ===

# === Runtime Loader ===
# Ensure runtime path is accessible to runtime modules
import sys
import os
from pathlib import Path
if __file__:
    # Try multiple strategies to find gba_runtime
    script_dir = Path(__file__).resolve().parent
    # Strategy 1: gba_runtime in same directory as script
    runtime_dir = script_dir / 'gba_runtime'
    if runtime_dir.exists():
        sys.path.insert(0, str(script_dir))
    else:
        # Strategy 2: check parent directories for gba_runtime
        for parent in [script_dir] + list(script_dir.parents):
            runtime_dir = parent / 'gba_runtime'
            if runtime_dir.exists():
                sys.path.insert(0, str(parent))
                break
    # Strategy 3: use environment variable if set
    gba_runtime_env = os.environ.get('GBA_RUNTIME_PATH')
    if gba_runtime_env and Path(gba_runtime_env).exists():
        sys.path.insert(0, gba_runtime_env)

# Initialize runtime objects
memory = Memory()
ppu_instance = PPU(memory)
apu_instance = APU()
# IRQ handler available via interrupts module
# Timer module available
# DMA module available
set_numba_enabled(True)


import pygame

registers[15] = 0x08000000

# Full ROM data
ROM_DATA = bytearray([

    0x2E, 0x00, 0x00, 0xEA, 0x24, 0xFF, 0xAE, 0x51, 0x69, 0x9A, 0xA2, 0x21, 0x3D, 0x84, 0x82, 0x0A, 
    0x84, 0xE4, 0x09, 0xAD, 0x11, 0x24, 0x8B, 0x98, 0xC0, 0x81, 0x7F, 0x21, 0xA3, 0x52, 0xBE, 0x19, 
    0x93, 0x09, 0xCE, 0x20, 0x10, 0x46, 0x4A, 0x4A, 0xF8, 0x27, 0x31, 0xEC, 0x58, 0xC7, 0xE8, 0x33, 
    0x82, 0xE3, 0xCE, 0xBF, 0x85, 0xF4, 0xDF, 0x94, 0xCE, 0x4B, 0x09, 0xC1, 0x94, 0x56, 0x8A, 0xC0, 
    0x13, 0x72, 0xA7, 0xFC, 0x9F, 0x84, 0x4D, 0x73, 0xA3, 0xCA, 0x9A, 0x61, 0x58, 0x97, 0xA3, 0x27, 
    0xFC, 0x03, 0x98, 0x76, 0x23, 0x1D, 0xC7, 0x61, 0x03, 0x04, 0xAE, 0x56, 0xBF, 0x38, 0x84, 0x00, 
    0x40, 0xA7, 0x0E, 0xFD, 0xFF, 0x52, 0xFE, 0x03, 0x6F, 0x95, 0x30, 0xF1, 0x97, 0xFB, 0xC0, 0x85, 
    0x60, 0xD6, 0x80, 0x25, 0xA9, 0x63, 0xBE, 0x03, 0x01, 0x4E, 0x38, 0xE2, 0xF9, 0xA2, 0x34, 0xFF, 
    0xBB, 0x3E, 0x03, 0x44, 0x78, 0x00, 0x90, 0xCB, 0x88, 0x11, 0x3A, 0x94, 0x65, 0xC0, 0x7C, 0x63, 
    0x87, 0xF0, 0x3C, 0xAF, 0xD6, 0x25, 0xE4, 0x8B, 0x38, 0x0A, 0xAC, 0x72, 0x21, 0xD4, 0xF8, 0x07, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x30, 0x31, 0x96, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF0, 0x00, 0x00, 
    0x06, 0x00, 0x00, 0xEA, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x01, 0x03, 0xA0, 0xE3, 0x08, 0x02, 0x80, 0xE5, 0x12, 0x00, 0xA0, 0xE3, 0x00, 0xF0, 0x29, 0xE1, 
    0xB8, 0xD0, 0x9F, 0xE5, 0x1F, 0x00, 0xA0, 0xE3, 0x00, 0xF0, 0x29, 0xE1, 0xB0, 0xD0, 0x9F, 0xE5, 
    0x01, 0x00, 0x8F, 0xE2, 0x10, 0xFF, 0x2F, 0xE1, 0x2B, 0x48, 0x40, 0x01, 0x0B, 0xD2, 0x78, 0x46, 
    0x40, 0x01, 0x0D, 0xD3, 0x02, 0x22, 0x12, 0x06, 0x28, 0x4B, 0x9B, 0x1A, 0x16, 0x1C, 0x91, 0x00, 
    0x00, 0xF0, 0x3C, 0xF8, 0x30, 0x47, 0x40, 0x21, 0x09, 0x03, 0xC8, 0x01, 0x00, 0xF0, 0x2B, 0xF8, 
    0x23, 0x48, 0x24, 0x49, 0x09, 0x1A, 0x00, 0xF0, 0x26, 0xF8, 0x23, 0x48, 0x23, 0x49, 0x09, 0x1A, 
    0x00, 0xF0, 0x21, 0xF8, 0x22, 0x49, 0x23, 0x4A, 0x23, 0x4C, 0x00, 0xF0, 0x26, 0xF8, 0x23, 0x49, 
    0x23, 0x4A, 0x24, 0x4C, 0x00, 0xF0, 0x21, 0xF8, 0x23, 0x4A, 0x24, 0x49, 0x53, 0x1A, 0x02, 0xD0, 
    0x23, 0x4A, 0x00, 0xF0, 0x1B, 0xF8, 0x23, 0x49, 0x23, 0x4A, 0x24, 0x4C, 0x00, 0xF0, 0x15, 0xF8, 
    0x23, 0x49, 0x24, 0x48, 0x08, 0x60, 0x24, 0x4B, 0x00, 0xF0, 0x0E, 0xF8, 0x00, 0x20, 0x00, 0x21, 
    0x22, 0x4B, 0x00, 0xF0, 0x09, 0xF8, 0x03, 0x22, 0x89, 0x18, 0x91, 0x43, 0x03, 0xD0, 0x00, 0x22, 
    0x04, 0xC0, 0x04, 0x39, 0xFC, 0xD1, 0x70, 0x47, 0x18, 0x47, 0xA3, 0x1A, 0x03, 0x20, 0x1B, 0x18, 
    0x83, 0x43, 0x03, 0xD0, 0x01, 0xC9, 0x01, 0xC2, 0x04, 0x3B, 0xFB, 0xD1, 0x70, 0x47, 0xC0, 0x46, 
    0xA0, 0x7F, 0x00, 0x03, 0x00, 0x7F, 0x00, 0x03, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x02, 
    0x00, 0x00, 0x00, 0x03, 0x20, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x02, 
    0x48, 0x05, 0x00, 0x08, 0x20, 0x00, 0x00, 0x03, 0x40, 0x03, 0x00, 0x03, 0x48, 0x05, 0x00, 0x08, 
    0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x03, 0x68, 0x08, 0x00, 0x08, 0x68, 0x08, 0x00, 0x08, 
    0x40, 0x03, 0x00, 0x03, 0x68, 0x08, 0x00, 0x08, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x02, 
    0x1C, 0x00, 0x00, 0x03, 0x00, 0x00, 0x04, 0x02, 0xE9, 0x04, 0x00, 0x08, 0x6C, 0x02, 0x00, 0x08, 
    0xF8, 0xB5, 0xC0, 0x46, 0xF8, 0xBC, 0x08, 0xBC, 0x9E, 0x46, 0x70, 0x47, 0x10, 0xB5, 0x07, 0x4C, 
    0x23, 0x78, 0x00, 0x2B, 0x07, 0xD1, 0x06, 0x4B, 0x00, 0x2B, 0x02, 0xD0, 0x05, 0x48, 0x00, 0xE0, 
    0x00, 0xBF, 0x01, 0x23, 0x23, 0x70, 0x10, 0xBC, 0x01, 0xBC, 0x00, 0x47, 0x00, 0x00, 0x00, 0x03, 
    0x00, 0x00, 0x00, 0x00, 0x44, 0x05, 0x00, 0x08, 0x05, 0x4B, 0x10, 0xB5, 0x00, 0x2B, 0x03, 0xD0, 
    0x04, 0x49, 0x05, 0x48, 0x00, 0xE0, 0x00, 0xBF, 0x10, 0xBC, 0x01, 0xBC, 0x00, 0x47, 0xC0, 0x46, 
    0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x03, 0x44, 0x05, 0x00, 0x08, 0x84, 0x10, 0x9F, 0xE5, 
    0x00, 0x10, 0x81, 0xE5, 0x22, 0x00, 0x00, 0xEB, 0x7C, 0x00, 0x9F, 0xE5, 0x6B, 0x00, 0x00, 0xEB, 
    0x6A, 0x00, 0x00, 0xEB, 0x69, 0x00, 0x00, 0xEB, 0x68, 0x00, 0x00, 0xEB, 0x67, 0x00, 0x00, 0xEB, 
    0x66, 0x00, 0x00, 0xEB, 0x65, 0x00, 0x00, 0xEB, 0x64, 0x00, 0x00, 0xEB, 0x63, 0x00, 0x00, 0xEB, 
    0x62, 0x00, 0x00, 0xEB, 0x61, 0x00, 0x00, 0xEB, 0x60, 0x00, 0x00, 0xEB, 0x5F, 0x00, 0x00, 0xEB, 
    0x5E, 0x00, 0x00, 0xEB, 0x5D, 0x00, 0x00, 0xEB, 0x5C, 0x00, 0x00, 0xEB, 0x5B, 0x00, 0x00, 0xEB, 
    0x5A, 0x00, 0x00, 0xEB, 0x59, 0x00, 0x00, 0xEB, 0x58, 0x00, 0x00, 0xEB, 0x2C, 0x00, 0x9F, 0xE5, 
    0x56, 0x00, 0x00, 0xEB, 0x55, 0x00, 0x00, 0xEB, 0x62, 0x00, 0xA0, 0xE3, 0x2B, 0x00, 0x00, 0xEB, 
    0x18, 0x00, 0x9F, 0xE5, 0x51, 0x00, 0x00, 0xEB, 0x50, 0x00, 0x00, 0xEB, 0x0D, 0x00, 0xA0, 0xE1, 
    0x59, 0x00, 0x00, 0xEB, 0xFE, 0xFF, 0xFF, 0xEA, 0x08, 0x02, 0x00, 0x04, 0x20, 0x00, 0x00, 0x03, 
    0x2E, 0x00, 0x00, 0x03, 0xFF, 0x00, 0x2D, 0xE9, 0x01, 0x03, 0xA0, 0xE3, 0x01, 0x1C, 0xA0, 0xE3, 
    0xB0, 0x10, 0xC0, 0xE1, 0x02, 0x1B, 0xA0, 0xE3, 0xB8, 0x10, 0xC0, 0xE1, 0x05, 0x04, 0xA0, 0xE3, 
    0x00, 0x10, 0xE0, 0xE3, 0xB2, 0x10, 0xC0, 0xE1, 0x06, 0x04, 0xA0, 0xE3, 0x03, 0x1C, 0xA0, 0xE3, 
    0xA8, 0x21, 0x9F, 0xE5, 0x01, 0x30, 0xD2, 0xE7, 0x04, 0x40, 0xA0, 0xE3, 0x00, 0x50, 0xA0, 0xE3, 
    0x05, 0x54, 0xA0, 0xE1, 0x80, 0x60, 0x03, 0xE2, 0xA6, 0x63, 0xA0, 0xE1, 0x83, 0x30, 0xA0, 0xE1, 
    0x06, 0x62, 0xA0, 0xE1, 0x80, 0x70, 0x03, 0xE2, 0xA7, 0x73, 0xA0, 0xE1, 0x83, 0x30, 0xA0, 0xE1, 
    0x07, 0x60, 0x86, 0xE1, 0x06, 0x50, 0x85, 0xE1, 0x01, 0x40, 0x54, 0xE2, 0xF3, 0xFF, 0xFF, 0x1A, 
    0x01, 0x51, 0x80, 0xE7, 0x01, 0x10, 0x51, 0xE2, 0xED, 0xFF, 0xFF, 0x1A, 0x02, 0x04, 0xA0, 0xE3, 
    0x00, 0x10, 0xC0, 0xE5, 0x01, 0x10, 0xC0, 0xE5, 0xFF, 0x00, 0xBD, 0xE8, 0x1E, 0xFF, 0x2F, 0xE1, 
    0x3F, 0x00, 0x2D, 0xE9, 0x02, 0x24, 0xA0, 0xE3, 0x00, 0x30, 0xD2, 0xE5, 0x01, 0x40, 0xD2, 0xE5, 
    0x3C, 0x11, 0x9F, 0xE5, 0x0A, 0x00, 0x50, 0xE3, 0x0A, 0x00, 0x00, 0x0A, 0x20, 0x00, 0x50, 0xE3, 
    0x1C, 0x00, 0x00, 0xBA, 0x7E, 0x00, 0x50, 0xE3, 0x1A, 0x00, 0x00, 0xCA, 0x20, 0x00, 0x40, 0xE2, 
    0x83, 0x50, 0xA0, 0xE1, 0x04, 0x53, 0x85, 0xE0, 0xB1, 0x00, 0x85, 0xE1, 0x01, 0x30, 0x83, 0xE2, 
    0x1E, 0x00, 0x53, 0xE3, 0x11, 0x00, 0x00, 0x1A, 0x00, 0x30, 0xA0, 0xE3, 0x01, 0x40, 0x84, 0xE2, 
    0x14, 0x00, 0x54, 0xE3, 0x0D, 0x00, 0x00, 0x1A, 0x40, 0x20, 0xA0, 0xE3, 0x05, 0x3C, 0x81, 0xE2, 
    0x01, 0x00, 0xA0, 0xE1, 0x02, 0x10, 0x81, 0xE0, 0x04, 0xE0, 0x2D, 0xE5, 0x28, 0x00, 0x00, 0xEB, 
    0x04, 0xE0, 0x9D, 0xE4, 0x02, 0x00, 0x80, 0xE0, 0x02, 0x10, 0x81, 0xE0, 0x03, 0x00, 0x50, 0xE1, 
    0xF8, 0xFF, 0xFF, 0x1A, 0x00, 0x30, 0xA0, 0xE3, 0x13, 0x40, 0xA0, 0xE3, 0x02, 0x24, 0xA0, 0xE3, 
    0x00, 0x30, 0xC2, 0xE5, 0x01, 0x40, 0xC2, 0xE5, 0x3F, 0x00, 0xBD, 0xE8, 0x1E, 0xFF, 0x2F, 0xE1, 
    0x03, 0x00, 0x2D, 0xE9, 0x00, 0x10, 0xA0, 0xE1, 0x01, 0x00, 0xD1, 0xE4, 0x00, 0x00, 0x50, 0xE3, 
    0x03, 0x00, 0x00, 0x0A, 0x04, 0xE0, 0x2D, 0xE5, 0xD0, 0xFF, 0xFF, 0xEB, 0x04, 0xE0, 0x9D, 0xE4, 
    0xF8, 0xFF, 0xFF, 0xEA, 0x03, 0x00, 0xBD, 0xE8, 0x1E, 0xFF, 0x2F, 0xE1, 0x07, 0x00, 0x2D, 0xE9, 
    0x00, 0x10, 0xA0, 0xE1, 0x08, 0x20, 0xA0, 0xE3, 0x0F, 0x02, 0x01, 0xE2, 0x20, 0x0E, 0xA0, 0xE1, 
    0x01, 0x12, 0xA0, 0xE1, 0x09, 0x00, 0x50, 0xE3, 0x01, 0x00, 0x00, 0xCA, 0x30, 0x00, 0x80, 0xE2, 
    0x00, 0x00, 0x00, 0xEA, 0x37, 0x00, 0x80, 0xE2, 0x04, 0xE0, 0x2D, 0xE5, 0xBF, 0xFF, 0xFF, 0xEB, 
    0x04, 0xE0, 0x9D, 0xE4, 0x01, 0x20, 0x52, 0xE2, 0xF2, 0xFF, 0xFF, 0x1A, 0x07, 0x00, 0xBD, 0xE8, 
    0x1E, 0xFF, 0x2F, 0xE1, 0x0C, 0x00, 0x2D, 0xE9, 0x01, 0x30, 0xE0, 0xE3, 0x03, 0x20, 0x02, 0xE0, 
    0xB2, 0x30, 0x91, 0xE1, 0xB2, 0x30, 0x80, 0xE1, 0x02, 0x20, 0x52, 0xE2, 0xFB, 0xFF, 0xFF, 0x1A, 
    0x0C, 0x00, 0xBD, 0xE8, 0x1E, 0xFF, 0x2F, 0xE1, 0x04, 0x20, 0x2D, 0xE5, 0x02, 0x10, 0xC0, 0xE7, 
    0x01, 0x20, 0x52, 0xE2, 0xFC, 0xFF, 0xFF, 0x1A, 0x04, 0x20, 0x9D, 0xE4, 0x1E, 0xFF, 0x2F, 0xE1, 
    0x38, 0x00, 0x00, 0x03, 0x00, 0x40, 0x00, 0x06, 0x70, 0xB5, 0x0E, 0x4D, 0x0E, 0x4E, 0x76, 0x1B, 
    0xB6, 0x10, 0x06, 0xD0, 0x00, 0x24, 0x08, 0xCD, 0x01, 0x34, 0x00, 0xF0, 0x1B, 0xF8, 0xA6, 0x42, 
    0xF9, 0xD1, 0xFF, 0xF7, 0x85, 0xFE, 0x09, 0x4D, 0x09, 0x4E, 0x76, 0x1B, 0xB6, 0x10, 0x06, 0xD0, 
    0x00, 0x24, 0x08, 0xCD, 0x01, 0x34, 0x00, 0xF0, 0x0D, 0xF8, 0xA6, 0x42, 0xF9, 0xD1, 0x70, 0xBC, 
    0x01, 0xBC, 0x00, 0x47, 0x38, 0x03, 0x00, 0x03, 0x38, 0x03, 0x00, 0x03, 0x38, 0x03, 0x00, 0x03, 
    0x3C, 0x03, 0x00, 0x03, 0x18, 0x47, 0xC0, 0x46, 0xF8, 0xB5, 0xC0, 0x46, 0xF8, 0xBC, 0x08, 0xBC, 
    0x9E, 0x46, 0x70, 0x47, 0x00, 0x00, 0x00, 0x00, 0x68, 0x65, 0x6C, 0x6C, 0x6F, 0x20, 0x77, 0x6F, 
    0x72, 0x6C, 0x64, 0x21, 0x0A, 0x00, 0x69, 0x74, 0x20, 0x77, 0x6F, 0x72, 0x6B, 0x73, 0x0A, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x18, 0x00, 
    0x36, 0x36, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x36, 0x36, 0x7F, 0x36, 0x7F, 0x36, 0x36, 0x00, 
    0x18, 0x7C, 0x06, 0x3C, 0x60, 0x3E, 0x18, 0x00, 0x00, 0x66, 0x35, 0x1B, 0x6C, 0x56, 0x33, 0x00, 
    0x1C, 0x36, 0x16, 0x6E, 0x3B, 0x73, 0xDE, 0x00, 0x18, 0x18, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x30, 0x18, 0x0C, 0x0C, 0x0C, 0x18, 0x30, 0x00, 0x0C, 0x18, 0x30, 0x30, 0x30, 0x18, 0x0C, 0x00, 
    0x00, 0x66, 0x3C, 0xFF, 0x3C, 0x66, 0x00, 0x00, 0x00, 0x18, 0x18, 0x7E, 0x18, 0x18, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x0C, 0x00, 0x00, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00, 0xC0, 0x60, 0x30, 0x18, 0x0C, 0x06, 0x03, 0x00, 
    0x3C, 0x66, 0x76, 0x7E, 0x6E, 0x66, 0x3C, 0x00, 0x18, 0x1C, 0x1E, 0x18, 0x18, 0x18, 0x18, 0x00, 
    0x3C, 0x66, 0x60, 0x30, 0x18, 0x0C, 0x7E, 0x00, 0x3C, 0x66, 0x60, 0x38, 0x60, 0x66, 0x3C, 0x00, 
    0x38, 0x3C, 0x36, 0x33, 0x7F, 0x30, 0x30, 0x00, 0x7E, 0x06, 0x3E, 0x60, 0x60, 0x66, 0x3C, 0x00, 
    0x38, 0x0C, 0x06, 0x3E, 0x66, 0x66, 0x3C, 0x00, 0x7E, 0x60, 0x60, 0x30, 0x18, 0x18, 0x18, 0x00, 
    0x3C, 0x66, 0x66, 0x3C, 0x66, 0x66, 0x3C, 0x00, 0x3C, 0x66, 0x66, 0x7C, 0x60, 0x30, 0x1C, 0x00, 
    0x00, 0x18, 0x18, 0x00, 0x00, 0x18, 0x18, 0x00, 0x00, 0x18, 0x18, 0x00, 0x00, 0x18, 0x18, 0x0C, 
    0x00, 0x60, 0x18, 0x06, 0x18, 0x60, 0x00, 0x00, 0x00, 0x00, 0x7E, 0x00, 0x7E, 0x00, 0x00, 0x00, 
    0x00, 0x06, 0x18, 0x60, 0x18, 0x06, 0x00, 0x00, 0x3C, 0x66, 0x60, 0x30, 0x18, 0x00, 0x18, 0x00, 
    0x3C, 0x66, 0x5A, 0x5A, 0x7A, 0x06, 0x3C, 0x00, 0x3C, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00, 
    0x3E, 0x66, 0x66, 0x3E, 0x66, 0x66, 0x3E, 0x00, 0x78, 0x0C, 0x06, 0x06, 0x06, 0x0C, 0x78, 0x00, 
    0x1E, 0x36, 0x66, 0x66, 0x66, 0x36, 0x1E, 0x00, 0x7E, 0x06, 0x06, 0x1E, 0x06, 0x06, 0x7E, 0x00, 
    0x7E, 0x06, 0x06, 0x1E, 0x06, 0x06, 0x06, 0x00, 0x3C, 0x66, 0x06, 0x76, 0x66, 0x66, 0x7C, 0x00, 
    0x66, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00, 0x3C, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00, 
    0x60, 0x60, 0x60, 0x60, 0x60, 0x66, 0x3C, 0x00, 0x63, 0x33, 0x1B, 0x0F, 0x1B, 0x33, 0x63, 0x00, 
    0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x7E, 0x00, 0x63, 0x77, 0x7F, 0x6B, 0x63, 0x63, 0x63, 0x00, 
    0x63, 0x67, 0x6F, 0x7B, 0x73, 0x63, 0x63, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00, 
    0x3E, 0x66, 0x66, 0x3E, 0x06, 0x06, 0x06, 0x00, 0x1E, 0x33, 0x33, 0x33, 0x33, 0x3B, 0x7E, 0x00, 
    0x3E, 0x66, 0x66, 0x3E, 0x36, 0x66, 0x66, 0x00, 0x3C, 0x66, 0x0E, 0x3C, 0x70, 0x66, 0x3C, 0x00, 
    0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00, 
    0x66, 0x66, 0x66, 0x66, 0x3C, 0x3C, 0x18, 0x00, 0x63, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x63, 0x00, 
    0xC3, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0xC3, 0x00, 0xC3, 0x66, 0x3C, 0x18, 0x18, 0x18, 0x18, 0x00, 
    0x7F, 0x30, 0x18, 0x0C, 0x06, 0x03, 0x7F, 0x00, 0x3C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x3C, 0x00, 
    0x03, 0x06, 0x0C, 0x18, 0x30, 0x60, 0xC0, 0x00, 0x3C, 0x30, 0x30, 0x30, 0x30, 0x30, 0x3C, 0x00, 
    0x18, 0x3C, 0x66, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3F, 0x00, 
    0x18, 0x18, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3C, 0x60, 0x7C, 0x66, 0x7C, 0x00, 
    0x06, 0x06, 0x3E, 0x66, 0x66, 0x66, 0x3E, 0x00, 0x00, 0x00, 0x3C, 0x06, 0x06, 0x06, 0x3C, 0x00, 
    0x60, 0x60, 0x7C, 0x66, 0x66, 0x66, 0x7C, 0x00, 0x00, 0x00, 0x3C, 0x66, 0x7E, 0x06, 0x3C, 0x00, 
    0x38, 0x0C, 0x3E, 0x0C, 0x0C, 0x0C, 0x0C, 0x00, 0x00, 0x00, 0x7C, 0x66, 0x66, 0x7C, 0x60, 0x3C, 
    0x06, 0x06, 0x3E, 0x66, 0x66, 0x66, 0x66, 0x00, 0x18, 0x00, 0x18, 0x18, 0x18, 0x18, 0x30, 0x00, 
    0x30, 0x00, 0x30, 0x30, 0x30, 0x30, 0x30, 0x1E, 0x06, 0x06, 0x66, 0x36, 0x1E, 0x36, 0x66, 0x00, 
    0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x30, 0x00, 0x00, 0x00, 0x37, 0x7F, 0x6B, 0x63, 0x63, 0x00, 
    0x00, 0x00, 0x3E, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x3C, 0x00, 
    0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x06, 0x00, 0x00, 0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60, 
    0x00, 0x00, 0x3E, 0x66, 0x06, 0x06, 0x06, 0x00, 0x00, 0x00, 0x3C, 0x06, 0x3C, 0x60, 0x3E, 0x00, 
    0x0C, 0x0C, 0x3E, 0x0C, 0x0C, 0x0C, 0x38, 0x00, 0x00, 0x00, 0x66, 0x66, 0x66, 0x66, 0x7C, 0x00, 
    0x00, 0x00, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00, 0x00, 0x00, 0x63, 0x63, 0x6B, 0x7F, 0x36, 0x00, 
    0x00, 0x00, 0x63, 0x36, 0x1C, 0x36, 0x63, 0x00, 0x00, 0x00, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x0C, 
    0x00, 0x00, 0x7E, 0x30, 0x18, 0x0C, 0x7E, 0x00, 0x30, 0x18, 0x18, 0x0C, 0x18, 0x18, 0x30, 0x00, 
    0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x0C, 0x18, 0x18, 0x30, 0x18, 0x18, 0x0C, 0x00, 
    0x00, 0x6E, 0x3B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x49, 0x02, 0x00, 0x08, 0x1D, 0x02, 0x00, 0x08, 0x64, 0x6B, 0x41, 0x52, 0x4D, 0x00, 0x00, 0x00
])

# Wave data for APU CH3
WAVE_DATA = bytearray([

])

# Tilemap data for backgrounds
bg0_tilemap = [
    0x0001,
    0xE28F,
    0xFF10,
    0xE12F,
    0x482B,
    0x0140,
    0xD20B,
    0x4678,
    0x0140,
    0xD30D,
    0x2202,
    0x0612,
    0x4B28,
    0x1A9B,
    0x1C16,
    0x0091,
    0xF000,
    0xF83C,
    0x4730,
    0x2140,
    0x0309,
    0x01C8,
    0xF000,
    0xF82B,
    0x4823,
    0x4924,
    0x1A09,
    0xF000,
    0xF826,
    0x4823,
    0x4923,
    0x1A09,
    0xF000,
    0xF821,
    0x4922,
    0x4A23,
    0x4C23,
    0xF000,
    0xF826,
    0x4923,
    0x4A23,
    0x4C24,
    0xF000,
    0xF821,
    0x4A23,
    0x4924,
    0x1A53,
    0xD002,
    0x4A23,
    0xF000,
    0xF81B,
    0x4923,
    0x4A23,
    0x4C24,
    0xF000,
    0xF815,
    0x4923,
    0x4824,
    0x6008,
    0x4B24,
    0xF000,
    0xF80E,
    0x2000,
    0x2100,
]

# Tile data for backgrounds
tile_data = bytearray([

    0x01, 0x00, 0x8F, 0xE2, 0x10, 0xFF, 0x2F, 0xE1, 0x2B, 0x48, 0x40, 0x01, 0x0B, 0xD2, 0x78, 0x46, 
    0x40, 0x01, 0x0D, 0xD3, 0x02, 0x22, 0x12, 0x06, 0x28, 0x4B, 0x9B, 0x1A, 0x16, 0x1C, 0x91, 0x00, 
    0x00, 0xF0, 0x3C, 0xF8, 0x30, 0x47, 0x40, 0x21, 0x09, 0x03, 0xC8, 0x01, 0x00, 0xF0, 0x2B, 0xF8, 
    0x23, 0x48, 0x24, 0x49, 0x09, 0x1A, 0x00, 0xF0, 0x26, 0xF8, 0x23, 0x48, 0x23, 0x49, 0x09, 0x1A, 
    0x00, 0xF0, 0x21, 0xF8, 0x22, 0x49, 0x23, 0x4A, 0x23, 0x4C, 0x00, 0xF0, 0x26, 0xF8, 0x23, 0x49, 
    0x23, 0x4A, 0x24, 0x4C, 0x00, 0xF0, 0x21, 0xF8, 0x23, 0x4A, 0x24, 0x49, 0x53, 0x1A, 0x02, 0xD0, 
    0x23, 0x4A, 0x00, 0xF0, 0x1B, 0xF8, 0x23, 0x49, 0x23, 0x4A, 0x24, 0x4C, 0x00, 0xF0, 0x15, 0xF8, 
    0x23, 0x49, 0x24, 0x48, 0x08, 0x60, 0x24, 0x4B, 0x00, 0xF0, 0x0E, 0xF8, 0x00, 0x20, 0x00, 0x21, 
    0x22, 0x4B, 0x00, 0xF0, 0x09, 0xF8, 0x03, 0x22, 0x89, 0x18, 0x91, 0x43, 0x03, 0xD0, 0x00, 0x22, 
    0x04, 0xC0, 0x04, 0x39, 0xFC, 0xD1, 0x70, 0x47, 0x18, 0x47, 0xA3, 0x1A, 0x03, 0x20, 0x1B, 0x18, 
    0x83, 0x43, 0x03, 0xD0, 0x01, 0xC9, 0x01, 0xC2, 0x04, 0x3B, 0xFB, 0xD1, 0x70, 0x47, 0xC0, 0x46, 
    0xA0, 0x7F, 0x00, 0x03, 0x00, 0x7F, 0x00, 0x03, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x02, 
    0x00, 0x00, 0x00, 0x03, 0x20, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x02, 
    0x48, 0x05, 0x00, 0x08, 0x20, 0x00, 0x00, 0x03, 0x40, 0x03, 0x00, 0x03, 0x48, 0x05, 0x00, 0x08, 
    0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x00, 0x03, 0x68, 0x08, 0x00, 0x08, 0x68, 0x08, 0x00, 0x08, 
    0x40, 0x03, 0x00, 0x03, 0x68, 0x08, 0x00, 0x08, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x02, 
    0x1C, 0x00, 0x00, 0x03, 0x00, 0x00, 0x04, 0x02, 0xE9, 0x04, 0x00, 0x08, 0x6C, 0x02, 0x00, 0x08, 
    0xF8, 0xB5, 0xC0, 0x46, 0xF8, 0xBC, 0x08, 0xBC, 0x9E, 0x46, 0x70, 0x47, 0x10, 0xB5, 0x07, 0x4C, 
    0x23, 0x78, 0x00, 0x2B, 0x07, 0xD1, 0x06, 0x4B, 0x00, 0x2B, 0x02, 0xD0, 0x05, 0x48, 0x00, 0xE0, 
    0x00, 0xBF, 0x01, 0x23, 0x23, 0x70, 0x10, 0xBC, 0x01, 0xBC, 0x00, 0x47, 0x00, 0x00, 0x00, 0x03, 
    0x00, 0x00, 0x00, 0x00, 0x44, 0x05, 0x00, 0x08, 0x05, 0x4B, 0x10, 0xB5, 0x00, 0x2B, 0x03, 0xD0, 
    0x04, 0x49, 0x05, 0x48, 0x00, 0xE0, 0x00, 0xBF, 0x10, 0xBC, 0x01, 0xBC, 0x00, 0x47, 0xC0, 0x46, 
    0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x03, 0x44, 0x05, 0x00, 0x08, 0x84, 0x10, 0x9F, 0xE5, 
    0x00, 0x10, 0x81, 0xE5, 0x22, 0x00, 0x00, 0xEB, 0x7C, 0x00, 0x9F, 0xE5, 0x6B, 0x00, 0x00, 0xEB, 
    0x6A, 0x00, 0x00, 0xEB, 0x69, 0x00, 0x00, 0xEB, 0x68, 0x00, 0x00, 0xEB, 0x67, 0x00, 0x00, 0xEB, 
    0x66, 0x00, 0x00, 0xEB, 0x65, 0x00, 0x00, 0xEB, 0x64, 0x00, 0x00, 0xEB, 0x63, 0x00, 0x00, 0xEB, 
    0x62, 0x00, 0x00, 0xEB, 0x61, 0x00, 0x00, 0xEB, 0x60, 0x00, 0x00, 0xEB, 0x5F, 0x00, 0x00, 0xEB, 
    0x5E, 0x00, 0x00, 0xEB, 0x5D, 0x00, 0x00, 0xEB, 0x5C, 0x00, 0x00, 0xEB, 0x5B, 0x00, 0x00, 0xEB, 
    0x5A, 0x00, 0x00, 0xEB, 0x59, 0x00, 0x00, 0xEB, 0x58, 0x00, 0x00, 0xEB, 0x2C, 0x00, 0x9F, 0xE5, 
    0x56, 0x00, 0x00, 0xEB, 0x55, 0x00, 0x00, 0xEB, 0x62, 0x00, 0xA0, 0xE3, 0x2B, 0x00, 0x00, 0xEB, 
    0x18, 0x00, 0x9F, 0xE5, 0x51, 0x00, 0x00, 0xEB, 0x50, 0x00, 0x00, 0xEB, 0x0D, 0x00, 0xA0, 0xE1, 
    0x59, 0x00, 0x00, 0xEB, 0xFE, 0xFF, 0xFF, 0xEA, 0x08, 0x02, 0x00, 0x04, 0x20, 0x00, 0x00, 0x03, 
    0x2E, 0x00, 0x00, 0x03, 0xFF, 0x00, 0x2D, 0xE9, 0x01, 0x03, 0xA0, 0xE3, 0x01, 0x1C, 0xA0, 0xE3, 
    0xB0, 0x10, 0xC0, 0xE1, 0x02, 0x1B, 0xA0, 0xE3, 0xB8, 0x10, 0xC0, 0xE1, 0x05, 0x04, 0xA0, 0xE3, 
    0x00, 0x10, 0xE0, 0xE3, 0xB2, 0x10, 0xC0, 0xE1, 0x06, 0x04, 0xA0, 0xE3, 0x03, 0x1C, 0xA0, 0xE3, 
    0xA8, 0x21, 0x9F, 0xE5, 0x01, 0x30, 0xD2, 0xE7, 0x04, 0x40, 0xA0, 0xE3, 0x00, 0x50, 0xA0, 0xE3, 
    0x05, 0x54, 0xA0, 0xE1, 0x80, 0x60, 0x03, 0xE2, 0xA6, 0x63, 0xA0, 0xE1, 0x83, 0x30, 0xA0, 0xE1, 
    0x06, 0x62, 0xA0, 0xE1, 0x80, 0x70, 0x03, 0xE2, 0xA7, 0x73, 0xA0, 0xE1, 0x83, 0x30, 0xA0, 0xE1, 
    0x07, 0x60, 0x86, 0xE1, 0x06, 0x50, 0x85, 0xE1, 0x01, 0x40, 0x54, 0xE2, 0xF3, 0xFF, 0xFF, 0x1A, 
    0x01, 0x51, 0x80, 0xE7, 0x01, 0x10, 0x51, 0xE2, 0xED, 0xFF, 0xFF, 0x1A, 0x02, 0x04, 0xA0, 0xE3, 
    0x00, 0x10, 0xC0, 0xE5, 0x01, 0x10, 0xC0, 0xE5, 0xFF, 0x00, 0xBD, 0xE8, 0x1E, 0xFF, 0x2F, 0xE1, 
    0x3F, 0x00, 0x2D, 0xE9, 0x02, 0x24, 0xA0, 0xE3, 0x00, 0x30, 0xD2, 0xE5, 0x01, 0x40, 0xD2, 0xE5, 
    0x3C, 0x11, 0x9F, 0xE5, 0x0A, 0x00, 0x50, 0xE3, 0x0A, 0x00, 0x00, 0x0A, 0x20, 0x00, 0x50, 0xE3, 
    0x1C, 0x00, 0x00, 0xBA, 0x7E, 0x00, 0x50, 0xE3, 0x1A, 0x00, 0x00, 0xCA, 0x20, 0x00, 0x40, 0xE2, 
    0x83, 0x50, 0xA0, 0xE1, 0x04, 0x53, 0x85, 0xE0, 0xB1, 0x00, 0x85, 0xE1, 0x01, 0x30, 0x83, 0xE2, 
    0x1E, 0x00, 0x53, 0xE3, 0x11, 0x00, 0x00, 0x1A, 0x00, 0x30, 0xA0, 0xE3, 0x01, 0x40, 0x84, 0xE2, 
    0x14, 0x00, 0x54, 0xE3, 0x0D, 0x00, 0x00, 0x1A, 0x40, 0x20, 0xA0, 0xE3, 0x05, 0x3C, 0x81, 0xE2, 
    0x01, 0x00, 0xA0, 0xE1, 0x02, 0x10, 0x81, 0xE0, 0x04, 0xE0, 0x2D, 0xE5, 0x28, 0x00, 0x00, 0xEB, 
    0x04, 0xE0, 0x9D, 0xE4, 0x02, 0x00, 0x80, 0xE0, 0x02, 0x10, 0x81, 0xE0, 0x03, 0x00, 0x50, 0xE1, 
    0xF8, 0xFF, 0xFF, 0x1A, 0x00, 0x30, 0xA0, 0xE3, 0x13, 0x40, 0xA0, 0xE3, 0x02, 0x24, 0xA0, 0xE3, 
    0x00, 0x30, 0xC2, 0xE5, 0x01, 0x40, 0xC2, 0xE5, 0x3F, 0x00, 0xBD, 0xE8, 0x1E, 0xFF, 0x2F, 0xE1, 
    0x03, 0x00, 0x2D, 0xE9, 0x00, 0x10, 0xA0, 0xE1, 0x01, 0x00, 0xD1, 0xE4, 0x00, 0x00, 0x50, 0xE3, 
    0x03, 0x00, 0x00, 0x0A, 0x04, 0xE0, 0x2D, 0xE5, 0xD0, 0xFF, 0xFF, 0xEB, 0x04, 0xE0, 0x9D, 0xE4, 
    0xF8, 0xFF, 0xFF, 0xEA, 0x03, 0x00, 0xBD, 0xE8, 0x1E, 0xFF, 0x2F, 0xE1, 0x07, 0x00, 0x2D, 0xE9, 
    0x00, 0x10, 0xA0, 0xE1, 0x08, 0x20, 0xA0, 0xE3, 0x0F, 0x02, 0x01, 0xE2, 0x20, 0x0E, 0xA0, 0xE1, 
    0x01, 0x12, 0xA0, 0xE1, 0x09, 0x00, 0x50, 0xE3, 0x01, 0x00, 0x00, 0xCA, 0x30, 0x00, 0x80, 0xE2, 
    0x00, 0x00, 0x00, 0xEA, 0x37, 0x00, 0x80, 0xE2, 0x04, 0xE0, 0x2D, 0xE5, 0xBF, 0xFF, 0xFF, 0xEB, 
    0x04, 0xE0, 0x9D, 0xE4, 0x01, 0x20, 0x52, 0xE2, 0xF2, 0xFF, 0xFF, 0x1A, 0x07, 0x00, 0xBD, 0xE8, 
    0x1E, 0xFF, 0x2F, 0xE1, 0x0C, 0x00, 0x2D, 0xE9, 0x01, 0x30, 0xE0, 0xE3, 0x03, 0x20, 0x02, 0xE0, 
    0xB2, 0x30, 0x91, 0xE1, 0xB2, 0x30, 0x80, 0xE1, 0x02, 0x20, 0x52, 0xE2, 0xFB, 0xFF, 0xFF, 0x1A, 
    0x0C, 0x00, 0xBD, 0xE8, 0x1E, 0xFF, 0x2F, 0xE1, 0x04, 0x20, 0x2D, 0xE5, 0x02, 0x10, 0xC0, 0xE7, 
    0x01, 0x20, 0x52, 0xE2, 0xFC, 0xFF, 0xFF, 0x1A, 0x04, 0x20, 0x9D, 0xE4, 0x1E, 0xFF, 0x2F, 0xE1, 
    0x38, 0x00, 0x00, 0x03, 0x00, 0x40, 0x00, 0x06, 0x70, 0xB5, 0x0E, 0x4D, 0x0E, 0x4E, 0x76, 0x1B, 
    0xB6, 0x10, 0x06, 0xD0, 0x00, 0x24, 0x08, 0xCD, 0x01, 0x34, 0x00, 0xF0, 0x1B, 0xF8, 0xA6, 0x42, 
    0xF9, 0xD1, 0xFF, 0xF7, 0x85, 0xFE, 0x09, 0x4D, 0x09, 0x4E, 0x76, 0x1B, 0xB6, 0x10, 0x06, 0xD0, 
    0x00, 0x24, 0x08, 0xCD, 0x01, 0x34, 0x00, 0xF0, 0x0D, 0xF8, 0xA6, 0x42, 0xF9, 0xD1, 0x70, 0xBC, 
    0x01, 0xBC, 0x00, 0x47, 0x38, 0x03, 0x00, 0x03, 0x38, 0x03, 0x00, 0x03, 0x38, 0x03, 0x00, 0x03, 
    0x3C, 0x03, 0x00, 0x03, 0x18, 0x47, 0xC0, 0x46, 0xF8, 0xB5, 0xC0, 0x46, 0xF8, 0xBC, 0x08, 0xBC, 
    0x9E, 0x46, 0x70, 0x47, 0x00, 0x00, 0x00, 0x00, 0x68, 0x65, 0x6C, 0x6C, 0x6F, 0x20, 0x77, 0x6F, 
    0x72, 0x6C, 0x64, 0x21, 0x0A, 0x00, 0x69, 0x74, 0x20, 0x77, 0x6F, 0x72, 0x6B, 0x73, 0x0A, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x18, 0x00, 
    0x36, 0x36, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x36, 0x36, 0x7F, 0x36, 0x7F, 0x36, 0x36, 0x00, 
    0x18, 0x7C, 0x06, 0x3C, 0x60, 0x3E, 0x18, 0x00, 0x00, 0x66, 0x35, 0x1B, 0x6C, 0x56, 0x33, 0x00, 
    0x1C, 0x36, 0x16, 0x6E, 0x3B, 0x73, 0xDE, 0x00, 0x18, 0x18, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x30, 0x18, 0x0C, 0x0C, 0x0C, 0x18, 0x30, 0x00, 0x0C, 0x18, 0x30, 0x30, 0x30, 0x18, 0x0C, 0x00, 
    0x00, 0x66, 0x3C, 0xFF, 0x3C, 0x66, 0x00, 0x00, 0x00, 0x18, 0x18, 0x7E, 0x18, 0x18, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x0C, 0x00, 0x00, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00, 0xC0, 0x60, 0x30, 0x18, 0x0C, 0x06, 0x03, 0x00, 
    0x3C, 0x66, 0x76, 0x7E, 0x6E, 0x66, 0x3C, 0x00, 0x18, 0x1C, 0x1E, 0x18, 0x18, 0x18, 0x18, 0x00, 
    0x3C, 0x66, 0x60, 0x30, 0x18, 0x0C, 0x7E, 0x00, 0x3C, 0x66, 0x60, 0x38, 0x60, 0x66, 0x3C, 0x00, 
    0x38, 0x3C, 0x36, 0x33, 0x7F, 0x30, 0x30, 0x00, 0x7E, 0x06, 0x3E, 0x60, 0x60, 0x66, 0x3C, 0x00, 
    0x38, 0x0C, 0x06, 0x3E, 0x66, 0x66, 0x3C, 0x00, 0x7E, 0x60, 0x60, 0x30, 0x18, 0x18, 0x18, 0x00, 
    0x3C, 0x66, 0x66, 0x3C, 0x66, 0x66, 0x3C, 0x00, 0x3C, 0x66, 0x66, 0x7C, 0x60, 0x30, 0x1C, 0x00, 
    0x00, 0x18, 0x18, 0x00, 0x00, 0x18, 0x18, 0x00, 0x00, 0x18, 0x18, 0x00, 0x00, 0x18, 0x18, 0x0C, 
    0x00, 0x60, 0x18, 0x06, 0x18, 0x60, 0x00, 0x00, 0x00, 0x00, 0x7E, 0x00, 0x7E, 0x00, 0x00, 0x00, 
    0x00, 0x06, 0x18, 0x60, 0x18, 0x06, 0x00, 0x00, 0x3C, 0x66, 0x60, 0x30, 0x18, 0x00, 0x18, 0x00, 
    0x3C, 0x66, 0x5A, 0x5A, 0x7A, 0x06, 0x3C, 0x00, 0x3C, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00, 
    0x3E, 0x66, 0x66, 0x3E, 0x66, 0x66, 0x3E, 0x00, 0x78, 0x0C, 0x06, 0x06, 0x06, 0x0C, 0x78, 0x00, 
    0x1E, 0x36, 0x66, 0x66, 0x66, 0x36, 0x1E, 0x00, 0x7E, 0x06, 0x06, 0x1E, 0x06, 0x06, 0x7E, 0x00, 
    0x7E, 0x06, 0x06, 0x1E, 0x06, 0x06, 0x06, 0x00, 0x3C, 0x66, 0x06, 0x76, 0x66, 0x66, 0x7C, 0x00, 
    0x66, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00, 0x3C, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00, 
    0x60, 0x60, 0x60, 0x60, 0x60, 0x66, 0x3C, 0x00, 0x63, 0x33, 0x1B, 0x0F, 0x1B, 0x33, 0x63, 0x00, 
    0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x7E, 0x00, 0x63, 0x77, 0x7F, 0x6B, 0x63, 0x63, 0x63, 0x00, 
    0x63, 0x67, 0x6F, 0x7B, 0x73, 0x63, 0x63, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00, 
    0x3E, 0x66, 0x66, 0x3E, 0x06, 0x06, 0x06, 0x00, 0x1E, 0x33, 0x33, 0x33, 0x33, 0x3B, 0x7E, 0x00, 
    0x3E, 0x66, 0x66, 0x3E, 0x36, 0x66, 0x66, 0x00, 0x3C, 0x66, 0x0E, 0x3C, 0x70, 0x66, 0x3C, 0x00, 
    0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00, 
    0x66, 0x66, 0x66, 0x66, 0x3C, 0x3C, 0x18, 0x00, 0x63, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x63, 0x00, 
    0xC3, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0xC3, 0x00, 0xC3, 0x66, 0x3C, 0x18, 0x18, 0x18, 0x18, 0x00, 
    0x7F, 0x30, 0x18, 0x0C, 0x06, 0x03, 0x7F, 0x00, 0x3C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x3C, 0x00, 
    0x03, 0x06, 0x0C, 0x18, 0x30, 0x60, 0xC0, 0x00, 0x3C, 0x30, 0x30, 0x30, 0x30, 0x30, 0x3C, 0x00, 
    0x18, 0x3C, 0x66, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3F, 0x00, 
    0x18, 0x18, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3C, 0x60, 0x7C, 0x66, 0x7C, 0x00, 
    0x06, 0x06, 0x3E, 0x66, 0x66, 0x66, 0x3E, 0x00, 0x00, 0x00, 0x3C, 0x06, 0x06, 0x06, 0x3C, 0x00, 
    0x60, 0x60, 0x7C, 0x66, 0x66, 0x66, 0x7C, 0x00, 0x00, 0x00, 0x3C, 0x66, 0x7E, 0x06, 0x3C, 0x00, 
    0x38, 0x0C, 0x3E, 0x0C, 0x0C, 0x0C, 0x0C, 0x00, 0x00, 0x00, 0x7C, 0x66, 0x66, 0x7C, 0x60, 0x3C, 
    0x06, 0x06, 0x3E, 0x66, 0x66, 0x66, 0x66, 0x00, 0x18, 0x00, 0x18, 0x18, 0x18, 0x18, 0x30, 0x00, 
    0x30, 0x00, 0x30, 0x30, 0x30, 0x30, 0x30, 0x1E, 0x06, 0x06, 0x66, 0x36, 0x1E, 0x36, 0x66, 0x00, 
    0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x30, 0x00, 0x00, 0x00, 0x37, 0x7F, 0x6B, 0x63, 0x63, 0x00, 
    0x00, 0x00, 0x3E, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x3C, 0x00, 
    0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x06, 0x00, 0x00, 0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60, 
    0x00, 0x00, 0x3E, 0x66, 0x06, 0x06, 0x06, 0x00, 0x00, 0x00, 0x3C, 0x06, 0x3C, 0x60, 0x3E, 0x00, 
    0x0C, 0x0C, 0x3E, 0x0C, 0x0C, 0x0C, 0x38, 0x00, 0x00, 0x00, 0x66, 0x66, 0x66, 0x66, 0x7C, 0x00, 
    0x00, 0x00, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00, 0x00, 0x00, 0x63, 0x63, 0x6B, 0x7F, 0x36, 0x00, 
    0x00, 0x00, 0x63, 0x36, 0x1C, 0x36, 0x63, 0x00, 0x00, 0x00, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x0C, 
    0x00, 0x00, 0x7E, 0x30, 0x18, 0x0C, 0x7E, 0x00, 0x30, 0x18, 0x18, 0x0C, 0x18, 0x18, 0x30, 0x00, 
    0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x0C, 0x18, 0x18, 0x30, 0x18, 0x18, 0x0C, 0x00, 
    0x00, 0x6E, 0x3B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
])

# Palette data for backgrounds and sprites
palette_data = [
    0x0018,
    0x6363,
    0x6B63,
    0x777F,
    0x0063,
    0x66C3,
    0x183C,
    0x663C,
    0x00C3,
    0x66C3,
    0x183C,
    0x1818,
    0x0018,
    0x307F,
    0x0C18,
    0x0306,
    0x007F,
    0x0C3C,
    0x0C0C,
    0x0C0C,
    0x003C,
    0x0603,
    0x180C,
    0x6030,
    0x00C0,
    0x303C,
    0x3030,
    0x3030,
    0x003C,
    0x3C18,
    0x0066,
    0x0000,
    0x0000,
    0x0000,
    0x0000,
    0x0000,
    0x003F,
    0x1818,
    0x0030,
    0x0000,
    0x0000,
    0x0000,
    0x603C,
    0x667C,
    0x007C,
    0x0606,
    0x663E,
    0x6666,
    0x003E,
    0x0000,
    0x063C,
    0x0606,
    0x003C,
    0x6060,
    0x667C,
    0x6666,
    0x007C,
    0x0000,
    0x663C,
    0x067E,
    0x003C,
    0x0C38,
    0x0C3E,
    0x0C0C,
    0x000C,
    0x0000,
    0x667C,
    0x7C66,
    0x3C60,
    0x0606,
    0x663E,
    0x6666,
    0x0066,
    0x0018,
    0x1818,
    0x1818,
    0x0030,
    0x0030,
    0x3030,
    0x3030,
    0x1E30,
    0x0606,
    0x3666,
    0x361E,
    0x0066,
    0x1818,
    0x1818,
    0x1818,
    0x0030,
    0x0000,
    0x7F37,
    0x636B,
    0x0063,
    0x0000,
    0x663E,
    0x6666,
    0x0066,
    0x0000,
    0x663C,
    0x6666,
    0x003C,
    0x0000,
    0x663E,
    0x3E66,
    0x0606,
    0x0000,
    0x667C,
    0x7C66,
    0x6060,
    0x0000,
    0x663E,
    0x0606,
    0x0006,
    0x0000,
    0x063C,
    0x603C,
    0x003E,
    0x0C0C,
    0x0C3E,
    0x0C0C,
    0x0038,
    0x0000,
    0x6666,
    0x6666,
    0x007C,
    0x0000,
    0x6666,
    0x3C66,
    0x0018,
    0x0000,
    0x6363,
    0x7F6B,
    0x0036,
    0x0000,
    0x3663,
    0x361C,
    0x0063,
    0x0000,
    0x6666,
    0x3C66,
    0x0C18,
    0x0000,
    0x307E,
    0x0C18,
    0x007E,
    0x1830,
    0x0C18,
    0x1818,
    0x0030,
    0x1818,
    0x1818,
    0x1818,
    0x0018,
    0x180C,
    0x3018,
    0x1818,
    0x000C,
    0x6E00,
    0x003B,
    0x0000,
    0x0000,
    0x0000,
    0x0000,
    0x0000,
    0x0000,
    0x0249,
    0x0800,
    0x021D,
    0x0800,
    0x6B64,
    0x5241,
    0x004D,
    0x0000,
]

# Sample metadata: (start_addr, length, format)
SAMPLES = [
]

if bg0_tilemap:
    for i, v in enumerate(bg0_tilemap[:1024]):
        if i * 2 < len(memory.vram):
            memory.vram[i * 2] = v & 0xFF
            memory.vram[i * 2 + 1] = (v >> 8) & 0xFF
        if 0x8000 + i * 2 < len(memory.vram):
            memory.vram[0x8000 + i * 2] = v & 0xFF
            memory.vram[0x8000 + i * 2 + 1] = (v >> 8) & 0xFF
    ppu_instance.bg0_tilemap = bg0_tilemap[:1024]
if tile_data:
    for i, b in enumerate(tile_data):
        if 0x4000 + i < len(memory.vram):
            memory.vram[0x4000 + i] = b
        if 0x6000 + i < len(memory.vram):
            memory.vram[0x6000 + i] = b
        if 0x10000 + i < len(memory.vram):
            memory.vram[0x10000 + i] = b
    ppu_instance.tiles_4bpp = list(tile_data)
if palette_data:
    for i, c in enumerate(palette_data[:256]):
        if i * 2 < len(memory.palette):
            memory.palette[i * 2] = c & 0xFF
            memory.palette[i * 2 + 1] = (c >> 8) & 0xFF
    ppu_instance.palette_bg = [((c & 0x1F) * 8, ((c >> 5) & 0x1F) * 8, ((c >> 10) & 0x1F) * 8) for c in palette_data]

# Sample playback helper
def play_sample(addr):
    """Play audio sample starting at given address in ROM_DATA
    Args: addr - address in ROM_DATA where sample starts
    """
    if not SAMPLES: return
    for sample_addr, length, fmt in SAMPLES:
        if sample_addr == addr:
            # Extract sample data from ROM
            sample_bytes = ROM_DATA[sample_addr:sample_addr + length]
            # Convert 4-bit samples to 8-bit audio
            if fmt == 0:  # 4-bit format
                audio = bytearray()
                for i in range(0, length, 2):
                    if i + 1 < length:
                        lo, hi = sample_bytes[i], sample_bytes[i+1]
                        combined = (lo & 0x0F) | ((hi & 0x0F) << 4)
                        audio.extend([combined, combined >> 4])
            else:  # 8-bit format
                audio = sample_bytes
            # Generate audio stream (repeat sample)
            sample_rate = 32768
            duration = 0.1
            num_samples = int(sample_rate * duration)
            if audio:
                repeat_len = num_samples // len(audio)
                audio_stream = bytearray()
                for _ in range(repeat_len):
                    audio_stream.extend(audio)
                import array
                # Convert to signed 16-bit stereo
                samples = array.array('h')
                for b in audio_stream:
                    samples.append(int((b - 128) / 127.0 * 32767))
                    samples.append(int((b - 128) / 127.0 * 32767))
                # Play via pygame
                import pygame
                try:
                    sound = pygame.mixer.Sound(buffer=samples)
                    channel = pygame.mixer.Channel(2)
                    channel.play(sound)
                except:
                    pass
            break

# GBA Memory Map Implementation
# Memory layout:
# - 0x00000000-0x00003FFF: BIOS ROM (16KB)
# - 0x02000000-0x0203FFFF: EWRAM (256KB)
# - 0x03000000-0x03007FFF: IWRAM (32KB)
# - 0x04000000-0x040003FF: MMIO registers
# - 0x05000000-0x050003FF: Palette RAM (1KB)
# - 0x06000000-0x06017FFF: VRAM (96KB)
# - 0x07000000-0x070003FF: OAM (1KB)
# - 0x08000000-0x09FFFFFF: ROM (up to 32MB)

class GBA:
    def __init__(self, rom_data):
        self.bios = bytearray(0x4000)       # 16KB
        self.ewram = bytearray(0x40000)     # 256KB
        self.iwram = bytearray(0x8000)      # 32KB
        self.mmio = {}                      # MMIO registers
        self.palette = bytearray(0x400)     # 1KB
        self.vram = bytearray(0x18000)      # 96KB
        self.oam = bytearray(0x400)         # 1KB
        self.rom = rom_data                 # up to 32MB

    def read_8(self, addr):
        if 0x00000000 <= addr <= 0x00003FFF:
            offset = addr - 0x00000000
            return self.bios[offset] if offset < len(self.bios) else 0
        elif 0x02000000 <= addr <= 0x0203FFFF:
            offset = addr - 0x02000000
            return self.ewram[offset] if offset < len(self.ewram) else 0
        elif 0x03000000 <= addr <= 0x03007FFF:
            offset = addr - 0x03000000
            return self.iwram[offset] if offset < len(self.iwram) else 0
        elif 0x04000000 <= addr <= 0x040003FF:
            offset = addr - 0x04000000
            return self.mmio.get(offset, 0)
        elif 0x05000000 <= addr <= 0x050003FF:
            offset = addr - 0x05000000
            return self.palette[offset] if offset < len(self.palette) else 0
        elif 0x06000000 <= addr <= 0x06017FFF:
            offset = addr - 0x06000000
            return self.vram[offset] if offset < len(self.vram) else 0
        elif 0x07000000 <= addr <= 0x070003FF:
            offset = addr - 0x07000000
            return self.oam[offset] if offset < len(self.oam) else 0
        elif 0x08000000 <= addr <= 0x09FFFFFF:
            offset = addr - 0x08000000
            return self.rom[offset] if offset < len(self.rom) else 0
        return 0

    def read_32(self, addr):
        b0 = self.read_8(addr)
        b1 = self.read_8(addr + 1)
        b2 = self.read_8(addr + 2)
        b3 = self.read_8(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)

    def write_8(self, addr, value):
        # Handle MMIO DMA control writes (detect FIFO C mode for DMA3)
        if 0x040000EC <= addr <= 0x040000EC:
            # DMA3 control register - check for FIFO C mode
            offset = addr - 0x04000000
            dma3_control = self.mmio.get(offset, 0)
            if dma3_control & 0x05000000:  # FIFO C trigger (bit 16)
                # Trigger FIFO C transfer for DMA3
                pass  # Handler in dma.py processes this
        
        if 0x02000000 <= addr <= 0x0203FFFF:
            offset = addr - 0x02000000
            if offset < len(self.ewram): self.ewram[offset] = value
        elif 0x03000000 <= addr <= 0x03007FFF:
            offset = addr - 0x03000000
            if offset < len(self.iwram): self.iwram[offset] = value
        elif 0x04000000 <= addr <= 0x040003FF:
            offset = addr - 0x04000000
            self.mmio[offset] = value  # MMIO side effects would be handled here
        elif 0x05000000 <= addr <= 0x050003FF:
            offset = addr - 0x05000000
            if offset < len(self.palette): self.palette[offset] = value
        elif 0x06000000 <= addr <= 0x06017FFF:
            offset = addr - 0x06000000
            if offset < len(self.vram): self.vram[offset] = value
        elif 0x07000000 <= addr <= 0x070003FF:
            offset = addr - 0x07000000
            if offset < len(self.oam): self.oam[offset] = value

    def write_32(self, addr, value):
        self.write_8(addr, value & 0xFF)
        self.write_8(addr + 1, (value >> 8) & 0xFF)
        self.write_8(addr + 2, (value >> 16) & 0xFF)
        self.write_8(addr + 3, (value >> 24) & 0xFF)

vram = memory.vram
palette_ram = memory.palette
oam = memory.oam
ewram = memory.ewram


def func_08000458(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return registers[14]

def func_0800037C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[0] = 33554432
    memory.write_u8(registers[0] + 0, registers[1] & 0xFF)
    memory.write_u8(registers[0] + 1, registers[1] & 0xFF)
    registers[0] = memory.read_u16(registers[13] + 15) & 0xFFFF
    registers[15] = 0x0800038C

def func_08000280(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080002F0(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x08000458

def func_0800033C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[5] = 0
    memory.write_u16(registers[0] + 1344, registers[5] & 0xFFFF)
    # AND unimplemented
    memory.write_u16(registers[0] + 1594, registers[6] & 0xFFFF)
    memory.write_u16(registers[0] + 776, registers[3] & 0xFFFF)
    memory.write_u16(registers[0] + 1568, registers[6] & 0xFFFF)
    # AND unimplemented
    memory.write_u16(registers[0] + 1850, registers[7] & 0xFFFF)
    memory.write_u16(registers[0] + 776, registers[3] & 0xFFFF)
    registers[6] = (registers[6] | registers[7]) & 0xFFFFFFFF
    registers[5] = (registers[5] | registers[6]) & 0xFFFFFFFF
    # SUB unimplemented
    registers[15] = 0x0800036C
    return 0x0800033C

def func_08000224(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x081B4644

def func_0800049C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[0] = memory.read_u32(registers[13] + 7)
    registers[15] = 0x080004A0

def func_080002E8(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_08000278(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[0] = memory.read_u16(registers[15] + 124) & 0xFFFF
    registers[15] = 0x0800027C
    return 0x0800042C

def func_08000140(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u32(registers[1] + 0, registers[15])
    registers[15] = 0x08000144
    return 0x088D25D0

def func_080002C8(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_0800050C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # ANDle unimplemented
    # COPROCESSORgt unimplemented
    registers[3] = (registers[0] & registers[1]) & 0xFFFFFFFF
    registers[15] = 0x08000518
    # ADCmi unimplemented
    # COPROCESSORlt unimplemented
    # STRmi unimplemented
    # TSTeq unimplemented
    # TSTeq unimplemented
    # TSTeq unimplemented
    # TSTeq unimplemented
    # STRBmi unimplemented
    # STRHmi unimplemented
    # COPROCESSORlt unimplemented
    # LDRBmi unimplemented
    # ANDeq unimplemented
    # COPROCESSORvs unimplemented
    # SWIvs unimplemented
    # CMNcs unimplemented
    # STRBvc unimplemented
    # RSBvc unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # LDRne unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    registers[15] = 0x08000578
    # LDRHcc unimplemented
    registers[15] = 0x0800057C
    # EOReq unimplemented
    # COPROCESSORcc unimplemented
    # ANDeq unimplemented
    registers[15] = 0x08000588
    return 0x08D59D8C

def func_08000148(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[4] = (registers[0] & registers[3]) & 0xFFFFFFFF
    registers[15] = 0x0800014C
    # STRmi unimplemented
    # COPROCESSORmi unimplemented
    registers[15] = 0x08000154
    memory.write_u32(registers[1] + 0, registers[15])
    # STRmi unimplemented
    # ANDle unimplemented
    registers[4] = (registers[0] & registers[3]) & 0xFFFFFFFF
    registers[15] = 0x08000164
    # STRmi unimplemented
    # COPROCESSORmi unimplemented
    registers[15] = 0x0800016C
    registers[15] = memory.read_u32(registers[5] + 0)
    # STRmi unimplemented
    registers[15] = 0x08000174
    return 0x08918198

def func_080003F4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[1] = (registers[2])
    memory.write_u32(registers[13] - 4, registers[14])
    registers[15] = 0x080003FC
    return 0x080004A0

def func_08000284(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080003E8(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[2] = 64
    # ADD unimplemented
    memory.write_u16(registers[0] + 0, registers[0] & 0xFFFF)
    registers[15] = 0x080003F4

def func_080004D8(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[2] = memory.read_u32(registers[13] + 4)
    registers[15] = 0x080004DC
    return registers[14]

def func_080000BC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # ANDeq unimplemented
    registers[15] = 0x080000C0
    return 0x080000DC

def func_08000430(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u32(registers[13] - 3, registers[0])
    registers[15] = 0x08000434

def func_08000000(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x080000BC

def func_080002BC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_0800038C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return registers[14]

def func_080004C0(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[0] = memory.read_u32(registers[13] + 12)
    registers[15] = 0x080004C4
    return registers[14]

def func_080004E0(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # TSTeq unimplemented
    # STReq unimplemented
    # COPROCESSORmi unimplemented
    registers[15] = 0x080004EC
    return 0x09D93D28

def func_080002B4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_08000288(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080002D4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080002A8(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080004A0(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return registers[14]

def func_08000178(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u32(registers[14] + 0, registers[15])
    # TSTcs unimplemented
    registers[4] = (registers[0] & registers[2]) & 0xFFFFFFFF
    registers[15] = 0x08000184
    # ANDcs unimplemented
    # ORRmi unimplemented
    # ANDcs unimplemented
    # STRcc unimplemented
    # LDRHmi unimplemented
    registers[15] = 0x08000198
    # Invalid branch target: 0x068D1DFC

def func_08000010(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # COPROCESSORge unimplemented
    # STRls unimplemented
    registers[15] = 0x08000018
    # CMNcs unimplemented
    # LDRne unimplemented
    # UMULLcs unimplemented
    registers[15] = 0x08000024
    return 0x09291868

def func_080002C0(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080002B8(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_08000370(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u32(registers[0] + 0, registers[5])
    # SUB unimplemented
    registers[15] = 0x08000378
    return 0x08000330

def func_08000294(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080004C8(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u32(registers[13] - 4, registers[2])
    memory.write_u8(registers[0] + 0, registers[1] & 0xFF)
    # SUB unimplemented
    registers[15] = 0x080004D4
    return 0x080004C8

def func_0800028C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080004F0(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # ANDle unimplemented
    # COPROCESSORgt unimplemented
    registers[3] = (registers[0] & registers[1]) & 0xFFFFFFFF
    registers[15] = 0x080004FC
    # ADCmi unimplemented
    registers[15] = 0x08000500
    registers[13] = memory.read_u16(registers[15] + 505) & 0xFFFF
    # COPROCESSORmi unimplemented
    registers[15] = 0x08000508
    return 0x09D93D30

def func_0800058C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # EOReq unimplemented
    # SWIvs unimplemented
    # SBCeq unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # COPROCESSOReq unimplemented
    # EOReq unimplemented
    # EORcc unimplemented
    # ANDeq unimplemented
    # SWI software interrupt
    # ANDeq unimplemented
    # SWIvc unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # COPROCESSOReq unimplemented
    # SWIvc unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # LDRne unimplemented
    # ANDeq unimplemented
    # SWIvc unimplemented
    # EOReq unimplemented
    # LDRne unimplemented
    # ANDeq unimplemented
    # RSBcc unimplemented
    # RSBeq unimplemented
    # STRHcc unimplemented
    # EOReq unimplemented
    # TEQcc unimplemented
    registers[15] = 0x08000604
    # EOReq unimplemented
    # EORvs unimplemented
    # EOReq unimplemented
    # SWIcc unimplemented
    # EOReq unimplemented
    # RSBcc unimplemented
    # ANDeq unimplemented
    # COPROCESSORcc unimplemented
    # EOReq unimplemented
    # COPROCESSORvc unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # COPROCESSOReq unimplemented
    # LDReq unimplemented
    # ANDeq unimplemented
    # RSBeq unimplemented
    # ANDeq unimplemented
    # ANDvs unimplemented
    # ANDeq unimplemented
    # RSBcc unimplemented
    # ANDeq unimplemented
    registers[15] = 0x08000660
    return 0x09699F54

def func_080002EC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u16(registers[0] + 0, registers[0] & 0xFFFF)
    registers[15] = 0x080002F0

def func_08000424(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u8(registers[2] + 1, registers[4] & 0xFF)
    registers[0] = memory.read_u16(registers[13] + 15) & 0xFFFF
    registers[15] = 0x0800042C

def func_080003AC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # CMP unimplemented
    registers[15] = 0x080003B0
    return 0x08000424

def func_08000464(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[2] = 8
    # AND unimplemented
    memory.write_u16(registers[0] + 226, registers[0] & 0xFFFF)
    memory.write_u16(registers[0] + 288, registers[1] & 0xFFFF)
    # CMP unimplemented
    registers[15] = 0x08000478
    return 0x08000480

def func_08000490(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[14] = memory.read_u32(registers[13] + 4)
    # SUB unimplemented
    registers[15] = 0x08000498
    return 0x08000464

def func_0800011C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # ADDeq unimplemented
    registers[15] = 0x08000120
    registers[15] = memory.read_u32(registers[12] + 0)
    # CMPcs unimplemented
    # BICeq unimplemented
    registers[15] = 0x0800012C
    memory.write_u32(registers[11] + 0, registers[15])
    # STRmi unimplemented
    registers[1] = (registers[0] & registers[9]) & 0xFFFFFFFF
    registers[15] = 0x08000138
    # STRmi unimplemented
    registers[15] = 0x0800013C
    return 0x082525CC

def func_08000414(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[3] = 0
    registers[4] = 19
    registers[15] = 0x0800041C

def func_0800041C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[2] = 33554432
    memory.write_u8(registers[2] + 0, registers[3] & 0xFF)
    registers[15] = 0x08000424

def func_080002A0(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080002A4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080003BC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # SUB unimplemented
    memory.write_u16(registers[0] + 1288, registers[5] & 0xFFFF)
    registers[5] = (registers[4])
    registers[0] = (registers[5] | 0) & 0xFFFFFFFF
    # ADD unimplemented
    # CMP unimplemented
    registers[15] = 0x080003D4

def func_08000228(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # ANDle unimplemented
    registers[4] = (registers[0] & registers[5]) & 0xFFFFFFFF
    # TSTcs unimplemented
    # COPROCESSORlt unimplemented
    # STRmi unimplemented
    # TSTeq unimplemented
    # ANDeq unimplemented
    # STReq unimplemented
    # LDRlt unimplemented
    # ANDle unimplemented
    # STRmi unimplemented
    # SWIlt unimplemented
    # COPROCESSORlt unimplemented
    # STRBmi unimplemented
    # ANDeq unimplemented
    # TSTeq unimplemented
    # STReq unimplemented
    registers[15] = 0x0800026C
    registers[1] = memory.read_u32(registers[15] + 132)
    memory.write_u32(registers[1] + 0, registers[1])
    registers[15] = 0x08000274
    return 0x08000300

def func_080002AC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080003B4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # CMP unimplemented
    registers[15] = 0x080003B8
    return 0x08000424

def func_080002F4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x080002F0

def func_08000290(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_08000444(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u32(registers[13] - 4, registers[14])
    registers[15] = 0x08000448
    return 0x0800038C

def func_08000664(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # EOReq unimplemented
    # SWIvc unimplemented
    # RSBeq unimplemented
    # SWIcc unimplemented
    # EOReq unimplemented
    # STRHeq unimplemented
    # RSBeq unimplemented
    # STRBvs unimplemented
    # ANDeq unimplemented
    # SWIne unimplemented
    # RSBeq unimplemented
    # SWIne unimplemented
    # ANDeq unimplemented
    # STRHvc unimplemented
    # RSBeq unimplemented
    # SWIvc unimplemented
    # RSBeq unimplemented
    # LDRHne unimplemented
    # EOReq unimplemented
    # RSBvs unimplemented
    # EOReq unimplemented
    # SWIeq unimplemented
    # RSBeq unimplemented
    # STReq unimplemented
    # RSBeq unimplemented
    registers[15] = 0x080006C8
    return 0x09FDE458

def func_08000300(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # TSTeq unimplemented
    memory.write_u16(registers[13] - 15, registers[0] & 0xFFFF)
    registers[0] = 67108864
    registers[1] = 256
    registers[1] = (registers[0] & ~ 0) & 0xFFFFFFFF
    registers[1] = 2048
    registers[1] = (registers[0] & ~ 0) & 0xFFFFFFFF
    registers[0] = 83886080
    registers[1] = 0 ^ 0xFFFFFFFF
    registers[1] = (registers[0] & ~ 0) & 0xFFFFFFFF
    registers[0] = 100663296
    registers[1] = 768
    registers[15] = 0x08000330

def func_080003D8(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[3] = 0
    # ADD unimplemented
    # CMP unimplemented
    registers[15] = 0x080003E4
    return 0x0800041C

def func_08000298(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_08000484(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # ADD unimplemented
    memory.write_u32(registers[13] - 4, registers[14])
    registers[15] = 0x0800048C
    return 0x0800038C

def func_080002D8(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[0] = 98
    registers[15] = 0x080002DC
    return 0x0800038C

def func_080004A4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u32(registers[13] - 12, registers[0])
    registers[3] = 1 ^ 0xFFFFFFFF
    registers[15] = 0x080004AC

def func_0800019C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # LDRne unimplemented
    # ANDle unimplemented
    # ANDgt unimplemented
    # LDRSHle unimplemented
    # STRHmi unimplemented
    # TSTeq unimplemented
    # TSTeq unimplemented
    # STReq unimplemented
    # ANDeq unimplemented
    # TSTeq unimplemented
    # TSTeq unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # STReq unimplemented
    # TSTeq unimplemented
    # TSTeq unimplemented
    # STReq unimplemented
    # TSTeq unimplemented
    # TSTeq unimplemented
    # STReq unimplemented
    # STReq unimplemented
    # TSTeq unimplemented
    # STReq unimplemented
    # ANDeq unimplemented
    # ANDeq unimplemented
    # TSTeq unimplemented
    # ANDeq unimplemented
    # STReq unimplemented
    # STReq unimplemented
    # STRHmi unimplemented
    # COPROCESSORlt unimplemented
    # LDRBmi unimplemented
    # COPROCESSORmi unimplemented
    registers[15] = 0x08000220
    return 0x0801E2B0

def func_080004AC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[2] = (registers[2] & registers[3]) & 0xFFFFFFFF
    registers[3] = (registers[1] | 0) & 0xFFFFFFFF
    registers[3] = (registers[0] | 0) & 0xFFFFFFFF
    # SUB unimplemented
    registers[15] = 0x080004BC
    return 0x080004AC

def func_08000450(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x08000434

def func_080006CC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # RSBeq unimplemented
    registers[15] = 0x080006D0
    return 0x09BDA460

def func_08000454(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[0] = memory.read_u32(registers[13] + 3)
    registers[15] = 0x08000458

def func_080002C4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080002B0(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080002CC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[0] = memory.read_u32(registers[15] + 44)
    registers[15] = 0x080002D0
    return 0x0800042C

def func_08000390(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u16(registers[13] - 15, registers[0] & 0xFFFF)
    registers[2] = 33554432
    registers[3] = memory.read_u8(registers[2] + 0) & 0xFF
    registers[4] = memory.read_u8(registers[2] + 1) & 0xFF
    registers[15] = 0x080003A0
    registers[1] = memory.read_u16(registers[15] + 316) & 0xFFFF
    # CMP unimplemented
    registers[15] = 0x080003A8
    return 0x080003D4

def func_08000434(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u16(registers[0] + 256, registers[1] & 0xFFFF)
    registers[0] = memory.read_u8(registers[1] + 1) & 0xFF
    # CMP unimplemented
    registers[15] = 0x08000440
    return 0x08000450

def func_08000400(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[14] = memory.read_u32(registers[13] + 4)
    registers[0] = (registers[2])
    registers[1] = (registers[2])
    # CMP unimplemented
    registers[15] = 0x08000410
    return 0x080003F4

def func_0800044C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[14] = memory.read_u32(registers[13] + 4)
    registers[15] = 0x08000450

def func_0800045C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    memory.write_u32(registers[13] - 7, registers[0])
    memory.write_u16(registers[0] + 256, registers[1] & 0xFFFF)
    registers[15] = 0x08000464

def func_080006D4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # RSBeq unimplemented
    # STRHvs unimplemented
    # EOReq unimplemented
    # SWIcc unimplemented
    # ANDeq unimplemented
    # TEQcc unimplemented
    # RSBeq unimplemented
    # SWIcc unimplemented
    # RSBeq unimplemented
    # COPROCESSORcc unimplemented
    # EOReq unimplemented
    # LDRHne unimplemented
    # ANDeq unimplemented
    # STRBvs unimplemented
    # EOReq unimplemented
    # STRBvs unimplemented
    # ANDeq unimplemented
    registers[15] = 0x08000718
    return 0x098D94A8

def func_0800029C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800042C

def func_080000DC(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    # ANDeq unimplemented
    registers[0] = 67108864
    memory.write_u32(registers[0] + 520, registers[0])
    registers[0] = 18
    registers[15] = 0x080000EC
    # SWP unimplemented
    registers[15] = 0x080000F0
    registers[13] = memory.read_u16(registers[15] + 184) & 0xFFFF
    registers[0] = 31
    registers[15] = 0x080000F8
    # SWP unimplemented
    registers[15] = 0x080000FC
    registers[13] = memory.read_u16(registers[15] + 176) & 0xFFFF
    # ADD unimplemented
    registers[15] = 0x08000104
    return registers[0]

def func_080003D4(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x0800041C

def func_0800042C(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return registers[14]

def func_08000480(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    return 0x08000484

def func_080002E0(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[0] = memory.read_u32(registers[15] + 24)
    registers[15] = 0x080002E4
    return 0x0800042C

def func_08000330(registers, cpsr):
    global vram, palette_ram, oam, ewram, ROM_DATA
    registers[2] = memory.read_u32(registers[15] + 424)
    registers[3] = memory.read_u8(registers[2] + 0) & 0xFF
    registers[4] = 4
    registers[15] = 0x0800033C
func_table = {}
func_table[0x08000458] = func_08000458
func_table[0x0800037C] = func_0800037C
func_table[0x08000280] = func_08000280
func_table[0x080002F0] = func_080002F0
func_table[0x0800033C] = func_0800033C
func_table[0x08000224] = func_08000224
func_table[0x0800049C] = func_0800049C
func_table[0x080002E8] = func_080002E8
func_table[0x08000278] = func_08000278
func_table[0x08000140] = func_08000140
func_table[0x080002C8] = func_080002C8
func_table[0x0800050C] = func_0800050C
func_table[0x08000148] = func_08000148
func_table[0x080003F4] = func_080003F4
func_table[0x08000284] = func_08000284
func_table[0x080003E8] = func_080003E8
func_table[0x080004D8] = func_080004D8
func_table[0x080000BC] = func_080000BC
func_table[0x08000430] = func_08000430
func_table[0x08000000] = func_08000000
func_table[0x080002BC] = func_080002BC
func_table[0x0800038C] = func_0800038C
func_table[0x080004C0] = func_080004C0
func_table[0x080004E0] = func_080004E0
func_table[0x080002B4] = func_080002B4
func_table[0x08000028] = func_08000458
func_table[0x08000288] = func_08000288
func_table[0x080002D4] = func_080002D4
func_table[0x080002A8] = func_080002A8
func_table[0x080004A0] = func_080004A0
func_table[0x080000C4] = func_08000458
func_table[0x08000178] = func_08000178
func_table[0x08000010] = func_08000010
func_table[0x080002C0] = func_080002C0
func_table[0x080002F8] = func_08000458
func_table[0x080002B8] = func_080002B8
func_table[0x08000004] = func_08000458
func_table[0x08000370] = func_08000370
func_table[0x08000294] = func_08000294
func_table[0x080004C8] = func_080004C8
func_table[0x08000108] = func_08000458
func_table[0x0800028C] = func_0800028C
func_table[0x080004F0] = func_080004F0
func_table[0x0800058C] = func_0800058C
func_table[0x080002EC] = func_080002EC
func_table[0x08000424] = func_08000424
func_table[0x080003AC] = func_080003AC
func_table[0x08000464] = func_08000464
func_table[0x08000490] = func_08000490
func_table[0x0800011C] = func_0800011C
func_table[0x08000414] = func_08000414
func_table[0x0800041C] = func_0800041C
func_table[0x08000088] = func_08000458
func_table[0x080002A0] = func_080002A0
func_table[0x080002A4] = func_080002A4
func_table[0x080003BC] = func_080003BC
func_table[0x08000228] = func_08000228
func_table[0x080002AC] = func_080002AC
func_table[0x080003B4] = func_080003B4
func_table[0x08000098] = func_08000458
func_table[0x080002F4] = func_080002F4
func_table[0x08000290] = func_08000290
func_table[0x08000444] = func_08000444
func_table[0x08000664] = func_08000664
func_table[0x08000300] = func_08000300
func_table[0x080003D8] = func_080003D8
func_table[0x08000298] = func_08000298
func_table[0x08000484] = func_08000484
func_table[0x080002D8] = func_080002D8
func_table[0x080004A4] = func_080004A4
func_table[0x0800019C] = func_0800019C
func_table[0x080004AC] = func_080004AC
func_table[0x08000450] = func_08000450
func_table[0x080006CC] = func_080006CC
func_table[0x08000454] = func_08000454
func_table[0x080002C4] = func_080002C4
func_table[0x080002B0] = func_080002B0
func_table[0x080002CC] = func_080002CC
func_table[0x08000390] = func_08000390
func_table[0x08000434] = func_08000434
func_table[0x08000400] = func_08000400
func_table[0x0800044C] = func_0800044C
func_table[0x0800045C] = func_0800045C
func_table[0x080006D4] = func_080006D4
func_table[0x0800029C] = func_0800029C
func_table[0x080000DC] = func_080000DC
func_table[0x080003D4] = func_080003D4
func_table[0x0800042C] = func_0800042C
func_table[0x08000480] = func_08000480
func_table[0x080002E0] = func_080002E0
func_table[0x0800047C] = func_0800049C
func_table[0x08000330] = func_08000330


def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    def ror(v, a):
        a = a & 31
        return ((v >> a) | (v << (32 - a))) & 0xFFFFFFFF
    fc = 0; mi = 1000000; ic = 0
    print(f"PC=0x{registers[15]:08X}")
    while ic < mi:
        pc = registers[15]
        func = func_table.get(pc)
        if func is None: print(f"Unknown PC: 0x{pc:08X}"); break
        func(registers, cpsr); ic += 1
        if registers[15] == pc: print(f"Loop at 0x{pc:08X}"); break
        if ic % 10000 == 0: print(f"{ic} instrs")
        if frame_limit and fc >= frame_limit: break
        if ic % 1000 == 0: fc += 1
    print(f"Done: {ic} instrs")
    return fc

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1, dump_memory=None, dump_region=None):
    pygame.init()
    if not headless:
        screen = pygame.display.set_mode((240 * scale, 160 * scale))
        pygame.display.set_caption("GBAtoPy")
    else:
        screen = pygame.Surface((240 * scale, 160 * scale))
    clock = pygame.time.Clock()
    fc = 0; running = True; mi = 1000000; ic = 0
    print(f"PC=0x{registers[15]:08X}")
    while running and fc < 10000:
        for e in pygame.event.get():
            if e.type == pygame.QUIT: running = False
        # Execute instructions for this frame (max 200000 instrs per frame)
        for _ in range(200000):
            pc = registers[15]
            func = func_table.get(pc)
            if func is None: break
            func(registers, cpsr); ic += 1
            if registers[15] == pc: break
        # Render frame and update APU
        ppu_instance.render_frame()
        # VBlank IRQ dispatch
        dispstat = memory.read_u16(0x04000004)
        vblank_flag = (dispstat & 0x01) != 0
        if vblank_flag:
            ie = memory.read_u16(0x04000200)
            ime = memory.read_u16(0x04000208)
            if ie & 0x01 and ime & 0x01:
                memory.write_u16(0x04000202, memory.read_u16(0x04000202) | 0x01)
                registers[15] = memory.read_u32(0x03007FFC)
        apu_instance.update()
        surf = ppu_instance.get_surface()
        screen.blit(pygame.transform.scale(surf, (240 * scale, 160 * scale)), (0, 0))
        if not headless: pygame.display.flip()
        clock.tick(60); fc += 1
        if frame_limit and fc >= frame_limit: break
    if screenshot_path:
        pygame.image.save(screen, screenshot_path)
        print(f"Screenshot: {screenshot_path}")
    pygame.quit()
    return fc

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--screenshot", type=str)
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args()
    frames = run_with_pygame(headless=args.headless, frame_limit=args.frame, screenshot_path=args.screenshot, scale=args.scale)
    print(f"{frames} frames")
