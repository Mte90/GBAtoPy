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
        
        # Affine background parameters (8 params × 2 bytes each)
        self._affine_params = bytearray(16)

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
        self.iwram[0x7FFC - 0x03000000] = isr_addr & 0xFF
        self.iwram[0x7FFD - 0x03000000] = (isr_addr >> 8) & 0xFF
        self.iwram[0x7FFE - 0x03000000] = (isr_addr >> 16) & 0xFF
        self.iwram[0x7FFF - 0x03000000] = (isr_addr >> 24) & 0xFF

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

    def read_u16(self, addr: int) -> int:
        """Read 16-bit unsigned value"""
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)
        
        lo = self.read_u8(addr)
        hi = self.read_u8(addr + 1)
        return lo | (hi << 8)
    
    def read_32(self, addr: int) -> int:
        """Read 32-bit unsigned value"""
        addr &= 0xFFFFFFFF
        addr = self._map_address(addr)
        
        b0 = self.read_u8(addr)
        b1 = self.read_u8(addr + 1)
        b2 = self.read_u8(addr + 2)
        b3 = self.read_u8(addr + 3)
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
    def read_u32(self, addr: int) -> int:
        """Read 32-bit unsigned value"""
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
