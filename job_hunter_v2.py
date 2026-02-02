"""
JOB HUNTER v2.0 - JobSpy Edition

Automatyczny system wyszukiwania i analizy ofert pracy z LinkedIn, Indeed, Glassdoor.

Workflow:
1. Scraping ofert z JobSpy (LinkedIn, Indeed)
2. Filtrowanie według kryteriów (lokalizacja, poziom, wynagrodzenie)
3. Scoring dopasowania do CV (0-100%)
4. Dodanie do bazy Job Crusher
5. Utworzenie katalogu dla ofert >70%
"""

import sys
import os
from datetime import datetime
from pathlib import Path
import re

# Dodaj ścieżki do importów
sys.path.insert(0, os.path.dirname(__file__))

from jobspy import scrape_jobs
from db_manager import add_offer, update_offer, get_conn


# ===== KONFIGURACJA =====
CV_MOJE_PATH = Path(r'c:\Users\pawel\OneDrive\python git 2501\Officer\03_FREELANCE_Labs\Job_Crusher\CV Moje')
CV_BASE_PATH = CV_MOJE_PATH / '_pliki_Bazowe'

# Keywords do wyszukiwania
SEARCH_TERMS = [
    "commercial director",
    "head of sales",
    "sales director",
]

# Lokalizacje
LOCATIONS = [
    "Warsaw, Poland",
    "Poland",
]

# Hard filters
ALLOWED_WORK_MODES = [
    "remote", "hybrid", "warszawa", "warsaw"
]

REQUIRED_LEVELS = [
    "director", "head of", "vp", "senior manager"
]

EXCLUDED_TITLES = [
    "junior", "mid", "assistant", "coordinator", "specialist"
]

MIN_SALARY_PLN = 12000  # PLN brutto/mies
MIN_SALARY_USD_YEARLY = 50000  # USD/rok


# ===== FUNKCJE POMOCNICZE =====

def check_location(job_data: dict) -> bool:
    """Sprawdza czy lokalizacja spełnia kryteria"""
    location = str(job_data.get('location', '')).lower()
    city = str(job_data.get('city', '')).lower()
    state = str(job_data.get('state', '')).lower()
    is_remote = job_data.get('is_remote', False)
    
    # Praca zdalna
    if is_remote:
        return True
    
    # Warszawa lub Polska
    if any(loc in location or loc in city or loc in state for loc in ['warszawa', 'warsaw', 'poland', 'polska']):
        return True
    
    return False


def check_position_level(title: str) -> bool:
    """Sprawdza czy poziom stanowiska jest odpowiedni"""
    title_lower = title.lower()
    
    # Wykluczenia
    for excluded in EXCLUDED_TITLES:
        if excluded in title_lower:
            return False
    
    # Wymagane poziomy
    if any(req in title_lower for req in REQUIRED_LEVELS):
        return True
    
    return False


def extract_salary_pln(job_data: dict) -> int:
    """Wyciąga wartość wynagrodzenia w PLN"""
    min_amount = job_data.get('min_amount')
    max_amount = job_data.get('max_amount')
    interval = job_data.get('interval', '').lower()
    
    if not min_amount and not max_amount:
        return 0
    
    # Bierz min_amount jeśli dostępne, inaczej max_amount
    amount = min_amount if min_amount else max_amount
    
    # Konwersja do miesięcznego PLN
    if interval == 'yearly':
        # Zakładamy USD -> PLN (4.0) i dzielimy przez 12
        amount_pln = (amount * 4.0) / 12
    elif interval == 'monthly':
        # Już miesięcznie, zakładamy PLN
        amount_pln = amount
    elif interval == 'hourly':
        # Godzinowo -> miesięcznie (160h/mies)
        amount_pln = amount * 160
    else:
        amount_pln = amount
    
    return int(amount_pln)


def calculate_cv_match(job_data: dict) -> dict:
    """
    Oblicza dopasowanie oferty do CV (scoring 0-100%)
    
    Returns:
        dict: {'score': int, 'breakdown': dict, 'verdict': str}
    """
    score = 0
    breakdown = {}
    
    # Przygotuj tekst do analizy
    text_to_analyze = " ".join([
        str(job_data.get('title', '')),
        str(job_data.get('description', '')),
        str(job_data.get('company', '')),
    ]).lower()
    
    # 1. FMCG (30 pkt)
    fmcg_keywords = ["fmcg", "fast moving", "consumer goods", "spożywcze", "kosmetyki", "chemia gospodarcza"]
    fmcg_score = sum(15 if kw in text_to_analyze else 0 for kw in fmcg_keywords[:2])
    breakdown['FMCG'] = min(fmcg_score, 30)
    score += breakdown['FMCG']
    
    # 2. Retail (25 pkt)
    retail_keywords = ["retail", "e-commerce", "sprzedaż detaliczna", "sieci handlowe", "marketplace"]
    retail_score = sum(12 if kw in text_to_analyze else 0 for kw in retail_keywords[:2])
    breakdown['Retail'] = min(retail_score, 25)
    score += breakdown['Retail']
    
    # 3. Zarządzanie zespołem (20 pkt)
    team_keywords = ["team management", "people management", "zarządzanie zespołem", "budowanie zespołu", "lider", "zespół"]
    team_score = sum(10 if kw in text_to_analyze else 0 for kw in team_keywords[:2])
    breakdown['Team Management'] = min(team_score, 20)
    score += breakdown['Team Management']
    
    # 4. Analityka (15 pkt)
    analytics_keywords = ["data analysis", "analytics", "excel", "power bi", "sql", "raportowanie", "analityczne"]
    analytics_score = sum(7 if kw in text_to_analyze else 0 for kw in analytics_keywords[:2])
    breakdown['Analytics'] = min(analytics_score, 15)
    score += breakdown['Analytics']
    
    # 5. Język angielski (10 pkt)
    english_keywords = ["english", "angielski", "b2", "c1", "fluent"]
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


def create_offer_folder(job_data: dict, match_result: dict):
    """Tworzy katalog dla oferty z plikami"""
    company = str(job_data.get('company', 'Unknown')).replace('/', '-').replace('\\', '-')
    title = str(job_data.get('title', 'Unknown'))[:50].replace('/', '-').replace('\\', '-')
    date = datetime.now().strftime("%Y-%m-%d")
    
    folder_name = f"{date} ( {company} ) {title}"
    folder_path = CV_MOJE_PATH / folder_name
    
    # Utwórz katalog
    folder_path.mkdir(exist_ok=True)
    
    # Formatuj wynagrodzenie
    salary_str = "Nie podano"
    if job_data.get('min_amount') or job_data.get('max_amount'):
        min_amt = job_data.get('min_amount', 0)
        max_amt = job_data.get('max_amount', 0)
        interval = job_data.get('interval', 'yearly')
        salary_str = f"{min_amt:,.0f} - {max_amt:,.0f} {interval}" if min_amt and max_amt else f"{max_amt:,.0f} {interval}"
    
    # 1. Szczegóły oferty
    offer_md = f"""# {job_data.get('title', 'Unknown')}

## 🏢 Informacje podstawowe
- **Firma:** {job_data.get('company', 'Unknown')}
- **Lokalizacja:** {job_data.get('location', 'Unknown')} ({job_data.get('city', '')}, {job_data.get('state', '')})
- **Wynagrodzenie:** {salary_str}
- **Typ pracy:** {job_data.get('job_type', 'Unknown')}
- **Remote:** {'Tak' if job_data.get('is_remote') else 'Nie'}
- **Źródło:** {job_data.get('site', 'Unknown')}
- **Link:** {job_data.get('job_url', 'Unknown')}
- **Data publikacji:** {job_data.get('date_posted', 'Unknown')}

## 📊 Dopasowanie do CV: {match_result['score']}% - {match_result['verdict']}

### Breakdown:
"""
    for category, points in match_result['breakdown'].items():
        offer_md += f"- **{category}:** {points} pkt\n"
    
    offer_md += f"\n## 📋 Opis stanowiska\n\n{job_data.get('description', 'Brak opisu')}\n"
    
    # Zapisz plik
    (folder_path / "00_OFERTA.md").write_text(offer_md, encoding='utf-8')
    
    # 2. Analiza
    analysis_md = f"""# Analiza oferty: {job_data.get('title', 'Unknown')}

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
    notes_md = f"""# Notatki: {job_data.get('title', 'Unknown')}

## Timeline
- **{date}:** Oferta znaleziona przez Job Hunter v2.0 (JobSpy)

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

def job_hunter():
    """Główna funkcja Job Hunter v2.0"""
    print("=" * 100)
    print("🔍 JOB HUNTER v2.0 - JobSpy Edition")
    print("=" * 100)
    
    all_jobs = []
    
    # 1. Scraping ofert z JobSpy
    print(f"\n📡 Scraping ofert z Indeed (LinkedIn wymaga proxy)...")
    print(f"Keywords: {SEARCH_TERMS}")
    print(f"Lokalizacje: {LOCATIONS}\n")
    
    for search_term in SEARCH_TERMS:
        for location in LOCATIONS:
            print(f"🔍 Szukam: '{search_term}' w '{location}'...")
            
            try:
                jobs = scrape_jobs(
                    site_name=["indeed"],  # Tylko Indeed (bez rate limitingu)
                    search_term=search_term,
                    location=location,
                    results_wanted=50,  # Więcej wyników z Indeed
                    is_remote=True,
                    country_indeed='Poland',
                )
                
                if jobs is not None and len(jobs) > 0:
                    print(f"   ✅ Znaleziono {len(jobs)} ofert")
                    all_jobs.append(jobs)
                else:
                    print(f"   ⚠️ Brak wyników")
                    
            except Exception as e:
                print(f"   ❌ Błąd: {str(e)}")
    
    if not all_jobs:
        print("\n❌ Nie znaleziono żadnych ofert!")
        return
    
    # Połącz wszystkie DataFrames
    import pandas as pd
    df_all = pd.concat(all_jobs, ignore_index=True)
    
    # Usuń duplikaty (po job_url)
    df_all = df_all.drop_duplicates(subset=['job_url'], keep='first')
    
    print(f"\n✅ Łącznie znaleziono {len(df_all)} unikalnych ofert (przed filtrowaniem)\n")
    
    # 2. Filtrowanie i analiza
    filtered_jobs = []
    
    print(f"📊 Analizuję oferty...\n")
    
    for idx, row in df_all.iterrows():
        job_data = row.to_dict()
        
        print(f"[{idx+1}/{len(df_all)}] {job_data.get('title', 'Unknown')[:60]}...")
        
        # Hard filters
        # Lokalizacja
        if not check_location(job_data):
            print(f"   ❌ Lokalizacja: {job_data.get('location', 'Unknown')}")
            continue
        
        # Poziom stanowiska
        if not check_position_level(job_data.get('title', '')):
            print(f"   ❌ Poziom stanowiska")
            continue
        
        # Wynagrodzenie (jeśli podane)
        salary_pln = extract_salary_pln(job_data)
        if salary_pln > 0 and salary_pln < MIN_SALARY_PLN:
            print(f"   ❌ Wynagrodzenie: {salary_pln:,.0f} PLN (min: {MIN_SALARY_PLN:,.0f} PLN)")
            continue
        
        # Scoring
        match_result = calculate_cv_match(job_data)
        
        # Odrzuć oferty <50%
        if match_result['score'] < 50:
            print(f"   ❌ Score: {match_result['score']}% (min: 50%)")
            continue
        
        print(f"   ✅ PASS - Score: {match_result['score']}% - {match_result['verdict']}")
        
        # Dodaj do listy
        filtered_jobs.append({
            'data': job_data,
            'match': match_result
        })
    
    print(f"\n✅ Po filtrowaniu: {len(filtered_jobs)} ofert\n")
    
    if not filtered_jobs:
        print("❌ Brak ofert spełniających kryteria!")
        return
    
    # 3. Sortuj według score
    filtered_jobs.sort(key=lambda x: x['match']['score'], reverse=True)
    
    # 4. Dodaj do bazy i utwórz katalogi
    for item in filtered_jobs:
        job_data = item['data']
        match = item['match']
        
        print("=" * 100)
        print(f"📊 {match['verdict']} - {match['score']}%")
        print(f"🏢 {job_data.get('company', 'Unknown')}")
        print(f"💼 {job_data.get('title', 'Unknown')}")
        print(f"📍 {job_data.get('location', 'Unknown')}")
        
        # Dodaj do bazy
        add_offer(
            job_data.get('company', 'Unknown'),
            job_data.get('title', 'Unknown'),
            job_data.get('location', 'Unknown'),
            job_data.get('job_url', ''),
            match['status']
        )
        
        # Pobierz ID oferty
        with get_conn() as conn:
            offer_id = conn.execute("""
                SELECT o.id FROM offers o 
                JOIN companies c ON o.company_id = c.id 
                WHERE c.name = ? AND o.title = ? 
                ORDER BY o.added_at DESC LIMIT 1
            """, (job_data.get('company', 'Unknown'), job_data.get('title', 'Unknown'))).fetchone()[0]
        
        # Dodaj notatki
        notes = f"Scoring: {match['score']}% - {match['verdict']}\n"
        for cat, pts in match['breakdown'].items():
            notes += f"{cat}: {pts} pkt\n"
        notes += f"\nŹródło: {job_data.get('site', 'Unknown')}\n"
        notes += f"Data publikacji: {job_data.get('date_posted', 'Unknown')}\n"
        
        update_offer(offer_id, note=notes)
        
        # Utwórz katalog dla ofert >70%
        if match['score'] >= 70:
            create_offer_folder(job_data, match)
        
        print("=" * 100)
        print()
    
    print(f"\n🎉 Job Hunter v2.0 zakończony! Znaleziono {len(filtered_jobs)} dopasowanych ofert.")


if __name__ == "__main__":
    job_hunter()
