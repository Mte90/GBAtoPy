#!/usr/bin/env python3
"""
Compare two WAV files and report audio similarity metrics.

Supports both 8-bit and 16-bit WAV files. Optionally uses FFT for
spectral comparison. Mirrors the content detection pattern from
compare_screenshots.py to avoid false positives on silent files.

Usage:
    python3 compare_audio.py golden.wav transpiled.wav [--threshold N] [--spectral]
"""

import argparse
import wave
import struct
import math
import sys
from pathlib import Path
from typing import Tuple, Optional

import numpy as np


def load_wav(path: Path) -> Tuple[int, int, np.ndarray]:
    """
    Load a WAV file and return (framerate, num_channels, samples).
    
    Supports both 8-bit unsigned and 16-bit signed WAV files.
    Normalizes all samples to float64 in range [-1.0, 1.0].
    
    Returns:
        Tuple of (framerate, num_channels, mono_samples as numpy array)
    """
    path = Path(path)
    if not path.exists():
        print(f"Error: Cannot open file {path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        with wave.open(str(path), 'rb') as w:
            framerate = w.getframerate()
            num_channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            num_frames = w.getnframes()
            
            if num_frames == 0:
                print(f"Error: {path} is empty", file=sys.stderr)
                sys.exit(1)
            
            raw = w.readframes(num_frames)
            
            # Parse samples based on bit depth
            if sampwidth == 1:
                # 8-bit unsigned: range [0, 255], center at 128
                samples = np.frombuffer(raw, dtype=np.uint8)
                samples = samples.astype(np.float64) - 128.0
                # Normalize to [-1.0, 1.0]
                samples = samples / 128.0
            elif sampwidth == 2:
                # 16-bit signed: range [-32768, 32767]
                samples = np.frombuffer(raw, dtype=np.int16)
                samples = samples.astype(np.float64) / 32768.0
            else:
                print(f"Error: {path} has unsupported bit depth ({sampwidth} bytes)", file=sys.stderr)
                sys.exit(1)
            
            # Mix stereo to mono if needed
            if num_channels == 2:
                samples = samples.reshape(-1, 2)
                mono = (samples[:, 0] + samples[:, 1]) / 2.0
            elif num_channels == 1:
                mono = samples
            else:
                # For >2 channels, average all
                samples = samples.reshape(-1, num_channels)
                mono = np.mean(samples, axis=1)
            
            return framerate, num_channels, mono
    
    except wave.Error as e:
        print(f"Error: Cannot open WAV file {path}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to read {path}: {e}", file=sys.stderr)
        sys.exit(1)


def compute_metrics(
    golden_samples: np.ndarray,
    transpiled_samples: np.ndarray,
    use_spectral: bool = False
) -> dict:
    """
    Compute audio similarity metrics.
    
    Args:
        golden_samples: Reference audio as float64 array in [-1.0, 1.0]
        transpiled_samples: Transpiled audio as float64 array in [-1.0, 1.0]
        use_spectral: If True, compute FFT-based spectral comparison
    
    Returns:
        Dict with all metrics including time-domain and optionally spectral data
    """
    min_len = min(len(golden_samples), len(transpiled_samples))
    
    if min_len == 0:
        print("Error: Both files are empty", file=sys.stderr)
        sys.exit(1)
    
    golden_overlap = golden_samples[:min_len]
    transpiled_overlap = transpiled_samples[:min_len]
    
    # Time-domain metrics
    diff = np.abs(golden_overlap - transpiled_overlap)
    mean_diff = float(np.mean(diff))
    rms_diff = float(np.sqrt(np.mean((golden_overlap - transpiled_overlap) ** 2)))
    
    # Correlation
    golden_norm = np.linalg.norm(golden_overlap)
    transpiled_norm = np.linalg.norm(transpiled_overlap)
    
    if golden_norm > 1e-10 and transpiled_norm > 1e-10:
        correlation = float(np.dot(golden_overlap, transpiled_overlap) / (golden_norm * transpiled_norm))
    else:
        correlation = 0.0
    
    # Content detection (mirrors compare_screenshots.py pattern)
    # Count samples with significant amplitude (above noise floor)
    NOISE_FLOOR = 1e-4  # Samples below this are considered silence
    golden_content = float(np.sum(np.abs(golden_samples) > NOISE_FLOOR) / len(golden_samples) * 100)
    transpiled_content = float(np.sum(np.abs(transpiled_samples) > NOISE_FLOOR) / len(transpiled_samples) * 100)
    
    # Normalize diff to percentage (max diff is 2.0 for range [-1, 1])
    diff_percentage = (mean_diff / 2.0) * 100
    
    metrics = {
        'mean_diff': mean_diff,
        'rms_diff': rms_diff,
        'correlation': correlation,
        'diff_percentage': diff_percentage,
        'golden_content': golden_content,
        'transpiled_content': transpiled_content,
        'golden_samples': len(golden_samples),
        'transpiled_samples': len(transpiled_samples),
        'compared_samples': min_len,
    }
    
    # Spectral comparison if requested
    if use_spectral:
        # Compute FFT of both signals
        golden_fft = np.fft.rfft(golden_overlap)
        transpiled_fft = np.fft.rfft(transpiled_overlap)
        
        # Get magnitude spectra
        golden_mag = np.abs(golden_fft)
        transpiled_mag = np.abs(transpiled_fft)
        
        # Compute spectral correlation
        golden_mag_norm = np.linalg.norm(golden_mag)
        transpiled_mag_norm = np.linalg.norm(transpiled_mag)
        
        if golden_mag_norm > 1e-10 and transpiled_mag_norm > 1e-10:
            spectral_correlation = float(
                np.dot(golden_mag, transpiled_mag) / (golden_mag_norm * transpiled_mag_norm)
            )
        else:
            spectral_correlation = 0.0
        
        # Spectral difference (mean absolute difference in magnitude)
        spectral_diff = float(np.mean(np.abs(golden_mag - transpiled_mag)))
        
        metrics['spectral_correlation'] = spectral_correlation
        metrics['spectral_diff'] = spectral_diff
        metrics['num_fft_bins'] = len(golden_mag)
    
    return metrics


def main():
    parser = argparse.ArgumentParser(
        description='Compare two WAV audio files and report similarity',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 compare_audio.py golden.wav transpiled.wav
  python3 compare_audio.py golden.wav transpiled.wav --spectral
  python3 compare_audio.py golden.wav transpiled.wav --threshold 20.0

Exit codes:
  0 - PASS or SKIP (both silent)
  1 - FAIL or error
"""
    )
    parser.add_argument('golden', type=Path, help='Reference audio file from mGBA')
    parser.add_argument('transpiled', type=Path, help='Audio file from transpiled Python')
    parser.add_argument('--threshold', type=float, default=30.0,
                        help='Max allowed difference percentage (default: 30.0)')
    parser.add_argument('--frame', type=int, default=60, help='Frame count used for capture (default: 60)')
    parser.add_argument('--spectral', action='store_true',
                        help='Enable FFT-based spectral comparison')
    
    args = parser.parse_args()
    
    # Load both WAV files (handles 8-bit and 16-bit)
    golden_fr, golden_ch, golden_samples = load_wav(args.golden)
    transpiled_fr, transpiled_ch, transpiled_samples = load_wav(args.transpiled)
    
    # Report format mismatch warning
    if golden_fr != transpiled_fr or golden_ch != transpiled_ch:
        print(f"Warning: Sample rate or channel mismatch ({golden_fr}Hz/{golden_ch}ch vs {transpiled_fr}Hz/{transpiled_ch}ch)")
    
    metrics = compute_metrics(golden_samples, transpiled_samples, use_spectral=args.spectral)
    
    # Content detection - both silent is SKIP, not PASS
    MIN_CONTENT_PCT = 0.1  # At least 0.1% of samples must have significant amplitude
    both_silent = (metrics['golden_content'] < MIN_CONTENT_PCT and 
                   metrics['transpiled_content'] < MIN_CONTENT_PCT)
    
    print('=' * 50)
    print("AUDIO COMPARISON RESULTS")
    print('=' * 50)
    print(f"Golden:       {args.golden}")
    print(f"Transpiled:   {args.transpiled}")
    print(f"Frame:        {args.frame}")
    print(f"Golden rate:  {golden_fr}Hz, {golden_ch}ch")
    print(f"Transpiled:   {transpiled_fr}Hz, {transpiled_ch}ch")
    print('-' * 50)
    print(f"Golden samples:       {metrics['golden_samples']}")
    print(f"Transpiled samples:   {metrics['transpiled_samples']}")
    print(f"Compared samples:     {metrics['compared_samples']}")
    print('-' * 50)
    print(f"Mean diff:    {metrics['mean_diff']:.6f}")
    print(f"RMS diff:     {metrics['rms_diff']:.6f}")
    print(f"Correlation:  {metrics['correlation']:.4f}")
    print(f"Difference:   {metrics['diff_percentage']:.2f}%")
    print('-' * 50)
    print(f"Golden content:       {metrics['golden_content']:.2f}%")
    print(f"Transpiled content:   {metrics['transpiled_content']:.2f}%")
    
    # Report spectral metrics if enabled
    if args.spectral and 'spectral_correlation' in metrics:
        print('-' * 50)
        print(f"Spectral correlation: {metrics['spectral_correlation']:.4f}")
        print(f"Spectral diff:        {metrics['spectral_diff']:.6f}")
        print(f"FFT bins:             {metrics['num_fft_bins']}")
    
    # Determine status
    if both_silent:
        print('-' * 50)
        print("Status:       SKIP (both files silent)")
        print('=' * 50)
        print(f"SKIP: {args.golden.name} (both files silent, cannot verify)")
        print('=' * 50)
        sys.exit(0)
    
    passed = metrics['diff_percentage'] < args.threshold
    status = "PASS" if passed else "FAIL"
    
    print('-' * 50)
    print(f"Threshold:    {args.threshold}%")
    print(f"Status:       {status}")
    print('=' * 50)
    
    if passed:
        print(f"PASS: {args.golden.name} ({metrics['diff_percentage']:.2f}% < {args.threshold}%)")
        print('=' * 50)
        sys.exit(0)
    else:
        print(f"FAIL: {args.golden.name} ({metrics['diff_percentage']:.2f}% >= {args.threshold}%)")
        print('=' * 50)
        sys.exit(1)


if __name__ == '__main__':
    main()