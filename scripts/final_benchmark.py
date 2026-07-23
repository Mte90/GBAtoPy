#!/usr/bin/env python3
"""
Final Performance Comparison Script
Compares before/after metrics for all optimizations.
"""

import json
import subprocess
import time
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import List

@dataclass
class Metrics:
    rom_name: str
    code_size_lines: int
    code_size_bytes: int
    exec_time_ms: float
    fps: float

def transpile_and_measure(rom_path: str, output_path: str) -> tuple:
    """Transpile ROM and measure code size."""
    start = time.perf_counter()
    result = subprocess.run(
        ['cargo', 'run', '-p', 'gbatopy-cli', '--', 'pipeline',
         '--rom', rom_path, '--output', output_path],
        capture_output=True, timeout=120
    )
    transpile_time = time.perf_counter() - start
    
    if result.returncode != 0:
        return None
    
    size_bytes = Path(output_path).stat().st_size
    with open(output_path, 'r') as f:
        size_lines = len(f.readlines())
    
    return size_lines, size_bytes, transpile_time

def run_benchmark(rom_path: str, frames: int = 60) -> tuple:
    """Run ROM and measure execution time."""
    py_path = rom_path.replace('.gba', '.py')
    start = time.perf_counter()
    result = subprocess.run(
        ['python3', py_path, '--headless', '--frame', str(frames)],
        capture_output=True, timeout=300
    )
    exec_time = (time.perf_counter() - start) * 1000
    fps = (frames / exec_time) * 1000 if exec_time > 0 else 0
    
    return exec_time, fps

def compare_roms(rom_dir: str, output_dir: str = "/tmp"):
    """Compare all ROMs and generate report."""
    roms = list(Path(rom_dir).glob("*.gba"))
    results = []
    
    print(f"Comparing {len(roms)} ROMs...")
    
    for rom in roms:
        name = rom.stem
        print(f"  {name}...")
        
        # Transpile
        output = f"{output_dir}/{name}_optimized.py"
        metrics = transpile_and_measure(str(rom), output)
        if not metrics:
            continue
        
        lines, size, transpile_time = metrics
        
        # Benchmark
        bench = run_benchmark(str(rom))
        if not bench:
            continue
        
        exec_time, fps = bench
        
        results.append({
            'name': name,
            'lines': lines,
            'size_kb': round(size / 1024, 2),
            'exec_time_ms': round(exec_time, 2),
            'fps': round(fps, 1),
            'transpile_time_s': round(transpile_time, 2)
        })
    
    # Summary
    avg_lines = sum(r['lines'] for r in results) / len(results)
    avg_fps = sum(r['fps'] for r in results) / len(results)
    avg_size = sum(r['size_kb'] for r in results) / len(results)
    
    print(f"\n{'='*70}")
    print("OPTIMIZATION RESULTS SUMMARY")
    print(f"{'='*70}")
    print(f"ROMs tested: {len(results)}")
    print(f"Average code size: {avg_lines:.0f} lines ({avg_size:.0f} KB)")
    print(f"Average FPS: {avg_fps:.1f}")
    
    # Save results
    with open("optimization_results.json", 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: optimization_results.json")
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark GBAtoPy transpiled ROMs")
    parser.add_argument("--rom", type=str, help="Single ROM path")
    parser.add_argument("--roms-dir", type=str, default="test_roms/roms",
                       help="Directory containing ROMs")
    parser.add_argument("--output-dir", type=str, default="/tmp",
                       help="Output directory for transpiled Python")
    parser.add_argument("--frames", type=int, default=60,
                       help="Number of frames to benchmark")
    args = parser.parse_args()
    
    compare_roms(args.roms_dir if not args.rom else str(Path(args.rom).parent), 
                 args.output_dir)
