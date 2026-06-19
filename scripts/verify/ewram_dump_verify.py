#!/usr/bin/env python3
"""
EWRAM Dump Verification Script

Compares EWRAM dumps from GBAtoPy vs reference (mGBA or FuzzARM) to ensure memory correctness.

Usage:
    python3 ewram_dump_verify.py --gbatopy /tmp/mem_gbatopy.bin --reference /tmp/mem_ref.bin
    python3 ewram_dump_verify.py --gbatopy /tmp/mem_gbatopy.bin --pattern test_pattern
"""

import argparse
import sys
from pathlib import Path
from typing import Optional


def load_binary_dump(filepath: str) -> bytes:
    """Load binary memory dump from file."""
    with open(filepath, 'rb') as f:
        return f.read()


def compare_dumps(
    gbatopy_dump: bytes,
    reference_dump: bytes,
    region_name: str = "EWRAM"
) -> dict:
    """
    Compare two binary dumps byte-by-byte.

    Returns:
        dict with comparison results including:
        - match: bool (True if identical)
        - total_bytes: int
        - diff_count: int
        - differences: list of (address, gbatopy_val, reference_val)
    """
    results = {
        "match": False,
        "total_bytes": max(len(gbatopy_dump), len(reference_dump)),
        "diff_count": 0,
        "differences": [],
        "gbatopy_size": len(gbatopy_dump),
        "reference_size": len(reference_dump),
    }

    # Check size mismatch
    if len(gbatopy_dump) != len(reference_dump):
        results["differences"].append({
            "type": "size_mismatch",
            "gbatopy_size": len(gbatopy_dump),
            "reference_size": len(reference_dump),
            "message": f"Size mismatch: GBAtoPy={len(gbatopy_dump)} bytes, Reference={len(reference_dump)} bytes"
        })

    # Compare byte-by-byte
    min_len = min(len(gbatopy_dump), len(reference_dump))
    for i in range(min_len):
        if gbatopy_dump[i] != reference_dump[i]:
            results["diff_count"] += 1
            if len(results["differences"]) < 100:  # Limit to first 100 differences
                results["differences"].append({
                    "type": "byte_diff",
                    "address": f"0x02000000 + {i:#06x}",
                    "offset": i,
                    "gbatopy_val": f"0x{gbatopy_dump[i]:02X}",
                    "reference_val": f"0x{reference_dump[i]:02X}",
                })

    # Determine match status
    results["match"] = (
        results["diff_count"] == 0 and
        len(gbatopy_dump) == len(reference_dump)
    )

    # Add summary
    if results["match"]:
        results["summary"] = f"✓ {region_name} dumps match perfectly ({min_len} bytes)"
    else:
        diff_pct = (results["diff_count"] / min_len * 100) if min_len > 0 else 0
        results["summary"] = (
            f"✗ {region_name} dumps differ: {results['diff_count']} bytes different "
            f"({diff_pct:.2f}%) out of {min_len} bytes"
        )

    return results


def print_comparison_report(results: dict, region_name: str = "EWRAM"):
    """Print formatted comparison report to stdout."""
    print(f"\n{'='*60}")
    print(f"{region_name} Memory Comparison Report")
    print(f"{'='*60}")
    print(f"\n{results['summary']}")
    print(f"\nSize Information:")
    print(f"  GBAtoPy dump:    {results['gbatopy_size']} bytes")
    print(f"  Reference dump:  {results['reference_size']} bytes")
    print(f"  Compared:        {results['total_bytes']} bytes")

    if not results["match"]:
        print(f"\nDifferences Found: {results['diff_count']} bytes")

        if any(d.get("type") == "size_mismatch" for d in results["differences"]):
            print(f"\n⚠ SIZE MISMATCH:")
            for diff in results["differences"]:
                if diff.get("type") == "size_mismatch":
                    print(f"  {diff['message']}")

        # Show first 20 byte differences
        byte_diffs = [d for d in results["differences"] if d.get("type") == "byte_diff"]
        if byte_diffs:
            print(f"\nFirst 20 byte differences:")
            print(f"{'Offset':<15} {'GBAtoPy':<12} {'Reference':<12} {'Address':<20}")
            print(f"{'-'*60}")
            for diff in byte_diffs[:20]:
                print(f"{diff['offset']:<15} {diff['gbatopy_val']:<12} {diff['reference_val']:<12} {diff['address']:<20}")

        if len(byte_diffs) > 20:
            print(f"\n... and {len(byte_diffs) - 20} more differences (not shown)")

    print(f"\n{'='*60}\n")


def generate_pattern_test_rom():
    """
    Generate a simple test ROM that writes known patterns to EWRAM.
    Returns the ROM as bytes.
    """
    # This is a minimal ARM assembly ROM that writes patterns to EWRAM
    # Assembled with: arm-none-eabi-as -mcpu=arm7tdmi test.s -o test.o
    #                arm-none-eabi-ld -Ttext=0x08000000 test.o -o test.elf
    #                arm-none-eabi-objcopy -O binary test.elf test.gba

    # For now, we'll create a simple pattern verification without needing to compile
    # The test ROM writes:
    # - 0x00-0xFF pattern at 0x02000000
    # - 0xFF-0x00 pattern at 0x02000100
    # - 0xAA at 0x02000200
    # - 0x55 at 0x02000204

    print("Pattern test ROM expected EWRAM layout:")
    print("  0x02000000-0x020000FF: 0x00, 0x01, 0x02, ..., 0xFF (ascending)")
    print("  0x02000100-0x020001FF: 0xFF, 0xFE, 0xFD, ..., 0x00 (descending)")
    print("  0x02000200: 0xAA")
    print("  0x02000204: 0x55")
    print()


def verify_pattern_dump(dump: bytes, region_name: str = "EWRAM") -> dict:
    """
    Verify that a dump contains expected test patterns.

    Expected patterns:
    - Ascending 0x00-0xFF at offset 0x000
    - Descending 0xFF-0x00 at offset 0x100
    - 0xAA at offset 0x200
    - 0x55 at offset 0x204
    """
    results = {
        "valid": True,
        "checks": [],
    }

    if len(dump) < 0x210:
        results["valid"] = False
        results["checks"].append({
            "name": "size",
            "passed": False,
            "message": f"Dump too small: {len(dump)} bytes (need at least 0x210)"
        })
        return results

    # Check ascending pattern (0x00-0xFF)
    ascending_ok = True
    for i in range(256):
        if dump[i] != i:
            ascending_ok = False
            break
    results["checks"].append({
        "name": "ascending_pattern",
        "passed": ascending_ok,
        "message": "0x00-0xFF ascending pattern at 0x000" if ascending_ok else "FAILED at offset 0x{:03X}".format(
            next(i for i in range(256) if dump[i] != i)
        )
    })

    # Check descending pattern (0xFF-0x00)
    descending_ok = True
    for i in range(256):
        if dump[0x100 + i] != 0xFF - i:
            descending_ok = False
            break
    results["checks"].append({
        "name": "descending_pattern",
        "passed": descending_ok,
        "message": "0xFF-0x00 descending pattern at 0x100" if descending_ok else "FAILED"
    })

    # Check 0xAA at 0x200
    aa_ok = dump[0x200] == 0xAA
    results["checks"].append({
        "name": "0xAA_marker",
        "passed": aa_ok,
        "message": "0xAA at 0x200" if aa_ok else f"Got 0x{dump[0x200]:02X}"
    })

    # Check 0x55 at 0x204
    fivefive_ok = dump[0x204] == 0x55
    results["checks"].append({
        "name": "0x55_marker",
        "passed": fivefive_ok,
        "message": "0x55 at 0x204" if fivefive_ok else f"Got 0x{dump[0x204]:02X}"
    })

    results["valid"] = all(c["passed"] for c in results["checks"])

    return results


def print_pattern_report(results: dict):
    """Print pattern verification report."""
    print(f"\n{'='*60}")
    print("Pattern Verification Report")
    print(f"{'='*60}\n")

    for check in results["checks"]:
        status = "✓" if check["passed"] else "✗"
        print(f"  {status} {check['name']}: {check['message']}")

    print()
    if results["valid"]:
        print("✓ All pattern checks passed!")
    else:
        print("✗ Some pattern checks failed")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="EWRAM Dump Verification - Compare GBAtoPy vs reference dumps"
    )

    # Comparison mode
    parser.add_argument(
        "--gbatopy", "-g",
        type=str,
        help="Path to GBAtoPy EWRAM dump (binary)"
    )
    parser.add_argument(
        "--reference", "-r",
        type=str,
        help="Path to reference EWRAM dump (binary from mGBA/FuzzARM)"
    )

    # Pattern verification mode
    parser.add_argument(
        "--pattern", "-p",
        type=str,
        help="Verify dump against known test pattern (path to dump file)"
    )

    # Output options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show all differences (not just first 100)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.pattern and not (args.gbatopy and args.reference):
        parser.error(
            "Must specify either --pattern <dump> OR --gbatopy <dump> --reference <dump>"
        )

    # Pattern verification mode
    if args.pattern:
        print(f"Loading dump: {args.pattern}")
        dump = load_binary_dump(args.pattern)
        print(f"Dump size: {len(dump)} bytes")

        generate_pattern_test_rom()

        results = verify_pattern_dump(dump)
        print_pattern_report(results)

        if args.json:
            import json
            print(json.dumps(results, indent=2))

        sys.exit(0 if results["valid"] else 1)

    # Comparison mode
    print(f"Loading GBAtoPy dump: {args.gbatopy}")
    gbatopy_dump = load_binary_dump(args.gbatopy)
    print(f"  Size: {len(gbatopy_dump)} bytes")

    print(f"Loading reference dump: {args.reference}")
    reference_dump = load_binary_dump(args.reference)
    print(f"  Size: {len(reference_dump)} bytes")

    results = compare_dumps(gbatopy_dump, reference_dump)

    if args.json:
        import json
        print(json.dumps(results, indent=2))
    else:
        print_comparison_report(results)

    sys.exit(0 if results["match"] else 1)


if __name__ == "__main__":
    main()
