"""
JOB HUNTER - Automatyczny system wyszukiwania i analizy ofert pracy

Workflow:
1. Scraping ofert z Pracuj.pl (keywords)
2. Filtrowanie według kryteriów (lokalizacja, poziom, wynagrodzenie)
3. Scoring dopasowania do CV (0-100%)
4. Dodanie do bazy Job Crusher
5. Utworzenie katalogu dla ofert >70%
"""

import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# Dodaj ścieżki do importów
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Pracuj-pl-Scraper'))
sys.path.insert(0, os.path.dirname(__file__))

from scraper import PracujScraper
from get_offer_details import get_offer_details
from db_manager import add_offer, update_offer, get_conn
from curl_cffi.requests import AsyncSession


# ===== KONFIGURACJA =====
CV_MOJE_PATH = Path(r'c:\Users\pawel\OneDrive\python git 2501\Officer\03_FREELANCE_Labs\Job_Crusher\CV Moje')
CV_BASE_PATH = CV_MOJE_PATH / '_pliki_Bazowe'

# Keywords do wyszukiwania
SEARCH_KEYWORDS = [
    "dyrektor sprzedaży",
    "commercial director",
    "head of sales",
    "dyrektor handlowy",
]

# Hard filters
ALLOWED_LOCATIONS = [
    "warszawa", "praca zdalna", "remote", "hybrydowa"
]

REQUIRED_LEVELS = [
    "dyrektor", "head of", "vp", "senior manager"
]

EXCLUDED_TITLES = [
    "żłobka", "przedszkola", "sklepu", "restauracji", "oddziału"
]

MIN_SALARY = 12000  # PLN brutto


# ===== FUNKCJE POMOCNICZE =====

def check_location(location: str, work_modes: list) -> bool:
    """Sprawdza czy lokalizacja spełnia kryteria"""
    location_lower = location.lower()
    
    # Praca zdalna
    if any(mode in ["praca zdalna", "remote"] for mode in work_modes):
        return True
    
    # Warszawa lub hybrydowa
    if "warszawa" in location_lower:
        return True
    
    if any(mode in ["praca hybrydowa", "hybrid"] for mode in work_modes):
        return True
    
    return False


def check_position_level(title: str, position_levels: list) -> bool:
    """Sprawdza czy poziom stanowiska jest odpowiedni"""
    title_lower = title.lower()
    
    # Wykluczenia
    for excluded in EXCLUDED_TITLES:
        if excluded in title_lower:
            return False
    
    # Wymagane poziomy
    for level in position_levels:
        level_lower = level.lower()
        if any(req in level_lower for req in ["dyrektor", "menedżer"]):
            return True
    
    # Sprawdź tytuł
    if any(req in title_lower for req in REQUIRED_LEVELS):
        return True
    
    return False


def extract_salary(salary_str: str) -> int:
    """Wyciąga wartość wynagrodzenia z tekstu"""
    if not salary_str or salary_str == "Nie podano":
        return 0
    
    # Szukaj liczb w tekście
    import re
    numbers = re.findall(r'\d+[\s\d]*', salary_str.replace(' ', ''))
    if numbers:
        # Bierz pierwszą liczbę (od)
        return int(numbers[0].replace(' ', ''))
    return 0


def calculate_cv_match(details: dict) -> dict:
    """
    Oblicza dopasowanie oferty do CV (scoring 0-100%)
    
    Returns:
        dict: {'score': int, 'breakdown': dict, 'verdict': str}
    """
    score = 0
    breakdown = {}
    
    # Przygotuj tekst do analizy
    text_to_analyze = " ".join([
        details.get('title', ''),
        " ".join(details.get('requirements', [])),
        " ".join(details.get('responsibilities', [])),
        " ".join(details.get('categories', [])),
    ]).lower()
    
    # 1. FMCG (30 pkt)
    fmcg_keywords = ["fmcg", "fast moving", "spożywcze", "kosmetyki", "chemia gospodarcza"]
    fmcg_score = sum(15 if kw in text_to_analyze else 0 for kw in fmcg_keywords[:2])
    breakdown['FMCG'] = min(fmcg_score, 30)
    score += breakdown['FMCG']
    
    # 2. Retail (25 pkt)
    retail_keywords = ["retail", "e-commerce", "sprzedaż detaliczna", "sieci handlowe"]
    retail_score = sum(12 if kw in text_to_analyze else 0 for kw in retail_keywords[:2])
    breakdown['Retail'] = min(retail_score, 25)
    score += breakdown['Retail']
    
    # 3. Zarządzanie zespołem (20 pkt)
    team_keywords = ["zarządzanie zespołem", "budowanie zespołu", "lider", "people management", "zespół"]
    team_score = sum(10 if kw in text_to_analyze else 0 for kw in team_keywords[:2])
    breakdown['Team Management'] = min(team_score, 20)
    score += breakdown['Team Management']
    
    # 4. Analityka (15 pkt)
    analytics_keywords = ["analiza danych", "excel", "power bi", "sql", "raportowanie", "analityczne"]
    analytics_score = sum(7 if kw in text_to_analyze else 0 for kw in analytics_keywords[:2])
    breakdown['Analytics'] = min(analytics_score, 15)
    score += breakdown['Analytics']
    
    # 5. Język angielski (10 pkt)
    english_keywords = ["angielski", "english", "b2", "c1", "fluent"]
    english_score = 10 if any(kw in text_to_analyze for kw in english_keywords) else 0
    breakdown['English'] = english_score
    score += breakdown['English']
    
    # Verdict
    if score >= 90:
        verdict = "🔥 MUST APPLY"
        status = "Lead"
    elif score >= 70:
        verdict = "✅ STRONG MATCH"
        status = "Lead"
    elif score >= 50:
        verdict = "⚠️ MAYBE"
        status = "poczekalnia"
    else:
        verdict = "❌ REJECT"
        status = "Rejected"
    
    return {
        'score': score,
        'breakdown': breakdown,
        'verdict': verdict,
        'status': status
    }


def create_offer_folder(details: dict, match_result: dict):
    """Tworzy katalog dla oferty z plikami"""
    company = details['company'].replace('/', '-').replace('\\', '-')
    title = details['title'][:50].replace('/', '-').replace('\\', '-')
    date = datetime.now().strftime("%Y-%m-%d")
    
    folder_name = f"{date} ( {company} ) {title}"
    folder_path = CV_MOJE_PATH / folder_name
    
    # Utwórz katalog
    folder_path.mkdir(exist_ok=True)
    
    # 1. Szczegóły oferty
    offer_md = f"""# {details['title']}

## 🏢 Informacje podstawowe
- **Firma:** {details['company']}
- **Lokalizacja:** {details['location']} ({details['region']})
- **Wynagrodzenie:** {details['salary']}
- **Poziom:** {', '.join(details['position_levels'])}
- **Tryb pracy:** {', '.join(details['work_modes'])}
- **Umowa:** {', '.join(details['contract_types'])}
- **Link:** {details['url']}

## 📊 Dopasowanie do CV: {match_result['score']}% - {match_result['verdict']}

### Breakdown:
"""
    for category, points in match_result['breakdown'].items():
        offer_md += f"- **{category}:** {points} pkt\n"
    
    offer_md += f"\n## 📋 Obowiązki\n"
    for i, resp in enumerate(details.get('responsibilities', []), 1):
        offer_md += f"{i}. {resp}\n"
    
    offer_md += f"\n## ✅ Wymagania\n"
    for i, req in enumerate(details.get('requirements', []), 1):
        offer_md += f"{i}. {req}\n"
    
    offer_md += f"\n## 🎁 Oferujemy\n"
    for i, off in enumerate(details.get('offered', []), 1):
        offer_md += f"{i}. {off}\n"
    
    offer_md += f"\n## 💎 Benefity\n"
    for i, ben in enumerate(details.get('benefits', []), 1):
        offer_md += f"{i}. {ben}\n"
    
    # Zapisz plik
    (folder_path / "00_OFERTA.md").write_text(offer_md, encoding='utf-8')
    
    # 2. Analiza
    analysis_md = f"""# Analiza oferty: {details['title']}

## Scoring: {match_result['score']}% - {match_result['verdict']}

### Mocne strony:
- [ ] TODO: Wypełnij po przeczytaniu oferty

### Słabe strony:
- [ ] TODO: Wypełnij po przeczytaniu oferty

### Pytania do rekrutera:
- [ ] TODO: Przygotuj pytania

### Decyzja:
- [ ] Aplikować
- [ ] Odrzucić
- [ ] Czekać na więcej informacji
"""
    (folder_path / "01_ANALIZA.md").write_text(analysis_md, encoding='utf-8')
    
    # 3. Notatki
    notes_md = f"""# Notatki: {details['title']}

## Timeline
- **{date}:** Oferta znaleziona przez Job Hunter

## Kontakt z firmą
- [ ] TODO: Dodaj informacje kontaktowe

## Status aplikacji
- [ ] CV wysłane
- [ ] Odpowiedź otrzymana
- [ ] Rozmowa telefoniczna
- [ ] Spotkanie
"""
    (folder_path / "04_NOTATKI.md").write_text(notes_md, encoding='utf-8')
    
    print(f"✅ Utworzono katalog: {folder_name}")
    return folder_path


# ===== GŁÓWNA FUNKCJA =====

async def job_hunter():
    """Główna funkcja Job Hunter"""
    print("=" * 100)
    print("🔍 JOB HUNTER - Automatyczne wyszukiwanie ofert pracy")
    print("=" * 100)
    
    scraper = PracujScraper()
    all_offers = []
    
    # 1. Scraping ofert
    print(f"\n📡 Scraping ofert dla keywords: {SEARCH_KEYWORDS}")
    async with AsyncSession() as client:
        tasks = [scraper.scrape_keyword(client, kw, max_pages=1) for kw in SEARCH_KEYWORDS]
        results = await asyncio.gather(*tasks)
        
        for r in results:
            all_offers.extend(r)
    
    print(f"✅ Znaleziono {len(all_offers)} ofert (przed filtrowaniem)")
    print(f"⚠️ TRYB TESTOWY: Ograniczam do pierwszych 10 ofert\n")
    
    all_offers = all_offers[:10]  # TESTING ONLY
    
    # 2. Filtrowanie i analiza
    filtered_offers = []
    
    print(f"📊 Analizuję oferty (z opóźnieniem 5s między requestami)...\n")
    
    for idx, offer in enumerate(all_offers, 1):
        print(f"[{idx}/{len(all_offers)}] Sprawdzam: {offer['Title'][:60]}...")
        
        # Opóźnienie między requestami (rate limiting)
        if idx > 1:
            await asyncio.sleep(5)  # Zwiększone z 2s do 5s
        
        # Pobierz szczegóły
        try:
            details = await get_offer_details(offer['Link'])
            
            if 'error' in details:
                print(f"   ⚠️ Błąd: {details.get('error', 'Unknown')}")
                continue
        except Exception as e:
            print(f"   ⚠️ Exception: {str(e)}")
            continue
        
        # Hard filters
        # Lokalizacja
        if not check_location(details['location'], details.get('work_modes', [])):
            print(f"   ❌ Lokalizacja: {details['location']}")
            continue
        
        # Poziom stanowiska
        if not check_position_level(details['title'], details.get('position_levels', [])):
            print(f"   ❌ Poziom: {details.get('position_levels', [])}")
            continue
        
        # Wynagrodzenie (jeśli podane)
        salary = extract_salary(details['salary'])
        if salary > 0 and salary < MIN_SALARY:
            print(f"   ❌ Wynagrodzenie: {salary} zł (min: {MIN_SALARY} zł)")
            continue
        
        # Scoring
        match_result = calculate_cv_match(details)
        
        # Odrzuć oferty <50%
        if match_result['score'] < 50:
            print(f"   ❌ Score: {match_result['score']}% (min: 50%)")
            continue
        
        print(f"   ✅ PASS - Score: {match_result['score']}% - {match_result['verdict']}")
        
        # Dodaj do listy
        filtered_offers.append({
            'details': details,
            'match': match_result
        })
    
    print(f"✅ Po filtrowaniu: {len(filtered_offers)} ofert\n")
    
    # 3. Sortuj według score
    filtered_offers.sort(key=lambda x: x['match']['score'], reverse=True)
    
    # 4. Dodaj do bazy i utwórz katalogi
    for item in filtered_offers:
        details = item['details']
        match = item['match']
        
        print("=" * 100)
        print(f"📊 {match['verdict']} - {match['score']}%")
        print(f"🏢 {details['company']}")
        print(f"💼 {details['title']}")
        print(f"📍 {details['location']}")
        print(f"💰 {details['salary']}")
        
        # Dodaj do bazy
        add_offer(
            details['company'],
            details['title'],
            details['location'],
            details['url'],
            match['status']
        )
        
        # Pobierz ID oferty
        with get_conn() as conn:
            offer_id = conn.execute("""
                SELECT o.id FROM offers o 
                JOIN companies c ON o.company_id = c.id 
                WHERE c.name = ? AND o.title = ? 
                ORDER BY o.added_at DESC LIMIT 1
            """, (details['company'], details['title'])).fetchone()[0]
        
        # Dodaj notatki
        notes = f"Scoring: {match['score']}% - {match['verdict']}\n"
        for cat, pts in match['breakdown'].items():
            notes += f"{cat}: {pts} pkt\n"
        
        update_offer(offer_id, note=notes)
        
        # Utwórz katalog dla ofert >70%
        if match['score'] >= 70:
            create_offer_folder(details, match)
        
        print("=" * 100)
        print()
    
    print(f"\n🎉 Job Hunter zakończony! Znaleziono {len(filtered_offers)} dopasowanych ofert.")


if __name__ == "__main__":
    asyncio.run(job_hunter())
