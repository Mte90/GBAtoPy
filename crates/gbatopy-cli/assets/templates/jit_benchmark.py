#! /usr/bin/env python3
"""
GBAtoPy JIT Performance Benchmark
Compares Python vs numba JIT performance on hot paths.
"""

import time
import sys
import argparse

# JIT Compilation Support
try:
    import numba
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False

# Simulated hot path functions
def simulate_instruction_dispatch_loop(n_instructions=10000):
    """Simulate the main instruction dispatch loop"""
    r = [0] * 16
    r[15] = 0x08000000  # Initial PC
    func_map = {
        0x08000000: lambda: _simple_add(RR(0, 1), R2(1, 2)),
        0x08000004: lambda: _simple_mov(R2(3, 4), R2(5, 6)),
    }
    
    pc = r[15]
    ic = 0
    
    while ic < n_instructions:
        pc = r[15]
        if pc in func_map:
            func_map[pc]()
        ic += 1
    
    return ic

def simulate_rendering_loop(num_frames=100):
    """Simulate rendering loop with viewport updates"""
    screen = bytearray(240 * 160)  # 38400 bytes
    rom_data = bytearray(0x4000)   # 16KB ROM chunk
    
    for _ in range(num_frames):
        # Simulate: render_rom_pattern(screen, ROM_DATA)
        for i in range(0, len(screen), 4):
            screen[i] = (screen[i] + 1) % 256
        # Simulate: pygame.display.flip()
        pass
    
    return num_frames


def _simple_add(r0, r1):
    """Simulated ARM ADD instruction"""
    return r0 + r1


def _simple_mov(rd, rm):
    """Simulated ARM MOV instruction"""
    return rm


def _jit_compile(func):
    """Attempt to JIT compile a function"""
    try:
        if _HAS_NUMBA:
            compiled_func = numba.njit(func)
            compiled_func.compile()
            return compiled_func
    except Exception as e:
        print(f"JIT compilation failed for {func.__name__}: {e}", file=sys.stderr)
    return func


def benchmark_python(n_instructions=10000, n_frames=100, warmup=False):
    """Benchmark pure Python execution"""
    if warmup:
        simulate_instruction_dispatch_loop(1000)
        simulate_rendering_loop(10)
    
    # Measure dispatch loop
    dispatch_start = time.perf_counter()
    simulate_instruction_dispatch_loop(n_instructions)
    dispatch_end = time.perf_counter()
    
    # Measure rendering loop
    render_start = time.perf_counter()
    simulate_rendering_loop(n_frames)
    render_end = time.perf_counter()
    
    dispatch_time = dispatch_end - dispatch_start
    render_time = render_end - render_start
    
    return dispatch_time, render_time


def benchmark_jit(n_instructions=10000, n_frames=100, warmup=False):
    """Benchmark JIT-compiled execution"""
    if warmup:
        _jit_compile(simulate_instruction_dispatch_loop)
        _jit_compile(simulate_rendering_loop)
        simulate_instruction_dispatch_loop(1000)
        simulate_rendering_loop(10)
    
    # Measure dispatch loop
    dispatch_start = time.perf_counter()
    jit_dispatch = _jit_compile(simulate_instruction_dispatch_loop)
    jit_dispatch(n_instructions)
    dispatch_end = time.perf_counter()
    
    # Measure rendering loop
    render_start = time.perf_counter()
    jit_render = _jit_compile(simulate_rendering_loop)
    jit_render(n_frames)
    render_end = time.perf_counter()
    
    dispatch_time = dispatch_end - dispatch_start
    render_time = render_end - render_start
    
    return dispatch_time, render_time


def main():
    parser = argparse.ArgumentParser(description="GBAtoPy JIT Performance Benchmark")
    parser.add_argument("--instructions", type=int, default=10000,
                       help="Number of instructions for dispatch loop benchmark")
    parser.add_argument("--frames", type=int, default=100,
                       help="Number of frames for rendering loop benchmark")
    parser.add_argument("--warmup", action="store_true",
                       help="Run warmup to pre-JIT compile functions")
    parser.add_argument("--runs", type=int, default=3,
                       help="Number of benchmark runs (averaged)")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("GBAtoPy JIT Performance Benchmark")
    print("=" * 70)
    print(f"Instruction loop: {args.instructions} iterations")
    print(f"Rendering loop: {args.frames} frames")
    print(f"Benchmark runs: {args.runs}")
    print(f"Numba available: {_HAS_NUMBA}")
    print("=" * 70)
    
    if not _HAS_NUMBA:
        print("\nNumba not available - skipping JIT benchmarks", file=sys.stderr)
        print("\nInstall numba with: pip install numba\n")
        return
    
    results = []
    
    # Run benchmarks
    for run in range(args.runs):
        if run == 0 and args.warmup:
            results.append((benchmark_python(args.instructions, args.frames, True),
                          benchmark_python(args.instructions, args.frames, True)))
        else:
            results.append(benchmark_python(args.instructions, args.frames, run == 0 and args.warmup))
    
    # JIT run (after Python runs to avoid dual compilation)
    if args.warmup:
        for run in range(args.runs):
            if run == 0:
                results.append(benchmark_jit(args.instructions, args.frames, True))
            else:
                results.append(benchmark_jit(args.instructions, args.frames, run == 0))
    else:
        results.append(benchmark_jit(args.instructions, args.frames))
        results.append(benchmark_jit(args.instructions, args.frames))
    
    # Calculate averages
    python_dispatch_avg = sum(r[0] for r in results[:args.runs]) / args.runs
    python_render_avg = sum(r[1] for r in results[:args.runs]) / args.runs
    
    for run in range(args.runs):
        jit_dispatch = results[args.runs][0][0]
        jit_render = results[args.runs][0][1]
    
    print("\n" + "-" * 70)
    print("Results")
    print("-" * 70)
    print(f"Python Instruction Dispatch: {python_dispatch_avg*1000:.2f} ms")
    print(f"Python Rendering:            {python_render_avg*1000:.2f} ms")
    
    print(f"JIT Instruction Dispatch:    {jit_dispatch*1000:.2f} ms")
    print(f"JIT Rendering:               {jit_render*1000:.2f} ms")
    
    # Calculate speedup
    dispatch_speedup = python_dispatch_avg / jit_dispatch if jit_dispatch > 0 else float('inf')
    render_speedup = python_render_avg / jit_render if jit_render > 0 else float('inf')
    
    print("-" * 70)
    print("Speedup")
    print("-" * 70)
    print(f"Instruction Dispatch: {dispatch_speedup:.2f}x")
    print(f"Rendering:            {render_speedup:.2f}x")
    print("=" * 70)
    
    # Overall speedup
    python_total = python_dispatch_avg + python_render_avg
    jit_total = jit_dispatch + jit_render
    overall_speedup = python_total / jit_total if jit_total > 0 else float('inf')
    
    print(f"Overall: {overall_speedup:.2f}x speedup")
    print("=" * 70)
    
    return overall_speedup, dispatch_speedup, render_speedup


if __name__ == "__main__":
    main()
