"""GBA PPU (Pixel Processing Unit) - Graphics rendering"""

import struct
from typing import Optional, List, Tuple


class PPU:
    """Game Boy Advance Pixel Processing Unit"""

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

    # Sprite/OBJ registers
    REG_DISPSTAT2 = 0x04000056

    # Additional MMIO for mosaic (correct address)
    REG_MOSAIC_EXT = 0x040000F4

    def __init__(self, memory):
        self.memory = memory

        # Display control
        self.mode = 0
        self.display_frame_select = 0
        self.hblank_interval_free = False
        self.obj_character_vram_mapping = False
        self.forced_blank = False
        self.bg0_enable = False
        self.bg1_enable = False
        self.bg2_enable = False
        self.bg3_enable = False
        self.obj_enable = False
        self.win0_enable = False
        self.win1_enable = False
        self.obj_window_enable = False

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

        # Framebuffer
        self.framebuffer: List[List[Tuple[int, int, int]]] = []
        self._init_framebuffer()

    def get_surface(self) -> "pygame.Surface":
        """Convert framebuffer to pygame Surface for screenshot"""
        import pygame

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
            # WINOUT: bits 0-5 = window 0 out, bits 8-13 = window 1 out
            self.win0_out_enable = value & 0x3F
            self.win1_out_enable = (value >> 8) & 0x3F
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
            self.mode = value & 0x7
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
            return self.win0_out_enable | (self.win1_out_enable << 8)
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

        # Unmapped MMIO register — standard GBA behavior is to return 0
        return 0

    def _read_bg_control(self, bg_num: int) -> int:
        """Read BG control register"""
        if bg_num < 0 or bg_num > 3:
            # Invalid BG number — return 0 as per GBA hardware behavior
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

    def _apply_affine_transform(self, bg_num: int, x: int, y: int) -> Tuple[int, int]:
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

    def _get_window_layer_enable(self, x: int, y: int) -> int:
        """Get which layers are enabled at the given coordinate based on windows"""
        # Check WIN0 first
        if self.win0_enable and self._is_in_window(x, y, 0):
            return self.win0_in_enable

        # Check WIN1
        if self.win1_enable and self._is_in_window(x, y, 1):
            return self.win1_in_enable

        # Check OBJ window
        if self.obj_window_enable:
            return 0x3F  # All enabled by default (BG0-3 + OBJ + Blend)

        # Default to out enables
        if self.win0_enable or self.win1_enable:
            return self.win0_out_enable

        return 0x3F  # All enabled by default (BG0-3 + OBJ + Blend)

    def _apply_mosaic(self, x: int, y: int, is_obj: bool = False) -> Tuple[int, int]:
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
        """Render one frame of graphics with Windows, Mosaic, and all effects"""
        # Update VCOUNT
        self.vcount = (self.vcount + 1) % self.screen_height
        self.vblank = self.vcount >= self.screen_height

        # Clear framebuffer if forced blank
        if self.forced_blank:
            self._init_framebuffer()
            return

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
        """Render Mode 0: Text backgrounds (BG0-3)"""
        # Render each background layer in priority order
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                # Check window enable
                layer_enable = self._get_window_layer_enable(x, y)

                # Render BG layers (simplified - would need tile lookup)
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

                    # For now, render as solid color based on BG number
                    # Full implementation would look up tile data from VRAM
                    color = (bg * 32, bg * 32, bg * 32)
                    self.framebuffer[y][x] = color

                if self.obj_enable and (layer_enable & 0x10):
                    self._render_sprite_line(y)

    def _render_mode1(self):
        """Render Mode 1: Text BG0/1 + Affine BG2/3"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                # Render BG0, BG1 (text)
                for bg in [0, 1]:
                    if not getattr(self, f"bg{bg}_enable"):
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    mx, my = self._apply_mosaic(x, y, is_obj=False)
                    tile_x = (mx + self.bg_hofs[bg]) % 256
                    tile_y = (my + self.bg_vofs[bg]) % 256

                    color = (bg * 64, bg * 64, bg * 64)
                    self.framebuffer[y][x] = color

                # Render BG2, BG3 (affine)
                for bg in [2, 3]:
                    if not getattr(self, f"bg{bg}_enable"):
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    # Apply affine transformation
                    aff_x, aff_y = self._apply_affine_transform(bg, x, y)

                    # Apply mosaic
                    mx, my = self._apply_mosaic(int(aff_x), int(aff_y), is_obj=False)

                    color = (bg * 80, bg * 80, bg * 80)
                    self.framebuffer[y][x] = color

    def _render_mode2(self):
        """Render Mode 2: Affine BG2/3 only"""
        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                # Render BG2, BG3 (affine)
                for bg in [2, 3]:
                    if not getattr(self, f"bg{bg}_enable"):
                        continue
                    if not (layer_enable & (1 << bg)):
                        continue

                    aff_x, aff_y = self._apply_affine_transform(bg, x, y)
                    mx, my = self._apply_mosaic(int(aff_x), int(aff_y), is_obj=False)

                    color = (bg * 100, bg * 100, bg * 100)
                    self.framebuffer[y][x] = color

    def _render_mode3(self):
        """Render Mode 3: 240x160 bitmap mode"""
        vram_base = 0x06000000

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                if not (layer_enable & 0x20):  # Blend enable check
                    # Read 16-bit color from VRAM
                    offset = (y * 240 + x) * 2
                    addr = vram_base + offset

                    try:
                        color_val = self.memory.read_u16(addr)
                        # Convert 15-bit RGB555 to RGB888
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

    def _render_mode4(self):
        """Render Mode 4: 240x160 bitmap with double buffering"""
        # Page 0: 0x06000000, Page 1: 0x0600A000
        page = self.display_frame_select
        vram_base = 0x06000000 if page == 0 else 0x0600A000

        for y in range(self.screen_height):
            for x in range(self.screen_width):
                layer_enable = self._get_window_layer_enable(x, y)

                if not (layer_enable & 0x20):
                    offset = (y * 240 + x) * 2
                    addr = vram_base + offset

                    try:
                        color_val = self.memory.read_u16(addr)
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

    def _render_mode5(self):
        """Render Mode 5: 160x128 bitmap mode"""
        vram_base = 0x06000000

        for y in range(128):
            for x in range(160):
                layer_enable = self._get_window_layer_enable(x, y)

                if not (layer_enable & 0x20):
                    offset = (y * 160 + x) * 2
                    addr = vram_base + offset

                    try:
                        color_val = self.memory.read_u16(addr)
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        self.framebuffer[y][x] = (r, g, b)
                    except:
                        self.framebuffer[y][x] = (0, 0, 0)

    def _blending_enabled(self) -> bool:
        return (self.bldcnt & 0x3FFF) != 0

    def _apply_blending_to_framebuffer(self):
        blend_mode = (self.bldcnt >> 6) & 0x3

        if blend_mode == 1:
            eva = min(self.bldalpha_eva, 16)
            evb = min(self.bldalpha_evb, 16)
            if eva > 0 or evb > 0:
                for y in range(self.screen_height):
                    for x in range(self.screen_width):
                        r, g, b = self.framebuffer[y][x]
                        bg_r = min(r + 20, 255)
                        bg_g = min(g + 20, 255)
                        bg_b = min(b + 20, 255)
                        r = (r * eva + bg_r * evb) // 16
                        g = (g * eva + bg_g * evb) // 16
                        b = (b * eva + bg_b * evb) // 16
                        self.framebuffer[y][x] = (r, g, b)
        elif blend_mode == 2:
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
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
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
                        r = ((color_val >> 0) & 0x1F) * 8
                        g = ((color_val >> 5) & 0x1F) * 8
                        b = ((color_val >> 10) & 0x1F) * 8
                        colors.append((r, g, b))
                    else:
                        colors.append(None)
                except:
                    colors.append(None)

        return colors
