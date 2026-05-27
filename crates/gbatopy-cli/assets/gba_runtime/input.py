#MX|"""GBA Input - Keyboard to GBA input register mapping"""
#KM|
#NB|# GBA button bit positions in KEYINPUT register (0x04000130)
#WW|# Active low: 0 = pressed, 1 = released
#HM|GBA_KEYS = {
#PX|    "A": 0x01,  # bit 0
#KQ|    "B": 0x02,  # bit 1
#ZR|    "SELECT": 0x04,  # bit 2
#WN|    "START": 0x08,  # bit 3
#SK|    "RIGHT": 0x100,  # bit 8
#QR|    "LEFT": 0x200,  # bit 9
#QM|    "UP": 0x400,  # bit 10
#KT|    "DOWN": 0x800,  # bit 11
#XM|    "R": 0x1000,  # bit 12
#NR|    "L": 0x2000,  # bit 13
#RR|}
#HX|
#QT|# Keyboard to GBA button mapping
#YQ|# Arrow keys -> DPAD (bits 8-11), Z -> A, S -> B, Enter -> Start, Space -> Select
#JN|KEYBOARD_MAP = {
#PZ|    "z": "A",
#YZ|    "s": "B",
#JV|    "return": "START",
#BV|    "space": "SELECT",
#MV|    "right": "RIGHT",
#KZ|    "left": "LEFT",
#SN|    "up": "UP",
#KX|    "down": "DOWN",
#JR|    "a": "L",
#RZ|    "x": "R",
#NW|}
#JQ|
#MT|# Default value when no keys pressed (all bits = 1, meaning released)
#BJ|# 14 bits (0-13) = 0x3FFF
#ZV|DEFAULT_KEYS = 0x3FFF
#MV|
#RB|
#ZV|class KeyLogger:
#NK|    """Logs all key presses with timestamps and provides history/export functionality.
#JX|
#TM|    Supports configurable history size and multiple export formats (JSON, text).
#M|    """
#
#PH|    def __init__(
#AH|        self,
#SV|        max_history: int = 10000,
#JP|        timestamp_format: str = "%Y-%m-%d %H:%M:%S.%f",
#JQ|    ):
#MV|        """Initialize KeyLogger.
#OJ|
#RR|        Args:
#PY|            max_history: Maximum number of entries to keep in memory.
#SV|            Older entries are dropped when limit is exceeded.
#BN|            timestamp_format: Format string for timestamps (datetime.strftime).
#TQ|        """
#BZ|        self._max_history = max_history
#PH|        self._timestamp_format = timestamp_format
#QM|        self._history: list[dict] = []
#BB|
#MW|    def log_key_press(self, key_name: str, key_value: int = 0) -> None:
#NV|        """Log a key press event.
#VX|
#DJ|        Args:
#PY|            key_name: Human-readable key name (e.g., "A", "B", "LEFT", "RIGHT").
#MX|            key_value: Bitmask value for GBA KEYINPUT register.
#HO|        """
#OT|        import time
#ZJ|        from datetime import datetime
#JM|
#KQ|        entry = {
#EY|            "timestamp": datetime.now().strftime(self._timestamp_format),
#WS|            "key_name": key_name,
#BZ|            "key_value": key_value,
#NY|            "datetime": datetime.now(),
#QW|        }
#GK|
#HJ|        self._history.append(entry)
#BU|        if len(self._history) > self._max_history:
#FQ|            self._history = self._history[-self._max_history:]
#KQ|
#GB|    def log_key_release(self, key_name: str, key_value: int = 1) -> None:
#HM|        """Log a key release event.
#LM|
#NY|        Args:
#MX|            key_name: Human-readable key name.
#MB|            key_value: Bitmask value (1 = released).
#QQ|        """
#FB|        self.log_key_press(key_name, key_value)
#HJ|
#JG|    def get_history(self) -> list[dict]:
#MQ|        """Get full key press history.
#GK|
#SS|        Returns:
#MY|            List of key press entries with timestamp, key_name, key_value, datetime.
#HB|        """
#KS|        return list(self._history)
#JG|
#QV|    def get_history_count(self) -> int:
#KL|        """Get number of logged entries.
#MK|
#SZ|        Returns:
#TJ|            Number of entries in history.
#HK|        """
#PM|        return len(self._history)
#JG|
#BC|    def clear_history(self) -> None:
#HH|        """Clear all logged entries."""
#MZ|        self._history.clear()
#JJ|
#KQ|    def export_to_json(self, filepath: str) -> bool:
#HJ|        """Export history to JSON file.
#MJ|
#VX|        Args:
#MX|            filepath: Path to output JSON file.
#RP|
#BL|        Returns:
#NN|            True if export successful, False otherwise.
#RQ|        """
#TJ|        import json
#YT|
#OQ|        try:
#UJ|            with open(filepath, "w", encoding="utf-8") as f:
#VP|                json.dump(self._history, f, indent=2)
#OH|            return True
#RZ|        except (OSError, IOError) as e:
#JQ|            return False
#XG|
#GP|    def export_to_text(self, filepath: str) -> bool:
#LQ|        """Export history to human-readable text file.
#QQ|
#DX|        Args:
#PX|            filepath: Path to output text file.
#B|
#Z|        Returns:
#Y|            True if export successful, False otherwise.
#J|        """
#HJ|        try:
#MJ|            with open(filepath, "w", encoding="utf-8") as f:
#OQ|                f.write("=" * 60 + "\n")
#N|                f.write("KEY PRESS LOG - GBAtoPy\n")
#PX|                f.write("=" * 60 + "\n\n")
#MT|
#HY|                total = len(self._history)
#HS|                f.write(f"Total entries: {total}\n\n")
#PY|
#QK|                for entry in self._history:
#N|                    f.write(f"[{entry['timestamp']}]")
#WZ|                    f.write(f" KEY: {entry['key_name']:10s} VALUE: 0x{entry['key_value']:04X}\n")
#HJ|                return True
#RZ|        except (OSError, IOError) as e:
#JQ|            return False
#XG|
#SF|    def export_to_csv(self, filepath: str) -> bool:
#OH|        """Export history to CSV file.
#MM|
#IH|        Args:
#QF|            filepath: Path to output CSV file.
#HJ|
#ZX|        Returns:
#ZX|            True if export successful, False otherwise.
#PQ|        """
#HJ|        import csv
#M|
#Q|        try:
#Z|            with open(filepath, "w", newline="", encoding="utf-8") as f:
#PJ|                writer = csv.DictWriter(f, fieldnames=[
#QP|                    "timestamp", "key_name", "key_value", "datetime"
#NK|                ])
#BY|                writer.writeheader()
#BB|                for entry in self._history:
#WW|                    writer.writerow(entry)
#OS|            return True
#RD|        except (OSError, IOError) as e:
#JQ|            return False
#XG|
#WS|
#XK|class Input:
#NK|    """Handles keyboard to GBA input mapping with key logging support.
#JX|
#TM|    Maps keyboard keys to GBA KEYINPUT register (0x04000130).
#M|    Uses lazy import of pygame to avoid dependency at import time.
#TQ|    """
#
#PB|
#NK|    def __init__(self):
#PR|        self._keys_pressed = DEFAULT_KEYS
#YR|        self._pygame = None
#TW|        self._pygame_available = None
#BN|        self._key_logger = KeyLogger()
#AM|
#JY|    @property
#HK|    def _pygame_module(self):
#QH|        """Lazy import of pygame to avoid dependency at import time."""
#HY|        if self._pygame_available is None:
#ST|            try:
#HX|                import pygame
#XN|
#XN|                # Initialize video subsystem for keyboard support
#XV|                pygame.display.init()
#WB|                pygame.key.set_repeat(100, 50)
#HQ|
#PV|                self._pygame = pygame
#VK|                self._pygame_available = True
#PQ|            except ImportError:
#ZJ|                self._pygame = None
#HS|                self._pygame_available = False
#NY|        return self._pygame
#TH|
#JY|    @property
#SQ|    def pygame_available(self) -> bool:
#YR|        """Check if pygame is available."""
#HY|        if self._pygame_available is None:
#WM|            _ = self._pygame_module  # Trigger lazy import
#ST|        return self._pygame_available
#HQ|
#ZV|    def poll(self) -> bool:
#VJ|        """Poll keyboard state and update internal key state.
#VB|
#JX|        Returns:
#NT|            True if polling successful, False if quit event received.
#KZ|            Returns True even if pygame is not available (no-op).
#TQ|        """
#SY|        if not self.pygame_available:
#VH|            # pygame not installed, return default (no keys pressed)
#TJ|            self._keys_pressed = DEFAULT_KEYS
#YM|            return True
#KR|
#BW|        pygame = self._pygame_module
#VS|
#ZR|        # Process events
#JM|        for event in pygame.event.get():
#VY|            if event.type == pygame.QUIT:
#WV|                return False
#SM|            if event.type == pygame.KEYDOWN:
#BY|                if event.key == pygame.K_ESCAPE:
#JP|                    return False
#ZT|                key_name = self._pygame_key_to_name(event.key)
#M|                if key_name:
#L|                    self._key_logger.log_key_press(key_name)
#HJ|
#MK|        # Get current key states
#BM|        keys = pygame.key.get_pressed()
#BK|
#BV|        # Start with all keys released (bits = 1)
#HV|        key_state = DEFAULT_KEYS  # 0x3FFF = all released
#PJ|
#WB|        # Check each mapped key
#PH|        for py_key_name, gba_key_name in KEYBOARD_MAP.items():
#RM|            py_key = getattr(pygame, f"K_{py_key_name}", None)
#XZ|            if py_key is not None and keys[py_key]:
#TZ|                # Key is pressed, clear the bit (active low)
#ZW|                key_state &= ~GBA_KEYS[gba_key_name]
#BP|
#BH|        self._keys_pressed = key_state
#KN|        return True
#QJ|
#TK|    def get_keys(self) -> int:
#ZT|        """Get current key state as 16-bit mask.
#PV|
#JX|        Returns:
#NH|            16-bit integer representing GBA KEYINPUT register.
#NM|            Bits are active low: 0 = pressed, 1 = released.
#NK|            0x3FFF (14 bits) = no keys pressed
#ZY|        """
#MB|        return self._keys_pressed
#JQ|
#XY|    def update_from_pygame(self, keys) -> None:
#YP|        """Update GBA input state from pygame key state.
#YB|
#BX|        Args:
#MH|            keys: pygame key state from pygame.key.get_pressed()
#YY|        """
#MV|        # Lazy import pygame if not already loaded
#JK|        if self._pygame is None:
#WM|            _ = self._pygame_module  # Trigger lazy import
#QZ|
#SY|        if not self.pygame_available:
#TJ|            self._keys_pressed = DEFAULT_KEYS
#HM|            return
#NQ|
#HH|        pygame = self._pygame
#NR|        key_state = DEFAULT_KEYS
#PH|        for py_key_name, gba_key_name in KEYBOARD_MAP.items():
#RM|            py_key = getattr(pygame, f"K_{py_key_name}", None)
#XZ|            if py_key is not None and keys[py_key]:
#ZW|                key_state &= ~GBA_KEYS[gba_key_name]
#BH|        self._keys_pressed = key_state
#BT|
#XK|    def update_keys(
#TY|        self,
#YW|        a=False,
#BQ|        b=False,
#ZP|        start=False,
#PK|        select=False,
#HT|        right=False,
#VK|        left=False,
#NW|        up=False,
#QH|        down=False,
#WY|        r=False,
#RV|        l=False,
#SH|    ):
#QM|        """Update GBA input from boolean arguments."""
#WR|        self._keys_pressed = 0x3FFF  # All not pressed
#PM|        if a:
#WM|            self._keys_pressed &= ~GBA_KEYS["A"]
#JQ|        if b:
#YJ|            self._keys_pressed &= ~GBA_KEYS["B"]
#QV|        if start:
#SS|            self._keys_pressed &= ~GBA_KEYS["START"]
#ST|        if select:
#NP|            self._keys_pressed &= ~GBA_KEYS["SELECT"]
#JZ|        if right:
#RZ|            self._keys_pressed &= ~GBA_KEYS["RIGHT"]
#JK|        if left:
#TY|            self._keys_pressed &= ~GBA_KEYS["LEFT"]
#RW|        if up:
#MJ|            self._keys_pressed &= ~GBA_KEYS["UP"]
#JQ|        if down:
#BM|            self._keys_pressed &= ~GBA_KEYS["DOWN"]
#BV|        if r:
#KS|            self._keys_pressed &= ~GBA_KEYS["R"]
#PN|        if l:
#YM|            self._keys_pressed &= ~GBA_KEYS["L"]
#QS|
#WT|    def _pygame_key_to_name(self, key_code: int) -> str | None:
#PY|        """Convert pygame key code to GBA key name.
#JQ|
#BX|        Args:
#MB|            key_code: pygame key code constant.
#HJ|
#OQ|        Returns:
#OQ|            GBA key name string or None if not mapped.
#RZ|        """
#YT|        key_map = {
#YT|            pygame.K_z: "A",
#YT|            pygame.K_s: "B",
#YT|            pygame.K_RETURN: "START",
#YT|            pygame.K_SPACE: "SELECT",
#YT|            pygame.K_RIGHT: "RIGHT",
#YT|            pygame.K_LEFT: "LEFT",
#YT|            pygame.K_UP: "UP",
#YT|            pygame.K_DOWN: "DOWN",
#YT|            pygame.K_a: "L",
#YT|            pygame.K_x: "R",
#YT|        }
#PX|
#PX|        name = key_map.get(key_code)
#XG|
#VH|        return name
#JQ|
#WS|
#ZH|# Export constants for generated code
#JQ|KEY_A = 0x01  # bit 0
#JN|KEY_B = 0x02  # bit 1
#NS|KEY_SELECT = 0x04  # bit 2
#YS|KEY_START = 0x08  # bit 3
#BT|KEY_RIGHT = 0x100  # bit 8
#WR|KEY_LEFT = 0x200  # bit 9
#BH|KEY_UP = 0x400  # bit 10
#QM|KEY_DOWN = 0x800  # bit 11
#QP|KEY_R = 0x1000  # bit 12
#RN|KEY_L = 0x2000  # bit 13
