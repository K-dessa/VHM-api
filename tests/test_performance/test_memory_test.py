"""
Memory usage testing and monitoring.
"""
import psutil
import time
import gc
import tracemalloc
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class MemorySnapshot:
    """Memory usage snapshot."""
    timestamp: float
    rss_mb: float
    vms_mb: float
    percent: float
    tracemalloc_current_mb: float = 0
    tracemalloc_peak_mb: float = 0


class MemoryProfiler:
    """Memory profiler for performance testing."""
    
    def __init__(self):
        self.process = psutil.Process()
        self.snapshots: List[MemorySnapshot] = []
        self.baseline_snapshot = None
        self.tracemalloc_enabled = False
    
    def start_profiling(self, enable_tracemalloc=True):
        """Start memory profiling."""
        if enable_tracemalloc:
            tracemalloc.start()
            self.tracemalloc_enabled = True
        
        self.baseline_snapshot = self.take_snapshot()
        self.snapshots = [self.baseline_snapshot]
    
    def take_snapshot(self) -> MemorySnapshot:
        """Take a memory usage snapshot."""
        memory_info = self.process.memory_info()
        memory_percent = self.process.memory_percent()
        
        tracemalloc_current = 0
        tracemalloc_peak = 0
        
        if self.tracemalloc_enabled:
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc_current = current / 1024 / 1024  # MB
            tracemalloc_peak = peak / 1024 / 1024  # MB
        
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=memory_info.rss / 1024 / 1024,
            vms_mb=memory_info.vms / 1024 / 1024,
            percent=memory_percent,
            tracemalloc_current_mb=tracemalloc_current,
            tracemalloc_peak_mb=tracemalloc_peak
        )
        
        self.snapshots.append(snapshot)
        return snapshot
    
    def stop_profiling(self) -> Dict:
        """Stop profiling and return analysis."""
        if self.tracemalloc_enabled:
            tracemalloc.stop()
        
        if len(self.snapshots) < 2:
            return {"error": "Not enough snapshots for analysis"}
        
        final_snapshot = self.snapshots[-1]
        baseline = self.baseline_snapshot
        
        # Calculate statistics
        rss_values = [s.rss_mb for s in self.snapshots]
        vms_values = [s.vms_mb for s in self.snapshots]
        
        analysis = {
            "baseline": {
                "rss_mb": baseline.rss_mb,
                "vms_mb": baseline.vms_mb,
                "percent": baseline.percent
            },
            "final": {
                "rss_mb": final_snapshot.rss_mb,
                "vms_mb": final_snapshot.vms_mb,
                "percent": final_snapshot.percent
            },
            "growth": {
                "rss_mb": final_snapshot.rss_mb - baseline.rss_mb,
                "vms_mb": final_snapshot.vms_mb - baseline.vms_mb,
                "percent": final_snapshot.percent - baseline.percent
            },
            "statistics": {
                "rss_max_mb": max(rss_values),
                "rss_min_mb": min(rss_values),
                "rss_avg_mb": sum(rss_values) / len(rss_values),
                "vms_max_mb": max(vms_values),
                "vms_min_mb": min(vms_values),
                "vms_avg_mb": sum(vms_values) / len(vms_values)
            },
            "snapshots_count": len(self.snapshots),
            "duration_seconds": final_snapshot.timestamp - baseline.timestamp
        }
        
        if self.tracemalloc_enabled:
            analysis["tracemalloc"] = {
                "current_mb": final_snapshot.tracemalloc_current_mb,
                "peak_mb": final_snapshot.tracemalloc_peak_mb
            }
        
        return analysis
    
    def get_memory_leak_indicators(self) -> Dict:
        """Analyze for potential memory leaks."""
        if len(self.snapshots) < 10:
            return {"error": "Need at least 10 snapshots for leak analysis"}
        
        # Look for consistent growth patterns
        rss_values = [s.rss_mb for s in self.snapshots]
        
        # Calculate growth trend
        n = len(rss_values)
        x_sum = sum(range(n))
        y_sum = sum(rss_values)
        xy_sum = sum(i * val for i, val in enumerate(rss_values))
        x2_sum = sum(i * i for i in range(n))
        
        # Linear regression slope
        slope = (n * xy_sum - x_sum * y_sum) / (n * x2_sum - x_sum * x_sum)
        
        # Check for consistent growth
        growth_rate_mb_per_snapshot = slope
        
        # Look for sudden spikes
        max_increase = 0
        for i in range(1, len(rss_values)):
            increase = rss_values[i] - rss_values[i-1]
            max_increase = max(max_increase, increase)
        
        leak_indicators = {
            "growth_rate_mb_per_snapshot": growth_rate_mb_per_snapshot,
            "total_growth_mb": rss_values[-1] - rss_values[0],
            "max_single_increase_mb": max_increase,
            "potential_leak": growth_rate_mb_per_snapshot > 0.5,  # More than 0.5MB per snapshot
            "concerning_spikes": max_increase > 50,  # Spike of more than 50MB
            "baseline_memory_mb": rss_values[0],
            "final_memory_mb": rss_values[-1]
        }
        
        return leak_indicators


def run_memory_stress_test():
    """Run a memory stress test."""
    profiler = MemoryProfiler()
    profiler.start_profiling()
    
    # Simulate memory-intensive operations
    data_chunks = []
    
    try:
        print("Running memory stress test...")
        
        # Phase 1: Allocate memory
        print("Phase 1: Memory allocation")
        for i in range(20):
            # Allocate 10MB chunks
            chunk = bytearray(10 * 1024 * 1024)
            data_chunks.append(chunk)
            profiler.take_snapshot()
            print(f"  Allocated chunk {i+1}/20")
        
        # Phase 2: Hold memory
        print("Phase 2: Memory retention")
        for i in range(10):
            time.sleep(0.1)
            profiler.take_snapshot()
        
        # Phase 3: Release some memory
        print("Phase 3: Partial memory release")
        for i in range(10):
            if data_chunks:
                data_chunks.pop()
            profiler.take_snapshot()
            print(f"  Released chunk {i+1}/10")
        
        # Phase 4: Force garbage collection
        print("Phase 4: Garbage collection")
        gc.collect()
        time.sleep(0.5)
        profiler.take_snapshot()
        
        # Phase 5: Final cleanup
        print("Phase 5: Final cleanup")
        data_chunks.clear()
        gc.collect()
        time.sleep(0.5)
        profiler.take_snapshot()
        
    finally:
        data_chunks.clear()
        gc.collect()
    
    analysis = profiler.stop_profiling()
    leak_indicators = profiler.get_memory_leak_indicators()
    
    print("\n=== Memory Stress Test Results ===")
    print(f"Duration: {analysis['duration_seconds']:.1f} seconds")
    print(f"Baseline memory: {analysis['baseline']['rss_mb']:.1f} MB")
    print(f"Peak memory: {analysis['statistics']['rss_max_mb']:.1f} MB")
    print(f"Final memory: {analysis['final']['rss_mb']:.1f} MB")
    print(f"Memory growth: {analysis['growth']['rss_mb']:.1f} MB")
    
    if 'tracemalloc' in analysis:
        print(f"Tracemalloc peak: {analysis['tracemalloc']['peak_mb']:.1f} MB")
    
    print(f"\n=== Leak Analysis ===")
    print(f"Growth rate: {leak_indicators['growth_rate_mb_per_snapshot']:.3f} MB/snapshot")
    print(f"Potential leak: {leak_indicators['potential_leak']}")
    print(f"Concerning spikes: {leak_indicators['concerning_spikes']}")
    print(f"Max single increase: {leak_indicators['max_single_increase_mb']:.1f} MB")
    
    return analysis, leak_indicators


def monitor_api_memory_usage():
    """Monitor memory usage during API operations."""
    profiler = MemoryProfiler()
    profiler.start_profiling()
    
    print("Monitoring API memory usage...")
    print("This would typically run alongside API load tests")
    
    # Simulate API request patterns
    for i in range(60):  # 1 minute of monitoring
        time.sleep(1)
        snapshot = profiler.take_snapshot()
        
        if i % 10 == 0:
            print(f"  {i}s - Memory: {snapshot.rss_mb:.1f} MB")
    
    analysis = profiler.stop_profiling()
    leak_indicators = profiler.get_memory_leak_indicators()
    
    print("\n=== API Memory Monitoring Results ===")
    print(f"Monitoring duration: {analysis['duration_seconds']:.1f} seconds")
    print(f"Memory usage - Min: {analysis['statistics']['rss_min_mb']:.1f} MB")
    print(f"Memory usage - Max: {analysis['statistics']['rss_max_mb']:.1f} MB")
    print(f"Memory usage - Avg: {analysis['statistics']['rss_avg_mb']:.1f} MB")
    print(f"Memory growth: {analysis['growth']['rss_mb']:.1f} MB")
    
    if leak_indicators['potential_leak']:
        print("⚠️  Potential memory leak detected!")
        print(f"   Growth rate: {leak_indicators['growth_rate_mb_per_snapshot']:.3f} MB/snapshot")
    else:
        print("✅ No significant memory leaks detected")
    
    # Check against thresholds
    warnings = []
    if analysis['statistics']['rss_max_mb'] > 512:
        warnings.append(f"Peak memory usage exceeds 512MB: {analysis['statistics']['rss_max_mb']:.1f} MB")
    
    if analysis['growth']['rss_mb'] > 100:
        warnings.append(f"Memory growth exceeds 100MB: {analysis['growth']['rss_mb']:.1f} MB")
    
    if leak_indicators['max_single_increase_mb'] > 50:
        warnings.append(f"Large memory spike detected: {leak_indicators['max_single_increase_mb']:.1f} MB")
    
    if warnings:
        print("\n⚠️  Memory Usage Warnings:")
        for warning in warnings:
            print(f"   {warning}")
    else:
        print("\n✅ All memory thresholds passed")
    
    return analysis, warnings


if __name__ == "__main__":
    print("Business Analysis API - Memory Testing")
    print("=" * 50)
    
    # Run stress test
    stress_analysis, leak_indicators = run_memory_stress_test()
    
    print("\n" + "=" * 50)
    
    # Run API monitoring simulation
    api_analysis, warnings = monitor_api_memory_usage()
    
    # Summary
    print("\n" + "=" * 50)
    print("MEMORY TEST SUMMARY")
    print("=" * 50)
    
    if leak_indicators['potential_leak'] or warnings:
        print("❌ MEMORY TESTS FAILED")
        if leak_indicators['potential_leak']:
            print(f"   - Potential memory leak (growth: {leak_indicators['growth_rate_mb_per_snapshot']:.3f} MB/snapshot)")
        for warning in warnings:
            print(f"   - {warning}")
    else:
        print("✅ MEMORY TESTS PASSED")
        print("   - No memory leaks detected")
        print("   - All usage thresholds met")
        print(f"   - Peak usage: {max(stress_analysis['statistics']['rss_max_mb'], api_analysis['statistics']['rss_max_mb']):.1f} MB")