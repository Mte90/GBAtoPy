# VRAM Initialization Strategy

## Final Decision: Zero Initialization

VRAM is initialized to **all zeros** to match real GBA hardware behavior on reset.

```python
# Real GBA hardware behavior
self.vram = _array.array('B', [0] * MemoryMap.VRAM_SIZE)
```

## Why Not Pattern Fill?

Initial attempts used a `0x55/0xAA` checkerboard pattern to make instruction-only test ROMs visible. However:

1. **Not hardware-accurate**: Real GBA zeros VRAM on reset
2. **Interferes with tilemap**: The pattern overwrites tilemap entries, causing incorrect rendering
3. **mGBA behavior**: mGBA may show graphics due to internal optimizations, but the transpiler must be faithful to hardware

## Test ROM Limitations

Small test ROMs (< 1KB) like `redline.gba`:
- Write **tilemap entries** but **no tile data**
- This is **correct behavior** - they're incomplete ROMs

**Note**: `shades.gba` and `stripes.gba` now achieve 100% golden match despite their small size, as they properly utilize the rendering pipeline.

For these ROMs to render graphics, they must either:
1. Write tile data to VRAM (0x06000000-0x06003FFF for 4BPP tiles)
2. Use DMA to copy tile data from ROM
3. Be combined with external asset extraction

## Results

| ROM | VRAM State | Screenshot |
|-----|-----------|------------|
| `shades.gba` (352B) | Zero | ✅ PASS (100% golden match) |
| `stripes.gba` | Overwritten by ROM | ✅ PASS (100% golden match) |
| Full ROMs (>10KB) | Overwritten by ROM | Correct graphics |

## Implementation Location

`crates/gbatopy-cli/assets/gba_runtime/memory.py` - `Memory.__init__()` method (line 52)

## Related

- Test ROM classification: `docs/reference/test-roms.md`
- Memory mapping: `docs/runtime-architecture.md#memory-management`
