#!/usr/bin/env python3
"""Optimized test runner for GBAtoPy - parallel execution with timeout.

Test Levels:
  Level 1 (syntax): Transpile + py_compile (default)
  Level 2 (execution): Run script, check for crashes
  Level 3 (visual): Screenshot comparison with golden
"""

import subprocess, tempfile, os, sys, argparse, shutil
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
            capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            return (rom_path.name, False, "transpile_failed", output)
        compile_result = subprocess.run(
            ["python3", "-m", "py_compile", output],
            capture_output=True, timeout=30
        )
        return (rom_path.name, compile_result.returncode == 0, 
                "ok" if compile_result.returncode == 0 else "syntax_error", output)
    except subprocess.TimeoutExpired:
        return (rom_path.name, False, "timeout", output)

def execute_rom(output_path, frame=60):
    """Execute generated script and capture screenshot."""
    screenshot_path = output_path.replace('.py', '_frame{}.png'.format(frame))
    try:
        result = subprocess.run(
            ["python3", output_path, "--headless", "--frame={}".format(frame),
             "--screenshot", screenshot_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return False, "execution_failed", screenshot_path
        if not os.path.exists(screenshot_path):
            return False, "no_screenshot", screenshot_path
        return True, "ok", screenshot_path
    except subprocess.TimeoutExpired:
        return False, "timeout", screenshot_path

def compare_screenshot(transpiled_screenshot, rom_name):
    """Compare transpiled screenshot with golden."""
    golden_dir = Path("scripts/screenshot/golden")
    golden_pattern = "golden_{}_frame_*.png".format(rom_name.replace('.gba', ''))
    golden_files = list(golden_dir.glob(golden_pattern))
    
    if not golden_files:
        return None, "no_golden_screenshot"
    
    golden_path = golden_files[0]
    result = subprocess.run(
        ["python3", "scripts/verify/compare_screenshots.py",
         "--golden", str(golden_path),
         "--transpiled", str(transpiled_screenshot),
         "--threshold", "30"],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        return True, "pass", result.stdout
    else:
        return False, "fail", result.stdout[:200]

def test_rom_level2(rom_path):
    """Level 2: Transpile + Execute."""
    rom_name = rom_path.name
    success, status, output = transpile_rom(rom_path)
    if not success:
        return (rom_name, False, "level1_{}".format(status))
    
    exec_success, exec_status, _ = execute_rom(output)
    if not exec_success:
        return (rom_name, False, "level2_{}".format(exec_status))
    
    return (rom_name, True, "level2_ok")

def test_rom_level3(rom_path):
    """Level 3: Transpile + Execute + Visual Compare."""
    rom_name = rom_path.name
    success, status, output = transpile_rom(rom_path)
    if not success:
        return (rom_name, False, "level1_{}".format(status))
    
    exec_success, exec_status, screenshot = execute_rom(output)
    if not exec_success:
        return (rom_name, False, "level2_{}".format(exec_status))
    
    compare_result, compare_status, details = compare_screenshot(screenshot, rom_name)
    if compare_result is None:
        return (rom_name, True, "level3_no_golden")
    elif compare_result:
        return (rom_name, True, "level3_pass")
    else:
        return (rom_name, False, "level3_fail: {}".format(details))

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
