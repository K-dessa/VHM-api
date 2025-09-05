#!/usr/bin/env python3
"""Final test voor Nederlandse Philips analyse."""

import asyncio
import json
from app.api.endpoints.analyze import nederlands_bedrijf_analyse
from app.models.request_models import CompanyAnalysisRequest
from fastapi import Response
from unittest.mock import MagicMock

async def test_nederlands_endpoint():
    """Test Nederlandse endpoint direct."""
    
    print("🧪 FINAL TEST: Nederlandse Bedrijfsanalyse Endpoint")
    print("=" * 60)
    
    # Mock de authentication
    auth_data = ("test-api-key", {"requests_remaining": 100})
    
    # Create request
    request = CompanyAnalysisRequest(
        company_name="Koninklijke Philips N.V.",
        kvk_nummer="17001910", 
        contactpersoon="Roy Jakobs"
    )
    
    # Mock response object
    response = MagicMock(spec=Response)
    response.headers = {}
    
    print(f"🏢 Bedrijf: {request.company_name}")
    print(f"🆔 KvK: {request.kvk_nummer}")
    print(f"👤 Contact: {request.contactpersoon}")
    print()
    
    try:
        # Call the endpoint
        result = await nederlands_bedrijf_analyse(request, response, auth_data)
        
        print("📊 RESULTATEN:")
        print("-" * 30)
        print(f"✅ Goed nieuws: {len(result.goed_nieuws)}")
        print(f"❌ Slecht nieuws: {len(result.slecht_nieuws)}")
        print(f"📝 Samenvatting: {result.samenvatting}")
        
        if result.goed_nieuws:
            print(f"\n📈 GOED NIEUWS:")
            for i, item in enumerate(result.goed_nieuws, 1):
                print(f"   {i}. {item.titel}")
                print(f"      🔗 {item.link}")
                print()
        
        if result.slecht_nieuws:
            print(f"📉 SLECHT NIEUWS:")
            for i, item in enumerate(result.slecht_nieuws, 1):
                print(f"   {i}. {item.titel}")
                print(f"      🔗 {item.link}")
                print()
        
        # Check voor duplicaten
        all_links = [item.link for item in result.goed_nieuws + result.slecht_nieuws]
        unique_links = set(all_links)
        if len(all_links) != len(unique_links):
            print(f"⚠️  DUPLICATEN GEVONDEN: {len(all_links)} total, {len(unique_links)} unique")
        else:
            print(f"✅ GEEN DUPLICATEN: Alle {len(all_links)} links zijn uniek")
        
        # Check Roy Jakobs mentions
        jakobs_mentions = 0
        for item in result.goed_nieuws + result.slecht_nieuws:
            if "roy jakobs" in item.titel.lower() or "jakobs" in item.titel.lower():
                jakobs_mentions += 1
        print(f"👤 Roy Jakobs vermeld in {jakobs_mentions} artikelen")
        
        print(f"\n🎯 OVERALL SCORE:")
        total_articles = len(result.goed_nieuws) + len(result.slecht_nieuws)
        if total_articles >= 3:
            print(f"✅ SUCCES: {total_articles} artikelen gevonden (verbetering t.o.v. 1-2)")
        else:
            print(f"⚠️  BEPERKT: Slechts {total_articles} artikelen")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_nederlands_endpoint())