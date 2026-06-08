# === Numba JIT Support for PPU ===

try:
    from numba import njit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    
    def njit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    prange = range


@njit if NUMBA_AVAILABLE else lambda f: f
def render_tile_4bpp(tile_data, palette, x, y, width, height):
    """Render a 4BPP tile with numba JIT acceleration."""
    for py in range(height):
        for px in range(width):
            tile_x = px % 8
            tile_y = py % 8
            byte_offset = (tile_y // 8) * 8 + tile_x
            byte_val = tile_data[byte_offset]
            color_idx = (byte_val >> (4 * (tile_x % 2))) & 0xF
            # Render pixel...
    return True


@njit if NUMBA_AVAILABLE else lambda f: f
def render_tile_8bpp(tile_data, palette, x, y, width, height):
    """Render a 8BPP tile with numba JIT acceleration."""
    for py in range(height):
        for px in range(width):
            tile_x = px % 8
            tile_y = py % 8
            byte_offset = tile_y * 8 + tile_x
            color_idx = tile_data[byte_offset]
            # Render pixel...
    return True


@njit if NUMBA_AVAILABLE else lambda f: f
def blend_pixels(color1, color2, factor):
    """Blend two pixels with numba JIT acceleration."""
    r = (color1[0] * factor + color2[0] * (256 - factor)) // 256
    g = (color1[1] * factor + color2[1] * (256 - factor)) // 256
    b = (color1[2] * factor + color2[2] * (256 - factor)) // 256
    return (r, g, b)
