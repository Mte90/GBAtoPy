#!/usr/bin/env python3
import time
import sys
import json
import argparse
import subprocess
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import tempfile
import shutil


@dataclass
class ROMBenchmarkResult:
    rom_name: str
    rom_path: str
    frames_executed: int
    total_time_ms: float
    avg_frame_time_ms: float
    fps: float
    code_size_lines: int
    code_size_bytes: int
    func_count: int
    timestamp: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CodeMetrics:
    total_lines: int
    code_lines: int
    blank_lines: int
    comment_lines: int
    function_count: int
    class_count: int
    global_count: int
    file_size_bytes: int


def count_code_metrics(file_path: str) -> CodeMetrics:
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    total_lines = len(lines)
    blank_lines = 0
    comment_lines = 0
    function_count = 0
    class_count = 0
    global_count = 0
    code_lines = 0
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            blank_lines += 1
        elif stripped.startswith('#'):
            comment_lines += 1
        else:
            code_lines += 1
            if stripped.startswith('def '):
                function_count += 1
            elif stripped.startswith('class '):
                class_count += 1
            elif stripped.startswith('global '):
                global_count += 1
    
    file_size = os.path.getsize(file_path)
    
    return CodeMetrics(
        total_lines=total_lines,
        code_lines=code_lines,
        blank_lines=blank_lines,
        comment_lines=comment_lines,
        function_count=function_count,
        class_count=class_count,
        global_count=global_count,
        file_size_bytes=file_size
    )


def transpile_rom(rom_path: str, output_path: str) -> bool:
    try:
        result = subprocess.run(
            ['cargo', 'run', '-p', 'gbatopy-cli', '--', 'pipeline',
             '--rom', rom_path, '--output', output_path],
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  Transpilation failed: {e}")
        return False


def run_benchmark(py_path: str, frames: int, headless: bool = True) -> Optional[float]:
    try:
        cmd = ['python3', py_path]
        if headless:
            cmd.extend(['--headless'])
        cmd.extend(['--frame', str(frames)])
        
        start = time.perf_counter()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        end = time.perf_counter()
        
        if result.returncode != 0:
            print(f"  Runtime error: {result.stderr[:200]}")
            return None
        
        return (end - start) * 1000
    except Exception as e:
        print(f"  Benchmark failed: {e}")
        return None


def benchmark_single_rom(rom_path: str, frames: int = 60, output_dir: str = "/tmp") -> Optional[ROMBenchmarkResult]:
    rom_name = Path(rom_path).stem
    print(f"\nBenchmarking: {rom_name}")
    
    print("  Transpiling...")
    output_py = os.path.join(output_dir, f"{rom_name}_benchmark.py")
    if not transpile_rom(rom_path, output_py):
        print("  ✗ Transpilation failed")
        return None
    
    print("  Analyzing code...")
    metrics = count_code_metrics(output_py)
    print(f"    Lines: {metrics.total_lines}, Functions: {metrics.function_count}")
    
    print(f"  Running {frames} frames...")
    exec_time = run_benchmark(output_py, frames, headless=True)
    
    if exec_time is None:
        print("  ✗ Runtime failed")
        return None
    
    avg_frame_time = exec_time / frames
    fps = 1000.0 / avg_frame_time if avg_frame_time > 0 else 0
    
    result = ROMBenchmarkResult(
        rom_name=rom_name,
        rom_path=rom_path,
        frames_executed=frames,
        total_time_ms=exec_time,
        avg_frame_time_ms=avg_frame_time,
        fps=fps,
        code_size_lines=metrics.total_lines,
        code_size_bytes=metrics.file_size_bytes,
        func_count=metrics.function_count,
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
    )
    
    print(f"  ✓ Complete: {exec_time:.2f}ms total, {fps:.1f} FPS")
    return result


def benchmark_all_roms(rom_dir: str, frames: int = 60, output_dir: str = "/tmp") -> List[ROMBenchmarkResult]:
    results = []
    rom_files = list(Path(rom_dir).glob("*.gba"))
    
    print(f"\n{'='*70}")
    print(f"GBAtoPy Performance Benchmark Suite")
    print(f"{'='*70}")
    print(f"ROMs to benchmark: {len(rom_files)}")
    print(f"Frames per ROM: {frames}")
    print(f"{'='*70}")
    
    for idx, rom_path in enumerate(rom_files, 1):
        print(f"\n[{idx}/{len(rom_files)}] {rom_path.name}")
        result = benchmark_single_rom(str(rom_path), frames, output_dir)
        if result:
            results.append(result)
    
    return results


def save_results(results: List[ROMBenchmarkResult], output_path: str):
    data = {
        'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
        'total_roms': len(results),
        'results': [r.to_dict() for r in results]
    }
    
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")


def print_summary(results: List[ROMBenchmarkResult]):
    if not results:
        print("\nNo results to summarize")
        return
    
    print(f"\n{'='*70}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*70}")
    
    total_time = sum(r.total_time_ms for r in results)
    avg_fps = sum(r.fps for r in results) / len(results)
    avg_code_size = sum(r.code_size_lines for r in results) / len(results)
    
    print(f"Total ROMs benchmarked: {len(results)}")
    print(f"Total execution time: {total_time:.2f}ms")
    print(f"Average FPS: {avg_fps:.1f}")
    print(f"Average code size: {avg_code_size:.0f} lines")
    
    print(f"\nTop 5 Fastest ROMs:")
    fastest = sorted(results, key=lambda r: r.fps, reverse=True)[:5]
    for r in fastest:
        print(f"  {r.rom_name}: {r.fps:.1f} FPS ({r.total_time_ms:.2f}ms)")
    
    print(f"\nTop 5 Slowest ROMs:")
    slowest = sorted(results, key=lambda r: r.fps)[:5]
    for r in slowest:
        print(f"  {r.rom_name}: {r.fps:.1f} FPS ({r.total_time_ms:.2f}ms)")


def main():
    parser = argparse.ArgumentParser(description="GBAtoPy Performance Benchmark Suite")
    parser.add_argument("--rom", type=str, help="Single ROM path to benchmark")
    parser.add_argument("--roms-dir", type=str, default="test_roms/roms",
                       help="Directory containing ROMs to benchmark")
    parser.add_argument("--frames", type=int, default=60,
                       help="Number of frames to execute")
    parser.add_argument("--output", type=str, default="benchmark_results.json",
                       help="Output JSON file")
    parser.add_argument("--output-dir", type=str, default="/tmp",
                       help="Directory for generated Python files")
    parser.add_argument("--summary", action="store_true",
                       help="Print summary after benchmarking")
    
    args = parser.parse_args()
    
    results = []
    
    if args.rom:
        result = benchmark_single_rom(args.rom, args.frames, args.output_dir)
        if result:
            results.append(result)
    else:
        results = benchmark_all_roms(args.roms_dir, args.frames, args.output_dir)
    
    save_results(results, args.output)
    
    if args.summary or not args.rom:
        print_summary(results)


if __name__ == "__main__":
    main()
