#!/usr/bin/env python3

"""
Quick test script for the new company name-based API
"""

import requests
import json
import os
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000"
API_KEY = "test-api-key-12345678901234567890"

def test_health():
    """Test the health endpoint"""
    print("🩺 Testing health endpoint...")
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Health check passed")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_company_analysis():
    """Test the company analysis endpoint"""
    print("\n🏢 Testing company analysis...")
    
    payload = {
        "company_name": "ASML Holding N.V.",
        "search_depth": "standard",
        "news_date_range": "last_year",
        "legal_date_range": "last_3_years",
        "include_subsidiaries": False
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    print(f"📝 Request payload:")
    print(json.dumps(payload, indent=2))
    
    try:
        print(f"🚀 Sending request to {API_BASE_URL}/analyze-company...")
        start_time = datetime.now()
        
        response = requests.post(
            f"{API_BASE_URL}/analyze-company", 
            json=payload, 
            headers=headers,
            timeout=70
        )
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        print(f"⏱️  Request took {processing_time:.2f} seconds")
        print(f"📊 HTTP Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Analysis successful!")
            
            # Print key information
            print(f"📋 Request ID: {data.get('request_id', 'N/A')}")
            print(f"🏢 Company Name: {data.get('company_info', {}).get('name', 'N/A')}")
            print(f"⚠️  Risk Level: {data.get('risk_assessment', {}).get('overall_risk_level', 'N/A')}")
            print(f"📊 Risk Score: {data.get('risk_assessment', {}).get('risk_score', 'N/A')}")
            print(f"📰 Data Sources: {', '.join(data.get('data_sources', []))}")
            
            # Print warnings if any
            warnings = data.get('warnings', [])
            if warnings:
                print(f"⚠️  Warnings:")
                for warning in warnings[:3]:  # Show first 3 warnings
                    print(f"   - {warning}")
            
            # Print risk factors
            risk_factors = data.get('risk_assessment', {}).get('risk_factors', [])
            if risk_factors:
                print(f"🚨 Risk Factors:")
                for factor in risk_factors[:3]:  # Show first 3 factors
                    print(f"   - {factor}")
            
            return True
        elif response.status_code == 500:
            print("❌ Server error - likely OpenAI API key not configured")
            print(f"💬 Response: {response.text}")
            return False
        else:
            print(f"❌ Analysis failed: {response.status_code}")
            print(f"💬 Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out (>70s)")
        return False
    except Exception as e:
        print(f"❌ Analysis error: {e}")
        return False

def test_invalid_input():
    """Test with invalid input"""
    print("\n🚫 Testing invalid input...")
    
    payload = {
        "company_name": "X"  # Too short
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/analyze-company", 
            json=payload, 
            headers=headers
        )
        
        if response.status_code == 400:
            print("✅ Invalid input properly rejected")
            return True
        else:
            print(f"❌ Expected 400, got {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Testing New Company Name-Based API")
    print("=" * 50)
    
    # Check if OpenAI API key is configured
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        print("⚠️  Warning: OPENAI_API_KEY not found in environment")
        print("   The news analysis service will not work without it")
        print()
    else:
        print(f"✅ OpenAI API key found (starts with: {openai_key[:10]}...)")
        print()
    
    results = []
    
    # Run tests
    results.append(("Health Check", test_health()))
    results.append(("Company Analysis", test_company_analysis()))
    results.append(("Invalid Input", test_invalid_input()))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<20} {status}")
        if result:
            passed += 1
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! API is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    exit(main())