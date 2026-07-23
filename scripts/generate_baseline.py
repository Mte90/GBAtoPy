#!/usr/bin/env python3
import subprocess
import json
import os
import argparse
from pathlib import Path
from datetime import datetime

def transpile_and_measure(rom_path: str, output_dir: str = "/tmp") -> dict:
    """Transpile ROM and measure metrics"""
    rom_name = Path(rom_path).stem
    py_path = os.path.join(output_dir, f"{rom_name}.py")
    
    # Transpile with longer timeout
    result = subprocess.run(
        ['cargo', 'run', '-p', 'gbatopy-cli', '--', 'pipeline',
         '--rom', rom_path, '--output', py_path],
        capture_output=True, text=True, timeout=300
    )
    
    if result.returncode != 0:
        return {'rom_name': rom_name, 'error': 'transpilation_failed'}
    
    # Measure
    if os.path.exists(py_path):
        size = os.path.getsize(py_path)
        with open(py_path, 'r') as f:
            lines = len(f.readlines())
        return {
            'rom_name': rom_name,
            'rom_path': rom_path,
            'lines': lines,
            'size_bytes': size,
            'size_kb': round(size / 1024, 2)
        }
    return {'rom_name': rom_name, 'error': 'file_not_created'}

def main():
    parser = argparse.ArgumentParser(description="Generate baseline metrics for GBAtoPy")
    parser.add_argument("--rom", type=str, help="Single ROM path")
    parser.add_argument("--roms-dir", type=str, default="test_roms/roms",
                       help="Directory containing ROMs")
    parser.add_argument("--output-dir", type=str, default="/tmp",
                       help="Output directory for transpiled Python")
    parser.add_argument("--output", type=str, default="baseline.json",
                       help="Output JSON file")
    args = parser.parse_args()
    
    roms = []
    if args.rom:
        roms = [Path(args.rom)]
    else:
        roms = list(Path(args.roms_dir).glob("*.gba"))
    
    print(f"Generating baseline for {len(roms)} ROMs...")
    results = []
    
    for idx, rom in enumerate(roms, 1):
        print(f"[{idx}/{len(roms)}] {rom.name}")
        metrics = transpile_and_measure(str(rom), args.output_dir)
        results.append(metrics)
        
        if 'error' not in metrics:
            print(f"  {metrics['lines']} lines, {metrics['size_kb']} KB")
        else:
            print(f"  ERROR: {metrics['error']}")
    
    # Save baseline
    baseline = {
        'timestamp': datetime.now().isoformat(),
        'total_roms': len(roms),
        'successful': sum(1 for r in results if 'error' not in r),
        'failed': sum(1 for r in results if 'error' in r),
        'results': results
    }
    
    with open(args.output, 'w') as f:
        json.dump(baseline, f, indent=2)
    
    print(f"\nBaseline saved to {args.output}")
    print(f"Successful: {baseline['successful']}, Failed: {baseline['failed']}")

if __name__ == "__main__":
    main()
