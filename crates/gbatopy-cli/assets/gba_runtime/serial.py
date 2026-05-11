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
