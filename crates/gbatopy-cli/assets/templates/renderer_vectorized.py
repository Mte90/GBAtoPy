import time
import pygame
import numpy as np

try:
    import numba
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False

try:
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class VectorizedRenderer:
    WIDTH = 240
    HEIGHT = 160
    SCREEN_SIZE = WIDTH * HEIGHT
    BYTES_PER_4BPP_TILE = 32
    BYTES_PER_8BPP_TILE = 64

    def __init__(self, palette_bg=None, tiles_4bpp=None, tiles_8bpp=None):
        self.palette_bg = palette_bg or []
        self.tiles_4bpp = tiles_4bpp or bytearray()
        self.tiles_8bpp = tiles_8bpp or bytearray()
        self.palette_array = self._convert_palette_to_numpy()
        self.pixel_buffer = np.zeros((160, 240, 4), dtype=np.uint8, order='C')

    def _convert_palette_to_numpy(self):
        result = []
        for color16 in self.palette_bg:
            r = ((color16 >> 0) & 0x1F) * 8
            g = ((color16 >> 5) & 0x1F) * 8
            b = ((color16 >> 10) & 0x1F) * 8
            result.append([r, g, b, 255])
        return np.array(result, dtype=np.uint8, order='C')

    def _expand_4bpp_to_rgb(self, tile_data):
        data = tile_data if isinstance(tile_data, (bytes, bytearray)) else bytearray(tile_data[:32])
        pixels = np.frombuffer(data, dtype=np.uint8)
        high = np.right_shift(pixels, 4)
        low = pixels & 0x0F
        indices = np.concatenate([high, low])
        if len(self.palette_array) > 0:
            safe_indices = indices % min(len(self.palette_array), 256)
            rgba = self.palette_array[safe_indices]
        else:
            rgba = np.zeros((64, 4), dtype=np.uint8)
            rgba[:, 3] = 255
        return rgba.reshape(8, 8, 4, order='C')

    def _expand_8bpp_to_rgb(self, tile_data):
        data = tile_data[:64] if isinstance(tile_data, (bytes, bytearray)) else tile_data[:64]
        pixels = np.frombuffer(data, dtype=np.uint8)
        if len(self.palette_array) > 0:
            safe_pixels = pixels % min(len(self.palette_array), 256)
            rgba = self.palette_array[safe_pixels]
        else:
            rgba = np.zeros((64, 4), dtype=np.uint8)
        return rgba.reshape(8, 8, 4, order='C')

    def render_tile_4bpp_to_screen(self, x, y, tile_idx, screen_buffer, palette_bg):
        tile_offset = tile_idx * self.BYTES_PER_4BPP_TILE
        if tile_offset < 0 or tile_offset >= len(self.tiles_4bpp):
            return
        tile_data = bytes(self.tiles_4bpp[tile_offset:tile_offset + self.BYTES_PER_4BPP_TILE])
        if len(tile_data) >= 32:
            rgba_tile = self._expand_4bpp_to_rgb(tile_data)
            y_min = max(0, y)
            y_max = min(160, y + 8)
            x_min = max(0, x)
            x_max = min(240, x + 8)
            if y_max > y_min and x_max > x_min:
                screen_buffer[y_min:y_max, x_min:x_max] = rgba_tile[:8, :8]

    def render_tile_8bpp_to_screen(self, x, y, tile_idx, screen_buffer, palette_bg):
        tile_offset = tile_idx * self.BYTES_PER_8BPP_TILE
        if tile_offset < 0 or tile_offset >= len(self.tiles_8bpp):
            return
        tile_data = bytes(self.tiles_8bpp[tile_offset:tile_offset + self.BYTES_PER_8BPP_TILE])
        if len(tile_data) >= 64:
            rgba_tile = self._expand_8bpp_to_rgb(tile_data)
            y_min = max(0, y)
            y_max = min(160, y + 8)
            x_min = max(0, x)
            x_max = min(240, x + 8)
            if y_max > y_min and x_max > x_min:
                screen_buffer[y_min:y_max, x_min:x_max] = rgba_tile[:8, :8]

    def render_frame_vectorized(self, tilemap_entries=None):
        self.pixel_buffer.fill(0)
        if tilemap_entries is not None:
            for idx in range(min(len(tilemap_entries), 960)):
                entry = tilemap_entries[idx]
                x = (idx * 8) % 240
                y = (idx // 30) * 8
                tile_idx = entry & 0x3FF
                if self.tiles_4bpp and tile_idx < (len(self.tiles_4bpp) // 32):
                    self.render_tile_4bpp_to_screen(x, y, tile_idx, self.pixel_buffer, self.palette_bg)
        return self.pixel_buffer


def vectorized_palette_lookup(palette_data, indices):
    """Fast 15-bit GBA color lookup using NumPy."""
    if not HAS_NUMPY:
        return np.zeros((len(indices), 4), dtype=np.uint8, order='C')
    rgba_palette = []
    for color16 in palette_data:
        r = ((color16 >> 0) & 0x1F) * 8
        g = ((color16 >> 5) & 0x1F) * 8
        b = ((color16 >> 10) & 0x1F) * 8
        rgba_palette.append([r, g, b, 255])
    palette_array = np.array(rgba_palette, dtype=np.uint8, order='C')
    return palette_array[indices % len(palette_array)]


def benchmark_vectorized_vs_scoped():
    """Compare rendering: NumPy vectorized vs Python loops."""
    results = {
        'vectorized': {'mean_ms': 0, 'samples': 0},
        'scoped': {'mean_ms': 0, 'samples': 0}
    }
    if not HAS_NUMPY:
        return results
    palette_bg = [0x7FFF] * 256
    tiles_4bpp = bytes([0x11, 0x22, 0x33] * 100 + [0] * 2900)
    tiles_8bpp = bytes([255] * 100 + [0] * 6300)
    screen_vec = np.zeros((160, 240, 4), dtype=np.uint8, order='C')
    screen_scp = np.zeros((160, 240, 4), dtype=np.uint8, order='C')
    num_samples = 500
    if num_samples > 0:
        start = time.perf_counter()
        for _ in range(num_samples):
            screen_scp.fill(0)
            for y in range(160):
                for x in range(240):
                    screen_scp[y, x] = [100, 100, 100, 255]
        scoped_time = time.perf_counter() - start
        start = time.perf_counter()
        fill_color = np.array([[100, 100, 100, 255]], dtype=np.uint8, order='C')
        for _ in range(num_samples):
            screen_vec.fill(0)
            screen_vec[:] = fill_color
        vectorized_time = time.perf_counter() - start
        results['scoped'] = {
            'mean_ms': (scoped_time * 1000.0 / num_samples),
            'samples': num_samples
        }
        results['vectorized'] = {
            'mean_ms': (vectorized_time * 1000.0 / num_samples),
            'samples': num_samples
        }
        if vectorized_time > 0:
            results['speedup'] = scoped_time / vectorized_time
    return results


def render_rom_pattern(screen, ROM_DATA):
    """Render GBA ROM pattern using vectorized renderer."""
    if not HAS_NUMPY:
        return
    palette_bg = ROM_DATA.get('palette_bg', [])
    tiles_4bpp = ROM_DATA.get('tiles_4bpp', None)
    tiles_8bpp = ROM_DATA.get('tiles_8bpp', None)
    tilemap_entries = ROM_DATA.get('bg0_tilemap', None)
    renderer = VectorizedRenderer(palette_bg=palette_bg, tiles_4bpp=tiles_4bpp, tiles_8bpp=tiles_8bpp)
    frame = renderer.render_frame_vectorized(tilemap_entries=tilemap_entries)
    if hasattr(screen, 'dtype'):
        screen[:] = frame


# ============================================================================
# Memory Layout Optimizations
# ============================================================================

def _expand_4bpp_to_rgb_fast(tile_bytes, palette):
    """Fast 4BPP tile expansion using numpy bitwise operations."""
    pixels = np.frombuffer(tile_bytes, dtype=np.uint8)
    high = np.right_shift(pixels, 4)
    low = pixels & 0x0F
    indices = np.concatenate([high, low])
    if len(palette) > 0:
        safe_indices = indices % min(len(palette), 256)
        rgba = palette[safe_indices]
    else:
        rgba = np.zeros((64, 4), dtype=np.uint8, order='C')
        rgba[:, 3] = 255
    return rgba.reshape(8, 8, 4, order='C')


def create_contiguous_tile_array(tiles_data):
    """Create contiguous NumPy array from tile data."""
    if not HAS_NUMPY or len(tiles_data) == 0:
        return None
    arr = np.frombuffer(bytes(tiles_data), dtype=np.uint8)
    return arr.reshape(-1, 32, order='C')


def create_masked_pixel_buffer(height=160, width=240):
    """Pre-allocate RGBA pixel buffer with C-contiguous layout."""
    if not HAS_NUMPY:
        return None
    return np.zeros((height, width, 4), dtype=np.uint8, order='C')


def render_batch_4bpp_tiles(tiles_array, tilemap, frame=None, palette_bg=None):
    """Batch render multiple 4BPP tiles efficiently."""
    if not HAS_NUMPY:
        return None
    if palette_bg is None:
        palette_bg = [0x7FFF]
    palette = np.array([[c & 0x1F] * 4 + [255] for c in palette_bg], dtype=np.uint8, order='C')
    if frame is None:
        frame = np.zeros((160, 240, 4), dtype=np.uint8, order='C')

    for idx, tile_idx in enumerate(tilemap):
        if tile_idx < 0 or tile_idx >= len(tiles_array):
            continue
        tile_bytes = tiles_array[tile_idx:tile_idx + 1].flatten()
        rgba_tile = _expand_4bpp_to_rgb_fast(tile_bytes, palette)
        y_pos = (idx % 32) * 8
        x_pos = (idx // 32) * 8
        if y_pos < 160 and x_pos < 240:
            frame[y_pos:y_pos+8, x_pos:x_pos+8] = rgba_tile[:8, :8]
    return frame


if __name__ == "__main__":
    print("=" * 60)
    print("GBAtoPy Vectorized Rendering Scaffold")
    print("=" * 60)
    print("\nVectorized Rendering Features:")
    print("  • NumPy array-based pixel buffers")
    print("  • Batch palette lookup via advanced indexing")
    print("  • Tile expansion with contiguous memory layout")
    print("  • Single-vector frame rendering for performance")
    print("\nBenchmark Results:")
    if HAS_NUMPY:
        results = benchmark_vectorized_vs_scoped()
        print(f"  Scoped rendering:  {results['scoped']['mean_ms']:.4f} ms")
        print(f"  Vectorized:        {results['vectorized']['mean_ms']:.4f} ms")
        if results['vectorized']['mean_ms'] > 0:
            print(f"  Potential speedup: {results['speedup']:.2f}x")
    else:
        print("  NumPy not available - benchmarks disabled")
    print("\nReady for integration with ROM pipeline")
