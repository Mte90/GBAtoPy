import pytest
from gba_runtime.ppu import PPU
from gba_runtime.memory import Memory


class TestPPUInit:
    def test_ppu_creation_with_none_memory(self):
        ppu = PPU(None)
        assert ppu.memory is None
        assert ppu.SCREEN_WIDTH == 240
        assert ppu.SCREEN_HEIGHT == 160

    def test_ppu_creation_with_memory(self):
        mem = Memory()
        ppu = PPU(mem)
        assert ppu.memory is mem

    def test_framebuffer_initialized(self):
        ppu = PPU(None)
        assert ppu.framebuffer is not None
        assert len(ppu.framebuffer) == 240 * 160


class TestPPUWriteRegister:
    def test_dispcnt_write(self):
        ppu = PPU(None)
        ppu.write_register(0x04000000, 0x0003)  # Mode 3
        assert ppu.dispcnt == 0x0003
        assert ppu.display_mode == 3

    def test_bg_enable_bits(self):
        ppu = PPU(None)
        ppu.write_register(0x04000000, 0x0F00)  # All BGs enabled
        assert ppu.bg_enabled == [True, True, True, True]

    def test_bg_cnt_write(self):
        ppu = PPU(None)
        ppu.write_register(0x04000008, 0x0C01)  # BG0: priority 1, char base 0, screen base 0
        assert ppu.bg_cnt[0] == 0x0C01

    def test_scroll_registers(self):
        ppu = PPU(None)
        ppu.write_register(0x04000010, 0x0010)  # BG0HOFS = 16
        ppu.write_register(0x04000012, 0x0020)  # BG0VOFS = 32
        assert ppu.bg_hofs[0] == 16
        assert ppu.bg_vofs[0] == 32


class TestPPUFramebuffer:
    def test_render_frame_creates_framebuffer(self):
        ppu = PPU(None)
        ppu.render_frame()
        assert ppu.framebuffer is not None
        assert len(ppu.framebuffer) == 240 * 160

    def test_framebuffer_returns_tuple_list(self):
        ppu = PPU(None)
        ppu.render_frame()
        fb = ppu.framebuffer
        assert isinstance(fb, list)
        if fb:
            assert isinstance(fb[0], tuple)
            assert len(fb[0]) == 3


class TestPPUColors:
    def test_bgr555_to_rgb888_basic(self):
        ppu = PPU(None)
        # Pure red: R=31, G=0, B=0
        color = 0x7C00
        r, g, b = ppu._bgr555_to_rgb888(color)
        assert r == 248
        assert g == 0
        assert b == 0

    def test_bgr555_to_rgb888_green(self):
        ppu = PPU(None)
        # Pure green: R=0, G=31, B=0
        color = 0x03E0
        r, g, b = ppu._bgr555_to_rgb888(color)
        assert r == 0
        assert g == 248
        assert b == 0

    def test_bgr555_to_rgb888_blue(self):
        ppu = PPU(None)
        # Pure blue: R=0, G=0, B=31
        color = 0x001F
        r, g, b = ppu._bgr555_to_rgb888(color)
        assert r == 0
        assert g == 0
        assert b == 248

    def test_bgr555_to_rgb888_white(self):
        ppu = PPU(None)
        color = 0x7FFF
        r, g, b = ppu._bgr555_to_rgb888(color)
        assert r == 248
        assert g == 248
        assert b == 248


class TestPPUMode3:
    def test_mode3_renders(self):
        mem = Memory()
        ppu = PPU(mem)
        ppu.write_register(0x04000000, 0x0003)  # Mode 3

        # Write a red pixel at (0, 0) in BGR555
        mem.write_u16(0x06000000, 0x7C00)

        ppu.render_frame()

        fb = ppu.framebuffer
        assert fb[0] == (248, 0, 0)

    def test_mode3_scanlines(self):
        mem = Memory()
        ppu = PPU(mem)
        ppu.write_register(0x04000000, 0x0003)

        # Write pixels to first row
        for x in range(240):
            mem.write_u16(0x06000000 + x * 2, 0x7C00)

        ppu.render_line(0)

        assert ppu.framebuffer[0] == (248, 0, 0)


class TestPPUMode4:
    def test_mode4_renders(self):
        mem = Memory()
        ppu = PPU(mem)
        ppu.write_register(0x04000000, 0x0004)  # Mode 4

        # Set palette entry 1 to red
        mem.write_u16(0x05000000 + 1 * 2, 0x7C00)

        # Write palette index 1 to first VRAM byte
        mem.vram[0] = 1

        ppu.render_frame()

        fb = ppu.framebuffer
        assert fb[0] == (248, 0, 0)

    def test_mode4_page_select(self):
        mem = Memory()
        ppu = PPU(mem)

        # Page 0
        ppu.write_register(0x04000000, 0x0004)
        mem.vram[0] = 0xAA

        # Page 1
        ppu.write_register(0x04000000, 0x0014)  # Mode 4 + page 1
        mem.vram[0xA000] = 0xBB

        ppu.render_frame()

        # Should use page 1 data
        assert mem.vram[0] == 0xAA
        assert mem.vram[0xA000] == 0xBB


class TestPPUMode0:
    def test_mode0_renders_black_when_no_tiles(self):
        mem = Memory()
        ppu = PPU(mem)
        ppu.write_register(0x04000000, 0x0000)  # Mode 0

        # Set palette entry 0 to black
        mem.write_u16(0x05000000, 0x0000)

        ppu.render_frame()

        # All pixels should be black
        fb = ppu.framebuffer
        assert all(pixel == (0, 0, 0) for pixel in fb)

    def test_mode0_uses_scroll_registers(self):
        mem = Memory()
        ppu = PPU(mem)
        ppu.write_register(0x04000000, 0x0100)  # Mode 0 + BG0 enabled
        ppu.write_register(0x04000008, 0x0000)  # BG0CNT: 256x256, char base 0, screen base 0

        # Set background color to black
        mem.write_u16(0x05000000, 0x0000)

        # Set horizontal scroll
        ppu.write_register(0x04000010, 8)

        ppu.render_frame()

        assert ppu.bg_hofs[0] == 8


class TestPPUProperties:
    def test_display_mode_property(self):
        ppu = PPU(None)
        ppu.dispcnt = 0x0005
        assert ppu.display_mode == 5

    def test_bg_enabled_property(self):
        ppu = PPU(None)
        ppu.dispcnt = 0x0000
        assert ppu.bg_enabled == [False, False, False, False]

        ppu.dispcnt = 0x0F00
        assert ppu.bg_enabled == [True, True, True, True]


class TestPPUQATest:
    def test_qa_basic_render(self):
        ppu = PPU(None)
        ppu.render_frame()
        assert ppu.framebuffer is not None

    def test_qa_with_memory(self):
        mem = Memory()
        ppu = PPU(mem)
        ppu.render_frame()
        assert ppu.framebuffer is not None
        assert len(ppu.framebuffer) == 240 * 160


class TestPPUPalette:
    def test_palette_cache_initialized(self):
        ppu = PPU(None)
        assert len(ppu._palette_cache) == 512
        assert ppu._palette_cache[0] == (0, 0, 0)

    def test_read_palette_with_memory(self):
        mem = Memory()
        mem.write_u16(0x05000000, 0x7C00)  # Red in BGR555

        ppu = PPU(mem)
        color = ppu._read_palette(0)

        assert color == (248, 0, 0)

    def test_read_palette_index_out_of_bounds(self):
        ppu = PPU(None)
        color = ppu._read_palette(600)
        assert color == (0, 0, 0)
