class GameError(Exception):
    pass


class GBARuntimeError(GameError):
    pass


class InvalidRom(GameError):
    pass


class InvalidROMError(InvalidRom):
    pass


class InvalidAddress(GameError):
    pass


__all__ = ["GameError", "GBARuntimeError", "InvalidRom", "InvalidROMError", "InvalidAddress"]
