#!/usr/bin/env python3
"""
Backfill pass_status field in test-roms-config.toml for all 76 ROMs.

This script adds pass_status = "pass" | "fail" | "new" to each [[tests]] block
based on a hardcoded status map. It preserves all existing formatting, comments,
and blank lines.

Usage:
    python3 scripts/backfill_pass_status.py
"""

import re
import os

# Hardcoded status map - ground truth from docs/reference/test-roms.md
# 5 FAIL ROMs
FAIL_ROMS = {
    "line_timing",
    "cascade7",
    "fantasy-knight",
    "Skyland",
    "blindjump_BlindJump",
}

# 2 NEW ROMs (only these two, per task spec)
NEW_ROMS = {
    "gbarcade_gbarcade_v0.1.4",
    "bpcore_BPCoreEngine",
}

# All other ROMs are PASS
DEFAULT_STATUS = "pass"


def get_status(rom_name):
    """Get pass_status for a ROM name."""
    if rom_name in FAIL_ROMS:
        return "fail"
    elif rom_name in NEW_ROMS:
        return "new"
    else:
        return DEFAULT_STATUS


def backfill_pass_status(toml_path):
    """
    Read TOML file, add pass_status to each [[tests]] block if missing,
    and write back. Returns summary dict.
    """
    with open(toml_path, "r") as f:
        content = f.read()

    # Track counts
    counts = {"pass": 0, "fail": 0, "new": 0, "updated": 0, "unchanged": 0}

    # Split into lines for processing
    lines = content.split("\n")
    result_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if this is a [[tests]] block start
        if line.strip() == "[[tests]]":
            # Collect all lines in this block until next [[tests]] or EOF
            block_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip() != "[[tests]]":
                block_lines.append(lines[i])
                i += 1

            # Parse the block to find the name and check for existing pass_status
            block_text = "\n".join(block_lines)
            name_match = re.search(r'name\s*=\s*"([^"]+)"', block_text)
            has_pass_status = "pass_status" in block_text

            if name_match:
                rom_name = name_match.group(1)
                desired_status = get_status(rom_name)

                if has_pass_status:
                    # Check if it matches desired status
                    existing_match = re.search(
                        r'pass_status\s*=\s*"([^"]+)"', block_text
                    )
                    if existing_match:
                        existing_status = existing_match.group(1)
                        if existing_status == desired_status:
                            counts["unchanged"] += 1
                            counts[desired_status] += 1
                        else:
                            # Update to correct status
                            block_text = re.sub(
                                r'pass_status\s*=\s*"[^"]+"',
                                f'pass_status = "{desired_status}"',
                                block_text,
                            )
                            counts["updated"] += 1
                            counts[desired_status] += 1
                    else:
                        # Add pass_status after test_type line
                        block_text = re.sub(
                            r'(test_type\s*=\s*"[^"]+")',
                            rf'\1\npass_status = "{desired_status}"',
                            block_text,
                        )
                        counts["updated"] += 1
                        counts[desired_status] += 1
                else:
                    # Add pass_status after test_type line
                    block_text = re.sub(
                        r'(test_type\s*=\s*"[^"]+")',
                        rf'\1\npass_status = "{desired_status}"',
                        block_text,
                    )
                    counts["updated"] += 1
                    counts[desired_status] += 1
            else:
                counts["unchanged"] += 1

            # Add processed block to result
            result_lines.extend(block_text.split("\n"))
        else:
            result_lines.append(line)
            i += 1

    # Write back
    new_content = "\n".join(result_lines)
    with open(toml_path, "w") as f:
        f.write(new_content)

    return counts


def main():
    # Determine path relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    toml_path = os.path.join(project_root, "test-roms-config.toml")

    if not os.path.exists(toml_path):
        print(f"Error: {toml_path} not found")
        return 1

    print(f"Processing {toml_path}...")
    counts = backfill_pass_status(toml_path)

    total = counts["pass"] + counts["fail"] + counts["new"]
    print(f"\nSummary:")
    print(f"  Total ROMs with pass_status: {total}")
    print(f"  PASS: {counts['pass']}")
    print(f"  FAIL: {counts['fail']}")
    print(f"  NEW:  {counts['new']}")
    print(f"  Updated: {counts['updated']} entries")
    print(f"  Unchanged: {counts['unchanged']} entries")

    if total != 76:
        print(f"\nWarning: Expected 76 ROMs, found {total}")
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    exit(main())