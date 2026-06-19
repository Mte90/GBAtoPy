#!/usr/bin/env python3
"""
Golden screenshot comparison for GBAtoPy vs mGBA.

Compares two PNG images pixel-by-pixel, handling different resolutions
by resizing the golden image to match the transpiled image.

Reports:
- Per-ROM pass/fail status (based on threshold)
- Difference percentage
- Max pixel difference
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
    # Convert to RGB if necessary (handle RGBA, palette, etc.)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    return np.array(img)


def resize_to_match(source: np.ndarray, target_shape: tuple) -> np.ndarray:
    """Resize source image to match target dimensions using nearest neighbor."""
    source_img = Image.fromarray(source)
    target_h, target_w = target_shape[:2]
    
    # Use nearest neighbor to preserve exact pixel values
    resized = source_img.resize((target_w, target_h), resample=Image.Resampling.NEAREST)
    
    return np.array(resized)


def calculate_difference(
    golden: np.ndarray,
    transpiled: np.ndarray,
    threshold: int = 30
) -> dict:
    """
    Calculate pixel-by-pixel difference between two images.
    
    Args:
        golden: Golden (mGBA) image array
        transpiled: Transpiled (GBAtoPy) image array
        threshold: Pixel value threshold for considering a pixel "different"
    
    Returns:
        Dict with difference metrics
    """
    # Ensure same shape
    if golden.shape != transpiled.shape:
        raise ValueError(
            f"Image shapes don't match: {golden.shape} vs {transpiled.shape}. "
            "Use --resize-golden to resize golden image first."
        )
    
    # Calculate per-pixel difference
    diff = np.abs(golden.astype(np.int16) - transpiled.astype(np.int16))
    
    # Count pixels where any channel differs by more than threshold
    diff_mask = np.any(diff > threshold, axis=2)
    total_pixels = diff_mask.size
    diff_pixels = np.sum(diff_mask)
    
    # Calculate metrics
    diff_percentage = (diff_pixels / total_pixels) * 100
    max_diff = np.max(diff)
    mean_diff = np.mean(diff)
    
    # Per-channel stats
    diff_r = np.sum(diff[:, :, 0] > threshold)
    diff_g = np.sum(diff[:, :, 1] > threshold)
    diff_b = np.sum(diff[:, :, 2] > threshold)
    
    return {
        "total_pixels": int(total_pixels),
        "diff_pixels": int(diff_pixels),
        "diff_percentage": round(diff_percentage, 2),
        "max_diff": int(max_diff),
        "mean_diff": round(float(mean_diff), 2),
        "pass": diff_percentage < 30,  # Default threshold
        "per_channel": {
            "red_diff": int(diff_r),
            "green_diff": int(diff_g),
            "blue_diff": int(diff_b),
        }
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
    
    # Create diff image: original transpiled with differences highlighted in red
    diff_img = transpiled.copy()
    diff_img[diff_mask] = [255, 0, 0]  # Red for differences
    
    # Also create a side-by-side comparison
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
        
        # Resize golden if requested or if shapes differ
        if resize_golden or golden.shape != transpiled.shape:
            print(f"  Resizing golden from {golden.shape} to {transpiled.shape[:2]}")
            golden = resize_to_match(golden, transpiled.shape)
        
        metrics = calculate_difference(golden, transpiled, threshold)
        result.update(metrics)
        
        # Generate visual diff if requested
        if output_diff:
            generate_visual_diff(golden, transpiled, output_diff, threshold)
        
    except Exception as e:
        result["error"] = str(e)
        result["pass"] = False
    
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
            "errors": 0,
        },
        "roms": []
    }
    
    for i, (golden_path, transpiled_path) in enumerate(roms):
        rom_name = transpiled_path.stem
        
        # Generate output path for visual diff
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
        
        # Update summary
        if result.get("error"):
            results["summary"]["errors"] += 1
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
    
    # Mode selection
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
    
    # Options
    parser.add_argument(
        "--golden-dir", "-g",
        type=Path,
        default=Path("scripts/screenshot/golden"),
        help="Directory containing golden screenshots (default: scripts/screenshot/golden)"
    )
    parser.add_argument(
        "--transpiled-dir", "-t",
        type=Path,
        default=Path("/tmp"),
        help="Directory containing transpiled screenshots (default: /tmp)"
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
    
    # Create output directory if needed
    output_dir = None
    if args.output_diff:
        output_dir = Path(args.output_diff)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.single:
        # Single image comparison
        golden_path = Path(args.single[0])
        transpiled_path = Path(args.single[1])
        
        result = compare_single(
            golden_path,
            transpiled_path,
            resize_golden=args.resize_golden,
            threshold=args.threshold,
            output_diff=output_dir / "diff.png" if output_dir else None
        )
        
        # Print results
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
        print(f"Status:      {'PASS' if result['pass'] else 'FAIL'}")
        
        # Exit code
        sys.exit(0 if result['pass'] else 1)
    
    elif args.batch:
        # Batch comparison
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
        
        # Print summary
        print("\n" + "=" * 60)
        print("BATCH COMPARISON SUMMARY")
        print("=" * 60)
        
        summary = results["summary"]
        print(f"Total ROMs:    {summary['total']}")
        print(f"Passed:        {summary['passed']}")
        print(f"Failed:        {summary['failed']}")
        print(f"Errors:        {summary['errors']}")
        
        print("\nPer-ROM Results:")
        print("-" * 60)
        for rom in results["roms"]:
            status = "PASS" if rom.get("pass") else "FAIL"
            diff_pct = rom.get("diff_percentage", "N/A")
            print(f"  {rom['name']:20s} {diff_pct:>6}%  {status}")
        
        # Save JSON report if requested
        if args.output_json:
            with open(args.output_json, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nJSON report saved to: {args.output_json}")
        
        # Exit code
        sys.exit(0 if summary['failed'] == 0 and summary['errors'] == 0 else 1)


if __name__ == "__main__":
    main()
