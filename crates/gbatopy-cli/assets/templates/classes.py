# GBA Runtime Classes
# Extracted from pipeline_cmd.rs for modularity

class GBA:
    """GBA system with memory mapping and MMIO support"""
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


class MemorySimple:
    """Minimal Memory class for PPU-only rendering (no full GBA system)"""
    def __init__(self, vram, palette):
        self.vram = vram
        self.palette = palette
    
    def read_8(self, addr):
        if addr < len(self.vram):
            return self.vram[addr]
        return 0
    
    def read_16(self, addr):
        if addr + 1 < len(self.vram):
            return self.vram[addr] | (self.vram[addr + 1] << 8)
        return 0
    
    def read_32(self, addr):
        if addr + 3 < len(self.vram):
            return (self.vram[addr] | (self.vram[addr + 1] << 8) |
                   (self.vram[addr + 2] << 16) | (self.vram[addr + 3] << 24))
        return 0
    
    def write_8(self, addr, value):
        if addr < len(self.vram):
            self.vram[addr] = value & 0xFF
    
    def write_16(self, addr, value):
        if addr < len(self.vram):
            self.vram[addr] = value & 0xFF
            if addr + 1 < len(self.vram):
                self.vram[addr + 1] = (value >> 8) & 0xFF
    
    def write_32(self, addr, value):
        if addr < len(self.vram):
            self.vram[addr] = value & 0xFF
            if addr + 1 < len(self.vram):
                self.vram[addr + 1] = (value >> 8) & 0xFF
            if addr + 2 < len(self.vram):
                self.vram[addr + 2] = (value >> 16) & 0xFF
            if addr + 3 < len(self.vram):
                self.vram[addr + 3] = (value >> 24) & 0xFF
