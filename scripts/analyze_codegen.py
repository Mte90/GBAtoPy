#!/usr/bin/env python3
import os
import sys
import csv
import argparse
from pathlib import Path
from typing import Dict, List, Tuple


def analyze_file(file_path: str) -> Dict:
    """Analyze a single Python file for code metrics"""
    with open(file_path, 'r') as f:
        content = f.read()
        lines = content.split('\n')
    
    total_lines = len(lines)
    blank_lines = 0
    comment_lines = 0
    code_lines = 0
    function_count = 0
    class_count = 0
    global_count = 0
    import_count = 0
    decorator_count = 0
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            blank_lines += 1
        elif stripped.startswith('#'):
            comment_lines += 1
        else:
            code_lines += 1
            if stripped.startswith('def '):
                function_count += 1
            elif stripped.startswith('class '):
                class_count += 1
            elif stripped.startswith('global '):
                global_count += 1
            elif stripped.startswith('import ') or stripped.startswith('from '):
                import_count += 1
            elif stripped.startswith('@'):
                decorator_count += 1
    
    file_size = os.path.getsize(file_path)
    
    # Calculate overhead
    overhead_lines = blank_lines + comment_lines
    overhead_pct = (overhead_lines / total_lines * 100) if total_lines > 0 else 0
    code_pct = (code_lines / total_lines * 100) if total_lines > 0 else 0
    
    return {
        'total_lines': total_lines,
        'code_lines': code_lines,
        'blank_lines': blank_lines,
        'comment_lines': comment_lines,
        'function_count': function_count,
        'class_count': class_count,
        'global_count': global_count,
        'import_count': import_count,
        'decorator_count': decorator_count,
        'file_size_bytes': file_size,
        'overhead_lines': overhead_lines,
        'overhead_pct': round(overhead_pct, 2),
        'code_pct': round(code_pct, 2),
        'lines_per_function': round(total_lines / function_count, 2) if function_count > 0 else 0,
        'size_per_function': round(file_size / function_count, 2) if function_count > 0 else 0
    }


def analyze_rom(rom_path: str, output_dir: str = "/tmp") -> Dict:
    """Analyze transpiled ROM"""
    rom_name = Path(rom_path).stem
    py_path = os.path.join(output_dir, f"{rom_name}.py")
    
    if not os.path.exists(py_path):
        # Transpile first
        print(f"  Transpiling {rom_name}...")
        import subprocess
        result = subprocess.run(
            ['cargo', 'run', '-p', 'gbatopy-cli', '--', 'pipeline',
             '--rom', rom_path, '--output', py_path],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            print(f"  ✗ Transpilation failed: {result.stderr[:200]}")
            return None
    
    metrics = analyze_file(py_path)
    metrics['rom_name'] = rom_name
    metrics['rom_path'] = rom_path
    
    return metrics


def analyze_all_roms(rom_dir: str, output_dir: str = "/tmp") -> List[Dict]:
    """Analyze all ROMs in directory"""
    rom_files = list(Path(rom_dir).glob("*.gba"))
    results = []
    
    print(f"\n{'='*70}")
    print(f"Code Size Analysis - {len(rom_files)} ROMs")
    print(f"{'='*70}")
    
    for idx, rom_path in enumerate(rom_files, 1):
        print(f"[{idx}/{len(rom_files)}] {rom_path.name}")
        metrics = analyze_rom(str(rom_path), output_dir)
        if metrics:
            results.append(metrics)
            print(f"  Lines: {metrics['total_lines']}, "
                  f"Functions: {metrics['function_count']}, "
                  f"Overhead: {metrics['overhead_pct']}%")
    
    return results


def generate_report(results: List[Dict], output_path: str):
    """Generate CSV report"""
    if not results:
        print("No results to report")
        return
    
    fieldnames = [
        'rom_name', 'rom_path', 'total_lines', 'code_lines', 'blank_lines', 'comment_lines',
        'function_count', 'class_count', 'global_count', 'import_count', 'decorator_count',
        'file_size_bytes', 'overhead_lines', 'overhead_pct', 'code_pct',
        'lines_per_function', 'size_per_function'
    ]
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\nReport saved to: {output_path}")


def print_summary(results: List[Dict]):
    """Print analysis summary"""
    if not results:
        print("No results to summarize")
        return
    
    print(f"\n{'='*70}")
    print("CODE SIZE ANALYSIS SUMMARY")
    print(f"{'='*70}")
    
    avg_lines = sum(r['total_lines'] for r in results) / len(results)
    avg_functions = sum(r['function_count'] for r in results) / len(results)
    avg_overhead = sum(r['overhead_pct'] for r in results) / len(results)
    avg_size = sum(r['file_size_bytes'] for r in results) / len(results)
    
    print(f"Total ROMs analyzed: {len(results)}")
    print(f"Average lines per ROM: {avg_lines:.0f}")
    print(f"Average functions per ROM: {avg_functions:.0f}")
    print(f"Average overhead: {avg_overhead:.1f}%")
    print(f"Average file size: {avg_size/1024:.1f} KB")
    
    # Top 5 largest
    print(f"\nTop 5 Largest ROMs:")
    largest = sorted(results, key=lambda r: r['total_lines'], reverse=True)[:5]
    for r in largest:
        print(f"  {r['rom_name']}: {r['total_lines']} lines, "
              f"{r['function_count']} functions, {r['overhead_pct']}% overhead")
    
    # Top 5 highest overhead
    print(f"\nTop 5 Highest Overhead:")
    highest_overhead = sorted(results, key=lambda r: r['overhead_pct'], reverse=True)[:5]
    for r in highest_overhead:
        print(f"  {r['rom_name']}: {r['overhead_pct']}% overhead "
              f"({r['blank_lines']} blank, {r['comment_lines']} comments)")
    
    # Identify top 5 bloat sources
    print(f"\nTop Code Bloat Sources:")
    total_blank = sum(r['blank_lines'] for r in results)
    total_comments = sum(r['comment_lines'] for r in results)
    total_overhead = total_blank + total_comments
    
    print(f"  1. Blank lines: {total_blank} ({total_blank/total_overhead*100:.1f}% of overhead)")
    print(f"  2. Comments: {total_comments} ({total_comments/total_overhead*100:.1f}% of overhead)")
    
    # Lines per function analysis
    avg_lines_per_func = sum(r['lines_per_function'] for r in results) / len(results)
    print(f"\n  3. Average lines per function: {avg_lines_per_func:.1f}")
    print(f"     (Target: <10 lines/function for efficient code)")


def main():
    parser = argparse.ArgumentParser(description="Analyze GBAtoPy code generation metrics")
    parser.add_argument("--rom", type=str, help="Single ROM to analyze")
    parser.add_argument("--roms-dir", type=str, default="test_roms/roms",
                       help="Directory containing ROMs")
    parser.add_argument("--output-dir", type=str, default="/tmp",
                       help="Directory for transpiled Python files")
    parser.add_argument("--output", type=str, default="codegen_analysis.csv",
                       help="Output CSV file")
    parser.add_argument("--summary", action="store_true",
                       help="Print summary")
    
    args = parser.parse_args()
    
    results = []
    
    if args.rom:
        metrics = analyze_rom(args.rom, args.output_dir)
        if metrics:
            results.append(metrics)
    else:
        results = analyze_all_roms(args.roms_dir, args.output_dir)
    
    generate_report(results, args.output)
    
    if args.summary or not args.rom:
        print_summary(results)


if __name__ == "__main__":
    main()
