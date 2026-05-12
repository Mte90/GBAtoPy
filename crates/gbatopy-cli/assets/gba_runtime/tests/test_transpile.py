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
    roms_dir = Path("test_roms/roms")
    if not roms_dir.exists():
        pytest.skip("test_roms/roms directory not found")
    
    passed = 0
    failed = 0
    results = []
    
    for rom in roms_dir.glob("*.gba"):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            output_path = f.name
        
        try:
            # Transpile
            result = subprocess.run(
                ["cargo", "run", "-q", "-p", "gbatopy-cli", "--",
                 "pipeline", "--rom", str(rom), "--output", output_path],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                failed += 1
                results.append(f"✗ {rom.name}: transpile failed")
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
    
    assert failed == 0, f"{failed} ROMs failed to transpile"


if __name__ == "__main__":
    test_all_roms_transpile()
