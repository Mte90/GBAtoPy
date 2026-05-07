#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)


def find_test_roms(rom_dir: str) -> list:
    roms = []
    for root, dirs, files in os.walk(rom_dir):
        for file in files:
            if file.endswith(".gba"):
                roms.append(os.path.join(root, file))
    return sorted(roms)


def generate_python_for_rom(rom_path: str, output_dir: str, assets_dir: str) -> str:
    rom_name = Path(rom_path).stem
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"{rom_name}_test.py")

    if os.path.exists(output_path):
        return output_path

    print(f"  Transpiling {rom_name}...")

    transpiler = Path("/home/archimede/Desktop/projects/GBAtoPy/target/debug/gbatopy-cli")
    if not transpiler.exists():
        print(f"    ERROR: Transpiler not found at {transpiler}")
        print(f"    Run: cargo build --bin gbatopy-cli")
        return None

    result = subprocess.run(
        [
            str(transpiler),
            "pipeline",
            "--rom",
            rom_path,
            "--output",
            output_path,
            "--assets-dir",
            assets_dir,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        print(f"    ERROR: {result.stderr[:200]}")
        return None

    return output_path


def execute_rom_python(py_path: str, screenshot_path: str, frames: int = 3) -> dict:
    result = {"success": False, "error": None, "non_black_pixels": 0, "execution_time": 0}

    try:
        cmd = [
            "python3",
            py_path,
            "--headless",
            f"--frame={frames}",
            f"--screenshot={screenshot_path}",
        ]

        import time

        start = time.time()

        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, cwd=str(Path(py_path).parent)
        )

        result["execution_time"] = time.time() - start

        if proc.returncode != 0:
            result["error"] = proc.stderr[:500]
            return result

        if os.path.exists(screenshot_path):
            img = Image.open(screenshot_path)
            pixels = list(img.getdata())
            non_black = sum(1 for r, g, b in pixels if r > 30 or g > 30 or b > 30)
            result["non_black_pixels"] = non_black
            result["success"] = non_black > 100

    except subprocess.TimeoutExpired:
        result["error"] = "Execution timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


def verify_regression(py_path: str, frames: int = 500) -> dict:
    result = {"success": False, "frames_completed": 0, "error": None}

    try:
        cmd = ["python3", py_path, "--headless", f"--frame={frames}"]

        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, cwd=str(Path(py_path).parent)
        )

        if proc.returncode == 0:
            result["success"] = True
            result["frames_completed"] = frames
        else:
            result["error"] = proc.stderr[:500]
            import re

            match = re.search(r"Frame (\d+)", proc.stdout)
            if match:
                result["frames_completed"] = int(match.group(1))

    except subprocess.TimeoutExpired:
        result["error"] = "Timeout during regression test"
        result["frames_completed"] = frames // 2
    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description="Verify all test ROMs")
    parser.add_argument("--rom-dir", default="test_roms/", help="Directory containing test ROMs")
    parser.add_argument(
        "--output-dir", default="output_python/", help="Output directory for generated Python"
    )
    parser.add_argument(
        "--assets-dir", default="crates/gbatopy-cli/assets", help="Assets directory"
    )
    parser.add_argument("--report", default="verification_report.json", help="Output report path")
    parser.add_argument("--frames", type=int, default=3, help="Frames for rendering test")
    parser.add_argument(
        "--regression-frames", type=int, default=100, help="Frames for regression test"
    )
    args = parser.parse_args()

    print(f"Scanning for ROMs in {args.rom_dir}...")
    roms = find_test_roms(args.rom_dir)
    print(f"Found {len(roms)} ROMs")

    os.makedirs(args.output_dir, exist_ok=True)

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_roms": len(roms),
        "passed": 0,
        "failed": 0,
        "results": [],
    }

    for i, rom_path in enumerate(roms):
        rom_name = Path(rom_path).stem
        print(f"\n[{i + 1}/{len(roms)}] Testing {rom_name}...")

        result = {
            "rom": rom_path,
            "rom_name": rom_name,
            "rendering": None,
            "regression": None,
            "status": "UNKNOWN",
        }

        py_path = generate_python_for_rom(rom_path, args.output_dir, args.assets_dir)
        if not py_path:
            result["status"] = "TRANSPILER_FAILED"
            report["failed"] += 1
            report["results"].append(result)
            continue

        screenshot_path = f"/tmp/{rom_name}_screenshot.png"
        render_result = execute_rom_python(py_path, screenshot_path, args.frames)
        result["rendering"] = render_result

        if render_result["success"]:
            regression_result = verify_regression(py_path, args.regression_frames)
            result["regression"] = regression_result

            if regression_result["success"]:
                result["status"] = "PASS"
                report["passed"] += 1
            else:
                result["status"] = "REGRESSION_FAILED"
                report["failed"] += 1
        else:
            result["status"] = "RENDERING_FAILED"
            report["failed"] += 1

        report["results"].append(result)

        status_icon = "✓" if result["status"] == "PASS" else "✗"
        print(f"  {status_icon} {rom_name}: {result['status']}")
        if result["rendering"] and result["rendering"]["error"]:
            print(f"    Rendering error: {result['rendering']['error'][:100]}")
        if result["regression"] and result["regression"]["error"]:
            print(f"    Regression error: {result['regression']['error'][:100]}")

    with open(args.report, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"VERIFICATION COMPLETE")
    print(f"  Total: {report['total_roms']}")
    print(f"  Passed: {report['passed']}")
    print(f"  Failed: {report['failed']}")
    print(f"  Report: {args.report}")
    print(f"{'=' * 60}")

    sys.exit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
