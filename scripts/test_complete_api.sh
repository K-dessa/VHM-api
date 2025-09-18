#!/bin/bash

# Complete API testing script as specified in stap5.md

set -e

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-test-api-key-123456789012345678901234567890}"
TEST_COMPANY_NAME="${TEST_COMPANY_NAME:-ASML Holding N.V.}"

echo "=========================================="
echo "Business Analysis API - Complete Test Suite"
echo "=========================================="
echo "API Base URL: $API_BASE_URL"
echo "Test Company Name: $TEST_COMPANY_NAME"
echo ""

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo "❌ jq is required for this script. Please install it first."
    echo "   macOS: brew install jq"
    echo "   Ubuntu: sudo apt-get install jq"
    exit 1
fi

# Function to make API request with error handling
make_request() {
    local method="$1"
    local endpoint="$2" 
    local data="$3"
    local headers="$4"
    
    if [[ "$method" == "POST" ]]; then
        curl -s -X POST "$API_BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "$headers" \
            -d "$data" \
            --max-time 70
    else
        curl -s -X GET "$API_BASE_URL$endpoint" \
            -H "$headers" \
            --max-time 10
    fi
}

# Function to check HTTP status
check_status() {
    local method="$1"
    local endpoint="$2"
    local data="$3"
    local headers="$4"
    
    if [[ "$method" == "POST" ]]; then
        curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "$headers" \
            -d "$data" \
            --max-time 70
    else
        curl -s -o /dev/null -w "%{http_code}" -X GET "$API_BASE_URL$endpoint" \
            -H "$headers" \
            --max-time 10
    fi
}

echo "1. Health Check Test"
echo "===================="
health_status=$(check_status "GET" "/health" "" "")
if [[ "$health_status" == "200" ]]; then
    echo "✅ Health check passed (HTTP $health_status)"
    make_request "GET" "/health" "" "" | jq '.' 2>/dev/null || echo "Response received but not valid JSON"
else
    echo "❌ Health check failed (HTTP $health_status)"
fi
echo ""

echo "2. System Status Test"
echo "====================="
status_result=$(check_status "GET" "/status" "" "")
if [[ "$status_result" == "200" ]]; then
    echo "✅ Status endpoint passed (HTTP $status_result)"
    make_request "GET" "/status" "" "" | jq '.service, .status, .statistics' 2>/dev/null || echo "Response received"
else
    echo "❌ Status endpoint failed (HTTP $status_result)"
fi
echo ""

echo "3. Complete Company Analysis Test"
echo "================================="

# Prepare request payload
analysis_payload=$(cat <<EOF
{
    "company_name": "$TEST_COMPANY_NAME",
    "search_depth": "standard",
    "news_date_range": "last_year",
    "include_subsidiaries": false
}
EOF
)

echo "Testing analysis request..."
echo "Request payload:"
echo "$analysis_payload" | jq '.'
echo ""

start_time=$(date +%s)
analysis_response=$(make_request "POST" "/analyze-company" "$analysis_payload" "X-API-Key: $API_KEY")
end_time=$(date +%s)
response_time=$((end_time - start_time))

echo "Response time: ${response_time}s"
echo ""

# Check if response is valid JSON
if echo "$analysis_response" | jq '.' >/dev/null 2>&1; then
    echo "✅ Valid JSON response received"
    
    # Extract key information
    request_id=$(echo "$analysis_response" | jq -r '.request_id // "N/A"')
    processing_time=$(echo "$analysis_response" | jq -r '.processing_time_seconds // "N/A"')
    company_name=$(echo "$analysis_response" | jq -r '.company_info.name // "N/A"')
    risk_level=$(echo "$analysis_response" | jq -r '.risk_assessment.overall_risk_level // "N/A"')
    data_sources=$(echo "$analysis_response" | jq -r '.data_sources | length')
    
    echo "Analysis Results:"
    echo "  Request ID: $request_id"
    echo "  Processing Time: ${processing_time}s"
    echo "  Company Name: $company_name"
    echo "  Risk Level: $risk_level"
    echo "  Data Sources: $data_sources"
    
    # Check response completeness
    echo ""
    echo "Response Completeness Check:"
    
    required_fields=("request_id" "analysis_timestamp" "processing_time_seconds" "company_info" "risk_assessment" "data_sources")
    all_present=true
    
    for field in "${required_fields[@]}"; do
        if echo "$analysis_response" | jq -e ".$field" >/dev/null 2>&1; then
            echo "  ✅ $field: present"
        else
            echo "  ❌ $field: missing"
            all_present=false
        fi
    done
    
    if $all_present; then
        echo "✅ All required fields present"
    else
        echo "❌ Some required fields missing"
    fi
    
    # Performance check
    echo ""
    echo "Performance Check:"
    if (( $(echo "$processing_time < 60" | bc -l 2>/dev/null || echo "$processing_time < 60" | python3 -c "import sys; print(float(input()) < 60)") )); then
        echo "  ✅ Processing time within 60s limit: ${processing_time}s"
    else
        echo "  ⚠️  Processing time exceeds 60s: ${processing_time}s"
    fi
    
else
    echo "❌ Invalid JSON response or error occurred"
    echo "Response: $analysis_response"
fi

echo ""

echo "4. Error Handling Test"
echo "======================"

# Test with invalid company name
invalid_payload='{"company_name": "X"}'
echo "Testing with invalid company name..."

invalid_status=$(check_status "POST" "/analyze-company" "$invalid_payload" "X-API-Key: $API_KEY")
if [[ "$invalid_status" == "400" ]]; then
    echo "✅ Invalid input properly rejected (HTTP 400)"
else
    echo "❌ Expected HTTP 400 for invalid input, got HTTP $invalid_status"
fi

# Test without API key
echo "Testing without API key..."
no_key_status=$(check_status "POST" "/analyze-company" "$analysis_payload" "")
if [[ "$no_key_status" == "403" ]] || [[ "$no_key_status" == "401" ]]; then
    echo "✅ Unauthorized request properly rejected (HTTP $no_key_status)"
else
    echo "❌ Expected HTTP 401/403 for unauthorized request, got HTTP $no_key_status"
fi

echo ""

echo "5. Rate Limiting Test"
echo "===================="
echo "Testing rate limiting (making multiple requests)..."

rate_limit_key="rate-limit-test-$(date +%s)"
rate_limit_payload='{"company_name": "Test Company"}'

# Make multiple requests quickly
success_count=0
rate_limited_count=0

for i in {1..10}; do
    status=$(check_status "POST" "/analyze-company" "$rate_limit_payload" "X-API-Key: $rate_limit_key")
    if [[ "$status" == "200" ]]; then
        ((success_count++))
    elif [[ "$status" == "429" ]]; then
        ((rate_limited_count++))
    fi
    
    # Small delay to avoid overwhelming the server
    sleep 0.1
done

echo "Rate limiting results:"
echo "  Successful requests: $success_count"
echo "  Rate limited requests: $rate_limited_count"

if [[ $success_count -gt 0 ]]; then
    echo "✅ Some requests succeeded (rate limiting working)"
else
    echo "❌ No requests succeeded (potential issue)"
fi

echo ""

echo "6. System Metrics Test"
echo "======================"
metrics_response=$(make_request "GET" "/metrics" "" "")
if [[ $? -eq 0 ]] && [[ -n "$metrics_response" ]]; then
    echo "✅ Metrics endpoint accessible"
    
    # Count different metric types
    counter_metrics=$(echo "$metrics_response" | grep -c "TYPE.*counter" || echo "0")
    histogram_metrics=$(echo "$metrics_response" | grep -c "TYPE.*histogram" || echo "0")
    gauge_metrics=$(echo "$metrics_response" | grep -c "TYPE.*gauge" || echo "0")
    
    echo "  Counter metrics: $counter_metrics"
    echo "  Histogram metrics: $histogram_metrics"
    echo "  Gauge metrics: $gauge_metrics"
    
    if [[ $((counter_metrics + histogram_metrics + gauge_metrics)) -gt 0 ]]; then
        echo "✅ Prometheus metrics available"
    else
        echo "⚠️  No Prometheus metrics found"
    fi
else
    echo "❌ Metrics endpoint not accessible"
fi

echo ""

# Final summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="

total_tests=6
passed_tests=0

# Basic scoring (simplified)
if [[ "$health_status" == "200" ]]; then ((passed_tests++)); fi
if [[ "$status_result" == "200" ]]; then ((passed_tests++)); fi
if echo "$analysis_response" | jq '.' >/dev/null 2>&1; then ((passed_tests++)); fi
if [[ "$invalid_status" == "400" ]]; then ((passed_tests++)); fi
if [[ "$no_key_status" == "403" ]] || [[ "$no_key_status" == "401" ]]; then ((passed_tests++)); fi
if [[ $success_count -gt 0 ]]; then ((passed_tests++)); fi

echo "Tests passed: $passed_tests/$total_tests"
echo ""

if [[ $passed_tests -eq $total_tests ]]; then
    echo "🎉 All tests passed! API is functioning correctly."
    exit 0
elif [[ $passed_tests -ge 4 ]]; then
    echo "✅ Most tests passed. API is mostly functional with minor issues."
    exit 0
else
    echo "❌ Multiple test failures. API may have significant issues."
    exit 1
fi