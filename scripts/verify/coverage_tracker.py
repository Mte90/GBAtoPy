#!/usr/bin/env python3
"""
coverage_tracker.py: Feature coverage tracker for GBAtoPy transpiler

Analyzes transpiled Python ROMs to detect which GBA features they use,
and reports coverage against the known feature set.

Usage:
    python3 coverage_tracker.py <transpiled_rom.py>
    python3 coverage_tracker.py --roms-dir test_roms/roms --output-dir /tmp/coverage
"""

import sys
import re
import json
import argparse
from pathlib import Path
from typing import Dict, Set, List, Any, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict


# GBA Feature definitions
ARM_INSTRUCTIONS = {
    # Data Processing
    "MOV", "MVN", "ADD", "ADC", "SUB", "SBC", "RSB", "RSC",
    "AND", "EOR", "ORR", "BIC", "TST", "TEQ", "CMP", "CMN",
    # Multiply
    "MUL", "MLA", "UMULL", "UMLAL", "SMULL", "SMLAL",
    # Load/Store
    "LDR", "STR", "LDRB", "STRB", "LDRH", "STRH", "LDRSB", "LDRSH",
    "LDM", "STM", "SWP", "SWPB",
    # Branch
    "B", "BL", "BX", "BLX",
    # Status
    "MRS", "MSR",
    # Other
    "SWI", "NOP",
}

THUMB_INSTRUCTIONS = {
    # Data Processing
    "MOV", "MVN", "ADD", "SUB", "ADC", "SBC",
    "AND", "EOR", "ORR", "BIC", "LSL", "LSR", "ASR", "ROR",
    "CMP", "CMN", "TST",
    # Load/Store
    "LDR", "STR", "LDRB", "STRB", "LDRH", "STRH",
    "LDRSP", "STRSP", "LDRPC",
    "PUSH", "POP", "LDMIA", "STMIA",
    # Branch
    "B", "BL", "BX", "BEQ", "BNE", "BCS", "BCC", "BMI", "BPL",
    "BVS", "BVC", "BHI", "BLS", "BGE", "BLT", "BGT", "BLE",
    # Other
    "SWI", "NOP", "ADDSP", "SUBSP",
}

# MMIO register categories
MMIO_REGISTERS = {
    # Display
    "DISPCNT", "DISPSTAT", "VCOUNT",
    "BG0CNT", "BG1CNT", "BG2CNT", "BG3CNT",
    "BG0HOFS", "BG0VOFS", "BG1HOFS", "BG1VOFS",
    "BG2HOFS", "BG2VOFS", "BG3HOFS", "BG3VOFS",
    "BG2PA", "BG2PB", "BG2PC", "BG2PD", "BG2X", "BG2Y",
    "BG3PA", "BG3PB", "BG3PC", "BG3PD", "BG3X", "BG3Y",
    "WIN0H", "WIN1H", "WIN0V", "WIN1V", "WININ", "WINOUT",
    "MOSAIC", "BLDCNT", "BLDALPHA", "BLDY",
    # Sound
    "SOUND1CNT_L", "SOUND1CNT_H", "SOUND1CNT_X",
    "SOUND2CNT_L", "SOUND2CNT_H",
    "SOUND3CNT_L", "SOUND3CNT_H", "SOUND3CNT_X",
    "SOUND4CNT_L", "SOUND4CNT_H",
    "SOUNDCNT_L", "SOUNDCNT_H", "SOUNDCNT_X",
    "FIFO_A", "FIFO_B",
    # DMA
    "DMA0SAD", "DMA0DAD", "DMA0CNT_L", "DMA0CNT_H",
    "DMA1SAD", "DMA1DAD", "DMA1CNT_L", "DMA1CNT_H",
    "DMA2SAD", "DMA2DAD", "DMA2CNT_L", "DMA2CNT_H",
    "DMA3SAD", "DMA3DAD", "DMA3CNT_L", "DMA3CNT_H",
    # Timers
    "TM0CNT_L", "TM0CNT_H", "TM1CNT_L", "TM1CNT_H",
    "TM2CNT_L", "TM2CNT_H", "TM3CNT_L", "TM3CNT_H",
    # Keypad
    "KEYINPUT", "KEYCNT",
    # Serial
    "SIOCNT", "SIODATA", "RCNT",
    # Interrupts
    "IE", "IF", "IME",
    # System
    "WAITCNT", "POSTFLG", "HALTCNT",
}

# PPU modes
PPU_MODES = {
    "Mode0": "Text backgrounds (4 tiled BG layers)",
    "Mode1": "Text + Rotation/Scaling (mixed)",
    "Mode2": "Rotation/Scaling only",
    "Mode3": "Bitmap (320x240 16-bit)",
    "Mode4": "Bitmap (240x160 8-bit palette)",
    "Mode5": "Bitmap (240x160 16-bit)",
}

# BIOS SWI functions
BIOS_SWI = {
    "SoftReset", "RegisterRamReset", "Halt", "Stop", "IntrWait",
    "VBlankIntrWait", "Div", "DivArm", "Sqrt", "ArcTan", "ArcTan2",
    "CpuSet", "CpuFastSet", "BgAffineSet", "ObjAffineSet",
    "BitFillUnf", "LZ77UnCompWram", "LZ77UnCompVram",
    "HuffUnComp", "RLUnComp", "Diff8bitUnFilter",
    "Diff16bitUnFilter", "SoundBias", "SoundGetWaveData",
    "SoundDriverInit", "SoundDriverMain", "SoundDriverVSync",
    "SoundChannelClear", "MidiKey2Freq", "SoundEffectInit",
    "SoundEffectPlay", "SoundEffectVSync", "FMID2Note",
    "FMID2Freq", "MusicPlayerOpen", "MusicPlayerStart",
    "MusicPlayerStop", "MusicPlayerFadeOut", "MusicPlayerIsPlaying",
    "MusicPlayerGetPos", "MusicPlayerSetTempo", "MusicPlayerSetVolume",
    "MusicPlayerNoteOn", "MusicPlayerNoteOff", "MusicAllKeyOff",
}

# Feature categories
FEATURE_CATEGORIES = {
    "arm_instructions": ("ARM Instructions", len(ARM_INSTRUCTIONS)),
    "thumb_instructions": ("Thumb Instructions", len(THUMB_INSTRUCTIONS)),
    "mmio_registers": ("MMIO Registers", len(MMIO_REGISTERS)),
    "ppu_modes": ("PPU Modes", len(PPU_MODES)),
    "bios_swi": ("BIOS SWI Calls", len(BIOS_SWI)),
}


@dataclass
class CoverageReport:
    """Complete coverage report for a ROM"""
    rom_name: str
    file_path: str
    
    # Feature usage
    arm_instructions_used: Set[str] = field(default_factory=set)
    thumb_instructions_used: Set[str] = field(default_factory=set)
    mmio_registers_used: Set[str] = field(default_factory=set)
    ppu_modes_used: Set[str] = field(default_factory=set)
    bios_swi_used: Set[str] = field(default_factory=set)
    
    # Memory regions accessed
    memory_regions: Set[str] = field(default_factory=set)
    
    # Statistics
    total_instructions: int = 0
    total_functions: int = 0
    code_lines: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "rom_name": self.rom_name,
            "file_path": self.file_path,
            "arm_instructions": sorted(self.arm_instructions_used),
            "thumb_instructions": sorted(self.thumb_instructions_used),
            "mmio_registers": sorted(self.mmio_registers_used),
            "ppu_modes": sorted(self.ppu_modes_used),
            "bios_swi": sorted(self.bios_swi_used),
            "memory_regions": sorted(self.memory_regions),
            "statistics": {
                "total_instructions": self.total_instructions,
                "total_functions": self.total_functions,
                "code_lines": self.code_lines,
            },
            "coverage": {
                "arm_instructions": f"{len(self.arm_instructions_used)}/{len(ARM_INSTRUCTIONS)}",
                "thumb_instructions": f"{len(self.thumb_instructions_used)}/{len(THUMB_INSTRUCTIONS)}",
                "mmio_registers": f"{len(self.mmio_registers_used)}/{len(MMIO_REGISTERS)}",
                "ppu_modes": f"{len(self.ppu_modes_used)}/{len(PPU_MODES)}",
                "bios_swi": f"{len(self.bios_swi_used)}/{len(BIOS_SWI)}",
            }
        }
    
    def format_text(self) -> str:
        """Format as human-readable text"""
        lines = [
            f"Coverage Report: {self.rom_name}",
            "=" * 50,
            f"Total instructions: {self.total_instructions}",
            f"Total functions: {self.total_functions}",
            f"Code lines: {self.code_lines}",
            "",
            "Feature Coverage:",
            f"  ARM Instructions:  {len(self.arm_instructions_used):3d}/{len(ARM_INSTRUCTIONS)}",
            f"  Thumb Instructions:{len(self.thumb_instructions_used):3d}/{len(THUMB_INSTRUCTIONS)}",
            f"  MMIO Registers:   {len(self.mmio_registers_used):3d}/{len(MMIO_REGISTERS)}",
            f"  PPU Modes:        {len(self.ppu_modes_used):3d}/{len(PPU_MODES)}",
            f"  BIOS SWI:         {len(self.bios_swi_used):3d}/{len(BIOS_SWI)}",
            "",
        ]
        
        if self.arm_instructions_used:
            lines.append(f"ARM Instructions used: {', '.join(sorted(self.arm_instructions_used))}")
        
        if self.thumb_instructions_used:
            lines.append(f"Thumb Instructions used: {', '.join(sorted(self.thumb_instructions_used))}")
        
        if self.mmio_registers_used:
            lines.append(f"MMIO Registers used: {', '.join(sorted(self.mmio_registers_used))}")
        
        if self.ppu_modes_used:
            lines.append(f"PPU Modes used: {', '.join(sorted(self.ppu_modes_used))}")
        
        if self.bios_swi_used:
            lines.append(f"BIOS SWI used: {', '.join(sorted(self.bios_swi_used))}")
        
        if self.memory_regions:
            lines.append(f"Memory regions: {', '.join(sorted(self.memory_regions))}")
        
        return "\n".join(lines)


class CoverageTracker:
    """Analyzes transpiled Python code for feature coverage"""
    
    def __init__(self):
        self.report = None
    
    def analyze_file(self, filepath: str) -> CoverageReport:
        """Analyze a transpiled Python file"""
        path = Path(filepath)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        report = CoverageReport(
            rom_name=path.stem,
            file_path=str(path.absolute()),
        )
        
        # Count code lines (non-empty, non-comment)
        code_lines = [l for l in content.split('\n') 
                      if l.strip() and not l.strip().startswith('#')]
        report.code_lines = len(code_lines)
        
        # Analyze features
        report.arm_instructions_used = self._detect_arm_instructions(content)
        report.thumb_instructions_used = self._detect_thumb_instructions(content)
        report.mmio_registers_used = self._detect_mmio_registers(content)
        report.ppu_modes_used = self._detect_ppu_modes(content)
        report.bios_swi_used = self._detect_bios_swi(content)
        report.memory_regions = self._detect_memory_regions(content)
        
        # Count instructions and functions
        report.total_functions = len(re.findall(r'^def \w+\(', content, re.MULTILINE))
        report.total_instructions = self._count_instructions(content)
        
        self.report = report
        return report
    
    def _detect_arm_instructions(self, content: str) -> Set[str]:
        """Detect ARM instructions used"""
        instructions = set()
        
        # Pattern to match instruction functions like "def instr_0xE3A00004()"
        # These are generated for each unique ARM instruction encountered
        for instr in ARM_INSTRUCTIONS:
            if re.search(rf'\b{instr}\b', content, re.IGNORECASE):
                instructions.add(instr)
        
        # Also check for func_map entries which indicate actual used instructions
        # func_map entries look like: 0x08000000: instr_0xE3A00004,
        func_map_pattern = r'0x[0-9A-Fa-f]+:\s*instr_0x([0-9A-Fa-f]+)'
        matches = re.findall(func_map_pattern, content)
        
        for opcode_hex in matches:
            # Extract instruction name from opcode (first 4 bits = condition, next 4 = opcode class)
            # This is a simplification - we'd need proper disassembly for exact match
            pass
        
        return instructions
    
    def _detect_thumb_instructions(self, content: str) -> Set[str]:
        """Detect Thumb instructions used"""
        instructions = set()
        
        for instr in THUMB_INSTRUCTIONS:
            if re.search(rf'\b{instr}\b', content, re.IGNORECASE):
                instructions.add(instr)
        
        return instructions
    
    def _detect_mmio_registers(self, content: str) -> Set[str]:
        """Detect MMIO registers accessed"""
        registers = set()
        
        # Check for MMIO register constants
        for reg in MMIO_REGISTERS:
            if re.search(rf'\b{reg}\b', content):
                registers.add(reg)
        
        # Check for MMIO addresses accessed
        # Patterns like: memory.write_32(0x04000000, or memory.read_16(0x04000004
        addr_pattern = r'(?:read|write)_\d+\(0x(04[0-9A-Fa-f]+)'
        addr_matches = re.findall(addr_pattern, content)
        
        addr_to_reg = {
            "04000000": "DISPCNT", "04000002": "GREENSWAP", "04000004": "DISPSTAT",
            "04000006": "VCOUNT", "04000008": "BG0CNT", "0400000A": "BG1CNT",
            "0400000C": "BG2CNT", "0400000E": "BG3CNT", "04000020": "BG2PA",
            "04000030": "BG3PA", "04000040": "WIN0H", "04000042": "WIN1H",
            "04000044": "WIN0V", "04000046": "WIN1V", "04000048": "WININ",
            "0400004A": "WINOUT", "0400004C": "MOSAIC", "04000050": "BLDCNT",
            "04000052": "BLDALPHA", "04000054": "BLDY",
            "04000060": "SOUND1CNT_L", "04000068": "SOUND2CNT_L",
            "04000070": "SOUND3CNT_L", "04000078": "SOUND4CNT_L",
            "04000080": "SOUNDCNT_L", "04000082": "SOUNDCNT_H", "04000084": "SOUNDCNT_X",
            "040000A0": "FIFO_A", "040000A4": "FIFO_B",
            "040000B0": "DMA0SAD", "040000B4": "DMA0DAD", "040000B8": "DMA0CNT_L",
            "040000BC": "DMA1SAD", "040000C0": "DMA1DAD", "040000C4": "DMA1CNT_L",
            "040000C8": "DMA2SAD", "040000CC": "DMA2DAD", "040000D0": "DMA2CNT_L",
            "040000D4": "DMA3SAD", "040000D8": "DMA3DAD", "040000DC": "DMA3CNT_L",
            "04000100": "TM0CNT_L", "04000104": "TM1CNT_L",
            "04000108": "TM2CNT_L", "0400010C": "TM3CNT_L",
            "04000120": "SIODATA32", "04000128": "SIOCNT",
            "04000130": "KEYINPUT", "04000132": "KEYCNT",
            "04000200": "IE", "04000202": "IF", "04000204": "WAITCNT",
            "04000208": "IME",
            "04000300": "POSTFLG", "04000301": "HALTCNT",
        }
        
        for addr in addr_matches:
            addr_upper = addr.upper()
            if addr_upper in addr_to_reg:
                registers.add(addr_to_reg[addr_upper])
        
        return registers
    
    def _detect_ppu_modes(self, content: str) -> Set[str]:
        """Detect PPU modes used"""
        modes = set()
        
        # Check for mode detection in the code
        mode_patterns = {
            "Mode0": r'display_mode\s*==\s*0|Mode\s*0|render_mode0',
            "Mode1": r'display_mode\s*==\s*1|Mode\s*1|render_mode1',
            "Mode2": r'display_mode\s*==\s*2|Mode\s*2|render_mode2',
            "Mode3": r'display_mode\s*==\s*3|Mode\s*3|render_mode3_bitmap|_render_mode3',
            "Mode4": r'display_mode\s*==\s*4|Mode\s*4|render_mode4_bitmap|_render_mode4',
            "Mode5": r'display_mode\s*==\s*5|Mode\s*5|render_mode5',
        }
        
        for mode, pattern in mode_patterns.items():
            if re.search(pattern, content, re.IGNORECASE):
                modes.add(mode)
        
        return modes
    
    def _detect_bios_swi(self, content: str) -> Set[str]:
        """Detect BIOS SWI calls used"""
        swi_calls = set()
        
        # Check for SWI handler calls
        for swi in BIOS_SWI:
            if re.search(rf'\b{swi}\b', content, re.IGNORECASE):
                swi_calls.add(swi)
        
        # Also check for SWI number handling (e.g., 0x01, 0x02, etc.)
        swi_pattern = r'SWI\s*(?:0x)?(\d+)'
        swi_matches = re.findall(swi_pattern, content)
        
        # Common SWI numbers
        swi_num_to_name = {
            "0": "SoftReset", "1": "RegisterRamReset", "2": "Halt",
            "3": "Stop", "4": "IntrWait", "5": "VBlankIntrWait",
            "6": "Div", "7": "DivArm", "8": "Sqrt",
            "9": "ArcTan", "10": "ArcTan2", "11": "CpuSet",
            "12": "CpuFastSet", "13": "BgAffineSet", "14": "ObjAffineSet",
        }
        
        for num in swi_matches:
            if num in swi_num_to_name:
                swi_calls.add(swi_num_to_name[num])
        
        return swi_calls
    
    def _detect_memory_regions(self, content: str) -> Set[str]:
        """Detect memory regions accessed"""
        regions = set()
        
        memory_patterns = {
            "BIOS": r'0x0{5}[0-9A-Fa-f]+|bios\b',
            "EWRAM": r'0x02[0-9A-Fa-f]+|ewram\b',
            "IWRAM": r'0x03[0-9A-Fa-f]+|iwram\b',
            "VRAM": r'0x06[0-9A-Fa-f]+|vram\b',
            "Palette": r'0x05[0-9A-Fa-f]+|palette\b',
            "OAM": r'0x07[0-9A-Fa-f]+|oam\b',
            "ROM": r'0x08[0-9A-Fa-f]+|ROM_DATA|rom_data',
            "MMIO": r'0x04[0-9A-Fa-f]+|mmio\b',
        }
        
        for region, pattern in memory_patterns.items():
            if re.search(pattern, content, re.IGNORECASE):
                regions.add(region)
        
        return regions
    
    def _count_instructions(self, content: str) -> int:
        """Count the number of instructions (function definitions in func_map)"""
        # func_map contains entries for each instruction address
        func_map_count = len(re.findall(r'0x[0-9A-Fa-f]+:\s*\w+,', content))
        return func_map_count


def analyze_rom(py_path: str, output_json: Optional[str] = None) -> CoverageReport:
    """Analyze a single ROM and return coverage report"""
    tracker = CoverageTracker()
    report = tracker.analyze_file(py_path)
    
    if output_json:
        with open(output_json, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"JSON report saved to {output_json}")
    
    return report


def analyze_roms_dir(roms_dir: str, output_dir: Optional[str] = None) -> List[CoverageReport]:
    """Analyze all transpiled ROMs in a directory"""
    roms_dir = Path(roms_dir)
    
    if not roms_dir.exists():
        raise FileNotFoundError(f"Directory not found: {roms_dir}")
    
    # Find all .py files that look like transpiled ROMs
    py_files = list(roms_dir.glob("*.py"))
    
    reports = []
    for py_file in sorted(py_files):
        print(f"Analyzing {py_file.name}...")
        try:
            output_json = None
            if output_dir:
                output_json = str(Path(output_dir) / f"{py_file.stem}_coverage.json")
            
            report = analyze_rom(str(py_file), output_json)
            reports.append(report)
            print(f"  -> {len(report.arm_instructions_used)} ARM, "
                  f"{len(report.thumb_instructions_used)} Thumb, "
                  f"{len(report.mmio_registers_used)} MMIO")
        except Exception as e:
            print(f"  -> ERROR: {e}")
    
    return reports


def generate_summary_report(reports: List[CoverageReport]) -> str:
    """Generate a summary report across all ROMs"""
    # Aggregate features
    all_arm = set()
    all_thumb = set()
    all_mmio = set()
    all_ppu = set()
    all_swi = set()
    
    for r in reports:
        all_arm.update(r.arm_instructions_used)
        all_thumb.update(r.thumb_instructions_used)
        all_mmio.update(r.mmio_registers_used)
        all_ppu.update(r.ppu_modes_used)
        all_swi.update(r.bios_swi_used)
    
    lines = [
        "=" * 60,
        "GBAtoPy Feature Coverage Summary",
        "=" * 60,
        f"Total ROMs analyzed: {len(reports)}",
        "",
        "Cumulative feature usage:",
        f"  ARM Instructions:  {len(all_arm):3d}/{len(ARM_INSTRUCTIONS)} ({100*len(all_arm)//len(ARM_INSTRUCTIONS)}%)",
        f"  Thumb Instructions:{len(all_thumb):3d}/{len(THUMB_INSTRUCTIONS)} ({100*len(all_thumb)//len(THUMB_INSTRUCTIONS)}%)",
        f"  MMIO Registers:   {len(all_mmio):3d}/{len(MMIO_REGISTERS)} ({100*len(all_mmio)//len(MMIO_REGISTERS)}%)",
        f"  PPU Modes:        {len(all_ppu):3d}/{len(PPU_MODES)} ({100*len(all_ppu)//len(PPU_MODES)}%)",
        f"  BIOS SWI:         {len(all_swi):3d}/{len(BIOS_SWI)} ({100*len(all_swi)//len(BIOS_SWI)}%)",
        "",
    ]
    
    if all_arm:
        lines.append(f"ARM instructions used: {', '.join(sorted(all_arm))}")
    if all_thumb:
        lines.append(f"Thumb instructions used: {', '.join(sorted(all_thumb))}")
    if all_mmio:
        lines.append(f"MMIO registers used: {', '.join(sorted(all_mmio))}")
    if all_ppu:
        lines.append(f"PPU modes used: {', '.join(sorted(all_ppu))}")
    if all_swi:
        lines.append(f"BIOS SWI used: {', '.join(sorted(all_swi))}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='GBAtoPy Feature Coverage Tracker'
    )
    parser.add_argument(
        "rom",
        nargs="?",
        help="Path to transpiled Python ROM file"
    )
    parser.add_argument(
        "--roms-dir",
        help="Analyze all .py files in directory"
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for JSON reports"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Generate summary report for multiple ROMs"
    )
    parser.add_argument(
        "--json",
        help="Output JSON report to file"
    )
    
    args = parser.parse_args()
    
    if args.roms_dir:
        reports = analyze_roms_dir(args.roms_dir, args.output_dir)
        
        if args.summary and reports:
            print("\n" + generate_summary_report(reports))
        
        # Save summary JSON
        if args.output_dir:
            summary = {
                "total_roms": len(reports),
                "cumulative_features": {
                    "arm_instructions": list(sorted(set().union(*[r.arm_instructions_used for r in reports]))),
                    "thumb_instructions": list(sorted(set().union(*[r.thumb_instructions_used for r in reports]))),
                    "mmio_registers": list(sorted(set().union(*[r.mmio_registers_used for r in reports]))),
                    "ppu_modes": list(sorted(set().union(*[r.ppu_modes_used for r in reports]))),
                    "bios_swi": list(sorted(set().union(*[r.bios_swi_used for r in reports]))),
                },
                "roms": [r.to_dict() for r in reports],
            }
            summary_path = Path(args.output_dir) / "summary.json"
            with open(summary_path, 'w') as f:
                json.dump(summary, f, indent=2)
            print(f"\nSummary saved to {summary_path}")
        
        return 0
    
    if not args.rom:
        parser.error("ROM path or --roms-dir required")
    
    # Single ROM analysis
    report = analyze_rom(args.rom, args.json)
    print("\n" + report.format_text())
    
    return 0


if __name__ == '__main__':
    sys.exit(main())