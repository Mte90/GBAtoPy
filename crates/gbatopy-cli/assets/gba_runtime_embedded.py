"""
PyBoyAdvance Runtime (Embedded)
MIT License - Original code from PyBoyAdvance
https://github.com/d7499/pyboy-advance

Required imports for standalone execution:
"""

import argparse
import math
import os
import pygame
import struct
import sys
import time
from enum import Enum, auto
from PIL import Image
from typing import Callable, List, Dict, Tuple, Optional




# === Start of memory.py ===



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

    SRAM_START = 0x0E000000
    SRAM_END = 0x0E007FFF
    SRAM_SIZE = 0x8000


class Memory:
    def __init__(self):
        # Use array.array('B') for faster memory access
        self.bios = _array.array('B', [0] * MemoryMap.BIOS_SIZE)
        self.ewram = _array.array('B', [0] * MemoryMap.EWRAM_SIZE)
        self.iwram = _array.array('B', [0] * MemoryMap.IWRAM_SIZE)
        self.io = _array.array('B', [0] * MemoryMap.IO_SIZE)
        self.palette = _array.array('B', [0] * MemoryMap.PALETTE_SIZE)
        
        # Initialize VRAM to zero (real GBA hardware behavior on reset)
        # Some test ROMs (like stripes.gba) rely on uninitialized VRAM data for graphics
        # mGBA happens to initialize VRAM with non-zero data, making those ROMs appear to work
        # For faithful hardware emulation, we use zero initialization
        self.vram = _array.array('B', [0] * MemoryMap.VRAM_SIZE)
        
        self.oam = _array.array('B', [0] * MemoryMap.OAM_SIZE)
        self.sram = _array.array('B', [0] * MemoryMap.SRAM_SIZE)

        # GBA hardware default: identity affine (dx=0x100, dmy=0x100).
        # Matches mGBA's GBAVideoSoftwareRendererInit (bg->dx=256, bg->dmy=256).
        # Without this, bitmap modes (3/4/5) map every pixel to VRAM[0] (black).
        _ap = [0] * 16
        _ap[0] = 0x00; _ap[1] = 0x01  # BG2PA = 0x0100 (dx = 256)
        _ap[6] = 0x00; _ap[7] = 0x01  # BG2PD = 0x0100 (dmy = 256)
        self._affine_params = _array.array('B', _ap)

        self.rom: Optional[bytearray] = None
        self.rom_size: int = 0
        self.rom_mirror_size: int = MemoryMap.ROM_MAX_SIZE
        self.open_bus: int = 0

        self._mmio_write_handlers: dict[int, Callable[[int, int], None]] = {}
        self._mmio_read_handlers: dict[int, Callable[[int], int]] = {}
        # GBA hardware default: DISPCNT = 0x0080 (Mode 0, display not forced blank, all BGs off)
        # The ROM writes to DISPCNT will set the correct mode and enable bits
        self.io[0x00] = 0x80  # DISPCNT low byte: Mode 0, BG3 display on
        self.io[0x01] = 0x00  # DISPCNT high byte: no forced blank

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
        if 0x04000020 <= addr <= 0x0400002E:
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
        # PPU registers (0x04000000-0x0400005F) — return live values from PPU
        if 0x04000000 <= addr <= 0x0400005F and self._ppu is not None:
            val16 = self._ppu.read_register(addr & ~1)
            return (val16 >> (8 * (addr & 1))) & 0xFF
        # Window registers (0x04000048-0x0400004F)
        if 0x04000048 <= addr <= 0x0400004F:
            return self._handle_window_read(addr)
        if 0x04000020 <= addr <= 0x0400002E:
            return self._handle_affine_bg_read(addr)
        # Sound registers (0x04000060-0x0400008F, exclusive of affine range)
        if 0x04000060 <= addr <= 0x0400008F:
            return self._handle_sound_read(addr)
        # Interrupt registers: IE (0x04000200), IF (0x04000202), IME (0x04000208)
        if self._interrupts is not None:
            if addr == 0x04000200 or addr == 0x04000201:
                return (self._interrupts.ie_reg >> (8 * (addr & 1))) & 0xFF
            if addr == 0x04000202 or addr == 0x04000203:
                return (self._interrupts.if_reg >> (8 * (addr & 1))) & 0xFF
            if addr == 0x04000208 or addr == 0x04000209:
                return (self._interrupts.ime_reg >> (8 * (addr & 1))) & 0xFF
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
        channel = (addr - 0x040000B0) // 0x0C
        reg_offset = (addr - 0x040000B0) % 0x0C
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
        elif reg_offset == 10:
            return ch.control
        return 0

    def _handle_dma_write(self, addr: int, value: int):
        channel = (addr - 0x040000B0) // 0x0C
        reg_offset = (addr - 0x040000B0) % 0x0C
        if channel < 0 or channel > 3:
            return
        ch = self._dma.channels[channel]
        was_enabled = ch.enabled
        ch.read_from_memory()
        if reg_offset == 0:
            ch.src_addr = value
        elif reg_offset == 4:
            ch.dst_addr = value
        elif reg_offset == 8:
            if value > 0xFFFF:
                ch.count = value & 0xFFFF
                ch.control = (value >> 16) & 0xFFFF
            else:
                ch.count = value & 0xFFFF
        elif reg_offset == 10:
            ch.control = value & 0xFFFF
        ch.read_from_memory()
        if ch.enabled and not was_enabled:
            if ch.is_immediate():
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
        elif addr == 0x04000202:
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
        base = MemoryMap.IO_START + 0x20
        byte_offset = addr - base
        if 0 <= byte_offset < 16:
            byte_idx = byte_offset % 2
            param_idx = byte_offset // 2
            return self._affine_params[param_idx * 2 + byte_idx]
        return 0

    def _handle_affine_bg_write(self, addr: int, value: int):
        """Write affine background parameter (16-bit)."""
        base = MemoryMap.IO_START + 0x20
        byte_offset = addr - base
        if 0 <= byte_offset < 16:
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

        offset = (addr - MemoryMap.ROM_START) % self.rom_mirror_size
        if offset >= self.rom_size:
            return -1
        return offset

    def _map_address(self, addr: int) -> int:
        # GBA memory map: BIOS (0x0000-0x3FFF) is read-only; writes ignored.
        # Small addresses are NOT remapped to MMIO — that corrupts ROMs (e.g. rates)
        # whose IWRAM code legitimately uses small values as buffer pointers.
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
            offset = addr & 0x0001FFFF
            if offset >= MemoryMap.VRAM_SIZE:
                offset -= MemoryMap.VRAM_SIZE
            return offset | 0x06000000

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
                return result & 0xFF
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
        addr &= 0xFFFFFFFF
        mapped = self._map_address(addr)
        if MemoryMap.IO_START <= mapped <= MemoryMap.IO_END:
            lo = self.read_u8(mapped)
            hi = self.read_u8(mapped + 1)
            return lo | (hi << 8)
        buf, start = self._buffer_for_addr(addr)
        if buf:
            return int.from_bytes(buf[start:start + 2], 'little')
        return int.from_bytes(self.rom[addr - 0x08000000:(addr - 0x08000000) + 2], 'little')
    
    def read_32(self, addr: int) -> int:
        """Read 32-bit unsigned value"""
        addr &= 0xFFFFFFFF
        mapped = self._map_address(addr)
        if MemoryMap.IO_START <= mapped <= MemoryMap.IO_END:
            b0 = self.read_u8(mapped)
            b1 = self.read_u8(mapped + 1)
            b2 = self.read_u8(mapped + 2)
            b3 = self.read_u8(mapped + 3)
            return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
        buf, off = self._buffer_for_addr(mapped)
        if buf is not None and off + 4 <= len(buf):
            return int.from_bytes(buf[off:off + 4], 'little')
        b0 = self.read_u8(mapped)
        b1 = self.read_u8(mapped + 1)
        b2 = self.read_u8(mapped + 2)
        b3 = self.read_u8(mapped + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
    def read_u32(self, addr: int) -> int:
        """Read 32-bit unsigned value"""
        addr &= 0xFFFFFFFF
        mapped = self._map_address(addr)
        if MemoryMap.IO_START <= mapped <= MemoryMap.IO_END:
            b0 = self.read_u8(mapped)
            b1 = self.read_u8(mapped + 1)
            b2 = self.read_u8(mapped + 2)
            b3 = self.read_u8(mapped + 3)
            return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
        buf, off = self._buffer_for_addr(mapped)
        if buf is not None and off + 4 <= len(buf):
            return int.from_bytes(buf[off:off + 4], 'little')
        b0 = self.read_u8(mapped)
        b1 = self.read_u8(mapped + 1)
        b2 = self.read_u8(mapped + 2)
        b3 = self.read_u8(mapped + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
    def write_u8(self, addr: int, value: int, _from_multibyte: bool = False):
        addr &= 0xFFFFFFFF
        value &= 0xFF
        if not (0x04000000 <= addr <= 0x07FFFFFF):
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
            return

        if MemoryMap.IO_START <= addr <= MemoryMap.IO_END:
            offset = addr - MemoryMap.IO_START
            self.io[offset] = value
            self.open_bus = value
            if not _from_multibyte and 0x04000000 <= addr <= 0x0400005F:
                reg_base = addr & ~1
                base_offset = reg_base - MemoryMap.IO_START
                merged = self.io[base_offset] | (self.io[base_offset + 1] << 8)
                self._dispatch_hal_write(reg_base, merged)
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
        mapped_addr = self._map_address(addr)
        if 0x04000020 <= mapped_addr <= 0x0400002E and mapped_addr % 2 == 0:
            base = MemoryMap.IO_START + 0x20
            byte_offset = mapped_addr - base
            param_idx = byte_offset // 2
            self._affine_params[param_idx * 2] = value & 0xFF
            self._affine_params[param_idx * 2 + 1] = (value >> 8) & 0xFF
            self._dispatch_hal_write(mapped_addr, value)
            return

        self.write_u8(mapped_addr, value & 0xFF, _from_multibyte=True)
        self.write_u8(mapped_addr + 1, (value >> 8) & 0xFF, _from_multibyte=True)

        if MemoryMap.IO_START <= mapped_addr <= MemoryMap.IO_END:
            self._dispatch_hal_write(mapped_addr, value)

    def write_u32(self, addr: int, value: int):
        addr &= 0xFFFFFFFF
        value &= 0xFFFFFFFF
        mapped_addr = self._map_address(addr)

        if MemoryMap.IO_START <= mapped_addr <= MemoryMap.IO_END:
            # GBA MMIO registers are 16-bit. A 32-bit write only affects the
            # lower 16 bits (the register at the base address). The upper 16
            # bits target an adjacent address that is often undefined and
            # ignored on real hardware. Writing them to io[] pollutes bytes
            # that read_u32 reads back, corrupting 32-bit MMIO reads (e.g.,
            # IME at 0x04000208 reads back 0x04000001 instead of 0x00000001
            # because io[0x20B] was polluted by a prior STR of 0x04000000).
            lo = value & 0xFFFF
            self.write_u8(mapped_addr, lo & 0xFF, _from_multibyte=True)
            self.write_u8(mapped_addr + 1, (lo >> 8) & 0xFF, _from_multibyte=True)
            self._dispatch_hal_write(mapped_addr, lo)
            return

        self.write_u8(mapped_addr, value & 0xFF, _from_multibyte=True)
        self.write_u8(mapped_addr + 1, (value >> 8) & 0xFF, _from_multibyte=True)
        self.write_u8(mapped_addr + 2, (value >> 16) & 0xFF, _from_multibyte=True)
        self.write_u8(mapped_addr + 3, (value >> 24) & 0xFF, _from_multibyte=True)

    def load_rom(self, path: str):
        with open(path, "rb") as f:
            rom_data = f.read()

        self.load_rom_data(rom_data)

    def load_rom_data(self, data):
        if isinstance(data, str):
            data = data.encode("latin-1")
        self.rom = _array.array('B', data)
        self.rom_size = len(data)
        _ms = 1
        while _ms < self.rom_size:
            _ms <<= 1
        self.rom_mirror_size = max(_ms, 1)

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

        if self.dump_dir is None:
            raise ValueError("No dump directory set. Call set_dump_directory() first.")

        if filename is None:
            filename = f"memory_dump_{dump.get('timestamp', 'unknown')}"

        # Ensure directory exists
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


# === End of memory.py ===


# === Start of ppu.py ===



# Numba JIT compilation support
try:
    _HAS_NUMBA = True
except ImportError:
    numba = None
    njit = None
    prange = None
    _HAS_NUMBA = False

_NUMBA_ENABLED = False
_NUMBA_PPU_ENABLED = True  # Separate flag for PPU JIT


def _try_enable_numba_jit() -> bool:
    """Attempt to enable Numba JIT for PPU functions.

    Returns the enabled state. Falls back gracefully if numba is not installed."""
    global _NUMBA_PPU_ENABLED, _HAS_NUMBA
    try:
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
                    color_idx = int(byte_val & 0x0F)
                else:
                    color_idx = int((byte_val >> 4) & 0x0F)
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
        self.sprite_list = []
        
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
            x = attr1 & 0x1FF  # X position (0-511, wraps at 256 for display)
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
                "mosaic": mosaic,
            })

    def _render_sprites(self, layer_enable: int = 0x3F):
        """Render all sprites from OAM after background layers.
        
        Called from render_frame() after backgrounds are rendered.
        Handles:
        - 4BPP/8BPP color modes (index 0 = transparent)
        - 2D and 1D OBJ character VRAM mapping (DISPCNT bit 6)
        - Sprite priority (lower value = draw on top)
        - Rotation/scaling (affine sprites)
        - Per-object mosaic
        - Blend target capture (second_target_framebuffer/layer_origin)
        """
        self.parse_oam()
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
        # Calculate base tile address in VRAM (OBJ char base = 0x06010000)
        # 4BPP tiles: 32 bytes each (8x8 pixels × 4 bits)
        # 8BPP tiles: 64 bytes each (8x8 pixels × 8 bits)
        vram_base = 0x06010000
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
                if sprite.get("mosaic", 0) and self.mosaic_enabled:
                    src_px, src_py = self._apply_mosaic(px, py, is_obj=True)
                else:
                    src_px, src_py = px, py
                tile_x = src_px // 8
                tile_y = src_py // 8
                local_x = src_px % 8
                local_y = src_py % 8
                
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
                    self.second_target_framebuffer[screen_y][screen_x] = self.framebuffer[screen_y][screen_x]
                    self.second_target_layer[screen_y][screen_x] = self.layer_origin[screen_y][screen_x]
                    self.framebuffer[screen_y][screen_x] = (r, g, b)
                    self.layer_origin[screen_y][screen_x] = 4
                except Exception:
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
        
        # VRAM tile addressing - OBJ char base is 0x06010000
        vram_base = 0x06010000
        tile_size = 32
        tiles_per_row = 32
        vram_offset = 0
        if not self.obj_character_vram_mapping:
            vram_offset = 128
        
        # Render sprite with affine transformation
        for py in range(height):
            for px in range(width):
                if sprite.get("mosaic", 0) and self.mosaic_enabled:
                    mpx, mpy = self._apply_mosaic(px, py, is_obj=True)
                else:
                    mpx, mpy = px, py
                rel_x = mpx - cx
                rel_y = mpy - cy
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
                    self.second_target_framebuffer[screen_y][screen_x] = self.framebuffer[screen_y][screen_x]
                    self.second_target_layer[screen_y][screen_x] = self.layer_origin[screen_y][screen_x]
                    self.framebuffer[screen_y][screen_x] = (r, g, b)
                    self.layer_origin[screen_y][screen_x] = 4
                except Exception:
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
    REG_WIN1H = 0x04000042
    REG_WIN0V = 0x04000044
    REG_WIN1V = 0x04000046
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
        self.sprite_list = []

        # Display control - use sensible defaults (mode 3, all BGs)
        # But read actual DISPCNT from memory if available
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
        
        # Read DISPCNT from memory to get actual mode
        if self.memory:
            dispcnt = self.memory.read_u16(self.REG_DISPCNT)
            mode = dispcnt & 0x7
            if mode <= 5:
                self.mode = mode
            self.bg0_enable = bool(dispcnt & 0x0100)
            self.bg1_enable = bool(dispcnt & 0x0200)
            self.bg2_enable = bool(dispcnt & 0x0400)
            self.bg3_enable = bool(dispcnt & 0x0800)
            self.obj_enable = bool(dispcnt & 0x1000)
        self.win1_enable = False
        self.obj_window_enable = False
        self.dispcnt = 0x0403
        self._obj_window_rects = []
        
        # Numba JIT control for PPU
        self.numba_ppu_enabled = is_numba_ppu_enabled()
        
        # Cache for VRAM/palette data (updated each frame for JIT)
        self._vram_cache = None
        self._palette_cache = None
        
        # Screen dimensions
        self.screen_width = 240
        self.screen_height = 160

        # Per-scanline BG2 affine snapshots for HBlank-DMA support.
        # Fixed-size array indexed by vcount (0..159) so that step_scanline() being
        # called from both the main loop and the fallback interpreter is idempotent:
        # the same vcount overwrites the same slot instead of appending duplicates.
        self._bg2_affine_snapshots = [None] * self.screen_height

        # BG configurations (per layer)
        self.bg_priority = [0] * 4
        self.bg_char_block = [0] * 4
        self.bg_mosaic = [False] * 4
        self.bg256 = [False] * 4
        self.bg_screen_block = [0] * 4
        self.bg_affine = [False] * 4
        self.bg_size = [0] * 4  # 0=256x256, 1=512x256, 2=256x512, 3=512x512
        
        # Read BGxCNT registers to get BG configuration (after initializing lists)
        if self.memory:
            for bg in range(4):
                bg_cnt_addr = 0x04000008 + bg * 2  # BG0CNT=0x04000008, BG1CNT=0x0400000A, etc.
                bg_cnt = self.memory.read_u16(bg_cnt_addr)
                self.bg_priority[bg] = bg_cnt & 0x03
                self.bg_char_block[bg] = (bg_cnt >> 2) & 0x03
                self.bg_mosaic[bg] = bool(bg_cnt & 0x0040)
                self.bg256[bg] = bool(bg_cnt & 0x0080)  # 8BPP if set
                self.bg_screen_block[bg] = (bg_cnt >> 8) & 0x1F
                self.bg_affine[bg] = bool(bg_cnt & 0x0100)  # Affine if bit 8 is set (for BG2/BG3)
                self.bg_size[bg] = (bg_cnt >> 14) & 0x03

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

        # Per-scanline latched window flags
        self._win0_active = False
        self._win1_active = False

        # Per-scanline window snapshots: (left, right, top, bottom) for WIN0/WIN1
        # captured at the start of each scanline, before VBlank IRQs update them.
        # Mirrors _bg2_affine_snapshots so mid-frame WIN0V/WIN1V writes take effect.
        self._win0_snapshots = [None] * self.screen_height
        self._win1_snapshots = [None] * self.screen_height

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

        try:

            arr = np.array(self.framebuffer, dtype=np.uint8)
            # Transpose from (height, width, 3) to (width, height, 3) for blit_array
            arr = np.transpose(arr, (1, 0, 2))
            surf = pygame.Surface((self.screen_width, self.screen_height))
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
        """Initialize the framebuffer with the backdrop color (palette entry 0)."""
        backdrop = (0, 0, 0)
        try:
            color_val = self.memory.read_u16(0x05000000)
            r = (color_val >> 0) & 0x1F
            g = (color_val >> 5) & 0x1F
            b = (color_val >> 10) & 0x1F
            backdrop = (_c5to8(r), _c5to8(g), _c5to8(b))
        except Exception:
            pass
        self.framebuffer = [
            [backdrop for _ in range(self.screen_width)] for _ in range(self.screen_height)
        ]
        # Track which BG layer (0-3) or OBJ (4) or backdrop (5) each pixel belongs to
        self.layer_origin = [[5]*240 for _ in range(160)]
        # Second target framebuffer for blend operations
        self.second_target_framebuffer = [[None]*240 for _ in range(160)]
        # Second target layer index for blend operations (5 = backdrop)
        self.second_target_layer = [[5]*240 for _ in range(160)]

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
        # Use modulo 256 to match mGBA behavior for out-of-range tile indices
        tile_offset = (tile_index % 256) * 64
        return _decode_tile_8bpp_jit(vram_data, char_block + tile_offset)

    def _get_palette_color_jit(self, palette_idx: int) -> Tuple[int, int, int]:
        """JIT-accelerated palette color lookup."""
        palette_data = self._get_palette_data()
        addr = palette_idx * 2
        color_val = _read_palette_jit(palette_data, addr)
        r = _c5to8_jit((color_val >> 0) & 0x1F)
        g = _c5to8_jit((color_val >> 5) & 0x1F)
        b = _c5to8_jit((color_val >> 10) & 0x1F)
        return (r, g, b)

    def _get_palette_color_256_jit(self, palette_idx: int) -> Tuple[int, int, int]:
        """JIT-accelerated 256-color palette lookup."""
        palette_data = self._get_palette_data()
        addr = palette_idx * 2
        color_val = _read_palette_jit(palette_data, addr)
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
            self.bg2_x = (self.bg2_x & 0xFFFF0000) | (value & 0xFFFF)
        elif addr == self.REG_BG2X + 2:
            self.bg2_x = (self.bg2_x & 0x0000FFFF) | (value << 16)
            # Sign-extend from 28 bits
            self.bg2_x &= 0x0FFFFFFF
            if self.bg2_x & 0x08000000:
                self.bg2_x -= 0x10000000
        elif addr == self.REG_BG2Y:
            self.bg2_y = (self.bg2_y & 0xFFFF0000) | (value & 0xFFFF)
        elif addr == self.REG_BG2Y + 2:
            self.bg2_y = (self.bg2_y & 0x0000FFFF) | (value << 16)
            self.bg2_y &= 0x0FFFFFFF
            if self.bg2_y & 0x08000000:
                self.bg2_y -= 0x10000000

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
            self.bg3_x = (self.bg3_x & 0xFFFF0000) | (value & 0xFFFF)
        elif addr == self.REG_BG3X + 2:
            self.bg3_x = (self.bg3_x & 0x0000FFFF) | (value << 16)
            self.bg3_x &= 0x0FFFFFFF
            if self.bg3_x & 0x08000000:
                self.bg3_x -= 0x10000000
        elif addr == self.REG_BG3Y:
            self.bg3_y = (self.bg3_y & 0xFFFF0000) | (value & 0xFFFF)
        elif addr == self.REG_BG3Y + 2:
            self.bg3_y = (self.bg3_y & 0x0000FFFF) | (value << 16)
            self.bg3_y &= 0x0FFFFFFF
            if self.bg3_y & 0x08000000:
                self.bg3_y -= 0x10000000

        # Window registers
        # mGBA layout: low byte = end (right/bottom), high byte = start (left/top)
        elif addr == self.REG_WIN0H:
            self.win0_right = value & 0xFF
            self.win0_left = (value >> 8) & 0xFF
            if self.win0_left > 240 and self.win0_left > self.win0_right:
                self.win0_left = 0
            if self.win0_right > 240:
                self.win0_right = 240
                if self.win0_left > 240:
                    self.win0_left = 240
        elif addr == self.REG_WIN1H:
            self.win1_right = value & 0xFF
            self.win1_left = (value >> 8) & 0xFF
            if self.win1_left > 240 and self.win1_left > self.win1_right:
                self.win1_left = 0
            if self.win1_right > 240:
                self.win1_right = 240
                if self.win1_left > 240:
                    self.win1_left = 240
        elif addr == self.REG_WIN0V:
            self.win0_bottom = value & 0xFF
            self.win0_top = (value >> 8) & 0xFF

        elif addr == self.REG_WIN1V:
            self.win1_bottom = value & 0xFF
            self.win1_top = (value >> 8) & 0xFF
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
            return self.win0_right | (self.win0_left << 8)
        elif addr == self.REG_WIN1H:
            return self.win1_right | (self.win1_left << 8)
        elif addr == self.REG_WIN0V:
            return self.win0_bottom | (self.win0_top << 8)
        elif addr == self.REG_WIN1V:
            return self.win1_bottom | (self.win1_top << 8)
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
                        color_idx = byte_val & 0x0F
                    else:
                        color_idx = (byte_val >> 4) & 0x0F

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
            r = _c5to8((color_val >> 0) & 0x1F)
            g = _c5to8((color_val >> 5) & 0x1F)
            b = _c5to8((color_val >> 10) & 0x1F)
            return (r, g, b)
        except:
            return (0, 0, 0)

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

    def _s178_to_float(self, value: int) -> float:
        """Convert s1.7.8 fixed point to float (16-bit, 256 = 1.0)"""
        if value & 0x8000:
            value = value - 0x10000
        return value / 256.0

    def _is_in_window(self, x: int, y: int, win_num: int) -> bool:
        """Check if coordinate is inside specified window using per-scanline snapshots.
        The Y range is implicit: a scanline only has a snapshot if it falls within
        the window's Y bounds at step_scanline time. The X check is geometric:
        left <= x < right, with GBATEK's left >= right => full width (right=240)."""
        if not (0 <= y < self.screen_height):
            return False
        if win_num == 0:
            snap = self._win0_snapshots[y]
        elif win_num == 1:
            snap = self._win1_snapshots[y]
        else:
            return False
        if snap is None:
            return False
        left, right = snap
        if left >= right:
            return False
        return left <= x < right

    def _is_in_obj_window(self, x: int, y: int) -> bool:
        for sx, sy, w, h in self._obj_window_rects:
            if sy <= y < sy + h and sx <= x < sx + w:
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

        if self.obj_window_enable and self._obj_window_rects:
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

    def _read_registers(self):
        """Read PPU state from MMIO registers before rendering.
        
        This is necessary because the PPU may be created before the ROM
        initializes DISPCNT/BGxCNT, and Memory writes do not notify the PPU.
        """
        if not self.memory:
            return
            
        # DISPCNT
        dispcnt = self.memory.read_u16(self.REG_DISPCNT)
        mode = dispcnt & 0x7
        if mode > 5:
            mode = 5
        self.mode = mode
        self.display_frame_select = (dispcnt >> 4) & 1
        self.hblank_interval_free = bool((dispcnt >> 5) & 1)
        self.obj_character_vram_mapping = bool((dispcnt >> 6) & 1)
        self.forced_blank = bool((dispcnt >> 7) & 1)
        self.bg0_enable = bool((dispcnt >> 8) & 1)
        self.bg1_enable = bool((dispcnt >> 9) & 1)
        self.bg2_enable = bool((dispcnt >> 10) & 1)
        self.bg3_enable = bool((dispcnt >> 11) & 1)
        self.obj_enable = bool((dispcnt >> 12) & 1)
        self.win0_enable = bool((dispcnt >> 13) & 1)
        self.win1_enable = bool((dispcnt >> 14) & 1)
        self.obj_window_enable = bool((dispcnt >> 15) & 1)
        
        # DISPSTAT
        dispstat = self.memory.read_u16(self.REG_DISPSTAT)
        self.lyc = (dispstat >> 8) & 0xFF
        self.vblank_irq_enable = bool((dispstat >> 3) & 1)
        self.hblank_irq_enable = bool((dispstat >> 4) & 1)
        self.vcount_irq_enable = bool((dispstat >> 5) & 1)
        
        # BG Control and scroll registers
        for bg in range(4):
            bg_cnt = self.memory.read_u16(self.REG_BG0CNT + bg * 2)
            self._write_bg_control(bg, bg_cnt)
            self.bg_hofs[bg] = self.memory.read_u16(self.REG_BG0HOFS + bg * 4) & 0x1FF
            self.bg_vofs[bg] = self.memory.read_u16(self.REG_BG0VOFS + bg * 4) & 0x1FF

        # Window geometry registers
        # Window geometry registers (mGBA layout: low byte = end, high byte = start)
        win0h = self.memory.read_u16(self.REG_WIN0H)
        self.win0_right = win0h & 0xFF
        self.win0_left = (win0h >> 8) & 0xFF
        if self.win0_left > 240 and self.win0_left > self.win0_right:
            self.win0_left = 0
        if self.win0_right > 240:
            self.win0_right = 240
            if self.win0_left > 240:
                self.win0_left = 240
        win1h = self.memory.read_u16(self.REG_WIN1H)
        self.win1_right = win1h & 0xFF
        self.win1_left = (win1h >> 8) & 0xFF
        if self.win1_left > 240 and self.win1_left > self.win1_right:
            self.win1_left = 0
        if self.win1_right > 240:
            self.win1_right = 240
            if self.win1_left > 240:
                self.win1_left = 240
        win0v = self.memory.read_u16(self.REG_WIN0V)
        self.win0_bottom = win0v & 0xFF
        self.win0_top = (win0v >> 8) & 0xFF
        win1v = self.memory.read_u16(self.REG_WIN1V)
        self.win1_bottom = win1v & 0xFF
        self.win1_top = (win1v >> 8) & 0xFF
        winin = self.memory.read_u16(self.REG_WININ)
        self.win0_in_enable = winin & 0x3F
        self.win1_in_enable = (winin >> 8) & 0x3F
        winout = self.memory.read_u16(self.REG_WINOUT)

        self.win0_out_enable = winout & 0x1F
        self.win1_out_enable = (winout >> 8) & 0x1F
        self.winout_obj_enable = bool(winout & 0x10)

        # Pre-scan OAM for OBJ window sprites (obj_mode == 3) once per frame
        self._obj_window_rects = []
        if self.obj_window_enable:
            OAM_BASE = 0x07000000
            for sprite_idx in range(128):
                sprite_addr = OAM_BASE + (sprite_idx * 8)
                try:
                    attr0 = self.memory.read_u16(sprite_addr)
                    attr1 = self.memory.read_u16(sprite_addr + 2)
                except Exception:
                    continue
                if ((attr0 >> 10) & 3) != 3:
                    continue
                sy = attr0 & 0xFF
                sx = attr1 & 0x1FF
                h = ((attr0 >> 12) & 7) * 8 + 8
                w = ((attr1 >> 8) & 0x3) * 8 + 8
                if w > 64:
                    w = 64
                if h > 64:
                    h = 64
                self._obj_window_rects.append((sx, sy, w, h))

    def step_scanline(self):
        """Advance one scanline during instruction execution.
        Updates VCount in MMIO, fires HBlank/VBlank DMA and IRQs.
        Called 160+ times per frame by the main loop between instruction batches.
        Does NOT render pixels — use render_frame() for that."""
        if self.vcount == 0:
            self._bg2_affine_snapshots = [None] * self.screen_height
            self._win0_snapshots = [None] * self.screen_height
            self._win1_snapshots = [None] * self.screen_height

        # Per-scanline window snapshot: capture (left, right) from WIN0H/WIN1H
        # for the CURRENT scanline if it falls within the window's Y range.
        # Using the PPU's cached fields (self.win0_top etc.) which are updated
        # from MMIO writes, so mid-frame VCount-IRQ writes to WIN0V/WIN1V
        # take effect on subsequent scanlines.
        # GBATEK: y1 >= y2 means the window covers the full screen (y2=160).
        # GBATEK: left >= right means the window covers the full width (right=240).
        if 0 <= self.vcount < self.screen_height:
            win0_y1, win0_y2 = self.win0_top, self.win0_bottom
            if win0_y1 >= win0_y2:
                win0_y2 = 160
            if win0_y1 <= self.vcount < win0_y2:
                self._win0_snapshots[self.vcount] = (self.win0_left, self.win0_right)

            win1_y1, win1_y2 = self.win1_top, self.win1_bottom
            if win1_y1 >= win1_y2:
                win1_y2 = 160
            if win1_y1 <= self.vcount < win1_y2:
                self._win1_snapshots[self.vcount] = (self.win1_left, self.win1_right)

        # Snapshot BG2 affine params for the CURRENT scanline BEFORE HBlank-DMA
        # modifies them. On hardware the PPU latches the affine matrix at the
        # start of the scanline; HBlank DMA fires later and prepares the
        # value for the NEXT scanline. Capturing before the vcount increment
        # guarantees snapshot[0] is populated.
        if 0 <= self.vcount < self.screen_height:
            try:
                self._bg2_affine_snapshots[self.vcount] = self._read_affine_bg2_params()
            except Exception:
                self._bg2_affine_snapshots[self.vcount] = None

        # Fire HBlank DMA AFTER the snapshot so DMA-written values land in the
        # next scanline's snapshot, not the current one.
        # mGBA (video.c:217) gates GBADMARunHblank on vcount < 160: HBlank DMA
        # fires only on visible scanlines, never during VBlank. Firing during
        # VBlank consumes source values that belong to the next frame's visible
        # lines, shifting per-scanline gradients (bgpd) by ~50 scanlines.
        dma = self.memory._dma
        if dma is not None and self.vcount < self.screen_height:
            dma.hblank_fire(self.vcount)

        self.vcount = (self.vcount + 1) % 228
        self.vblank = self.vcount >= self.screen_height

        io = self.memory.io
        io[6] = self.vcount & 0xFF
        io[7] = 0

        dispstat = io[4] | (io[5] << 8)
        if self.vblank:
            dispstat |= 0x0001
        else:
            dispstat &= ~0x0001
        dispstat |= 0x0002

        lyc = (dispstat >> 8) & 0xFF
        if self.vcount == lyc:
            dispstat |= 0x0004
        else:
            dispstat &= ~0x0004
        io[4] = dispstat & 0xFF
        io[5] = (dispstat >> 8) & 0xFF

        if dma is not None:
            if self.vblank:
                dma.vblank_fire()

        irq = self.memory._interrupts
        if irq is not None:
            if self.vcount == self.screen_height and (dispstat & 0x0008):
                irq.vblank_irq()
            if dispstat & 0x0010:
                irq.hblank_irq()
            if (dispstat & 0x0004) and (dispstat & 0x0020):
                irq.vcounter_irq()

        if self.vblank:
            mod = sys.modules.get("generated_rom")
            if mod is not None:
                mod.z = 1


    def render_frame(self):
        """Render one frame of graphics. Called once per frame after all scanlines."""
        self._read_registers()
        self._init_framebuffer()
        _fc = getattr(self, '_frame_count', 0) + 1
        self._frame_count = _fc
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

        # Render sprites before blending so OBJ can be a blend target
        self._render_sprites()

        # Apply blending if enabled
        if self._blending_enabled():
            self._apply_blending_to_framebuffer()

    def _render_mode0(self):
        """Render Mode 0: Text backgrounds (BG0-3) with priority-based compositing"""
        any_bg = self.bg0_enable or self.bg1_enable or self.bg2_enable or self.bg3_enable
        if not any_bg and not self.obj_enable:
            return

        # Cache BG control registers per BG (avoids per-pixel read_u16)
        bg_enabled = [self.bg0_enable, self.bg1_enable, self.bg2_enable, self.bg3_enable]
        bg_cnt = [0, 0, 0, 0]
        bg_priority = [0, 0, 0, 0]
        bg_bpp8 = [False, False, False, False]
        bg_char_block = [0, 0, 0, 0]
        bg_screen_block = [0, 0, 0, 0]
        for bg in range(4):
            if not bg_enabled[bg]:
                continue
            cnt = self.memory.read_u16(0x04000008 + bg * 2)
            bg_cnt[bg] = cnt
            bg_priority[bg] = cnt & 0x03
            bg_bpp8[bg] = bool((cnt >> 7) & 1)
            bg_char_block[bg] = self.bg_char_block[bg]
            bg_screen_block[bg] = self.bg_screen_block[bg]

        # Tile decode cache: key=(tile_index, char_block, bpp8) → palette_indices list
        tile_cache = {}

        def get_tile(tile_index, char_block, bpp8):
            key = (tile_index, char_block, bpp8)
            cached = tile_cache.get(key)
            if cached is not None:
                return cached
            if bpp8:
                decoded = self._decode_tile_8bpp(tile_index, char_block)
            else:
                decoded = self._decode_tile_4bpp(tile_index, char_block)
            tile_cache[key] = decoded
            return decoded

        # Cache palette colors for speed (palette has 256 entries)
        palette_colors = [self._get_palette_color(i) for i in range(256)]

        # Check if windows are active
        win_active = self.win0_enable or self.win1_enable or self.obj_window_enable

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                if win_active:
                    layer_enable = self._get_window_layer_enable(x, y)
                else:
                    layer_enable = 0x0F  # All BGs enabled

                best_priority = 99
                best_color = None
                best_bg = -1

                for bg in range(4):
                    if not bg_enabled[bg]:
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    mx, my = self._apply_mosaic(x, y, is_obj=False)
                    tile_x = (mx + self.bg_hofs[bg]) % 256
                    tile_y = (my + self.bg_vofs[bg]) % 256

                    screen_block = bg_screen_block[bg]
                    tilemap_base = 0x06000000 + (screen_block * 0x0800)
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x
                    tilemap_addr = tilemap_base + (tilemap_index * 2)

                    tilemap_entry = self.memory.read_u16(tilemap_addr)
                    tile_index = tilemap_entry & 0x03FF
                    palette_bank = (tilemap_entry >> 12) & 0xF
                    h_flip = bool((tilemap_entry >> 10) & 1)
                    v_flip = bool((tilemap_entry >> 11) & 1)

                    pixel_x = tile_x % 8
                    pixel_y = tile_y % 8
                    if h_flip:
                        pixel_x = 7 - pixel_x
                    if v_flip:
                        pixel_y = 7 - pixel_y
                    pixel_index = pixel_y * 8 + pixel_x

                    palette_indices = get_tile(tile_index, bg_char_block[bg], bg_bpp8[bg])
                    if pixel_index >= len(palette_indices):
                        continue
                    color_idx = palette_indices[pixel_index]
                    if color_idx == 0:
                        continue

                    if bg_priority[bg] < best_priority:
                        # Save previous color as second target (it was underneath)
                        if best_color is not None:
                            self.second_target_framebuffer[y][x] = best_color
                            self.second_target_layer[y][x] = best_bg
                        best_priority = bg_priority[bg]
                        if bg_bpp8[bg]:
                            best_color = palette_colors[color_idx]
                        else:
                            best_color = palette_colors[palette_bank * 16 + color_idx]
                        best_bg = bg

                if best_color is not None:
                    self.framebuffer[y][x] = best_color
                    self.layer_origin[y][x] = best_bg

        if self.obj_enable:
            self._render_sprites(0x3F)


    def _render_mode1(self):
        """Render Mode 1: Text BG0/1 + Affine BG2
        
        BG0 and BG1: text-mode (4BPP tiled, same as Mode 0)
        BG2: affine background (256x256 or 512x512 pixels, 8-bit or 4-bit tiles)
        BG3: NOT available in Mode 1
        """
        any_bg = self.bg0_enable or self.bg1_enable or self.bg2_enable
        if not any_bg and not self.obj_enable:
            return

        # Cache BG control registers for BG0/1 (text mode)
        bg_enabled = [self.bg0_enable, self.bg1_enable, self.bg2_enable, False]
        bg_cnt = [0, 0, 0, 0]
        bg_priority = [0, 0, 0, 0]
        bg_bpp8 = [False, False, False, False]
        bg_char_block = [0, 0, 0, 0]
        bg_screen_block = [0, 0, 0, 0]
        bg_hofs = [0, 0, 0, 0]
        bg_vofs = [0, 0, 0, 0]
        
        for bg in range(3):
            if not bg_enabled[bg]:
                continue
            cnt = self.memory.read_u16(0x04000008 + bg * 2)
            bg_cnt[bg] = cnt
            bg_priority[bg] = cnt & 0x03
            bg_bpp8[bg] = bool((cnt >> 7) & 1)
            bg_char_block[bg] = self.bg_char_block[bg]
            bg_screen_block[bg] = self.bg_screen_block[bg]
            bg_hofs[bg] = self.bg_hofs[bg]
            bg_vofs[bg] = self.bg_vofs[bg]

        # Tile decode cache
        tile_cache = {}

        def get_tile(tile_index, char_block, bpp8):
            key = (tile_index, char_block, bpp8)
            cached = tile_cache.get(key)
            if cached is not None:
                return cached
            if bpp8:
                decoded = self._decode_tile_8bpp(tile_index, char_block)
            else:
                decoded = self._decode_tile_4bpp(tile_index, char_block)
            tile_cache[key] = decoded
            return decoded

        palette_colors = [self._get_palette_color(i) for i in range(256)]
        win_active = self.win0_enable or self.win1_enable or self.obj_window_enable

        # Per-scanline affine snapshots for BG2
        snaps = self._bg2_affine_snapshots
        if snaps and snaps[0] is not None:
            _, _, _, _, refx, refy, overflow0 = snaps[0]
        else:
            dx_f, dmx_f, dy_f, dmy_f, refx, refy, overflow0 = self._read_affine_bg2_params()

        sx = refx
        sy = refy

        for y in range(self.screen_height):
            # Get per-scanline affine params for BG2
            if y < len(snaps) and snaps[y] is not None:
                dx, dmx, dy, dmy, _, _, overflow = snaps[y]
            else:
                dx, dmx, dy, dmy, _, _, overflow = self._read_affine_bg2_params()

            row_fb = self.framebuffer[y]
            row_lo = self.layer_origin[y]
            
            for x in range(self.screen_width):
                if win_active:
                    layer_enable = self._get_window_layer_enable(x, y)
                else:
                    layer_enable = 0x0F

                best_priority = 99
                best_color = None
                best_bg = -1

                # Render text BGs (BG0, BG1)
                for bg in [0, 1]:
                    if not bg_enabled[bg]:
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    mx, my = self._apply_mosaic(x, y, is_obj=False)
                    tile_x = (mx + bg_hofs[bg]) % 256
                    tile_y = (my + bg_vofs[bg]) % 256

                    screen_block = bg_screen_block[bg]
                    tilemap_base = 0x06000000 + (screen_block * 0x0800)
                    tilemap_x = tile_x // 8
                    tilemap_y = tile_y // 8
                    tilemap_index = tilemap_y * 32 + tilemap_x
                    tilemap_addr = tilemap_base + (tilemap_index * 2)
                    tilemap_entry = self.memory.read_u16(tilemap_addr)

                    tile_index = tilemap_entry & 0x03FF
                    palette_num = (tilemap_entry >> 12) & 0x0F

                    pixel_x = tile_x % 8
                    pixel_y = tile_y % 8
                    pixel_index = pixel_y * 8 + pixel_x

                    palette_indices = get_tile(tile_index, bg_char_block[bg], bg_bpp8[bg])
                    if pixel_index >= len(palette_indices):
                        continue
                    color_idx = palette_indices[pixel_index]
                    if color_idx == 0:
                        continue

                    if bg_priority[bg] < best_priority:
                        # Save previous color as second target (it was underneath)
                        if best_color is not None:
                            self.second_target_framebuffer[y][x] = best_color
                            self.second_target_layer[y][x] = best_bg
                        best_priority = bg_priority[bg]
                        if bg_bpp8[bg]:
                            best_color = palette_colors[color_idx]
                        else:
                            best_color = palette_colors[palette_num * 16 + color_idx]
                        best_bg = bg

                # Render affine BG2
                if bg_enabled[2] and (layer_enable & 0x04):
                    # Apply affine transformation for BG2
                    x_float = float(x)
                    y_float = float(y)
                    
                    # source_x = refx + (x * dx) + (y * dmx)
                    # source_y = refy + (x * dy) + (y * dmy)
                    source_x = sx + (x_float * dx) + (y_float * dmx)
                    source_y = sy + (x_float * dy) + (y_float * dmy)
                    
                    # Convert to integer coordinates (8.8 fixed point)
                    tx = int(source_x) >> 8
                    ty = int(source_y) >> 8
                    
                    # Handle wrap-around or out-of-bounds
                    if overflow:
                        bg_size = self.bg_size[2]
                        if bg_size == 0:  # 256x256
                            tx &= 255
                            ty &= 255
                        elif bg_size == 1:  # 512x256
                            tx &= 511
                            ty &= 255
                        elif bg_size == 2:  # 256x512
                            tx &= 255
                            ty &= 511
                        else:  # 512x512
                            tx &= 511
                            ty &= 511
                    elif tx < 0 or ty < 0:
                        continue
                    
                    # Get BG2 size for bounds checking
                    bg_size = self.bg_size[2]
                    bg_width = 256 if bg_size in [0, 2] else 512
                    bg_height = 256 if bg_size in [0, 1] else 512
                    
                    if tx >= bg_width or ty >= bg_height:
                        continue

                    # Read tilemap
                    screen_block = bg_screen_block[2]
                    tilemap_base = 0x06000000 + (screen_block * 0x0800)
                    tilemap_x = tx // 8
                    tilemap_y = ty // 8
                    
                    # Handle screen size > 256x256 (tilemap is larger)
                    tilemap_width = 32 if bg_size in [0, 2] else 64
                    tilemap_index = tilemap_y * tilemap_width + tilemap_x
                    tilemap_addr = tilemap_base + (tilemap_index * 2)
                    
                    try:
                        tilemap_entry = self.memory.read_u16(tilemap_addr)
                    except:
                        continue

                    tile_index = tilemap_entry & 0x03FF
                    pixel_x = int(tx) % 8
                    pixel_y = int(ty) % 8
                    pixel_index = pixel_y * 8 + pixel_x

                    palette_indices = get_tile(tile_index, bg_char_block[2], bg_bpp8[2])
                    if pixel_index >= len(palette_indices):
                        continue
                    color_idx = palette_indices[pixel_index]
                    if color_idx == 0:
                        continue

                    if bg_priority[2] < best_priority:
                        # Save previous color as second target (it was underneath)
                        if best_color is not None:
                            self.second_target_framebuffer[y][x] = best_color
                            self.second_target_layer[y][x] = best_bg
                        best_priority = bg_priority[2]
                        if bg_bpp8[2]:
                            best_color = palette_colors[color_idx]
                        else:
                            palette_num = (tilemap_entry >> 12) & 0x0F
                            best_color = palette_colors[palette_num * 16 + color_idx]
                        best_bg = 2

                if best_color is not None:
                    row_fb[x] = best_color
                    row_lo[x] = best_bg

            # Accumulate affine offsets for next scanline
            sx += dmx
            sy += dmy

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _render_mode2(self):
        """Render Mode 2: Affine BG2/3 only
        
        BG2 and BG3: both affine backgrounds
        Same affine parameters as Mode 1's BG2
        BG2 and BG3 can both be affine-transformed independently
        """
        any_bg = self.bg2_enable or self.bg3_enable
        if not any_bg and not self.obj_enable:
            return

        # Cache BG control registers for BG2/3 (both affine)
        bg_enabled = [False, False, self.bg2_enable, self.bg3_enable]
        bg_priority = [0, 0, 0, 0]
        bg_bpp8 = [False, False, False, False]
        bg_char_block = [0, 0, 0, 0]
        bg_screen_block = [0, 0, 0, 0]
        bg_size = [0, 0, 0, 0]
        
        for bg in [2, 3]:
            if not bg_enabled[bg]:
                continue
            cnt = self.memory.read_u16(0x04000008 + bg * 2)
            bg_priority[bg] = cnt & 0x03
            bg_bpp8[bg] = bool((cnt >> 7) & 1)
            bg_char_block[bg] = self.bg_char_block[bg]
            bg_screen_block[bg] = self.bg_screen_block[bg]
            bg_size[bg] = self.bg_size[bg]

        # Tile decode cache
        tile_cache = {}

        def get_tile(tile_index, char_block, bpp8):
            key = (tile_index, char_block, bpp8)
            cached = tile_cache.get(key)
            if cached is not None:
                return cached
            if bpp8:
                decoded = self._decode_tile_8bpp(tile_index, char_block)
            else:
                decoded = self._decode_tile_4bpp(tile_index, char_block)
            tile_cache[key] = decoded
            return decoded

        palette_colors = [self._get_palette_color(i) for i in range(256)]
        win_active = self.win0_enable or self.win1_enable or self.obj_window_enable

        # Per-scanline affine snapshots
        snaps = self._bg2_affine_snapshots
        
        # For BG3, we need to read its affine params separately
        # BG3 uses different registers (BG3PA, BG3PB, etc.)
        def read_affine_bg3_params():
            """Read BG3 affine parameters from MMIO."""
            ap = self.memory._affine_params if hasattr(self.memory, '_affine_params') else None
            
            def _s16(lo, hi):
                v = lo | (hi << 8)
                return v - 0x10000 if v & 0x8000 else v
            
            # Read from BG3 registers directly
            try:
                bg3pa = self.memory.read_u16(0x04000030)
                bg3pb = self.memory.read_u16(0x04000032)
                bg3pc = self.memory.read_u16(0x04000034)
                bg3pd = self.memory.read_u16(0x04000036)
                bg3x_lo = self.memory.read_u16(0x04000038)
                bg3x_hi = self.memory.read_u16(0x0400003A)
                bg3y_lo = self.memory.read_u16(0x0400003C)
                bg3y_hi = self.memory.read_u16(0x0400003E)
                
                dx = _s16(bg3pa & 0xFF, (bg3pa >> 8) & 0xFF)
                dmx = _s16(bg3pb & 0xFF, (bg3pb >> 8) & 0xFF)
                dy = _s16(bg3pc & 0xFF, (bg3pc >> 8) & 0xFF)
                dmy = _s16(bg3pd & 0xFF, (bg3pd >> 8) & 0xFF)
                
                raw_refx = bg3x_lo | (bg3x_hi << 16)
                raw_refy = bg3y_lo | (bg3y_hi << 16)
                
                refx = raw_refx - 0x10000000 if raw_refx & 0x08000000 else raw_refx
                refy = raw_refy - 0x10000000 if raw_refy & 0x08000000 else raw_refy
                
                overflow = self.bg_affine[3]
                return dx, dmx, dy, dmy, refx, refy, overflow
            except:
                return 256, 0, 0, 256, 0, 0, False

        # Frame-start reference positions
        if snaps and snaps[0] is not None:
            _, _, _, _, refx_bg2, refy_bg2, overflow0_bg2 = snaps[0]
        else:
            dx_f, dmx_f, dy_f, dmy_f, refx_bg2, refy_bg2, overflow0_bg2 = self._read_affine_bg2_params()
        
        # BG3 reference position
        _, _, _, _, refx_bg3, refy_bg3, overflow0_bg3 = read_affine_bg3_params()

        sx_bg2 = refx_bg2
        sy_bg2 = refy_bg2
        sx_bg3 = refx_bg3
        sy_bg3 = refy_bg3

        for y in range(self.screen_height):
            # Get per-scanline affine params
            if y < len(snaps) and snaps[y] is not None:
                dx_bg2, dmx_bg2, dy_bg2, dmy_bg2, _, _, overflow_bg2 = snaps[y]
            else:
                dx_bg2, dmx_bg2, dy_bg2, dmy_bg2, _, _, overflow_bg2 = self._read_affine_bg2_params()
            
            dx_bg3, dmx_bg3, dy_bg3, dmy_bg3, _, _, overflow_bg3 = read_affine_bg3_params()

            row_fb = self.framebuffer[y]
            row_lo = self.layer_origin[y]
            
            for x in range(self.screen_width):
                if win_active:
                    layer_enable = self._get_window_layer_enable(x, y)
                else:
                    layer_enable = 0x0F

                best_priority = 99
                best_color = None
                best_bg = -1

                # Render affine BG2
                if bg_enabled[2] and (layer_enable & 0x04):
                    x_float = float(x)
                    y_float = float(y)
                    
                    source_x = sx_bg2 + (x_float * dx_bg2) + (y_float * dmx_bg2)
                    source_y = sy_bg2 + (x_float * dy_bg2) + (y_float * dmy_bg2)
                    
                    tx = int(source_x) >> 8
                    ty = int(source_y) >> 8
                    
                    # Handle wrap-around based on BG2 size
                    if overflow_bg2:
                        size = bg_size[2]
                        if size == 0:  # 256x256
                            tx &= 255
                            ty &= 255
                        elif size == 1:  # 512x256
                            tx &= 511
                            ty &= 255
                        elif size == 2:  # 256x512
                            tx &= 255
                            ty &= 511
                        else:  # 512x512
                            tx &= 511
                            ty &= 511
                    elif tx < 0 or ty < 0:
                        # Out of bounds (negative), skip this pixel
                        tx = -1
                    else:
                        # Check bounds
                        bg_width = 256 if bg_size[2] in [0, 2] else 512
                        bg_height = 256 if bg_size[2] in [0, 1] else 512
                        if tx >= bg_width or ty >= bg_height:
                            tx = -1  # Mark as invalid

                    if tx >= 0:
                        screen_block = bg_screen_block[2]
                        tilemap_base = 0x06000000 + (screen_block * 0x0800)
                        tilemap_x = tx // 8
                        tilemap_y = ty // 8
                        
                        tilemap_width = 32 if bg_size[2] in [0, 2] else 64
                        tilemap_index = tilemap_y * tilemap_width + tilemap_x
                        tilemap_addr = tilemap_base + (tilemap_index * 2)
                        
                        try:
                            tilemap_entry = self.memory.read_u16(tilemap_addr)
                            tile_index = tilemap_entry & 0x03FF
                            pixel_x = int(tx) % 8
                            pixel_y = int(ty) % 8
                            pixel_index = pixel_y * 8 + pixel_x

                            palette_indices = get_tile(tile_index, bg_char_block[2], bg_bpp8[2])
                            if pixel_index < len(palette_indices):
                                color_idx = palette_indices[pixel_index]
                                if color_idx > 0 and bg_priority[2] < best_priority:
                                    best_priority = bg_priority[2]
                                    if bg_bpp8[2]:
                                        best_color = palette_colors[color_idx]
                                    else:
                                        palette_num = (tilemap_entry >> 12) & 0x0F
                                        best_color = palette_colors[palette_num * 16 + color_idx]
                                    best_bg = 2
                        except:
                            # Error reading tilemap, skip this pixel
                            pass

                # Render affine BG3
                if bg_enabled[3] and (layer_enable & 0x08):
                    x_float = float(x)
                    y_float = float(y)
                    
                    source_x = sx_bg3 + (x_float * dx_bg3) + (y_float * dmx_bg3)
                    source_y = sy_bg3 + (x_float * dy_bg3) + (y_float * dmy_bg3)
                    
                    tx = int(source_x) >> 8
                    ty = int(source_y) >> 8
                    
                    # Handle wrap-around based on BG3 size
                    if overflow_bg3:
                        size = bg_size[3]
                        if size == 0:  # 256x256
                            tx &= 255
                            ty &= 255
                        elif size == 1:  # 512x256
                            tx &= 511
                            ty &= 255
                        elif size == 2:  # 256x512
                            tx &= 255
                            ty &= 511
                        else:  # 512x512
                            tx &= 511
                            ty &= 511
                    elif tx < 0 or ty < 0:
                        # Out of bounds (negative), skip this pixel
                        tx = -1
                    else:
                        bg_width = 256 if bg_size[3] in [0, 2] else 512
                        bg_height = 256 if bg_size[3] in [0, 1] else 512
                        if tx >= bg_width or ty >= bg_height:
                            tx = -1

                    if tx >= 0:
                        screen_block = bg_screen_block[3]
                        tilemap_base = 0x06000000 + (screen_block * 0x0800)
                        tilemap_x = tx // 8
                        tilemap_y = ty // 8
                        
                        tilemap_width = 32 if bg_size[3] in [0, 2] else 64
                        tilemap_index = tilemap_y * tilemap_width + tilemap_x
                        tilemap_addr = tilemap_base + (tilemap_index * 2)
                        
                        try:
                            tilemap_entry = self.memory.read_u16(tilemap_addr)
                            tile_index = tilemap_entry & 0x03FF
                            pixel_x = int(tx) % 8
                            pixel_y = int(ty) % 8
                            pixel_index = pixel_y * 8 + pixel_x

                            palette_indices = get_tile(tile_index, bg_char_block[3], bg_bpp8[3])
                            if pixel_index < len(palette_indices):
                                color_idx = palette_indices[pixel_index]
                                if color_idx > 0 and bg_priority[3] < best_priority:
                                    best_priority = bg_priority[3]
                                    if bg_bpp8[3]:
                                        best_color = palette_colors[color_idx]
                                    else:
                                        palette_num = (tilemap_entry >> 12) & 0x0F
                                        best_color = palette_colors[palette_num * 16 + color_idx]
                                    best_bg = 3
                        except:
                            # Error reading tilemap, skip this pixel
                            pass

                if best_color is not None:
                    row_fb[x] = best_color
                    row_lo[x] = best_bg

            # Accumulate affine offsets for next scanline
            sx_bg2 += dmx_bg2
            sy_bg2 += dmy_bg2
            sx_bg3 += dmx_bg3
            sy_bg3 += dmy_bg3

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _read_affine_bg2_params(self):
        """Read and sign-extend BG2 affine parameters from _affine_params.
        Returns (dx, dmx, dy, dmy, refx, refy, overflow).
        Matches mGBA's GBAVideoSoftwareBackground layout.
        """
        ap = self.memory._affine_params

        def _s16(lo, hi):
            v = lo | (hi << 8)
            return v - 0x10000 if v & 0x8000 else v

        dx = _s16(ap[0], ap[1])    # BG2PA: per-pixel X increment
        dmx = _s16(ap[2], ap[3])   # BG2PB: per-scanline X increment
        dy = _s16(ap[4], ap[5])    # BG2PC: per-pixel Y increment
        dmy = _s16(ap[6], ap[7])   # BG2PD: per-scanline Y increment

        raw_refx = (ap[8] | (ap[9] << 8) | (ap[10] << 16) | (ap[11] << 24)) & 0x0FFFFFFF
        refx = raw_refx - 0x10000000 if raw_refx & 0x08000000 else raw_refx
        raw_refy = (ap[12] | (ap[13] << 8) | (ap[14] << 16) | (ap[15] << 24)) & 0x0FFFFFFF
        refy = raw_refy - 0x10000000 if raw_refy & 0x08000000 else raw_refy

        overflow = self.bg_affine[2]
        return dx, dmx, dy, dmy, refx, refy, overflow

    def _render_mode3(self):
        """Render Mode 3: 240x160 16-bit bitmap via affine BG2 transformation.

        mGBA's GBAVideoSoftwareRendererDrawBackgroundMode3 applies the BG2 affine
        matrix per scanline. Per-scanline snapshots captured by step_scanline()
        before HBlank DMA provide the correct dx/dy/dmx/dmy values.
        """
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000
        try:
            vram_arr, vram_off = self.memory._buffer_for_addr(vram_base)
            vram_bytes = bytes(vram_arr[vram_off:vram_off + self.screen_height * self.screen_width * 2])
        except Exception:
            vram_bytes = bytes(self.screen_height * self.screen_width * 2)

        try:
            bdv = self.memory.read_u16(0x05000000)
            backdrop_rgb = (
                _c5to8((bdv >> 0) & 0x1F),
                _c5to8((bdv >> 5) & 0x1F),
                _c5to8((bdv >> 10) & 0x1F),
            )
        except Exception:
            backdrop_rgb = (0, 0, 0)

        snaps = self._bg2_affine_snapshots
        if snaps and snaps[0] is not None:
            _, _, _, _, refx, refy, overflow0 = snaps[0]
        else:
            dx_f, dmx_f, dy_f, dmy_f, refx, refy, overflow0 = self._read_affine_bg2_params()

        fb = self.framebuffer
        lo = self.layer_origin
        sw = self.screen_width
        sh = self.screen_height
        vlen = len(vram_bytes)
        n_snaps = len(snaps)

        # Check if windows are active
        win_active = self.win0_enable or self.win1_enable or self.obj_window_enable

        sx = refx
        sy = refy

        for y in range(sh):
            if y < n_snaps and snaps[y] is not None:
                dx, dmx, dy, dmy, _, _, overflow = snaps[y]
            else:
                dx, dmx, dy, dmy, _, _, overflow = self._read_affine_bg2_params()
            row_fb = fb[y]
            row_lo = lo[y]
            x = sx - dx
            y_coord = sy - dy
            for px in range(sw):
                x += dx
                y_coord += dy
                
                # Apply window masking
                if win_active:
                    layer_enable = self._get_window_layer_enable(px, y)
                    if not (layer_enable & 0x04):  # BG2 bit is 2
                        row_fb[px] = backdrop_rgb
                        row_lo[px] = 0
                        continue
                
                tx = x >> 8
                ty = y_coord >> 8
                if overflow:
                    tx %= sw
                    ty %= sh
                elif tx < 0 or ty < 0 or tx >= sw or ty >= sh:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
                    continue
                offset = (tx + ty * sw) * 2
                if offset + 1 < vlen:
                    color_val = vram_bytes[offset] | (vram_bytes[offset + 1] << 8)
                    row_fb[px] = (
                        _c5to8((color_val >> 0) & 0x1F),
                        _c5to8((color_val >> 5) & 0x1F),
                        _c5to8((color_val >> 10) & 0x1F),
                    )
                    row_lo[px] = 2
                else:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
            sx += dmx
            sy += dmy

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _render_mode4(self):
        """Render Mode 4: 240x160 8BPP bitmap via affine BG2 transformation.

        Same affine pipeline as Mode 3, but pixels are palette-indexed (1 byte each).
        """
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        try:
            vram_arr, vram_off = self.memory._buffer_for_addr(vram_base)
            vram_bytes = bytes(vram_arr[vram_off:vram_off + self.screen_height * self.screen_width])
        except Exception:
            vram_bytes = bytes(self.screen_height * self.screen_width)
        try:
            pal_arr, pal_off = self.memory._buffer_for_addr(0x05000000)
            palette_bytes = bytes(pal_arr[pal_off:pal_off + 512])
        except Exception:
            palette_bytes = bytes(512)
        palette_rgb = []
        for i in range(256):
            cv = palette_bytes[i * 2] | (palette_bytes[i * 2 + 1] << 8)
            palette_rgb.append((
                _c5to8((cv >> 0) & 0x1F),
                _c5to8((cv >> 5) & 0x1F),
                _c5to8((cv >> 10) & 0x1F),
            ))

        # Per-scanline affine snapshots captured by step_scanline() before HBlank-DMA.
        snaps = self._bg2_affine_snapshots
        if snaps and snaps[0] is not None:
            _, _, _, _, refx, refy, overflow0 = snaps[0]
            _ap = snaps[0]

        sx = refx
        sy = refy
        fb = self.framebuffer
        lo = self.layer_origin
        sw = self.screen_width
        sh = self.screen_height
        vlen = len(vram_bytes)
        n_snaps = len(snaps)

        for y in range(sh):
            if y < n_snaps and snaps[y] is not None:
                dx, dmx, dy, dmy, _, _, overflow = snaps[y]
            else:
                dx, dmx, dy, dmy, _, _, overflow = self._read_affine_bg2_params()
            row_fb = fb[y]
            row_lo = lo[y]
            x = sx - dx
            y_coord = sy - dy
            for px in range(sw):
                x += dx
                y_coord += dy
                tx = x >> 8
                ty = y_coord >> 8
                if overflow:
                    tx %= sw
                    ty %= sh
                elif tx < 0 or ty < 0 or tx >= sw or ty >= sh:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
                    continue
                offset = tx + ty * sw
                if offset < vlen:
                    row_fb[px] = palette_rgb[vram_bytes[offset]]
                    row_lo[px] = 2
                else:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
            sx += dmx
            sy += dmy

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _get_palette_color_256(self, palette_idx: int) -> Tuple[int, int, int]:
        """Get RGB color from 256-color palette (Mode 4)."""
        palette_addr = 0x05000000 + (palette_idx * 2)

        try:
            color_val = self.memory.read_u16(palette_addr)
            # On real hardware, palette entry 0 = color 0 = black.
            # Do NOT generate fallback grayscale for uninitialized entries.
            r = _c5to8((color_val >> 0) & 0x1F)
            g = _c5to8((color_val >> 5) & 0x1F)
            b = _c5to8((color_val >> 10) & 0x1F)
            return (r, g, b)
        except:
            return (0, 0, 0)

    def _render_mode5(self):
        """Render Mode 5: 160x128 16-bit bitmap via affine BG2 transformation.

        Bitmap is 160x128 but screen is 240x160. Pixels outside the 160x128
        bitmap region are filled with the backdrop color (palette[0]).
        """
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000
        try:
            vram_arr, vram_off = self.memory._buffer_for_addr(vram_base)
            vram_bytes = bytes(vram_arr[vram_off:vram_off + 128 * 160 * 2])
        except Exception:
            vram_bytes = bytes(128 * 160 * 2)

        try:
            bdv = self.memory.read_u16(0x05000000)
            backdrop_rgb = (
                _c5to8((bdv >> 0) & 0x1F),
                _c5to8((bdv >> 5) & 0x1F),
                _c5to8((bdv >> 10) & 0x1F),
            )
        except Exception:
            backdrop_rgb = (0, 0, 0)

        snaps = self._bg2_affine_snapshots
        if snaps and snaps[0] is not None:
            _, _, _, _, refx, refy, overflow0 = snaps[0]
        else:
            dx_f, dmx_f, dy_f, dmy_f, refx, refy, overflow0 = self._read_affine_bg2_params()

        fb = self.framebuffer
        lo = self.layer_origin
        sw = self.screen_width
        sh = self.screen_height
        bw = 160
        bh = 128
        vlen = len(vram_bytes)
        n_snaps = len(snaps)

        win_active = self.win0_enable or self.win1_enable or self.obj_window_enable

        sx = refx
        sy = refy

        for y in range(sh):
            if y < n_snaps and snaps[y] is not None:
                dx, dmx, dy, dmy, _, _, overflow = snaps[y]
            else:
                dx, dmx, dy, dmy, _, _, overflow = self._read_affine_bg2_params()
            row_fb = fb[y]
            row_lo = lo[y]
            x = sx - dx
            y_coord = sy - dy
            for px in range(sw):
                x += dx
                y_coord += dy

                if win_active:
                    layer_enable = self._get_window_layer_enable(px, y)
                    if not (layer_enable & 0x04):
                        row_fb[px] = backdrop_rgb
                        row_lo[px] = 0
                        continue

                tx = x >> 8
                ty = y_coord >> 8
                if overflow:
                    tx %= bw
                    ty %= bh
                elif tx < 0 or ty < 0 or tx >= bw or ty >= bh:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
                    continue
                offset = (tx + ty * bw) * 2
                if offset + 1 < vlen:
                    color_val = vram_bytes[offset] | (vram_bytes[offset + 1] << 8)
                    row_fb[px] = (
                        _c5to8((color_val >> 0) & 0x1F),
                        _c5to8((color_val >> 5) & 0x1F),
                        _c5to8((color_val >> 10) & 0x1F),
                    )
                    row_lo[px] = 2
                else:
                    row_fb[px] = backdrop_rgb
                    row_lo[px] = 0
            sx += dmx
            sy += dmy

        if self.obj_enable:
            self._render_sprites(0x3F)

    def _blending_enabled(self) -> bool:
        return (self.bldcnt & 0x3FFF) != 0

    def _apply_blending_to_framebuffer(self):
        blend_mode = (self.bldcnt >> 6) & 0x3
        
        if blend_mode == 1:  # Special effect: alpha blend between 1st and 2nd targets
            eva = min(self.bldalpha_eva, 16)
            evb = min(self.bldalpha_evb, 16)
            if eva > 0 or evb > 0:
                # BLDCNT bits 0-5: 1st target (BG0=bit0, BG1=bit1, BG2=bit2, BG3=bit3, OBJ=bit4, BD=bit5)
                # BLDCNT bits 8-13: 2nd target (same mapping)
                first_target_mask = self.bldcnt & 0x3F
                second_target_mask = (self.bldcnt >> 8) & 0x3F
                
                # Read backdrop color for BD (bit 5 of each mask) from palette entry 0
                try:
                    backdrop_color_val = self.memory.read_u16(0x05000000)
                    bg_backdrop_r = _c5to8((backdrop_color_val >> 0) & 0x1F)
                    bg_backdrop_g = _c5to8((backdrop_color_val >> 5) & 0x1F)
                    bg_backdrop_b = _c5to8((backdrop_color_val >> 10) & 0x1F)
                except Exception:
                    bg_backdrop_r, bg_backdrop_g, bg_backdrop_b = 0, 0, 0
                if second_target_mask & (1 << 5):  # BD is 2nd target
                    pass  # backdrop already read above
                
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        source_layer = self.layer_origin[y][x]
                        r, g, b = self.framebuffer[y][x]
                        
                        # Check if this pixel's source layer is in 1st target
                        if (first_target_mask >> source_layer) & 1:
                            # Find 2nd target pixel color
                            second_r, second_g, second_b = bg_backdrop_r, bg_backdrop_g, bg_backdrop_b
                            
                            # Check if 2nd target includes backdrop (BD)
                            if (second_target_mask >> 5) & 1:
                                second_r, second_g, second_b = bg_backdrop_r, bg_backdrop_g, bg_backdrop_b
                            else:
                                # Look for 2nd target layer at this position
                                stf_color = self.second_target_framebuffer[y][x]
                                stf_layer = self.second_target_layer[y][x]
                                if stf_color is not None and ((second_target_mask >> stf_layer) & 1):
                                    second_r, second_g, second_b = stf_color
                            
                            # Apply blend formula: result = (pixel * eva + second_target * evb) / 16
                            r = (r * eva + second_r * evb) // 16
                            g = (g * eva + second_g * evb) // 16
                            b = (b * eva + second_b * evb) // 16
                        
                        self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 2 or blend_mode == 3:  # Brightness up (2) / down (3)
            first_target_mask = self.bldcnt & 0x3F
            if first_target_mask == 0:
                return
            evy = min(self.bldy, 16)
            if evy == 0:
                return
            factor = evy / 16.0
            for y in range(self.screen_height):
                row = self.framebuffer[y]
                origin_row = self.layer_origin[y]
                for x in range(self.screen_width):
                    source_layer = origin_row[x]
                    if not ((first_target_mask >> source_layer) & 1):
                        continue
                    r, g, b = row[x]
                    if blend_mode == 2:
                        r = min(int(r + (255 - r) * factor), 255)
                        g = min(int(g + (255 - g) * factor), 255)
                        b = min(int(b + (255 - b) * factor), 255)
                    else:
                        r = int(r * (1.0 - factor))
                        g = int(g * (1.0 - factor))
                        b = int(b * (1.0 - factor))
                    row[x] = (r, g, b)

    def save_screenshot(self, path: str):
        """Save current framebuffer as screenshot"""
        try:

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

    def _get_sprite_affine_params(self, attr1: int) -> Tuple[int, int, int, int, int, int]:
        """Get affine parameters for sprite from OAM affine parameter table.
        
        attr1 bits 8-10 store the affine parameter table index (0-31).
        Each entry in the table is 8 bytes: PA, PB, PC, PD (16-bit each).
        """
        affine_index = (attr1 >> 8) & 0x1F
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
        """Apply affine transform using s1.7.8 fixed-point parameters."""
        pa_float = self._s178_to_float(pa)
        pb_float = self._s178_to_float(pb)
        pc_float = self._s178_to_float(pc)
        pd_float = self._s178_to_float(pd)
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
            
            # Check double-size flag (attr0 bit 8)
            double_size = bool(attr0 & 0x100)
            if double_size:
                # Double the bounding box dimensions
                sprite_width *= 2
                height *= 2
            
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
            # Check flip flags for normal (non-affine) sprites
            hflip = bool(attr1 & 0x0800)  # bit 12
            vflip = bool(attr1 & 0x1000)  # bit 13
            
            for px in range(width):
                if sprite_x + px < 0 or sprite_x + px >= self.screen_width:
                    colors.append(None)
                    continue
                if line < 0 or line >= self.screen_height:
                    colors.append(None)
                    continue
                
                # Apply horizontal flip
                src_px = width - 1 - px if hflip else px
                
                # Apply vertical flip
                src_line = height - 1 - (line - sprite_y) if vflip else (line - sprite_y)
                
                vram_addr = 0x06014000 + (src_line * width + src_px) * 2
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


# === End of ppu.py ===


# === Start of dma.py ===




DMA_ENABLE         = 0x8000  # bit 15
DMA_IRQ_ENABLE     = 0x4000  # bit 14
DMA_TIMING_MASK    = 0x3000  # bits 13-12
DMA_TIMING_IMMEDIATE = 0x0000
DMA_TIMING_VBLANK    = 0x1000
DMA_TIMING_HBLANK     = 0x2000
DMA_TIMING_SPECIAL    = 0x3000
DMA_DRQ            = 0x0800  # bit 11 (DMA3 only)
DMA_32BIT          = 0x0400  # bit 10
DMA_REPEAT          = 0x0200  # bit 9
DMA_SRC_CTRL_MASK   = 0x0180  # bits 8-7
DMA_DST_CTRL_MASK   = 0x0060  # bits 6-5

DMA_CHANNEL_SPACING = 0x0C

DMA0_SRC_ADDR = 0x040000B0
DMA1_SRC_ADDR = 0x040000BC
DMA2_SRC_ADDR = 0x040000C8
DMA3_SRC_ADDR = 0x040000D4

# DMA_OFFSET[] = { +1, -1, 0, +1 } — matches mGBA dma.c
# Indexed by SrcControl/DestControl value:
#   0=increment, 1=decrement, 2=fixed, 3=reload(same as increment during transfer)
_DMA_OFFSET = {0: 1, 1: -1, 2: 0, 3: 1}


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
        self._orig_src = 0
        self._orig_dst = 0
        self._orig_count = 0
        self.latch: int = 0
    def attach_interrupts(self, interrupts):
        self._interrupts = interrupts

    @property
    def irq_enabled(self) -> bool:
        return (self.control & DMA_IRQ_ENABLE) != 0

    def _timing_bits(self) -> int:
        return (self.control >> 12) & 0x3

    def is_immediate(self) -> bool:
        return self._timing_bits() == 0

    def is_vblank(self) -> bool:
        return self._timing_bits() == 1

    def is_hblank(self) -> bool:
        return self._timing_bits() == 2

    def is_special(self) -> bool:
        return self._timing_bits() == 3

    def get_src_increment(self) -> int:
        return (self.control >> 7) & 0x3

    def get_dst_increment(self) -> int:
        return (self.control >> 5) & 0x3

    def is_32bit(self) -> bool:
        return (self.control & DMA_32BIT) != 0

    def is_repeat(self) -> bool:
        return (self.control & DMA_REPEAT) != 0

    def get_transfer_size(self) -> int:
        return 4 if self.is_32bit() else 2

    def _base(self) -> int:
        return 0x040000B0 + (self.channel_id * DMA_CHANNEL_SPACING)

    def read_from_memory(self):
        b = self._base() - 0x04000000
        new_control = self.mem.io[b+10] | (self.mem.io[b+11] << 8)
        new_enabled = (new_control & DMA_ENABLE) != 0

        if new_enabled and not self.enabled:
            self.src_addr = self.mem.io[b] | (self.mem.io[b+1] << 8) | (self.mem.io[b+2] << 16) | (self.mem.io[b+3] << 24)
            self.dst_addr = self.mem.io[b+4] | (self.mem.io[b+5] << 8) | (self.mem.io[b+6] << 16) | (self.mem.io[b+7] << 24)
            self.count = self.mem.io[b+8] | (self.mem.io[b+9] << 8)
            self._orig_src = self.src_addr
            self._orig_dst = self.dst_addr
            self._orig_count = self.count
        elif not new_enabled:
            self.src_addr = self.mem.io[b] | (self.mem.io[b+1] << 8) | (self.mem.io[b+2] << 16) | (self.mem.io[b+3] << 24)
            self.dst_addr = self.mem.io[b+4] | (self.mem.io[b+5] << 8) | (self.mem.io[b+6] << 16) | (self.mem.io[b+7] << 24)
            self.count = self.mem.io[b+8] | (self.mem.io[b+9] << 8)

        self.control = new_control
        self.enabled = new_enabled

    def _write_control_to_memory(self):
        b = self._base() - 0x04000000
        self.mem.io[b+10] = self.control & 0xFF
        self.mem.io[b+11] = (self.control >> 8) & 0xFF

    def write_to_memory(self):
        b = self._base() - 0x04000000
        self.mem.io[b] = self.src_addr & 0xFF
        self.mem.io[b+1] = (self.src_addr >> 8) & 0xFF
        self.mem.io[b+2] = (self.src_addr >> 16) & 0xFF
        self.mem.io[b+3] = (self.src_addr >> 24) & 0xFF
        self.mem.io[b+4] = self.dst_addr & 0xFF
        self.mem.io[b+5] = (self.dst_addr >> 8) & 0xFF
        self.mem.io[b+6] = (self.dst_addr >> 16) & 0xFF
        self.mem.io[b+7] = (self.dst_addr >> 24) & 0xFF
        self.mem.io[b+8] = self.count & 0xFF
        self.mem.io[b+9] = (self.count >> 8) & 0xFF
        self.mem.io[b+10] = self.control & 0xFF
        self.mem.io[b+11] = (self.control >> 8) & 0xFF

    def get_count_value(self) -> int:
        if self.count == 0:
            return 0x10000 if self.is_32bit() else 0x4000
        return self.count


class DMA:
    """GBA DMA Controller with 4 channels"""

    FIFO_A_ADDR = 0x040000A0
    FIFO_B_ADDR = 0x040000A4

    def __init__(self):
        self.mem = None
        self._interrupts = None
        self._apu = None
        self.channels: List[DMAChannel] = [
            DMAChannel(0, None),
            DMAChannel(1, None),
            DMAChannel(2, None),
            DMAChannel(3, None),
        ]

    def attach_memory(self, mem):
        self.mem = mem
        for ch in self.channels:
            ch.mem = mem

    def attach_apu(self, apu):
        self._apu = apu

    def attach_interrupts(self, interrupts):
        self._interrupts = interrupts
        for ch in self.channels:
            ch.attach_interrupts(interrupts)

    def fifo_a_is_empty(self) -> bool:
        if self._apu is None:
            return False
        return len(self._apu.fifo_a.data) == 0

    def fifo_b_is_empty(self) -> bool:
        if self._apu is None:
            return False
        return len(self._apu.fifo_b.data) == 0

    def start_transfer(self, channel: int):
        if not 0 <= channel <= 3:
            return
        ch = self.channels[channel]
        ch.read_from_memory()
        if not ch.enabled:
            return
        self._do_transfer(ch)

    def _step_for(self, ctrl: int, width: int) -> int:
        return _DMA_OFFSET.get(ctrl, 0) * width

    def _do_transfer(self, ch: DMAChannel):
        if ch.busy:
            return

        ch.busy = True

        src_ctrl = ch.get_src_increment()
        dst_ctrl = ch.get_dst_increment()
        count = ch.get_count_value()
        transfer_size = ch.get_transfer_size()

        src_step = self._step_for(src_ctrl, transfer_size)
        dst_step = self._step_for(dst_ctrl, transfer_size)

        src = ch.src_addr
        dst = ch.dst_addr
        orig_dst = ch.dst_addr
        orig_src = ch.src_addr

        for _ in range(count):
            if transfer_size == 4:
                if src >= 0x02000000:
                    ch.latch = self.mem.read_u32(src)
                value = ch.latch
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
            else:
                if src >= 0x02000000:
                    ch.latch = self.mem.read_u16(src)
                    ch.latch = ch.latch | (ch.latch << 16)
                value = (ch.latch >> (8 * (dst & 2))) & 0xFFFF
                if dst == DMA.FIFO_A_ADDR and self._apu:
                    self._apu.fifo_a.write(value & 0xFF)
                    self._apu.fifo_a.write((value >> 8) & 0xFF)
                elif dst == DMA.FIFO_B_ADDR and self._apu:
                    self._apu.fifo_b.write(value & 0xFF)
                    self._apu.fifo_b.write((value >> 8) & 0xFF)
                else:
                    self.mem.write_u16(dst, value)

            src += src_step
            dst += dst_step

        if ch.is_repeat() and dst_ctrl == 3:
            ch.dst_addr = orig_dst
        else:
            ch.dst_addr = dst
        if ch.is_repeat() and src_ctrl == 3:
            ch.src_addr = orig_src
        else:
            ch.src_addr = src

        if ch.is_repeat():
            ch.count = ch._orig_count if ch._orig_count else ch.get_count_value()
            if ch.is_repeat() and src_ctrl == 3:
                ch.src_addr = orig_src
            if ch.is_repeat() and dst_ctrl == 3:
                ch.dst_addr = orig_dst
        else:
            ch.control &= ~DMA_ENABLE
            ch.enabled = False
            ch._write_control_to_memory()

        ch.busy = False
        ch.pending = False

        if ch.irq_enabled and self._interrupts:
            self._interrupts.dma_irq(ch.channel_id)

    def step(self):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_immediate():
                if ch.pending:
                    ch.pending = False
                    self._do_transfer(ch)

    def _do_transfer_single(self, ch: DMAChannel):
        """Transfer one unit, advance src/dst, keep channel enabled.

        Per GBATEK, HBlank/VBlank DMA with the Repeat bit transfers a single
        unit per trigger (not the full count at once). The channel stays enabled
        until count is exhausted, then reloads if Repeat is set or disables.
        """
        if ch.busy:
            return
        ch.busy = True

        src_ctrl = ch.get_src_increment()
        dst_ctrl = ch.get_dst_increment()
        transfer_size = ch.get_transfer_size()
        src_step = self._step_for(src_ctrl, transfer_size)
        dst_step = self._step_for(dst_ctrl, transfer_size)

        src = ch.src_addr
        dst = ch.dst_addr

        if transfer_size == 4:
            if src >= 0x02000000:
                ch.latch = self.mem.read_u32(src)
            value = ch.latch
            if dst == DMA.FIFO_A_ADDR and self._apu:
                self._apu.fifo_a.write(value & 0xFF)
                self._apu.fifo_a.write((value >> 8) & 0xFF)
                self._apu.fifo_a.write((value >> 16) & 0xFF)
                self._apu.fifo_a.write((value >> 24) & 0xFF)
            elif dst == DMA.FIFO_B_ADDR and self._apu:
                self._apu.fifo_b.write(value & 0xFF)
                self._apu.fifo_b.write((value >> 8) & 0xFF)
                self._apu.fifo_b.write((value >> 16) & 0xFF)
                self._apu.fifo_b.write((value >> 24) & 0xFF)
            else:
                self.mem.write_u32(dst, value)
        else:
            if src >= 0x02000000:
                ch.latch = self.mem.read_u16(src)
                ch.latch = ch.latch | (ch.latch << 16)
            value = (ch.latch >> (8 * (dst & 2))) & 0xFFFF
            if dst == DMA.FIFO_A_ADDR and self._apu:
                self._apu.fifo_a.write(value & 0xFF)
                self._apu.fifo_a.write((value >> 8) & 0xFF)
            elif dst == DMA.FIFO_B_ADDR and self._apu:
                self._apu.fifo_b.write(value & 0xFF)
                self._apu.fifo_b.write((value >> 8) & 0xFF)
            else:
                self.mem.write_u16(dst, value)
        ch.src_addr = src + src_step
        ch.dst_addr = dst + dst_step
        ch.count = max(0, ch.count - 1)

        if ch.count == 0:
            if ch.is_repeat():
                ch.count = ch._orig_count if ch._orig_count else 0x10000
                if dst_ctrl == 3:
                    ch.dst_addr = ch._orig_dst
                if src_ctrl == 3:
                    ch.src_addr = ch._orig_src
            else:
                ch.control &= ~DMA_ENABLE
                ch.enabled = False
                ch._write_control_to_memory()

        ch.busy = False
        ch.pending = False

        if ch.irq_enabled and self._interrupts:
            self._interrupts.dma_irq(ch.channel_id)

    def vblank_fire(self):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_vblank():
                self._do_transfer(ch)

    def hblank_fire(self, vcount: int = 0):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_hblank():
                self._do_transfer(ch)

    def custom_fire(self):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_special() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def timer_trigger(self, timer_index: int):
        for ch in self.channels:
            ch.read_from_memory()
            if not ch.enabled or ch.busy:
                continue
            if ch.is_special() and ch.pending:
                self._do_transfer(ch)
                ch.pending = False

    def fifo_a_empty_fire(self):
        ch = self.channels[1]
        ch.read_from_memory()
        if ch.enabled and not ch.busy and ch.is_special() and ch.pending:
            self._do_transfer(ch)
            ch.pending = False

    def fifo_b_empty_fire(self):
        ch = self.channels[2]
        ch.read_from_memory()
        if ch.enabled and not ch.busy and ch.is_special() and ch.pending:
            self._do_transfer(ch)
            ch.pending = False

    def fifo_a_step(self):
        if not self._apu:
            return
        self._apu.fifo_a.timer += 1
        if self._apu.fifo_a.timer >= self._apu.fifo_a.timer_period:
            self._apu.fifo_a.timer = 0
            self._apu.fifo_a.read()

    def get_channel(self, channel: int) -> Optional[DMAChannel]:
        if 0 <= channel <= 3:
            return self.channels[channel]
        return None


def clear_dma_pending(dma_instance):
    for ch in dma_instance.channels:
        ch.pending = False


# === End of dma.py ===


# === Start of arm7tdmi.py ===



try:
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

_NUMBA_ENABLED = False

_MODE_TO_SPSR_IDX = {0x10: 0, 0x1F: 1, 0x13: 2, 0x17: 3, 0x1B: 4, 0x11: 5, 0x12: 6}
_MODES_WITH_SPSR = frozenset({0x11, 0x12, 0x13, 0x17, 0x1B})


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
        self.spsr = [0] * 7  # Saved PSR for each mode (USR, SYS, SVC, ABT, UND, FIQ, IRQ)

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
        self.running = True
        self.cycles = 0
        self._halted = False
        self._halt_reason = None

        # Banked SP/LR per mode (FIQ also banks r8-r12)
        # User (0x10) and System (0x1F) share the same register bank
        _user_sys_bank = {'sp': 0, 'lr': 0}
        self.banked_sp_lr = {
            0x10: _user_sys_bank,  # User
            0x1F: _user_sys_bank,  # System
            0x11: {'sp': 0, 'lr': 0, 'r8': 0, 'r9': 0, 'r10': 0, 'r11': 0, 'r12': 0},  # FIQ
            0x12: {'sp': 0, 'lr': 0},  # IRQ
            0x13: {'sp': 0, 'lr': 0},  # SVC
            0x17: {'sp': 0, 'lr': 0},  # ABT
            0x1B: {'sp': 0, 'lr': 0},  # UND
        }

        # Initialize BIOS for SWI handlers
        self.bios = BIOS(self.memory)

    def _switch_mode(self, new_mode: int):
        """Swap banked SP/LR (and r8-r12 for FIQ) on mode change."""
        old_mode = self.mode
        if new_mode == old_mode:
            return

        # Save outgoing mode's banked registers
        if old_mode in self.banked_sp_lr:
            bank = self.banked_sp_lr[old_mode]
            bank['sp'] = self.registers[13]
            bank['lr'] = self.registers[14]
            if old_mode == 0x11:  # FIQ banks r8-r12
                bank['r8'] = self.registers[8]
                bank['r9'] = self.registers[9]
                bank['r10'] = self.registers[10]
                bank['r11'] = self.registers[11]
                bank['r12'] = self.registers[12]

        # Load incoming mode's banked registers
        if new_mode in self.banked_sp_lr:
            bank = self.banked_sp_lr[new_mode]
            self.registers[13] = bank['sp']
            self.registers[14] = bank['lr']
            if new_mode == 0x11:  # FIQ banks r8-r12
                self.registers[8] = bank['r8']
                self.registers[9] = bank['r9']
                self.registers[10] = bank['r10']
                self.registers[11] = bank['r11']
                self.registers[12] = bank['r12']

        self.mode = new_mode

    @property
    def r(self):
        return self.registers

    @property
    def thumb_mode(self) -> bool:
        return bool((self.cpsr >> 5) & 1)

    @thumb_mode.setter
    def thumb_mode(self, value: bool):
        if value:
            self.cpsr |= (1 << 5)
        else:
            self.cpsr &= ~(1 << 5)

    @property
    def pc(self) -> int:
        return self.registers[15]

    @pc.setter
    def pc(self, value: int):
        if value & 1:
            self.thumb_mode = True
            self.registers[15] = value & 0xFFFFFFFE
        else:
            self.registers[15] = value & (0xFFFFFFFE if self.thumb_mode else 0xFFFFFFFC)

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
            if value & 1:
                self.thumb_mode = True
                self.registers[15] = value & 0xFFFFFFFE
            else:
                self.registers[15] = value & (0xFFFFFFFE if self.thumb_mode else 0xFFFFFFFC)

    def _operand(self, reg: int) -> int:
        """Read a register as an instruction operand.

        R15 has a visible value of PC+8 in ARM mode and PC+4 in Thumb mode
        because of the 3-stage pipeline: when the current instruction at PC
        is executing, the fetch for PC+8 (ARM) is already in flight. Reading
        R15 directly returns the fetch address, so operand reads must add the
        pipeline offset.
        """
        if (reg & 0xF) == 15:
            offset = 4 if self.thumb_mode else 8
            return (self.registers[15] + offset) & 0xFFFFFFFF
        return self.registers[reg & 0xF]

    @jit_compile
    def step(self) -> int:
        if self.thumb_mode:
            return self.step_thumb()
        return self.step_arm()

    @jit_compile
    def step_arm(self) -> int:
        pc = self.pc
        instr = self.memory.read_u32(pc)
        cond = (instr >> 28) & 0xF

        if not self.check_condition(cond):
            self.registers[15] += 4
            return 1

        return self.execute_arm(instr)

    @jit_compile
    def step_thumb(self) -> int:
        pc = self.pc
        instr = self.memory.read_u16(pc)
        return self.execute_thumb(instr)

    @jit_compile
    def execute_arm(self, instr: int) -> int:
        opcode = (instr >> 21) & 0xF
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        rm = instr & 0xF

        if (instr & 0x0FFFFFF0) == 0x012FFF10:
            return self.exec_bx(instr)

        if (instr & 0x0C000000) == 0:
            is_immediate = (instr >> 25) & 1
            if not is_immediate:
                op_lo = instr & 0xF0
                if op_lo == 0x90:
                    return self.exec_mul(instr)
                if op_lo == 0xB0 or op_lo == 0xD0 or op_lo == 0xF0:
                    return self.exec_extra_load_store(instr)
            return self.exec_data_processing(instr)

        if (instr & 0xC000000) == 0x4000000:
            return self.exec_load_store(instr)

        if (instr & 0xE000000) == 0xA000000:
            return self.exec_branch(instr)

        if (instr & 0xE000000) == 0x8000000:
            return self.exec_block_transfer(instr)

        if (instr & 0xF000000) == 0xF000000:
            return self.exec_swi(instr)

        return 1

    def _exec_status_transfer(self, instr: int, rd: int) -> int:
        """Execute MSR (write PSR) or MRS (read PSR).

        Encoding overlaps with TST/TEQ/CMP/CMN when S=0:
          - Rd == 15 (Rn field == 15 in disassembly) -> MSR: write masked fields
          - Rn == 15 (rd field == 15)                  -> MRS: read PSR to Rd

        Field mask (bits 19:16 of instr):
          bit 19 = f -> update N,Z,C,V (bits 31:28)
          bit 18 = s -> reserved (bits 23:16)
          bit 17 = x -> reserved (bits 15:8)
          bit 16 = c -> update mode,I,F,T (bits 7:0)
        """
        is_mrs = (rd == 15)  # Rn field holds the mask for MSR; Rd field == 15 means MRS
        # In our encoding MSR has Rd==15 (Rn in standard form), MRS has Rn==15.
        # Re-derive cleanly: MSR is selected when bit 21 (opcode bit) is 0x2 AND Rn != 15.
        rn = (instr >> 16) & 0xF
        rd_field = (instr >> 12) & 0xF
        # MRS: 00010?001111???????1111????????
        #   - Rn field = 1111? No: MRS has Rn=1111 (15) and Rd != 15.
        # MSR (reg): 00010?10?1111????1111????????
        #   - Rd field = 1111 (15), Rn field = mask.
        # MSR (imm): 00110010?1111????1111????????
        #   - Rd field = 1111 (15), Rn field = mask.
        is_msr = (rd_field == 15)

        if not is_msr and rn == 15:
            # MRS: Rd <- CPSR (or SPSR if bit 22 set)
            psr_sel = (instr >> 22) & 1
            if psr_sel:
                mode_idx = _MODE_TO_SPSR_IDX.get(self.mode, 0)
                psr = self.spsr[mode_idx] if 0 <= mode_idx < len(self.spsr) else 0
            else:
                psr = self.cpsr
            self.registers[rd_field] = psr & 0xFFFFFFFF
            self.registers[15] = (self.registers[15] + 4) & 0xFFFFFFFF
            return 1

        # MSR: compute operand
        imm = (instr >> 25) & 1
        if imm:
            imm_val = instr & 0xFF
            rot = ((instr >> 8) & 0xF) * 2
            if rot:
                imm_val = ((imm_val >> rot) | (imm_val << (32 - rot))) & 0xFFFFFFFF
            operand = imm_val
        else:
            rm = instr & 0xF
            operand = self.registers[rm & 0xF] & 0xFFFFFFFF

        # Field mask from bits 19:16
        mask_f = (rn >> 3) & 1  # bit 19
        mask_s = (rn >> 2) & 1  # bit 18
        mask_x = (rn >> 1) & 1  # bit 17
        mask_c = (rn >> 0) & 1  # bit 16

        psr_sel = (instr >> 22) & 1
        if psr_sel:
            mode_idx = {0x10: 0, 0x1F: 1, 0x13: 2, 0x17: 3, 0x1A: 4, 0x11: 5}.get(self.mode, 0)
            target = self.spsr[mode_idx] if 0 <= mode_idx < 6 else 0
            write_back_spsr = True
        else:
            target = self.cpsr
            write_back_spsr = False

        new_psr = target
        if mask_f:
            new_psr = (new_psr & 0x0FFFFFFF) | (operand & 0xF0000000)
        if mask_s:
            new_psr = (new_psr & 0xFF00FFFF) | (operand & 0x00FF0000)
        if mask_x:
            new_psr = (new_psr & 0xFFFF00FF) | (operand & 0x0000FF00)
        if mask_c:
            new_psr = (new_psr & 0xFFFFFF00) | (operand & 0x000000FF)

        if write_back_spsr:
            self.spsr[mode_idx] = new_psr & 0xFFFFFFFF
        else:
            self.cpsr = new_psr & 0xFFFFFFFF
            # Apply mode and Thumb state from control field
            self.mode = new_psr & 0x1F
            self.thumb_mode = bool((new_psr >> 5) & 1)

        self.registers[15] = (self.registers[15] + 4) & 0xFFFFFFFF
        return 1

    @jit_compile
    def exec_data_processing(self, instr: int) -> int:
        """Execute ARM data processing instruction."""
        opcode = (instr >> 21) & 0xF
        s_bit = (instr >> 20) & 1
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        rm = instr & 0xF

        # MSR/MRS: test opcodes (TST=8, TEQ=9, CMP=A, CMN=B) with S=0
        # are status register transfers, not arithmetic tests.
        # Rd=15 → MSR (write PSR), Rn=15 → MRS (read PSR).
        if opcode in (8, 9, 0xA, 0xB) and s_bit == 0:
            return self._exec_status_transfer(instr, rd)

        shifter_carry = (self.cpsr >> 29) & 1

        # Check for immediate
        imm = (instr >> 25) & 1
        if imm:
            imm_val = instr & 0xFF
            rot = ((instr >> 8) & 0xF) * 2
            if rot:
                imm_val = ((imm_val >> rot) | (imm_val << (32 - rot))) & 0xFFFFFFFF
                shifter_carry = (imm_val >> 31) & 1
            operand2 = imm_val
        else:
            shift_type = (instr >> 5) & 3
            shift_imm = (instr >> 7) & 0x1F
            operand2 = self._operand(rm)
            if shift_imm:
                if shift_type == 0:  # LSL
                    shifter_carry = (operand2 >> (32 - shift_imm)) & 1
                    operand2 = (operand2 << shift_imm) & 0xFFFFFFFF
                elif shift_type == 1:  # LSR
                    shifter_carry = (operand2 >> (shift_imm - 1)) & 1
                    operand2 = operand2 >> shift_imm
                elif shift_type == 2:  # ASR
                    shifter_carry = (operand2 >> (shift_imm - 1)) & 1
                    operand2 = (operand2 >> shift_imm) | (
                        (operand2 & 0x80000000) * (0xFFFFFFFF >> (32 - shift_imm))
                    )
                elif shift_type == 3:  # ROR
                    shifter_carry = (operand2 >> (shift_imm - 1)) & 1
                    operand2 = (
                        (operand2 >> shift_imm) | (operand2 << (32 - shift_imm))
                    ) & 0xFFFFFFFF
            else:
                if shift_type == 1:  # LSR #0 means LSR #32
                    shifter_carry = (operand2 >> 31) & 1
                    operand2 = 0
                elif shift_type == 2:  # ASR #0 means ASR #32
                    shifter_carry = (operand2 >> 31) & 1
                    operand2 = 0xFFFFFFFF if (operand2 & 0x80000000) else 0
                elif shift_type == 3:  # ROR #0 means RRX
                    carry = (self.cpsr >> 29) & 1
                    shifter_carry = operand2 & 1
                    operand2 = ((carry << 31) | (operand2 >> 1)) & 0xFFFFFFFF

        operand1 = self._operand(rn)

        is_test = opcode in (8, 9, 0xA, 0xB)
        is_arithmetic = opcode in (2, 3, 4, 5, 6, 7, 0xA, 0xB)
        update_flags = s_bit or is_test
        alu_carry = shifter_carry
        alu_overflow = (self.cpsr >> 28) & 1

        if opcode == 0:  # AND
            result = operand1 & operand2
            self.write_register(rd, result)
        elif opcode == 1:  # EOR
            result = operand1 ^ operand2
            self.write_register(rd, result)
        elif opcode == 2:  # SUB
            result = (operand1 - operand2) & 0xFFFFFFFF
            alu_carry = 1 if operand1 >= operand2 else 0
            alu_overflow = 1 if ((operand1 ^ operand2) & (operand1 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 3:  # RSB
            result = (operand2 - operand1) & 0xFFFFFFFF
            alu_carry = 1 if operand2 >= operand1 else 0
            alu_overflow = 1 if ((operand2 ^ operand1) & (operand2 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 4:  # ADD
            raw = operand1 + operand2
            result = raw & 0xFFFFFFFF
            alu_carry = 1 if raw > 0xFFFFFFFF else 0
            alu_overflow = 1 if ((operand1 ^ result) & (operand2 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 5:  # ADC
            c = (self.cpsr >> 29) & 1
            raw = operand1 + operand2 + c
            result = raw & 0xFFFFFFFF
            alu_carry = 1 if raw > 0xFFFFFFFF else 0
            alu_overflow = 1 if ((operand1 ^ result) & (operand2 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 6:  # SBC
            c = (self.cpsr >> 29) & 1
            result = (operand1 - operand2 - (1 - c)) & 0xFFFFFFFF
            alu_carry = 1 if (operand1 >= operand2 + (1 - c)) else 0
            alu_overflow = 1 if ((operand1 ^ operand2) & (operand1 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 7:  # RSC
            c = (self.cpsr >> 29) & 1
            result = (operand2 - operand1 - (1 - c)) & 0xFFFFFFFF
            alu_carry = 1 if (operand2 >= operand1 + (1 - c)) else 0
            alu_overflow = 1 if ((operand2 ^ operand1) & (operand2 ^ result) & 0x80000000) else 0
            self.write_register(rd, result)
        elif opcode == 8:  # TST
            result = operand1 & operand2
        elif opcode == 9:  # TEQ
            result = operand1 ^ operand2
        elif opcode == 0xA:  # CMP
            result = (operand1 - operand2) & 0xFFFFFFFF
            alu_carry = 1 if operand1 >= operand2 else 0
            alu_overflow = 1 if ((operand1 ^ operand2) & (operand1 ^ result) & 0x80000000) else 0
        elif opcode == 0xB:  # CMN
            raw = operand1 + operand2
            result = raw & 0xFFFFFFFF
            alu_carry = 1 if raw > 0xFFFFFFFF else 0
            alu_overflow = 1 if ((operand1 ^ result) & (operand2 ^ result) & 0x80000000) else 0
        elif opcode == 0xC:  # ORR
            result = operand1 | operand2
            self.write_register(rd, result)
        elif opcode == 0xD:  # MOV
            result = operand2
            self.write_register(rd, result)
        elif opcode == 0xE:  # BIC
            result = operand1 & (~operand2 & 0xFFFFFFFF)
            self.write_register(rd, result)
        elif opcode == 0xF:  # MVN
            result = (~operand2) & 0xFFFFFFFF
            self.write_register(rd, result)

        if update_flags:
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            if is_arithmetic:
                c = alu_carry
                v = alu_overflow
            else:
                c = shifter_carry
                v = (self.cpsr >> 28) & 1
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)

        if rd != 15:
            self.registers[15] += 4
        elif update_flags:
            # SUBS/MOVS PC, Rm — exception return: restore CPSR from SPSR.
            # Only privileged modes have an SPSR; User/System mode leaves CPSR unchanged.
            if self.mode in _MODES_WITH_SPSR:
                _idx = _MODE_TO_SPSR_IDX.get(self.mode, -1)
                if 0 <= _idx < len(self.spsr):
                    new_cpsr = self.spsr[_idx] & 0xFFFFFFFF
                    new_mode = new_cpsr & 0x1F
                    self._switch_mode(new_mode)
                    self.cpsr = new_cpsr
                    self.mode = new_mode

        return 1

    @jit_compile
    def exec_load_store(self, instr: int) -> int:
        is_load = (instr >> 20) & 1
        is_byte = (instr >> 22) & 1
        is_up = (instr >> 23) & 1
        p_bit = (instr >> 24) & 1
        w_bit = (instr >> 21) & 1
        is_imm = not ((instr >> 25) & 1)
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF

        base = self._operand(rn)

        if is_imm:
            offset = instr & 0xFFF
        else:
            rm = instr & 0xF
            shift_type = (instr >> 5) & 3
            shift_imm = (instr >> 7) & 0x1F
            offset = self._operand(rm)
            if shift_imm:
                if shift_type == 0:
                    offset = (offset << shift_imm) & 0xFFFFFFFF
                elif shift_type == 1:
                    offset = offset >> shift_imm
                elif shift_type == 2:
                    offset = (offset >> shift_imm) | ((offset & 0x80000000) * (0xFFFFFFFF >> (32 - shift_imm)))
                elif shift_type == 3:
                    offset = ((offset >> shift_imm) | (offset << (32 - shift_imm))) & 0xFFFFFFFF

        eff_offset = offset if is_up else -offset

        if p_bit:
            addr = (base + eff_offset) & 0xFFFFFFFF
        else:
            addr = base

        if is_load:
            if is_byte:
                val = self.memory.read_u8(addr)
            else:
                val = self.memory.read_u32(addr)
            self.write_register(rd, val)
        else:
            val = self._operand(rd)
            if is_byte:
                self.memory.write_u8(addr, val & 0xFF)
            else:
                self.memory.write_u32(addr, val)

        if w_bit or not p_bit:
            if rn != 15:
                self.registers[rn] = (base + eff_offset) & 0xFFFFFFFF

        if rd != 15:
            self.registers[15] += 4
        return 2

    @jit_compile
    def exec_extra_load_store(self, instr: int) -> int:
        p_bit = (instr >> 24) & 1
        is_up = (instr >> 23) & 1
        is_imm = (instr >> 22) & 1
        w_bit = (instr >> 21) & 1
        is_load = (instr >> 20) & 1
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        sh = (instr >> 5) & 0x3

        base = self._operand(rn)

        if is_imm:
            imm_hi = (instr >> 8) & 0xF
            imm_lo = instr & 0xF
            offset = (imm_hi << 4) | imm_lo
        else:
            rm = instr & 0xF
            offset = self._operand(rm)

        eff_offset = offset if is_up else -offset

        if p_bit:
            addr = (base + eff_offset) & 0xFFFFFFFF
        else:
            addr = base

        if not is_load:
            val = self._operand(rd)
            self.memory.write_u16(addr, val & 0xFFFF)
        else:
            if sh == 1:
                val = self.memory.read_u16(addr)
            elif sh == 2:
                val = self.memory.read_u8(addr)
                if val & 0x80:
                    val |= 0xFFFFFF00
            elif sh == 3:
                val = self.memory.read_u16(addr)
                if val & 0x8000:
                    val |= 0xFFFF0000
            else:
                val = 0
            self.write_register(rd, val)

        if w_bit or not p_bit:
            if rn != 15:
                self.registers[rn] = (base + eff_offset) & 0xFFFFFFFF

        if rd != 15:
            self.registers[15] = (self.registers[15] + 4) & 0xFFFFFFFF
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
        self.registers[15] = ((self.registers[15] + 8) + offset) & 0xFFFFFFFF
        return 3

    def exec_bx(self, instr: int) -> int:
        """Execute BX instruction."""
        rm = instr & 0xF
        target = self._operand(rm)
        self.thumb_mode = (target & 1) != 0
        self.registers[15] = target & 0xFFFFFFFE
        return 3

    def exec_block_transfer(self, instr: int) -> int:
        """Execute LDM/STM instruction.
        ARM encoding:
          bits 24: P (pre/post index)
          bit  23: U (up/down)
          bit  22: S (force user mode, or restore CPSR on LDM PC^)
          bit  21: W (writeback)
          bit  20: L (load/store)
          bits 19-16: Rn (base)
          bits 15-0:  register list
        """
        p_bit = (instr >> 24) & 1
        is_up = (instr >> 23) & 1
        s_bit = (instr >> 22) & 1
        is_load = (instr >> 20) & 1
        w_bit = (instr >> 21) & 1
        rn = (instr >> 16) & 0xF
        reg_list = instr & 0xFFFF

        if reg_list == 0:
            return 2

        base = self._operand(rn)
        n_regs = bin(reg_list).count('1')

        # Compute start address honoring pre/post index
        # ARM addressing modes (P=pre/post, U=up/down):
        #   IA (P=0,U=1): start at base, increment after each access
        #   IB (P=1,U=1): start at base+4, increment after each access
        #   DA (P=0,U=0): start at base-4*(n-1), increment after each access
        #   DB (P=1,U=0): start at base-4*n, increment after each access
        if p_bit:
            if is_up:
                addr = base + 4
            else:
                addr = base - 4 * n_regs
        else:
            if is_up:
                addr = base
            else:
                addr = base - 4 * (n_regs - 1)

        if is_load:
            for i in range(16):
                if reg_list & (1 << i):
                    val = self.memory.read_u32(addr)
                    self.write_register(i, val)
                    addr += 4
        else:
            for i in range(16):
                if reg_list & (1 << i):
                    val = self._operand(i)
                    self.memory.write_u32(addr, val & 0xFFFFFFFF)
                    addr += 4

        if w_bit:
            if is_up:
                self.registers[rn] = (base + n_regs * 4) & 0xFFFFFFFF
            else:
                self.registers[rn] = (base - n_regs * 4) & 0xFFFFFFFF

        if not (is_load and (reg_list & (1 << 15))):
            self.registers[15] += 4
        elif s_bit and self.mode in _MODES_WITH_SPSR:
            # LDM ... PC^: exception return — restore CPSR from SPSR.
            _idx = _MODE_TO_SPSR_IDX.get(self.mode, -1)
            if 0 <= _idx < len(self.spsr):
                new_cpsr = self.spsr[_idx] & 0xFFFFFFFF
                new_mode = new_cpsr & 0x1F
                self._switch_mode(new_mode)
                self.cpsr = new_cpsr
                self.mode = new_mode
        return 2 + (n_regs * 2)

    @jit_compile
    def exec_mul(self, instr: int) -> int:
        rm = instr & 0xF
        rs = (instr >> 8) & 0xF
        rd = (instr >> 16) & 0xF
        result = (self._operand(rm) * self._operand(rs)) & 0xFFFFFFFF
        self.write_register(rd, result)
        self.registers[15] += 4
        return 2

    def exec_swi(self, instr: int) -> int:
        """Execute SWI (software interrupt).
        GBA BIOS extracts the SWI number from bits 23:16 of the 24-bit
        comment field (mGBA: immediate >> 16)."""
        swi_num = (instr >> 16) & 0xFF
        self.swi_handler(swi_num)
        self.registers[15] += 4
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
        
        SWI exception entry (ARM hardware behavior):
        - Save CPSR to SPSR_svc
        - Save PC+4 to LR_svc (return address after SWI)
        - Switch to SVC mode (0x13) with IRQ disabled (I bit set)
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
        elif num == 0x02:  # Halt — wake on ANY enabled IRQ
            # SWI exception entry: save state and switch to SVC mode
            self._swi_exception_entry()
            self._halted = True
            self._halt_reason = 'any'
        elif num == 0x03:  # Stop
            if hasattr(self, 'bios') and self.bios is not None:
                self.bios.swi_stop(self.registers[0])
        elif num == 0x04:  # IntrWait — wake on ANY enabled IRQ
            # SWI exception entry: save state and switch to SVC mode
            self._swi_exception_entry()
            self._halted = True
            self._halt_reason = 'any'
        elif num == 0x05:  # VBlankIntrWait — wake on VBlank IRQ only
            # SWI exception entry: save state and switch to SVC mode
            self._swi_exception_entry()
            self._halted = True
            self._halt_reason = 'vblank'
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
                self.bios.swi_cpufastset(self.registers[0], self.registers[1], self.registers[2], self.registers[2])
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

    def _swi_exception_entry(self):
        """Model ARM SWI exception entry.
        
        On SWI execution, real ARM hardware:
        1. Saves current CPSR to SPSR_svc
        2. Saves PC+4 to LR_svc (return address)
        3. Switches to SVC mode (0x13) with IRQ disabled (I bit set)
        
        This ensures that when an IRQ fires during SWI (e.g., during halt),
        the CPU has proper SVC-mode state, and IRQ entry can correctly
        save to IRQ banked registers without corrupting the SWI return address.
        
        Note: PC at this point is still the SWI instruction address. The caller
        (exec_swi) will increment PC by 4 after the handler returns.
        """
        # Save current CPSR to SPSR_svc (index 2 for mode 0x13)
        svc_spsr_idx = 2  # _MODE_TO_SPSR_IDX[0x13]
        self.spsr[svc_spsr_idx] = self.cpsr
        
        # Save return address to LR_svc
        # In ARM mode: return = PC + 4 (pipeline offset)
        # In Thumb mode: return = PC + 4 (SWI is 2 bytes, but return is PC+4)
        # At this point, PC is the SWI instruction address
        if self.thumb_mode:
            # Thumb SWI is 2 bytes, but exception return is PC+4
            return_addr = (self.registers[15] + 4) & 0xFFFFFFFF
        else:
            # ARM SWI is 4 bytes, return is PC+4
            return_addr = (self.registers[15] + 4) & 0xFFFFFFFF
        self.banked_sp_lr[0x13]['lr'] = return_addr
        
        # Switch to SVC mode (0x13)
        # The I bit (bit 7) should be set to disable IRQs, but we keep it simple
        self.cpsr = (self.cpsr & ~0x1F) | 0x13  # Set mode bits to 0x13 (SVC)
        
        # Perform mode switch to load SVC banked registers
        self._switch_mode(0x13)

    def execute_thumb(self, instr: int) -> int:
        """Execute Thumb instruction.

        Dispatch matches the ThumbDecoder format table in
        crates/gbatopy-disasm/src/thumb/mod.rs (instr >> 8 → format ranges).
        """
        op = instr >> 8  # bits 15-8

        if op <= 0x17:  # format 1: LSL/LSR/ASR Rd, Rs, #Offset5
            return self.exec_thumb_move_shift(instr)
        elif op <= 0x1F:  # format 2: ADD/SUB Rd, Rs, Rn/#Imm3
            return self.exec_thumb_add_sub(instr)
        elif op <= 0x3F:  # format 3: MOV/CMP/ADD/SUB Rd, #Imm8
            return self.exec_thumb_imm3(instr)
        elif op <= 0x43:  # format 4: ALU operations
            return self.exec_thumb_alu(instr)
        elif op <= 0x47:  # format 5: Hi register operations / BX
            return self.exec_thumb_hi(instr)
        elif op <= 0x4F:  # format 6: LDR Rd, [PC, #Imm8*4]
            return self.exec_thumb_pc_rel(instr)
        elif op <= 0x5F:  # format 7: Load/store with register offset
            return self.exec_thumb_load_store(instr)
        elif op <= 0x77:  # format 9: Load/store with immediate offset (word/byte)
            return self.exec_thumb_load_store_imm(instr)
        elif op <= 0x7F:  # format 10: Load/store halfword with immediate offset
            return self.exec_thumb_load_store_imm(instr)
        elif op <= 0x8F:  # format 9: Load/store with immediate offset (cont.)
            return self.exec_thumb_load_store_imm(instr)
        elif op <= 0x9F:  # format 11: Load/store SP-relative
            return self.exec_thumb_sp_rel(instr)
        elif op <= 0xAF:  # format 12: Load address (PC or SP + Imm8*4)
            return self.exec_thumb_load_addr(instr)
        elif op == 0xB0:  # format 13: ADD SP, #Imm7*4
            return self.exec_thumb_add_sp(instr)
        elif op <= 0xB5:  # format 14: PUSH {reglist, LR}
            return self.exec_thumb_push_pop(instr)
        elif op <= 0xBD:  # format 14: POP {reglist, PC}
            return self.exec_thumb_push_pop(instr)
        elif op <= 0xCF:  # format 15: LDM/STM
            return self.exec_thumb_ldm_stm(instr)
        elif op <= 0xDF:  # format 16: Conditional branch (cond 0xE) or SWI (cond 0xF)
            if (instr >> 8) == 0xDF:
                return self.exec_thumb_swi(instr)
            return self.exec_thumb_cond_branch(instr)
        elif op <= 0xEF:  # format 18: Unconditional branch
            return self.exec_thumb_branch(instr)
        elif op <= 0xF7:  # format 19: BL prefix
            return self.exec_thumb_bl_prefix(instr)
        else:  # 0xF8-0xFF: format 19: BL suffix
            return self.exec_thumb_bl_suffix(instr)

    def exec_thumb_move_shift(self, instr: int) -> int:
        """Thumb move shifted register (format 1: LSL/LSR/ASR Rd, Rs, #Offset5). Sets N, Z, C."""
        op = (instr >> 11) & 3
        offset = (instr >> 6) & 0x1F
        rs = (instr >> 3) & 7
        rd = instr & 7
        val = self.registers[rs]
        c = (self.cpsr >> 29) & 1
        if op == 0:  # LSL
            if offset == 0:
                result = val
            else:
                c = (val >> (32 - offset)) & 1
                result = (val << offset) & 0xFFFFFFFF
        elif op == 1:  # LSR
            if offset == 0:
                offset = 32
            c = (val >> (offset - 1)) & 1
            result = val >> offset
        elif op == 2:  # ASR
            if offset == 0:
                offset = 32
            c = (val >> (offset - 1)) & 1
            if val & 0x80000000:
                result = (val >> offset) | ((0xFFFFFFFF << (32 - offset)) & 0xFFFFFFFF)
            else:
                result = val >> offset
        self.write_register(rd, result)
        n = (result >> 31) & 1
        z = 1 if result == 0 else 0
        v = (self.cpsr >> 28) & 1
        self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        self.registers[15] += 2
        return 1

    def exec_thumb_add_sub(self, instr: int) -> int:
        """Thumb ADD/SUB (format 2). Sets N, Z, C, V."""
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
            c = 1 if op1 >= offset else 0
            v = 1 if ((op1 ^ offset) & (op1 ^ result) & 0x80000000) else 0
        else:
            result = (op1 + offset) & 0xFFFFFFFF
            c = 1 if result < op1 else 0
            v = 1 if ((~(op1 ^ offset) & 0xFFFFFFFF) & (op1 ^ result) & 0x80000000) else 0

        self.write_register(rd, result)
        n = (result >> 31) & 1
        z = 1 if result == 0 else 0
        self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        self.registers[15] += 2
        return 1

    def exec_thumb_imm3(self, instr: int) -> int:
        """Thumb MOV/CMP/ADD/SUB Rd, #Imm8 (format 3). All set N, Z; ADD/SUB/CMP also set C, V."""
        op = (instr >> 11) & 3  # bits 12-11
        rd = (instr >> 8) & 7   # bits 10-8
        imm8 = instr & 0xFF     # bits 7-0

        if op == 0:  # MOV Rd, #Imm8
            result = imm8 & 0xFFFFFFFF
            self.write_register(rd, result)
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            c = (self.cpsr >> 29) & 1
            v = (self.cpsr >> 28) & 1
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        elif op == 1:  # CMP Rd, #Imm8
            op1 = self.registers[rd]
            result = (op1 - imm8) & 0xFFFFFFFF
            c = 1 if op1 >= imm8 else 0
            v = 1 if ((op1 ^ imm8) & (op1 ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        elif op == 2:  # ADD Rd, #Imm8
            op1 = self.registers[rd]
            result = (op1 + imm8) & 0xFFFFFFFF
            self.write_register(rd, result)
            c = 1 if result < op1 else 0
            v = 1 if ((~(op1 ^ imm8) & 0xFFFFFFFF) & (op1 ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        elif op == 3:  # SUB Rd, #Imm8
            op1 = self.registers[rd]
            result = (op1 - imm8) & 0xFFFFFFFF
            self.write_register(rd, result)
            c = 1 if op1 >= imm8 else 0
            v = 1 if ((op1 ^ imm8) & (op1 ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)

        self.registers[15] += 2
        return 1

    def exec_thumb_alu(self, instr: int) -> int:
        """Thumb ALU operations. All set N and Z; arithmetic/shift ops also set C and V."""
        op = (instr >> 6) & 0xF
        rs = (instr >> 3) & 7
        rd = instr & 7

        val = self.registers[rs]
        rd_val = self.registers[rd]

        c = (self.cpsr >> 29) & 1
        v = (self.cpsr >> 28) & 1

        if op == 0:  # AND
            result = rd_val & val
        elif op == 1:  # EOR
            result = rd_val ^ val
        elif op == 2:  # LSL
            shift = val & 0xFF
            if shift == 0:
                result = rd_val
            elif shift < 32:
                c = (rd_val >> (32 - shift)) & 1
                result = (rd_val << shift) & 0xFFFFFFFF
            elif shift == 32:
                c = rd_val & 1
                result = 0
            else:
                c = 0
                result = 0
        elif op == 3:  # LSR
            shift = val & 0xFF
            if shift == 0:
                result = rd_val
            elif shift < 32:
                c = (rd_val >> (shift - 1)) & 1
                result = rd_val >> shift
            elif shift == 32:
                c = (rd_val >> 31) & 1
                result = 0
            else:
                c = 0
                result = 0
        elif op == 4:  # ASR
            shift = val & 0xFF
            if shift == 0:
                result = rd_val
            elif shift < 32:
                c = (rd_val >> (shift - 1)) & 1
                if rd_val & 0x80000000:
                    result = (rd_val >> shift) | ((0xFFFFFFFF << (32 - shift)) & 0xFFFFFFFF)
                else:
                    result = rd_val >> shift
            else:
                c = (rd_val >> 31) & 1
                result = 0xFFFFFFFF if rd_val & 0x80000000 else 0
        elif op == 5:  # ADC
            carry_in = (self.cpsr >> 29) & 1
            raw = rd_val + val + carry_in
            result = raw & 0xFFFFFFFF
            c = 1 if raw > 0xFFFFFFFF else 0
            v = 1 if ((rd_val ^ result) & (val ^ result) & 0x80000000) else 0
        elif op == 6:  # SBC
            carry_in = (self.cpsr >> 29) & 1
            not_c = 1 - carry_in
            result = (rd_val - val - not_c) & 0xFFFFFFFF
            c = 1 if rd_val >= (val + not_c) else 0
            v = 1 if ((rd_val ^ val) & (rd_val ^ result) & 0x80000000) else 0
        elif op == 7:  # ROR
            shift = val & 0x1F
            if shift == 0:
                c = (rd_val >> 31) & 1
                result = rd_val
            else:
                result = ((rd_val >> shift) | (rd_val << (32 - shift))) & 0xFFFFFFFF
                c = (rd_val >> (shift - 1)) & 1
        elif op == 8:  # TST
            result = rd_val & val
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
            self.registers[15] += 2
            return 1
        elif op == 9:  # NEG (RSB Rd, Rs, #0)
            result = (0 - val) & 0xFFFFFFFF
            c = 1 if val == 0 else 0
            v = 1 if (val & result & 0x80000000) else 0
        elif op == 0xA:  # CMP
            result = (rd_val - val) & 0xFFFFFFFF
            c = 1 if rd_val >= val else 0
            v = 1 if ((rd_val ^ val) & (rd_val ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
            self.registers[15] += 2
            return 1
        elif op == 0xB:  # CMN
            raw = rd_val + val
            result = raw & 0xFFFFFFFF
            c = 1 if raw > 0xFFFFFFFF else 0
            v = 1 if ((rd_val ^ result) & (val ^ result) & 0x80000000) else 0
            n = (result >> 31) & 1
            z = 1 if result == 0 else 0
            self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
            self.registers[15] += 2
            return 1
        elif op == 0xC:  # ORR
            result = rd_val | val
        elif op == 0xD:  # MUL
            result = (rd_val * val) & 0xFFFFFFFF
        elif op == 0xE:  # BIC
            result = rd_val & (~val & 0xFFFFFFFF)
        else:  # 0xF: MVN
            result = (~val) & 0xFFFFFFFF

        self.write_register(rd, result)
        n = (result >> 31) & 1
        z = 1 if result == 0 else 0
        self.cpsr = (self.cpsr & 0x0FFFFFFF) | (n << 31) | (z << 30) | (c << 29) | (v << 28)
        self.registers[15] += 2
        return 1

    def exec_thumb_hi(self, instr: int) -> int:
        """Thumb hi register operations/BX."""
        op = (instr >> 8) & 3
        rs = (instr >> 3) & 7
        rd = (instr >> 0) & 7
        h1 = (instr >> 7) & 1
        h2 = (instr >> 6) & 1

        if op == 3 and h1 == 0:  # BX
            rm_reg = rs + (h2 << 3)
            target = self._operand(rm_reg)
            self.thumb_mode = (target & 1) != 0
            self.registers[15] = target & 0xFFFFFFFE
            return 1

        rdn = rd + (h1 << 3)
        rm = rs + (h2 << 3)

        if op == 0:  # ADD
            result = (self._operand(rdn) + self._operand(rm)) & 0xFFFFFFFF
            self.write_register(rdn, result)
        elif op == 1:  # CMP
            result = (self._operand(rdn) - self._operand(rm)) & 0xFFFFFFFF
            self.cpsr = (
                (self.cpsr & 0x0FFFFFFF)
                | ((result >> 31) << 28)
                | (0 if result == 0 else (1 << 30))
            )
        elif op == 2:  # MOV
            self.write_register(rdn, self._operand(rm))

        self.registers[15] += 2
        return 1

    def exec_thumb_pc_rel(self, instr: int) -> int:
        """Thumb PC-relative load."""
        rd = (instr >> 8) & 7
        offset = (instr & 0xFF) * 4
        addr = ((self.registers[15] + 4) & 0xFFFFFFFC) + offset
        val = self.memory.read_u32(addr)
        self.write_register(rd, val)
        self.registers[15] += 2
        return 2

    def exec_thumb_load_store(self, instr: int) -> int:
        """Thumb load/store with register offset (formats 7+8).

        Opcode bits 11-9 select the access type:
        000=STR, 001=STRH, 010=STRB, 011=LDSB, 100=LDR, 101=LDSH, 110=LDRB, 111=LDRH
        """
        op = (instr >> 9) & 7   # bits 11-9
        ro = (instr >> 6) & 7   # bits 8-6
        rb = (instr >> 3) & 7   # bits 5-3
        rd = instr & 7          # bits 2-0

        addr = (self.registers[rb] + self.registers[ro]) & 0xFFFFFFFF

        if op == 0:    # STR Rd, [Rb, Ro]
            self.memory.write_u32(addr, self.registers[rd])
        elif op == 1:  # STRH Rd, [Rb, Ro]
            self.memory.write_u16(addr, self.registers[rd] & 0xFFFF)
        elif op == 2:  # STRB Rd, [Rb, Ro]
            self.memory.write_u8(addr, self.registers[rd] & 0xFF)
        elif op == 3:  # LDSB Rd, [Rb, Ro] (sign-extended byte)
            val = self.memory.read_u8(addr)
            if val & 0x80:
                val |= 0xFFFFFF00
            self.write_register(rd, val)
        elif op == 4:  # LDR Rd, [Rb, Ro]
            self.write_register(rd, self.memory.read_u32(addr))
        elif op == 5:  # LDSH Rd, [Rb, Ro] (sign-extended halfword)
            val = self.memory.read_u16(addr)
            if val & 0x8000:
                val |= 0xFFFF0000
            self.write_register(rd, val)
        elif op == 6:  # LDRB Rd, [Rb, Ro]
            self.write_register(rd, self.memory.read_u8(addr))
        elif op == 7:  # LDRH Rd, [Rb, Ro]
            self.write_register(rd, self.memory.read_u16(addr))

        self.registers[15] += 2
        return 2

    def exec_thumb_load_store_imm(self, instr: int) -> int:
        """Thumb load/store with immediate offset (formats 9+10).

        Bits 15-11 select the access type:
        01100=STR word, 01101=LDR word, 01110=STRB, 01111=LDRB,
        10000=STRH, 10001=LDRH
        """
        op = (instr >> 11) & 0x1F  # bits 15-11
        imm5 = (instr >> 6) & 0x1F  # bits 10-6
        rb = (instr >> 3) & 7       # bits 5-3
        rd = instr & 7              # bits 2-0

        if op == 0b01100:  # STR Rd, [Rb, #Imm5*4]
            addr = self.registers[rb] + imm5 * 4
            self.memory.write_u32(addr, self.registers[rd])
        elif op == 0b01101:  # LDR Rd, [Rb, #Imm5*4]
            addr = self.registers[rb] + imm5 * 4
            self.write_register(rd, self.memory.read_u32(addr))
        elif op == 0b01110:  # STRB Rd, [Rb, #Imm5]
            addr = self.registers[rb] + imm5
            self.memory.write_u8(addr, self.registers[rd] & 0xFF)
        elif op == 0b01111:  # LDRB Rd, [Rb, #Imm5]
            addr = self.registers[rb] + imm5
            self.write_register(rd, self.memory.read_u8(addr))
        elif op == 0b10000:  # STRH Rd, [Rb, #Imm5*2]
            addr = self.registers[rb] + imm5 * 2
            self.memory.write_u16(addr, self.registers[rd] & 0xFFFF)
        elif op == 0b10001:  # LDRH Rd, [Rb, #Imm5*2]
            addr = self.registers[rb] + imm5 * 2
            self.write_register(rd, self.memory.read_u16(addr))

        self.registers[15] += 2
        return 2

    def exec_thumb_sp_rel(self, instr: int) -> int:
        """Thumb load/store SP-relative (format 11)."""
        is_load = (instr >> 11) & 1  # bit 11: 0=STR, 1=LDR
        rd = (instr >> 8) & 7        # bits 10-8
        imm8 = instr & 0xFF          # bits 7-0
        addr = (self.registers[13] + imm8 * 4) & 0xFFFFFFFF

        if is_load:
            self.write_register(rd, self.memory.read_u32(addr))
        else:
            self.memory.write_u32(addr, self.registers[rd])

        self.registers[15] += 2
        return 2

    def exec_thumb_load_addr(self, instr: int) -> int:
        """Thumb load address (format 12): ADD Rd, PC/SP, #Imm8*4."""
        use_sp = (instr >> 11) & 1  # bit 11: 0=PC, 1=SP
        rd = (instr >> 8) & 7       # bits 10-8
        imm8 = instr & 0xFF         # bits 7-0

        if use_sp:
            addr = (self.registers[13] + imm8 * 4) & 0xFFFFFFFF
        else:
            # Thumb PC reads as current instruction + 4
            pc = (self.registers[15] + 4) & 0xFFFFFFFF
            addr = ((pc & 0xFFFFFFFC) + imm8 * 4) & 0xFFFFFFFF
        self.write_register(rd, addr)
        self.registers[15] += 2
        return 1

    def exec_thumb_add_sp(self, instr: int) -> int:
        """Thumb add/sub offset to SP (format 13)."""
        sign = (instr >> 7) & 1  # bit 7: 0=ADD, 1=SUB
        imm7 = instr & 0x7F       # bits 6-0
        if sign:
            self.registers[13] = (self.registers[13] - imm7 * 4) & 0xFFFFFFFF
        else:
            self.registers[13] = (self.registers[13] + imm7 * 4) & 0xFFFFFFFF
        self.registers[15] += 2
        return 1

    def exec_thumb_push_pop(self, instr: int) -> int:
        """Thumb push/pop registers (format 14)."""
        op8 = (instr >> 8) & 0xFF
        is_pop = op8 in (0xBC, 0xBD)
        with_extra = op8 in (0xB5, 0xBD)  # LR for push, PC for pop
        reg_list = instr & 0xFF  # bits 7-0

        if is_pop:
            addr = self.registers[13]
            for i in range(8):
                if reg_list & (1 << i):
                    self.write_register(i, self.memory.read_u32(addr))
                    addr += 4
            if with_extra:
                val = self.memory.read_u32(addr)
                addr += 4
                self.thumb_mode = (val & 1) != 0
                self.registers[15] = val & 0xFFFFFFFE
                # Exception return from a privileged mode: restore CPSR from SPSR.
                if self.mode in _MODES_WITH_SPSR:
                    _idx = _MODE_TO_SPSR_IDX.get(self.mode, -1)
                    if 0 <= _idx < len(self.spsr):
                        new_cpsr = self.spsr[_idx] & 0xFFFFFFFF
                        new_mode = new_cpsr & 0x1F
                        self._switch_mode(new_mode)
                        self.cpsr = new_cpsr
                        self.mode = new_mode
                        self.thumb_mode = (new_cpsr >> 5) & 1
            else:
                self.registers[15] += 2
            self.registers[13] = addr
            return 2
        else:
            count = bin(reg_list).count('1') + (1 if with_extra else 0)
            addr = (self.registers[13] - count * 4) & 0xFFFFFFFF
            self.registers[13] = addr
            for i in range(8):
                if reg_list & (1 << i):
                    self.memory.write_u32(addr, self.registers[i])
                    addr += 4
            if with_extra:
                self.memory.write_u32(addr, self.registers[14])  # LR
            self.registers[15] += 2
            return 2

    def exec_thumb_ldm_stm(self, instr: int) -> int:
        """Thumb LDM/STM (format 15)."""
        is_load = (instr >> 11) & 1  # bit 11: 0=STM, 1=LDM
        rb = (instr >> 8) & 7        # bits 10-8
        reg_list = instr & 0xFF      # bits 7-0

        if reg_list == 0:
            self.registers[15] += 2
            return 1

        addr = self.registers[rb]
        for i in range(8):
            if reg_list & (1 << i):
                if is_load:
                    self.write_register(i, self.memory.read_u32(addr))
                else:
                    self.memory.write_u32(addr, self.registers[i])
                addr += 4
        self.registers[rb] = addr  # write back

        self.registers[15] += 2
        return 2

    def _check_condition(self, cond: int) -> bool:
        """Check ARM condition code."""
        n = (self.cpsr >> 31) & 1
        z = (self.cpsr >> 30) & 1
        c = (self.cpsr >> 29) & 1
        v = (self.cpsr >> 28) & 1

        if cond == 0x0:   # EQ
            return z == 1
        elif cond == 0x1: # NE
            return z == 0
        elif cond == 0x2: # CS/HS
            return c == 1
        elif cond == 0x3: # CC/LO
            return c == 0
        elif cond == 0x4: # MI
            return n == 1
        elif cond == 0x5: # PL
            return n == 0
        elif cond == 0x6: # VS
            return v == 1
        elif cond == 0x7: # VC
            return v == 0
        elif cond == 0x8: # HI
            return c == 1 and z == 0
        elif cond == 0x9: # LS
            return c == 0 or z == 1
        elif cond == 0xA: # GE
            return n == v
        elif cond == 0xB: # LT
            return n != v
        elif cond == 0xC: # GT
            return n == v and z == 0
        elif cond == 0xD: # LE
            return n != v or z == 1
        elif cond == 0xE: # AL
            return True
        return False       # NV

    def exec_thumb_cond_branch(self, instr: int) -> int:
        """Thumb conditional branch (format 16)."""
        cond = (instr >> 8) & 0xF  # bits 11-8
        offset = instr & 0xFF      # bits 7-0
        if offset & 0x80:
            offset -= 0x100
        offset *= 2

        if self._check_condition(cond):
            self.registers[15] = ((self.registers[15] + 4) + offset) & 0xFFFFFFFF
        else:
            self.registers[15] += 2
        return 2

    def exec_thumb_branch(self, instr: int) -> int:
        """Thumb unconditional branch (format 18)."""
        offset = instr & 0x7FF  # bits 10-0
        if offset & 0x400:
            offset -= 0x800
        offset *= 2
        self.registers[15] = ((self.registers[15] + 4) + offset) & 0xFFFFFFFF
        return 2

    def exec_thumb_bl_prefix(self, instr: int) -> int:
        """Thumb BL prefix (format 19)."""
        offset_high = instr & 0x7FF  # bits 10-0
        if offset_high & 0x400:
            offset_high -= 0x800
        offset_high <<= 12
        # Thumb PC reads as current instruction + 4
        pc = (self.registers[15] + 4) & 0xFFFFFFFF
        self.registers[14] = (pc + offset_high) & 0xFFFFFFFF
        self.registers[15] += 2
        return 1

    def exec_thumb_bl_suffix(self, instr: int) -> int:
        """Thumb BL suffix (format 19)."""
        offset_low = (instr & 0x7FF) << 1  # bits 10-0, *2
        target = (self.registers[14] + offset_low) & 0xFFFFFFFF
        # Return address = next instruction with Thumb bit set
        self.registers[14] = (self.registers[15] + 2) | 1
        self.registers[15] = target
        return 2

    def exec_thumb_swi(self, instr: int) -> int:
        """Thumb SWI (format 17)."""
        swi_num = instr & 0xFF
        if hasattr(self, 'swi_handler'):
            self.swi_handler(swi_num)
        self.registers[15] += 2
        return 1


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




# === End of arm7tdmi.py ===


# === Start of bios.py ===




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
        """CPU Set - block copy (bit 24 = 16-bit flag, no fill mode)"""
        is_16bit = bool(control & 0x01000000)
        word_count = count & 0x001FFFFF

        if is_16bit:
            for i in range(word_count):
                value = self.memory.read_u16(src + i * 2)
                self.memory.write_u16(dst + i * 2, value)
        else:
            for i in range(word_count):
                value = self.memory.read_u32(src + i * 4)
                self.memory.write_u32(dst + i * 4, value)

    def swi_cpufastset(self, src: int, dst: int, count: int, control: int):
        """CPU Fast Set - faster block copy/fill (32-bit only)"""
        is_fill = bool(control & 0x01000000)

        word_count = count
        if is_fill:
            value = self.memory.read_u32(src)
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
        """Huffman decompression (SWI 0x11)
        
        GBA BIOS Huffman decompression algorithm:
        - Header: 5 bytes (format byte + decompressed size + tree size)
        - Tree: tree_size bytes (must be even), stored as packed nodes
        - Data: compressed bitstream following the tree
        
        Tree structure:
        - Each node is 1 byte: bit 7 = 1 for branch, 0 for data
        - Branch node: bits 0-6 = child offset (left child at offset, right at offset+1)
        - Data node: bits 0-6 = output value
        - Root node is at offset (tree_size / 2)
        
        Returns: number of bytes decompressed, or 0 on failure
        """
        src = self.memory.read_bytes(src_addr, 102400)

        if len(src) < 8 or src[0] != 0x11:
            # Invalid header - return 0 bytes decompressed (graceful fallback)
            return 0

        expanded_size = struct.unpack("<I", src[1:5])[0]
        if expanded_size == 0:
            return 0
            
        tree_size = src[4] if len(src) > 4 else 0
        
        # Tree size must be even and non-zero
        if tree_size == 0 or tree_size % 2 != 0:
            return 0
        
        # Tree occupies tree_size bytes, stored starting at src_addr + 5
        # Tree nodes are packed: (tree_size / 2) + 1 nodes
        tree_node_count = (tree_size >> 1) + 1
        tree_start = src_addr + 5
        data_start = tree_start + tree_size
        
        # Read tree nodes
        tree_nodes = []
        for i in range(tree_node_count):
            if data_start + tree_size - tree_size + i < src_addr + len(src):
                tree_nodes.append(self.memory.read_u8(tree_start + i))
            else:
                return 0
        
        # Root node is at offset (tree_size / 2)
        root_offset = tree_size >> 1
        
        # Decompression state
        output = bytearray()
        bit_buffer = 0
        bits_in_buffer = 0
        data_byte_offset = 0
        
        while len(output) < expanded_size:
            # Start from root and walk tree
            node_offset = root_offset
            
            while True:
                # Ensure we have bits in buffer
                if bits_in_buffer == 0:
                    # Read next byte from compressed data
                    if data_byte_offset >= tree_node_count:
                        # Error: ran out of compressed data
                        return 0
                    bit_buffer = self.memory.read_u8(data_start + data_byte_offset)
                    data_byte_offset += 1
                    bits_in_buffer = 8
                
                # Read next bit (MSB first)
                bit = (bit_buffer >> (bits_in_buffer - 1)) & 1
                bits_in_buffer -= 1
                
                # Get current node
                if node_offset >= len(tree_nodes):
                    return 0
                    
                node = tree_nodes[node_offset]
                
                if node & 0x80:
                    # Branch node: bits 0-6 = child offset
                    child_offset = node & 0x7F
                    
                    if bit == 0:
                        # Left child
                        node_offset = child_offset
                    else:
                        # Right child (offset + 1)
                        node_offset = child_offset + 1
                else:
                    # Data node: bits 0-6 = value
                    value = node & 0x7F
                    output.append(value)
                    break
        
        # Write output to destination
        for i, byte in enumerate(output):
            if i >= expanded_size:
                break
            self.memory.write_u8(dst_addr + i, byte)

        return len(output)

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
        """Huffman decompression (SWI 0x13). Returns bytes decompressed or 0 on failure."""
        header_byte0 = self.memory.read_u8(src_addr)
        decompressed_size = struct.unpack(
            "<I", 
            bytes([
                self.memory.read_u8(src_addr + 1),
                self.memory.read_u8(src_addr + 2),
                self.memory.read_u8(src_addr + 3),
                self.memory.read_u8(src_addr + 4)
            ])
        )[0]
        
        if decompressed_size == 0:
            return 0
        
        data_size_format = header_byte0 >> 4
        tree_size = header_byte0 & 0x0F
        
        if tree_size == 0 or tree_size % 2 != 0:
            return 0
        
        tree_node_count = (tree_size >> 1) + 1
        tree_start = src_addr + 4
        data_start = tree_start + tree_node_count
        
        tree_nodes = [self.memory.read_u8(tree_start + i) for i in range(tree_node_count)]
        root_offset = tree_size >> 1
        
        output = []
        bit_buffer = 0
        bits_in_buffer = 0
        data_byte_offset = 0
        
        while len(output) < decompressed_size:
            node_offset = root_offset
            
            while True:
                if bits_in_buffer == 0:
                    if data_byte_offset >= tree_node_count:
                        return 0
                    bit_buffer = self.memory.read_u8(data_start + data_byte_offset)
                    data_byte_offset += 1
                    bits_in_buffer = 8
                
                bit = (bit_buffer >> (bits_in_buffer - 1)) & 1
                bits_in_buffer -= 1
                node = tree_nodes[node_offset]
                
                if node & 0x80:
                    child_offset = node & 0x7F
                    node_offset = child_offset if bit == 0 else child_offset + 1
                else:
                    output.append(node & 0x7F)
                    break
        
        if data_size_format == 0x1:
            for i, val in enumerate(output):
                if i >= decompressed_size:
                    break
                self.memory.write_u8(dst_addr + i, val)
            return len(output)
        
        elif data_size_format == 0x2:
            for i in range(0, len(output), 2):
                if i + 1 >= len(output):
                    break
                val = output[i] | (output[i + 1] << 8)
                self.memory.write_u16(dst_addr + (i // 2) * 2, val)
            return len(output)
        
        elif data_size_format == 0x4:
            for i in range(0, len(output), 4):
                if i + 3 >= len(output):
                    break
                val = output[i] | (output[i + 1] << 8) | (output[i + 2] << 16) | (output[i + 3] << 24)
                self.memory.write_u32(dst_addr + (i // 4) * 4, val)
            return len(output)
        
        return 0

    def swi_vblank_intr_wait(self):
        if not hasattr(self, "memory") or not hasattr(self.memory, "cpu"):
            return

        cpu = self.memory.cpu
        memory = self.memory
        interrupts = getattr(memory, "_interrupts", None)

        # If a fresh VBlank is already pending, consume it without advancing.
        if interrupts is not None and (interrupts.if_reg & (1 << 0)):
            interrupts.if_reg &= ~(1 << 0)
            cpu.cpsr |= (1 << 30)
            cpu.registers[0] = 1
            return

        # Halt the CPU. The main loop's scanline stepping will advance the PPU
        # and deliver the VBlank IRQ, which clears the halt.
        cpu._halted = True

    def swi_intr_wait(self, wait_flag: int, vblank_flag: int):
        """Wait for interrupt. Halt CPU; wakes on any enabled IRQ (handled by _deliver_irq)."""
        cpu = getattr(getattr(self, "memory", None), "cpu", None)
        if cpu is not None:
            cpu._halted = True

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
        """Halt CPU until any enabled interrupt fires.

        Sets the halt flag only — the main loop owns all PPU timing.
        The _deliver_irq routine in the main loop checks _cpu_halted and
        wakes the CPU when an enabled interrupt becomes pending.
        """
        cpu = getattr(self, "cpu", None) or getattr(getattr(self, "memory", None), "cpu", None)
        if cpu is not None:
            cpu._halted = True
            cpu._halt_reason = 'any'
        else:
            self._sleep_mode = True

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

        note = 69 + 12 * math.log2(freq / 440.0)
        return max(0, min(127, int(note + 0.5)))

    def swi_midi_note_to_freq(self, note: int) -> int:
        """Convert MIDI note number to frequency"""
        if note < 0:
            return 0
        # freq = 440 * 2^((note - 69) / 12)

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


# === End of bios.py ===


# === Start of apu.py ===



# Optional Numba JIT support
try:
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
        
        # Continuous audio playback with thread-safe queue
        self._audio_channel = None
        self._buffer_size = 4096  # Samples per buffer (93ms at 44100Hz) - larger for stability
        self._sound_queue = queue_module.Queue(maxsize=3)  # Buffer 3 sounds ahead
        self._audio_thread = None
        self._stop_event = threading.Event()
        self._audio_started = False
        self._last_audio_state = False  # Track previous audio state

    def start(self):
        """Start audio playback"""
        if not pygame.mixer.get_init():
            # Use larger buffer for smoother playback
            pygame.mixer.init(frequency=self.SAMPLE_RATE, size=-8, channels=2, buffer=2048)

    def _audio_worker(self):
        """Background thread that continuously generates and queues audio buffers."""
        while not self._stop_event.is_set():
            try:
                # Generate audio samples
                samples = self._generate_samples(self._buffer_size)
                sound = pygame.mixer.Sound(buffer=samples)
                
                # Queue the sound (blocks if queue is full)
                self._sound_queue.put(sound, timeout=0.1)
            except queue_module.Full:
                # Queue is full, skip this buffer
                continue
            except Exception:
                # Ignore errors in audio generation
                continue

    def stop(self):
        """Stop audio playback"""
        self._stop_event.set()
        
        # Wait for audio thread to finish
        if self._audio_thread is not None:
            self._audio_thread.join(timeout=1.0)
            self._audio_thread = None
        
        # Clear the queue
        while not self._sound_queue.empty():
            try:
                self._sound_queue.get_nowait()
            except queue_module.Empty:
                break
        
        # Stop mixer
        try:
            pygame.mixer.stop()
        except pygame.error:
            pass
        
        self._audio_started = False
        self._audio_channel = None

    def read_register(self, addr: int) -> int:
        """Handle MMIO reads from sound registers (write-only on hardware, return 0)."""
        return 0

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

    def _generate_samples(self, count: int) -> bytes:
        """Generate 'count' stereo samples and return as bytes."""
        samples = array.array('B')
        for _ in range(count):
            left, right = self.get_sample()
            samples.append(left)
            samples.append(right)
        return samples.tobytes()

    def _audio_worker(self):
        """Background thread that continuously generates and queues audio buffers."""
        while not self._stop_event.is_set():
            try:
                # Generate audio samples
                samples = self._generate_samples(self._buffer_size)
                sound = pygame.mixer.Sound(buffer=samples)
                
                # Queue the sound (blocks if queue is full)
                self._sound_queue.put(sound, timeout=0.1)
            except queue_module.Full:
                # Queue is full, skip this buffer
                continue
            except Exception:
                # Ignore errors in audio generation
                continue

    def update(self):
        """Update audio playback with continuous thread-based buffering."""
        if not pygame.mixer.get_init():
            return

        # Check if any audio is enabled
        audio_enabled = (self.ch1_enabled or self.ch2_enabled or
                        self.ch3_enabled or self.ch4_enabled or
                        self.fifo_a_enabled or self.fifo_b_enabled)
        
        # Stop audio if nothing is enabled
        if not audio_enabled:
            if self._last_audio_state:
                self.stop()
                self._last_audio_state = False
            return

        # Initialize audio channel on first use
        if not self._audio_started:
            try:
                if pygame.mixer.get_num_channels() < 2:
                    pygame.mixer.set_num_channels(2)
                self._audio_channel = pygame.mixer.Channel(1)
                
                # Start the audio worker thread
                self._stop_event.clear()
                self._audio_thread = threading.Thread(target=self._audio_worker, daemon=True)
                self._audio_thread.start()
                
                self._audio_started = True
                self._last_audio_state = True
            except pygame.error:
                return

        # Play sounds from the queue
        try:
            # Check if channel is busy
            if not self._audio_channel.get_busy():
                # Try to get next sound from queue (non-blocking)
                try:
                    next_sound = self._sound_queue.get_nowait()
                    self._audio_channel.play(next_sound)
                except queue_module.Empty:
                    # No sound ready yet, will be filled by worker thread
                    pass
        except pygame.error:
            pass


# === End of apu.py ===


# === Start of timers.py ===



class TimerChannel:
    """Individual timer channel"""
    
    def __init__(self):
        self.count = 0
        self.reload = 0
        self.control = 0

    @property
    def enabled(self) -> bool:
        """Check if timer is enabled (bit 8)"""
        return bool(self.control & 0x80)

    @property
    def irq_enable(self) -> bool:
        """Check if IRQ is enabled (bit 6)"""
        return bool(self.control & 0x40)

    @property
    def cascade(self) -> bool:
        """Check if cascade mode is enabled (bit 2)"""
        return bool(self.control & 0x04)

    @property
    def prescaler_value(self) -> int:
        """Get prescaler divisor value (bits 0-1)"""
        prescale_bits = self.control & 0x03
        return [1, 64, 256, 1024][prescale_bits]


class Timers:
    """GBA Timer Controller with 4 timer channels"""
    
    PRESCALER_VALUES = [1, 64, 256, 1024]

    def __init__(self):
        self._channels = [TimerChannel() for _ in range(4)]
        self._overflow_flags = [False] * 4
        self._interrupts = None
        self._cycle_subcount = [0] * 4

    def attach_interrupts(self, interrupts):
        """Attach interrupt controller for timer IRQ callbacks"""
        self._interrupts = interrupts

    @property
    def channels(self):
        """Access timer channels"""
        return self._channels

    def get_timer(self, channel: int) -> int:
        """Get current count value for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        return self._channels[channel].count

    def set_timer(self, channel: int, value: int) -> None:
        """Set count value for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        self._channels[channel].count = value & 0xFFFF

    def set_control(self, channel: int, control: int) -> None:
        """Set control register for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        self._channels[channel].control = control & 0xFF

    def set_reload(self, channel: int, reload: int) -> None:
        """Set reload value for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        self._channels[channel].reload = reload & 0xFFFF

    def get_control(self, channel: int) -> int:
        """Get control register for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        return self._channels[channel].control

    def get_reload(self, channel: int) -> int:
        """Get reload value for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        return self._channels[channel].reload

    def get_overflow_flag(self, channel: int) -> bool:
        """Get overflow flag for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        return self._overflow_flags[channel]

    def clear_overflow_flag(self, channel: int) -> None:
        """Clear overflow flag for timer channel"""
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        self._overflow_flags[channel] = False

    def step(self, cycles: int) -> None:
        """Advance all enabled timers by given cycles.
        
        Args:
            cycles: Number of CPU cycles to advance timers
        """
        # Check cascade flags BEFORE reset, then clear
        cascade_flags = [self._overflow_flags[i] for i in range(4)]
        self._overflow_flags = [False] * 4

        # Process each timer
        for i in range(4):
            channel = self._channels[i]

            # Skip disabled timers
            if not channel.enabled:
                continue

            # Cascade mode: increment only when previous timer overflows
            if channel.cascade:
                if i == 0:
                    continue
                if not cascade_flags[i - 1]:
                    continue
                increment = 1
            else:
                prescaler = channel.prescaler_value
                total = self._cycle_subcount[i] + cycles
                increment = total // prescaler
                self._cycle_subcount[i] = total % prescaler

            if increment > 0:
                new_count = channel.count + increment
                if new_count > 0xFFFF:
                    self._overflow_flags[i] = True
                    new_count = (new_count - 0x10000) + channel.reload
                    if channel.irq_enable and self._interrupts:
                        self._interrupts.timer_irq(i)
                channel.count = new_count & 0xFFFF

# === End of timers.py ===


# === Start of interrupts.py ===



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


# === End of interrupts.py ===


# === Start of input.py ===


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


# === End of input.py ===


# === Start of hooks.py ===




class HookManager:
    """
    Manages debugging hooks and callbacks for the GBA emulator.
    
    All hook types support zero-overhead operation when no hooks are registered.
    """
    
    def __init__(self):
        self._instruction_hooks: Dict[int, Callable[[int], None]] = {}
        self._write_hooks: Dict[int, Callable[[int, int], None]] = {}
        self._read_hooks: Dict[int, Callable[[int], int]] = {}
        self._frame_hooks: List[Callable[[int], None]] = []
        self._breakpoints: Set[int] = set()
        self._step_mode: bool = False
        
        # Fast-path flag - updated when hooks are added/removed
        self._has_any_hooks: bool = False
    
    def on_instruction(self, addr: int, callback: Callable[[int], None]) -> None:
        """
        Register a callback for instruction execution at a specific address.
        
        Args:
            addr: Instruction address (PC value) to hook
            callback: Function called with the PC address when instruction executes
        """
        self._instruction_hooks[addr] = callback
        self._has_any_hooks = True
    
    def on_write(self, addr: int, callback: Callable[[int, int], None]) -> None:
        """
        Register a callback for memory writes to a specific address.
        
        Args:
            addr: Memory address to watch for writes
            callback: Function called with (address, value) on write
        """
        self._write_hooks[addr] = callback
        self._has_any_hooks = True
    
    def on_read(self, addr: int, callback: Callable[[int], int]) -> None:
        """
        Register a callback for memory reads from a specific address.
        
        Args:
            addr: Memory address to watch for reads
            callback: Function called with address, returns value to use
        """
        self._read_hooks[addr] = callback
        self._has_any_hooks = True
    
    def on_frame(self, callback: Callable[[int], None]) -> None:
        """
        Register a callback for each rendered frame.
        
        Args:
            callback: Function called with frame number after each render
        """
        self._frame_hooks.append(callback)
        self._has_any_hooks = True
    
    def add_breakpoint(self, addr: int) -> None:
        """
        Add a breakpoint at the specified address.
        
        When execution reaches this address, the emulator will pause.
        
        Args:
            addr: Address where execution should pause
        """
        self._breakpoints.add(addr)
        self._has_any_hooks = True
    
    def remove_breakpoint(self, addr: int) -> None:
        """
        Remove a breakpoint from the specified address.
        
        Args:
            addr: Address to remove breakpoint from
        """
        self._breakpoints.discard(addr)
        # Check if any hooks remain
        self._has_any_hooks = bool(
            self._instruction_hooks or
            self._write_hooks or
            self._read_hooks or
            self._frame_hooks or
            self._breakpoints or
            self._step_mode
        )
    
    def enable_step_mode(self, enabled: bool = True) -> None:
        """
        Enable or disable single-step execution mode.
        
        When enabled, execution pauses after every instruction.
        
        Args:
            enabled: True to enable step mode, False to disable
        """
        self._step_mode = enabled
        self._has_any_hooks = enabled or bool(
            self._instruction_hooks or
            self._write_hooks or
            self._read_hooks or
            self._frame_hooks or
            self._breakpoints
        )
    
    def check_hooks(self, pc: int, event_type: str) -> Optional[bool]:
        """
        Check and execute hooks for the current execution state.
        
        Args:
            pc: Current program counter value
            event_type: Type of event ('instruction', 'write', 'read', 'frame')
            
        Returns:
            True if execution should pause (breakpoint hit), None otherwise
        """
        # Check for breakpoint
        if pc in self._breakpoints:
            print(f"\n[BREAKPOINT] PC=0x{pc:08X}")
            return True
        
        # Check instruction hooks
        if event_type == 'instruction' and pc in self._instruction_hooks:
            self._instruction_hooks[pc](pc)
        
        # Step mode - pause after every instruction
        if self._step_mode:
            print(f"[STEP] PC=0x{pc:08X}")
            return True
        
        return None
    
    def check_write_hook(self, addr: int, value: int) -> None:
        """
        Check and execute write hooks for a memory write.
        
        Args:
            addr: Memory address being written
            value: Value being written
        """
        if addr in self._write_hooks:
            self._write_hooks[addr](addr, value)
    
    def check_read_hook(self, addr: int) -> Optional[int]:
        """
        Check and execute read hooks for a memory read.
        
        Args:
            addr: Memory address being read
            
        Returns:
            Value from hook if registered, None otherwise
        """
        if addr in self._read_hooks:
            return self._read_hooks[addr](addr)
        return None
    
    def notify_frame(self, frame_num: int) -> None:
        """
        Notify all frame hooks of a new frame.
        
        Args:
            frame_num: Current frame number
        """
        for callback in self._frame_hooks:
            callback(frame_num)
    
    def has_hooks(self) -> bool:
        """
        Fast check if any hooks are registered.
        
        Returns:
            True if any hooks exist, False otherwise (zero-overhead path)
        """
        return self._has_any_hooks
    
    def clear_all(self) -> None:
        """Remove all registered hooks and breakpoints."""
        self._instruction_hooks.clear()
        self._write_hooks.clear()
        self._read_hooks.clear()
        self._frame_hooks.clear()
        self._breakpoints.clear()
        self._step_mode = False
        self._has_any_hooks = False
    
    def list_breakpoints(self) -> List[int]:
        """
        Get list of all breakpoint addresses.
        
        Returns:
            Sorted list of breakpoint addresses
        """
        return sorted(self._breakpoints)
    
    def __repr__(self) -> str:
        return (
            f"HookManager(instructions={len(self._instruction_hooks)}, "
            f"writes={len(self._write_hooks)}, reads={len(self._read_hooks)}, "
            f"frames={len(self._frame_hooks)}, breakpoints={len(self._breakpoints)}, "
            f"step_mode={self._step_mode})"
        )


# === End of hooks.py ===


# === Start of assets.py ===




class AssetType(Enum):
    """Types of GBA assets"""

    TILE_4BPP = auto()  # 4 bits per pixel, 16 colors, 8x8 = 32 bytes
    TILE_8BPP = auto()  # 8 bits per pixel, 256 colors, 8x8 = 64 bytes
    PALETTE = auto()  # 15-bit BGR color palette
    TILEMAP = auto()  # Tilemap with tile indices and attributes
    SPRITE = auto()  # Sprite data
    COMPRESSED = auto()  # Compressed data (needs decompression)
    UNKNOWN = auto()


class AssetExtractor:
    """Extract and decompress GBA assets from ROM"""

    def __init__(self, memory):
        self.memory = memory

    def decompress_lz77(self, data: bytes) -> bytes:
        """Decompress LZ77 compressed data (method 0x10)

        GBA LZ77 format:
        - Byte 0: 0x10 (method identifier)
        - Bytes 1-3: 24-bit decompressed size (little-endian)
        - Byte 4: flags
        """
        if len(data) < 4 or data[0] != 0x10:
            return b""

        # GBA uses 24-bit expanded_size (3 bytes little-endian), NOT 32-bit
        expanded_size = data[1] | (data[2] << 8) | (data[3] << 16)
        src_pos = 8
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(data):
            flags = data[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    # Compressed block
                    if src_pos + 1 >= len(data):
                        break
                    pair = struct.unpack("<H", data[src_pos : src_pos + 2])[0]
                    src_pos += 2

                    back = (pair >> 4) + 3
                    count = (pair & 0xF) + 3

                    for j in range(count):
                        if len(dst) >= expanded_size:
                            break
                        if src_pos - back - len(data) < 0:
                            dst.append(0)
                        else:
                            idx = len(dst) - back - 1
                            if idx >= 0 and idx < len(dst):
                                dst.append(dst[idx])
                            else:
                                dst.append(0)
                else:
                    # Raw byte
                    if src_pos < len(data):
                        dst.append(data[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        return bytes(dst[:expanded_size])

    def decompress_huffman(self, data: bytes) -> bytes:
        """Decompress Huffman compressed data (method 0x11)

        GBA Huffman format:
        - Byte 0: 0x11 (method identifier)
        - Bytes 1-4: 32-bit decompressed size (little-endian)
        - Tree size byte at position 4 (or 5 depending on variant)
        - Tree data follows header
        - Compressed bitstream after tree
        """
        if len(data) < 4 or data[0] != 0x11:
            return b""

        # GBA uses 32-bit size at bytes 1-4 (unlike LZ77's 24-bit)
        expanded_size = struct.unpack("<I", data[1:5])[0]

        # Tree size is at byte 4 (size of tree table / 2 - 1)
        tree_size = data[4] if len(data) > 4 else 0
        tree_end = 8 + tree_size

        if len(data) <= tree_end:
            return b""

        # Build Huffman tree from tree data
        # Each node is 2 bytes: bits 0-7 of left child, bits 0-7 of right child
        # Special values: 0xFF means "no data", other values are data or node index
        tree = data[8:tree_end]

        # Number of nodes in tree
        num_nodes = len(tree) // 2

        # Build a lookup table for decoding
        # GBA Huffman uses a binary tree where:
        # - If node < 256, it's a leaf with that byte value
        # - If node >= 256, it's an internal node: node - 256 gives the table index
        decode_table = {}

        def build_decode_table(node_idx: int, bit_string: int, bits: int):
            """Recursively build decode table"""
            if node_idx >= num_nodes:
                return

            # Read node pair (2 bytes per node)
            if node_idx * 2 + 1 >= len(tree):
                return

            left = tree[node_idx * 2]
            right = tree[node_idx * 2 + 1]

            # Left child (bit 0)
            if left < 256:
                # Leaf node - data
                decode_table[bit_string] = (left, bits)
            elif left < 0xFF:
                # Internal node - continue tree
                build_decode_table(left, (bit_string << 1) | 0, bits + 1)

            # Right child (bit 1)
            if right < 256:
                decode_table[(bit_string << 1) | 1] = (right, bits)
            elif right < 0xFF:
                build_decode_table(right, (bit_string << 1) | 1, bits + 1)

        # Start from root node (0)
        build_decode_table(0, 0, 0)

        # Now decompress using the bitstream
        compressed = data[tree_end:]
        dst = bytearray()
        bit_pos = 0

        # Track current node state
        current_bits = 0
        current_bit_count = 0

        while len(dst) < expanded_size and bit_pos < len(compressed) * 8:
            # Read one bit
            byte_idx = bit_pos // 8
            bit_idx = 7 - (bit_pos % 8)

            if byte_idx >= len(compressed):
                break

            bit = (compressed[byte_idx] >> bit_idx) & 1
            bit_pos += 1

            current_bits = (current_bits << 1) | bit
            current_bit_count += 1

            # Look up in decode table
            if current_bits in decode_table:
                symbol, expected_bits = decode_table[current_bits]
                if expected_bits == current_bit_count:
                    dst.append(symbol)
                    current_bits = 0
                    current_bit_count = 0

                    if len(dst) >= expanded_size:
                        break

        return bytes(dst[:expanded_size])

    def decompress_rle(self, data: bytes) -> bytes:
        """Decompress Run-Length compressed data (method 0x12)"""
        if len(data) < 5 or data[0] != 0x12:
            return b""

        expanded_size = struct.unpack("<I", data[1:5])[0]
        src_pos = 5  # GBA RLE header: 0x12 (1 byte) + 32-bit size (4 bytes) = 5 bytes
        dst = bytearray()

        while len(dst) < expanded_size and src_pos < len(data):
            flags = data[src_pos]
            src_pos += 1

            for i in range(8):
                if len(dst) >= expanded_size:
                    break

                if flags & 0x80:
                    # Run-length block
                    if src_pos >= len(data):
                        break
                    byte_val = data[src_pos]
                    src_pos += 1

                    if src_pos >= len(data):
                        break
                    count = data[src_pos] + 1
                    src_pos += 1

                    dst.extend([byte_val] * min(count, expanded_size - len(dst)))
                else:
                    # Raw byte
                    if src_pos < len(data):
                        dst.append(data[src_pos])
                        src_pos += 1

                flags = (flags << 1) & 0xFF

        return bytes(dst[:expanded_size])

    def extract_palette(self, addr: int, num_colors: int = 256) -> List[Tuple[int, int, int]]:
        """Extract 15-bit color palette from memory"""
        palette = []
        for i in range(num_colors):
            color16 = self.memory.read_u16(addr + i * 2)
            r = (color16 & 0x1F) * 8
            g = ((color16 >> 5) & 0x1F) * 8
            b = ((color16 >> 10) & 0x1F) * 8
            palette.append((r, g, b))
        return palette

    def extract_tile_4bpp(self, tile_addr: int, tile_num: int = 0) -> bytes:
        """Extract 4bpp (16-color) 8x8 tile"""
        addr = tile_addr + tile_num * 32  # 32 bytes per 4bpp tile
        return self.memory.read_bytes(addr, 32)

    def extract_tile_8bpp(self, tile_addr: int, tile_num: int = 0) -> bytes:
        """Extract 8bpp (256-color) 8x8 tile"""
        addr = tile_addr + tile_num * 64  # 64 bytes per 8bpp tile
        return self.memory.read_bytes(addr, 64)

    def scan_rom_for_assets(self, rom_data: bytes) -> Dict:
        """Scan ROM for potential asset regions with size validation"""
        assets = {
            "palettes": [],
            "compressed": [],
            "tiles_4bpp": [],
            "tiles_8bpp": [],
            "tilemaps": [],
        }

        MAX_COMPRESSED_SIZE = 10 * 1024 * 1024
        MIN_ASSET_SIZE = 16

        for offset in range(0, len(rom_data) - 512, 2):
            if offset + 32 < len(rom_data):
                sample = rom_data[offset : offset + 32]
                valid_colors = 0
                for i in range(0, min(32, len(sample)), 2):
                    if i + 1 < len(sample):
                        color = sample[i] | (sample[i + 1] << 8)
                        if (color & 0x7C00) == 0:
                            valid_colors += 1
                if valid_colors >= 10:
                    assets["palettes"].append(offset)

        for offset in range(0, len(rom_data) - 8):
            method = rom_data[offset]
            if method in [0x10, 0x11, 0x12]:
                if method == 0x10:
                    size = (
                        rom_data[offset + 1]
                        | (rom_data[offset + 2] << 8)
                        | (rom_data[offset + 3] << 16)
                    )
                else:
                    size = struct.unpack("<I", rom_data[offset + 1 : offset + 5])[0]

                if MIN_ASSET_SIZE <= size <= MAX_COMPRESSED_SIZE:
                    compressed_type = (
                        "lz77" if method == 0x10 else ("huffman" if method == 0x11 else "rle")
                    )

                    compressed_size_estimate = self._estimate_compressed_size(offset, size, method)

                    if compressed_size_estimate > 0:
                        assets["compressed"].append(
                            {
                                "offset": offset,
                                "type": compressed_type,
                                "decompressed_size": size,
                                "compressed_estimate": compressed_size_estimate,
                            }
                        )

        return assets

    def _estimate_compressed_size(
        self, offset: int, decompressed_size: int, method: int, rom_data: bytes = None
    ) -> int:
        """Estimate compressed data size for validation"""
        if method == 0x10:
            header_size = 4
            return header_size + (decompressed_size // 8) + 1
        elif method == 0x11:
            return 8 + (decompressed_size // 4)
        else:
            return 5 + (decompressed_size // 8)

    def detect_asset_type(self, data: bytes) -> AssetType:
        """Detect asset type from raw data"""
        if not data or len(data) < 4:
            return AssetType.UNKNOWN

        data_len = len(data)

        if data_len % 2 == 0:
            valid_colors = self._count_valid_15bit_colors(data[:64])
            if valid_colors >= data_len // 4:
                return AssetType.PALETTE

        if data_len % 64 == 0 and data_len >= 64:
            if self._is_likely_8bpp_tiles(data):
                return AssetType.TILE_8BPP

        if data_len % 32 == 0 and data_len >= 32:
            if self._is_likely_4bpp_tiles(data):
                return AssetType.TILE_4BPP

        if data_len % 2 == 0 and data_len >= 32:
            if self._is_likely_tilemap(data):
                return AssetType.TILEMAP

        return AssetType.UNKNOWN

    def _count_valid_15bit_colors(self, data: bytes) -> int:
        """Count valid 15-bit BGR colors in data"""
        valid = 0
        for i in range(0, min(len(data), 64), 2):
            if i + 1 >= len(data):
                break
            color = data[i] | (data[i + 1] << 8)
            r = color & 0x1F
            g = (color >> 5) & 0x1F
            b = (color >> 10) & 0x1F
            if r <= 31 and g <= 31 and b <= 31:
                valid += 1
        return valid

    def _is_likely_4bpp_tiles(self, data: bytes) -> bool:
        """Check if data looks like 4BPP tiles"""
        if len(data) % 32 != 0:
            return False

        unique_bytes = len(set(data[:64]))

        if unique_bytes > 16 and unique_bytes < 256:
            return True

        return False

    def _is_likely_8bpp_tiles(self, data: bytes) -> bool:
        """Check if data looks like 8BPP tiles"""
        if len(data) % 64 != 0:
            return False

        unique_bytes = len(set(data[:128]))

        if unique_bytes > 32:
            return True

        return False

    def _is_likely_tilemap(self, data: bytes) -> bool:
        """Check if data looks like tilemap"""
        if len(data) < 32:
            return False

        unique_indices = set()
        for i in range(0, min(len(data), 64), 2):
            if i + 1 >= len(data):
                break
            entry = data[i] | (data[i + 1] << 8)
            tile_idx = entry & 0x3FF
            unique_indices.add(tile_idx)

        if 2 <= len(unique_indices) <= 1024:
            return True

        return False

    def find_palette_in_rom(self, rom_data: bytes) -> Optional[int]:
        """Find palette data in ROM, returns offset or None"""
        if not rom_data or len(rom_data) < 512:
            return None

        best_offset = None
        best_score = 0

        for offset in range(0, min(len(rom_data) - 512, 1024 * 1024), 16):
            palette_size = min(512, len(rom_data) - offset)
            sample = rom_data[offset : offset + palette_size]

            score = self._score_palette_candidate(sample)

            if score > best_score:
                best_score = score
                best_offset = offset

        if best_score >= 10:
            return best_offset

        return None

    def _score_palette_candidate(self, data: bytes) -> int:
        """Score how likely data is a palette"""
        if len(data) < 32:
            return -1

        score = 0

        unique_colors = set()
        color_pairs = []

        for i in range(0, min(len(data), 512), 2):
            if i + 1 >= len(data):
                break
            color = data[i] | (data[i + 1] << 8)
            r = color & 0x1F
            g = (color >> 5) & 0x1F
            b = (color >> 10) & 0x1F

            if r <= 31 and g <= 31 and b <= 31:
                unique_colors.add((r, g, b))
                color_pairs.append((r, g, b))

        score += len(unique_colors)

        if len(unique_colors) >= 8:
            score += 5

        if len(color_pairs) >= 16:
            gradient_count = 0
            for i in range(1, len(color_pairs)):
                prev = color_pairs[i - 1]
                curr = color_pairs[i]
                if (
                    abs(curr[0] - prev[0]) <= 8
                    and abs(curr[1] - prev[1]) <= 8
                    and abs(curr[2] - prev[2]) <= 8
                ):
                    gradient_count += 1

            if gradient_count > len(color_pairs) // 3:
                score += 3

        return score

    def load_assets(self, assets_dir: str, ppu) -> bool:
        rom_path = None
        if os.path.isfile(assets_dir) and assets_dir.endswith(".gba"):
            rom_path = assets_dir
        elif os.path.isdir(assets_dir):
            for f in os.listdir(assets_dir):
                if f.endswith(".gba"):
                    rom_path = os.path.join(assets_dir, f)
                    break

        if not rom_path:
            for f in os.listdir("."):
                if f.endswith(".gba"):
                    rom_path = f
                    break

        if not rom_path or not os.path.exists(rom_path):
            return False

        with open(rom_path, "rb") as f:
            rom_data = f.read()

        if not rom_data or len(rom_data) < 512:
            return False

        extractor = AssetExtractor(self.memory)
        palette_offset = extractor.find_palette_in_rom(rom_data)
        if palette_offset:
            palette_data = rom_data[palette_offset : palette_offset + 512]
            ppu.palette_bg = []
            for i in range(0, min(len(palette_data), 512), 2):
                if i + 1 < len(palette_data):
                    color_val = palette_data[i] | (palette_data[i + 1] << 8)
                    r = ((color_val >> 0) & 0x1F) * 8
                    g = ((color_val >> 5) & 0x1F) * 8
                    b = ((color_val >> 10) & 0x1F) * 8
                    ppu.palette_bg.append((r, g, b))

        tile_data = []
        for offset in range(0, len(rom_data) - 32, 2):
            sample = rom_data[offset : offset + 32]
            unique_bytes = len(set(sample[:64]))
            if unique_bytes > 16 and unique_bytes < 256:
                tile_data.extend(sample)
                if len(tile_data) >= 8192:
                    break

        if tile_data:
            ppu.tiles_4bpp = list(tile_data)

        tilemap_data = []
        for offset in range(0, len(rom_data) - 2, 2):
            if len(tilemap_data) >= 1024 * 2:
                break
            if offset + 1 < len(rom_data):
                entry = rom_data[offset] | (rom_data[offset + 1] << 8)
                tilemap_data.append(entry)

        if tilemap_data:
            ppu.bg0_tilemap = tilemap_data[:1024]

        return True


# === End of assets.py ===


# === Start of cartridge.py ===





class SaveType:
    NONE = 0
    SRAM = 1
    FLASH512 = 2
    FLASH1M = 3
    EEPROM4K = 4
    EEPROM16K = 5


SAVE_TYPE_NAMES = {
    SaveType.NONE: "None",
    SaveType.SRAM: "SRAM (64KB)",
    SaveType.FLASH512: "FLASH512 (512KB)",
    SaveType.FLASH1M: "FLASH1M (1MB)",
    SaveType.EEPROM4K: "EEPROM4K (512 bytes)",
    SaveType.EEPROM16K: "EEPROM16K (2KB)",
}


ROM_OFFSET_SAVE_TYPE = 0x1A4


SAVE_TYPE_DETECTION = {
    0x00: SaveType.NONE,
    0x01: SaveType.SRAM,
    0x02: SaveType.FLASH512,
    0x03: SaveType.FLASH1M,
    0x04: SaveType.EEPROM4K,
    0x05: SaveType.EEPROM16K,
    0x12: SaveType.FLASH512,
    0x13: SaveType.FLASH1M,
}


KNOWN_GAME_SAVE_TYPES = {
    "POKEMON RUBY": SaveType.FLASH1M,
    "POKEMON SAPPHIRE": SaveType.FLASH1M,
    "POKEMON EMERALD": SaveType.FLASH1M,
    "POKEMON FIRE RED": SaveType.FLASH1M,
    "POKEMON LEAF GREEN": SaveType.FLASH1M,
    "SONIC ADVANCE": SaveType.FLASH512,
    "SONIC ADVANCE 2": SaveType.FLASH512,
    "SONIC ADVANCE 3": SaveType.FLASH512,
    "MARIO KART": SaveType.EEPROM16K,
    "ZELDA MINISH CAP": SaveType.EEPROM4K,
    "METROID FUSION": SaveType.EEPROM4K,
    "METROID ZERO MISSION": SaveType.EEPROM4K,
    "SUPER MARIO ADVANCE": SaveType.EEPROM4K,
    "SUPER MARIO ADVANCE 2": SaveType.EEPROM4K,
    "SUPER MARIO ADVANCE 3": SaveType.EEPROM4K,
    "SUPER MARIO ADVANCE 4": SaveType.EEPROM4K,
}


class SramHandler:
    SRAM_SIZE = 64 * 1024
    
    def __init__(self):
        self._data = bytearray(self.SRAM_SIZE)
        self._filepath = None
        self._dirty = False
    
    @property
    def size(self):
        return self.SRAM_SIZE
    
    def read(self, addr, length=1):
        result = []
        for i in range(length):
            offset = (addr - 0x0A000000 + i) % self.SRAM_SIZE
            result.append(self._data[offset])
        return bytes(result)
    
    def write(self, addr, data):
        for i, byte in enumerate(data):
            offset = (addr - 0x0A000000 + i) % self.SRAM_SIZE
            self._data[offset] = byte
            self._dirty = True
    
    def load_from_file(self, filepath):
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, "rb") as f:
                self._data = bytearray(f.read())
            self._filepath = filepath
            self._dirty = False
            return True
        except:
            return False
    
    def save_to_file(self, filepath=None):
        path = filepath or self._filepath
        if path is None:
            return False
        try:
            d = os.path.dirname(path)
            if d and not os.path.exists(d):
                os.makedirs(d)
            with open(path, "wb") as f:
                f.write(bytes(self._data))
            self._dirty = False
            self._filepath = path
            return True
        except:
            return False
    
    def is_dirty(self):
        return self._dirty
    
    def get_data(self):
        return bytes(self._data)
    
    def set_data(self, data):
        self._data[:len(data)] = data[:self.SRAM_SIZE]
        self._dirty = True


class Cartridge:
    def __init__(self):
        self._save_type = SaveType.NONE
        self._save_handler = None
        self._rom_data = None
        self._game_title = ""
        self._game_code = ""
    
    def load_rom(self, rom_path: str) -> bool:
        try:
            with open(rom_path, "rb") as f:
                self._rom_data = f.read()
            
            if len(self._rom_data) < 0x1A5:
                return False
            
            self._game_title = self._rom_data[0xA0:0xAC].rstrip(b"\x00").decode("ascii", errors="replace")
            self._game_code = self._rom_data[0xAC:0xB0].decode("ascii", errors="replace")
            
            self._detect_save_type()
            self._create_save_handler()
            
            return True
        except Exception:
            return False
    
    def load_rom_data(self, data: bytes) -> bool:
        try:
            self._rom_data = data
            
            if len(self._rom_data) < 0x1A5:
                return False
            
            self._game_title = self._rom_data[0xA0:0xAC].rstrip(b"\x00").decode("ascii", errors="replace")
            self._game_code = self._rom_data[0xAC:0xB0].decode("ascii", errors="replace")
            
            self._detect_save_type()
            self._create_save_handler()
            
            return True
        except Exception:
            return False
    
    def _detect_save_type(self) -> None:
        if self._rom_data is None or len(self._rom_data) < 0x1A5:
            self._save_type = SaveType.NONE
            return
        
        save_type_byte = self._rom_data[ROM_OFFSET_SAVE_TYPE]
        
        self._save_type = SAVE_TYPE_DETECTION.get(save_type_byte, SaveType.NONE)
        
        if self._save_type == SaveType.NONE:
            title_upper = self._game_title.upper()
            for game_pattern, save_type in KNOWN_GAME_SAVE_TYPES.items():
                if game_pattern in title_upper:
                    self._save_type = save_type
                    break
    
    def _create_save_handler(self) -> None:
        if self._save_type == SaveType.NONE:
            self._save_handler = None
        elif self._save_type == SaveType.SRAM:
            self._save_handler = SramHandler()
        elif self._save_type == SaveType.FLASH512:
            self._save_handler = create_flash_save("512KB")
        elif self._save_type == SaveType.FLASH1M:
            self._save_handler = create_flash_save("1MB")
        elif self._save_type == SaveType.EEPROM4K:
            self._save_handler = create_eeprom_save("4K")
        elif self._save_type == SaveType.EEPROM16K:
            self._save_handler = create_eeprom_save("16K")
    
    @property
    def save_type(self) -> int:
        return self._save_type
    
    @property
    def save_type_name(self) -> str:
        return SAVE_TYPE_NAMES.get(self._save_type, "Unknown")
    
    @property
    def game_title(self) -> str:
        return self._game_title
    
    @property
    def game_code(self) -> str:
        return self._game_code
    
    @property
    def has_save(self) -> bool:
        return self._save_handler is not None
    
    def get_save_handler(self):
        return self._save_handler
    
    def read_save(self, addr: int, length: int = 1) -> bytes:
        if self._save_handler is None:
            return bytes([0xFF] * length)
        return self._save_handler.read(addr, length)
    
    def write_save(self, addr: int, data: bytes) -> None:
        if self._save_handler is not None:
            self._save_handler.write(addr, data)
    
    def load_save_file(self, filepath: str) -> bool:
        if self._save_handler is None:
            return False
        return self._save_handler.load_from_file(filepath)
    
    def save_to_file(self, filepath: str) -> bool:
        if self._save_handler is None:
            return False
        return self._save_handler.save_to_file(filepath)
    
    def is_dirty(self) -> bool:
        if self._save_handler is None:
            return False
        return self._save_handler.is_dirty()


def detect_save_type(rom_data: bytes) -> int:
    if rom_data is None or len(rom_data) < 0x1A5:
        return SaveType.NONE
    
    save_type_byte = rom_data[ROM_OFFSET_SAVE_TYPE]
    return SAVE_TYPE_DETECTION.get(save_type_byte, SaveType.NONE)


def create_cartridge(rom_path: str = None) -> Cartridge:
    cartridge = Cartridge()
    if rom_path and os.path.exists(rom_path):
        cartridge.load_rom(rom_path)
    return cartridge


# === End of cartridge.py ===


# === Start of eeprom_save.py ===




class EepromSave:
    """EEPROM save memory handler for GBA cartridges.
    
    Supports:
    - EEPROM4K: 4Kbit (512 bytes) with 10-bit addressing
    - EEPROM16K: 16Kbit (2KB) with 14-bit addressing
    
    The EEPROM uses a serial-like protocol:
    - Commands: READ (0x03), WRITE (0x02), WREN (0x06), WRDI (0x04)
    - Address is sent MSB first
    - Data is read/written sequentially
    """
    
    EEPROM4K_SIZE = 512
    EEPROM16K_SIZE = 2048
    
    EEPROM4K_ADDR_BITS = 10
    EEPROM16K_ADDR_BITS = 14
    
    CMD_READ = 0x03
    CMD_WRITE = 0x02
    CMD_WREN = 0x06
    CMD_WRDI = 0x04
    CMD_RDSR = 0x05
    CMD_WRSR = 0x01
    
    STATUS_WIP = 0x01
    STATUS_WEL = 0x02
    
    def __init__(self, size: int = EEPROM4K_SIZE):
        self._size = size
        self._is_16k = (size == self.EEPROM16K_SIZE)
        
        self._addr_bits = self.EEPROM16K_ADDR_BITS if self._is_16k else self.EEPROM4K_ADDR_BITS
        
        self._data = bytearray(self._size)
        
        self._write_enabled = False
        self._command_buffer = []
        self._command_state = 0
        
        self._filepath: Optional[str] = None
        self._dirty = False
    
    @property
    def size(self) -> int:
        return self._size
    
    @property
    def is_16k(self) -> bool:
        return self._is_16k
    
    @property
    def addr_bits(self) -> int:
        return self._addr_bits
    
    def _translate_address(self, addr: int) -> int:
        return addr % self._size
    
    def read(self, addr: int, length: int = 1) -> bytes:
        result = bytearray()
        
        for i in range(length):
            offset = self._translate_address(addr + i)
            if offset < self._size:
                result.append(self._data[offset])
            else:
                result.append(0xFF)
        
        return bytes(result)
    
    def write(self, addr: int, data: bytes) -> None:
        if not self._write_enabled:
            return
        
        for i, byte in enumerate(data):
            offset = self._translate_address(addr + i)
            if offset < self._size:
                self._data[offset] = byte
                self._dirty = True
    
    def send_command(self, value: int) -> Optional[int]:
        self._command_buffer.append(value)
        
        if self._command_state == 0:
            cmd = value
            
            if cmd == self.CMD_WREN:
                self._write_enabled = True
                self._command_buffer = []
                self._command_state = 0
                return None
            
            elif cmd == self.CMD_WRDI:
                self._write_enabled = False
                self._command_buffer = []
                self._command_state = 0
                return None
            
            elif cmd == self.CMD_RDSR:
                self._command_state = 1
                status = 0x00
                if self._write_enabled:
                    status |= self.STATUS_WEL
                return status
            
            elif cmd == self.CMD_READ:
                self._command_state = 2
                return None
            
            elif cmd == self.CMD_WRITE:
                self._command_state = 3
                return None
            
            else:
                self._command_buffer = []
                return None
        
        elif self._command_state == 1:
            self._command_buffer = []
            self._command_state = 0
            return 0x00
        
        elif self._command_state == 2:
            if len(self._command_buffer) >= 2:
                addr_bytes = self._command_buffer[-2:]
                addr = ((addr_bytes[0] << 8) | addr_bytes[1]) & ((1 << self._addr_bits) - 1)
                
                offset = self._translate_address(addr)
                if offset < self._size:
                    value = self._data[offset]
                    addr = (addr + 1) % self._size
                    return value
        
        elif self._command_state == 3:
            if len(self._command_buffer) >= 2:
                addr_bytes = self._command_buffer[-2:]
                addr = ((addr_bytes[0] << 8) | addr_bytes[1]) & ((1 << self._addr_bits) - 1)
                
                if len(self._command_buffer) >= 3:
                    data_byte = self._command_buffer[-1]
                    offset = self._translate_address(addr)
                    if offset < self._size:
                        self._data[offset] = data_byte
                        self._dirty = True
        
        return None
    
    def read_id(self) -> int:
        return 0x00
    
    def get_status(self) -> int:
        status = 0x00
        if self._write_enabled:
            status |= self.STATUS_WEL
        return status
    
    def enable_write(self, enabled: bool = True) -> None:
        self._write_enabled = enabled
    
    def load_from_file(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            
            if len(data) == self.EEPROM16K_SIZE:
                self._data = bytearray(data)
                self._size = self.EEPROM16K_SIZE
                self._is_16k = True
                self._addr_bits = self.EEPROM16K_ADDR_BITS
            elif len(data) == self.EEPROM4K_SIZE:
                self._data = bytearray(data)
                self._size = self.EEPROM4K_SIZE
                self._is_16k = False
                self._addr_bits = self.EEPROM4K_ADDR_BITS
            else:
                self._data = bytearray(self._size)
                self._data[:len(data)] = data[:self._size]
            
            self._filepath = filepath
            self._dirty = False
            return True
        except Exception:
            return False
    
    def save_to_file(self, filepath: Optional[str] = None) -> bool:
        path = filepath or self._filepath
        if path is None:
            return False
        
        try:
            directory = os.path.dirname(path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            with open(path, "wb") as f:
                f.write(bytes(self._data))
            
            self._dirty = False
            self._filepath = path
            return True
        except Exception:
            return False
    
    def is_dirty(self) -> bool:
        return self._dirty
    
    def get_data(self) -> bytes:
        return bytes(self._data)
    
    def set_data(self, data: bytes) -> None:
        size = min(len(data), self._size)
        self._data[:size] = data[:size]
        if len(data) < self._size:
            self._data[size:] = b'\xFF' * (self._size - size)
        self._dirty = True


def create_eeprom_save(size: str = "4K") -> EepromSave:
    if size == "16K":
        return EepromSave(EepromSave.EEPROM16K_SIZE)
    return EepromSave(EepromSave.EEPROM4K_SIZE)

# === End of eeprom_save.py ===


# === Start of flash_save.py ===




class FlashSave:
    """FLASH save memory handler for GBA cartridges.
    
    Supports:
    - FLASH512: 512KB (8Mbit) with 2 banks of 256KB
    - FLASH1M: 1MB (16Mbit) with 2 banks of 512KB
    
    Memory map:
    - FLASH512: 8 x 32KB sectors per bank, 2 banks
    - FLASH1M: 8 x 64KB sectors per bank, 2 banks
    """
    
    FLASH512_SIZE = 512 * 1024
    FLASH1M_SIZE = 1024 * 1024
    
    FLASH512_SECTOR_SIZE = 32 * 1024
    FLASH1M_SECTOR_SIZE = 64 * 1024
    
    SECTORS_PER_BANK = 8
    
    CMD_UNLOCK1 = 0xAA
    CMD_UNLOCK2 = 0x55
    CMD_READ_ID = 0x90
    CMD_READ_STATUS = 0xF0
    CMD_WRITE_BYTE = 0xA0
    CMD_ERASE_SETUP = 0x80
    CMD_ERASE_SECTOR = 0x30
    CMD_ERASE_CHIP = 0x10
    CMD_BANK_SWITCH = 0xB0
    CMD_ERASE_CONTINUE = 0xD0
    
    CMD_ADDR1 = 0x5555
    CMD_ADDR2 = 0x2AAA
    
    MANUFACTURER_ID_PANASONIC = 0x1B
    MANUFACTURER_ID_SANYO = 0x1C
    MANUFACTURER_ID_MACRONIX = 0x1C
    DEVICE_ID_FLASH512 = 0x09
    DEVICE_ID_FLASH1M = 0x1C
    
    def __init__(self, size: int = FLASH512_SIZE):
        self._size = size
        self._is_1m = (size == self.FLASH1M_SIZE)
        
        self._sector_size = self.FLASH1M_SECTOR_SIZE if self._is_1m else self.FLASH512_SECTOR_SIZE
        self._num_sectors = self.SECTORS_PER_BANK * 2
        
        self._data = bytearray(self._size)
        self._current_bank = 0
        
        self._command_state = 0
        self._pending_command = None
        self._erase_address = None
        
        self._filepath: Optional[str] = None
        self._dirty = False
    
    @property
    def size(self) -> int:
        return self._size
    
    @property
    def is_1m(self) -> bool:
        return self._is_1m
    
    @property
    def sector_size(self) -> int:
        return self._sector_size
    
    def _get_bank_offset(self, bank: int) -> int:
        if self._is_1m:
            return bank * (self.FLASH1M_SIZE // 2)
        return bank * (self.FLASH512_SIZE // 2)
    
    def _translate_address(self, addr: int) -> int:
        offset = addr & 0xFFFF
        
        if self._is_1m:
            if offset >= 0x8000:
                offset = (offset & 0x7FFF) | (self._current_bank << 15)
        else:
            if offset >= 0x8000:
                offset = (offset & 0x7FFF) | (self._current_bank << 15)
        
        return offset
    
    def read(self, addr: int, length: int = 1) -> bytes:
        result = bytearray()
        
        for i in range(length):
            offset = self._translate_address(addr + i)
            if offset < self._size:
                result.append(self._data[offset])
            else:
                result.append(0xFF)
        
        return bytes(result)
    
    def write(self, addr: int, data: bytes) -> None:
        for i, byte in enumerate(data):
            self._write_byte(addr + i, byte)
    
    def _write_byte(self, addr: int, value: int) -> None:
        offset = addr & 0xFFFF
        
        if offset == self.CMD_ADDR1:
            if value == self.CMD_UNLOCK1:
                self._command_state = 1
                return
            elif value == self.CMD_READ_ID:
                if self._command_state == 2:
                    self._pending_command = self.CMD_READ_ID
                    self._command_state = 0
                    return
            elif value == self.CMD_ERASE_SETUP:
                if self._command_state == 2:
                    self._pending_command = self.CMD_ERASE_SETUP
                    self._command_state = 0
                    return
            elif value == self.CMD_ERASE_CHIP:
                if self._command_state == 2 and self._pending_command == self.CMD_ERASE_SETUP:
                    self._erase_chip()
                    self._pending_command = None
                    self._command_state = 0
                    return
        
        elif offset == self.CMD_ADDR2:
            if value == self.CMD_UNLOCK2:
                if self._command_state == 1:
                    self._command_state = 2
                    return
            elif value == self.CMD_WRITE_BYTE:
                if self._command_state == 2:
                    self._pending_command = self.CMD_WRITE_BYTE
                    self._command_state = 0
                    return
            elif value == self.CMD_ERASE_SECTOR:
                if self._command_state == 2 and self._pending_command == self.CMD_ERASE_SETUP:
                    if self._erase_address is not None:
                        self._erase_sector(self._erase_address)
                    self._pending_command = None
                    self._erase_address = None
                    self._command_state = 0
                    return
            elif value == self.CMD_ERASE_CONTINUE:
                if self._command_state == 2 and self._pending_command == self.CMD_ERASE_SETUP:
                    if self._erase_address is not None:
                        self._erase_sector(self._erase_address)
                    self._pending_command = None
                    self._erase_address = None
                    self._command_state = 0
                    return
        
        elif offset == 0xAAA and value == self.CMD_BANK_SWITCH:
            self._pending_command = self.CMD_BANK_SWITCH
            self._command_state = 0
            return
        
        elif addr >= 0x0A000000 and addr <= 0x0A00FFFF:
            if self._pending_command == self.CMD_BANK_SWITCH:
                self._current_bank = 1 if (value & 0x1) else 0
                self._pending_command = None
                return
            
            if self._pending_command == self.CMD_WRITE_BYTE:
                flash_offset = self._translate_address(addr)
                if flash_offset < self._size:
                    self._data[flash_offset] = value
                    self._dirty = True
                self._pending_command = None
                return
            
            if self._pending_command == self.CMD_ERASE_SETUP:
                self._erase_address = addr & 0xFFFF
                return
        
        self._command_state = 0
        self._pending_command = None
        
        flash_offset = self._translate_address(addr)
        if flash_offset < self._size:
            self._data[flash_offset] = value
            self._dirty = True
    
    def _erase_sector(self, addr: int) -> None:
        offset = addr & 0xFFFF
        
        if self._is_1m:
            if offset >= 0x8000:
                bank = 1
                offset = offset & 0x7FFF
            else:
                bank = 0
            sector = offset // self.FLASH1M_SECTOR_SIZE
        else:
            if offset >= 0x8000:
                bank = 1
                offset = offset & 0x7FFF
            else:
                bank = 0
            sector = offset // self.FLASH512_SECTOR_SIZE
        
        sector_offset = (bank * (self.SECTORS_PER_BANK * self._sector_size)) + (sector * self._sector_size)
        
        if sector_offset + self._sector_size <= self._size:
            for i in range(self._sector_size):
                self._data[sector_offset + i] = 0xFF
            self._dirty = True
    
    def _erase_chip(self) -> None:
        for i in range(self._size):
            self._data[i] = 0xFF
        self._dirty = True
    
    def read_id(self) -> int:
        if self._is_1m:
            return self.MANUFACTURER_ID_MACRONIX
        return self.MANUFACTURER_ID_PANASONIC
    
    def read_device_id(self) -> int:
        if self._is_1m:
            return self.DEVICE_ID_FLASH1M
        return self.DEVICE_ID_FLASH512
    
    def get_status(self) -> int:
        return 0x80
    
    def set_bank(self, bank: int) -> None:
        self._current_bank = bank & 1
    
    def get_bank(self) -> int:
        return self._current_bank
    
    def load_from_file(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            
            if len(data) == self.FLASH1M_SIZE:
                self._data = bytearray(data)
                self._size = self.FLASH1M_SIZE
                self._is_1m = True
                self._sector_size = self.FLASH1M_SECTOR_SIZE
            elif len(data) == self.FLASH512_SIZE:
                self._data = bytearray(data)
                self._size = self.FLASH512_SIZE
                self._is_1m = False
                self._sector_size = self.FLASH512_SECTOR_SIZE
            else:
                self._data = bytearray(self._size)
                self._data[:len(data)] = data[:self._size]
            
            self._filepath = filepath
            self._dirty = False
            return True
        except Exception:
            return False
    
    def save_to_file(self, filepath: Optional[str] = None) -> bool:
        path = filepath or self._filepath
        if path is None:
            return False
        
        try:
            directory = os.path.dirname(path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            with open(path, "wb") as f:
                f.write(bytes(self._data))
            
            self._dirty = False
            self._filepath = path
            return True
        except Exception:
            return False
    
    def is_dirty(self) -> bool:
        return self._dirty
    
    def get_data(self) -> bytes:
        return bytes(self._data)
    
    def set_data(self, data: bytes) -> None:
        size = min(len(data), self._size)
        self._data[:size] = data[:size]
        if len(data) < self._size:
            self._data[size:] = b'\xFF' * (self._size - size)
        self._dirty = True


def create_flash_save(size: str = "512KB") -> FlashSave:
    if size == "1MB":
        return FlashSave(FlashSave.FLASH1M_SIZE)
    return FlashSave(FlashSave.FLASH512_SIZE)

# === End of flash_save.py ===


# === Start of rom.py ===




class ROM:
    """Represents a loaded GBA ROM image with header parsing.

    Provides access to ROM data and parsed header fields including
    title, game code, maker code, and entry point.
    """

    # GBA ROM header offsets
    OFFSET_ENTRY_POINT = 0x00  # 4 bytes - ARM branch to start
    OFFSET_NINTENDO_LOGO = 0x04  # 156 bytes - compressed logo
    OFFSET_TITLE = 0xA0  # 12 bytes - game title (ASCII)
    OFFSET_GAME_CODE = 0xAC  # 4 bytes - game code
    OFFSET_MAKER_CODE = 0xB0  # 2 bytes - maker code
    OFFSET_ROM_SIZE = 0xB4  # 1 byte - ROM size code

    def __init__(self):
        """Create an empty ROM instance."""
        self._data: bytes = b""
        self._header: dict = {}

    def load(self, path: str) -> None:
        """Load a GBA ROM file from disk.

        Args:
            path: Path to the .gba file to load.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file is too small to contain a valid header.
        """
        with open(path, "rb") as f:
            self._data = f.read()

        if len(self._data) < 0xC0:
            raise ValueError(f"ROM file too small: {len(self._data)} bytes")

        self._parse_header()

    def _parse_header(self) -> None:
        """Parse the GBA ROM header and populate header dict."""
        # Entry point (4 bytes at 0x00)
        entry = int.from_bytes(self._data[0x00:0x04], "little")

        # Game title (12 bytes at 0xA0, null-padded ASCII)
        title_bytes = self._data[0xA0:0xAC]
        title = title_bytes.rstrip(b"\x00").decode("ascii", errors="replace")

        # Game code (4 bytes at 0xAC)
        game_code = self._data[0xAC:0xB0].decode("ascii", errors="replace")

        # Maker code (2 bytes at 0xB0)
        maker_code = self._data[0xB0:0xB2].decode("ascii", errors="replace")

        rom_size_code = self._data[0xB4]
        shift = rom_size_code & 0x0F
        if rom_size_code < 0x18 and shift < 16:
            rom_size = 0x80000 << shift
        else:
            rom_size = len(self._data)

        self._header = {
            "entry_point": entry,
            "title": title,
            "game_code": game_code,
            "maker_code": maker_code,
            "rom_size": rom_size,
        }

    def get_header(self) -> dict:
        """Return the parsed ROM header fields.

        Returns:
            Dictionary containing: entry_point, title, game_code,
            maker_code, rom_size.
        """
        return self._header.copy()

    @property
    def data(self) -> bytes:
        """Return the raw ROM data."""
        return self._data

    @property
    def title(self) -> str:
        """Return the game title (up to 12 bytes, null-padded)."""
        return self._header.get("title", "")

    @property
    def game_code(self) -> str:
        """Return the 4-character game code."""
        return self._header.get("game_code", "")

    @property
    def maker_code(self) -> str:
        """Return the 2-character maker code."""
        return self._header.get("maker_code", "")

    @property
    def rom_size(self) -> int:
        """Return the ROM size in bytes (0 if unknown)."""
        return self._header.get("rom_size", 0)

    @property
    def entry_point(self) -> int:
        """Return the entry point address (ARM branch instruction)."""
        return self._header.get("entry_point", 0)

    def read_bytes(self, offset: int, length: int) -> bytes:
        """Read raw bytes from the ROM at the given offset.

        Args:
            offset: Byte offset from start of ROM.
            length: Number of bytes to read.

        Returns:
            Bytes read (may be shorter if ROM ends).
        """
        return self._data[offset : offset + length]


# === End of rom.py ===


# === Start of save_state.py ===



# Version for future compatibility
VERSION = 1


class SaveState:
    """Save State class for complete emulator state serialization.
    
    Provides save(filepath) and load(filepath) methods to serialize and deserialize
    the complete emulator state including CPU, Memory, PPU, APU, DMA, Timers,
    Interrupts, and Input state.
    """
    
    def __init__(self, cpu=None, memory=None, ppu=None, apu=None, 
                 dma=None, timers=None, interrupts=None, input_state=None):
        """Initialize SaveState with emulator component references.
        
        Args:
            cpu: ARM7TDMI CPU instance
            memory: Memory instance
            ppu: PPU instance
            apu: APU instance
            dma: DMA instance
            timers: Timers instance
            interrupts: InterruptController instance
            input_state: Input instance
        """
        self.cpu = cpu
        self.memory = memory
        self.ppu = ppu
        self.apu = apu
        self.dma = dma
        self.timers = timers
        self.interrupts = interrupts
        self.input_state = input_state
    
    def save(self, filepath: str) -> bool:
        """Save complete emulator state to JSON file.
        
        Args:
            filepath: Path to save file
            
        Returns:
            True on success, False on error
        """
        try:
            state = {
                "version": VERSION,
                "cpu": self._save_cpu(),
                "memory": self._save_memory(),
                "ppu": self._save_ppu(),
                "apu": self._save_apu(),
                "dma": self._save_dma(),
                "timers": self._save_timers(),
                "interrupts": self._save_interrupts(),
                "input": self._save_input()
            }
            
            with open(filepath, 'w') as f:
                json.dump(state, f, indent=2)
            
            return True
        except Exception as e:
            print(f"Error saving state: {e}", file=sys.stderr)
            return False
    
    def load(self, filepath: str) -> bool:
        """Load complete emulator state from JSON file.
        
        Args:
            filepath: Path to save file
            
        Returns:
            True on success, False on error
        """
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            
            # Check version compatibility
            if state.get("version", 0) > VERSION:
                print(f"Warning: Save state version {state['version']} is newer than "
                      f"supported version {VERSION}", file=sys.stderr)
                return False
            
            # Restore all components
            if not self._load_cpu(state.get("cpu", {})):
                return False
            if not self._load_memory(state.get("memory", {})):
                return False
            if not self._load_ppu(state.get("ppu", {})):
                return False
            if not self._load_apu(state.get("apu", {})):
                return False
            if not self._load_dma(state.get("dma", {})):
                return False
            if not self._load_timers(state.get("timers", {})):
                return False
            if not self._load_interrupts(state.get("interrupts", {})):
                return False
            if not self._load_input(state.get("input", {})):
                return False
            
            return True
        except Exception as e:
            print(f"Error loading state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # CPU State
    # =========================================================================
    
    def _save_cpu(self) -> Dict[str, Any]:
        """Save CPU state."""
        if not self.cpu:
            return {}
        
        return {
            "registers": list(self.cpu.registers),  # r0-r15
            "cpsr": self.cpu.cpsr,
            "spsr": list(self.cpu.spsr),  # Saved PSR for each mode
            "mode": self.cpu.mode,
            "thumb_mode": self.cpu.thumb_mode,
            "running": self.cpu.running,
            "cycles": self.cpu.cycles
        }
    
    def _load_cpu(self, state: Dict[str, Any]) -> bool:
        """Load CPU state."""
        if not self.cpu or not state:
            return True
        
        try:
            self.cpu.registers = list(state.get("registers", [0] * 16))
            self.cpu.cpsr = state.get("cpsr", 0)
            self.cpu.spsr = list(state.get("spsr", [0] * 6))
            self.cpu.mode = state.get("mode", 0x1F)
            self.cpu.thumb_mode = state.get("thumb_mode", False)
            self.cpu.running = state.get("running", True)
            self.cpu.cycles = state.get("cycles", 0)
            return True
        except Exception as e:
            print(f"Error loading CPU state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # Memory State
    # =========================================================================
    
    def _save_memory(self) -> Dict[str, Any]:
        """Save Memory state."""
        if not self.memory:
            return {}
        
        return {
            "ewram": list(self.memory.ewram),
            "iwram": list(self.memory.iwram),
            "io": list(self.memory.io),
            "palette": list(self.memory.palette),
            "vram": list(self.memory.vram),
            "oam": list(self.memory.oam),
            "sram": list(self.memory.sram)
        }
    
    def _load_memory(self, state: Dict[str, Any]) -> bool:
        """Load Memory state."""
        if not self.memory or not state:
            return True
        
        try:
            # Convert lists back to bytearray for memory arrays
            ewram = state.get("ewram", [])
            if ewram:
                self.memory.ewram = list(ewram)
            
            iwram = state.get("iwram", [])
            if iwram:
                self.memory.iwram = list(iwram)
            
            io = state.get("io", [])
            if io:
                self.memory.io = list(io)
            
            palette = state.get("palette", [])
            if palette:
                self.memory.palette = list(palette)
            
            vram = state.get("vram", [])
            if vram:
                self.memory.vram = list(vram)
            
            oam = state.get("oam", [])
            if oam:
                self.memory.oam = list(oam)
            
            sram = state.get("sram", [])
            if sram:
                self.memory.sram = list(sram)
            
            return True
        except Exception as e:
            print(f"Error loading memory state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # PPU State
    # =========================================================================
    
    def _save_ppu(self) -> Dict[str, Any]:
        """Save PPU state."""
        if not self.ppu:
            return {}
        
        state = {}
        
        # Save PPU registers
        if hasattr(self.ppu, 'disp_cnt'):
            state["disp_cnt"] = self.ppu.disp_cnt
        if hasattr(self.ppu, 'disp_stat'):
            state["disp_stat"] = self.ppu.disp_stat
        if hasattr(self.ppu, 'v_count'):
            state["v_count"] = self.ppu.v_count
        
        # Save BG registers
        for i in range(4):
            bg_prefix = f"bg{i}"
            if hasattr(self.ppu, f'{bg_prefix}_cnt'):
                state[f'bg{i}_cnt'] = getattr(self.ppu, f'{bg_prefix}_cnt')
            if hasattr(self.ppu, f'{bg_prefix}_x'):
                state[f'bg{i}_x'] = getattr(self.ppu, f'{bg_prefix}_x')
            if hasattr(self.ppu, f'{bg_prefix}_y'):
                state[f'bg{i}_y'] = getattr(self.ppu, f'{bg_prefix}_y')
        
        # Save affine matrix parameters
        for i in range(2):
            for param in ['pa', 'pb', 'pc', 'pd', 'x', 'y']:
                attr_name = f'bg{i}_{param}'
                if hasattr(self.ppu, attr_name):
                    state[attr_name] = getattr(self.ppu, attr_name)
        
        # Save window registers
        for i in range(2):
            for attr in ['win0_h', 'win1_h', 'win0_v', 'win1_v', 'win_in', 'win_out']:
                attr_name = f'{attr}{i}' if i > 0 and attr.endswith(str(i-1)) else attr
                if hasattr(self.ppu, attr_name):
                    state[attr_name] = getattr(self.ppu, attr_name)
        
        # Save special effects
        for attr in ['blend_cnt', 'blend_alpha', 'blend_bright']:
            if hasattr(self.ppu, attr):
                state[attr] = getattr(self.ppu, attr)
        
        # Save mosaic
        if hasattr(self.ppu, 'mosaic_size'):
            state["mosaic_size"] = self.ppu.mosaic_size
        
        # Save framebuffer if available
        if hasattr(self.ppu, 'framebuffer'):
            fb = self.ppu.framebuffer
            if fb:
                state["framebuffer"] = list(fb)
        
        return state
    
    def _load_ppu(self, state: Dict[str, Any]) -> bool:
        """Load PPU state."""
        if not self.ppu or not state:
            return True
        
        try:
            # Load PPU registers
            if "disp_cnt" in state and hasattr(self.ppu, 'disp_cnt'):
                self.ppu.disp_cnt = state["disp_cnt"]
            if "disp_stat" in state and hasattr(self.ppu, 'disp_stat'):
                self.ppu.disp_stat = state["disp_stat"]
            if "v_count" in state and hasattr(self.ppu, 'v_count'):
                self.ppu.v_count = state["v_count"]
            
            # Load BG registers
            for i in range(4):
                bg_prefix = f"bg{i}"
                if f'bg{i}_cnt' in state and hasattr(self.ppu, f'{bg_prefix}_cnt'):
                    setattr(self.ppu, f'{bg_prefix}_cnt', state[f'bg{i}_cnt'])
                if f'bg{i}_x' in state and hasattr(self.ppu, f'{bg_prefix}_x'):
                    setattr(self.ppu, f'{bg_prefix}_x', state[f'bg{i}_x'])
                if f'bg{i}_y' in state and hasattr(self.ppu, f'{bg_prefix}_y'):
                    setattr(self.ppu, f'{bg_prefix}_y', state[f'bg{i}_y'])
            
            # Load affine matrix parameters
            for i in range(2):
                for param in ['pa', 'pb', 'pc', 'pd', 'x', 'y']:
                    attr_name = f'bg{i}_{param}'
                    if attr_name in state and hasattr(self.ppu, attr_name):
                        setattr(self.ppu, attr_name, state[attr_name])
            
            # Load window registers
            for attr in ['win0_h', 'win1_h', 'win0_v', 'win1_v', 'win_in', 'win_out']:
                if attr in state and hasattr(self.ppu, attr):
                    setattr(self.ppu, attr, state[attr])
            
            # Load special effects
            for attr in ['blend_cnt', 'blend_alpha', 'blend_bright']:
                if attr in state and hasattr(self.ppu, attr):
                    setattr(self.ppu, attr, state[attr])
            
            # Load mosaic
            if "mosaic_size" in state and hasattr(self.ppu, 'mosaic_size'):
                self.ppu.mosaic_size = state["mosaic_size"]
            
            # Load framebuffer
            if "framebuffer" in state and hasattr(self.ppu, 'framebuffer'):
                fb_data = state["framebuffer"]
                if fb_data and self.ppu.framebuffer:
                    self.ppu.framebuffer = list(fb_data)
            
            return True
        except Exception as e:
            print(f"Error loading PPU state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # APU State
    # =========================================================================
    
    def _save_apu(self) -> Dict[str, Any]:
        """Save APU state."""
        if not self.apu:
            return {}
        
        state = {}
        
        # Save master control
        if hasattr(self.apu, 'sound_on'):
            state["sound_on"] = self.apu.sound_on
        
        # Save all 4 channels
        for i in range(4):
            ch_prefix = f"ch{i + 1}"
            if hasattr(self.apu, f'{ch_prefix}_volume'):
                state[f'ch{i+1}_volume'] = getattr(self.apu, f'{ch_prefix}_volume')
            if hasattr(self.apu, f'{ch_prefix}_frequency'):
                state[f'ch{i+1}_frequency'] = getattr(self.apu, f'{ch_prefix}_frequency')
            if hasattr(self.apu, f'{ch_prefix}_duty_cycle'):
                state[f'ch{i+1}_duty_cycle'] = getattr(self.apu, f'{ch_prefix}_duty_cycle')
            if hasattr(self.apu, f'{ch_prefix}_envelope_volume'):
                state[f'ch{i+1}_envelope_volume'] = getattr(self.apu, f'{ch_prefix}_envelope_volume')
            if hasattr(self.apu, f'{ch_prefix}_envelope_direction'):
                state[f'ch{i+1}_envelope_direction'] = getattr(self.apu, f'{ch_prefix}_envelope_direction')
            if hasattr(self.apu, f'{ch_prefix}_envelope_steps'):
                state[f'ch{i+1}_envelope_steps'] = getattr(self.apu, f'{ch_prefix}_envelope_steps')
            if hasattr(self.apu, f'{ch_prefix}_enabled'):
                state[f'ch{i+1}_enabled'] = getattr(self.apu, f'{ch_prefix}_enabled')
            if hasattr(self.apu, f'{ch_prefix}_wave'):
                state[f'ch{i+1}_wave'] = list(getattr(self.apu, f'{ch_prefix}_wave', []))
        
        # Save FIFO buffers
        for fifo in ['a', 'b']:
            if hasattr(self.apu, f'fifo_{fifo}'):
                state[f'fifo_{fifo}'] = list(getattr(self.apu, f'fifo_{fifo}', []))
        
        # Save wave RAM
        if hasattr(self.apu, 'wave_ram'):
            state["wave_ram"] = list(self.apu.wave_ram)
        
        # Save master volume
        if hasattr(self.apu, 'master_volume'):
            state["master_volume"] = self.apu.master_volume
        
        return state
    
    def _load_apu(self, state: Dict[str, Any]) -> bool:
        """Load APU state."""
        if not self.apu or not state:
            return True
        
        try:
            # Load master control
            if "sound_on" in state and hasattr(self.apu, 'sound_on'):
                self.apu.sound_on = state["sound_on"]
            
            # Load all 4 channels
            for i in range(4):
                ch_prefix = f"ch{i + 1}"
                if f'ch{i+1}_volume' in state and hasattr(self.apu, f'{ch_prefix}_volume'):
                    setattr(self.apu, f'{ch_prefix}_volume', state[f'ch{i+1}_volume'])
                if f'ch{i+1}_frequency' in state and hasattr(self.apu, f'{ch_prefix}_frequency'):
                    setattr(self.apu, f'{ch_prefix}_frequency', state[f'ch{i+1}_frequency'])
                if f'ch{i+1}_duty_cycle' in state and hasattr(self.apu, f'{ch_prefix}_duty_cycle'):
                    setattr(self.apu, f'{ch_prefix}_duty_cycle', state[f'ch{i+1}_duty_cycle'])
                if f'ch{i+1}_envelope_volume' in state and hasattr(self.apu, f'{ch_prefix}_envelope_volume'):
                    setattr(self.apu, f'{ch_prefix}_envelope_volume', state[f'ch{i+1}_envelope_volume'])
                if f'ch{i+1}_envelope_direction' in state and hasattr(self.apu, f'{ch_prefix}_envelope_direction'):
                    setattr(self.apu, f'{ch_prefix}_envelope_direction', state[f'ch{i+1}_envelope_direction'])
                if f'ch{i+1}_envelope_steps' in state and hasattr(self.apu, f'{ch_prefix}_envelope_steps'):
                    setattr(self.apu, f'{ch_prefix}_envelope_steps', state[f'ch{i+1}_envelope_steps'])
                if f'ch{i+1}_enabled' in state and hasattr(self.apu, f'{ch_prefix}_enabled'):
                    setattr(self.apu, f'{ch_prefix}_enabled', state[f'ch{i+1}_enabled'])
                if f'ch{i+1}_wave' in state and hasattr(self.apu, f'{ch_prefix}_wave'):
                    setattr(self.apu, f'{ch_prefix}_wave', list(state[f'ch{i+1}_wave']))
            
            # Load FIFO buffers
            for fifo in ['a', 'b']:
                if f'fifo_{fifo}' in state and hasattr(self.apu, f'fifo_{fifo}'):
                    setattr(self.apu, f'fifo_{fifo}', list(state[f'fifo_{fifo}']))
            
            # Load wave RAM
            if "wave_ram" in state and hasattr(self.apu, 'wave_ram'):
                self.apu.wave_ram = list(state["wave_ram"])
            
            # Load master volume
            if "master_volume" in state and hasattr(self.apu, 'master_volume'):
                self.apu.master_volume = state["master_volume"]
            
            return True
        except Exception as e:
            print(f"Error loading APU state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # DMA State
    # =========================================================================
    
    def _save_dma(self) -> Dict[str, Any]:
        """Save DMA state."""
        if not self.dma:
            return {}
        
        state = {}
        
        # Save all 4 DMA channels
        for i in range(4):
            ch = f"ch{i}"
            if hasattr(self.dma, ch):
                channel = getattr(self.dma, ch)
                if channel:
                    state[f'channel{i}'] = {
                        "src_addr": channel.src_addr if hasattr(channel, 'src_addr') else 0,
                        "dst_addr": channel.dst_addr if hasattr(channel, 'dst_addr') else 0,
                        "control": channel.control if hasattr(channel, 'control') else 0,
                        "enabled": channel.enabled if hasattr(channel, 'enabled') else False,
                    }
        
        return state
    
    def _load_dma(self, state: Dict[str, Any]) -> bool:
        """Load DMA state."""
        if not self.dma or not state:
            return True
        
        try:
            # Load all 4 DMA channels
            for i in range(4):
                ch = f"ch{i}"
                if hasattr(self.dma, ch):
                    channel = getattr(self.dma, ch)
                    if channel and f'channel{i}' in state:
                        ch_state = state[f'channel{i}']
                        if hasattr(channel, 'src_addr'):
                            channel.src_addr = ch_state.get("src_addr", 0)
                        if hasattr(channel, 'dst_addr'):
                            channel.dst_addr = ch_state.get("dst_addr", 0)
                        if hasattr(channel, 'control'):
                            channel.control = ch_state.get("control", 0)
                        if hasattr(channel, 'enabled'):
                            channel.enabled = ch_state.get("enabled", False)
            
            return True
        except Exception as e:
            print(f"Error loading DMA state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # Timer State
    # =========================================================================
    
    def _save_timers(self) -> Dict[str, Any]:
        """Save Timer state."""
        if not self.timers:
            return {}
        
        state = {}
        
        # Save all 4 timers
        for i in range(4):
            ch = f"timer{i}"
            if hasattr(self.timers, ch):
                timer = getattr(self.timers, ch)
                if timer:
                    state[f'timer{i}'] = {
                        "count": timer.count if hasattr(timer, 'count') else 0,
                        "control": timer.control if hasattr(timer, 'control') else 0,
                        "reload": timer.reload if hasattr(timer, 'reload') else 0,
                    }
        
        return state
    
    def _load_timers(self, state: Dict[str, Any]) -> bool:
        """Load Timer state."""
        if not self.timers or not state:
            return True
        
        try:
            # Load all 4 timers
            for i in range(4):
                ch = f"timer{i}"
                if hasattr(self.timers, ch):
                    timer = getattr(self.timers, ch)
                    if timer and f'timer{i}' in state:
                        timer_state = state[f'timer{i}']
                        if hasattr(timer, 'count'):
                            timer.count = timer_state.get("count", 0)
                        if hasattr(timer, 'control'):
                            timer.control = timer_state.get("control", 0)
                        if hasattr(timer, 'reload'):
                            timer.reload = timer_state.get("reload", 0)
            
            return True
        except Exception as e:
            print(f"Error loading timer state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # Interrupt State
    # =========================================================================
    
    def _save_interrupts(self) -> Dict[str, Any]:
        """Save Interrupt state."""
        if not self.interrupts:
            return {}
        
        state = {}
        
        # Save interrupt registers
        if hasattr(self.interrupts, 'ie'):
            state["ie"] = self.interrupts.ie
        if hasattr(self.interrupts, 'if_reg'):
            state["if"] = self.interrupts.if_reg
        if hasattr(self.interrupts, 'ime'):
            state["ime"] = self.interrupts.ime
        
        # Save pending flags
        if hasattr(self.interrupts, 'pending'):
            state["pending"] = self.interrupts.pending
        
        return state
    
    def _load_interrupts(self, state: Dict[str, Any]) -> bool:
        """Load Interrupt state."""
        if not self.interrupts or not state:
            return True
        
        try:
            # Load interrupt registers
            if "ie" in state and hasattr(self.interrupts, 'ie'):
                self.interrupts.ie = state["ie"]
            if "if" in state:
                if hasattr(self.interrupts, 'if_reg'):
                    self.interrupts.if_reg = state["if"]
            if "ime" in state and hasattr(self.interrupts, 'ime'):
                self.interrupts.ime = state["ime"]
            
            # Load pending flags
            if "pending" in state and hasattr(self.interrupts, 'pending'):
                self.interrupts.pending = state["pending"]
            
            return True
        except Exception as e:
            print(f"Error loading interrupt state: {e}", file=sys.stderr)
            return False
    
    # =========================================================================
    # Input State
    # =========================================================================
    
    def _save_input(self) -> Dict[str, Any]:
        """Save Input state."""
        if not self.input_state:
            return {}
        
        state = {}
        
        # Save key input
        if hasattr(self.input_state, 'key_input'):
            state["key_input"] = self.input_state.key_input
        elif hasattr(self.input_state, 'keys'):
            state["key_input"] = self.input_state.keys
        
        # Save key control
        if hasattr(self.input_state, 'key_cnt'):
            state["key_cnt"] = self.input_state.key_cnt
        
        return state
    
    def _load_input(self, state: Dict[str, Any]) -> bool:
        """Load Input state."""
        if not self.input_state or not state:
            return True
        
        try:
            # Load key input
            if "key_input" in state:
                if hasattr(self.input_state, 'key_input'):
                    self.input_state.key_input = state["key_input"]
                elif hasattr(self.input_state, 'keys'):
                    self.input_state.keys = state["key_input"]
            
            # Load key control
            if "key_cnt" in state and hasattr(self.input_state, 'key_cnt'):
                self.input_state.key_cnt = state["key_cnt"]
            
            return True
        except Exception as e:
            print(f"Error loading input state: {e}", file=sys.stderr)
            return False


def create_save_state(cpu=None, memory=None, ppu=None, apu=None,
                     dma=None, timers=None, interrupts=None, input_state=None) -> SaveState:
    """Create a SaveState instance with emulator component references.
    
    Convenience function to create a SaveState instance.
    
    Args:
        cpu: ARM7TDMI CPU instance
        memory: Memory instance
        ppu: PPU instance
        apu: APU instance
        dma: DMA instance
        timers: Timers instance
        interrupts: InterruptController instance
        input_state: Input instance
    
    Returns:
        SaveState instance
    """
    return SaveState(cpu, memory, ppu, apu, dma, timers, interrupts, input_state)

# === End of save_state.py ===


# === Start of serial.py ===

class Serial:
    REG_SIOCNT = 0x04000128
    REG_SIODATA8 = 0x0400012A
    REG_SIOMULTI0 = 0x04000120
    REG_SIOMULTI1 = 0x04000122
    REG_SIOMULTI2 = 0x04000124
    REG_SIOMULTI3 = 0x04000126
    REG_SIOMLT_SEND = 0x0400012A
    REG_SIOSTAT = 0x04000128
    REG_SIOCNT = 0x0400012C

    def __init__(self, memory):
        self.memory = memory
        self.sio_mode = 0
        self.transfer_enabled = False
        self.clock_select = 0
        self.receive_data = 0
        self.send_data = 0
        self.multi_player_id = 0
        self.multi_player_data = [0, 0, 0, 0]
        self.busy_flag = False
        self.error_flag = False
        self.uart_mode = 0
        self.uart_receive_data = 0
        self.gpio_direction = 0
        self.gpio_data = 0

    def write_register(self, addr: int, value: int):
        if addr == 0x04000120:
            self.multi_player_data[0] = value & 0xFFFF
        elif addr == 0x04000122:
            self.multi_player_data[1] = value & 0xFFFF
        elif addr == 0x04000124:
            self.multi_player_data[2] = value & 0xFFFF
        elif addr == 0x04000126:
            self.multi_player_data[3] = value & 0xFFFF
        elif addr == 0x04000128:
            self._write_siocnt(value)
        elif addr == 0x0400012A:
            self.send_data = value & 0xFFFF
            if self.sio_mode == 0:
                self._uart_transfer()
        elif addr == 0x0400012C:
            self._write_siocnt(value)

    def _write_siocnt(self, value: int):
        self.sio_mode = (value >> 12) & 0x3
        self.transfer_enabled = bool((value >> 7) & 1)
        self.clock_select = (value >> 0) & 0x3
        self.multi_player_id = (value >> 8) & 0x3

    def _uart_transfer(self):
        self.busy_flag = True
        self.receive_data = self.send_data
        self.busy_flag = False

    def read_register(self, addr: int) -> int:
        if addr == 0x04000120:
            if self.sio_mode == 1:
                return self.multi_player_data[0]
            return self.receive_data & 0xFFFF
        elif addr == 0x04000122:
            if self.sio_mode == 1:
                return self.multi_player_data[1]
            return (self.receive_data >> 8) & 0xFF
        elif addr == 0x04000124:
            if self.sio_mode == 1:
                return self.multi_player_data[2]
            return 0xFF  # Unconnected
        elif addr == 0x04000126:
            if self.sio_mode == 1:
                return self.multi_player_data[3]
            return 0xFF
        elif addr == 0x04000128:
            return self._read_siocnt()
        elif addr == 0x0400012A:
            if self.sio_mode == 0:
                return self.receive_data & 0xFFFF
            return self.send_data & 0xFFFF
        elif addr == 0x0400012C:
            return self._read_siocnt()
        return 0xFF

    def _read_siocnt(self) -> int:
        value = 0
        value |= self.sio_mode << 12
        value |= self.multi_player_id << 8
        value |= int(self.transfer_enabled) << 7
        value |= self.clock_select
        value |= int(self.busy_flag) << 3
        value |= int(self.error_flag) << 2
        return value & 0xFFFF


# === End of serial.py ===


# === Start of rtc.py ===




class RTC:
    """Real-Time Clock implementation for GBA games."""
    
    # MMIO register addresses
    REG_RTC_SI = 0x04000134  # Serial input data
    REG_RTC_SO = 0x04000136  # Serial output data  
    REG_RTC_SCK = 0x04000138  # Serial clock
    REG_RTC_CS = 0x0400013C  # Chip select
    
    # RTC commands
    CMD_READ_STATUS1 = 0x6E
    CMD_READ_STATUS2 = 0x6A
    CMD_READ_TIME = 0x66
    CMD_READ_DATE = 0x62
    CMD_WRITE_TIME = 0x80
    CMD_WRITE_DATE = 0x82
    CMD_WRITE_STATUS = 0xA0
    
    # Status register bits
    STATUS1_24H = 0x40  # 24-hour mode
    STATUS1_POWER = 0x20  # Power on
    STATUS1_RESET = 0x10  # Reset
    STATUS1_STOP = 0x08  # Stop oscillator
    
    def __init__(self, memory, state_file: str = "rtc_state.json"):
        self.memory = memory
        self.state_file = state_file
        
        # RTC state
        self.seconds = 0
        self.minutes = 0
        self.hours = 0
        self.day = 1
        self.month = 1
        self.year = 0  # 00-99 (2000-2099)
        
        # Status registers
        self.status1 = self.STATUS1_POWER | self.STATUS1_24H
        self.status2 = 0x00
        
        # Serial communication state
        self.bit_count = 0
        self.command = 0
        self.data_buffer = 0
        self.transfer_count = 0
        self.current_operation = None  # 'read' or 'write'
        self.read_data = 0
        
        # Base time for calculating elapsed time (stored as offset from epoch)
        self.base_timestamp: float = 0.0
        self.base_realtime: float = 0.0
        self.so_value: int = 0
        
        # Load persisted state
        self._load_state()
        
        # Register MMIO handlers
        self._register_mmio()
    
    def _register_mmio(self):
        """Register RTC MMIO handlers with memory system."""
        self.memory.register_mmio_read(self.REG_RTC_SI - 0x04000000, self._read_si)
        self.memory.register_mmio_read(self.REG_RTC_SO - 0x04000000, self._read_so)
        self.memory.register_mmio_read(self.REG_RTC_SCK - 0x04000000, self._read_sck)
        self.memory.register_mmio_read(self.REG_RTC_CS - 0x04000000, self._read_cs)
        
        self.memory.register_mmio_write(self.REG_RTC_SI - 0x04000000, self._write_si)
        self.memory.register_mmio_write(self.REG_RTC_SO - 0x04000000, self._write_so)
        self.memory.register_mmio_write(self.REG_RTC_SCK - 0x04000000, self._write_sck)
        self.memory.register_mmio_write(self.REG_RTC_CS - 0x04000000, self._write_cs)
    
    def _read_si(self, addr: int) -> int:
        """Read from SI register."""
        return 0
    
    def _read_so(self, addr: int) -> int:
        """Read from SO register - returns serial output data."""
        if self.bit_count > 0 and self.bit_count <= 8:
            # Return the MSB of read_data
            return (self.read_data >> (8 - self.bit_count)) & 1
        return 0
    
    def _read_sck(self, addr: int) -> int:
        """Read from SCK register."""
        return 0
    
    def _read_cs(self, addr: int) -> int:
        """Read from CS register."""
        return 0
    
    def _write_si(self, addr: int, value: int):
        """Write to SI register - serial input."""
        si_bit = value & 1
        
        if self.bit_count == 0:
            # First bit of command
            self.command = si_bit << 7
            self.bit_count = 1
        elif self.bit_count < 8:
            # Continue building command
            self.command |= si_bit << (7 - self.bit_count)
            self.bit_count += 1
            
            if self.bit_count == 8:
                self._process_command()
    
    def _write_so(self, addr: int, value: int):
        """Write to SO register - no operation (SO is output only)."""
        # SO is a read-only output pin, writes are ignored
        # But we track the value for debugging/logging purposes
        self.so_value = value
    
    def _write_sck(self, addr: int, value: int):
        """Write to SCK register - clock pulse."""
        # SCK rising edge triggers data transfer
        if value & 1:
            # Rising edge - process data
            if self.bit_count > 0:
                self._clock_tick()
    
    def _write_cs(self, addr: int, value: int):
        """Write to CS register - chip select."""
        if value & 1:
            # CS high - reset transfer
            self._reset_transfer()
    
    def _clock_tick(self):
        """Process a clock tick for data transfer."""
        if self.current_operation == 'read' and self.transfer_count < 8:
            # Shift read_data left and add 0 (SO is pulled high internally)
            self.read_data = (self.read_data << 1) & 0xFF
            self.transfer_count += 1
        elif self.current_operation == 'write' and self.transfer_count < 8:
            # Collect write data - SI bit is already in self.command LSB during write
            # We need to read the SI bit from the SI register
            si_bit = (self.memory.read_u16(self.REG_RTC_SI - 0x04000000) & 1)
            self.data_buffer = (self.data_buffer << 1) | si_bit
            self.transfer_count += 1
            
            # Check if we've received a complete byte
            if self.transfer_count == 8:
                self._handle_write_byte()
    
    def _process_command(self):
        """Process the received RTC command."""
        cmd = self.command
        
        if cmd == self.CMD_READ_STATUS1:
            self.read_data = self.status1
            self.current_operation = 'read'
            self.transfer_count = 0
        elif cmd == self.CMD_READ_STATUS2:
            self.read_data = self.status2
            self.current_operation = 'read'
            self.transfer_count = 0
        elif cmd == self.CMD_READ_TIME:
            # Pack time: seconds, minutes, hours (BCD format)
            self.read_data = self._pack_time()
            self.current_operation = 'read'
            self.transfer_count = 0
        elif cmd == self.CMD_READ_DATE:
            # Pack date: day, month, year (BCD format)
            self.read_data = self._pack_date()
            self.current_operation = 'read'
            self.transfer_count = 0
        elif (cmd & 0xF0) == self.CMD_WRITE_TIME:
            # Write time command - prepare to receive 3 bytes (seconds, minutes, hours)
            self.current_operation = 'write'
            self.data_buffer = 0
            self.transfer_count = 0
            self.write_buffer = []
            self.write_command = cmd
        elif (cmd & 0xF0) == self.CMD_WRITE_DATE:
            # Write date command - prepare to receive 3 bytes (day, month, year)
            self.current_operation = 'write'
            self.data_buffer = 0
            self.transfer_count = 0
            self.write_buffer = []
            self.write_command = cmd
        elif cmd == self.CMD_WRITE_STATUS:
            # Write status register - receive 1 byte
            self.current_operation = 'write'
            self.data_buffer = 0
            self.transfer_count = 0
            self.write_buffer = []
            self.write_command = cmd
        else:
            # Unknown command - reset
            self._reset_transfer()
    
    def _pack_time(self) -> int:
        """Pack time data into byte (seconds | minutes | hours in BCD)."""
        sec_bcd = self._int_to_bcd(self.seconds)
        min_bcd = self._int_to_bcd(self.minutes)
        hour_bcd = self._int_to_bcd(self.hours)
        return ((hour_bcd & 0x3F) << 8) | ((min_bcd & 0x7F) << 4) | (sec_bcd & 0x7F)
    
    def _pack_date(self) -> int:
        """Pack date data into byte (day | month | year in BCD)."""
        day_bcd = self._int_to_bcd(self.day)
        month_bcd = self._int_to_bcd(self.month)
        year_bcd = self._int_to_bcd(self.year)
        return ((year_bcd & 0xFF) << 8) | ((month_bcd & 0x1F) << 4) | (day_bcd & 0x3F)
    
    def _unpack_time(self, data: int):
        """Unpack time data from byte."""
        self.seconds = self._bcd_to_int(data & 0x7F)
        self.minutes = self._bcd_to_int((data >> 4) & 0x7F)
        self.hours = self._bcd_to_int((data >> 8) & 0x3F)
    
    def _unpack_date(self, data: int):
        """Unpack date data from byte."""
        self.day = self._bcd_to_int(data & 0x3F)
        self.month = self._bcd_to_int((data >> 4) & 0x1F)
        self.year = self._bcd_to_int((data >> 8) & 0xFF)
    
    def _int_to_bcd(self, value: int) -> int:
        """Convert integer to BCD format."""
        tens = value // 10
        ones = value % 10
        return (tens << 4) | ones
    
    def _bcd_to_int(self, bcd: int) -> int:
        """Convert BCD to integer."""
        tens = (bcd >> 4) & 0x0F
        ones = bcd & 0x0F
        return tens * 10 + ones
    
    def _reset_transfer(self):
        """Reset transfer state machine."""
        self.bit_count = 0
        self.command = 0
        self.data_buffer = 0
        self.transfer_count = 0
        self.current_operation = None
        self.read_data = 0
        self.write_buffer = []
        self.write_command = 0
    
    def _is_leap_year(self, year: int) -> bool:
        """Check if a year is a leap year."""
        full_year = 2000 + year
        if full_year % 400 == 0:
            return True
        if full_year % 100 == 0:
            return False
        return full_year % 4 == 0
    
    def _get_days_in_month(self, month: int, year: int) -> int:
        """Get number of days in a given month."""
        days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        if month == 2 and self._is_leap_year(year):
            return 29
        return days[month - 1]
    
    def update_time(self):
        """Update RTC time based on elapsed real time."""
        if self.base_timestamp == 0.0:
            # First call - initialize
            self.base_timestamp = time.time()
            self.base_realtime = time.time()
            self._sync_from_system()
            return
        
        # Calculate elapsed time since base
        current_time = time.time()
        elapsed = current_time - self.base_realtime
        
        if elapsed > 0:
            # Add elapsed time to stored timestamp
            self.base_timestamp += elapsed
            self.base_realtime = current_time
            self._sync_from_timestamp()
    
    def _sync_from_system(self):
        """Sync RTC time from system time."""
        now = datetime.now()
        self.seconds = now.second
        self.minutes = now.minute
        self.hours = now.hour
        self.day = now.day
        self.month = now.month
        self.year = now.year % 100
        
        # Store current system time as base
        self.base_timestamp = now.timestamp()
        self.base_realtime = time.time()
    
    def _sync_from_timestamp(self):
        """Sync RTC time from stored timestamp."""
        dt = datetime.fromtimestamp(self.base_timestamp)
        self.seconds = dt.second
        self.minutes = dt.minute
        self.hours = dt.hour
        self.day = dt.day
        self.month = dt.month
        self.year = dt.year % 100
    
    def _handle_write_byte(self):
        """Handle a complete byte received during write operation."""
        # Store the byte in write buffer
        self.write_buffer.append(self.data_buffer)
        
        # Determine how many bytes we need based on command
        if self.write_command == self.CMD_WRITE_STATUS:
            # Status register: 1 byte
            if len(self.write_buffer) >= 1:
                self._apply_write_status()
        elif self.write_command == self.CMD_WRITE_TIME:
            # Time: 3 bytes (seconds, minutes, hours)
            if len(self.write_buffer) >= 3:
                self._apply_write_time()
        elif self.write_command == self.CMD_WRITE_DATE:
            # Date: 3 bytes (day, month, year)
            if len(self.write_buffer) >= 3:
                self._apply_write_date()
        
        # Reset for next byte
        self.data_buffer = 0
        self.transfer_count = 0
    
    def _apply_write_status(self):
        """Apply written status register value."""
        if len(self.write_buffer) >= 1:
            status = self.write_buffer[0]
            # Update status1 register
            self.status1 = status
            
            # Handle STOP bit (bit 3)
            if status & self.STATUS1_STOP:
                # Clock stopped - don't update time
                pass
            else:
                # Clock running - time updates normally
                pass
            
            # Handle RESET bit (bit 4)
            if status & self.STATUS1_RESET:
                # Reset time to initial values
                self.seconds = 0
                self.minutes = 0
                self.hours = 0
                self.day = 1
                self.month = 1
                self.year = 0
                # Clear reset bit after reset
                self.status1 &= ~self.STATUS1_RESET
    
    def _apply_write_time(self):
        """Apply written time values."""
        if len(self.write_buffer) >= 3:
            # Bytes are: seconds, minutes, hours
            self._unpack_time(self.write_buffer[0])
            self._unpack_time((self.write_buffer[1] << 8) | self.write_buffer[0])  # Reuse unpack logic
            
            # Actually unpack properly
            self.seconds = self._bcd_to_int(self.write_buffer[0] & 0x7F)
            self.minutes = self._bcd_to_int(self.write_buffer[1] & 0x7F)
            self.hours = self._bcd_to_int(self.write_buffer[2] & 0x3F)
            
            # Reset base timestamp to match new time
            now = time.time()
            dt = datetime.now()
            dt = dt.replace(hour=self.hours, minute=self.minutes, second=self.seconds, microsecond=0)
            self.base_timestamp = dt.timestamp()
            self.base_realtime = now
    
    def _apply_write_date(self):
        """Apply written date values."""
        if len(self.write_buffer) >= 3:
            # Bytes are: day, month, year
            self.day = self._bcd_to_int(self.write_buffer[0] & 0x3F)
            self.month = self._bcd_to_int(self.write_buffer[1] & 0x1F)
            self.year = self._bcd_to_int(self.write_buffer[2] & 0xFF)
            
            # Reset base timestamp to match new date
            now = time.time()
            dt = datetime.now()
            dt = dt.replace(year=2000 + self.year, month=self.month, day=self.day, microsecond=0)
            self.base_timestamp = dt.timestamp()
            self.base_realtime = now
    
    def _load_state(self):
        """Load RTC state from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.base_timestamp = state.get('base_timestamp', 0.0)
                    self.seconds = state.get('seconds', 0)
                    self.minutes = state.get('minutes', 0)
                    self.hours = state.get('hours', 0)
                    self.day = state.get('day', 1)
                    self.month = state.get('month', 1)
                    self.year = state.get('year', 0)
                    self.status1 = state.get('status1', self.STATUS1_POWER | self.STATUS1_24H)
                    self.status2 = state.get('status2', 0)
                    
                    # Sync from stored timestamp
                    if self.base_timestamp > 0:
                        self._sync_from_timestamp()
                    else:
                        self._sync_from_system()
            except (json.JSONDecodeError, IOError):
                self._sync_from_system()
        else:
            self._sync_from_system()
    
    def save_state(self):
        """Save RTC state to file."""
        # Update time before saving
        self.update_time()
        
        state = {
            'base_timestamp': self.base_timestamp,
            'seconds': self.seconds,
            'minutes': self.minutes,
            'hours': self.hours,
            'day': self.day,
            'month': self.month,
            'year': self.year,
            'status1': self.status1,
            'status2': self.status2
        }
        
        with open(self.state_file, 'w') as f:
            json.dump(state, f)
    
    def get_time_string(self) -> str:
        """Get current RTC time as string."""
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}"
    
    def get_date_string(self) -> str:
        """Get current RTC date as string."""
        return f"20{self.year:02d}-{self.month:02d}-{self.day:02d}"


def detect_rtc(rom_data: bytes) -> bool:
    """
    Auto-detect if ROM uses RTC.
    
    Checks for known RTC game identifiers in ROM header or game code.
    Common RTC games: Pokemon Gold/Silver, Mario Artist, Boktai, etc.
    """
    if rom_data is None or len(rom_data) < 0x100:
        return False
    
    # Check for known RTC game identifiers
    rtc_identifiers = [
        b'GOLD',      # Pokemon Gold
        b'SILVER',    # Pokemon Silver
        b'POKEMON',   # Pokemon (various)
        b'MARIO ARTIST',  # Mario Artist
        b'BOKTAI',    # Boktai
        b'KAGUYA',    # Kaguya
        b'MOON',      # Kaguya
    ]
    
    # Search in ROM header and game title area
    search_area = rom_data[:0x100000]  # Search first 1MB
    
    for identifier in rtc_identifiers:
        if identifier in search_area:
            return True
    
    # Check for RTC hardware detection code patterns
    # Games that use RTC typically access 0x04000134-0x0400013F
    # This is a heuristic check
    
    return False


def create_rtc(memory, rom_data: Optional[bytes] = None, state_file: str = "rtc_state.json") -> Optional[RTC]:
    """
    Create and initialize RTC if needed.
    
    Args:
        memory: Memory object for MMIO registration
        rom_data: ROM data for auto-detection
        state_file: Path to state file
        
    Returns:
        RTC instance if RTC detected or forced, None otherwise
    """
    if rom_data is not None and not detect_rtc(rom_data):
        return None
    
    return RTC(memory, state_file)

# === End of rtc.py ===


# === Start of exceptions.py ===

class GameError(Exception):
    pass


class GBARuntimeError(GameError):
    pass


class InvalidRom(GameError):
    pass


class InvalidROMError(InvalidRom):
    pass


class InvalidAddress(GameError):
    pass


__all__ = ["GameError", "GBARuntimeError", "InvalidRom", "InvalidROMError", "InvalidAddress"]


# === End of exceptions.py ===


# === Start of numba.py ===

try:
    _HAS_NUMBA = True
except ImportError:
    njit = None
    prange = None
    _HAS_NUMBA = False

_NUMBA_ENABLED = False


def jit_compile(func):
    if not _HAS_NUMBA or not _NUMBA_ENABLED:
        return func
    try:
        return njit(func, cache=True, fastmath=True)
    except Exception:
        return func


def set_numba_enabled(enabled: bool):
    global _NUMBA_ENABLED
    _NUMBA_ENABLED = enabled and _HAS_NUMBA


def is_numba_available() -> bool:
    return _HAS_NUMBA

# === End of numba.py ===


# === Start of text_lib.py ===




# Glyph data per caratteri ASCII 32-126 (95 caratteri)
# Convertito da test_roms/gba-tests-master/lib/glyphs.asm
# Each glyph is 8 bytes (8x8 pixel, 2 bit per pixel)
GLYPHS = {
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    '!': [0x00, 0x00, 0x18, 0x18, 0x00, 0x18, 0x00, 0x00],
    '"': [0x00, 0x00, 0x36, 0x36, 0x00, 0x00, 0x00, 0x00],
    '#': [0x00, 0x00, 0x36, 0x7F, 0x36, 0x36, 0x7F, 0x3C],
    '$': [0x06, 0x1B, 0x35, 0x66, 0x00, 0x00, 0x33, 0x56],
    '%': [0x6C, 0x6E, 0x16, 0x36, 0x1C, 0x00, 0x00, 0xDE],
    '&': [0x73, 0x3B, 0x00, 0x0C, 0x18, 0x18, 0x00, 0x0C],
    "'": [0x0C, 0x18, 0x18, 0x00, 0x0C, 0x0C, 0x18, 0x30],
    '(': [0x00, 0x30, 0x18, 0x0C, 0x0C, 0x18, 0x30, 0x18],
    ')': [0x0C, 0x18, 0x30, 0x18, 0x18, 0x30, 0x18, 0x0C],
    '*': [0x00, 0x30, 0x0C, 0x7E, 0x0C, 0x30, 0x00, 0x00],
    '+': [0x00, 0x18, 0x18, 0x7E, 0x18, 0x18, 0x00, 0x00],
    ',': [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x00, 0x00],
    '-': [0x00, 0x00, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00],
    '/': [0x00, 0x00, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x00],
    '0': [0x3C, 0x66, 0x66, 0x6E, 0x76, 0x66, 0x66, 0x3C],
    '1': [0x18, 0x38, 0x18, 0x18, 0x18, 0x18, 0x18, 0x7E],
    '2': [0x3C, 0x66, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x7E],
    '3': [0x3C, 0x66, 0x06, 0x0C, 0x06, 0x66, 0x3C, 0x00],
    '4': [0x0C, 0x1C, 0x3C, 0x6C, 0x7E, 0x0C, 0x0C, 0x1E],
    '5': [0x7E, 0x40, 0x7C, 0x06, 0x06, 0x66, 0x3C, 0x00],
    '6': [0x1C, 0x36, 0x60, 0x7C, 0x66, 0x66, 0x3C, 0x00],
    '7': [0x7E, 0x06, 0x0C, 0x18, 0x18, 0x18, 0x18, 0x00],
    '8': [0x3C, 0x66, 0x66, 0x3C, 0x66, 0x66, 0x3C, 0x00],
    '9': [0x3C, 0x66, 0x66, 0x3E, 0x06, 0x0C, 0x78, 0x00],
    ':': [0x00, 0x00, 0x66, 0x00, 0x00, 0x66, 0x00, 0x00],
    ';': [0x00, 0x00, 0x66, 0x00, 0x00, 0x66, 0x06, 0x0C],
    '<': [0x00, 0x30, 0x0C, 0x06, 0x0C, 0x30, 0x00, 0x00],
    '=': [0x00, 0x00, 0x7E, 0x00, 0x00, 0x7E, 0x00, 0x00],
    '>': [0x00, 0x0C, 0x30, 0x60, 0x30, 0x0C, 0x00, 0x00],
    '?': [0x3C, 0x66, 0x06, 0x0C, 0x18, 0x00, 0x18, 0x00],
    '@': [0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'A': [0x18, 0x3C, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x00],
    'B': [0x7C, 0x66, 0x66, 0x7C, 0x66, 0x66, 0x7C, 0x00],
    'C': [0x3C, 0x66, 0x60, 0x60, 0x60, 0x66, 0x3C, 0x00],
    'D': [0x78, 0x6C, 0x66, 0x66, 0x66, 0x6C, 0x78, 0x00],
    'E': [0x7E, 0x60, 0x60, 0x7C, 0x60, 0x60, 0x7E, 0x00],
    'F': [0x7E, 0x60, 0x60, 0x7C, 0x60, 0x60, 0x60, 0x00],
    'G': [0x3C, 0x66, 0x60, 0x7E, 0x66, 0x66, 0x3C, 0x00],
    'H': [0x66, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
    'I': [0x3C, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'J': [0x06, 0x06, 0x06, 0x06, 0x06, 0x66, 0x3C, 0x00],
    'K': [0x66, 0x6C, 0x78, 0x70, 0x78, 0x6C, 0x66, 0x00],
    'L': [0x60, 0x60, 0x60, 0x60, 0x60, 0x60, 0x7E, 0x00],
    'M': [0x63, 0x77, 0x7F, 0x6B, 0x63, 0x63, 0x63, 0x00],
    'N': [0x66, 0x6E, 0x76, 0x7E, 0x66, 0x66, 0x66, 0x00],
    'O': [0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'P': [0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60, 0x60, 0x00],
    'Q': [0x3C, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x06, 0x0C],
    'R': [0x7C, 0x66, 0x66, 0x7C, 0x78, 0x6C, 0x66, 0x00],
    'S': [0x3C, 0x66, 0x60, 0x3C, 0x06, 0x66, 0x3C, 0x00],
    'T': [0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00],
    'U': [0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'V': [0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
    'W': [0x63, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x63, 0x00],
    'X': [0x66, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0x66, 0x00],
    'Y': [0x66, 0x66, 0x66, 0x3C, 0x18, 0x18, 0x18, 0x00],
    'Z': [0x7E, 0x46, 0x0C, 0x18, 0x30, 0x62, 0x7E, 0x00],
    '[': [0x3C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x3C, 0x00],
    '\\': [0x60, 0x30, 0x18, 0x0C, 0x06, 0x03, 0x01, 0x00],
    ']': [0x3C, 0x30, 0x30, 0x30, 0x30, 0x30, 0x3C, 0x00],
    '^': [0x00, 0x00, 0x18, 0x18, 0x00, 0x18, 0x18, 0x00],
    '_': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7E],
    '`': [0x0C, 0x18, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00],
    'a': [0x00, 0x00, 0x3C, 0x06, 0x3E, 0x66, 0x3E, 0x00],
    'b': [0x00, 0x60, 0x60, 0x7C, 0x66, 0x66, 0x7C, 0x00],
    'c': [0x00, 0x00, 0x3C, 0x60, 0x60, 0x60, 0x3C, 0x00],
    'd': [0x00, 0x06, 0x06, 0x3E, 0x66, 0x66, 0x3E, 0x00],
    'e': [0x00, 0x00, 0x3C, 0x66, 0x7E, 0x60, 0x3C, 0x00],
    'f': [0x18, 0x30, 0x7E, 0x30, 0x30, 0x30, 0x00, 0x00],
    'g': [0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x7C],
    'h': [0x00, 0x60, 0x60, 0x7C, 0x66, 0x66, 0x66, 0x00],
    'i': [0x00, 0x00, 0x18, 0x00, 0x18, 0x18, 0x3C, 0x00],
    'j': [0x00, 0x06, 0x00, 0x06, 0x06, 0x06, 0x3E, 0x00],
    'k': [0x00, 0x60, 0x60, 0x6C, 0x78, 0x6C, 0x60, 0x00],
    'l': [0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'm': [0x00, 0x00, 0x66, 0x7F, 0x6B, 0x63, 0x63, 0x00],
    'n': [0x00, 0x00, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x00],
    'o': [0x00, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'p': [0x00, 0x00, 0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60],
    'q': [0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x06],
    'r': [0x00, 0x00, 0x66, 0x6C, 0x78, 0x60, 0x60, 0x00],
    's': [0x00, 0x00, 0x3E, 0x40, 0x3C, 0x06, 0x7C, 0x00],
    't': [0x00, 0x18, 0x18, 0x3E, 0x18, 0x18, 0x0C, 0x00],
    'u': [0x00, 0x00, 0x66, 0x66, 0x66, 0x66, 0x3E, 0x00],
    'v': [0x00, 0x00, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
    'w': [0x00, 0x00, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x00],
    'x': [0x00, 0x00, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0x00],
    'y': [0x00, 0x00, 0x66, 0x66, 0x66, 0x3E, 0x06, 0x7C],
    'z': [0x00, 0x00, 0x7E, 0x40, 0x30, 0x0C, 0x7E, 0x00],
    '{': [0x0C, 0x18, 0x18, 0x30, 0x18, 0x18, 0x0C, 0x00],
    '|': [0x18, 0x18, 0x18, 0x00, 0x18, 0x18, 0x18, 0x00],
    '}': [0x30, 0x18, 0x18, 0x0C, 0x18, 0x18, 0x30, 0x00],
    '~': [0x00, 0x00, 0x00, 0x76, 0x7F, 0x4B, 0x00, 0x00],
}

_memory_ref = None


def _set_memory(mem):
    global _memory_ref
    _memory_ref = mem


def text_init(memory=None):
    """
    Inizializza la modalità video 4 (320x240 8-bit color) con BG2 attivo.

    Assembly originale:
        text_init:
            mov r0, 4                   ; Background mode 4
            orr r0, 1 shl 10            ; Background 2
            mov r1, MEM_IO              ; 0x04000000
            strh r0, [r1, REG_DISPCNT]  ; DISPCNT = 0x1404

    Effect:
        - Imposta display mode 4 (320x240 bitmap)
        - Abilita Background 2
        - DISPCNT = 0x1404 (Mode 4 + BG2 on)

    Args:
        memory: Optional Memory instance. If None, uses global GBA runtime.
    """
    # Mode 4 = 320x240 8-bit color bitmap
    # Bit 10 = BG2 enable
    # DISPCNT = 0x1404 = 0b0001010000000100
    #   Bits 0-2: Mode 4
    #   Bit 10: BG2 enable
    dispcnt_value = 0x1404

    if memory is not None:
        # Use provided memory instance (for testing)
        memory.write_u16(0x04000000, dispcnt_value)
    else:
        # Use global GBA runtime memory
        if _memory_ref is None:
            raise RuntimeError('gba_runtime._memory not initialized. Call text_lib._set_memory() first.')
        _memory_ref.write_u16(0x04000000, dispcnt_value)


def text_color(color: int, index: int, memory=None):
    """
    Imposta un colore nella palette a un indice specifico.

    Assembly originale:
        text_color:
            ; r0: color (16-bit RGB555)
            ; r1: index (0-255)
            lsl r1, 1                   ; index *= 2 (each entry is 2 bytes)
            mov r2, MEM_PALETTE         ; 0x05000000
            strh r0, [r2, r1]           ; palette[index] = color

    Effect:
        - Scrive il colore 16-bit alla posizione palette[index]
    - Each palette entry is 2 bytes (16-bit RGB555)
    - Address = 0x05000000 + (index * 2)

    Args:
        color: 16-bit RGB555 color (0x0000-0xFFFF)
        index: palette index (0-255)        memory: Optional Memory instance. If None, uses global GBA runtime.
    """
    # Each palette entry is 2 bytes
    palette_offset = index * 2
    palette_addr = 0x05000000 + palette_offset

    if memory is not None:
        memory.write_u16(palette_addr, color)
    else:
        if _memory_ref is None:
            raise RuntimeError('gba_runtime._memory not initialized. Call text_lib._set_memory() first.')
        _memory_ref.write_u16(palette_addr, color)


def m_vsync(memory=None):
    """
    Attende il prossimo VBlank (sincronizzazione frame).

    Assembly originale (macro m_vsync):
        .vblank_end:
            ldr r1, [r0, REG_DISPSTAT]
            tst r1, STAT_VBLANK_FLG
            bne .vblank_end             ; Loop until NOT in vblank

        .vblank_beg:
            ldr r1, [r0, REG_DISPSTAT]
            tst r1, STAT_VBLANK_FLG
            beq .vblank_beg             ; Loop until IN vblank

    Effect:
        - Attende la fine del VBlank corrente
        - Attende l'inizio del prossimo VBlank
        - Ritorna quando siamo in VBlank

    Args:
        memory: Optional Memory instance. If None, uses global GBA runtime.
    """
    dispstat_addr = 0x04000004  # REG_DISPSTAT
    vblank_flag = 0x0001  # STAT_VBLANK_FLG (bit 0 of DISPSTAT)

    if memory is not None:
        mem = memory
    else:
        if _memory_ref is None:
            raise RuntimeError('gba_runtime._memory not initialized. Call text_lib._set_memory() first.')
        mem = _memory_ref

    # Wait until NOT in VBlank (bit 0 = 0)
    while mem.read_u16(dispstat_addr) & vblank_flag:
        time.sleep(0.001)  # Busy-wait: poll until VBlank flag clears

    # Wait until IN VBlank (bit 0 = 1)
    while not (mem.read_u16(dispstat_addr) & vblank_flag):
        time.sleep(0.001)  # Busy-wait: poll until VBlank flag sets


def text_glyph_data(data: int, vram_ptr: int, memory=None):
    """
    Converte 32 bit di dati in 32 pixel (2 bit per pixel) e scrive in VRAM.

    Assembly originale:
        text_glyph_data:
            ; r0: data (32-bit), modified
            ; r1: pointer (VRAM address), modified
            mov r2, 0                   ; Loop counter
        .loop:
            and r3, r0, 1               ; First bit
            lsr r0, 1
            and r4, r0, 1               ; Second bit
            lsr r0, 1
            orr r3, r4, ror 24          ; Combine bits
            strh r3, [r1], 2            ; Write 2 pixels, advance
            add r2, 2
            tst r2, 7                   ; Line end?
            addeq r1, 232               ; Move to next line
            cmp r2, 32
            bne .loop

    Args:
        data: 32-bit glyph data (16 pixel × 2 bit)
        vram_ptr: indirizzo VRAM di destinazione
        memory: Optional Memory instance. If None, uses global GBA runtime.
    """
    if memory is not None:
        mem = memory
    else:
        if _memory_ref is None:
            raise RuntimeError('gba_runtime._memory not initialized. Call text_lib._set_memory() first.')
        mem = _memory_ref

    current_ptr = vram_ptr

    for i in range(16):
        # Estrai 2 bit per pixel
        pixel0 = data & 1
        data >>= 1
        pixel1 = data & 1
        data >>= 1

        # Combina in valore 2-bit (come l'assembly: ror 24)
        pixel_val = pixel0 | (pixel1 << 24)

        # Scrivi 2 pixel (2 byte)
        mem.write_u16(current_ptr, pixel_val & 0xFFFF)
        current_ptr += 2

        # Line wrap every 8 pixels (4 iterations)
        if (i + 1) % 4 == 0:
            current_ptr += 232


def text_glyph(x: int, y: int, data_upper: int, data_lower: int, memory=None):
    """
    Renderizza un glyph 8x8 a due colori in VRAM.

    Assembly originale:
        text_glyph:
            ; r0: x
            ; r1: y
            ; r2: glyph data upper
            ; r3: glyph data lower
            mov r4, 240
            mla r4, r4, r1, r0          ; offset = y * 240 + x
            add r4, MEM_VRAM            ; vram_addr = 0x06000000 + offset
            mov r0, r2
            mov r1, r4
            bl text_glyph_data          ; Render first half
            mov r0, r3
            mov r1, r4
            bl text_glyph_data          ; Render second half

    Args:
        x: coordinata X nella VRAM
        y: coordinata Y nella VRAM
        data_upper: primi 32 bit del glyph
        data_lower: ultimi 32 bit del glyph
        memory: Optional Memory instance. If None, uses global GBA runtime.
    """
    offset = y * 240 + x
    vram_addr = 0x06000000 + offset

    text_glyph_data(data_upper, vram_addr, memory)
    text_glyph_data(data_lower, vram_addr, memory)


def text_char(x: int, y: int, char: str, memory=None) -> int:
    """
    Renderizza un carattere ASCII a una posizione.

    Assembly originale:
        text_char:
            ; r0: x, modified
            ; r1: y
            ; r2: char (ASCII)
            sub r2, 32                  ; char -= 32
            lsl r2, 3                   ; glyph_offset = char * 8
            adr r3, glyphs              ; Load glyphs base
            add r3, r2
            ldmia r3, {r2, r3}          ; Load 8 bytes (2 words)
            bl text_glyph               ; Render glyph
            add r0, 8                   ; x += 8

    Args:
        x: coordinata X
        y: coordinata Y
        char: carattere ASCII (32-127)
        memory: Optional Memory instance. If None, uses global GBA runtime.

    Returns:
        Nuova coordinata X (x + 8)
    """
    glyph_index = ord(char) - 32

    if glyph_index < 0 or glyph_index >= len(GLYPHS):
        return x + 8

    glyph_bytes = GLYPHS[char]
    data_upper = (glyph_bytes[0] << 24) | (glyph_bytes[1] << 16) | (glyph_bytes[2] << 8) | glyph_bytes[3]
    data_lower = (glyph_bytes[4] << 24) | (glyph_bytes[5] << 16) | (glyph_bytes[6] << 8) | glyph_bytes[7]

    text_glyph(x, y, data_upper, data_lower, memory)

    return x + 8


# === End of text_lib.py ===
