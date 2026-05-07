"""GBA Timers"""


class TimerChannel:
    """Individual timer channel"""

    def __init__(self):
        self.count = 0
        self.reload = 0
        self.control = 0

    @property
    def enabled(self) -> bool:
        """Check if timer is enabled (bit 7)"""
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
        """Advance all enabled timers by given cycles"""
        # Reset overflow flags at start of step
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
                    # Timer0 in cascade mode - should not happen, but handle it
                    continue
                # Check if previous timer overflowed this step
                if not self._overflow_flags[i - 1]:
                    continue
                # Increment by 1 for cascade
                increment = 1
            else:
                # Normal mode: increment based on prescaler
                prescaler = channel.prescaler_value
                increment = cycles // prescaler

            if increment > 0:
                old_count = channel.count
                channel.count = (channel.count + increment) & 0xFFFF

                # Check for overflow (wrapped around)
                if channel.count < old_count:
                    self._overflow_flags[i] = True
                    # Reload from reload value on overflow
                    channel.count = channel.reload
