#!/usr/bin/env python3
"""Test de verbeterde article filtering."""

import asyncio
from app.services.news_service import NewsService
from app.core.config import settings

async def test_improved_filtering():
    """Test de verbeteringen in article filtering."""
    
    print("🔧 Testing Improved Article Filtering")
    print("=" * 50)
    
    if not settings.GOOGLE_SEARCH_API_KEY or not settings.OPENAI_API_KEY:
        print("❌ APIs niet geconfigureerd")
        return
    
    try:
        news_service = NewsService()
        
        # Test bedrijven
        test_companies = ["ING Bank", "Shell", "ASML"]
        
        for company in test_companies:
            print(f"\n📊 Testing: {company}")
            print("-" * 30)
            
            search_params = {
                "date_range": "6m",
                "include_positive": True, 
                "include_negative": True
            }
            
            # Voer volledige analyse uit
            analysis = await news_service.search_company_news(
                company_name=company,
                search_params=search_params
            )
            
            print(f"🔢 Totaal artikelen gevonden: {analysis.total_articles_found}")
            print(f"📊 Overall sentiment: {analysis.overall_sentiment:.2f}")
            
            # Toon positieve artikelen
            pos_count = analysis.positive_news.count
            if pos_count > 0:
                print(f"\n✅ POSITIEVE ARTIKELEN ({pos_count}):")
                for i, article in enumerate(analysis.positive_news.articles[:5], 1):
                    print(f"   {i}. {article.title[:80]}...")
                    print(f"      📊 Sentiment: {article.sentiment_score:.2f} | Relevantie: {article.relevance_score:.2f}")
                    print(f"      📰 {article.source} | 🔗 {article.url}")
                    print()
            
            # Toon negatieve artikelen  
            neg_count = analysis.negative_news.count
            if neg_count > 0:
                print(f"❌ NEGATIEVE ARTIKELEN ({neg_count}):")
                for i, article in enumerate(analysis.negative_news.articles[:5], 1):
                    print(f"   {i}. {article.title[:80]}...")
                    print(f"      📊 Sentiment: {article.sentiment_score:.2f} | Relevantie: {article.relevance_score:.2f}")  
                    print(f"      📰 {article.source} | 🔗 {article.url}")
                    print()
            
            total_articles = pos_count + neg_count
            print(f"📈 RESULTAAT: {total_articles} artikelen (was voorheen vaak 1)")
            
            # Controleer of we genoeg artikelen hebben
            if total_articles >= 3:
                print("✅ VERBETERING SUCCESVOL: Meer artikelen dan voorheen!")
            else:
                print("⚠️ NOG STEEDS WEINIG ARTIKELEN - mogelijk verdere aanpassing nodig")
            
            print("\n" + "="*50)
    
    except Exception as e:
        print(f"❌ Error tijdens test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_improved_filtering())