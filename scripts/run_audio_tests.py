#!/usr/bin/env python3
"""
Audio spectral test harness runner for GBAtoPy.

Orchestrates the existing capture/compare pipeline across all audio-capable ROMs.
For each ROM: transpile → capture transpiled audio → capture mGBA golden → spectral compare.

Reports per-ROM pass/fail/skip with diff percentage and duration.

Usage:
    python3 scripts/run_audio_tests.py [--rom NAME] [--list] [--verbose] [--output PATH]
"""

import argparse
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Optional


# Audio capture parameters
AUDIO_FRAMES = 300  # ~5 seconds of audio
CAPTURE_TIMEOUT = 30  # seconds per step
PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def load_config(config_path: Path) -> list[dict]:
    """Load test configuration and filter for audio-capable ROMs."""
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(config_path, 'rb') as f:
        config = tomllib.load(f)
    
    # Filter ROMs with "audio" in features
    audio_roms = []
    for test in config.get('tests', []):
        features = test.get('features', [])
        if 'audio' in features:
            audio_roms.append(test)
    
    return audio_roms


def transpile_rom(rom_path: Path, output_path: Path, verbose: bool = False) -> tuple[bool, str]:
    """Transpile a GBA ROM to Python."""
    cmd = [
        str(PROJECT_ROOT / 'target' / 'release' / 'gbatopy-cli'),
        'pipeline',
        '--rom', str(rom_path),
        '--output', str(output_path)
    ]
    
    if verbose:
        print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CAPTURE_TIMEOUT,
            cwd=Path(__file__).parent.parent
        )
        
        if result.returncode != 0:
            return False, f"Transpile failed: {result.stderr.strip()}"
        
        if not output_path.exists():
            return False, "Transpile succeeded but output file not created"
        
        return True, ""
    
    except subprocess.TimeoutExpired:
        return False, "Transpile timed out"
    except Exception as e:
        return False, f"Transpile error: {str(e)}"


def capture_transpiled_audio(transpiled_path: Path, output_path: Path, audio_frames: int, verbose: bool = False) -> tuple[bool, str]:
    """Capture audio from transpiled Python ROM."""
    cmd = [
        'python3',
        'scripts/audio/capture_transpiled.py',
        str(transpiled_path),
        str(output_path),
        '--frames', str(audio_frames)
    ]
    
    if verbose:
        print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CAPTURE_TIMEOUT,
            cwd=Path(__file__).parent.parent
        )
        
        if result.returncode != 0:
            return False, f"Capture failed: {result.stderr.strip()}"
        
        if not output_path.exists():
            return False, "Capture succeeded but output file not created"
        
        return True, ""
    
    except subprocess.TimeoutExpired:
        return False, "Audio capture timed out"
    except Exception as e:
        return False, f"Capture error: {str(e)}"


def capture_golden_audio(rom_path: Path, output_path: Path, audio_frames: int, verbose: bool = False) -> tuple[bool, str]:
    """Capture golden audio from mGBA."""
    script_path = Path(__file__).parent / 'audio' / 'capture_golden.sh'
    
    if not script_path.exists():
        return False, f"Capture script not found: {script_path}"
    
    cmd = [
        'bash',
        str(script_path),
        str(rom_path),
        '--frame', str(audio_frames),
        '--output', str(output_path)
    ]
    
    if verbose:
        print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CAPTURE_TIMEOUT,
            cwd=Path(__file__).parent.parent
        )
        
        if result.returncode != 0:
            return False, f"Golden capture failed: {result.stderr.strip()}"
        
        if not output_path.exists():
            return False, "Golden capture succeeded but output file not created"
        
        return True, ""
    
    except subprocess.TimeoutExpired:
        return False, "Golden capture timed out"
    except Exception as e:
        return False, f"Golden capture error: {str(e)}"


def compare_audio(golden_path: Path, transpiled_path: Path, audio_frames: int, verbose: bool = False) -> tuple[str, float, str]:
    """
    Compare golden and transpiled audio.
    
    Returns: (status, diff_percentage, notes)
    - status: 'PASS', 'FAIL', or 'SKIP'
    - diff_percentage: float (0.0-100.0)
    - notes: additional information
    """
    cmd = [
        'python3',
        'scripts/verify/compare_audio.py',
        str(golden_path),
        str(transpiled_path),
        '--frame', str(audio_frames)
    ]
    
    if verbose:
        print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CAPTURE_TIMEOUT,
            cwd=Path(__file__).parent.parent
        )
        
        # Parse output to extract diff percentage
        diff_pct = 0.0
        notes = ""
        
        for line in result.stdout.split('\n'):
            if 'Difference:' in line:
                try:
                    diff_pct = float(line.split('%')[0].split()[-1])
                except (ValueError, IndexError):
                    pass
            
            if 'SKIP' in line and 'silent' in line:
                notes = "both silent"
        
        # Determine status from exit code and output
        if result.returncode == 0:
            if 'SKIP' in result.stdout:
                return 'SKIP', diff_pct, notes or "both silent"
            return 'PASS', diff_pct, ""
        else:
            return 'FAIL', diff_pct, ""
    
    except subprocess.TimeoutExpired:
        return 'FAIL', 0.0, "compare timed out"
    except Exception as e:
        return 'FAIL', 0.0, f"compare error: {str(e)}"


def run_single_rom(
    rom_name: str,
    rom_path: Path,
    output_dir: Path,
    audio_frames: int,
    verbose: bool = False
) -> dict:
    """Run the full audio test pipeline for a single ROM."""
    result = {
        'name': rom_name,
        'status': 'SKIP',
        'diff_pct': 0.0,
        'duration': 0.0,
        'notes': ''
    }
    
    start_time = time.time()
    
    # Check ROM exists
    if not rom_path.exists():
        result['status'] = 'SKIP'
        result['notes'] = 'ROM not found'
        result['duration'] = time.time() - start_time
        return result
    
    # Paths for intermediate files
    transpiled_path = output_dir / f"{rom_name}_audio.py"
    transpiled_audio_path = output_dir / f"{rom_name}_transpiled.wav"
    golden_audio_path = output_dir / f"{rom_name}_golden.wav"
    
    # Step 1: Transpile
    success, error = transpile_rom(rom_path, transpiled_path, verbose)
    if not success:
        result['status'] = 'FAIL'
        result['notes'] = error
        result['duration'] = time.time() - start_time
        return result
    
    # Step 2: Capture transpiled audio
    success, error = capture_transpiled_audio(transpiled_path, transpiled_audio_path, audio_frames, verbose)
    if not success:
        result['status'] = 'FAIL'
        result['notes'] = error
        result['duration'] = time.time() - start_time
        return result
    
    # Step 3: Capture golden audio
    success, error = capture_golden_audio(rom_path, golden_audio_path, audio_frames, verbose)
    if not success:
        result['status'] = 'FAIL'
        result['notes'] = error
        result['duration'] = time.time() - start_time
        return result
    
    # Step 4: Compare audio
    status, diff_pct, notes = compare_audio(golden_audio_path, transpiled_audio_path, audio_frames, verbose)
    result['status'] = status
    result['diff_pct'] = diff_pct
    result['notes'] = notes
    
    result['duration'] = time.time() - start_time
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Audio spectral test harness runner for GBAtoPy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 scripts/run_audio_tests.py --list
    python3 scripts/run_audio_tests.py --rom helloAudio
    python3 scripts/run_audio_tests.py --rom helloAudio --verbose
    python3 scripts/run_audio_tests.py --output /tmp/audio_report.txt
"""
    )
    
    parser.add_argument(
        '--rom',
        type=str,
        help='Test a single ROM by name'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all audio-capable ROMs and exit'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output including commands run'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Write results to file instead of stdout'
    )
    parser.add_argument(
        '--frames',
        type=int,
        default=AUDIO_FRAMES,
        help=f'Number of audio frames to capture (default: {AUDIO_FRAMES})'
    )
    
    args = parser.parse_args()
    
    # Update audio frames for this run
    audio_frames = args.frames
    
    # Set paths
    project_root = Path(__file__).parent.parent
    config_path = project_root / 'test-roms-config.toml'
    roms_dir = project_root / 'test_roms' / 'roms'
    output_dir = Path('/tmp')
    
    # Load configuration
    audio_roms = load_config(config_path)
    
    if not audio_roms:
        print("No audio-capable ROMs found in test-roms-config.toml", file=sys.stderr)
        sys.exit(2)
    
    # List mode
    if args.list:
        print(f"Found {len(audio_roms)} audio-capable ROMs:")
        print('-' * 60)
        for rom in audio_roms:
            name = rom.get('name', 'unknown')
            features = rom.get('features', [])
            print(f"  {name:40} features: {', '.join(features)}")
        print('-' * 60)
        print(f"Total: {len(audio_roms)}")
        sys.exit(0)
    
    # Single ROM mode
    if args.rom:
        # Find the ROM in config
        target_rom = None
        for rom in audio_roms:
            if rom.get('name') == args.rom:
                target_rom = rom
                break
        
        if not target_rom:
            print(f"Error: ROM '{args.rom}' not found in audio-capable ROMs", file=sys.stderr)
            print(f"Available audio ROMs: {[r.get('name') for r in audio_roms]}", file=sys.stderr)
            sys.exit(2)
        
        rom_path = roms_dir / target_rom.get('rom_path', f"{args.rom}.gba")
        result = run_single_rom(args.rom, rom_path, output_dir, audio_frames, args.verbose)
        
        # Output results
        output_lines = []
        output_lines.append('=' * 70)
        output_lines.append(f"ROM: {result['name']}")
        output_lines.append(f"Status: {result['status']}")
        if result['diff_pct'] > 0:
            output_lines.append(f"Diff: {result['diff_pct']:.2f}%")
        if result['notes']:
            output_lines.append(f"Notes: {result['notes']}")
        output_lines.append(f"Duration: {result['duration']:.2f}s")
        output_lines.append('=' * 70)
        
        output_text = '\n'.join(output_lines)
        
        if args.output:
            args.output.write_text(output_text)
            print(f"Results written to {args.output}")
        else:
            print(output_text)
        
        # Exit code based on status
        if result['status'] == 'PASS':
            sys.exit(0)
        elif result['status'] == 'SKIP':
            sys.exit(2)
        else:
            sys.exit(1)
    
    # Batch mode: run all audio ROMs
    print('=' * 70)
    print("GBAtoPy Audio Spectral Test Runner")
    print('=' * 70)
    print(f"Testing {len(audio_roms)} audio-capable ROMs")
    print(f"Audio frames per ROM: {audio_frames}")
    print(f"Output directory: {output_dir}")
    print('=' * 70)
    
    results = []
    for rom in audio_roms:
        name = rom.get('name', 'unknown')
        rom_path = roms_dir / rom.get('rom_path', f"{name}.gba")
        
        print(f"\n[{len(results) + 1}/{len(audio_roms)}] Testing: {name}")
        result = run_single_rom(name, rom_path, output_dir, audio_frames, args.verbose)
        results.append(result)
        
        # Print result summary
        status_str = result['status']
        if status_str == 'PASS':
            status_str = f"PASS ({result['diff_pct']:.2f}%)"
        elif result['notes']:
            status_str = f"{status_str} ({result['notes']})"
        
        print(f"  → {status_str} ({result['duration']:.2f}s)")
    
    # Print summary table
    print('\n' + '=' * 70)
    print("SUMMARY")
    print('=' * 70)
    print(f"{'ROM':<35} {'Status':<15} {'Diff%':>8} {'Duration':>10}")
    print('-' * 70)
    
    pass_count = 0
    fail_count = 0
    skip_count = 0
    
    for r in results:
        diff_str = f"{r['diff_pct']:.2f}" if r['diff_pct'] > 0 else '-'
        print(f"{r['name']:<35} {r['status']:<15} {diff_str:>8} {r['duration']:>10.2f}s")
        
        if r['status'] == 'PASS':
            pass_count += 1
        elif r['status'] == 'FAIL':
            fail_count += 1
        else:
            skip_count += 1
    
    print('-' * 70)
    total = len(results)
    print(f"Total: {total} | PASS: {pass_count} | FAIL: {fail_count} | SKIP: {skip_count}")
    print('=' * 70)
    
    # Exit code
    if fail_count > 0:
        sys.exit(1)
    elif skip_count == total:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
