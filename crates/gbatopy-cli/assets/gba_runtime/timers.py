"""GBA Timers"""


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
        self._dma = None
        self._cycle_subcount = [0] * 4
        self._active_count = 0

    def attach_dma(self, dma):
        """Attach DMA controller for timer-triggered DMA transfers."""
        self._dma = dma

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
        """Set control register for timer channel.

        On the GBA, when bit 7 transitions 0->1 (enable), the timer count is
        reset to the reload value. This matches hardware behavior: re-enabling
        a timer always restarts it from the reload value.
        """
        if not 0 <= channel <= 3:
            raise ValueError(f"Invalid channel: {channel}")
        ch = self._channels[channel]
        was_enabled = bool(ch.control & 0x80)
        ch.control = control & 0xFF
        new_enabled = bool(ch.control & 0x80)
        if not was_enabled and new_enabled:
            ch.count = ch.reload
            self._cycle_subcount[channel] = 0
        if was_enabled != new_enabled:
            self._active_count += 1 if new_enabled else -1

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
        if self._active_count == 0:
            self._overflow_flags[0] = False
            self._overflow_flags[1] = False
            self._overflow_flags[2] = False
            self._overflow_flags[3] = False
            return

        cascade = (self._overflow_flags[0], self._overflow_flags[1],
                   self._overflow_flags[2], self._overflow_flags[3])
        self._overflow_flags[0] = False
        self._overflow_flags[1] = False
        self._overflow_flags[2] = False
        self._overflow_flags[3] = False

        prescalers = self.PRESCALER_VALUES
        subcounts = self._cycle_subcount
        channels = self._channels
        overflow = self._overflow_flags
        interrupts = self._interrupts

        for i in range(4):
            channel = channels[i]
            ctrl = channel.control

            if not (ctrl & 0x80):
                continue

            if ctrl & 0x04:
                if i == 0 or not cascade[i - 1]:
                    continue
                increment = 1
            else:
                prescaler = prescalers[ctrl & 0x03]
                total = subcounts[i] + cycles
                increment = total // prescaler
                subcounts[i] = total % prescaler

            if increment > 0:
                new_count = channel.count + increment
                if new_count > 0xFFFF:
                    overflow[i] = True
                    new_count = (new_count - 0x10000) + channel.reload
                    if (ctrl & 0x40) and interrupts:
                        interrupts.timer_irq(i)
                    # Fire timer-triggered DMA if attached
                    if self._dma:
                        self._dma.timer_trigger_fire(i)
                channel.count = new_count & 0xFFFF