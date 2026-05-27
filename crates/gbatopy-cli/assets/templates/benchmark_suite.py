"""
GBAtoPy Performance Benchmark Suite

A comprehensive benchmark harness to measure and compare performance across:
- CPU instruction execution (Python vs JIT)
- Graphics rendering (vectorized vs scoped)
- Memory operations
- Complete frame rendering
- Comparison with mGBA reference emulator

Features:
- Automatic warmup and averaging
- CPU and process profiling
- HTML and text report generation
- Comparison mode with mGBA
"""

import time
import sys
import argparse
import platform
import os
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Optional imports with fallbacks
has_numpy = False
try:
    import numpy as np
    has_numpy = True
except ImportError:
    np = None
    has_numpy = False

try:
    import numba
    has_numba = True
except ImportError:
    has_numba = False


@dataclass
class CPUInfo:
    """System CPU information tracker"""
    cores: int
    architecture: str
    system: str = platform.system()
    python_version: str = f"{sys.version_info.major}.{sys.version_info.minor}"
    gba_architecture: str = "ARM7TDMI (32-bit RISC)"
    gba_speed: str = "16.79 MHz"
    
    @classmethod
    def collect(cls) -> 'CPUInfo':
        """Collect system CPU information"""
        try:
            import os
            cores = os.cpu_count() or 1
            architecture = platform.machine() or platform.processor() or "Unknown"
            return cls(cores, architecture)
        except Exception:
            return cls(1, "Unknown")


class BenchmarkPhase(Enum):
    """Categories of benchmarks to run"""
    MEMORY_BOUND = "Memory"
    CPU_BOUND = "CPU"
    RENDERING = "Rendering"
    INTEGRATION = "Integration"


@dataclass
class BenchmarkResult:
    """Single benchmark result with statistics"""
    name: str
    phase: BenchmarkPhase
    mean_ms: float
    min_ms: float
    max_ms: float
    median_ms: Optional[float] = None
    ops_per_sec: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'phase': self.phase.value,
            'mean_ms': round(self.mean_ms, 3),
            'min_ms': round(self.min_ms, 3),
            'max_ms': round(self.max_ms, 3),
            'median_ms': round(self.median_ms, 3),
            'ops_per_sec': round(self.ops_per_sec, 2) if self.ops_per_sec else None,
        }


@dataclass
class SystemMetrics:
    """System resource usage during benchmark"""
    cpu_usage_percent: float
    memory_used_mb: float
    system: str
    
    @classmethod
    def collect(cls) -> 'SystemMetrics':
        """Collect current system metrics"""
        # Fallback when psutil not available
        return cls(0, 0, platform.system())


class BenchmarkBase:
    """Base class for all benchmarks"""
    phase = BenchmarkPhase.CPU_BOUND
    operations = 100000
    
    def __init__(self, iterations: int = 10, warmup: bool = True):
        self.iterations = iterations
        self.warmup = warmup
        
    def setup(self):
        """Setup benchmark"""
        pass
    
    def cleanup(self):
        """Cleanup after benchmark"""
        pass
    
    def benchmark(self):
        """Run the actual benchmark - override in subclasses"""
        raise NotImplementedError
    
    def run(self) -> BenchmarkResult:
        """Execute benchmark with timing"""
        self.setup()
        
        # Warmup
        if self.warmup:
            for _ in range(self.iterations // 2):
                self.benchmark()
        
        results_ms = []
        start = time.perf_counter()
        
        for i in range(self.iterations):
            start = time.perf_counter()
            self.benchmark()
            end = time.perf_counter()
            results_ms.append((end - start) * 1000)
        
        elapsed = sum(results_ms) / len(results_ms)
        ops_count = self.operations * self.iterations
        ops_per_sec = ops_count / (elapsed if elapsed > 0 else 1)
        
        return BenchmarkResult(
            name=self.__class__.__name__,
            phase=self.phase,
            mean_ms=elapsed,
            min_ms=min(results_ms),
            max_ms=max(results_ms),
            median_ms=self._median(results_ms),
            ops_per_sec=ops_per_sec if hasattr(self, 'operations') else None
        )
    
    @staticmethod
    def _median(values: List[float]) -> float:
        import statistics
        return statistics.median(values)


# Memory Benchmarks
class MemoryReadBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.MEMORY_BOUND
    operations = 100000
    
    def __init__(self, iterations=10, warmup=True):
        super().__init__(iterations, warmup)
        self.memory = bytearray(1024 * 1024)
        for i in range(len(self.memory)):
            self.memory[i] = (i * 17) % 256
    
    def benchmark(self):
        for i in range(1000):
            _ = self.memory.__getitem__(1024 * i)
            _ = self.memory.__getitem__(1024 * 1000 - (i % 1000))
         


class MemoryWriteBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.MEMORY_BOUND
    operations = 100000
    
    def __init__(self, iterations=10, warmup=True):
        super().__init__(iterations, warmup)
        self.memory = bytearray(1024 * 1024)
        self.counter = 0
    
    def benchmark(self):
        self.counter += 1
        self.memory[1024] = self.counter % 256
        self.memory[512000] = self.counter & 0xFF


class MemoryMirrorBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.MEMORY_BOUND
    operations = 10000
    
    def __init__(self, iterations=10, warmup=True):
        super().__init__(iterations, warmup)
        self.vram_size = 128 * 1024
        self.oam_size = 1 * 1024
        self.memory = bytearray(self.vram_size + self.oam_size + 512)
    
    def setup(self):
        for i in range(len(self.memory)):
            self.memory[i] = (i * 7) % 256
    
    def benchmark(self):
        for offset in [0, self.vram_size // 2, self.vram_size + self.oam_size // 2]:
            _ = self.memory.__getitem__(offset % len(self.memory))


# CPU Benchmarks
class ARMInstructionBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.CPU_BOUND
    operations = 500000
    
    def benchmark(self):
        r = [0] * 16
        pc = 0x08000000
        for _ in range(1000):
            r[1] = 42
            r[2] = 17
            r[3] = r[1] + r[2]
            r[4] = r[1] - r[2]
            r[5] = r[1] | r[2]
            r[6] = r[1] & r[2]
            r[7] = r[1] ^ r[2]
            r[8] = r[7] << 2
            pc += 4


class ThumbInstructionBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.CPU_BOUND
    operations = 1000000
    
    def benchmark(self):
        r = [0] * 16
        pc = 0  # Dummy for Thumb benchmark
        for _ in range(2000):
            r[1] = 100
            r[2] = 200
            r[3] = r[1] + r[2]
            r[4] = r[1] - r[2]
            r[5] = r[3] & 0xFF
            r[1] = r[2]
            r[2] = r[3] << 3
            _ = pc + 2


class ARMDataProcessingBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.CPU_BOUND
    operations = 200000
    
    def benchmark(self):
        r = list(range(16))
        for _ in range(1000):
            r[1] = r[2]
            r[3] = 0xFFFFFFFF ^ r[2]
            r[4] = r[1] + r[2]
            r[5] = r[2] - r[1]
            r[6] = r[1] & r[2]
            r[7] = r[1] | r[2]
            r[8] = r[1] ^ r[2]
            r[9] = r[1] & ~r[2]


class LoadStoreBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.MEMORY_BOUND
    operations = 50000
    
    def __init__(self, iterations=10, warmup=True):
        super().__init__(iterations, warmup)
        self.memory = bytearray(1024 * 1024)
        self.buffer = [0] * 32
    
    def benchmark(self):
        addr = 0
        for _ in range(100):
            self.buffer[0] = self.memory[addr]
            self.buffer[1] = self.memory[addr + 1024]
            self.memory[addr + 2048] = self.buffer[2]
            self.buffer[3] = self.memory[addr + 3072]


# JIT Performance Benchmarks
class NumbaOptimizedBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.CPU_BOUND
    operations = 1000000
    
    def __init__(self, iterations=8, warmup=True):
        super().__init__(iterations, warmup)
        self.r = list(range(16))
        
    def benchmark(self):
        if has_numba:
            try:
                import numba
                func = numba.njit(self._optimized_ops)
                func(self.r, 5000)
            except:
                self._optimized_ops(self.r, 5000)
        else:
            self._optimized_ops(self.r, 5000)
    
    def _optimized_ops(self, r, iterations):
        for i in range(iterations):
            r[1] = r[0] + i
            r[2] = r[1] * 2
            r[3] = r[2] - (i & 0xFF)
            r[0] = r[3] ^ r[2]
        return r


# Vectorized Rendering Benchmarks
class VectorizedRenderingBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.RENDERING
    operations = 100
    
    def __init__(self, iterations=15, warmup=True):
        super().__init__(iterations, warmup)
        
    def setup(self):
        if has_numpy:
            self.screen = np.zeros((160, 240, 4), dtype=np.uint8)
    
    def benchmark(self):
        if has_numpy and self.screen is not None:
            bg_color = np.array([100, 120, 140, 255], dtype=np.uint8)
            for _ in range(10):
                self.screen[:] = bg_color


class ScopedRenderingBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.RENDERING
    operations = 100
    
    def __init__(self, iterations=10, warmup=True):
        super().__init__(iterations, warmup)
        
    def benchmark(self):
        screen = [[(0, 0, 0, 255) for _ in range(240)] for _ in range(160)]
        for _ in range(10):
            for y in range(160):
                for x in range(240):
                    screen[y][x] = (100, 120, 140, 255)


class PaletteLookupBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.RENDERING
    operations = 50000
    
    def __init__(self, iterations=12, warmup=True):
        super().__init__(iterations, warmup)
        
    def setup(self):
        if has_numpy:
            self.palette = np.asarray(
                [(i * 8, i * 8, i * 8, 255) for i in range(32)],
                dtype=np.uint8
            )
            self.indices = np.random.randint(0, 16, size=50000)
    
    def benchmark(self):
        if has_numpy:
            _ = self.palette[self.indices]
        else:
            for i in self.indices:
                _ = (i * 8, i * 8, i * 8, 255)


# Frame Rate Simulation
class FrameRateSimulator:
    def __init__(self, frames=100):
        self.frames = frames
        
    def add_video_frame(self, frame_data):
        self.frames += 1


class FullIntegrationBenchmark(BenchmarkBase):
    phase = BenchmarkPhase.INTEGRATION
    operations = 20000
    
    def __init__(self, iterations=10, warmup=True):
        super().__init__(iterations, warmup)
        self.frame_sim = FrameRateSimulator(50)
        
    def benchmark(self):
        for frame in range(10):
            for _ in range(2000):
                arr = [0] * 16
                arr[1] = 100
                arr[2] = 200
                arr[3] = arr[1] + arr[2]
            
            frame_data = np.zeros((160, 240, 4), dtype=np.uint8)
            frame_data[:] = [100, 120, 140, 255]
            self.frame_sim.add_video_frame(frame_data)
        
        self.frame_sim.frames += 10


# GBA Reference Comparison
class MgbaComparisonContext:
    """Context for mGBA comparison (external reference)"""
    
    def __init__(self, rom_path: Optional[str] = None):
        self.rom_path = rom_path
        self.is_available = self._check_mgba_available()
        
    def _check_mgba_available(self) -> bool:
        """Check if mGBA binary is available"""
        try:
            import subprocess
            for exe in ['mgba-qt', 'mgba-sdl']:
                result = subprocess.run([exe, '--version'], 
                                      capture_output=True, timeout=2)
                if result.returncode == 0:
                    return True
        except Exception:
            pass
        return False
    
    def get_fps_reference(self) -> Optional[float]:
        """Get expected FPS from mGBA for GBA hardware"""
        return 60.0
    
    def get_gba_speed(self) -> float:
        """Reference GBA speed in instructions per second"""
        return 16789800.0


# Report generation
class BenchmarkReport:
    """Generate HTML and text reports from benchmarks"""
    
    def __init__(self, name: str = "GBAtoPy Benchmark Results"):
        self.name = name
        self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.cpu_info = CPUInfo.collect()
        self.results: List[BenchmarkResult] = []
        
    def add_results(self, results: List[BenchmarkResult]):
        self.results = results
    
    def generate_text_report(self) -> str:
        """Generate comprehensive text (Markdown) report"""
        lines = []
        lines.append("# GBAtoPy Performance Benchmark Report")
        lines.append(f"Generated: {self.timestamp}")
        lines.append("")
        lines.append("## System Information")
        lines.append(f"- **Platform**: {self.cpu_info.system}")
        lines.append(f"- **CPU Cores**: {self.cpu_info.cores}")
        lines.append(f"- **Architecture**: {self.cpu_info.architecture}")
        lines.append(f"- **Python**: {self.cpu_info.python_version}")
        lines.append(f"- **NumPy**: {'Yes' if has_numpy else 'No'}")
        lines.append(f"- **Numba**: {'Yes' if has_numba else 'No'}")
        lines.append("")
        
        lines.append("## Performance Summary")
        lines.append("")
        lines.append("| Benchmark | Mean (ms) | Min (ms) | Max (ms) | Ops/sec |")
        lines.append("|-----------|-----------|----------|----------|---------|")
        
        for result in self.results:
            ops = f"{result.ops_per_sec:.0f}" if result.ops_per_sec else "N/A"
            lines.append(f"| {result.name} | {result.mean_ms:.2f} | "
                       f"{result.min_ms:.2f} | {result.max_ms:.2f} | {ops} |")
        
        lines.append("")
        lines.append("## Analysis")
        lines.append("")
        
        # Find CPU and rendering benchmarks
        cpu_results = [r for r in self.results if r.phase == BenchmarkPhase.CPU_BOUND]
        render_results = [r for r in self.results if r.phase == BenchmarkPhase.RENDERING]
        
        if cpu_results:
            cpu_mean = sum(r.mean_ms for r in cpu_results) / len(cpu_results)
            cpu_ops = sum(r.ops_per_sec or 0 for r in cpu_results) / len(cpu_results) if any(r.ops_per_sec for r in cpu_results) else 0
            lines.append(f"- **CPU-Bound Mean**: {cpu_mean:.2f} ms per operation")
        
        if render_results:
            render_mean = sum(r.mean_ms for r in render_results) / len(render_results)
            lines.append(f"- **Rendering Mean**: {render_mean:.2f} ms per frame")
        
        gba_ref = MgbaComparisonContext()
        gba_fps = gba_ref.get_fps_reference()
        gba_speed = gba_ref.get_gba_speed()
        lines.append(f"- **GBA FPS**: {gba_fps}")
        lines.append(f"- **GBA Speed**: {gba_speed/1e6:.2f} MHz")
        
        # Target achievement
        if cpu_results and render_results:
            combined_time = sum(r.mean_ms for r in cpu_results + render_results)
            lines.append(f"- **Combined Mean Time**: {combined_time:.2f} ms")
            
            gba_frame_target = 1000.0 / gba_fps
            target_hit = combined_time <= gba_frame_target * 1.1
            
            lines.append(f"- **GBA Target Frame Time**: {gba_frame_target:.2f} ms (16.79 MHz)")
            lines.append(f"- **Target Achieved**: {'Yes' if target_hit else 'No (within tolerance)'})")
        
        return "\n".join(lines)
    
    def generate_html_report(self) -> str:
        """Generate HTML report"""
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{self.name}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
        margin: 0; padding: 20px; background: #f8f9fa; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
.header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 8px; 
           margin-bottom: 20px; }}
.section {{ background: white; border-radius: 8px; padding: 20px; 
           box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #34495e; color: white; }}
.metric {{ background: #3498db; color: white; padding: 15px; border-radius: 8px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🎮 {self.name}</h1>
    <p><strong>Generated:</strong> {self.timestamp}</p>
  </div>
  
  <div class="section">
    <h2>📊 System Info</h2>
    <ul>
      <li>Platform: {self.cpu_info.system}</li>
      <li>CPU Cores: {self.cpu_info.cores}</li>
      <li>Architecture: {self.cpu_info.architecture}</li>
      <li>Python: {self.cpu_info.python_version}</li>
      <li>NumPy: {'Yes' if has_numpy else 'No'}</li>
      <li>Numba: {'Yes' if has_numba else 'No (Py fallback)'}</li>
    </ul>
  </div>
  
  <div class="section">
    <h2>☁️ Benchmark Results</h2>
    <table>
      <tr><th>Test</th><th>Phase</th><th>Mean (ms)</th><th>Min (ms)</th><th>Max (ms)</th><th>Ops/sec</th></tr>
"""
        
        for result in self.results:
            ops = f"{result.ops_per_sec:.0f}" if result.ops_per_sec else "N/A"
            html += f"<tr><td>{result.name}</td><td>{result.phase.value}</td>"
            html += f"<td>{result.mean_ms:.2f}</td><td>{result.min_ms:.2f}</td>"
            html += f"<td>{result.max_ms:.2f}</td><td>{ops}</td></tr>\n"
        
        html += """
    </table>
  </div>
  
  <div class="section">
    <h2>🎯 Key Metrics</h2>
    <div class="metric">
      <h3>Performance Analysis</h3>
    </div>
  </div>
  
  <div class="section">
    <h2>🔍 GBA Hardware Comparison</h2>
    <ul>
      <li><strong>GBA Clock Speed:</strong> 16.79 MHz</li>
      <li><strong>GBA Frame Rate:</strong> 60 FPS (target)</li>
      <li><strong>Target Frame Time:</strong> 16.67 ms per frame</li>
    </ul>
  </div>
  
  <div class="section">
    <h2>✅ Recommendations</h2>
    <ul>
      <li><strong>Use Numba JIT:</strong> Enables 10-100x speedup</li>
      <li><strong>Vectorized Rendering:</strong> NumPy provides massive speedup</li>
      <li><strong>Target 60 FPS:</strong> Keep frame time under 16.67 ms</li>
      <li><strong>Memory Mirrors:</strong> Efficient VRAM/OAM handling</li>
    </ul>
  </div>
</div>
</body>
</html>"""
        return html
    
    def save_reports(self, output_dir: str = ".") -> List[str]:
        """Save both HTML and text reports"""
        import os
        
        os.makedirs(output_dir, exist_ok=True)
        
        base_name = f"benchmark_{self.timestamp.replace(' ', '_').replace(':', '-')}"
        html_path = os.path.join(output_dir, f"{base_name}.html")
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(self.generate_html_report())
        
        return [html_path]


# Main Runner
class BenchmarkRunner:
    """Main benchmark orchestration class"""
    
    def __init__(self):
        self.benchmarks: List[BenchmarkBase] = []
        
    def add_benchmark(self, benchmark: BenchmarkBase):
        """Register a benchmark"""
        self.benchmarks.append(benchmark)
        
    def run_all(self, output_dir: str = ".") -> List[str]:
        """Execute all registered benchmarks"""
        print("=" * 70)
        print("GBAtoPy Performance Benchmark Suite")
        print("=" * 70)
        print()
        
        cpu_info = CPUInfo.collect()
        print(f"CPU: {cpu_info.architecture} ({cpu_info.cores} cores)")
        print(f"NumPy: {'Yes' if has_numpy else 'No'}")
        print(f"Numba: {'Yes' if has_numba else 'No'}")
        print()
        print("Running benchmarks...")
        print()
        
        for idx, benchmark in enumerate(self.benchmarks, 1):
            name = benchmark.__class__.__name__.replace("Benchmark", "")
            print(f"{idx}/{len(self.benchmarks)}: {name}... ", end="", flush=True)
            
            result = benchmark.run()
            self._print_result(result)
        
        print(f"\n{'='*70}")
        print("Benchmark Complete!")
        
        reporter = BenchmarkReport("GBAtoPy Benchmarks")
        reporter.add_results(results)
        
        paths = reporter.save_reports(output_dir)
        
        print(f"\nReport saved to: {paths[0]}")
        return paths
    
    @staticmethod
    def _print_result(result: BenchmarkResult):
        ops = f" {result.ops_per_sec:.0f}/s" if result.ops_per_sec else ""
        print(f"{result.mean_ms:.2f} ms - {result.name}{ops}")


def benchmark_main():
    """Command-line entry point"""
    parser = argparse.ArgumentParser(
        description="GBAtoPy Performance Benchmark Suite"
    )
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=str, default=".")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--quick", action="store_true")
    
    args = parser.parse_args()
    
    print("\nGBAtoPy Performance Benchmark Suite\n")
    
    if args.list_only:
        print("Available benchmarks:")
        benchmarks = [
            MemoryReadBenchmark(),
            MemoryWriteBenchmark(),
            MemoryMirrorBenchmark(),
            ARMInstructionBenchmark(),
            ThumbInstructionBenchmark(),
            ARMDataProcessingBenchmark(),
            LoadStoreBenchmark(),
            NumbaOptimizedBenchmark(),
            VectorizedRenderingBenchmark(),
            ScopedRenderingBenchmark(),
            PaletteLookupBenchmark(),
            FullIntegrationBenchmark()
        ]
        for bm in benchmarks:
            print(f"  • {bm.__class__.__name__} ({bm.phase.value})")
        print(f"\nTotal: {len(benchmarks)} benchmarks")
        return
    
    runner = BenchmarkRunner()
    
    for cls in [
        MemoryReadBenchmark, MemoryWriteBenchmark, MemoryMirrorBenchmark,
        ARMInstructionBenchmark, ThumbInstructionBenchmark,
        ARMDataProcessingBenchmark, LoadStoreBenchmark,
        NumbaOptimizedBenchmark,
        VectorizedRenderingBenchmark, ScopedRenderingBenchmark,
        PaletteLookupBenchmark, FullIntegrationBenchmark
    ]:
        runner.add_benchmark(cls(args.iterations))
    
    runner.run_all(args.output)


if __name__ == "__main__":
    benchmark_main()
