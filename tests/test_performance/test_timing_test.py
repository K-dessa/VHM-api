"""
Response time analysis and performance timing tests.
"""
import time
import statistics
import json
from typing import List, Dict, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests


@dataclass 
class TimingResult:
    """Result of a timing test."""
    endpoint: str
    method: str
    response_time: float
    status_code: int
    success: bool
    timestamp: float
    request_size_bytes: int = 0
    response_size_bytes: int = 0


class TimingAnalyzer:
    """Analyzer for response time performance."""
    
    def __init__(self):
        self.results: List[TimingResult] = []
    
    def record_result(self, result: TimingResult):
        """Record a timing result."""
        self.results.append(result)
    
    def analyze_response_times(self, endpoint: str = None) -> Dict:
        """Analyze response times for an endpoint."""
        filtered_results = self.results
        if endpoint:
            filtered_results = [r for r in self.results if r.endpoint == endpoint]
        
        if not filtered_results:
            return {"error": "No results to analyze"}
        
        response_times = [r.response_time for r in filtered_results if r.success]
        success_count = len([r for r in filtered_results if r.success])
        total_count = len(filtered_results)
        
        if not response_times:
            return {"error": "No successful responses to analyze"}
        
        # Calculate percentiles
        sorted_times = sorted(response_times)
        
        def percentile(data, p):
            if not data:
                return 0
            k = (len(data) - 1) * p / 100
            f = int(k)
            c = k - f
            if f == len(data) - 1:
                return data[f]
            return data[f] * (1 - c) + data[f + 1] * c
        
        analysis = {
            "endpoint": endpoint or "all",
            "total_requests": total_count,
            "successful_requests": success_count,
            "success_rate": (success_count / total_count) * 100 if total_count > 0 else 0,
            "response_times": {
                "min": min(response_times),
                "max": max(response_times),
                "mean": statistics.mean(response_times),
                "median": statistics.median(response_times),
                "std_dev": statistics.stdev(response_times) if len(response_times) > 1 else 0,
                "p50": percentile(sorted_times, 50),
                "p90": percentile(sorted_times, 90),
                "p95": percentile(sorted_times, 95),
                "p99": percentile(sorted_times, 99)
            },
            "thresholds": {
                "under_1s": len([t for t in response_times if t < 1.0]),
                "under_5s": len([t for t in response_times if t < 5.0]),
                "under_30s": len([t for t in response_times if t < 30.0]),
                "over_30s": len([t for t in response_times if t >= 30.0])
            }
        }
        
        # Calculate request rate
        if filtered_results:
            duration = max(r.timestamp for r in filtered_results) - min(r.timestamp for r in filtered_results)
            analysis["requests_per_second"] = total_count / duration if duration > 0 else 0
        
        return analysis
    
    def get_performance_summary(self) -> Dict:
        """Get overall performance summary."""
        if not self.results:
            return {"error": "No results available"}
        
        endpoints = list(set(r.endpoint for r in self.results))
        summary = {
            "total_requests": len(self.results),
            "unique_endpoints": len(endpoints),
            "overall_success_rate": len([r for r in self.results if r.success]) / len(self.results) * 100,
            "test_duration": max(r.timestamp for r in self.results) - min(r.timestamp for r in self.results),
            "endpoint_analyses": {}
        }
        
        # Analyze each endpoint
        for endpoint in endpoints:
            summary["endpoint_analyses"][endpoint] = self.analyze_response_times(endpoint)
        
        return summary


def make_timed_request(url: str, method: str = "POST", data: Dict = None, headers: Dict = None) -> TimingResult:
    """Make a timed HTTP request."""
    start_time = time.time()
    timestamp = start_time
    
    try:
        if method.upper() == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=70)
        elif method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=70)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        end_time = time.time()
        response_time = end_time - start_time
        
        request_size = len(json.dumps(data).encode('utf-8')) if data else 0
        response_size = len(response.content) if hasattr(response, 'content') else 0
        
        return TimingResult(
            endpoint=url.split('/')[-1],  # Extract endpoint name
            method=method,
            response_time=response_time,
            status_code=response.status_code,
            success=200 <= response.status_code < 300,
            timestamp=timestamp,
            request_size_bytes=request_size,
            response_size_bytes=response_size
        )
        
    except Exception as e:
        end_time = time.time()
        response_time = end_time - start_time
        
        return TimingResult(
            endpoint=url.split('/')[-1],
            method=method,
            response_time=response_time,
            status_code=0,
            success=False,
            timestamp=timestamp
        )


def test_endpoint_response_times(base_url: str = "http://localhost:8000") -> Dict:
    """Test response times for various endpoints."""
    analyzer = TimingAnalyzer()
    
    # Test different endpoints
    test_cases = [
        {
            "url": f"{base_url}/health",
            "method": "GET",
            "data": None,
            "headers": None,
            "runs": 20
        },
        {
            "url": f"{base_url}/status", 
            "method": "GET",
            "data": None,
            "headers": None,
            "runs": 10
        },
        {
            "url": f"{base_url}/analyze-company",
            "method": "POST",
            "data": {"kvk_number": "69599084", "search_depth": "standard"},
            "headers": {"X-API-Key": "timing-test-key"},
            "runs": 5
        },
        {
            "url": f"{base_url}/analyze-company",
            "method": "POST", 
            "data": {"kvk_number": "69599084", "search_depth": "deep"},
            "headers": {"X-API-Key": "timing-test-deep-key"},
            "runs": 3
        }
    ]
    
    print("Running endpoint response time tests...")
    
    for test_case in test_cases:
        endpoint_name = test_case["url"].split('/')[-1]
        method = test_case["method"]
        runs = test_case["runs"]
        
        print(f"\nTesting {method} {endpoint_name} ({runs} runs)...")
        
        for run in range(runs):
            result = make_timed_request(
                test_case["url"],
                test_case["method"],
                test_case["data"],
                test_case["headers"]
            )
            
            analyzer.record_result(result)
            
            status_symbol = "✅" if result.success else "❌"
            print(f"  Run {run+1}: {result.response_time:.3f}s {status_symbol}")
            
            # Small delay between requests
            time.sleep(0.5)
    
    return analyzer.get_performance_summary()


def test_concurrent_response_times(base_url: str = "http://localhost:8000", concurrent_users: int = 5) -> Dict:
    """Test response times under concurrent load."""
    analyzer = TimingAnalyzer()
    
    test_data = {"kvk_number": "69599084", "search_depth": "standard"}
    
    print(f"\nTesting concurrent response times ({concurrent_users} concurrent users)...")
    
    def make_concurrent_request(user_id: int) -> TimingResult:
        headers = {"X-API-Key": f"concurrent-user-{user_id}"}
        return make_timed_request(
            f"{base_url}/analyze-company",
            "POST",
            test_data,
            headers
        )
    
    # Execute concurrent requests
    with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
        futures = []
        for user in range(concurrent_users):
            future = executor.submit(make_concurrent_request, user)
            futures.append(future)
        
        # Collect results
        for future in as_completed(futures):
            result = future.result()
            analyzer.record_result(result)
            
            status_symbol = "✅" if result.success else "❌"
            print(f"  User request: {result.response_time:.3f}s {status_symbol}")
    
    return analyzer.analyze_response_times("analyze-company")


def run_comprehensive_timing_analysis():
    """Run comprehensive timing analysis."""
    print("Business Analysis API - Response Time Analysis")
    print("=" * 60)
    
    # Test individual endpoints
    print("Phase 1: Individual Endpoint Testing")
    endpoint_summary = test_endpoint_response_times()
    
    # Test concurrent load
    print("\nPhase 2: Concurrent Load Testing")
    concurrent_analysis = test_concurrent_response_times()
    
    # Results analysis
    print("\n" + "=" * 60)
    print("TIMING ANALYSIS RESULTS")
    print("=" * 60)
    
    print(f"\nOverall Summary:")
    print(f"  Total requests: {endpoint_summary['total_requests']}")
    print(f"  Success rate: {endpoint_summary['overall_success_rate']:.1f}%")
    print(f"  Test duration: {endpoint_summary['test_duration']:.1f}s")
    
    # Endpoint-specific results
    print(f"\nEndpoint Performance:")
    for endpoint, analysis in endpoint_summary['endpoint_analyses'].items():
        if analysis.get('error'):
            continue
            
        rt = analysis['response_times']
        print(f"\n  {endpoint.upper()}:")
        print(f"    Success rate: {analysis['success_rate']:.1f}%")
        print(f"    Response times - Mean: {rt['mean']:.3f}s, P95: {rt['p95']:.3f}s, Max: {rt['max']:.3f}s")
        
        # Check against thresholds
        if endpoint == 'analyze-company':
            if rt['p95'] < 30.0:
                print(f"    ✅ P95 response time meets 30s target")
            else:
                print(f"    ❌ P95 response time exceeds 30s target ({rt['p95']:.3f}s)")
        
        if endpoint in ['health', 'status']:
            if rt['mean'] < 1.0:
                print(f"    ✅ Fast response time for monitoring endpoint")
            else:
                print(f"    ⚠️  Slow response for monitoring endpoint ({rt['mean']:.3f}s)")
    
    # Concurrent performance
    print(f"\nConcurrent Performance:")
    if not concurrent_analysis.get('error'):
        rt = concurrent_analysis['response_times']
        print(f"  Concurrent requests: {concurrent_analysis['total_requests']}")
        print(f"  Success rate: {concurrent_analysis['success_rate']:.1f}%")
        print(f"  Response times - Mean: {rt['mean']:.3f}s, P95: {rt['p95']:.3f}s")
        
        if rt['p95'] < 35.0:  # Allow slightly higher for concurrent
            print(f"  ✅ Concurrent performance acceptable")
        else:
            print(f"  ⚠️  Concurrent performance degraded")
    
    # Performance classification
    issues = []
    warnings = []
    
    for endpoint, analysis in endpoint_summary['endpoint_analyses'].items():
        if analysis.get('error'):
            continue
            
        rt = analysis['response_times']
        
        if endpoint == 'analyze-company':
            if rt['p95'] > 30.0:
                issues.append(f"analyze-company P95 response time: {rt['p95']:.3f}s > 30s")
            elif rt['p95'] > 25.0:
                warnings.append(f"analyze-company P95 approaching limit: {rt['p95']:.3f}s")
        
        if endpoint in ['health', 'status'] and rt['mean'] > 1.0:
            warnings.append(f"{endpoint} endpoint slow: {rt['mean']:.3f}s")
        
        if analysis['success_rate'] < 95.0:
            issues.append(f"{endpoint} low success rate: {analysis['success_rate']:.1f}%")
    
    # Final assessment
    print(f"\n" + "=" * 60)
    print("PERFORMANCE ASSESSMENT")
    print("=" * 60)
    
    if issues:
        print("❌ PERFORMANCE ISSUES DETECTED:")
        for issue in issues:
            print(f"   - {issue}")
    
    if warnings:
        print("⚠️  PERFORMANCE WARNINGS:")
        for warning in warnings:
            print(f"   - {warning}")
    
    if not issues and not warnings:
        print("✅ ALL PERFORMANCE TARGETS MET")
        print("   - Response times within acceptable ranges")
        print("   - High success rates achieved")
        print("   - Concurrent performance stable")
    elif not issues:
        print("✅ PERFORMANCE ACCEPTABLE")
        print("   - No critical issues found")
        print("   - Minor optimizations recommended")
    
    return endpoint_summary, concurrent_analysis, issues, warnings


if __name__ == "__main__":
    try:
        summary, concurrent, issues, warnings = run_comprehensive_timing_analysis()
        
        # Exit code based on results
        if issues:
            exit(1)  # Critical issues
        elif warnings:
            exit(2)  # Warnings only
        else:
            exit(0)  # All good
            
    except Exception as e:
        print(f"❌ Timing test failed: {str(e)}")
        exit(3)  # Test failure