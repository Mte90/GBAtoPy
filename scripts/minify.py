#!/usr/bin/env python3
"""
Minification script for generated Python code.
Removes comments, extra whitespace, and unused lines.
"""

import re
import argparse
from pathlib import Path


def minify_python(content: str) -> str:
    """Minify Python code by removing comments and extra whitespace."""
    lines = content.split('\n')
    minified_lines = []
    
    for line in lines:
        # Remove trailing whitespace
        line = line.rstrip()
        
        # Skip pure comment lines
        if line.strip().startswith('#'):
            continue
        
        # Skip empty lines
        if not line.strip():
            continue
        
        # Remove inline comments (simple case - not in strings)
        if '#' in line:
            # Find # that's not in a string
            in_string = False
            string_char = None
            for i, char in enumerate(line):
                if char in '"\'':
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char:
                        in_string = False
                elif char == '#' and not in_string:
                    line = line[:i].rstrip()
                    break
        
        minified_lines.append(line)
    
    return '\n'.join(minified_lines)
    
    # Join with single newline
    return '\n'.join(minified_lines)


def minify_file(input_path: str, output_path: str = None) -> tuple:
    """Minify a Python file and return (original_size, minified_size)."""
    with open(input_path, 'r') as f:
        content = f.read()
    
    original_size = len(content)
    minified_content = minify_python(content)
    minified_size = len(minified_content)
    
    if output_path is None:
        output_path = input_path.replace('.py', '_minified.py')
    
    with open(output_path, 'w') as f:
        f.write(minified_content)
    
    reduction = (1 - minified_size / original_size) * 100
    
    return original_size, minified_size, reduction


def main():
    parser = argparse.ArgumentParser(description="Minify generated Python code")
    parser.add_argument("input", type=str, help="Input Python file")
    parser.add_argument("--output", type=str, help="Output file (default: input_minified.py)")
    
    args = parser.parse_args()
    
    if not Path(args.input).exists():
        print(f"Error: File not found: {args.input}")
        return
    
    orig, min_size, reduction = minify_file(args.input, args.output)
    
    print(f"Original:   {orig:,} bytes")
    print(f"Minified:   {min_size:,} bytes")
    print(f"Reduction:  {reduction:.1f}%")
    print(f"Output:     {args.output or args.input.replace('.py', '_minified.py')}")


if __name__ == "__main__":
    main()
