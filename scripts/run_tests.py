#!/usr/bin/env python3
"""Unified 3-level test runner for GBAtoPy.

Test Levels:
  Level 1 (syntax):     Transpile ROM + py_compile          — always runs
  Level 2 (execution):  Run generated script --headless      — runs if L1 passes
  Level 3 (visual):     Screenshot comparison with golden     — runs if L2 passes

Usage:
  python3 scripts/run_tests.py                          # Level 1 (default)
  python3 scripts/run_tests.py --level 2                # Levels 1+2
  python3 scripts/run_tests.py --level 3                 # Levels 1+2+3
  python3 scripts/run_tests.py --rom hello              # Single ROM
  python3 scripts/run_tests.py --filter stripes          # Filter by name
  python3 scripts/run_tests.py --workers 8               # Parallel workers
  python3 scripts/run_tests.py --frame 10                # Execution frame count (default 10)
  python3 scripts/run_tests.py --json test-reports/report.json

Exit codes:
  0 = all passed
  1 = at least one ROM failed (or errored)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from time import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROMS_DIR = PROJECT_ROOT / "test_roms" / "roms"
GOLDEN_DIR = PROJECT_ROOT / "test-reports" / "goldens"
GBATOPY_BIN = PROJECT_ROOT / "target" / "release" / "gbatopy-cli"
COMPARE_SCRIPT = PROJECT_ROOT / "scripts" / "verify" / "compare_screenshots.py"
OUTPUT_DIR = PROJECT_ROOT / "test-reports" / "artifacts"
TEST_CONFIG_PATH = PROJECT_ROOT / "test-roms-config.toml"

# Test types that use L3 screenshot comparison
VISUAL_TEST_TYPES = {"ScreenshotMgba", "ScreenshotGolden"}


def load_test_types():
    """Load test_type for each ROM from config. Returns dict: rom_filename -> test_type."""
    types = {}
    if not TEST_CONFIG_PATH.exists():
        return types
    with open(TEST_CONFIG_PATH, "rb") as f:
        cfg = tomllib.load(f)
    for test in cfg.get("tests", []):
        name = test.get("name", "")
        if name:
            types[f"{name}.gba"] = test.get("test_type", "Smoke")
    return types


def build_transpiler():
    """Build the transpiler once before running tests."""
    print("Building gbatopy-cli (release)...")
    result = subprocess.run(
        ["cargo", "build", "--release", "-p", "gbatopy-cli"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        print("ERROR: Build failed")
        print(result.stderr[-2000:])
        sys.exit(1)
    print(f"Build complete: {GBATOPY_BIN}")
    print()


def transpile_rom(rom_path, output_path, timeout=600):
    """Transpile a single ROM. Returns (success, error_msg)."""
    result = subprocess.run(
        [str(GBATOPY_BIN), "pipeline", "--rom", str(rom_path), "--output", str(output_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr_tail = result.stderr[-500:] if result.stderr else ""
        return False, f"transpile_failed: {stderr_tail}"
    return True, None


def check_syntax(output_path):
    """Check Python syntax with py_compile. Returns (success, error_msg)."""
    try:
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(output_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return False, result.stderr.strip().split('\n')[-1] if result.stderr else "syntax_error"
        return True, None
    except subprocess.TimeoutExpired:
        return False, "syntax_check_timeout"


def execute_rom(output_path, frame=10, timeout=90):
    """Run generated script headless. Returns (success, screenshot_path, error_msg).
    Default 10 frames at ~2.5s each (slow ROMs) = 25s; 90s timeout gives margin."""
    screenshot_path = output_path.replace('.py', f'_frame{frame}.png')
    try:
        result = subprocess.run(
            ["python3", str(output_path), "--headless", f"--frame={frame}",
             "--screenshot", str(screenshot_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr_tail = result.stderr[-300:] if result.stderr else ""
            return False, None, f"execution_failed: {stderr_tail}"
        if not os.path.exists(screenshot_path):
            return False, None, "no_screenshot_produced"
        return True, screenshot_path, None
    except subprocess.TimeoutExpired:
        return False, None, "execution_timeout"
    except Exception as e:
        return False, None, f"execution_error: {e}"


def compare_screenshot(transpiled_screenshot, rom_name, frame=60):
    """Compare transpiled screenshot with golden. Returns (status, details)."""
    rom_base = rom_name.replace('.gba', '')
    candidates = [
        GOLDEN_DIR / f"{rom_base}_f{frame}.png",
        GOLDEN_DIR / f"{rom_base}_f10.png",
        GOLDEN_DIR / f"golden_{rom_base}_frame_{frame}.png",
        GOLDEN_DIR / f"golden_{rom_base}_frame_10.png",
    ]
    golden_path = next((p for p in candidates if p.exists()), None)
    if golden_path is None:
        return "no_golden", "No golden screenshot available"

    result = subprocess.run(
        ["python3", str(COMPARE_SCRIPT), "-s", str(golden_path), str(transpiled_screenshot)],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if "INCONCLUSIVE" in result.stdout:
        return "inconclusive", result.stdout[-500:]
    if result.returncode == 0:
        return "pass", result.stdout[-300:]
    return "fail", result.stdout[-500:]


def test_rom_worker(rom_path, max_level, frame, test_type="Smoke"):
    """
    Run all applicable test levels for a single ROM.

    Returns dict:
      {name, level1, level1_status, level2, level2_status,
       level3, level3_status, level3_detail, elapsed}
    """
    rom_name = rom_path.name
    result = {
        "name": rom_name,
        "level1": False,
        "level1_status": "skipped",
        "level2": False,
        "level2_status": "skipped",
        "level3": False,
        "level3_status": "skipped",
        "level3_detail": None,
        "elapsed": 0.0,
    }

    start = time()
    rom_output_dir = OUTPUT_DIR / rom_name.replace('.gba', '')
    rom_output_dir.mkdir(parents=True, exist_ok=True)
    output_py = str(rom_output_dir / "output.py")

    # --- Level 1: Transpile + Syntax ---
    success, err = transpile_rom(rom_path, output_py)
    if not success:
        result["level1"] = False
        result["level1_status"] = err or "transpile_failed"
        result["elapsed"] = round(time() - start, 2)
        return result

    success, err = check_syntax(output_py)
    if not success:
        result["level1"] = False
        result["level1_status"] = err or "syntax_error"
        result["elapsed"] = round(time() - start, 2)
        return result

    result["level1"] = True
    result["level1_status"] = "pass"

    if max_level < 2:
        result["elapsed"] = round(time() - start, 2)
        return result

    # --- Level 2: Execution ---
    success, screenshot_path, err = execute_rom(output_py, frame=frame, timeout=90)
    if not success:
        result["level2"] = False
        result["level2_status"] = err or "execution_failed"
        result["elapsed"] = round(time() - start, 2)
        return result

    result["level2"] = True
    result["level2_status"] = "pass"

    if max_level < 3:
        result["elapsed"] = round(time() - start, 2)
        return result

    # --- Level 3: Visual Comparison ---
    if test_type not in VISUAL_TEST_TYPES:
        result["level3_status"] = "skipped"
        result["level3_detail"] = f"test_type={test_type}"
        result["elapsed"] = round(time() - start, 2)
        return result

    status, detail = compare_screenshot(screenshot_path, rom_name, frame=frame)
    result["level3_status"] = status
    result["level3_detail"] = detail if status != "pass" else None
    result["level3"] = (status == "pass")

    result["elapsed"] = round(time() - start, 2)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="GBAtoPy unified 3-level test runner"
    )
    parser.add_argument(
        "--level", type=int, default=1, choices=[1, 2, 3],
        help="Max test level to run (1=syntax, 2=execution, 3=visual). Default: 1"
    )
    parser.add_argument("--rom", type=str, help="Run single ROM by name")
    parser.add_argument("--filter", type=str, help="Filter ROMs by name substring")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--frame", type=int, default=10, help="Frame count for execution")
    parser.add_argument("--json", type=Path, help="Save JSON report to this path")
    parser.add_argument("--no-build", action="store_true", help="Skip building transpiler")
    args = parser.parse_args()

    if not args.no_build:
        build_transpiler()

    test_types = load_test_types()

    if not ROMS_DIR.exists():
        print(f"ERROR: {ROMS_DIR} not found")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Collect ROMs
    if args.rom:
        rom_base = args.rom.replace('.gba', '')
        rom_path = ROMS_DIR / f"{rom_base}.gba"
        if not rom_path.exists():
            print(f"ERROR: ROM not found: {rom_path}")
            sys.exit(1)
        roms = [rom_path]
    else:
        roms = sorted(ROMS_DIR.glob("*.gba"))
        if args.filter:
            roms = [r for r in roms if args.filter.lower() in r.name.lower()]

    if not roms:
        print("ERROR: No ROMs to test")
        sys.exit(1)

    print(f"Testing {len(roms)} ROM(s) at Level {args.level} with {args.workers} workers")
    print(f"  Levels: {'syntax' if args.level == 1 else 'syntax+execution' if args.level == 2 else 'syntax+execution+visual'}")
    print()

    start = time()
    results = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                test_rom_worker, rom, args.level, args.frame,
                test_types.get(rom.name, "Smoke")
            ): rom
            for rom in roms
        }

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)

            # Print per-ROM status
            name = result["name"]
            l1 = "PASS" if result["level1"] else "FAIL"
            l2 = "PASS" if result["level2"] else ("SKIP" if result["level2_status"] == "skipped" else "FAIL")
            l3 = ("PASS" if result["level3"] else
                  "SKIP" if result["level3_status"] == "skipped" else
                  result["level3_status"].upper())

            l1_icon = "L1:PASS" if result["level1"] else f"L1:FAIL"
            l2_icon = f"L2:{l2}" if args.level >= 2 else ""
            l3_icon = f"L3:{l3}" if args.level >= 3 else ""

            print(f"[{i:3d}/{len(roms)}] {name:30s} {l1_icon:10s} {l2_icon:10s} {l3_icon:12s} ({result['elapsed']:.1f}s)")

    results.sort(key=lambda r: r["name"])
    elapsed = time() - start

    # --- Summary ---
    print()
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Level:      {args.level}")
    print(f"Total ROMs: {len(results)}")
    print(f"Time:       {elapsed:.1f}s ({elapsed/len(results):.1f}s/ROM)")
    print()

    # Level 1
    l1_pass = sum(1 for r in results if r["level1"])
    l1_fail = len(results) - l1_pass
    print(f"Level 1 (syntax):     {l1_pass}/{len(results)} passed, {l1_fail} failed")

    if args.level >= 2:
        l2_run = [r for r in results if r["level2_status"] != "skipped"]
        l2_pass = sum(1 for r in l2_run if r["level2"])
        l2_fail = len(l2_run) - l2_pass
        print(f"Level 2 (execution):  {l2_pass}/{len(l2_run)} passed, {l2_fail} failed")

    if args.level >= 3:
        l3_run = [r for r in results if r["level3_status"] not in ("skipped", "no_golden")]
        l3_pass = sum(1 for r in l3_run if r["level3"])
        l3_fail = sum(1 for r in l3_run if r["level3_status"] == "fail")
        l3_inc = sum(1 for r in l3_run if r["level3_status"] == "inconclusive")
        l3_nog = sum(1 for r in results if r["level3_status"] == "no_golden")
        l3_skip = sum(1 for r in results if r["level3_status"] == "skipped")
        print(f"Level 3 (visual):     {l3_pass}/{len(l3_run)} passed, {l3_fail} failed, {l3_inc} inconclusive")
        if l3_skip:
            print(f"                      ({l3_skip} ROMs skipped — non-visual test type)")
        if l3_nog:
            print(f"                      ({l3_nog} ROMs without golden screenshots)")

    # Failed ROMs detail
    failed = [r for r in results if not r["level1"] or
              (args.level >= 2 and r["level2_status"] not in ("skipped", "pass") and r["level1"]) or
              (args.level >= 3 and r["level3_status"] == "fail")]
    if failed:
        print()
        print("-" * 60)
        print("FAILED ROMs:")
        for r in failed:
            reasons = []
            if not r["level1"]:
                reasons.append(f"L1:{r['level1_status']}")
            elif args.level >= 2 and r["level2_status"] not in ("skipped", "pass"):
                reasons.append(f"L2:{r['level2_status']}")
            elif args.level >= 3 and r["level3_status"] == "fail":
                reasons.append(f"L3:{r['level3_detail'][:80] if r['level3_detail'] else 'fail'}")
            print(f"  {r['name']:30s} {' | '.join(reasons)}")
        print("-" * 60)

    # JSON report
    report = {
        "timestamp": datetime.now().isoformat(),
        "level": args.level,
        "frame": args.frame,
        "total_roms": len(results),
        "elapsed_seconds": round(elapsed, 2),
        "summary": {
            "level1_pass": l1_pass,
            "level1_fail": l1_fail,
        },
        "roms": results,
    }
    if args.level >= 2:
        report["summary"]["level2_pass"] = l2_pass
        report["summary"]["level2_fail"] = l2_fail
    if args.level >= 3:
        report["summary"]["level3_pass"] = l3_pass
        report["summary"]["level3_fail"] = l3_fail
        report["summary"]["level3_inconclusive"] = l3_inc

    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nJSON report: {args.json}")
    else:
        default_report = PROJECT_ROOT / "test-reports" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        default_report.parent.mkdir(parents=True, exist_ok=True)
        with open(default_report, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nJSON report: {default_report}")

    # Exit code: fail if any L1 failed, or any L2/L3 failed at the requested level
    has_failures = l1_fail > 0
    if args.level >= 2:
        has_failures = has_failures or l2_fail > 0
    if args.level >= 3:
        has_failures = has_failures or l3_fail > 0
    sys.exit(1 if has_failures else 0)


if __name__ == "__main__":
    main()
