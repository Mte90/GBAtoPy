#!/usr/bin/env python3
"""
visual_test.py: Automated visual test for GBAtoPy transpiler

Compares transpiled Python output against mGBA golden screenshots.
Generates a JSON report with matching percentages.

Usage:
    python3 scripts/verify/visual_test.py
    python3 scripts/verify/visual_test.py --roms arm stripes hello bios armwrestler shades greenswap basic-timing
    python3 scripts/verify/visual_test.py --threshold 90
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from PIL import Image


# ROMs to test (without .gba extension)
DEFAULT_ROMS = [
    'arm',
    'stripes',
    'hello',
    'bios',
    'armwrestler',
    'shades',
    'greenswap',
    'basic-timing',
]

# Frames to capture and compare
FRAMES = [1, 10, 20, 30]

# Default matching threshold (percentage)
DEFAULT_THRESHOLD = 95.0

# Pixel tolerance for comparison
TOLERANCE = 10

# Directories
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
ROMS_DIR = PROJECT_ROOT / "test_roms" / "roms"
DEFAULT_MGBA = PROJECT_ROOT / "mgba" / "build" / "sdl" / "mgba"


def check_mgba() -> Optional[Path]:
    """Check if mGBA binary exists."""
    mgba = Path(os.environ.get("MGBA", DEFAULT_MGBA))
    if not mgba.exists():
        print(f"Warning: mGBA not found at {mgba}")
        print("Set MGBA env var or build mGBA first")
        return None
    return mgba


def capture_mgba_golden(rom_path: Path, output_dir: Path, mgba: Path) -> List[Path]:
    """Capture golden screenshots using mGBA."""
    lua_content = f'''local targetFrames = {{{", ".join(str(f) for f in FRAMES)}}}
local name = "{output_dir}/golden_frame"
local frameIdx = 1

local function onFrame()
    local current = emu:currentFrame()
    if frameIdx > #targetFrames then
        os.exit(0)
    end
    if current >= targetFrames[frameIdx] then
        emu:screenshot(name .. "_" .. targetFrames[frameIdx] .. ".png")
        print("Frame " .. targetFrames[frameIdx])
        frameIdx = frameIdx + 1
        if frameIdx > #targetFrames then
            os.exit(0)
        end
    end
end

callbacks:add("frame", onFrame)
'''
    lua_temp = Path(tempfile.gettempdir()) / f"golden_{rom_path.stem}.lua"
    lua_temp.write_text(lua_content)

    result = subprocess.run(
        [str(mgba), "--script", str(lua_temp), str(rom_path)],
        capture_output=True, text=True, timeout=30
    )

    lua_temp.unlink(missing_ok=True)

    captured = [output_dir / f"golden_frame_{f}.png" for f in FRAMES]
    return [p for p in captured if p.exists()]


def transpile_rom(rom_path: Path, output_path: Path) -> bool:
    """Transpile a ROM to Python using GBAtoPy."""
    result = subprocess.run(
        ["cargo", "run", "-q", "-p", "gbatopy-cli", "--",
         "pipeline", "--rom", str(rom_path), "--output", str(output_path)],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        print(f"  Transpile failed: {result.stderr}")
        return False
    if not output_path.exists():
        print(f"  Transpiled file not created")
        return False
    print(f"  Transpiled: {output_path.name}")
    return True


def capture_transpiled(output_dir: Path, transpiled_path: Path) -> List[Path]:
    """Run transpiled Python and capture screenshots."""
    captured = []
    for frame in FRAMES:
        out = output_dir / f"transpiled_frame_{frame}.png"
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy"}
        result = subprocess.run(
            ["python3", str(transpiled_path), "--headless",
             f"--frame={frame}", "--screenshot", str(out)],
            env=env, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and out.exists():
            captured.append(out)
            print(f"    Frame {frame}: {out.name}")
        else:
            print(f"    Frame {frame}: FAILED")
    return captured


def compare_images(img1: Image.Image, img2: Image.Image) -> Tuple[int, float, Image.Image, Tuple[int, int]]:
    """Compare two images and return matching percentage."""
    w = min(img1.width, img2.width)
    h = min(img1.height, img2.height)
    i1 = img1.resize((w, h), Image.NEAREST)
    i2 = img2.resize((w, h), Image.NEAREST)

    p1 = list(i1.getdata())
    p2 = list(i2.getdata())

    matching = sum(1 for a, b in zip(p1, p2)
                   if all(abs(ca - cb) <= TOLERANCE
                          for ca, cb in zip(a[:3], b[:3])))

    total = len(p1)
    pct = (matching / total) * 100 if total else 0

    diff = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dp = []
    for a, b in zip(p1, p2):
        if all(abs(ca - cb) <= TOLERANCE for ca, cb in zip(a[:3], b[:3])):
            dp.append((0, 0, 0, 0))
        else:
            dp.append((255, 0, 0, 255))
    diff.putdata(dp)

    return matching, pct, diff, (i1.size, i2.size)


def test_rom(rom_name: str, mgba: Optional[Path], threshold: float, keep: bool = False) -> Dict[str, Any]:
    """Test a single ROM and return results."""
    rom_path = ROMS_DIR / f"{rom_name}.gba"
    
    if not rom_path.exists():
        return {
            "rom_name": rom_name,
            "error": f"ROM not found: {rom_path}",
            "status": "ERROR",
        }

    output_dir = Path(tempfile.gettempdir()) / f"gbatopy_visual_{rom_name}"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    result = {
        "rom_name": rom_name,
        "frames": [],
    }

    print(f"\n{'='*50}")
    print(f"Testing: {rom_name}")
    print(f"{'='*50}")

    # Capture golden screenshots
    print(f"\n[1/3] Capturing golden screenshots...")
    golden = []
    if mgba:
        golden = capture_mgba_golden(rom_path, output_dir, mgba)
    if not golden:
        print(f"  No golden screenshots (mGBA unavailable)")

    # Transpile ROM
    print(f"\n[2/3] Transpiling ROM...")
    transpiled_path = Path(tempfile.gettempdir()) / f"transpiled_{rom_name}.py"
    if not transpile_rom(rom_path, transpiled_path):
        result["error"] = "Transpile failed"
        result["status"] = "ERROR"
        if not keep:
            shutil.rmtree(output_dir)
        return result

    # Run transpiled Python
    print(f"\n[3/3] Running transpiled Python...")
    transpiled = capture_transpiled(output_dir, transpiled_path)
    if not transpiled:
        result["error"] = "No screenshots captured"
        result["status"] = "ERROR"
        if not keep:
            shutil.rmtree(output_dir)
        return result

    # Compare screenshots
    print(f"\n{'='*50}")
    print(f"RESULTS: {rom_name}")
    print(f"{'='*50}")

    frame_results = []
    passed = 0

    for frame in FRAMES:
        g = output_dir / f"golden_frame_{frame}.png"
        t = output_dir / f"transpiled_frame_{frame}.png"

        if not g.exists():
            frame_results.append({
                "frame": frame,
                "status": "SKIP",
                "reason": "no golden",
                "matching_pct": 0,
            })
            continue
        if not t.exists():
            frame_results.append({
                "frame": frame,
                "status": "SKIP", 
                "reason": "no transpiled",
                "matching_pct": 0,
            })
            continue

        gi = Image.open(g).convert("RGB")
        ti = Image.open(t).convert("RGB")
        match, pct, diff, sizes = compare_images(gi, ti)

        diff_path = output_dir / f"diff_frame_{frame}.png"
        diff.save(diff_path)

        status = "PASS" if pct >= threshold else "FAIL"
        if status == "PASS":
            passed += 1

        frame_results.append({
            "frame": frame,
            "matching_pct": round(pct, 2),
            "status": status,
            "golden_size": sizes[0],
            "transpiled_size": sizes[1],
        })

        gs = f"{gi.width}x{gi.height}"
        ts = f"{ti.width}x{ti.height}"
        print(f"  Frame {frame:>2}: {pct:>6.2f}%  {status}  (golden={gs} transpiled={ts})")

    result["frames"] = frame_results
    result["passed"] = passed
    result["total"] = len([f for f in frame_results if f["status"] != "SKIP"])
    result["status"] = "PASS" if passed == result["total"] > 0 else "FAIL"

    print(f"\n  Summary: {passed}/{result['total']} frames passed")

    if not keep:
        shutil.rmtree(output_dir)
        print(f"  (temp files cleaned up)")
    else:
        print(f"  Screenshots: {output_dir}/")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Automated visual test for GBAtoPy transpiler"
    )
    parser.add_argument(
        "--roms",
        nargs="+",
        default=DEFAULT_ROMS,
        help=f"ROMs to test (default: {' '.join(DEFAULT_ROMS)})"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Minimum matching percentage (default: {DEFAULT_THRESHOLD})"
    )
    parser.add_argument(
        "--mgba",
        help="Path to mGBA binary"
    )
    parser.add_argument(
        "--output",
        default="scripts/verify/visual_coverage_report.json",
        help="Output JSON report path"
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep temporary screenshot files"
    )
    args = parser.parse_args()

    # Determine mGBA path
    mgba = None
    if args.mgba:
        mgba_path = Path(args.mgba)
        if mgba_path.exists():
            mgba = mgba_path
    else:
        mgba = check_mgba()

    # Test all ROMs
    print(f"\n{'#'*60}")
    print(f"# GBAtoPy Visual Test")
    print(f"# Testing {len(args.roms)} ROMs")
    print(f"# Threshold: {args.threshold}%")
    print(f"{'#'*60}")

    results = []
    for rom in args.roms:
        result = test_rom(rom, mgba, args.threshold, args.keep)
        results.append(result)

    # Generate report
    passed_roms = sum(1 for r in results if r.get("status") == "PASS")
    total_roms = len(results)
    error_roms = sum(1 for r in results if r.get("status") == "ERROR")

    report = {
        "summary": {
            "total_roms": total_roms,
            "passed": passed_roms,
            "failed": total_roms - passed_roms - error_roms,
            "errors": error_roms,
            "threshold": args.threshold,
            "overall_pass": passed_roms == total_roms,
        },
        "results": results,
    }

    # Save JSON report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {output_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Total ROMs:  {total_roms}")
    print(f"  Passed:      {passed_roms}")
    print(f"  Failed:      {total_roms - passed_roms - error_roms}")
    print(f"  Errors:      {error_roms}")
    print(f"  Threshold:   {args.threshold}%")
    print(f"\n  Overall:     {'PASS' if passed_roms == total_roms else 'FAIL'}")
    print(f"{'='*60}")

    # Exit code
    if passed_roms == total_roms:
        print(f"\n✓ All ROMs passed visual test")
        return 0
    else:
        print(f"\n✗ Some ROMs failed visual test")
        return 1


if __name__ == '__main__':
    sys.exit(main())