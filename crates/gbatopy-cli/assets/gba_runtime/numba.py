try:
    from numba import njit, prange
    _HAS_NUMBA = True
except ImportError:
    njit = None
    prange = None
    _HAS_NUMBA = False

_NUMBA_ENABLED = False
def set_numba_enabled(enabled: bool):
    global _NUMBA_ENABLED
    _NUMBA_ENABLED = enabled and _HAS_NUMBA


