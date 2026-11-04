"""Regression test for CFG explosion bug.

The CFG builder used to follow linear data walks, producing 50K+ reachable
addresses and causing transpilation to hang for minutes. This test verifies
that the fall-through budget and consecutive invalid instruction limits
prevent this regression.

See: docs/how-debug.md, crates/gbatopy-cli/src/pipeline_cmd.rs (CFG builder)
"""

import subprocess
import time
import os
import pytest
from pathlib import Path

# Test configuration
ROMS = ["combo.gba", "hyperspace-roll.gba", "the-purple-night.gba"]
ROM_DIR = Path("test_roms/roms")
OUTPUT_DIR = Path("/tmp")
MAX_TRANSPILE_SECONDS = 60
MAX_FUNCTION_COUNT = 50000  # CFG explosion would produce 50K+ functions

# Binary path (check both release and debug)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GBATOPY_BIN = PROJECT_ROOT / "target" / "release" / "gbatopy-cli"
if not GBATOPY_BIN.exists():
    GBATOPY_BIN = PROJECT_ROOT / "target" / "debug" / "gbatopy-cli"


def count_functions(py_file: Path) -> int:
    """Count the number of generated functions in the transpiled output."""
    with open(py_file, 'r') as f:
        content = f.read()
    # Count function definitions - the codegen emits func_NNNNN patterns
    return content.count("def func_")


def transpile_rom(rom_path: Path, output_path: Path, timeout: int) -> tuple[bool, float, str]:
    """Transpile a ROM and return (success, elapsed_time, error_message)."""
    start = time.time()
    try:
        result = subprocess.run(
            [str(GBATOPY_BIN), "pipeline", "--rom", str(rom_path), "--output", str(output_path)],
            capture_output=True,
            timeout=timeout
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            return True, elapsed, ""
        else:
            return False, elapsed, result.stderr.decode()
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - start
        return False, elapsed, f"Timeout after {timeout}s"
    except Exception as e:
        elapsed = time.time() - start
        return False, elapsed, str(e)


def verify_python_syntax(output_path: Path) -> tuple[bool, str]:
    """Verify the transpiled output is valid Python."""
    result = subprocess.run(
        ["python3", "-m", "py_compile", str(output_path)],
        capture_output=True
    )
    if result.returncode == 0:
        return True, ""
    else:
        return False, result.stderr.decode()


@pytest.mark.parametrize("rom_name", ROMS)
def test_cfg_does_not_explode(rom_name: pytest.FixtureRequest):
    """Test that CFG builder doesn't explode on complex ROMs.

    Verifies:
    a. Transpilation completes successfully (no hang, no crash)
    b. Transpilation completes in reasonable time (< 60 seconds)
    c. The transpiled output is valid Python
    d. The output has a reasonable number of functions (< 50K)
    """
    rom_path = PROJECT_ROOT / ROM_DIR / rom_name

    # Skip if ROM doesn't exist (don't fail the test suite for missing ROMs)
    if not rom_path.exists():
        pytest.skip(f"ROM not found: {rom_path}")

    output_path = OUTPUT_DIR / rom_name.replace(".gba", ".py")

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Run transpilation with timeout
    success, elapsed, error_msg = transpile_rom(rom_path, output_path, MAX_TRANSPILE_SECONDS + 30)

    # Assertion 1: Transpilation must succeed
    assert success, f"Transpilation failed for {rom_name}: {error_msg}"

    # Assertion 2: Transpilation must complete in reasonable time
    assert elapsed < MAX_TRANSPILE_SECONDS, (
        f"Transpilation took {elapsed:.1f}s for {rom_name} "
        f"(max allowed: {MAX_TRANSPILE_SECONDS}s) - CFG may be exploding"
    )

    # Assertion 3: Output must be valid Python
    syntax_valid, syntax_error = verify_python_syntax(output_path)
    assert syntax_valid, f"Output is not valid Python for {rom_name}: {syntax_error}"

    # Assertion 4: Function count must be reasonable (CFG explosion check)
    func_count = count_functions(output_path)
    assert func_count < MAX_FUNCTION_COUNT, (
        f"Too many functions ({func_count:,}) in {rom_name} - "
        f"CFG may have exploded (max allowed: {MAX_FUNCTION_COUNT:,})"
    )

    # Print summary for visibility
    print(f"\n{rom_name}: PASS (transpile_time={elapsed:.2f}s, functions={func_count:,})")


def test_cfg_budget_is_configured():
    """Verify the CFG fall-through budget is set in the codebase.

    This is a sanity check that the fix is actually in place.
    """
    pipeline_file = PROJECT_ROOT / "crates" / "gbatopy-cli" / "src" / "pipeline_cmd.rs"

    if not pipeline_file.exists():
        pytest.skip("pipeline_cmd.rs not found")

    content = pipeline_file.read_text()

    # Check for the fall-through budget constant
    assert "ESTIMATED_LINES_PER_INSTRUCTION" in content, (
        "ESTIMATED_LINES_PER_INSTRUCTION not found - CFG budget may not be configured"
    )

    # Verify it's set to a reasonable value (not too large)
    import re
    match = re.search(r'ESTIMATED_LINES_PER_INSTRUCTION\s*=\s*(\d+)', content)
    if match:
        value = int(match.group(1))
        # The budget should be reasonable (not 100000+ which would allow explosion)
        assert value < 100000, (
            f"ESTIMATED_LINES_PER_INSTRUCTION={value} is too large - "
            "may allow CFG explosion"
        )
