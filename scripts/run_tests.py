#!/usr/bin/env python3
"""Optimized test runner for GBAtoPy - parallel execution with timeout."""

import subprocess, tempfile, os, sys, argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from time import time

def transpile_rom(rom_path):
    """Transpile single ROM and verify syntax."""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        output = f.name
    try:
        result = subprocess.run(
            ["cargo", "run", "--release", "-p", "gbatopy-cli", "--",
             "pipeline", "--rom", str(rom_path), "--output", output],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return (rom_path.name, False, "transpile_failed")
        compile_result = subprocess.run(
            ["python3", "-m", "py_compile", output],
            capture_output=True, timeout=5
        )
        return (rom_path.name, compile_result.returncode == 0, 
                "ok" if compile_result.returncode == 0 else "syntax_error")
    except subprocess.TimeoutExpired:
        return (rom_path.name, False, "timeout")
    finally:
        if os.path.exists(output):
            os.unlink(output)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--rom", type=str)
    args = parser.parse_args()
    
    roms_dir = Path("test_roms/roms")
    if not roms_dir.exists():
        print("ERROR: test_roms/roms not found"); sys.exit(1)
    
    roms = [roms_dir / args.rom] if args.rom else list(roms_dir.glob("*.gba"))
    print(f"Testing {len(roms)} ROMs with {args.workers} workers...")
    
    start = time()
    passed, failed = 0, 0
    results = []
    
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(transpile_rom, rom): rom for rom in roms}
        for future in as_completed(futures):
            name, success, status = future.result()
            results.append((name, success, status))
            if success: passed += 1
            else: failed += 1
            print(f"{'✓' if success else '✗'} {name}: {status}")
    
    elapsed = time() - start
    print(f"\n{'='*50}")
    print(f"Passed: {passed}/{passed+failed} ({100*passed/(passed+failed):.1f}%)")
    print(f"Time: {elapsed:.1f}s ({elapsed/len(roms):.1f}s/ROM)")
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
