#!/usr/bin/env python3
"""
self_validate.py: Self-validation harness for transpiled GBA ROMs

Runs transpiled Python ROMs and validates their execution state against
expected outputs (generated from mGBA or provided manually).

Usage:
    python3 self_validate.py <transpiled_rom.py> [--frames N] [--compare FILE]
"""

import sys
import os
import json
import argparse
import importlib.util
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "crates" / "gbatopy-cli" / "assets" / "gba_runtime"))


def get_cpu_state(cpu) -> Dict[str, Any]:
    state = {
        "registers": {},
        "cpsr": cpu.cpsr,
        "thumb_mode": cpu.thumb_mode,
    }
    for i, name in enumerate(['r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7',
                               'r8', 'r9', 'r10', 'r11', 'r12', 'sp', 'lr', 'pc']):
        state["registers"][name] = cpu.registers[i]
    n = (cpu.cpsr >> 31) & 1
    z = (cpu.cpsr >> 30) & 1
    c = (cpu.cpsr >> 29) & 1
    v = (cpu.cpsr >> 28) & 1
    state["flags"] = {"N": n, "Z": z, "C": c, "V": v}
    return state


def get_mmio_state(memory) -> Dict[str, int]:
    mmio = {}
    mmio_addrs = {
        "DISPCNT": 0x04000000, "DISPSTAT": 0x04000004, "VCOUNT": 0x04000006,
        "BG0CNT": 0x04000008, "BG1CNT": 0x0400000A, "BG2CNT": 0x0400000C,
        "BG3CNT": 0x0400000E, "IE": 0x04000200, "IF": 0x04000202, "IME": 0x04000208,
        "KEYINPUT": 0x04000130, "KEYCNT": 0x04000132, "TM0CNT": 0x04000100,
        "TM1CNT": 0x04000104, "TM2CNT": 0x04000108, "TM3CNT": 0x0400010C,
        "DMA0CNT": 0x040000B0, "DMA1CNT": 0x040000B4, "DMA2CNT": 0x040000B8,
        "DMA3CNT": 0x040000BC,
    }
    for name, addr in mmio_addrs.items():
        try:
            mmio[name] = memory.read16(addr)
        except Exception:
            mmio[name] = 0
    return mmio


def run_transpiled_rom(py_path: str, frames: int = 60, headless: bool = True) -> Dict[str, Any]:
    if headless:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    spec = importlib.util.spec_from_file_location("transpiled_rom", py_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {py_path}")
    module = importlib.util.module_from_spec(spec)
    with open(py_path, 'r') as f:
        module_source = f.read()
    namespace = {'__name__': 'transpiled_rom', '__builtins__': __builtins__}
    exec(compile(module_source, py_path, 'exec'), namespace)
    game_class = namespace.get('Game') or namespace.get('GBAGame') or namespace.get('ROM')
    if game_class is None:
        raise RuntimeError(f"No Game class found in {py_path}")
    game = game_class(headless=headless)
    for _ in range(frames):
        try:
            game.update()
        except Exception as e:
            print(f"Warning: Exception during update: {e}")
            break
    state = {"frame": frames}
    if hasattr(game, 'cpu'):
        state["cpu"] = get_cpu_state(game.cpu)
    if hasattr(game, 'memory'):
        state["mmio"] = get_mmio_state(game.memory)
        state["memory_regions"] = {}
        if hasattr(game.memory, 'ewram'):
            state["memory_regions"]["ewram_size"] = len(game.memory.ewram)
        if hasattr(game.memory, 'iwram'):
            state["memory_regions"]["iwram_size"] = len(game.memory.iwram)
        if hasattr(game.memory, 'vram'):
            state["memory_regions"]["vram_size"] = len(game.memory.vram)
    if hasattr(game, 'screen'):
        state["has_screen"] = True
    if hasattr(game, 'ppu'):
        state["ppu_mode"] = game.ppu.display_mode if hasattr(game.ppu, 'display_mode') else 0
    return state


def compare_states(actual: Dict[str, Any], expected: Dict[str, Any], verbose: bool = False) -> List[Dict[str, Any]]:
    diffs = []
    if "cpu" in actual and "cpu" in expected:
        actual_cpu = actual["cpu"]
        expected_cpu = expected["cpu"]
        for reg_name in expected_cpu.get("registers", {}):
            actual_val = actual_cpu.get("registers", {}).get(reg_name)
            expected_val = expected_cpu.get("registers", {}).get(reg_name)
            if actual_val != expected_val:
                diffs.append({
                    "type": "register", "name": reg_name,
                    "actual": f"0x{actual_val:08X}" if actual_val is not None else "N/A",
                    "expected": f"0x{expected_val:08X}" if expected_val is not None else "N/A",
                })
        if actual_cpu.get("cpsr") != expected_cpu.get("cpsr"):
            diffs.append({"type": "cpsr", "actual": f"0x{actual_cpu.get('cpsr', 0):08X}", "expected": f"0x{expected_cpu.get('cpsr', 0):08X}"})
        actual_flags = actual_cpu.get("flags", {})
        expected_flags = expected_cpu.get("flags", {})
        for flag in ["N", "Z", "C", "V"]:
            if actual_flags.get(flag) != expected_flags.get(flag):
                diffs.append({"type": "flag", "name": flag, "actual": actual_flags.get(flag, 0), "expected": expected_flags.get(flag, 0)})
    if "mmio" in actual and "mmio" in expected:
        for reg_name in expected.get("mmio", {}):
            actual_val = actual.get("mmio", {}).get(reg_name)
            expected_val = expected.get("mmio", {}).get(reg_name)
            if actual_val != expected_val:
                diffs.append({
                    "type": "mmio", "name": reg_name,
                    "actual": f"0x{actual_val:04X}" if actual_val is not None else "N/A",
                    "expected": f"0x{expected_val:04X}" if expected_val is not None else "N/A",
                })
    if verbose and diffs:
        print("\nDifferences found:")
        for d in diffs:
            print(f"  {d['type']}: {d.get('name', '')} - actual: {d.get('actual', '')}, expected: {d.get('expected', '')}")
    return diffs


def load_expected(expected_path: str) -> Dict[str, Any]:
    with open(expected_path, 'r') as f:
        return json.load(f)


def save_state(state: Dict[str, Any], output_path: str):
    with open(output_path, 'w') as f:
        json.dump(state, f, indent=2)
    print(f"State saved to {output_path}")


def find_roms(roms_dir: str = "test_roms/roms") -> List[str]:
    roms = []
    rom_dir = Path(roms_dir)
    if rom_dir.exists():
        for f in rom_dir.glob("*.gba"):
            roms.append(str(f))
    return sorted(roms)


def get_rom_basename(rom_path: str) -> str:
    return Path(rom_path).stem


def main():
    parser = argparse.ArgumentParser(description='Self-validation harness for transpiled GBA ROMs')
    parser.add_argument("rom", nargs="?", help="Path to transpiled Python ROM file")
    parser.add_argument("--frames", type=int, default=60, help="Number of frames to run (default: 60)")
    parser.add_argument("--expected-dir", default="scripts/verify_roms/expected_outputs", help="Directory containing expected outputs")
    parser.add_argument("--output", help="Save state to JSON file")
    parser.add_argument("--compare", help="Compare against expected state file")
    parser.add_argument("--verbose", action="store_true", help="Print detailed comparison")
    parser.add_argument("--list", action="store_true", help="List available test ROMs")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default: True)")
    args = parser.parse_args()
    if args.list:
        roms = find_roms()
        print(f"Found {len(roms)} test ROMs:")
        for rom in roms:
            print(f"  {rom}")
        return 0
    if not args.rom:
        parser.error("ROM path required (or use --list)")
    rom_path = Path(args.rom)
    if not rom_path.exists():
        print(f"Error: File not found: {args.rom}")
        return 1
    print(f"Running {args.rom} for {args.frames} frames...")
    try:
        state = run_transpiled_rom(str(rom_path), frames=args.frames, headless=args.headless)
        print(f"Execution completed at frame {state.get('frame', '?')}")
        if args.output:
            save_state(state, args.output)
        if args.compare:
            expected = load_expected(args.compare)
            diffs = compare_states(state, expected, verbose=args.verbose)
            if diffs:
                print(f"\nFailed: {len(diffs)} differences found")
                return 1
            else:
                print("\nPassed: State matches expected")
                return 0
        expected_dir = Path(args.expected_dir)
        expected_file = expected_dir / f"{get_rom_basename(args.rom)}_expected.json"
        if expected_file.exists():
            expected = load_expected(str(expected_file))
            diffs = compare_states(state, expected, verbose=args.verbose)
            if diffs:
                print(f"\nFailed: {len(diffs)} differences found")
                return 1
            else:
                print("\nPassed: State matches expected")
                return 0
        else:
            print(f"\nNo expected output found at {expected_file}")
            print("Run with --compare <file> to compare against a reference")
        if args.verbose:
            print("\nCPU State:")
            if "cpu" in state:
                cpu = state["cpu"]
                print(f"  CPSR: 0x{cpu.get('cpsr', 0):08X}")
                print(f"  Flags: N={cpu.get('flags', {}).get('N')} Z={cpu.get('flags', {}).get('Z')} C={cpu.get('flags', {}).get('C')} V={cpu.get('flags', {}).get('V')}")
                print(f"  PC: 0x{cpu.get('registers', {}).get('pc', 0):08X}")
                print(f"  LR: 0x{cpu.get('registers', {}).get('lr', 0):08X}")
                print(f"  SP: 0x{cpu.get('registers', {}).get('sp', 0):08X}")
        return 0
    except Exception as e:
        print(f"Error running ROM: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())