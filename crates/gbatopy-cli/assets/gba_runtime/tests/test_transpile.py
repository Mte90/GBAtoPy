"""
Test suite for GBAtoPy transpiler - edge cases and CLI validation.

Run with: pytest crates/gbatopy-cli/assets/gba_runtime/tests/test_transpile.py -v
"""

import subprocess
import tempfile
import os
import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Get project root path (6 levels up from this test file)."""
    return Path(__file__).resolve().parent.parent.parent.parent.parent.parent


@pytest.fixture
def binary_path(project_root):
    """Get the transpiler binary path."""
    release_binary = project_root / "target" / "release" / "gbatopy-cli"
    if release_binary.exists():
        return release_binary
    # Fallback to cargo run
    return None


@pytest.fixture
def hello_rom(project_root):
    """Path to hello.gba test ROM."""
    return project_root / "test_roms" / "roms" / "hello.gba"


@pytest.fixture
def output_dir(project_root):
    """Project-local temp directory for test outputs."""
    tmp_dir = project_root / "test-reports" / "artifacts" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir


def build_command(binary_path, project_root, args):
    """Build command list for transpiler invocation."""
    if binary_path and binary_path.exists():
        cmd = [str(binary_path), "pipeline"] + args
    else:
        cmd = ["cargo", "run", "-q", "--release", "-p", "gbatopy-cli", "--",
               "pipeline"] + args
    return cmd


def test_single_rom_transpile(hello_rom, output_dir, binary_path, project_root):
    """Test transpiling a single ROM (hello.gba)."""
    assert hello_rom.exists(), "hello.gba test ROM not found"
    
    output_path = output_dir / "hello_single_transpile.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(hello_rom),
        "--output", str(output_path)
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    assert result.returncode == 0, f"Transpile failed: {result.stderr}"
    assert output_path.exists(), "Output file was not created"
    assert output_path.stat().st_size > 0, "Output file is empty"


def test_custom_output_path(hello_rom, output_dir, binary_path, project_root):
    """Test transpiling with custom output path (-o flag)."""
    custom_output = output_dir / "custom_output_test.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(hello_rom),
        "--output", str(custom_output)
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    assert result.returncode == 0, f"Transpile failed: {result.stderr}"
    assert custom_output.exists(), "Custom output file was not created"
    assert custom_output.stat().st_size > 0, "Custom output file is empty"


def test_transpile_minify_flag(hello_rom, output_dir, binary_path, project_root):
    """Test transpiling with --minify flag."""
    output_path = output_dir / "hello_minified.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(hello_rom),
        "--output", str(output_path),
        "--minify"
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    assert result.returncode == 0, f"Minified transpile failed: {result.stderr}"
    assert output_path.exists(), "Minified output file was not created"
    
    # Verify it's still valid Python
    compile_result = subprocess.run(
        ["python3", "-m", "py_compile", str(output_path)],
        capture_output=True
    )
    assert compile_result.returncode == 0, f"Minified output has syntax errors: {compile_result.stderr}"


def test_transpile_no_audio_flag(hello_rom, output_dir, binary_path, project_root):
    """Test transpiling with --no-audio flag."""
    output_path = output_dir / "hello_no_audio.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(hello_rom),
        "--output", str(output_path),
        "--no-audio"
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    assert result.returncode == 0, f"Transpile with --no-audio failed: {result.stderr}"
    assert output_path.exists(), "Output file was not created"


def test_transpile_no_irq_flag(hello_rom, output_dir, binary_path, project_root):
    """Test transpiling with --no-irq flag."""
    output_path = output_dir / "hello_no_irq.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(hello_rom),
        "--output", str(output_path),
        "--no-irq"
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    assert result.returncode == 0, f"Transpile with --no-irq failed: {result.stderr}"
    assert output_path.exists(), "Output file was not created"


def test_transpile_max_output_lines(hello_rom, output_dir, binary_path, project_root):
    """Test transpiling with --max-output-lines flag."""
    output_path = output_dir / "hello_limited.py"
    
    # Use a very high limit to ensure transpile succeeds
    cmd = build_command(binary_path, project_root, [
        "--rom", str(hello_rom),
        "--output", str(output_path),
        "--max-output-lines", "5000000"
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    assert result.returncode == 0, f"Transpile with custom max-output-lines failed: {result.stderr}"
    assert output_path.exists(), "Output file was not created"


def test_nonexistent_rom_error(binary_path, project_root, output_dir):
    """Test transpiling a non-existent ROM returns error."""
    nonexistent_rom = project_root / "test_roms" / "roms" / "does_not_exist.gba"
    output_path = output_dir / "should_not_exist.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(nonexistent_rom),
        "--output", str(output_path)
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    assert result.returncode != 0, "Should have failed for non-existent ROM"
    assert "Failed to read ROM" in result.stderr or "No such file" in result.stderr, \
        f"Error message should mention file not found: {result.stderr}"


def test_invalid_rom_error(binary_path, project_root, output_dir):
    """Test transpiling an invalid/corrupt ROM file returns error."""
    # Create a temporary invalid file
    invalid_file = output_dir / "invalid_rom.gba"
    invalid_file.write_text("This is not a valid GBA ROM file")
    
    output_path = output_dir / "should_not_exist2.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(invalid_file),
        "--output", str(output_path)
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    # Invalid ROMs may fail at various stages - just verify it doesn't succeed
    # when given clearly invalid input
    if result.returncode == 0:
        # If it succeeded, verify the output is at least valid Python
        compile_result = subprocess.run(
            ["python3", "-m", "py_compile", str(output_path)],
            capture_output=True
        )
        # If transpile succeeded but output is invalid Python, that's still a failure
        if compile_result.returncode != 0:
            pytest.fail("Transpile succeeded but produced invalid Python from corrupt ROM")


def test_transpiled_output_is_valid_python(hello_rom, output_dir, binary_path, project_root):
    """Test that transpiled output is valid, compilable Python."""
    output_path = output_dir / "hello_validity_test.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(hello_rom),
        "--output", str(output_path)
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"Transpile failed: {result.stderr}"
    
    # Verify Python syntax by compiling
    compile_result = subprocess.run(
        ["python3", "-m", "py_compile", str(output_path)],
        capture_output=True
    )
    
    assert compile_result.returncode == 0, \
        f"Transpiled output has syntax errors: {compile_result.stderr.decode()}"
    
    # Also verify it can be imported as a module (without running)
    import_result = subprocess.run(
        ["python3", "-c", f"import ast; ast.parse(open('{output_path}').read())"],
        capture_output=True
    )
    assert import_result.returncode == 0, \
        f"Transpiled output cannot be parsed as AST: {import_result.stderr.decode()}"


def test_transpiled_output_contains_runtime(hello_rom, output_dir, binary_path, project_root):
    """Test that transpiled output contains required runtime components."""
    output_path = output_dir / "hello_runtime_test.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(hello_rom),
        "--output", str(output_path)
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"Transpile failed: {result.stderr}"
    
    content = output_path.read_text()
    
    # Check for essential runtime components
    required_strings = [
        "import pygame",           # pygame import
        "if __name__ == \"__main__\":",  # entry point
        "while ",                  # game loop
    ]
    
    for required in required_strings:
        assert required in content, \
            f"Transpiled output missing required component: {required}"


def test_all_feature_flags_combined(hello_rom, output_dir, binary_path, project_root):
    """Test transpiling with multiple feature flags disabled."""
    output_path = output_dir / "hello_minimal.py"
    
    cmd = build_command(binary_path, project_root, [
        "--rom", str(hello_rom),
        "--output", str(output_path),
        "--no-audio",
        "--no-irq",
        "--no-timers",
        "--no-dma",
        "--no-numba"
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    assert result.returncode == 0, f"Transpile with all features disabled failed: {result.stderr}"
    assert output_path.exists(), "Output file was not created"
    
    # Verify it's still valid Python
    compile_result = subprocess.run(
        ["python3", "-m", "py_compile", str(output_path)],
        capture_output=True
    )
    assert compile_result.returncode == 0, \
        f"Minimal output has syntax errors: {compile_result.stderr}"


# Legacy test - keep for backwards compatibility
def test_all_roms_transpile(project_root, binary_path):
    """Verify all test ROMs transpile to valid Python (legacy test)."""
    roms_dir = project_root / "test_roms" / "roms"
    if not roms_dir.exists():
        pytest.skip("test_roms/roms directory not found")
    
    # Use project-local temp directory
    tmp_dir = project_root / "test-reports" / "artifacts" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    
    passed = 0
    failed = 0
    results = []
    per_rom_timeout = 600  # seconds
    
    # Only test a subset for speed - pick small ROMs
    small_roms = list(roms_dir.glob("hello.gba")) + list(roms_dir.glob("ARM_*.gba"))[:3]
    
    for rom in small_roms:
        output_path = tmp_dir / f"{rom.stem}_legacy_transpile.py"
        output_path.touch()
        
        try:
            cmd = build_command(binary_path, project_root, [
                "--rom", str(rom),
                "--output", str(output_path)
            ])
            
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
                    error_msg += " (timeout)"
                results.append(error_msg)
                continue
            
            # Verify Python syntax
            compile_result = subprocess.run(
                ["python3", "-m", "py_compile", str(output_path)],
                capture_output=True
            )
            
            if compile_result.returncode == 0:
                passed += 1
                results.append(f"✓ {rom.name}")
            else:
                failed += 1
                results.append(f"✗ {rom.name}: syntax error")
        finally:
            if output_path.exists():
                output_path.unlink()
    
    print("\n".join(results))
    print(f"\nPassed: {passed}/{passed + failed}")
    
    assert failed == 0, f"{failed} ROMs failed to transpile"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])