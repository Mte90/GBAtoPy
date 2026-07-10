#!/usr/bin/env python3
"""Batch golden screenshot generator using mGBA.

Captures golden screenshots for all (or selected) test ROMs at specified frame counts.
Screenshots are saved to scripts/screenshot/golden/ with the naming convention:
  golden_<rom_name>_frame_<N>.png

Usage:
  python3 scripts/generate_goldens.py                    # All ROMs, frame 60
  python3 scripts/generate_goldens.py --rom hello         # Single ROM
  python3 scripts/generate_goldens.py --frames 1,10,30   # Multiple frames
  python3 scripts/generate_goldens.py --frames 1,10,30,60 --workers 4
  python3 scripts/generate_goldens.py --mgba /path/to/mgba  # Custom mGBA path
"""

import argparse
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROMS_DIR = PROJECT_ROOT / "test_roms" / "roms"
GOLDEN_DIR = PROJECT_ROOT / "scripts" / "screenshot" / "golden"
LUA_SCRIPT = PROJECT_ROOT / "scripts" / "screenshot" / "golden_capture.lua"
MGBA_BIN = PROJECT_ROOT / "mgba" / "build" / "sdl" / "mgba"


def capture_golden(rom_path, frame, mgba_bin, timeout=120):
    """Capture a single golden screenshot. Returns (success, error_msg)."""
    rom_base = rom_path.stem  # e.g. "hello" from "hello.gba"
    output_path = GOLDEN_DIR / f"golden_{rom_base}_frame_{frame}"
    output_png = str(output_path) + ".png"

    env = os.environ.copy()
    env["GBATOPY_SCREENSHOT_PATH"] = str(output_path)
    env["GBATOPY_TARGET_FRAME"] = str(frame)

    try:
        result = subprocess.run(
            [str(mgba_bin), "-S", str(LUA_SCRIPT), str(rom_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode != 0:
            return False, f"mGBA exit {result.returncode}: {result.stderr[-200:]}"
        if not os.path.exists(output_png):
            return False, "screenshot not created"
        return True, None
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Generate golden screenshots via mGBA")
    parser.add_argument("--rom", type=str, help="Single ROM name (without .gba)")
    parser.add_argument("--filter", type=str, help="Filter ROMs by name substring")
    parser.add_argument(
        "--frames", type=str, default="60",
        help="Comma-separated frame numbers (default: 60)"
    )
    parser.add_argument("--workers", type=int, default=2, help="Parallel mGBA instances")
    parser.add_argument("--mgba", type=Path, default=MGBA_BIN, help="Path to mGBA binary")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per ROM in seconds")
    args = parser.parse_args()

    if not args.mgba.exists():
        print(f"ERROR: mGBA not found at {args.mgba}")
        print("Build mGBA first or specify --mgba /path/to/mgba")
        sys.exit(1)

    if not LUA_SCRIPT.exists():
        print(f"ERROR: Lua script not found: {LUA_SCRIPT}")
        sys.exit(1)

    frames = [int(f.strip()) for f in args.frames.split(",")]
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

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
        print("ERROR: No ROMs to process")
        sys.exit(1)

    # Build work items: (rom, frame) pairs
    work_items = []
    for rom in roms:
        for frame in frames:
            work_items.append((rom, frame))

    print(f"Generating {len(work_items)} golden screenshot(s)")
    print(f"  ROMs: {len(roms)}")
    print(f"  Frames: {frames}")
    print(f"  Workers: {args.workers}")
    print(f"  Output: {GOLDEN_DIR}")
    print()

    success_count = 0
    fail_count = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for rom, frame in work_items:
            futures[executor.submit(capture_golden, rom, frame, args.mgba, args.timeout)] = (rom, frame)

        for i, future in enumerate(as_completed(futures), 1):
            rom, frame = futures[future]
            success, err = future.result()
            name = rom.stem
            if success:
                success_count += 1
                print(f"[{i:3d}/{len(work_items)}] {name:30s} frame {frame:3d}  OK")
            else:
                fail_count += 1
                print(f"[{i:3d}/{len(work_items)}] {name:30s} frame {frame:3d}  FAIL: {err}")

    print()
    print(f"Done: {success_count} succeeded, {fail_count} failed")
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
