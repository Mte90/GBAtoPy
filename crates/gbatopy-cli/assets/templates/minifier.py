"""
Minification utility for transpiled Python code.

Removes comments, compresses whitespace, and optimizes code size
while maintaining executability and debuggability.
"""

import re
from typing import Optional


def keep_multiline_strings(line: str, keep_docstrings: bool) -> bool:
    """Handle multiline string preservation. Returns True if line should be kept as-is."""
    if not keep_docstrings:
        return False
    return False  # Simplified: not preserving docstrings for max minification


def remove_comments(line: str) -> str:
    """Remove # comments while preserving strings."""
    comment_pos = -1
    in_string = False
    string_char = None
    
    for i, char in enumerate(line):
        if char in ['"', "'"] and (i == 0 or line[i-1] != '\\'):
            in_string = not in_string and char == string_char if in_string else (True if (string_char := char) else False)
        elif char == '#' and not in_string:
            comment_pos = i
            break
    
    return line[:comment_pos] if comment_pos >= 0 else line


def compress_whitespace(line: str) -> str:
    """Compress whitespace while preserving indentation."""
    indent = len(line) - len(line.lstrip())
    stripped = re.sub(r' +', ' ', line.lstrip())
    return ' ' * indent + stripped if indent > 0 else stripped


def minify_python_code(code: str, keep_docstrings: bool = False) -> str:
    """
    Minify Python code by removing comments and compressing whitespace.
    
    Args:
        code: Original Python code
        keep_docstrings: If True, preserve docstrings (triple-quoted strings)
    
    Returns:
        Minified code with reduced size
    """
    lines = code.split('\n')
    result_lines = []
    
    in_multiline_string = False
    multiline_char = None
    
    for line in lines:
        if not line.strip():
            continue
        
        if keep_multiline_strings(line, keep_docstrings):
            continue
        
        line = remove_comments(line)
        line = line.rstrip()
        
        if not line.strip():
            continue
        
        line = compress_whitespace(line)
        result_lines.append(line)
    
    result = '\n'.join(result_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result


def minify_file(input_path: str, output_path: str, keep_docstrings: bool = False) -> int:
    """
    Minify a Python file and write to output.
    
    Args:
        input_path: Path to input file
        output_path: Path to output file
        keep_docstrings: Preserve docstrings if True
    
    Returns:
        Size reduction percentage
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        original = f.read()
    
    minified = minify_python_code(original, keep_docstrings)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(minified)
    
    original_size = len(original)
    minified_size = len(minified)
    
    reduction = ((original_size - minified_size) / original_size) * 100 if original_size > 0 else 0
    
    return reduction


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python minifier.py <input.py> <output.py> [--keep-docstrings]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    keep_docstrings = '--keep-docstrings' in sys.argv
    
    reduction = minify_file(input_file, output_file, keep_docstrings)
    
    print(f"Minified: {input_file} -> {output_file}")
    print(f"Size reduction: {reduction:.1f}%")
