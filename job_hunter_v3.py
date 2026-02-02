"""
JOB HUNTER v3.0 - Pracuj.pl Edition (Smart Filters)

Automatyczny system wyszukiwania i analizy ofert pracy z Pracuj.pl.

Workflow:
1. Scraping ofert z Pracuj.pl (z zaawansowanymi filtrami URL)
2. Filtrowanie według kryteriów (lokalizacja, poziom, wynagrodzenie)
3. Scoring dopasowania do CV (0-100%)
4. Dodanie do bazy Job Crusher
5. Utworzenie katalogu dla ofert >70%

UWAGA: Używa opóźnień 10s między ofertami (rate limiting)
"""

import sys
import os
from datetime import datetime
from pathlib import Path
import asyncio

# Dodaj ścieżki do importów
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Pracuj-pl-Scraper'))

from scraper import PracujScraper
from get_offer_details import get_offer_details
from curl_cffi.requests import AsyncSession
from db_manager import add_offer, update_offer, get_conn


# ===== KONFIGURACJA =====
CV_MOJE_PATH = Path(r'c:\Users\pawel\OneDrive\python git 2501\Officer\03_FREELANCE_Labs\Job_Crusher\CV Moje')
CV_BASE_PATH = CV_MOJE_PATH / '_pliki_Bazowe'

# Precyzyjne wyszukiwania (mniej wyników, lepsza jakość)
SEARCH_QUERIES = [
    {
        'keyword': 'dyrektor sprzedaży FMCG',
        'description': 'Dyrektor sprzedaży w FMCG'
    },
    {
        'keyword': 'commercial director retail',
        'description': 'Commercial Director w Retail'
    },
    {
        'keyword': 'head of sales',
        'description': 'Head of Sales'
    },
]

# Hard filters
ALLOWED_LOCATIONS = [
    "warszawa", "warsaw", "mazowieckie", "remote", "zdalna", "hybrydowa", "hybrid"
]

REQUIRED_LEVELS = [
    "director", "dyrektor", "head of", "vp", "kierownik", "manager"
]

EXCLUDED_KEYWORDS = [
    "junior", "młodszy", "assistant", "asystent", "coordinator", "koordynator",
    "specialist", "specjalista", "praktykant", "intern", "stażysta"
]

MIN_SALARY_PLN = 12000  # PLN brutto/mies


# ===== FUNKCJE POMOCNICZE =====

def check_location(location: str, work_modes: list) -> bool:
    """Sprawdza czy lokalizacja spełnia kryteria"""
    location_lower = str(location).lower()
    
    # Sprawdź tryby pracy
    for mode in work_modes:
        mode_lower = str(mode).lower()
        if any(allowed in mode_lower for allowed in ['remote', 'zdalna', 'hybrid', 'hybrydowa']):
            return True
    
    # Sprawdź lokalizację
    if any(loc in location_lower for loc in ALLOWED_LOCATIONS):
        return True
    
    return False


def check_position_level(title: str) -> bool:
    """Sprawdza czy poziom stanowiska jest odpowiedni"""
    title_lower = title.lower()
    
    # Wykluczenia
    for excluded in EXCLUDED_KEYWORDS:
        if excluded in title_lower:
            return False
    
    # Wymagane poziomy
    if any(req in title_lower for req in REQUIRED_LEVELS):
        return True
    
    return False


def extract_salary_pln(salary_str: str) -> int:
    """Wyciąga wartość wynagrodzenia w PLN"""
    if not salary_str or salary_str == "Nie podano":
        return 0
    
    # Usuń spacje i zamień przecinki na kropki
    salary_clean = salary_str.replace(' ', '').replace(',', '.')
    
    # Wyciągnij liczby
    import re
    numbers = re.findall(r'\d+', salary_clean)
    
    if not numbers:
        return 0
    
    # Bierz pierwszą liczbę (zazwyczaj minimum)
    salary = int(numbers[0])
    
    # Jeśli to roczne, podziel przez 12
    if 'rok' in salary_clean.lower() or 'year' in salary_clean.lower():
        salary = salary // 12
    
    return salary


def calculate_cv_match(details: dict) -> dict:
    """
    Oblicza dopasowanie oferty do CV (scoring 0-100%)
    
    Returns:
        dict: {'score': int, 'breakdown': dict, 'verdict': str, 'status': str}
    """
    score = 0
    breakdown = {}
    
    # Przygotuj tekst do analizy
    text_to_analyze = " ".join([
        str(details.get('title', '')),
        str(details.get('description', '')),
        str(details.get('company', '')),
        " ".join(details.get('responsibilities', [])),
        " ".join(details.get('requirements', [])),
    ]).lower()
    
    # 1. FMCG (30 pkt)
    fmcg_keywords = ["fmcg", "fast moving", "consumer goods", "spożywcze", "kosmetyki", "chemia gospodarcza", "retail"]
    fmcg_score = sum(15 if kw in text_to_analyze else 0 for kw in fmcg_keywords[:2])
    breakdown['FMCG'] = min(fmcg_score, 30)
    score += breakdown['FMCG']
    
    # 2. Retail/E-commerce (25 pkt)
    retail_keywords = ["retail", "e-commerce", "sprzedaż detaliczna", "sieci handlowe", "marketplace", "kanały sprzedaży"]
    retail_score = sum(12 if kw in text_to_analyze else 0 for kw in retail_keywords[:2])
    breakdown['Retail'] = min(retail_score, 25)
    score += breakdown['Retail']
    
    # 3. Zarządzanie zespołem (20 pkt)
    team_keywords = ["team management", "people management", "zarządzanie zespołem", "budowanie zespołu", "lider", "zespół", "zarządzanie ludźmi"]
    team_score = sum(10 if kw in text_to_analyze else 0 for kw in team_keywords[:2])
    breakdown['Team Management'] = min(team_score, 20)
    score += breakdown['Team Management']
    
    # 4. Analityka (15 pkt)
    analytics_keywords = ["data analysis", "analytics", "excel", "power bi", "sql", "raportowanie", "analityczne", "dane"]
    analytics_score = sum(7 if kw in text_to_analyze else 0 for kw in analytics_keywords[:2])
    breakdown['Analytics'] = min(analytics_score, 15)
    score += breakdown['Analytics']
    
    # 5. Język angielski (10 pkt)
    english_keywords = ["english", "angielski", "b2", "c1", "fluent", "biegły"]
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
    company = str(details.get('company', 'Unknown')).replace('/', '-').replace('\\', '-')
    title = str(details.get('title', 'Unknown'))[:50].replace('/', '-').replace('\\', '-')
    date = datetime.now().strftime("%Y-%m-%d")
    
    folder_name = f"{date} ( {company} ) {title}"
    folder_path = CV_MOJE_PATH / folder_name
    
    # Utwórz katalog
    folder_path.mkdir(exist_ok=True)
    
    # 1. Szczegóły oferty
    offer_md = f"""# {details.get('title', 'Unknown')}

## 🏢 Informacje podstawowe
- **Firma:** {details.get('company', 'Unknown')}
- **Lokalizacja:** {details.get('location', 'Unknown')}
- **Wynagrodzenie:** {details.get('salary', 'Nie podano')}
- **Typ umowy:** {', '.join(details.get('contract_types', []))}
- **Tryb pracy:** {', '.join(details.get('work_modes', []))}
- **Link:** {details.get('url', 'Unknown')}

## 📊 Dopasowanie do CV: {match_result['score']}% - {match_result['verdict']}

### Breakdown:
"""
    for category, points in match_result['breakdown'].items():
        offer_md += f"- **{category}:** {points} pkt\n"
    
    # Obowiązki
    if details.get('responsibilities'):
        offer_md += "\n## 📋 Obowiązki\n\n"
        for resp in details['responsibilities']:
            offer_md += f"- {resp}\n"
    
    # Wymagania
    if details.get('requirements'):
        offer_md += "\n## ✅ Wymagania\n\n"
        for req in details['requirements']:
            offer_md += f"- {req}\n"
    
    # Oferujemy
    if details.get('benefits'):
        offer_md += "\n## 🎁 Oferujemy\n\n"
        for benefit in details['benefits']:
            offer_md += f"- {benefit}\n"
    
    # Zapisz plik
    (folder_path / "00_OFERTA.md").write_text(offer_md, encoding='utf-8')
    
    # 2. Analiza
    analysis_md = f"""# Analiza oferty: {details.get('title', 'Unknown')}

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
    notes_md = f"""# Notatki: {details.get('title', 'Unknown')}

## Timeline
- **{date}:** Oferta znaleziona przez Job Hunter v3.0 (Pracuj.pl)

## Kontakt z firmą
- [ ] TODO: Dodaj informacje kontaktowe

## Status aplikacji
- [ ] CV wysłane
- [ ] Odpowiedź otrzymana
- [ ] Rozmowa telefoniczna
- [ ] Spotkanie
"""
    (folder_path / "04_NOTATKI.md").write_text(notes_md, encoding='utf-8')
    
    print(f"   ✅ Utworzono katalog: {folder_name}")
    return folder_path


# ===== GŁÓWNA FUNKCJA =====

async def job_hunter():
    """Główna funkcja Job Hunter v3.0"""
    print("=" * 100)
    print("🔍 JOB HUNTER v3.0 - Pracuj.pl Edition (Smart Filters)")
    print("=" * 100)
    
    scraper = PracujScraper()
    all_offers = []
    
    # 1. Scraping ofert z Pracuj.pl
    print(f"\n📡 Scraping ofert z Pracuj.pl...")
    print(f"Zapytania: {len(SEARCH_QUERIES)}\n")
    
    async with AsyncSession() as client:
        for query in SEARCH_QUERIES:
            print(f"🔍 {query['description']}...")
            
            try:
                results = await scraper.scrape_keyword(
                    client,
                    query['keyword'],
                    max_pages=2  # Tylko 2 strony (max ~50 ofert)
                )
                
                if results:
                    print(f"   ✅ Znaleziono {len(results)} ofert")
                    all_offers.extend(results)
                else:
                    print(f"   ⚠️ Brak wyników")
                    
            except Exception as e:
                print(f"   ❌ Błąd: {str(e)}")
    
    if not all_offers:
        print("\n❌ Nie znaleziono żadnych ofert!")
        return
    
    # Usuń duplikaty (po Link)
    unique_offers = {offer['Link']: offer for offer in all_offers}.values()
    all_offers = list(unique_offers)
    
    print(f"\n✅ Łącznie znaleziono {len(all_offers)} unikalnych ofert (przed filtrowaniem)")
    print(f"⚠️ Pobieranie szczegółów z opóźnieniem 10s (rate limiting)...\n")
    
    # 2. Filtrowanie i analiza
    filtered_offers = []
    
    for idx, offer in enumerate(all_offers, 1):
        print(f"[{idx}/{len(all_offers)}] {offer['Title'][:60]}...")
        
        # Opóźnienie między requestami (rate limiting)
        if idx > 1:
            await asyncio.sleep(10)  # 10s opóźnienia
        
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
        if not check_position_level(details['title']):
            print(f"   ❌ Poziom stanowiska")
            continue
        
        # Wynagrodzenie (jeśli podane)
        salary_pln = extract_salary_pln(details['salary'])
        if salary_pln > 0 and salary_pln < MIN_SALARY_PLN:
            print(f"   ❌ Wynagrodzenie: {salary_pln:,.0f} PLN (min: {MIN_SALARY_PLN:,.0f} PLN)")
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
    
    print(f"\n✅ Po filtrowaniu: {len(filtered_offers)} ofert\n")
    
    if not filtered_offers:
        print("❌ Brak ofert spełniających kryteria!")
        return
    
    # 3. Sortuj według score
    filtered_offers.sort(key=lambda x: x['match']['score'], reverse=True)
    
    # 4. Dodaj do bazy i utwórz katalogi
    for item in filtered_offers:
        details = item['details']
        match = item['match']
        
        print("=" * 100)
        print(f"📊 {match['verdict']} - {match['score']}%")
        print(f"🏢 {details.get('company', 'Unknown')}")
        print(f"💼 {details.get('title', 'Unknown')}")
        print(f"📍 {details.get('location', 'Unknown')}")
        
        # Dodaj do bazy
        add_offer(
            details.get('company', 'Unknown'),
            details.get('title', 'Unknown'),
            details.get('location', 'Unknown'),
            details.get('url', ''),
            match['status']
        )
        
        # Pobierz ID oferty
        with get_conn() as conn:
            offer_id = conn.execute("""
                SELECT o.id FROM offers o 
                JOIN companies c ON o.company_id = c.id 
                WHERE c.name = ? AND o.title = ? 
                ORDER BY o.added_at DESC LIMIT 1
            """, (details.get('company', 'Unknown'), details.get('title', 'Unknown'))).fetchone()[0]
        
        # Dodaj notatki
        notes = f"Scoring: {match['score']}% - {match['verdict']}\n"
        for cat, pts in match['breakdown'].items():
            notes += f"{cat}: {pts} pkt\n"
        notes += f"\nŹródło: Pracuj.pl\n"
        notes += f"Wynagrodzenie: {details.get('salary', 'Nie podano')}\n"
        
        update_offer(offer_id, note=notes)
        
        # Utwórz katalog dla ofert >70%
        if match['score'] >= 70:
            create_offer_folder(details, match)
        
        print("=" * 100)
        print()
    
    print(f"\n🎉 Job Hunter v3.0 zakończony! Znaleziono {len(filtered_offers)} dopasowanych ofert.")


if __name__ == "__main__":
    asyncio.run(job_hunter())
