"""SWI number-to-label mapping validation test for GBAtoPy.

This test validates that SWI handlers across all three dispatch tables
(cpu.py, arm7tdmi.py, game_loop.py template) have consistent and correct
mappings according to the GBATEK GBA BIOS specification.

GBATEK SWI Reference:
- 0x00: SoftReset
- 0x01: RegRamReset
- 0x02: Halt
- 0x03: Stop
- 0x04: IntrWait
- 0x05: VBlankIntrWait
- 0x06: Div
- 0x07: DivArm
- 0x08: Sqrt
- 0x09: ArcTan
- 0x0A: ArcTan2
- 0x0B: CpuSet
- 0x0C: CpuFastSet
- 0x0D: GetBiosChecksum
- 0x0E: BgAffineSet
- 0x0F: ObjAffineSet
- 0x10: DriverTestWait (BitUnPack)
- 0x11: DriverTestSkip (LZ77UnCompWram)
- 0x12: DriverTestControl (LZ77UnCompVram)
- 0x13: SqrtArm (HuffmanUnComp)
- 0x14: ConvToFloat (RLUnCompWram)
- 0x15: SoundBiasChange (RLUnCompVram)
- 0x16: HardReset (Diff8bitUnFilterWram)
- 0x17: SoundDriverInit (Diff8bitUnFilterVram)
- 0x18: SoundDriverMode (Diff16bitUnFilter)
- 0x19: SoundDriverMain
- 0x1A: SoundDriverVSync
- 0x1B: SoundChannelClear
- 0x1C: SoundHardwareIO
- 0x1D: MidiKey2Freq
- 0x1E: SoundVariableSet
- 0x1F: SoundVariableSet
- 0x28: SoundDriverVSyncOff

Note: Some SWI numbers have different names in different documentation sources.
The labels in comments are for human readability; the handler existence is what matters.
"""
import re
from pathlib import Path


# GBATEK SWI mapping (authoritative reference)
# Only include SWIs that are actually implemented in the codebase
SWI_REFERENCE = {
    0x00: "SoftReset",
    0x01: "RegRamReset",
    0x02: "Halt",
    0x03: "Stop",
    0x04: "IntrWait",
    0x05: "VBlankIntrWait",
    0x06: "Div",
    0x07: "DivArm",
    0x08: "Sqrt",
    0x09: "ArcTan",
    0x0A: "ArcTan2",
    0x0B: "CpuSet",
    0x0C: "CpuFastSet",
    # 0x0D: GetBiosChecksum - NOT IMPLEMENTED
    0x0E: "BgAffineSet",
    0x0F: "ObjAffineSet",
    0x10: "BitUnPack",  # Also known as DriverTestWait
    0x11: "LZ77UnCompWram",  # Also known as DriverTestSkip
    0x12: "LZ77UnCompVram",  # Also known as DriverTestControl
    0x13: "HuffmanUnComp",  # Also known as SqrtArm
    0x14: "RLUnCompWram",  # Also known as ConvToFloat
    0x15: "RLUnCompVram",  # Also known as SoundBiasChange
    0x16: "Diff8bitUnFilterWram",  # Also known as HardReset
    0x17: "Diff8bitUnFilterVram",  # Also known as SoundDriverInit
    0x18: "Diff16bitUnFilter",  # Also known as SoundDriverMode
    0x19: "SoundDriverMain",
    0x1A: "SoundDriverVSync",
    0x1B: "SoundChannelClear",
    0x1C: "SoundHardwareIO",  # Also known as SoundDriverVSync in some docs
    0x1D: "MidiKey2Freq",
    0x1E: "SoundVariableSet",  # Also known as SoundDriverInit in some docs
    0x1F: "SoundVariableSet",  # BUG: was mislabeled as SoundDriverVSyncOff
    0x28: "SoundDriverVSyncOff",
}

# Critical SWIs that MUST have correct labels (no aliasing allowed)
CRITICAL_SWI_MAPPINGS = {
    0x1F: "SoundVariableSet",  # Must NOT be SoundDriverVSyncOff
    0x28: "SoundDriverVSyncOff",  # Must NOT be SoundVariableSet
}

# Files to check (relative to project root)
FILES_TO_CHECK = [
    "../cpu.py",
    "../arm7tdmi.py",
    "../../templates/game_loop.py",
]


def extract_swi_handlers(file_path: Path) -> dict[int, tuple[str, int]]:
    """Extract SWI number → (label, line_number) mapping from a file.
    
    Returns a dict mapping SWI number to (comment_label, line_number).
    """
    handlers = {}
    content = file_path.read_text()
    
    # Pattern for SWI handler: "elif num == 0xNN:" or "if num == 0xNN:"
    # followed by a comment "# LabelName"
    # Handles both "swi_num" and "num" variable names
    pattern = r'(?:elif|if)\s+(?:swi_num|num)\s*==\s*0x([0-9A-Fa-f]{2})\s*:\s*#\s*(\w+)'
    
    for match in re.finditer(pattern, content):
        swi_num = int(match.group(1), 16)
        label = match.group(2)
        # Find line number
        line_num = content[:match.start()].count('\n') + 1
        handlers[swi_num] = (label, line_num)
    
    return handlers


def test_swi_mapping_consistency():
    """Validate SWI number→label mapping across all dispatch tables.
    
    Tests:
    1. All three files have handlers for the same SWI numbers
    2. Critical SWIs (0x1F, 0x28) have correct labels
    3. No mismatches in SWI number→label mapping
    """
    # Test file is at: crates/gbatopy-cli/assets/gba_runtime/tests/test_swi_mapping.py
    # Files to check are at:
    #   crates/gbatopy-cli/assets/gba_runtime/cpu.py (2 levels up)
    #   crates/gbatopy-cli/assets/gba_runtime/arm7tdmi.py (2 levels up)
    #   crates/gbatopy-cli/assets/templates/game_loop.py (3 levels up + templates)
    base_path = Path(__file__).parent.parent.parent.parent
    errors = []
    
    # Extract handlers from all files
    all_handlers = {}
    for rel_path in FILES_TO_CHECK:
        file_path = Path(__file__).parent / rel_path
        if not file_path.exists():
            errors.append(f"File not found: {file_path}")
            continue
        
        handlers = extract_swi_handlers(file_path)
        all_handlers[rel_path] = handlers
    
    if errors:
        raise AssertionError("\n".join(errors))
    
    # Check 1: All files have handlers for the same SWI numbers
    all_swi_nums = set(SWI_REFERENCE.keys())
    for rel_path, handlers in all_handlers.items():
        found_nums = set(handlers.keys())
        missing = all_swi_nums - found_nums
        if missing:
            errors.append(
                f"{rel_path}: Missing handlers for SWIs: "
                f"{', '.join(f'0x{num:02X}' for num in sorted(missing))}"
            )
    
    # Check 2: Critical SWIs have correct labels
    for rel_path, handlers in all_handlers.items():
        for swi_num, expected_label in CRITICAL_SWI_MAPPINGS.items():
            if swi_num not in handlers:
                errors.append(
                    f"{rel_path}: Critical SWI 0x{swi_num:02X} ({expected_label}) not found"
                )
                continue
            
            actual_label, line_num = handlers[swi_num]
            if actual_label != expected_label:
                errors.append(
                    f"{rel_path}:{line_num}: SWI 0x{swi_num:02X} labeled as '{actual_label}', "
                    f"expected '{expected_label}'"
                )
    
    # Check 3: Cross-file consistency (all files should agree on labels)
    file_paths = list(all_handlers.keys())
    if len(file_paths) >= 2:
        reference_file = file_paths[0]
        reference_handlers = all_handlers[reference_file]
        
        for other_file in file_paths[1:]:
            other_handlers = all_handlers[other_file]
            for swi_num in reference_handlers:
                if swi_num not in other_handlers:
                    continue  # Already caught in Check 1
                
                ref_label, _ = reference_handlers[swi_num]
                other_label, other_line = other_handlers[swi_num]
                
                if ref_label != other_label:
                    errors.append(
                        f"Inconsistency: {reference_file} has SWI 0x{swi_num:02X} as '{ref_label}', "
                        f"but {other_file}:{other_line} has '{other_label}'"
                    )
    
    if errors:
        raise AssertionError("\n".join([
            "SWI mapping validation failed:",
            "-" * 60,
            "\n".join(errors),
            "-" * 60,
            "Reference: GBATEK GBA BIOS SWI documentation",
        ]))
    
    print("✓ All SWI mappings are consistent across dispatch tables")
    print(f"  Checked {len(all_handlers)} files")
    print(f"  Validated {len(CRITICAL_SWI_MAPPINGS)} critical SWIs")
    print(f"  Total SWI handlers: {len(SWI_REFERENCE)}")


def test_swi_0x1f_not_sound_driver_vsync_off():
    """Specific test for the bug: SWI 0x1F should NOT be labeled SoundDriverVSyncOff.
    
    This was a known bug where SWI 0x1F (SoundVariableSet) was mislabeled as
    SoundDriverVSyncOff, which is actually SWI 0x28.
    """
    base_path = Path(__file__).parent.parent.parent.parent
    
    for rel_path in FILES_TO_CHECK:
        file_path = Path(__file__).parent / rel_path
        if not file_path.exists():
            continue
        
        handlers = extract_swi_handlers(file_path)
        
        if 0x1F not in handlers:
            raise AssertionError(
                f"{rel_path}: SWI 0x1F handler not found (required by GBATEK)"
            )
        
        label, line_num = handlers[0x1F]
        
        if label == "SoundDriverVSyncOff":
            raise AssertionError(
                f"{rel_path}:{line_num}: BUG DETECTED - SWI 0x1F labeled as 'SoundDriverVSyncOff'\n"
                f"  This is incorrect. SWI 0x1F = SoundVariableSet\n"
                f"  SoundDriverVSyncOff is SWI 0x28"
            )
        
        if label != "SoundVariableSet":
            # Allow other valid labels (aliasing exists in docs)
            print(
                f"  Warning: {rel_path}:{line_num} - SWI 0x1F labeled as '{label}' "
                f"(expected 'SoundVariableSet')"
            )
    
    print("✓ SWI 0x1F is correctly NOT labeled as SoundDriverVSyncOff")


def test_swi_0x28_sound_driver_vsync_off():
    """Specific test: SWI 0x28 should be labeled SoundDriverVSyncOff."""
    base_path = Path(__file__).parent.parent.parent.parent
    
    for rel_path in FILES_TO_CHECK:
        file_path = Path(__file__).parent / rel_path
        if not file_path.exists():
            continue
        
        handlers = extract_swi_handlers(file_path)
        
        if 0x28 not in handlers:
            raise AssertionError(
                f"{rel_path}: SWI 0x28 handler not found (required by GBATEK)"
            )
        
        label, line_num = handlers[0x28]
        
        if label != "SoundDriverVSyncOff":
            raise AssertionError(
                f"{rel_path}:{line_num}: SWI 0x28 labeled as '{label}', expected 'SoundDriverVSyncOff'"
            )
    
    print("✓ SWI 0x28 is correctly labeled as SoundDriverVSyncOff")


if __name__ == "__main__":
    import sys
    
    print("Running SWI mapping validation tests...")
    print("=" * 60)
    
    try:
        test_swi_mapping_consistency()
        test_swi_0x1f_not_sound_driver_vsync_off()
        test_swi_0x28_sound_driver_vsync_off()
        
        print("=" * 60)
        print("All SWI mapping tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print("=" * 60)
        print(f"FAILED: {e}")
        sys.exit(1)
