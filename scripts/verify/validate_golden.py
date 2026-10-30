#!/usr/bin/env python3
"""Validate that a golden screenshot is not an mGBA segfault artifact.

mGBA in offscreen mode can produce tiny PNG files (33B, 507B) that are
segfault artifacts, not real reference images. Comparing transpiled output
against these produces meaningless diffs.

Usage:
    python3 scripts/verify/validate_golden.py <golden.png> [<rom_name>]
    python3 scripts/verify/validate_golden.py --batch <dir>

Exit codes:
    0 — all goldens valid
    1 — one or more goldens invalid (segfault artifact)
    2 — usage error
"""

import argparse
import os
import sys
from pathlib import Path

# Threshold: goldens < 200 bytes are considered segfault artifacts
GOLDEN_SIZE_THRESHOLD = 200


def validate_golden(path: str) -> tuple[bool, str]:
    """Validate a single golden screenshot.
    
    Args:
        path: Path to the golden PNG file
        
    Returns:
        Tuple of (is_valid, message)
        
    Validation logic:
        - File must exist
        - File size must be >= 200 bytes
        - Files < 200 bytes are considered mGBA segfault artifacts
    """
    filepath = Path(path)
    
    if not filepath.exists():
        return (False, f"MISSING: {path} not found")
    
    size = filepath.stat().st_size
    
    if size < GOLDEN_SIZE_THRESHOLD:
        return (
            False,
            f"INVALID: {path} is {size}B — segfault artifact (<{GOLDEN_SIZE_THRESHOLD}B threshold)"
        )
    
    return (True, f"VALID: {path} is {size}B")


def validate_batch(dir_path: str) -> tuple[int, int, list[tuple[str, bool, str]]]:
    """Validate all PNG files in a directory.
    
    Args:
        dir_path: Path to directory containing golden screenshots
        
    Returns:
        Tuple of (valid_count, invalid_count, results_list)
        where results_list contains (path, is_valid, message) tuples
    """
    dirpath = Path(dir_path)
    
    if not dirpath.exists():
        print(f"ERROR: Directory not found: {dir_path}", file=sys.stderr)
        sys.exit(2)
    
    if not dirpath.is_dir():
        print(f"ERROR: Not a directory: {dir_path}", file=sys.stderr)
        sys.exit(2)
    
    png_files = sorted(dirpath.glob("*.png"))
    
    if not png_files:
        print(f"Warning: No PNG files found in {dir_path}", file=sys.stderr)
        return (0, 0, [])
    
    results = []
    valid_count = 0
    invalid_count = 0
    
    for png_file in png_files:
        is_valid, message = validate_golden(str(png_file))
        results.append((str(png_file), is_valid, message))
        
        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1
    
    return (valid_count, invalid_count, results)


def main():
    parser = argparse.ArgumentParser(
        description="Validate that golden screenshots are not mGBA segfault artifacts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a single golden file
  python3 scripts/verify/validate_golden.py test-reports/goldens/hello.png

  # Validate a single file with ROM name for context
  python3 scripts/verify/validate_golden.py test-reports/goldens/hello.png hello

  # Validate all goldens in a directory
  python3 scripts/verify/validate_golden.py --batch test-reports/goldens/

Exit codes:
  0 — all goldens valid
  1 — one or more goldens invalid (segfault artifact)
  2 — usage error (missing file, invalid directory, bad arguments)
"""
    )
    
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to golden PNG file to validate"
    )
    
    parser.add_argument(
        "rom_name",
        nargs="?",
        help="ROM name (optional, for context in output)"
    )
    
    parser.add_argument(
        "--batch",
        metavar="DIR",
        help="Validate all PNG files in directory"
    )
    
    args = parser.parse_args()
    
    # Batch mode
    if args.batch:
        valid_count, invalid_count, results = validate_batch(args.batch)
        
        print(f"=== Golden Validation Summary ===")
        print(f"Directory: {args.batch}")
        print(f"Total PNGs: {valid_count + invalid_count}")
        print(f"Valid:      {valid_count}")
        print(f"Invalid:    {invalid_count}")
        print()
        
        # Show invalid goldens first
        invalid_results = [r for r in results if not r[1]]
        if invalid_results:
            print("INVALID GOLDENS:")
            for path, is_valid, message in invalid_results:
                print(f"  ✗ {message}")
            print()
        
        # Show valid goldens
        valid_results = [r for r in results if r[1]]
        if valid_results:
            print("VALID GOLDENS:")
            for path, is_valid, message in valid_results:
                print(f"  ✓ {message}")
            print()
        
        # Exit code: 1 if any invalid, 0 if all valid
        sys.exit(1 if invalid_count > 0 else 0)
    
    # Single file mode
    if not args.path:
        parser.error("Expected at least one argument: path to golden file, or use --batch")
    
    is_valid, message = validate_golden(args.path)
    
    # Print message to stdout
    print(message)
    
    # Add ROM name context if provided
    if args.rom_name and not is_valid:
        print(f"ROM: {args.rom_name}", file=sys.stderr)
    
    # Exit code: 0 if valid, 1 if invalid
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
