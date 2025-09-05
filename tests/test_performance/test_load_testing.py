"""
Performance and load testing for the business analysis API.
"""
import time
import asyncio
import statistics
import pytest
import psutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.models.responses import CompanyInfo, LegalCase, NewsAnalysis


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture
def mock_company_data():
    """Mock company data for performance testing."""
    return CompanyInfo(
        kvk_number="12345678",
        name="Performance Test Company B.V.",
        trade_name="PerfTestCorp",
        status="Actief",
        establishment_date=datetime.now() - timedelta(days=365 * 3),
        address="Performance Street 1, 1000 AB Amsterdam",
        postal_code="1000AB",
        city="Amsterdam",
        country="Nederland",
        phone="+31 20 1234567",
        website="https://www.perftest.nl",
        email="info@perftest.nl",
        sbi_codes=["6201", "6202"],
        employee_count=50,
        legal_form="BV"
    )


@pytest.fixture
def mock_legal_data():
    """Mock legal data for performance testing."""
    return [
        LegalCase(
            case_id="PERF001",
            date=datetime.now() - timedelta(days=180),
            case_type="Civiel",
            summary="Performance test legal case",
            outcome="Resolved",
            court="Rechtbank Amsterdam",
            parties=["Performance Test Company B.V.", "Test Party"]
        )
    ]


@pytest.fixture
def mock_news_data():
    """Mock news data for performance testing."""
    return NewsAnalysis(
        total_articles_found=10,
        total_relevance=0.8,
        overall_sentiment=0.2,
        sentiment_summary={"positive": 60, "neutral": 30, "negative": 10},
        key_topics=["Performance", "Testing", "Business"],
        risk_indicators=[],
        positive_news={"count": 6, "themes": ["growth", "performance"]},
        negative_news={"count": 1, "themes": ["minor issue"]},
        articles=[
            {
                "title": "Performance Test Article",
                "summary": "Testing article for performance",
                "date": "2024-01-15",
                "sentiment": 0.3,
                "relevance": 0.8
            }
        ]
    )


class PerformanceMetrics:
    """Class to collect and analyze performance metrics."""
    
    def __init__(self):
        self.response_times = []
        self.success_count = 0
        self.error_count = 0
        self.start_time = None
        self.end_time = None
        self.memory_usage = []
        self.cpu_usage = []
    
    def record_response(self, response_time: float, success: bool):
        """Record a single response."""
        self.response_times.append(response_time)
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
    
    def record_system_metrics(self):
        """Record current system metrics."""
        process = psutil.Process()
        self.memory_usage.append(process.memory_info().rss / 1024 / 1024)  # MB
        self.cpu_usage.append(process.cpu_percent())
    
    def get_statistics(self):
        """Get performance statistics."""
        if not self.response_times:
            return {}
        
        total_time = self.end_time - self.start_time if self.end_time and self.start_time else 0
        
        return {
            "total_requests": len(self.response_times),
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": self.success_count / len(self.response_times) * 100,
            "total_duration_seconds": total_time,
            "requests_per_second": len(self.response_times) / total_time if total_time > 0 else 0,
            "response_time_stats": {
                "min": min(self.response_times),
                "max": max(self.response_times),
                "mean": statistics.mean(self.response_times),
                "median": statistics.median(self.response_times),
                "p95": self._percentile(self.response_times, 95),
                "p99": self._percentile(self.response_times, 99)
            },
            "memory_usage_mb": {
                "min": min(self.memory_usage) if self.memory_usage else 0,
                "max": max(self.memory_usage) if self.memory_usage else 0,
                "mean": statistics.mean(self.memory_usage) if self.memory_usage else 0
            },
            "cpu_usage_percent": {
                "max": max(self.cpu_usage) if self.cpu_usage else 0,
                "mean": statistics.mean(self.cpu_usage) if self.cpu_usage else 0
            }
        }
    
    def _percentile(self, data, percentile):
        """Calculate percentile of data."""
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        lower = int(index)
        upper = min(lower + 1, len(sorted_data) - 1)
        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight


def make_request(client, request_data, headers):
    """Make a single request and measure time."""
    start_time = time.time()
    try:
        response = client.post("/analyze-company", json=request_data, headers=headers)
        end_time = time.time()
        return end_time - start_time, response.status_code == 200
    except Exception:
        end_time = time.time()
        return end_time - start_time, False


class TestLoadTesting:
    """Load testing with concurrent requests."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_concurrent_requests_10_users(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        mock_company_data,
        mock_legal_data,
        mock_news_data
    ):
        """Test handling of 10 concurrent requests."""
        
        # Add realistic delay to simulate real service behavior
        async def delayed_kvk_response():
            await asyncio.sleep(0.5)  # 500ms delay
            return mock_company_data
        
        async def delayed_legal_response():
            await asyncio.sleep(0.3)
            return mock_legal_data
        
        async def delayed_news_response():
            await asyncio.sleep(0.4)
            return mock_news_data
        
        mock_kvk_info.side_effect = delayed_kvk_response
        mock_legal_init.return_value = None
        mock_legal_search.side_effect = delayed_legal_response
        mock_news_search.side_effect = delayed_news_response
        
        # Test parameters
        concurrent_users = 10
        requests_per_user = 5
        total_requests = concurrent_users * requests_per_user
        
        metrics = PerformanceMetrics()
        
        request_data = {"kvk_number": "12345678", "search_depth": "standard"}
        headers = {"X-API-Key": "load-test-key"}
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            metrics.start_time = time.time()
            
            # System metrics monitoring thread
            def monitor_system():
                while metrics.start_time and not metrics.end_time:
                    metrics.record_system_metrics()
                    time.sleep(0.5)
            
            monitor_thread = threading.Thread(target=monitor_system, daemon=True)
            monitor_thread.start()
            
            # Execute concurrent requests
            with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                futures = []
                
                for user in range(concurrent_users):
                    for request in range(requests_per_user):
                        future = executor.submit(make_request, client, request_data, headers)
                        futures.append(future)
                
                # Collect results
                for future in as_completed(futures):
                    response_time, success = future.result()
                    metrics.record_response(response_time, success)
            
            metrics.end_time = time.time()
        
        # Analyze results
        stats = metrics.get_statistics()
        
        print(f"\n=== Load Test Results (10 concurrent users) ===")
        print(f"Total requests: {stats['total_requests']}")
        print(f"Success rate: {stats['success_rate']:.1f}%")
        print(f"Requests per second: {stats['requests_per_second']:.1f}")
        print(f"Response time - Mean: {stats['response_time_stats']['mean']:.3f}s")
        print(f"Response time - P95: {stats['response_time_stats']['p95']:.3f}s")
        print(f"Response time - P99: {stats['response_time_stats']['p99']:.3f}s")
        print(f"Memory usage - Max: {stats['memory_usage_mb']['max']:.1f} MB")
        print(f"CPU usage - Max: {stats['cpu_usage_percent']['max']:.1f}%")
        
        # Assertions
        assert stats['success_rate'] >= 95.0, f"Success rate too low: {stats['success_rate']:.1f}%"
        assert stats['response_time_stats']['p95'] < 35.0, f"P95 response time too high: {stats['response_time_stats']['p95']:.3f}s"
        assert stats['memory_usage_mb']['max'] < 512, f"Memory usage too high: {stats['memory_usage_mb']['max']:.1f} MB"
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.initialize')
    def test_sustained_load_performance(
        self,
        mock_legal_init,
        mock_kvk_info,
        client,
        mock_company_data
    ):
        """Test sustained load over a longer period."""
        
        # Lightweight scenario - only KvK service
        mock_kvk_info.return_value = mock_company_data
        mock_legal_init.return_value = None
        
        # Test parameters
        duration_seconds = 30
        target_rps = 2  # 2 requests per second
        
        metrics = PerformanceMetrics()
        request_data = {"kvk_number": "12345678"}
        headers = {"X-API-Key": "sustained-test-key"}
        
        with patch('app.services.legal_service.LegalService.robots_allowed', False):
            with patch('app.services.news_service.NewsService.__init__', side_effect=ValueError("No OpenAI key")):
                metrics.start_time = time.time()
                
                while (time.time() - metrics.start_time) < duration_seconds:
                    request_start = time.time()
                    
                    response_time, success = make_request(client, request_data, headers)
                    metrics.record_response(response_time, success)
                    metrics.record_system_metrics()
                    
                    # Rate limiting - wait to achieve target RPS
                    elapsed = time.time() - request_start
                    sleep_time = (1.0 / target_rps) - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                
                metrics.end_time = time.time()
        
        stats = metrics.get_statistics()
        
        print(f"\n=== Sustained Load Test Results ===")
        print(f"Duration: {stats['total_duration_seconds']:.1f}s")
        print(f"Total requests: {stats['total_requests']}")
        print(f"Success rate: {stats['success_rate']:.1f}%")
        print(f"Average RPS: {stats['requests_per_second']:.1f}")
        print(f"Response time - Mean: {stats['response_time_stats']['mean']:.3f}s")
        print(f"Memory usage - Mean: {stats['memory_usage_mb']['mean']:.1f} MB")
        
        # Assertions
        assert stats['success_rate'] >= 98.0, f"Success rate too low for sustained load: {stats['success_rate']:.1f}%"
        assert stats['response_time_stats']['mean'] < 5.0, f"Mean response time too high: {stats['response_time_stats']['mean']:.3f}s"
        assert stats['memory_usage_mb']['mean'] < 256, f"Average memory usage too high: {stats['memory_usage_mb']['mean']:.1f} MB"


class TestStressTesting:
    """Stress testing to find system limits."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.initialize')
    def test_rate_limit_behavior_under_stress(
        self,
        mock_legal_init,
        mock_kvk_info,
        client,
        mock_company_data
    ):
        """Test behavior when rate limits are exceeded."""
        
        mock_kvk_info.return_value = mock_company_data
        mock_legal_init.return_value = None
        
        request_data = {"kvk_number": "12345678"}
        headers = {"X-API-Key": "stress-test-key"}
        
        # Make requests rapidly to trigger rate limiting
        responses = []
        
        with patch('app.services.legal_service.LegalService.robots_allowed', False):
            with patch('app.services.news_service.NewsService.__init__', side_effect=ValueError("No OpenAI key")):
                for i in range(120):  # Exceed 100/hour limit
                    response = client.post("/analyze-company", json=request_data, headers=headers)
                    responses.append(response.status_code)
                    
                    if response.status_code == 429:
                        break  # Stop when rate limited
        
        # Analyze rate limiting behavior
        success_responses = [r for r in responses if r == 200]
        rate_limited_responses = [r for r in responses if r == 429]
        
        print(f"\n=== Stress Test - Rate Limiting ===")
        print(f"Total requests made: {len(responses)}")
        print(f"Successful responses: {len(success_responses)}")
        print(f"Rate limited responses: {len(rate_limited_responses)}")
        
        # Should eventually hit rate limit
        assert len(rate_limited_responses) > 0, "Rate limiting should have been triggered"
        assert len(success_responses) >= 50, "Should allow reasonable number of requests before rate limiting"
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_resource_exhaustion_scenario(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        mock_company_data,
        mock_legal_data,
        mock_news_data
    ):
        """Test behavior under resource exhaustion conditions."""
        
        # Simulate slower responses under load
        async def slow_kvk_response():
            await asyncio.sleep(2.0)  # Slower under stress
            return mock_company_data
        
        async def slow_legal_response():
            await asyncio.sleep(1.5)
            return mock_legal_data
        
        async def slow_news_response():
            await asyncio.sleep(3.0)
            return mock_news_data
        
        mock_kvk_info.side_effect = slow_kvk_response
        mock_legal_init.return_value = None
        mock_legal_search.side_effect = slow_legal_response
        mock_news_search.side_effect = slow_news_response
        
        metrics = PerformanceMetrics()
        
        request_data = {"kvk_number": "12345678", "search_depth": "deep"}
        
        # Test with multiple users hitting slower endpoints
        concurrent_users = 5
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                metrics.start_time = time.time()
                
                futures = []
                for user in range(concurrent_users):
                    headers = {"X-API-Key": f"stress-user-{user}"}
                    future = executor.submit(make_request, client, request_data, headers)
                    futures.append(future)
                
                for future in as_completed(futures):
                    response_time, success = future.result()
                    metrics.record_response(response_time, success)
                    metrics.record_system_metrics()
                
                metrics.end_time = time.time()
        
        stats = metrics.get_statistics()
        
        print(f"\n=== Resource Exhaustion Test ===")
        print(f"Concurrent users: {concurrent_users}")
        print(f"Success rate: {stats['success_rate']:.1f}%")
        print(f"Response time - Mean: {stats['response_time_stats']['mean']:.3f}s")
        print(f"Response time - Max: {stats['response_time_stats']['max']:.3f}s")
        print(f"Memory usage - Max: {stats['memory_usage_mb']['max']:.1f} MB")
        
        # Under stress, some degradation is acceptable
        assert stats['success_rate'] >= 80.0, f"Success rate too low under stress: {stats['success_rate']:.1f}%"
        assert stats['response_time_stats']['max'] < 70.0, f"Max response time too high: {stats['response_time_stats']['max']:.3f}s"
        assert stats['memory_usage_mb']['max'] < 1024, f"Memory usage too high under stress: {stats['memory_usage_mb']['max']:.1f} MB"


class TestPerformanceBenchmarks:
    """Test specific performance benchmarks."""
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    def test_standard_search_benchmark(
        self,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        mock_company_data,
        mock_legal_data
    ):
        """Test standard search meets < 30s target."""
        
        # Simulate realistic response times
        async def realistic_kvk_response():
            await asyncio.sleep(0.8)  # KvK API delay
            return mock_company_data
        
        async def realistic_legal_response():
            await asyncio.sleep(1.2)  # Legal scraping delay
            return mock_legal_data
        
        mock_kvk_info.side_effect = realistic_kvk_response
        mock_legal_init.return_value = None
        mock_legal_search.side_effect = realistic_legal_response
        
        request_data = {"kvk_number": "12345678", "search_depth": "standard"}
        headers = {"X-API-Key": "benchmark-test-key"}
        
        # Run multiple tests to get average
        response_times = []
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            with patch('app.services.news_service.NewsService.__init__', side_effect=ValueError("No OpenAI key")):
                for i in range(10):
                    start_time = time.time()
                    response = client.post("/analyze-company", json=request_data, headers=headers)
                    end_time = time.time()
                    
                    assert response.status_code == 200, f"Request {i} failed"
                    response_times.append(end_time - start_time)
        
        avg_response_time = statistics.mean(response_times)
        max_response_time = max(response_times)
        p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
        
        print(f"\n=== Standard Search Benchmark ===")
        print(f"Average response time: {avg_response_time:.3f}s")
        print(f"Max response time: {max_response_time:.3f}s")
        print(f"P95 response time: {p95_response_time:.3f}s")
        
        # Benchmark assertions
        assert avg_response_time < 15.0, f"Average response time too high: {avg_response_time:.3f}s"
        assert max_response_time < 30.0, f"Max response time exceeds 30s target: {max_response_time:.3f}s"
        assert p95_response_time < 25.0, f"P95 response time too high: {p95_response_time:.3f}s"
    
    @patch('app.services.kvk_service.KvKService.get_company_info')
    @patch('app.services.legal_service.LegalService.search_company_cases')
    @patch('app.services.legal_service.LegalService.initialize')
    @patch('app.services.news_service.NewsService.search_company_news')
    def test_deep_search_benchmark(
        self,
        mock_news_search,
        mock_legal_init,
        mock_legal_search,
        mock_kvk_info,
        client,
        mock_company_data,
        mock_legal_data,
        mock_news_data
    ):
        """Test deep search meets < 60s target."""
        
        # Simulate longer response times for deep search
        async def deep_kvk_response():
            await asyncio.sleep(1.5)
            return mock_company_data
        
        async def deep_legal_response():
            await asyncio.sleep(3.0)  # More comprehensive legal search
            return mock_legal_data
        
        async def deep_news_response():
            await asyncio.sleep(4.0)  # AI processing takes longer
            return mock_news_data
        
        mock_kvk_info.side_effect = deep_kvk_response
        mock_legal_init.return_value = None
        mock_legal_search.side_effect = deep_legal_response
        mock_news_search.side_effect = deep_news_response
        
        request_data = {"kvk_number": "12345678", "search_depth": "deep"}
        headers = {"X-API-Key": "deep-benchmark-key"}
        
        # Run fewer tests for deep search due to time
        response_times = []
        
        with patch('app.services.legal_service.LegalService.robots_allowed', True):
            for i in range(5):
                start_time = time.time()
                response = client.post("/analyze-company", json=request_data, headers=headers)
                end_time = time.time()
                
                assert response.status_code == 200, f"Deep search request {i} failed"
                response_times.append(end_time - start_time)
        
        avg_response_time = statistics.mean(response_times)
        max_response_time = max(response_times)
        
        print(f"\n=== Deep Search Benchmark ===")
        print(f"Average response time: {avg_response_time:.3f}s")
        print(f"Max response time: {max_response_time:.3f}s")
        
        # Benchmark assertions for deep search
        assert avg_response_time < 45.0, f"Average deep search time too high: {avg_response_time:.3f}s"
        assert max_response_time < 60.0, f"Max deep search time exceeds 60s target: {max_response_time:.3f}s"
    
    def test_memory_usage_benchmark(self, client):
        """Test that memory usage stays within acceptable limits."""
        
        # Simple request to minimize external dependencies
        with patch('app.services.kvk_service.KvKService.get_company_info') as mock_kvk:
            from app.models.responses import CompanyInfo
            from datetime import datetime, timedelta
            
            mock_company_info = CompanyInfo(
                kvk_number="12345678",
                name="Memory Test Company B.V.",
                trade_name="MemTest",
                status="Actief",
                establishment_date=datetime.now() - timedelta(days=365),
                address="Memory Lane 1",
                postal_code="1234AB",
                city="Amsterdam", 
                country="Nederland",
                sbi_codes=["6201"],
                employee_count=10,
                legal_form="BV"
            )
            
            mock_kvk.return_value = mock_company_info
            
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            request_data = {"kvk_number": "12345678"}
            headers = {"X-API-Key": "memory-test-key"}
            
            # Make multiple requests and monitor memory
            memory_readings = [initial_memory]
            
            with patch('app.services.legal_service.LegalService.initialize'):
                with patch('app.services.legal_service.LegalService.robots_allowed', False):
                    with patch('app.services.news_service.NewsService.__init__', side_effect=ValueError("No OpenAI key")):
                        for i in range(50):
                            response = client.post("/analyze-company", json=request_data, headers=headers)
                            assert response.status_code == 200
                            
                            current_memory = process.memory_info().rss / 1024 / 1024
                            memory_readings.append(current_memory)
            
            final_memory = memory_readings[-1]
            max_memory = max(memory_readings)
            memory_growth = final_memory - initial_memory
            
            print(f"\n=== Memory Usage Benchmark ===")
            print(f"Initial memory: {initial_memory:.1f} MB")
            print(f"Final memory: {final_memory:.1f} MB")
            print(f"Max memory: {max_memory:.1f} MB")
            print(f"Memory growth: {memory_growth:.1f} MB")
            
            # Memory benchmark assertions
            assert max_memory < 512, f"Max memory usage exceeds 512MB: {max_memory:.1f} MB"
            assert memory_growth < 100, f"Memory growth too high: {memory_growth:.1f} MB"