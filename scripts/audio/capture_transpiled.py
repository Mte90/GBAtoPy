#!/usr/bin/env python3
"""
Capture audio from a transpiled GBA ROM Python file and write to WAV.

This script imports a transpiled ROM module, captures audio samples from
its APU instance, and writes them to a 16-bit stereo WAV file at 44100Hz.

Usage:
    python3 capture_transpiled.py <transpiled.py> <output.wav> [--frames N]

The transpiled ROM must have a global `apu_instance` (or `apu`) of type APU
from gba_runtime.apu. The script will:
1. Import the transpiled module
2. Access its APU instance
3. Call _generate_samples() in a loop for N frames
4. Write accumulated samples to WAV as 16-bit stereo 44100Hz

Example:
    python3 capture_transpiled.py /tmp/stripes.py /tmp/stripes_audio.wav --frames 300
"""

import argparse
import wave
import struct
import sys
import os
import importlib.util
from pathlib import Path
from typing import Optional


# Audio parameters
SAMPLE_RATE = 44100
FRAMES_PER_SECOND = 59.73  # GBA frame rate (approx 60)
SAMPLES_PER_FRAME = int(SAMPLE_RATE / FRAMES_PER_SECOND)  # ~738 samples per frame


def load_transpiled_module(path: Path):
    """
    Load a transpiled ROM module from a Python file.
    
    Args:
        path: Path to the transpiled Python file
        
    Returns:
        Imported module object
        
    Raises:
        SystemExit on any error
    """
    path = Path(path)
    if not path.exists():
        print(f"Error: Transpiled file not found: {path}", file=sys.stderr)
        sys.exit(1)
    
    if not path.suffix == '.py':
        print(f"Error: Expected .py file, got: {path.suffix}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Load module from file
        spec = importlib.util.spec_from_file_location("transpiled_rom", path)
        if spec is None or spec.loader is None:
            print(f"Error: Cannot load module spec from {path}", file=sys.stderr)
            sys.exit(1)
        
        module = importlib.util.module_from_spec(spec)
        sys.modules["transpiled_rom"] = module
        spec.loader.exec_module(module)
        
        return module
    
    except Exception as e:
        print(f"Error: Failed to load transpiled module: {e}", file=sys.stderr)
        sys.exit(1)


def validate_module(module) -> object:
    """
    Validate that the transpiled module has the required APU instance.
    
    Args:
        module: Imported transpiled ROM module
        
    Returns:
        APU instance from the module
        
    Raises:
        SystemExit if validation fails
    """
    # Check for APU instance — codegen uses 'apu_instance' as the global name
    apu = getattr(module, 'apu_instance', None) or getattr(module, 'apu', None)
    if apu is None:
        print("Error: Transpiled module has no 'apu_instance' or 'apu' attribute", file=sys.stderr)
        print("Hint: The transpiled ROM must expose a global APU instance", file=sys.stderr)
        sys.exit(1)
    
    # Validate APU has required methods
    if not hasattr(apu, '_generate_samples'):
        print("Error: APU instance has no '_generate_samples' method", file=sys.stderr)
        sys.exit(1)
    
    if not hasattr(apu, 'SAMPLE_RATE'):
        print("Warning: APU has no SAMPLE_RATE attribute, using default 44100Hz", file=sys.stderr)
    
    return apu


def capture_audio(
    apu: object,
    num_frames: int,
    samples_per_frame: int = SAMPLES_PER_FRAME
) -> bytes:
    """
    Capture audio samples from APU for a specified number of frames.
    
    Args:
        apu: APU instance with _generate_samples() method
        num_frames: Number of frames to capture
        samples_per_frame: Samples per frame (default: ~738 at 44100Hz)
        
    Returns:
        Raw audio bytes (stereo 8-bit unsigned)
    """
    print(f"Capturing {num_frames} frames ({num_frames * samples_per_frame} samples)...")
    
    all_samples = bytearray()
    
    for frame in range(num_frames):
        # Generate samples for this frame
        # _generate_samples() returns bytes (8-bit unsigned stereo per apu.py)
        samples = apu._generate_samples(samples_per_frame)
        
        if not samples:
            print(f"Warning: Frame {frame} returned empty samples", file=sys.stderr)
            continue
        
        all_samples.extend(samples)
        
        # Progress indicator every 50 frames
        if (frame + 1) % 50 == 0:
            print(f"  Frame {frame + 1}/{num_frames} captured")
    
    print(f"Captured {len(all_samples)} bytes of audio data")
    return bytes(all_samples)


def write_wav(path: Path, raw_samples: bytes, framerate: int = SAMPLE_RATE):
    """
    Write raw audio samples to a 16-bit stereo WAV file.
    
    Args:
        path: Output WAV file path
        raw_samples: Raw 8-bit unsigned stereo samples
        framerate: Sample rate (default: 44100Hz)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert 8-bit unsigned to 16-bit signed
    # 8-bit unsigned: [0, 255] -> 16-bit signed: [-32768, 32767]
    num_samples = len(raw_samples) // 2  # Stereo = 2 bytes per sample
    
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(framerate)
        
        # Convert and write samples
        for i in range(num_samples):
            offset = i * 2
            left_8bit = raw_samples[offset]
            right_8bit = raw_samples[offset + 1]
            
            # Convert to 16-bit signed
            left_16bit = (left_8bit - 128) * 256
            right_16bit = (right_8bit - 128) * 256
            
            wav.writeframes(struct.pack('<hh', left_16bit, right_16bit))
    
    # Verify output
    file_size = path.stat().st_size
    if file_size < 44:
        print(f"Error: Generated WAV file too small ({file_size} bytes)", file=sys.stderr)
        sys.exit(1)
    
    # Verify RIFF header
    with open(path, 'rb') as f:
        header = f.read(4)
        if header != b'RIFF':
            print(f"Error: WAV file missing RIFF header", file=sys.stderr)
            sys.exit(1)
    
    print(f"Written {file_size} bytes to {path}")


def main():
    parser = argparse.ArgumentParser(
        description='Capture audio from a transpiled GBA ROM and write to WAV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 capture_transpiled.py /tmp/stripes.py /tmp/stripes_audio.wav
    python3 capture_transpiled.py /tmp/hello.py /tmp/hello.wav --frames 60
    python3 capture_transpiled.py /tmp/mode3.py /tmp/mode3.wav --frames 600

The transpiled ROM must have a global 'apu' instance from gba_runtime.apu.
The script will call apu._generate_samples() in a loop and write the output
to a 16-bit stereo WAV file at 44100Hz.
"""
    )
    
    parser.add_argument(
        'transpiled',
        type=Path,
        help='Path to transpiled ROM Python file (e.g., /tmp/stripes.py)'
    )
    parser.add_argument(
        'output',
        type=Path,
        help='Output WAV file path (e.g., /tmp/stripes_audio.wav)'
    )
    parser.add_argument(
        '--frames',
        type=int,
        default=300,
        help='Number of frames to capture (default: 300 = ~5 seconds)'
    )
    parser.add_argument(
        '--samples-per-frame',
        type=int,
        default=SAMPLES_PER_FRAME,
        help=f'Samples per frame (default: {SAMPLES_PER_FRAME} at 44100Hz)'
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.transpiled.exists():
        print(f"Error: Transpiled file not found: {args.transpiled}", file=sys.stderr)
        sys.exit(1)
    
    # Load transpiled module
    print(f"Loading transpiled ROM: {args.transpiled}")
    module = load_transpiled_module(args.transpiled)
    
    # Validate module structure
    print("Validating module structure...")
    apu = validate_module(module)
    
    # Get actual sample rate from APU if available
    framerate = getattr(apu, 'SAMPLE_RATE', SAMPLE_RATE)
    print(f"APU sample rate: {framerate}Hz")
    
    # Capture audio
    raw_samples = capture_audio(apu, args.frames, args.samples_per_frame)
    
    if len(raw_samples) == 0:
        print("Error: No audio samples captured", file=sys.stderr)
        sys.exit(1)
    
    # Write WAV file
    print(f"Writing WAV file: {args.output}")
    write_wav(args.output, raw_samples, framerate)
    
    # Report success
    file_size = args.output.stat().st_size
    duration_secs = len(raw_samples) / (framerate * 2)  # 2 bytes per stereo sample
    
    print('=' * 50)
    print("CAPTURE COMPLETE")
    print('=' * 50)
    print(f"Output:       {args.output}")
    print(f"File size:    {file_size} bytes")
    print(f"Duration:     {duration_secs:.2f} seconds")
    print(f"Frames:       {args.frames}")
    print(f"Sample rate:  {framerate}Hz")
    print(f"Format:       16-bit stereo WAV")
    print('=' * 50)
    
    sys.exit(0)


if __name__ == '__main__':
    main()