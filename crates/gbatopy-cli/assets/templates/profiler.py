# === Performance Profiler (optional) ===

import cProfile
import pstats
import io
from typing import Optional


class Profiler:
    """Simple profiler wrapper for GBA emulation"""
    
    def __init__(self):
        self._profiler: Optional[cProfile.Profile] = None
        self._stats: Optional[pstats.Stats] = None
    
    def start(self):
        """Start profiling"""
        self._profiler = cProfile.Profile()
        self._profiler.enable()
    
    def stop(self):
        """Stop profiling and collect stats"""
        if self._profiler:
            self._profiler.disable()
            self._stats = pstats.Stats(self._profiler)
            self._stats.sort_stats('cumulative')
    
    def print_stats(self, top_n: int = 10):
        """Print top N slowest functions"""
        if self._stats:
            print(f"\n{'='*70}")
            print(f"TOP {top_n} SLOWEST FUNCTIONS")
            print(f"{'='*70}")
            self._stats.print_stats(top_n)
            print(f"\n{'='*70}")
    
    def save_stats(self, output_path: str):
        """Save profiling stats to file"""
        if self._stats:
            with open(output_path, 'w') as f:
                self._stats.stream = f
                self._stats.print_stats()


# Global profiler instance
_profiler = Profiler()


def enable_profiler():
    """Enable profiling"""
    _profiler.start()


def disable_profiler():
    """Disable profiling and print stats"""
    _profiler.stop()
    _profiler.print_stats(20)


def save_profiler_stats(output_path: str):
    """Save profiling stats to file"""
    _profiler.save_stats(output_path)
