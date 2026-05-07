"""GBA ROM handling - loads and parses cartridge ROM files."""



class ROM:
    """Represents a loaded GBA ROM image with header parsing.

    Provides access to ROM data and parsed header fields including
    title, game code, maker code, and entry point.
    """

    # GBA ROM header offsets
    OFFSET_ENTRY_POINT = 0x00  # 4 bytes - ARM branch to start
    OFFSET_NINTENDO_LOGO = 0x04  # 156 bytes - compressed logo
    OFFSET_TITLE = 0xA0  # 12 bytes - game title (ASCII)
    OFFSET_GAME_CODE = 0xAC  # 4 bytes - game code
    OFFSET_MAKER_CODE = 0xB0  # 2 bytes - maker code
    OFFSET_ROM_SIZE = 0xB4  # 1 byte - ROM size code

    def __init__(self):
        """Create an empty ROM instance."""
        self._data: bytes = b""
        self._header: dict = {}

    def load(self, path: str) -> None:
        """Load a GBA ROM file from disk.

        Args:
            path: Path to the .gba file to load.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file is too small to contain a valid header.
        """
        with open(path, "rb") as f:
            self._data = f.read()

        if len(self._data) < 0xC0:
            raise ValueError(f"ROM file too small: {len(self._data)} bytes")

        self._parse_header()

    def _parse_header(self) -> None:
        """Parse the GBA ROM header and populate header dict."""
        # Entry point (4 bytes at 0x00)
        entry = int.from_bytes(self._data[0x00:0x04], "little")

        # Game title (12 bytes at 0xA0, null-padded ASCII)
        title_bytes = self._data[0xA0:0xAC]
        title = title_bytes.rstrip(b"\x00").decode("ascii", errors="replace")

        # Game code (4 bytes at 0xAC)
        game_code = self._data[0xAC:0xB0].decode("ascii", errors="replace")

        # Maker code (2 bytes at 0xB0)
        maker_code = self._data[0xB0:0xB2].decode("ascii", errors="replace")

        rom_size_code = self._data[0xB4]
        shift = rom_size_code & 0x0F
        if rom_size_code < 0x18 and shift < 16:
            rom_size = 0x80000 << shift
        else:
            rom_size = len(self._data)

        self._header = {
            "entry_point": entry,
            "title": title,
            "game_code": game_code,
            "maker_code": maker_code,
            "rom_size": rom_size,
        }

    def get_header(self) -> dict:
        """Return the parsed ROM header fields.

        Returns:
            Dictionary containing: entry_point, title, game_code,
            maker_code, rom_size.
        """
        return self._header.copy()

    @property
    def data(self) -> bytes:
        """Return the raw ROM data."""
        return self._data

    @property
    def title(self) -> str:
        """Return the game title (up to 12 bytes, null-padded)."""
        return self._header.get("title", "")

    @property
    def game_code(self) -> str:
        """Return the 4-character game code."""
        return self._header.get("game_code", "")

    @property
    def maker_code(self) -> str:
        """Return the 2-character maker code."""
        return self._header.get("maker_code", "")

    @property
    def rom_size(self) -> int:
        """Return the ROM size in bytes (0 if unknown)."""
        return self._header.get("rom_size", 0)

    @property
    def entry_point(self) -> int:
        """Return the entry point address (ARM branch instruction)."""
        return self._header.get("entry_point", 0)

    def read_bytes(self, offset: int, length: int) -> bytes:
        """Read raw bytes from the ROM at the given offset.

        Args:
            offset: Byte offset from start of ROM.
            length: Number of bytes to read.

        Returns:
            Bytes read (may be shorter if ROM ends).
        """
        return self._data[offset : offset + length]
