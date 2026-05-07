# gbatopy-codegen

Generates Python code from GBAtoPy IR modules.

## Usage

```bash
cargo build --release
```

## Output format

The generator produces Python modules with:
- Function definitions for each IR function
- A `func_map` dictionary mapping addresses to function names
- Direct translation of IR operations to Python expressions
