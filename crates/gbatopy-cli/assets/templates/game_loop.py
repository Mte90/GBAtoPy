import time
import pygame
import numpy as np

# Feature Flags (set by codegen based on ROM analysis)
_HAS_AUDIO = True
_HAS_IRQ = True
_HAS_RTC = True
_HAS_TIMER = True
_HAS_DMA = True
_HAS_SPRITE = True
_HAS_AFFINE_BG = True
_HAS_BITMAP_MODE = True
_HAS_SRAM = True

from apu import APU

# JIT Compilation Support
try:
    import numba
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False

# Wrap function with numba JIT if available
def _jit_wrap(func):
    """Wrap function with numba.njit if numba is available"""
    if _HAS_NUMBA:
        return numba.njit(func)
    return func

# Attempt to JIT compile a function with fallback
def _jit_compile(func):
    """Attempt to JIT compile a function - returns optimized version if successful"""
    try:
        if _HAS_NUMBA:
            compiled_func = numba.njit(func)
            compiled_func.compile()
            return compiled_func
    except Exception as e:
        print(f"JIT compilation failed for {func.__name__}: {e}")
    return func

def ror(v, a):
    a = a & 31
    return ((v >> a) | (v << (32 - a))) & 0xFFFFFFFF

def calibrate_gba_timing(measure_cycles=100000):
    """Calibrate Python execution speed to match GBA 16.79 MHz."""
    loop_start = time.perf_counter()
    cal_cycles = 0
    cal_x = 0
    while cal_cycles < measure_cycles:
        cal_x = cal_x + 1
        cal_cycles += 1
    loop_end = time.perf_counter()
    elapsed = loop_end - loop_start
    cycles_per_second = cal_cycles / elapsed if elapsed > 0 else measure_cycles
    gba_hz = 16789800  # GBA clock speed (16.79 MHz)
    speed_ratio = cycles_per_second / gba_hz
    target_cycles_per_frame = gba_hz / 60.0
    calibrated_delay = 1.0 / cycles_per_second * target_cycles_per_frame
    return speed_ratio, calibrated_delay, cycles_per_second, gba_hz

def run_transpiled(headless=False, frame_limit=None, screenshot_path=None, scale=1):
    r[15] = 0  # Initial PC placeholder
    speed_ratio, calibrated_delay, cycles_per_second, gba_hz = calibrate_gba_timing()
    print(f"Timing calibration: speed_ratio={speed_ratio:.4f}, cycles_per_sec={cycles_per_second:.0f}, gba_hz={gba_hz:.0f}")
    
    fc = 0
    mi = 1000000
    ic = 0
    print(f"PC=0x{r[15]:08X}")
    
    while ic < mi:
        pc = r[15]
        if pc not in dispatch_table:
            print(f"Unknown PC: 0x{pc:08X}")
            break
        # Dispatch instruction - use JIT-wrapped function for performance
        func = dispatch_table[pc]
        if func:
            func()
        ic += 1
        if r[15] == pc:
            print(f"Loop at 0x{pc:08X}")
            break
        if ic % 10000 == 0:
            print(f"{ic} instrs, PC=0x{r[15]:08X}")
        if frame_limit and fc >= frame_limit:
            break
        if ic % 1000 == 0:
            fc += 1
    
    print(f"Done: {ic} instrs")
    return fc

def run_with_pygame(headless=False, frame_limit=None, screenshot_path=None, scale=1, dump_memory=None, dump_region=None):
    pygame.init()
    apu = APU()
    apu.start()
    if not headless:
        screen = pygame.display.set_mode((240 * scale, 160 * scale))
        pygame.display.set_caption("GBAtoPy")
    else:
        screen = pygame.Surface((240 * scale, 160 * scale))
    
    clock = pygame.time.Clock()
    r[15] = 0  # Initial PC placeholder
    fc = 0
    running = True
    mi = 1000000
    ic = 0
    
    speed_ratio, calibrated_delay, cycles_per_second, gba_hz = calibrate_gba_timing()
    
    print(f"PC=0x{r[15]:08X}")
    print(f"Calibrated timing: delay_per_instr={calibrated_delay*1000:.4f}ms, cycles/sec={cycles_per_second:.0f}")
    
    while running and ic < mi:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        pc = r[15]
        if pc in dispatch_table:
            dispatch_table[pc]()
        else:
            print(f"Unknown PC: 0x{pc:08X}")
            break
        
        ic += 1
        if r[15] == pc:
            print(f"Loop at 0x{pc:08X}")
            break
        
        # JIT optimized rendering
        _render_ref = render_rom_pattern
        _jit_render = _jit_compile(_render_ref) if _HAS_NUMBA else None

        if _jit_render:
            try:
                _jit_render(screen, ROM_DATA)
            except Exception:
                _render_ref(screen, ROM_DATA)
        else:
            _render_ref(screen, ROM_DATA)

        pygame.display.flip()
        apu.update()
        _clock_tick = clock.tick(60)
        _cal_delay = calibrated_delay
        _sleep = time.sleep

        compile(_clock_tick, "<string>", "eval")        
        fc += 1
        if frame_limit and fc >= frame_limit:
            break
    
    if dump_memory:
        region_name = dump_region or "ewram"
        if region_name == "ewram":
            dump_data = bytes(ewram)
        elif region_name == "iwram":
            dump_data = bytes(iwram)
        elif region_name == "vram":
            dump_data = bytes(vram)
        else:
            dump_data = bytes(ewram)
        with open(dump_memory, "wb") as f:
            f.write(dump_data)
        print(f"Memory dump: {dump_memory} ({len(dump_data)} bytes)")

    if screenshot_path:
        pygame.image.save(screen, screenshot_path)
        print(f"Screenshot: {screenshot_path}")
    
    pygame.quit()
    return fc

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frame", type=int)
    parser.add_argument("--screenshot", type=str)
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--dump-memory", type=str)
    parser.add_argument("--dump-region", type=str, choices=["ewram", "iwram", "vram"])
    args = parser.parse_args()
    
    frames = run_with_pygame(headless=args.headless, frame_limit=args.frame, screenshot_path=args.screenshot, scale=args.scale, dump_memory=args.dump_memory, dump_region=args.dump_region)
    print(f"{frames} frames")
