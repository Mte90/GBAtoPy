//! GBA Memory Map Implementation
#![allow(dead_code)]
//!
//! Memory layout:
//! - 0x00000000-0x00003FFF: BIOS ROM (16KB)
//! - 0x02000000-0x0203FFFF: EWRAM (256KB)
//! - 0x03000000-0x03007FFF: IWRAM (32KB)
//! - 0x04000000-0x040003FF: MMIO registers
//! - 0x05000000-0x050003FF: Palette RAM
//! - 0x06000000-0x06017FFF: VRAM
//! - 0x07000000-0x070003FF: OAM
//! - 0x08000000-0x09FFFFFF: ROM (up to 32MB)

use std::collections::HashMap;

pub struct GBA {
    pub bios: Vec<u8>,  // 16KB
    pub ewram: Vec<u8>, // 256KB
    pub iwram: Vec<u8>, // 32KB
    pub mmio: HashMap<u16, u8>,
    pub palette: Vec<u8>, // 1KB
    pub vram: Vec<u8>,    // 96KB
    pub oam: Vec<u8>,     // 1KB
    pub rom: Vec<u8>,     // up to 32MB
}

impl GBA {
    pub fn new(rom_data: Vec<u8>) -> Self {
        GBA {
            bios: vec![0; 0x4000],
            ewram: vec![0; 0x40000],
            iwram: vec![0; 0x8000],
            mmio: HashMap::new(),
            palette: vec![0; 0x400],
            vram: vec![0; 0x18000],
            oam: vec![0; 0x400],
            rom: rom_data,
        }
    }

    pub fn read_8(&self, addr: u32) -> u8 {
        match addr {
            0x00000000..=0x00003FFF => {
                let offset = (addr - 0x00000000) as usize;
                if offset < self.bios.len() {
                    self.bios[offset]
                } else {
                    0
                }
            }
            0x02000000..=0x0203FFFF => {
                let offset = (addr - 0x02000000) as usize;
                if offset < self.ewram.len() {
                    self.ewram[offset]
                } else {
                    0
                }
            }
            0x03000000..=0x03007FFF => {
                let offset = (addr - 0x03000000) as usize;
                if offset < self.iwram.len() {
                    self.iwram[offset]
                } else {
                    0
                }
            }
            0x04000000..=0x040003FF => {
                let offset = (addr - 0x04000000) as u16;
                *self.mmio.get(&offset).unwrap_or(&0)
            }
            0x05000000..=0x050003FF => {
                let offset = (addr - 0x05000000) as usize;
                if offset < self.palette.len() {
                    self.palette[offset]
                } else {
                    0
                }
            }
            0x06000000..=0x06017FFF => {
                let offset = (addr - 0x06000000) as usize;
                if offset < self.vram.len() {
                    self.vram[offset]
                } else {
                    0
                }
            }
            0x07000000..=0x070003FF => {
                let offset = (addr - 0x07000000) as usize;
                if offset < self.oam.len() {
                    self.oam[offset]
                } else {
                    0
                }
            }
            0x08000000..=0x09FFFFFF => {
                let offset = (addr - 0x08000000) as usize;
                if offset < self.rom.len() {
                    self.rom[offset]
                } else {
                    0
                }
            }
            _ => 0,
        }
    }

    pub fn read_32(&self, addr: u32) -> u32 {
        let b0 = self.read_8(addr) as u32;
        let b1 = self.read_8(addr + 1) as u32;
        let b2 = self.read_8(addr + 2) as u32;
        let b3 = self.read_8(addr + 3) as u32;
        b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
    }

    pub fn write_8(&mut self, addr: u32, value: u8) {
        match addr {
            0x02000000..=0x0203FFFF => {
                let offset = (addr - 0x02000000) as usize;
                if offset < self.ewram.len() {
                    self.ewram[offset] = value;
                }
            }
            0x03000000..=0x03007FFF => {
                let offset = (addr - 0x03000000) as usize;
                if offset < self.iwram.len() {
                    self.iwram[offset] = value;
                }
            }
            0x04000000..=0x040003FF => {
                let offset = (addr - 0x04000000) as u16;
                self.mmio.insert(offset, value);
                // MMIO side effects would be handled here (DISPCNT, BGxCNT, etc.)
            }
            0x05000000..=0x050003FF => {
                let offset = (addr - 0x05000000) as usize;
                if offset < self.palette.len() {
                    self.palette[offset] = value;
                }
            }
            0x06000000..=0x06017FFF => {
                let offset = (addr - 0x06000000) as usize;
                if offset < self.vram.len() {
                    self.vram[offset] = value;
                }
            }
            0x07000000..=0x070003FF => {
                let offset = (addr - 0x07000000) as usize;
                if offset < self.oam.len() {
                    self.oam[offset] = value;
                }
            }
            _ => {}
        }
    }

    pub fn write_32(&mut self, addr: u32, value: u32) {
        self.write_8(addr, (value & 0xFF) as u8);
        self.write_8(addr + 1, ((value >> 8) & 0xFF) as u8);
        self.write_8(addr + 2, ((value >> 16) & 0xFF) as u8);
        self.write_8(addr + 3, ((value >> 24) & 0xFF) as u8);
    }
}
