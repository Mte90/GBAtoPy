#!/usr/bin/env python3
"""Compare two WAV files and report audio similarity metrics."""

import argparse
import wave
import struct
import math
import sys


def load_wav(path):
    """Load a WAV file and return (framerate, num_channels, samples) where samples is a list of mono values."""
    try:
        with wave.open(path, 'rb') as w:
            framerate = w.getframerate()
            num_channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            
            if sampwidth != 2:
                print(f"Error: {path} is not 16-bit audio", file=sys.stderr)
                sys.exit(1)
            
            raw = w.readframes(w.getnframes())
            
            if len(raw) == 0:
                print(f"Error: {path} is empty", file=sys.stderr)
                sys.exit(1)
            
            num_samples = len(raw) // 2 // num_channels
            samples = []
            
            for i in range(num_samples):
                offset = i * 2 * num_channels
                left = struct.unpack('<h', raw[offset:offset+2])[0]
                if num_channels == 2:
                    right = struct.unpack('<h', raw[offset+2:offset+4])[0]
                    mono = (left + right) // 2
                else:
                    mono = left
                samples.append(mono + 32768)
            
            return framerate, num_channels, samples
    
    except FileNotFoundError:
        print(f"Error: Cannot open file {path}", file=sys.stderr)
        sys.exit(1)
    except wave.Error as e:
        print(f"Error: Cannot open WAV file {path}: {e}", file=sys.stderr)
        sys.exit(1)


def compute_metrics(golden_samples, transpiled_samples):
    """Compute audio similarity metrics. Returns dict with all metrics."""
    min_len = min(len(golden_samples), len(transpiled_samples))
    
    if min_len == 0:
        print("Error: Both files are empty", file=sys.stderr)
        sys.exit(1)
    
    golden_overlap = golden_samples[:min_len]
    transpiled_overlap = transpiled_samples[:min_len]
    
    mean_diff = sum(abs(g - t) for g, t in zip(golden_overlap, transpiled_overlap)) / min_len
    
    rms_diff = math.sqrt(sum((g - t) ** 2 for g, t in zip(golden_overlap, transpiled_overlap)) / min_len)
    
    golden_norm = math.sqrt(sum(g ** 2 for g in golden_overlap))
    transpiled_norm = math.sqrt(sum(t ** 2 for t in transpiled_overlap))
    
    if golden_norm > 0 and transpiled_norm > 0:
        correlation = sum(g * t for g, t in zip(golden_overlap, transpiled_overlap)) / (golden_norm * transpiled_norm)
    else:
        correlation = 0.0
    
    golden_content = sum(1 for g in golden_samples if g != 0) / len(golden_samples) * 100
    transpiled_content = sum(1 for t in transpiled_samples if t != 0) / len(transpiled_samples) * 100
    
    diff_percentage = (mean_diff / 65535) * 100
    
    return {
        'mean_diff': mean_diff,
        'rms_diff': rms_diff,
        'correlation': correlation,
        'diff_percentage': diff_percentage,
        'golden_content': golden_content,
        'transpiled_content': transpiled_content,
        'golden_samples': len(golden_samples),
        'transpiled_samples': len(transpiled_samples),
        'compared_samples': min_len
    }


def main():
    parser = argparse.ArgumentParser(description='Compare two WAV audio files and report similarity')
    parser.add_argument('golden', help='Reference audio file from mGBA')
    parser.add_argument('transpiled', help='Audio file from transpiled Python')
    parser.add_argument('--threshold', type=float, default=30.0, help='Max allowed difference percentage (default: 30.0)')
    parser.add_argument('--frame', type=int, default=60, help='Frame count used for capture (default: 60)')
    
    args = parser.parse_args()
    
    golden_fr, golden_ch, golden_samples = load_wav(args.golden)
    transpiled_fr, transpiled_ch, transpiled_samples = load_wav(args.transpiled)
    
    metrics = compute_metrics(golden_samples, transpiled_samples)
    
    both_silent = metrics['golden_content'] == 0 and metrics['transpiled_content'] == 0
    
    print('=' * 40)
    print(f"Golden:      {args.golden}")
    print(f"Transpiled:  {args.transpiled}")
    print(f"Frame:       {args.frame}")
    print(f"Golden samples:      {metrics['golden_samples']}")
    print(f"Transpiled samples:  {metrics['transpiled_samples']}")
    print(f"Compared samples:    {metrics['compared_samples']}")
    print(f"Mean diff:   {metrics['mean_diff']:.2f}")
    print(f"RMS diff:    {metrics['rms_diff']:.2f}")
    print(f"Correlation: {metrics['correlation']:.4f}")
    print(f"Difference:  {metrics['diff_percentage']:.2f}%")
    print(f"Golden content:      {metrics['golden_content']:.1f}%")
    print(f"Transpiled content:  {metrics['transpiled_content']:.1f}%")
    
    if both_silent:
        print("Status:      SKIP (both silent)")
        print()
        print('=' * 40)
        print(f"SKIP: {args.golden.split('/')[-1]} (both files silent)")
        print('=' * 40)
        sys.exit(0)
    
    passed = metrics['diff_percentage'] < args.threshold
    status = "PASS" if passed else "FAIL"
    print(f"Status:      {status}")
    print()
    print('=' * 40)
    
    if passed:
        print(f"PASS: {args.golden.split('/')[-1]} ({metrics['diff_percentage']:.2f}% difference, threshold {args.threshold}%)")
        print('=' * 40)
        sys.exit(0)
    else:
        print(f"FAIL: {args.golden.split('/')[-1]} ({metrics['diff_percentage']:.2f}% difference exceeds threshold {args.threshold}%)")
        print('=' * 40)
        sys.exit(1)


if __name__ == '__main__':
    main()