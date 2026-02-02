"""
JOB HUNTER v3.1 - Pracuj.pl Test (Simplified)

Prosty test scrapingu Pracuj.pl z VPN
"""

import sys
import os

# Dodaj ścieżki
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Pracuj-pl-Scraper'))

from scraper import PracujScraper
from curl_cffi.requests import AsyncSession
import asyncio


async def test_scraper():
    """Test scrapera"""
    print("=" * 100)
    print("🔍 TEST JOB HUNTER - Pracuj.pl")
    print("=" * 100)
    
    scraper = PracujScraper()
    
    print("\n📡 Scraping: 'dyrektor sprzedaży FMCG'...")
    
    async with AsyncSession() as client:
        results = await scraper.scrape_keyword(
            client,
            "dyrektor sprzedaży FMCG",
            max_pages=1
        )
        
        print(f"\n✅ Znaleziono {len(results)} ofert\n")
        
        for idx, offer in enumerate(results[:5], 1):
            print(f"{idx}. {offer['Title']}")
            print(f"   Firma: {offer['Company']}")
            print(f"   Lokalizacja: {offer['Location']}")
            print(f"   Link: {offer['Link']}")
            print()


if __name__ == "__main__":
    asyncio.run(test_scraper())
