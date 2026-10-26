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
        self._interrupts = None
        self._transfer_pending = False

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

    def attach_interrupts(self, interrupts):
        """Attach interrupt controller for serial IRQ callbacks."""
        self._interrupts = interrupts

    def _write_siocnt(self, value: int):
        was_transfer_enabled = self.transfer_enabled
        self.sio_mode = (value >> 12) & 0x3
        self.transfer_enabled = bool((value >> 7) & 1)
        self.clock_select = (value >> 0) & 0x3
        self.multi_player_id = (value >> 8) & 0x3
        
        # When transfer_enabled transitions 0->1, start the transfer
        if not was_transfer_enabled and self.transfer_enabled:
            self._start_transfer()
        # Also handle the case where SIOCNT is written with bit 7 already set
        # (some ROMs write the full control word including the start bit)
        elif self.transfer_enabled and not self.busy_flag and not self._transfer_pending:
            self._start_transfer()

    def _start_transfer(self):
        """Start a serial transfer. Sets busy flag and schedules completion."""
        self.busy_flag = True
        self._transfer_pending = True
        # Transfer completes on next step (simulates shift register timing)

    def _uart_transfer(self):
        """UART mode transfer - immediately copies send_data to receive_data."""
        # In UART mode, the transfer is immediate (loopback for testing)
        self.receive_data = self.send_data

    def _complete_transfer(self):
        """Complete a serial transfer and fire IRQ if enabled."""
        if not self._transfer_pending:
            return
        
        self.busy_flag = False
        self._transfer_pending = False
        self.receive_data = self.send_data
        
        # Fire serial IRQ if enabled (SIOCNT bit 14)
        # Note: In the current implementation, we check the irq_enable bit from SIOCNT
        # The irq_enable bit is bit 14 of the SIOCNT register
        siocnt_value = self._read_siocnt()
        irq_enable = bool(siocnt_value & 0x4000)  # bit 14
        
        if irq_enable and self._interrupts:
            self._interrupts.serial_irq()

    def step(self):
        """Advance serial state. Called each frame to process pending transfers."""
        if self._transfer_pending:
            self._complete_transfer()

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
