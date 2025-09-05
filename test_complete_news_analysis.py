#!/usr/bin/env python3
"""Complete test van het nieuws analyse systeem met echte links en OpenAI."""

import asyncio
import os
from app.services.news_service import NewsService
from app.core.config import settings

async def test_complete_news_analysis():
    """Test complete nieuws analyse workflow."""
    
    # Check configuratie
    print("🔍 Configuratie Check:")
    print(f"Google Search API: {'✓' if settings.GOOGLE_SEARCH_API_KEY else '✗'}")
    print(f"OpenAI API: {'✓' if settings.OPENAI_API_KEY else '✗'}")
    
    if not settings.GOOGLE_SEARCH_API_KEY or not settings.OPENAI_API_KEY:
        print("❌ Configuratie incompleet - beide API keys zijn vereist")
        return
    
    print("\n🤖 Initialiseren NewsService...")
    
    try:
        news_service = NewsService()
        print("✅ NewsService geïnitialiseerd")
    except Exception as e:
        print(f"❌ Fout bij initialiseren NewsService: {e}")
        return
    
    # Test bedrijven
    test_companies = [
        {"name": "ASML", "contact": None},
        {"name": "Shell", "contact": None},
        {"name": "ING Bank", "contact": None}
    ]
    
    for company_info in test_companies:
        company_name = company_info["name"] 
        contact_person = company_info["contact"]
        
        print(f"\n📊 Analyseren: {company_name}")
        print("=" * 50)
        
        search_params = {
            "date_range": "6m",
            "include_positive": True,
            "include_negative": True
        }
        
        try:
            # Volledige nieuws analyse
            analysis = await news_service.search_company_news(
                company_name=company_name,
                search_params=search_params,
                contact_person=contact_person
            )
            
            print(f"📈 Overall Sentiment: {analysis.overall_sentiment:.2f}")
            print(f"🔗 Artikelen gevonden: {analysis.total_articles_found}")
            print(f"⭐ Gemiddelde relevantie: {analysis.total_relevance:.2f}")
            
            # Sentiment verdeling
            sentiment_summary = analysis.sentiment_summary
            print(f"📊 Sentiment verdeling:")
            print(f"   Positief: {sentiment_summary['positive']:.1f}%")
            print(f"   Neutraal: {sentiment_summary['neutral']:.1f}%")
            print(f"   Negatief: {sentiment_summary['negative']:.1f}%")
            
            # Toon goed nieuws
            if analysis.positive_news.articles:
                print(f"\n✅ GOED NIEUWS ({analysis.positive_news.count} artikelen):")
                for i, article in enumerate(analysis.positive_news.articles[:3], 1):
                    print(f"   {i}. {article.title[:80]}...")
                    print(f"      📊 Sentiment: {article.sentiment_score:.2f} | Relevantie: {article.relevance_score:.2f}")
                    print(f"      📰 Bron: {article.source}")
                    print(f"      🔗 {article.url}")
                    print(f"      📝 {article.summary[:100]}...")
                    print()
            
            # Toon slecht nieuws
            if analysis.negative_news.articles:
                print(f"❌ SLECHT NIEUWS ({analysis.negative_news.count} artikelen):")
                for i, article in enumerate(analysis.negative_news.articles[:3], 1):
                    print(f"   {i}. {article.title[:80]}...")
                    print(f"      📊 Sentiment: {article.sentiment_score:.2f} | Relevantie: {article.relevance_score:.2f}")
                    print(f"      📰 Bron: {article.source}")
                    print(f"      🔗 {article.url}")
                    print(f"      📝 {article.summary[:100]}...")
                    print()
            
            # Key topics en risk indicators
            if analysis.key_topics:
                print(f"🏷️  Key Topics: {', '.join(analysis.key_topics)}")
            
            if analysis.risk_indicators:
                print(f"⚠️  Risk Indicators: {', '.join(analysis.risk_indicators)}")
            
            print(f"\n📝 Samenvatting: {analysis.summary}")
            
        except Exception as e:
            print(f"❌ Fout bij analyseren {company_name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Toon usage statistieken
    print(f"\n📊 USAGE STATISTIEKEN:")
    stats = news_service.get_usage_stats()
    print(f"🔄 Totaal requests: {stats['total_requests']}")
    print(f"🎯 Input tokens: {stats['total_input_tokens']}")
    print(f"📤 Output tokens: {stats['total_output_tokens']}")
    print(f"💰 Geschatte kosten: ${stats['estimated_cost_usd']}")

if __name__ == "__main__":
    asyncio.run(test_complete_news_analysis())