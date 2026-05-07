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
        self.bios = bytearray(MemoryMap.BIOS_SIZE)
        self.ewram = bytearray(MemoryMap.EWRAM_SIZE)
        self.iwram = bytearray(MemoryMap.IWRAM_SIZE)
        self.io = bytearray(MemoryMap.IO_SIZE)
        self.palette = bytearray(MemoryMap.PALETTE_SIZE)
        self.vram = bytearray(MemoryMap.VRAM_SIZE)
        self.oam = bytearray(MemoryMap.OAM_SIZE)
        self.sram = bytearray(MemoryMap.SRAM_SIZE)

        self.rom: Optional[bytearray] = None
        self.rom_size: int = 0
        self.open_bus: int = 0

        self._mmio_write_handlers: dict[int, Callable[[int, int], None]] = {}
        self._mmio_read_handlers: dict[int, Callable[[int], int]] = {}

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

    def attach_ppu(self, ppu):
        self._ppu = ppu

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
        if 0x0400004E <= addr <= 0x0400005F:
            if self._apu:
                self._apu.write_register(addr, value)
        elif 0x04000060 <= addr <= 0x040000A7:
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
        if addr == 0x04000130:
            if self._input:
                return self._input.get_keys()
        return None

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
            self._dma.channels[channel].enabled = (value & 0x80000000) != 0

    def _handle_timer_write(self, addr: int, value: int):
        base = 0x04000100
        if addr < base or addr > 0x0400010F:
            return
        timer_idx = (addr - base) // 4
        reg_offset = (addr - base) % 4
        if timer_idx < 0 or timer_idx > 3:
            return
        if reg_offset == 0:
            self._timers.set_timer(timer_idx, value & 0xFFFF)
        elif reg_offset == 2:
            self._timers.set_control(timer_idx, value & 0xFFFF)

    def _handle_interrupt_write(self, addr: int, value: int):
        if addr == 0x04000200:
            self._interrupts.write_ie(value)
        elif addr == 0x04000204:
            self._interrupts.write_if(value)
        elif addr == 0x04000208:
            self._interrupts.write_ime(value)

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

    def read_u16(self, addr: int) -> int:
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)

        lo = self.read_u8(addr)
        hi = self.read_u8(addr + 1)
        return lo | (hi << 8)

    def read_u32(self, addr: int) -> int:
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)

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
        self.rom = bytearray(data)
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
