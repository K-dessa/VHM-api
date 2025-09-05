#!/usr/bin/env python3
"""Snelle test van het nieuws analyse systeem."""

import asyncio
from app.services.news_service import NewsService
from app.core.config import settings

async def test_quick_analysis():
    """Test snelle nieuws analyse."""
    
    print("🔍 Quick Analysis Test")
    print(f"Google Search API: {'✓' if settings.GOOGLE_SEARCH_API_KEY else '✗'}")
    print(f"OpenAI API: {'✓' if settings.OPENAI_API_KEY else '✗'}")
    
    if not settings.GOOGLE_SEARCH_API_KEY or not settings.OPENAI_API_KEY:
        print("❌ APIs niet geconfigureerd")
        return
    
    try:
        news_service = NewsService()
        
        # Test met beperkt aantal resultaten voor snelheid
        search_params = {
            "date_range": "6m",
            "include_positive": True,
            "include_negative": True
        }
        
        company = "Shell"
        print(f"\n📊 Analyseren: {company}")
        
        # Direct search met beperkte resultaten
        results = await news_service.web_search.search_news(f"{company} nieuws", max_results=3)
        print(f"🔍 Gevonden {len(results)} artikelen")
        
        # Test volledige analyse met beperkt aantal
        if results:
            for i, article in enumerate(results, 1):
                print(f"\n📰 Artikel {i}:")
                print(f"   Titel: {article['title'][:80]}...")
                print(f"   Bron: {article['source']}")
                print(f"   URL: {article['url']}")
                print(f"   Content length: {len(article.get('content', ''))} karakters")
                
                # Test OpenAI analyse van eerste artikel
                if i == 1 and article.get('content'):
                    analyzed = await news_service._analyze_article(article, company)
                    if analyzed:
                        print(f"   🤖 OpenAI Sentiment: {analyzed.sentiment_score}")
                        print(f"   🎯 Relevance: {analyzed.relevance_score}")
                        print(f"   📝 Summary: {analyzed.summary[:100]}...")
        
        print(f"\n✅ Test voltooid voor {company}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_quick_analysis())