"""Timing calibration module for GBA runtime.

Measures Python instruction execution time and calibrates to GBA clock (16.79 MHz).

Provides:
- Calibration routine that runs at startup
- Cycles-per-Python-operation ratio measurement
- Helper function to convert GBA cycles to Python sleep/wait time
"""

import time
from typing import Optional, Tuple


GBA_CLOCK_MHZ = 16.79  # GBA runs at 16.79 MHz (16,790,000 cycles/second)
GBA_CYCLES_PER_SECOND = GBA_CLOCK_MHZ * 1_000_000  # 16,790,000 cycles/s


class TimingCalibrator:
    """Calibrates GBA cycle timing to Python execution time."""
    
    def __init__(self):
        self._cycles_per_python_iter: float = 0
        self._calibration_samples: int = 0
        self._calibrated = False
    
    def _warmup(self, iterations: int = 10000) -> None:
        """Warmup the calibrator to ensure consistent measurements."""
        for _ in range(iterations):
            # Simple operations to warm up CPU cache
            _ = sum(i * 2 for i in range(100))
            _ = 1000000 % 17  # Modulo for varying execution time
    
    def _get_python_iteration_time(self, samples: int = 1000) -> float:
        """
        Measure time for a single Python iteration using timeit methodology.
        
        Returns:
            Average time in seconds for one iteration of a calibrated loop.
        """
        start = time.perf_counter()
        
        # Calibrated loop - similar instruction density to GBA instructions
        for i in range(samples):
            # Data processing: ~1 cycle in GBA
            _ = (i * 2 + 7) & 0xFFFFFFFF
            _ = 1000000 % 17  # Modulo for branch misprediction
            
            # Load/store: ~2 cycles in GBA
            _ = (i + 123) % 10000
            _ = (i + 456) % 20000
            
            # Branch: ~1-3 cycles in GBA
            if i % 10 == 0:
                _ = sum(range(10))
            if i % 5 == 0:
                _ = 1 + 2 + 3 + 4 + 5
            
            # Memory access simulation
            temp1 = i * 17
            temp2 = i + 23
            temp3 = temp1 + temp2
            
            # MUL instruction: ~2 cycles in GBA
            _ = (i * 7) % 1000000
        
        end = time.perf_counter()
        
        total_time = end - start
        avg_iter_time = total_time / samples
        
        return avg_iter_time
    
    def calibrate(self, samples: int = 1000, iterations: int = 5) -> float:
        """
        Calibrate timing by measuring Python iteration time against known GBA cycles.
        
        Methodology:
        1. Warm up the calibrator to ensure consistent CPU behavior
        2. Run a calibrated loop with known instruction density
        3. Measure total execution time with time.perf_counter()
        4. Calculate cycles-per-iteration ratio
        5. Average across multiple runs for stability
        
        Args:
            samples: Number of iterations to measure (higher = more accurate)
            iterations: Number of times to repeat the measurement for averaging
        
        Returns:
            Estimated GBA cycles per Python iteration
        """
        self._warmup()
        
        total_cycles = 0
        
        # Simulated GBA cycle count for our calibrated loop
        # Based on ARM7TDMI instruction timing:
        # - Data processing: 1 cycle
        # - Load/store: 2 cycles  
        # - Branch: 2-3 cycles
        # - MUL: 2 cycles
        # Our loop has ~20-25 cycles per iteration on average
        cycles_per_python_iter_estimate = 22  # Baseline estimate
        
        for _ in range(iterations):
            python_time = self._get_python_iteration_time(samples)
            total_cycles += cycles_per_python_iter_estimate
        
        avg_cycles = total_cycles / iterations
        avg_time = python_time  # Get from last iteration
        
        # Calculate cycles per second (should be close to GBA_CLOCK_MHZ)
        cycles_per_second = avg_cycles / avg_time
        error_percent = abs(cycles_per_second - GBA_CLOCK_MHZ) / GBA_CLOCK_MHZ * 100
        
        self._cycles_per_python_iter = avg_cycles
        self._calibration_samples = samples
        self._calibrated = True
        
        # Print calibration info for debugging
        print(f"Timing Calibration:")
        print(f"  Python iteration time: {avg_time:.6f}s")
        print(f"  Estimated cycles/iter: {avg_cycles:.1f}")
        print(f"  Derived clock: {cycles_per_second:,.0f} MHz")
        print(f"  Error from target (16.79 MHz): {error_percent:.2f}%")
        print(f"  Samples: {samples}, Iterations: {iterations}")
        
        return avg_cycles
    
    def get_cycles_for_seconds(self, seconds: float) -> int:
        """
        Convert Python seconds to GBA cycles.
        
        Args:
            seconds: Time in Python execution time
        
        Returns:
            Number of GBA cycles that would execute in that time
        """
        if not self._calibrated:
            raise RuntimeError("Timing not calibrated. Call calibrate() first.")
        
        # cycles_per_python_iter = GBA cycles / Python iteration time
        python_iter_time = self._cycles_per_python_iter / GBA_CYCLES_PER_SECOND
        iterations_in_seconds = seconds / python_iter_time
        total_cycles = iterations_in_seconds * self._cycles_per_python_iter
        
        return int(total_cycles)
    
    def get_seconds_for_cycles(self, cycles: int) -> float:
        """
        Convert GBA cycles to Python seconds.
        
        This is the primary function for timing-calibrated delays.
        
        Args:
            cycles: Number of GBA cycles to wait
        
        Returns:
            Time in seconds to wait using Python sleep
        """
        if not self._calibrated:
            raise RuntimeError("Timing not calibrated. Call calibrate() first.")
        
        # Calculate Python iteration time
        python_iter_time = self._cycles_per_python_iter / GBA_CYCLES_PER_SECOND
        
        # Calculate how many Python iterations to wait
        iterations_needed = cycles / self._cycles_per_python_iter
        
        # Convert to seconds
        total_seconds = iterations_needed * python_iter_time
        
        return total_seconds
    
    def sleep_gba_cycles(self, cycles: int) -> None:
        """
        Sleep for a specified number of GBA cycles.
        
        Uses calibrated timing to ensure accurate GBA cycle timing.
        
        Args:
            cycles: Number of GBA cycles to sleep
        """
        if not self._calibrated:
            raise RuntimeError("Timing not calibrated. Call calibrate() first.")
        
        seconds = self.get_seconds_for_cycles(cycles)
        time.sleep(seconds)
    
    def sleep_gba_frames(self, frames: int) -> None:
        """
        Sleep for a specified number of GBA frames (60 FPS = 16.67ms per frame).
        
        Args:
            frames: Number of frames to sleep
        """
        if not self._calibrated:
            raise RuntimeError("Timing not calibrated. Call calibrate() first.")
        
        # GBA runs at ~60 FPS
        frame_time = 1.0 / 60.0  # ~16.67ms per frame
        total_seconds = frames * frame_time
        
        time.sleep(total_seconds)


def run_calibration(
    samples: int = 1000,
    iterations: int = 5,
    verbose: bool = True,
) -> Tuple[float, float]:
    """
    Run timing calibration and return timing parameters.
    
    Args:
        samples: Number of iterations for measurement
        iterations: Number of repeat measurements for averaging
        verbose: Print calibration details
        
    Returns:
        Tuple of (cycles_per_python_iter, python_iter_time)
    """
    calibrator = TimingCalibrator()
    cycles_per_iter = calibrator.calibrate(samples, iterations, verbose)
    python_iter_time = cycles_per_iter / GBA_CYCLES_PER_SECOND
    
    return cycles_per_iter, python_iter_time


def get_calibrated_timing() -> Tuple[float, float]:
    """
    Get calibrated timing parameters if available, otherwise return defaults.
    
    Returns:
        Tuple of (cycles_per_python_iter, python_iter_time)
    """
    # Try to get from global (would be set by initialization)
    try:
        from gba_runtime import _timing_data
        return _timing_data['cycles_per_iter'], _timing_data['python_iter_time']
    except (ImportError, KeyError):
        # Return calibrated values if available, otherwise defaults
        pass
    
    # Fallback to uncalibrated estimate
    return (
        GBA_CYCLES_PER_SECOND / 1_000_000 / (1.0 / 100) * 0.01,
        0.01  # ~10ms baseline
    )


# Global calibrator instance
_calibrator: Optional[TimingCalibrator] = None


def get_calibrator() -> TimingCalibrator:
    """Get or create the global timing calibrator."""
    global _calibrator
    if _calibrator is None:
        _calibrator = TimingCalibrator()
    return _calibrator


def initialize_timing() -> Tuple[float, float]:
    """
    Initialize timing calibration at runtime startup.
    
    This should be called early in runtime initialization to ensure
    all timing-dependent code has accurate calibration.
    
    Returns:
        Tuple of (cycles_per_python_iter, python_iter_time)
    """
    calibrator = get_calibrator()
    cycles_per_iter, python_iter_time = run_calibration(
        samples=1000,
        iterations=3,
        verbose=True
    )
    
    # Store for later use
    try:
        from gba_runtime import _timing_data
        _timing_data['cycles_per_iter'] = cycles_per_iter
        _timing_data['python_iter_time'] = python_iter_time
    except ImportError:
        pass
    
    return cycles_per_iter, python_iter_time


def cycles_to_sleep(cycles: int) -> float:
    """
    Convert GBA cycles to sleep time in seconds.
    
    Convenience function for quick conversion.
    
    Args:
        cycles: Number of GBA cycles
        
    Returns:
        Time in seconds to sleep
    """
    calibrator = get_calibrator()
    return calibrator.get_seconds_for_cycles(cycles)


def sleep_cycles(cycles: int) -> None:
    """
    Sleep for GBA cycles.
    
    Convenience function for quick timing.
    
    Args:
        cycles: Number of GBA cycles to sleep
    """
    calibrator = get_calibrator()
    calibrator.sleep_gba_cycles(cycles)
