#!/usr/bin/env python3
"""
compare_state.py: Compare CPU register + MMIO state dumps from transpiler vs mGBA
Usage: python3 compare_state.py mgba_dump.json transpiler_dump.json
"""

import json
import sys
import os
from pathlib import Path


def load_dump(path: str) -> dict:
    with open(path, 'r') as f:
        return json.load(f)


def compare_registers(mgba: dict, transpiler: dict) -> list:
    diffs = []
    mgba_regs = mgba.get('cpu_registers', {})
    trans_regs = transpiler.get('cpu_registers', {})
    
    all_regs = set(mgba_regs.keys()) | set(trans_regs.keys())
    
    for reg in sorted(all_regs):
        mgba_val = mgba_regs.get(reg)
        trans_val = trans_regs.get(reg)
        
        if mgba_val != trans_val:
            diffs.append({
                'type': 'register',
                'name': reg,
                'mgba': mgba_val,
                'transpiler': trans_val
            })
    
    return diffs


def compare_mmio(mgba: dict, transpiler: dict) -> list:
    diffs = []
    mgba_mmio = mgba.get('mmio', {})
    trans_mmio = transpiler.get('mmio', {})
    
    all_regs = set(mgba_mmio.keys()) | set(trans_mmio.keys())
    
    for reg in sorted(all_regs):
        mgba_val = mgba_mmio.get(reg)
        trans_val = trans_mmio.get(reg)
        
        if mgba_val != trans_val:
            diffs.append({
                'type': 'mmio',
                'name': reg,
                'mgba': mgba_val,
                'transpiler': trans_val
            })
    
    return diffs


def compare_palette(mgba: dict, transpiler: dict) -> list:
    diffs = []
    mgba_pal = mgba.get('palette_sample', {})
    trans_pal = transpiler.get('palette_sample', {})
    
    all_entries = set(mgba_pal.keys()) | set(trans_pal.keys())
    
    for entry in sorted(all_entries, key=lambda x: int(x)):
        mgba_val = mgba_pal.get(entry)
        trans_val = trans_pal.get(entry)
        
        if mgba_val != trans_val:
            diffs.append({
                'type': 'palette',
                'index': entry,
                'mgba': mgba_val,
                'transpiler': trans_val
            })
    
    return diffs


def compare_bin_files(mgba_dir: str, transpiler_dir: str) -> list:
    diffs = []
    
    for fname in ['vram_sample.bin', 'oam_dump.bin']:
        mgba_path = os.path.join(mgba_dir, fname)
        trans_path = os.path.join(transpiler_dir, fname)
        
        if not os.path.exists(mgba_path):
            continue
        if not os.path.exists(trans_path):
            diffs.append({
                'type': 'binary',
                'file': fname,
                'error': f'Missing in {transpiler_dir}'
            })
            continue
        
        with open(mgba_path, 'rb') as f:
            mgba_data = f.read()
        with open(trans_path, 'rb') as f:
            trans_data = f.read()
        
        if mgba_data != trans_data:
            # Find first difference
            first_diff = None
            for i in range(min(len(mgba_data), len(trans_data))):
                if mgba_data[i] != trans_data[i]:
                    first_diff = i
                    break
            
            diff_count = sum(1 for i in range(min(len(mgba_data), len(trans_data))) 
                           if mgba_data[i] != trans_data[i])
            diffs.append({
                'type': 'binary',
                'file': fname,
                'mgba_size': len(mgba_data),
                'trans_size': len(trans_data),
                'diff_bytes': diff_count,
                'first_diff_offset': first_diff
            })
    
    return diffs


def format_diff(diff: dict) -> str:
    if diff['type'] == 'register':
        return f"  REGISTER {diff['name']}: mGBA={diff['mgba']} transpiler={diff['transpiler']}"
    elif diff['type'] == 'mmio':
        return f"  MMIO {diff['name']}: mGBA={diff['mgba']} transpiler={diff['transpiler']}"
    elif diff['type'] == 'palette':
        return f"  PALETTE[{diff['index']}]: mGBA={diff['mgba']} transpiler={diff['transpiler']}"
    elif diff['type'] == 'binary':
        if 'error' in diff:
            return f"  BINARY {diff['file']}: {diff['error']}"
        return (f"  BINARY {diff['file']}: {diff['diff_bytes']} bytes differ "
                f"(first at offset {diff['first_diff_offset']}, "
                f"mgba={diff['mgba_size']} trans={diff['trans_size']})")
    return f"  {diff}"


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 compare_state.py <mgba_dump.json> <transpiler_dump.json>")
        print("  Or:   python3 compare_state.py <mgba_dir> <transpiler_dir>")
        sys.exit(1)
    
    arg1 = sys.argv[1]
    arg2 = sys.argv[2]
    
    # Determine if we're comparing JSON files or directories
    if os.path.isfile(arg1) and os.path.isfile(arg2):
        mgba = load_dump(arg1)
        transpiler = load_dump(arg2)
        
        mgba_dir = os.path.dirname(arg1)
        trans_dir = os.path.dirname(arg2)
    elif os.path.isdir(arg1) and os.path.isdir(arg2):
        mgba = load_dump(os.path.join(arg1, 'state_dump.json'))
        transpiler = load_dump(os.path.join(arg2, 'state_dump.json'))
        mgba_dir = arg1
        trans_dir = arg2
    else:
        print("Error: Arguments must be both files or both directories")
        sys.exit(1)
    
    print(f"Comparing dumps:")
    print(f"  mGBA:       {arg1}")
    print(f"  Transpiler: {arg2}")
    print()
    
    # Compare CPU registers
    reg_diffs = compare_registers(mgba, transpiler)
    if reg_diffs:
        print(f"CPU REGISTER DIFFERENCES ({len(reg_diffs)}):")
        for d in reg_diffs:
            print(format_diff(d))
        print()
    
    # Compare MMIO
    mmio_diffs = compare_mmio(mgba, transpiler)
    if mmio_diffs:
        print(f"MMIO DIFFERENCES ({len(mmio_diffs)}):")
        for d in mmio_diffs:
            print(format_diff(d))
        print()
    
    # Compare palette
    pal_diffs = compare_palette(mgba, transpiler)
    if pal_diffs:
        print(f"PALETTE DIFFERENCES ({len(pal_diffs)}):")
        for d in pal_diffs:
            print(format_diff(d))
        print()
    
    # Compare binary dumps
    bin_diffs = compare_bin_files(mgba_dir, trans_dir)
    if bin_diffs:
        print(f"BINARY DIFFERENCES ({len(bin_diffs)}):")
        for d in bin_diffs:
            print(format_diff(d))
        print()
    
    total_diffs = len(reg_diffs) + len(mmio_diffs) + len(pal_diffs) + len(bin_diffs)
    
    if total_diffs == 0:
        print("✓ No differences found!")
        sys.exit(0)
    else:
        print(f"✗ Found {total_diffs} total differences")
        sys.exit(1)


if __name__ == '__main__':
    main()