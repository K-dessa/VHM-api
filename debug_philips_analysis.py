#!/usr/bin/env python3
"""Debug Philips analyse om te zien waar het fout gaat."""

import asyncio
from app.services.news_service import NewsService
from app.core.config import settings

async def debug_philips():
    """Debug Philips analyse stap voor stap."""
    
    print("🔍 DEBUG: Philips Analysis")
    print("=" * 50)
    
    if not settings.GOOGLE_SEARCH_API_KEY or not settings.OPENAI_API_KEY:
        print("❌ APIs niet geconfigureerd")
        return
    
    try:
        news_service = NewsService()
        
        company = "Koninklijke Philips N.V."
        contact_person = "Roy Jakobs"
        
        print(f"🏢 Analyseren: {company}")
        print(f"👤 Contactpersoon: {contact_person}")
        print()
        
        search_params = {
            'date_range': '90d',
            'include_positive': True,
            'include_negative': True,
            'search_depth': 'deep',
            'prioritize_dutch_sources': True
        }
        
        # Stap 1: Kijk wat Google search oplevert
        print("📍 STAP 1: Google Search Results")
        print("-" * 30)
        
        # Test positive search
        pos_results = await news_service.web_search.search_news(
            f"{company} positive news success achievements growth expansion", 
            max_results=5
        )
        print(f"✅ Positieve zoekterm: {len(pos_results)} artikelen gevonden")
        for i, article in enumerate(pos_results, 1):
            print(f"   {i}. {article['title'][:60]}...")
            print(f"      🔗 {article['url']}")
        
        # Test negative search  
        neg_results = await news_service.web_search.search_news(
            f"{company} negative news problems lawsuit scandal investigation",
            max_results=5
        )
        print(f"\n❌ Negatieve zoekterm: {len(neg_results)} artikelen gevonden")
        for i, article in enumerate(neg_results, 1):
            print(f"   {i}. {article['title'][:60]}...")
            print(f"      🔗 {article['url']}")
        
        print(f"\n📍 STAP 2: Volledige NewsService Analyse")
        print("-" * 30)
        
        # Volledige analyse 
        analysis = await news_service.search_company_news(
            company_name=company,
            search_params=search_params,
            contact_person=contact_person
        )
        
        print(f"📊 Totaal gevonden: {analysis.total_articles_found}")
        print(f"📈 Overall sentiment: {analysis.overall_sentiment:.2f}")
        print(f"📊 Positief: {analysis.positive_news.count}")
        print(f"📊 Negatief: {analysis.negative_news.count}")
        
        print(f"\n📍 STAP 3: Detailanalyse Positieve Artikelen")
        print("-" * 30)
        if analysis.positive_news.articles:
            for i, article in enumerate(analysis.positive_news.articles, 1):
                print(f"{i}. {article.title[:80]}...")
                print(f"   📊 Sentiment: {article.sentiment_score:.2f} | Relevance: {article.relevance_score:.2f}")
                print(f"   🔗 {article.url}")
                # Check contactpersoon
                if contact_person.lower() in article.title.lower():
                    print(f"   👤 CONTACTPERSOON GEVONDEN!")
                print()
        else:
            print("❌ Geen positieve artikelen na filtering!")
        
        print(f"📍 STAP 4: Detailanalyse Negatieve Artikelen")  
        print("-" * 30)
        if analysis.negative_news.articles:
            for i, article in enumerate(analysis.negative_news.articles, 1):
                print(f"{i}. {article.title[:80]}...")
                print(f"   📊 Sentiment: {article.sentiment_score:.2f} | Relevance: {article.relevance_score:.2f}")
                print(f"   🔗 {article.url}")
                # Check contactpersoon
                if contact_person.lower() in article.title.lower():
                    print(f"   👤 CONTACTPERSOON GEVONDEN!")
                print()
        else:
            print("❌ Geen negatieve artikelen na filtering!")
            
        print(f"\n🔍 DIAGNOSE:")
        total_articles = analysis.positive_news.count + analysis.negative_news.count
        if total_articles < 3:
            print(f"⚠️  PROBLEEM: Slechts {total_articles} artikelen na filtering")
            print("🔧 MOGELIJKE OORZAKEN:")
            print("   - OpenAI geeft lage relevance scores")
            print("   - Artikelen bevatten weinig content") 
            print("   - Search query te specifiek")
        else:
            print(f"✅ GOED: {total_articles} artikelen na filtering")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_philips())