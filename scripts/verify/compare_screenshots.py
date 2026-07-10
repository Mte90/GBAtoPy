#!/usr/bin/env python3
"""
Golden screenshot comparison for GBAtoPy vs mGBA.

Compares two PNG images pixel-by-pixel, handling different resolutions
by resizing the golden image to match the transpiled image.

Reports:
- Per-ROM pass/fail/inconclusive status
- Difference percentage
- Max pixel difference
- Content detection (prevents false-positive on both-black images)
- Optional visual diff image
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image


def load_image(path: Path) -> np.ndarray:
    """Load PNG image as numpy array."""
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    img = Image.open(path)
    if img.mode != 'RGB':
        img = img.convert('RGB')

    return np.array(img)


def resize_to_match(source: np.ndarray, target_shape: tuple) -> np.ndarray:
    """Resize source image to match target dimensions using nearest neighbor."""
    source_img = Image.fromarray(source)
    target_h, target_w = target_shape[:2]
    resized = source_img.resize((target_w, target_h), resample=Image.Resampling.NEAREST)
    return np.array(resized)


def count_content_pixels(img: np.ndarray) -> int:
    """Count pixels that are not pure black (any channel > 0)."""
    return int(np.sum(np.any(img > 0, axis=2)))


def calculate_difference(
    golden: np.ndarray,
    transpiled: np.ndarray,
    threshold: int = 30
) -> dict:
    """
    Calculate pixel-by-pixel difference between two images.

    Detects false-positive matches where both images are empty/black.

    Returns dict with:
    - pass: True only if images differ by < threshold AND both have content
    - status: "pass", "fail", or "inconclusive"
    - inconclusive_reason: explanation when status is inconclusive
    """
    if golden.shape != transpiled.shape:
        raise ValueError(
            f"Image shapes don't match: {golden.shape} vs {transpiled.shape}. "
            "Use --resize-golden to resize golden image first."
        )

    total_pixels = golden.shape[0] * golden.shape[1]

    diff = np.abs(golden.astype(np.int16) - transpiled.astype(np.int16))
    diff_mask = np.any(diff > threshold, axis=2)
    diff_pixels = int(np.sum(diff_mask))
    diff_percentage = (diff_pixels / total_pixels) * 100
    max_diff = int(np.max(diff))
    mean_diff = round(float(np.mean(diff)), 2)

    golden_content = count_content_pixels(golden)
    transpiled_content = count_content_pixels(transpiled)
    golden_content_pct = (golden_content / total_pixels) * 100
    transpiled_content_pct = (transpiled_content / total_pixels) * 100

    per_channel = {
        "red_diff": int(np.sum(diff[:, :, 0] > threshold)),
        "green_diff": int(np.sum(diff[:, :, 1] > threshold)),
        "blue_diff": int(np.sum(diff[:, :, 2] > threshold)),
    }

    MIN_CONTENT_PCT = 0.5
    inconclusive_reason = None

    if golden_content_pct < MIN_CONTENT_PCT and transpiled_content_pct < MIN_CONTENT_PCT:
        inconclusive_reason = (
            f"Both images nearly empty (golden: {golden_content_pct:.2f}%, "
            f"transpiled: {transpiled_content_pct:.2f}% content)"
        )
    elif golden_content_pct < MIN_CONTENT_PCT:
        inconclusive_reason = (
            f"Golden image nearly empty ({golden_content_pct:.2f}% content) "
            f"- golden screenshot may be bad"
        )
    elif transpiled_content_pct < MIN_CONTENT_PCT:
        inconclusive_reason = (
            f"Transpiled image nearly empty ({transpiled_content_pct:.2f}% content) "
            f"- transpiled ROM produced no visible output"
        )

    if inconclusive_reason:
        return {
            "total_pixels": int(total_pixels),
            "diff_pixels": diff_pixels,
            "diff_percentage": round(diff_percentage, 2),
            "max_diff": max_diff,
            "mean_diff": mean_diff,
            "pass": False,
            "status": "inconclusive",
            "inconclusive_reason": inconclusive_reason,
            "golden_content_pct": round(golden_content_pct, 2),
            "transpiled_content_pct": round(transpiled_content_pct, 2),
            "per_channel": per_channel,
        }

    passed = diff_percentage < 30
    return {
        "total_pixels": int(total_pixels),
        "diff_pixels": diff_pixels,
        "diff_percentage": round(diff_percentage, 2),
        "max_diff": max_diff,
        "mean_diff": mean_diff,
        "pass": passed,
        "status": "pass" if passed else "fail",
        "golden_content_pct": round(golden_content_pct, 2),
        "transpiled_content_pct": round(transpiled_content_pct, 2),
        "per_channel": per_channel,
    }


def generate_visual_diff(
    golden: np.ndarray,
    transpiled: np.ndarray,
    output_path: Path,
    highlight_threshold: int = 30
) -> None:
    """Generate a visual diff image highlighting differences in red."""
    diff = np.abs(golden.astype(np.int16) - transpiled.astype(np.int16))
    diff_mask = np.any(diff > highlight_threshold, axis=2)

    diff_img = transpiled.copy()
    diff_img[diff_mask] = [255, 0, 0]

    combined = np.hstack([golden, transpiled, diff_img])
    Image.fromarray(combined).save(output_path)
    print(f"Visual diff saved to: {output_path}")


def compare_single(
    golden_path: Path,
    transpiled_path: Path,
    resize_golden: bool = False,
    threshold: int = 30,
    output_diff: Optional[Path] = None
) -> dict:
    """Compare two screenshots and return metrics."""
    result = {
        "golden": str(golden_path),
        "transpiled": str(transpiled_path),
        "error": None,
    }

    try:
        golden = load_image(golden_path)
        transpiled = load_image(transpiled_path)

        if resize_golden or golden.shape != transpiled.shape:
            print(f"  Resizing golden from {golden.shape} to {transpiled.shape[:2]}")
            golden = resize_to_match(golden, transpiled.shape)

        metrics = calculate_difference(golden, transpiled, threshold)
        result.update(metrics)

        if output_diff:
            generate_visual_diff(golden, transpiled, output_diff, threshold)

    except Exception as e:
        result["error"] = str(e)
        result["pass"] = False
        result["status"] = "error"

    return result


def compare_multiple(
    roms: list[tuple[Path, Path]],
    resize_golden: bool = False,
    threshold: int = 30,
    output_dir: Optional[Path] = None
) -> dict:
    """Compare multiple ROM screenshots."""
    results = {
        "summary": {
            "total": len(roms),
            "passed": 0,
            "failed": 0,
            "inconclusive": 0,
            "errors": 0,
        },
        "roms": []
    }

    for i, (golden_path, transpiled_path) in enumerate(roms):
        rom_name = transpiled_path.stem

        diff_path = None
        if output_dir:
            diff_path = output_dir / f"{rom_name}_diff.png"

        print(f"\n[{i+1}/{len(roms)}] {rom_name}")
        result = compare_single(
            golden_path,
            transpiled_path,
            resize_golden=resize_golden,
            threshold=threshold,
            output_diff=diff_path
        )
        result["name"] = rom_name

        status = result.get("status", "error")
        if result.get("error"):
            results["summary"]["errors"] += 1
        elif status == "inconclusive":
            results["summary"]["inconclusive"] += 1
        elif result.get("pass"):
            results["summary"]["passed"] += 1
        else:
            results["summary"]["failed"] += 1

        results["roms"].append(result)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Compare GBAtoPy vs mGBA screenshots"
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--single", "-s",
        nargs=2,
        metavar=("GOLDEN", "TRANSPILED"),
        help="Compare two images (golden.png transpiled.png)"
    )
    mode_group.add_argument(
        "--batch", "-b",
        nargs="+",
        metavar="ROM_NAME",
        help="Batch compare multiple ROMs (e.g., --batch stripes hello mode3)"
    )

    parser.add_argument(
        "--golden-dir", "-g",
        type=Path,
        default=Path("scripts/screenshot/golden"),
        help="Directory containing golden screenshots"
    )
    parser.add_argument(
        "--transpiled-dir", "-t",
        type=Path,
        default=Path("/tmp"),
        help="Directory containing transpiled screenshots"
    )
    parser.add_argument(
        "--resize-golden",
        action="store_true",
        help="Resize golden image to match transpiled dimensions"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=30,
        help="Pixel difference threshold for pass/fail (default: 30)"
    )
    parser.add_argument(
        "--output-diff",
        type=Path,
        help="Output directory for visual diff images"
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Output JSON report file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    output_dir = None
    if args.output_diff:
        output_dir = Path(args.output_diff)
        output_dir.mkdir(parents=True, exist_ok=True)

    if args.single:
        golden_path = Path(args.single[0])
        transpiled_path = Path(args.single[1])

        result = compare_single(
            golden_path,
            transpiled_path,
            resize_golden=args.resize_golden,
            threshold=args.threshold,
            output_diff=output_dir / "diff.png" if output_dir else None
        )

        print("\n" + "=" * 50)
        print("COMPARISON RESULTS")
        print("=" * 50)

        if result.get("error"):
            print(f"ERROR: {result['error']}")
            sys.exit(1)

        print(f"Golden:      {result['golden']}")
        print(f"Transpiled:  {result['transpiled']}")
        print(f"Total pixels: {result['total_pixels']}")
        print(f"Different pixels: {result['diff_pixels']}")
        print(f"Difference:  {result['diff_percentage']}%")
        print(f"Max diff:    {result['max_diff']}")
        print(f"Mean diff:   {result['mean_diff']}")
        print(f"Golden content:      {result.get('golden_content_pct', 'N/A')}%")
        print(f"Transpiled content:  {result.get('transpiled_content_pct', 'N/A')}%")

        status = result.get("status", "fail")
        if status == "inconclusive":
            print(f"Status:      INCONCLUSIVE")
            print(f"Reason:      {result.get('inconclusive_reason', 'unknown')}")
        else:
            print(f"Status:      {'PASS' if result['pass'] else 'FAIL'}")

        sys.exit(0 if result.get('pass') else 1)

    elif args.batch:
        roms = []
        for rom_name in args.batch:
            golden_path = args.golden_dir / f"{rom_name}_golden.png"
            transpiled_path = args.transpiled_dir / f"{rom_name}.png"

            if not golden_path.exists():
                print(f"Warning: Golden screenshot not found: {golden_path}")
                continue
            if not transpiled_path.exists():
                print(f"Warning: Transpiled screenshot not found: {transpiled_path}")
                continue

            roms.append((golden_path, transpiled_path))

        if not roms:
            print("Error: No valid ROM pairs found")
            sys.exit(1)

        results = compare_multiple(
            roms,
            resize_golden=args.resize_golden,
            threshold=args.threshold,
            output_dir=output_dir
        )

        print("\n" + "=" * 60)
        print("BATCH COMPARISON SUMMARY")
        print("=" * 60)

        summary = results["summary"]
        print(f"Total ROMs:    {summary['total']}")
        print(f"Passed:        {summary['passed']}")
        print(f"Failed:        {summary['failed']}")
        print(f"Inconclusive:  {summary['inconclusive']}")
        print(f"Errors:        {summary['errors']}")

        print("\nPer-ROM Results:")
        print("-" * 60)
        for rom in results["roms"]:
            status = rom.get("status", "fail").upper()
            diff_pct = rom.get("diff_percentage", "N/A")
            print(f"  {rom['name']:20s} {diff_pct:>6}%  {status}")

        if args.output_json:
            with open(args.output_json, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nJSON report saved to: {args.output_json}")

        sys.exit(0 if summary['failed'] == 0 and summary['errors'] == 0 else 1)


if __name__ == "__main__":
    main()
