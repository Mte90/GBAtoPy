try:
    from numba import njit, prange
    _HAS_NUMBA = True
except ImportError:
    njit = None
    prange = None
    _HAS_NUMBA = False

_NUMBA_ENABLED = False


def jit_compile(func):
    if not _HAS_NUMBA or not _NUMBA_ENABLED:
        return func
    try:
        return njit(func, cache=True, fastmath=True)
    except Exception:
        return func


def set_numba_enabled(enabled: bool):
    global _NUMBA_ENABLED
    _NUMBA_ENABLED = enabled and _HAS_NUMBA


def is_numba_available() -> bool:
    return _HAS_NUMBA