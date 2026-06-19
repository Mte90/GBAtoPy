#!/usr/bin/env python3
"""
Feature Detection Script
Analyzes generated Python code to detect which GBA features are actually used.
"""

import re
import argparse
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List


@dataclass
class FeatureUsage:
    rom_name: str
    audio: bool
    irq: bool
    rtc: bool
    timer: bool
    dma: bool
    sprite: bool
    affine_bg: bool
    bitmap_mode: bool
    sram: bool
    total_lines: int
    feature_lines: int
    savings_estimate: float
    
    def to_dict(self) -> Dict:
        return asdict(self)


def detect_features(py_file: str) -> FeatureUsage:
    with open(py_file, 'r') as f:
        content = f.read()
        lines = content.split('\n')
    
    total_lines = len(lines)
    feature_lines = 0
    
    # Feature patterns
    patterns = {
        'audio': [
            r'apu\s*=', r'audio', r'SquareWaveChannel', r'WaveChannel', 
            r'NoiseChannel', r'get_sample', r'mixer', r'sound'
        ],
        'irq': [
            r'IE\s*=', r'IF\s*=', r'IME\s*=', r'interrupt', r'IRQ',
            r'VBlank', r'HBlank', r'VCount', r'check_irq', r'handle_irq'
        ],
        'rtc': [
            r'rtc', r'SPI', r'RTC', r'0x04000138'  # RTC data port
        ],
        'timer': [
            r'TM0CNT', r'TM1CNT', r'TM2CNT', r'TM3CNT', r'timer',
            r'timer_0', r'timer_1', r'timer_2', r'timer_3'
        ],
        'dma': [
            r'DMA0CNT', r'DMA1CNT', r'DMA2CNT', r'DMA3CNT', r'dma_',
            r'dma_transfer', r'DMA_START'
        ],
        'sprite': [
            r'OAM', r'sprite', r'OBJ', r'obj_', r'sprite_update'
        ],
        'affine_bg': [
            r'BG2CNT.*0x02', r'BG3CNT', r'affine', r'pa\s*=', r'pb\s*=',
            r'pc\s*=', r'pd\s*=', r'BG_AFFINE'
        ],
        'bitmap_mode': [
            r'Mode\s*[345]', r'bitmap', r'vram_bitmap', r'DISPCNT.*0x04'
        ],
        'sram': [
            r'sram', r'SRAM', r'0x08000000.*save', r'save_state',
            r'load_state'
        ]
    }
    
    features_used = {k: False for k in patterns}
    
    for line in lines:
        # Skip comments and strings for more accurate detection
        line_clean = re.sub(r'#.*$', '', line)
        
        for feature, pattern_list in patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, line_clean, re.IGNORECASE):
                    if not features_used[feature]:
                        features_used[feature] = True
                        feature_lines += 1
                    break
    
    # Estimate savings (rough estimate: 20-30% per unused feature)
    unused_count = sum(1 for v in features_used.values() if not v)
    savings_estimate = unused_count * 0.025  # ~2.5% per feature
    
    rom_name = Path(py_file).stem
    
    return FeatureUsage(
        rom_name=rom_name,
        **features_used,
        total_lines=total_lines,
        feature_lines=feature_lines,
        savings_estimate=round(savings_estimate, 2)
    )


def analyze_rom(rom_path: str) -> FeatureUsage:
    py_path = rom_path.replace('.gba', '.py')
    if not Path(py_path).exists():
        print(f"  Python file not found: {py_path}")
        return None
    
    print(f"Analyzing: {Path(rom_path).name}")
    result = detect_features(py_path)
    
    print(f"  Features used:")
    for feature, used in vars(result).items():
        if feature in ['rom_name', 'total_lines', 'feature_lines', 'savings_estimate']:
            continue
        if used:
            print(f"    ✓ {feature}")
    
    print(f"  Potential savings: {result.savings_estimate*100:.1f}%")
    return result


def main():
    parser = argparse.ArgumentParser(description="Detect GBA features in generated Python")
    parser.add_argument("--rom", type=str, help="Single ROM path")
    parser.add_argument("--roms-dir", type=str, default="test_roms/roms",
                       help="Directory containing ROMs")
    parser.add_argument("--output", type=str, default="feature_analysis.json",
                       help="Output JSON file")
    
    args = parser.parse_args()
    
    results = []
    
    if args.rom:
        result = analyze_rom(args.rom)
        if result:
            results.append(result)
    else:
        rom_files = list(Path(args.roms_dir).glob("*.gba"))
        print(f"Analyzing {len(rom_files)} ROMs...")
        
        for rom_path in rom_files:
            result = analyze_rom(str(rom_path))
            if result:
                results.append(result)
    
    # Save results
    data = {
        'timestamp': __import__('time').strftime("%Y-%m-%d %H:%M:%S"),
        'total_roms': len(results),
        'results': [r.to_dict() for r in results]
    }
    
    with open(args.output, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\nResults saved to: {args.output}")
    
    # Summary
    if results:
        print(f"\n{'='*70}")
        print("FEATURE USAGE SUMMARY")
        print(f"{'='*70}")
        
        feature_counts = {}
        for r in results:
            for k, v in vars(r).items():
                if k not in ['rom_name', 'total_lines', 'feature_lines', 'savings_estimate']:
                    feature_counts[k] = feature_counts.get(k, 0) + (1 if v else 0)
        
        print("\nFeature usage across all ROMs:")
        for feature, count in sorted(feature_counts.items(), key=lambda x: -x[1]):
            pct = count / len(results) * 100
            print(f"  {feature:15} {count:3}/{len(results)} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
