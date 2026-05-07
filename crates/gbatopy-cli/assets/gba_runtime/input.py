"""GBA Input - Keyboard to GBA input register mapping"""

# GBA button bit positions in KEYINPUT register (0x04000130)
# Active low: 0 = pressed, 1 = released
GBA_KEYS = {
    "A": 0x01,  # bit 0
    "B": 0x02,  # bit 1
    "SELECT": 0x04,  # bit 2
    "START": 0x08,  # bit 3
    "RIGHT": 0x100,  # bit 8
    "LEFT": 0x200,  # bit 9
    "UP": 0x400,  # bit 10
    "DOWN": 0x800,  # bit 11
    "R": 0x1000,  # bit 12
    "L": 0x2000,  # bit 13
}

# Keyboard to GBA button mapping
# Arrow keys -> DPAD (bits 8-11), Z -> A, S -> B, Enter -> Start, Space -> Select
KEYBOARD_MAP = {
    "z": "A",
    "s": "B",
    "return": "START",
    "space": "SELECT",
    "right": "RIGHT",
    "left": "LEFT",
    "up": "UP",
    "down": "DOWN",
    "a": "L",
    "x": "R",
}

# Default value when no keys pressed (all bits = 1, meaning released)
# 14 bits (0-13) = 0x3FFF
DEFAULT_KEYS = 0x3FFF


class Input:
    """Handles keyboard to GBA input mapping.

    Maps keyboard keys to GBA KEYINPUT register (0x04000130).
    Uses lazy import of pygame to avoid dependency at import time.
    """

    def __init__(self):
        self._keys_pressed = DEFAULT_KEYS
        self._pygame = None
        self._pygame_available = None

    @property
    def _pygame_module(self):
        """Lazy import of pygame to avoid dependency at import time."""
        if self._pygame_available is None:
            try:
                import pygame

                # Initialize video subsystem for keyboard support
                pygame.display.init()
                pygame.key.set_repeat(100, 50)

                self._pygame = pygame
                self._pygame_available = True
            except ImportError:
                self._pygame = None
                self._pygame_available = False
        return self._pygame

    @property
    def pygame_available(self) -> bool:
        """Check if pygame is available."""
        if self._pygame_available is None:
            _ = self._pygame_module  # Trigger lazy import
        return self._pygame_available

    def poll(self) -> bool:
        """Poll keyboard state and update internal key state.

        Returns:
            True if polling successful, False if quit event received.
            Returns True even if pygame is not available (no-op).
        """
        if not self.pygame_available:
            # pygame not installed, return default (no keys pressed)
            self._keys_pressed = DEFAULT_KEYS
            return True

        pygame = self._pygame_module

        # Process events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False

        # Get current key states
        keys = pygame.key.get_pressed()

        # Start with all keys released (bits = 1)
        key_state = DEFAULT_KEYS  # 0x3FFF = all released

        # Check each mapped key
        for py_key_name, gba_key_name in KEYBOARD_MAP.items():
            py_key = getattr(pygame, f"K_{py_key_name}", None)
            if py_key is not None and keys[py_key]:
                # Key is pressed, clear the bit (active low)
                key_state &= ~GBA_KEYS[gba_key_name]

        self._keys_pressed = key_state
        return True

    def get_keys(self) -> int:
        """Get current key state as 16-bit mask.

        Returns:
            16-bit integer representing GBA KEYINPUT register.
            Bits are active low: 0 = pressed, 1 = released.
            0x3FFF (14 bits) = no keys pressed
        """
        return self._keys_pressed

    def update_from_pygame(self, keys) -> None:
        """Update GBA input state from pygame key state.

        Args:
            keys: pygame key state from pygame.key.get_pressed()
        """
        # Lazy import pygame if not already loaded
        if self._pygame is None:
            _ = self._pygame_module  # Trigger lazy import

        if not self.pygame_available:
            self._keys_pressed = DEFAULT_KEYS
            return

        pygame = self._pygame
        key_state = DEFAULT_KEYS
        for py_key_name, gba_key_name in KEYBOARD_MAP.items():
            py_key = getattr(pygame, f"K_{py_key_name}", None)
            if py_key is not None and keys[py_key]:
                key_state &= ~GBA_KEYS[gba_key_name]
        self._keys_pressed = key_state

    def update_keys(
        self,
        a=False,
        b=False,
        start=False,
        select=False,
        right=False,
        left=False,
        up=False,
        down=False,
        r=False,
        l=False,
    ):
        """Update GBA input from boolean arguments."""
        self._keys_pressed = 0x3FFF  # All not pressed
        if a:
            self._keys_pressed &= ~GBA_KEYS["A"]
        if b:
            self._keys_pressed &= ~GBA_KEYS["B"]
        if start:
            self._keys_pressed &= ~GBA_KEYS["START"]
        if select:
            self._keys_pressed &= ~GBA_KEYS["SELECT"]
        if right:
            self._keys_pressed &= ~GBA_KEYS["RIGHT"]
        if left:
            self._keys_pressed &= ~GBA_KEYS["LEFT"]
        if up:
            self._keys_pressed &= ~GBA_KEYS["UP"]
        if down:
            self._keys_pressed &= ~GBA_KEYS["DOWN"]
        if r:
            self._keys_pressed &= ~GBA_KEYS["R"]
        if l:
            self._keys_pressed &= ~GBA_KEYS["L"]


# Export constants for generated code
KEY_A = 0x01  # bit 0
KEY_B = 0x02  # bit 1
KEY_SELECT = 0x04  # bit 2
KEY_START = 0x08  # bit 3
KEY_RIGHT = 0x100  # bit 8
KEY_LEFT = 0x200  # bit 9
KEY_UP = 0x400  # bit 10
KEY_DOWN = 0x800  # bit 11
KEY_R = 0x1000  # bit 12
KEY_L = 0x2000  # bit 13
