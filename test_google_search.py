#!/usr/bin/env python3
"""Test script for Google Custom Search integration."""

import asyncio
import os
from app.services.news_service import WebSearch
from app.core.config import settings

async def test_google_search():
    """Test Google Custom Search functionality."""
    
    # Check if Google Search is configured
    if not settings.GOOGLE_SEARCH_API_KEY or not settings.GOOGLE_SEARCH_ENGINE_ID:
        print("⚠️ Google Search API niet geconfigureerd in environment variables")
        print(f"GOOGLE_SEARCH_API_KEY: {'✓ aanwezig' if settings.GOOGLE_SEARCH_API_KEY else '✗ ontbreekt'}")
        print(f"GOOGLE_SEARCH_ENGINE_ID: {'✓ aanwezig' if settings.GOOGLE_SEARCH_ENGINE_ID else '✗ ontbreekt'}")
        return False
    
    print("🔍 Google Custom Search API configuratie gevonden")
    print(f"API Key: {settings.GOOGLE_SEARCH_API_KEY[:10]}...")
    print(f"Engine ID: {settings.GOOGLE_SEARCH_ENGINE_ID}")
    
    # Initialize WebSearch
    web_search = WebSearch()
    
    # Test search for a Dutch company
    test_queries = [
        "ASML nieuws",
        "ING Bank financieel",
        "Shell olie"
    ]
    
    for query in test_queries:
        print(f"\n🔎 Zoeken naar: '{query}'")
        try:
            results = await web_search.search_news(query, max_results=5)
            
            if results:
                print(f"✅ Gevonden: {len(results)} artikelen")
                for i, article in enumerate(results, 1):
                    print(f"  {i}. {article['title'][:80]}...")
                    print(f"     Bron: {article['source']}")
                    print(f"     URL: {article['url']}")
                    print(f"     Datum: {article.get('date', 'Onbekend')}")
                    print()
            else:
                print("❌ Geen resultaten gevonden")
                
        except Exception as e:
            print(f"❌ Error bij zoeken: {e}")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_google_search())
    if success:
        print("\n✅ Google Search test voltooid")
    else:
        print("\n❌ Google Search test gefaald - configureer eerst de API keys")