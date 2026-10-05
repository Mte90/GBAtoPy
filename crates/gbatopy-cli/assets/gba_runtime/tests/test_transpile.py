"""
Test suite for GBAtoPy transpiler.

Run with: pytest tests/ -v
With coverage: coverage run -m pytest tests/ && coverage report
"""

import subprocess
import tempfile
import os
import pytest
from pathlib import Path


def test_all_roms_transpile():
    """Verify all test ROMs transpile to valid Python."""
    # Use absolute path relative to this test file (6 levels up from tests/ to project root)
    test_file = Path(__file__).resolve()
    project_root = test_file.parent.parent.parent.parent.parent.parent
    roms_dir = project_root / "test_roms" / "roms"
    if not roms_dir.exists():
        pytest.skip("test_roms/roms directory not found at {}".format(roms_dir))
    
    # Use release binary if available, else build release
    release_binary = project_root / "target" / "release" / "gbatopy-cli"
    
    if release_binary.exists():
        use_release = True
    else:
        use_release = False
    
    # Use project-local temp directory instead of /tmp (avoids user quota issues)
    tmp_dir = project_root / "test-reports" / "artifacts" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    
    passed = 0
    failed = 0
    results = []
    per_rom_timeout = 600  # seconds — large ROMs (rates.gba: 3.3M lines) need minutes
    
    for rom in roms_dir.glob("*.gba"):
        # Create temp file in project-local directory
        output_path = tmp_dir / f"{rom.stem}_transpile.py"
        output_path.touch()
        
        try:
            # Build command based on binary availability
            if use_release:
                cmd = [str(release_binary), "pipeline", "--rom", str(rom), "--output", output_path]
            else:
                cmd = ["cargo", "run", "-q", "--release", "-p", "gbatopy-cli", "--",
                       "pipeline", "--rom", str(rom), "--output", output_path]
            
            # Transpile with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=per_rom_timeout
            )
            
            if result.returncode != 0:
                failed += 1
                error_msg = f"✗ {rom.name}: transpile failed"
                if "timeout" in str(result.stderr).lower():
                    error_msg += " (timeout after {}s)".format(per_rom_timeout)
                results.append(error_msg)
                continue
            
            # Verify Python syntax
            compile_result = subprocess.run(
                ["python3", "-m", "py_compile", output_path],
                capture_output=True
            )
            
            if compile_result.returncode == 0:
                passed += 1
                results.append(f"✓ {rom.name}")
            else:
                failed += 1
                results.append(f"✗ {rom.name}: syntax error")
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    print("\n".join(results))
    print(f"\nPassed: {passed}/{passed + failed}")
    print(f"Using {'release binary' if use_release else 'cargo run --release'}")
    
    assert failed == 0, f"{failed} ROMs failed to transpile"


if __name__ == "__main__":
    test_all_roms_transpile()
