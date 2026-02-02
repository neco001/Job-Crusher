"""
JOB HUNTER v3.4.2 - The Clean Import Edition
"""

import os
import yaml
import asyncio
from datetime import datetime
from pathlib import Path
from curl_cffi.requests import AsyncSession

# Czyste importy dzięki zmianie nazwy folderu na Pracuj_pl_Scraper
from Pracuj_pl_Scraper.scraper import PracujScraper
from Pracuj_pl_Scraper.get_offer_details import get_offer_details
import db_manager

# ===== ŁADOWANIE KONFIGURACJI =====
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    CONFIG = yaml.safe_load(f)

# ===== FUNKCJE POMOCNICZE =====

def pre_filter_offer(offer: dict) -> bool:
    title = offer.get('Title', '').lower()
    location = offer.get('Location', '').lower()
    f = CONFIG['filters']
    
    if not any(loc in location for loc in f['allowed_locations']):
        return False, "Zła lokalizacja"
    if any(ex in title for ex in f['excluded_title_keywords']):
        return False, "Wykluczone słowo w tytule"
    if not any(req in title for req in f['required_title_keywords']):
        return False, "Brak kluczowego poziomu w tytule"
        
    return True, "OK"

def calculate_cv_match(details: dict) -> dict:
    score = 0
    breakdown = {}
    
    text = " ".join([
        str(details.get('title', '')),
        str(details.get('description', '')),
        " ".join(details.get('responsibilities', [])),
        " ".join(details.get('requirements', [])),
    ]).lower()
    
    sw = CONFIG['scoring_weights']
    
    for category, cfg in sw.items():
        weight = cfg['weight']
        keywords = cfg['keywords']
        cat_score = sum( (weight * 0.4) if kw in text else 0 for kw in keywords[:2])
        bonus = 10 if any(kw in text for kw in keywords[2:]) else 0
        final_cat_score = min(cat_score + bonus, weight)
        
        breakdown[category] = int(final_cat_score)
        score += final_cat_score

    score = int(score)
    if score >= 85: verdict, status = "🔥 MUST APPLY", "Lead"
    elif score >= 70: verdict, status = "✅ STRONG MATCH", "Lead"
    elif score >= 50: verdict, status = "⚠️ MAYBE", "poczekalnia"
    else: verdict, status = "❌ REJECT", "Rejected"
    
    return {'score': score, 'breakdown': breakdown, 'verdict': verdict, 'status': status}

def extract_salary(salary_str: str) -> int:
    import re
    if not salary_str or "Nie podano" in salary_str: return 0
    salary_clean = salary_str.replace(' ', '').replace(',', '.')
    numbers = re.findall(r'\d+', salary_clean)
    if not numbers: return 0
    val = int(numbers[0])
    if 'rok' in salary_clean.lower() or 'year' in salary_clean.lower(): val = val // 12
    return val

def create_folder(details: dict, match: dict):
    cv_path = BASE_DIR / 'CV Moje'
    cv_path.mkdir(exist_ok=True)
    
    company = str(details.get('company', 'Unknown')).replace('/', '-').replace('\\', '-')
    title = str(details.get('title', 'Unknown'))[:50].replace('/', '-').replace('\\', '-')
    folder_name = f"{datetime.now().strftime('%Y-%m-%d')} ( {company} ) {title}"
    path = cv_path / folder_name
    path.mkdir(exist_ok=True)
    
    content = f"# {details.get('title')}\n\n## Dopasowanie: {match['score']}% - {match['verdict']}\n\n"
    content += f"**Firma:** {details.get('company')}\n**Link:** {details.get('url')}\n\n"
    content += "### Responsibilities:\n" + "\n".join([f"- {r}" for r in details.get('responsibilities', [])])
    
    (path / "00_OFERTA.md").write_text(content, encoding='utf-8')
    (path / "01_ANALIZA.md").write_text(f"# Analiza\nScoring: {match['score']}%\nBreakdown: {match['breakdown']}", encoding='utf-8')
    print(f"   📂 Katalog utworzony: {folder_name}")

# ===== ENGINE =====

async def job_hunter():
    print("="*60)
    print(f"🚀 JOB HUNTER v3.4.2 - CLEAN ({len(CONFIG['search_queries'])} queries)")
    print("="*60)
    
    scraper = PracujScraper()
    all_raw_offers = []
    
    async with AsyncSession() as client:
        for q in CONFIG['search_queries']:
            print(f"📡 Scraping: {q['description']}...")
            try:
                res = await scraper.scrape_keyword(client, q['keyword'], max_pages=CONFIG['settings']['max_pages_per_query'])
                if res: all_raw_offers.extend(res)
            except Exception as e: print(f"   ❌ Error: {e}")
            
    unique_list = {o['Link']: o for o in all_raw_offers}.values()
    print(f"\n📊 Total on list: {len(unique_list)}")
    
    print(f"🧹 Pre-filtering...")
    candidates = []
    for o in unique_list:
        passed, reason = pre_filter_offer(o)
        if passed: candidates.append(o)
    
    print(f"✅ Candidates for deep analysis: {len(candidates)}")
    
    pauza = CONFIG['settings']['deep_analysis_pauza_sec']
    for idx, cand in enumerate(candidates, 1):
        print(f"[{idx}/{len(candidates)}] Analysis: {cand.get('Title', '')[:40]} | {cand.get('Company', '')}")
        
        if idx > 1: await asyncio.sleep(pauza)
        
        try:
            details = await get_offer_details(cand['Link'])
            if 'error' in details:
                print(f"   ⚠️ Error: {details['error']}")
                continue
                
            salary = extract_salary(details.get('salary', ''))
            if 0 < salary < CONFIG['filters']['min_salary_pln']:
                print(f"   ❌ Salary too low: {salary} PLN")
                continue
                
            match = calculate_cv_match(details)
            print(f"   🎯 MATCH: {match['score']}% ({match['verdict']})")
            
            # Zapis do BUFORA CACHE (full_text i score)
            full_description = f"TITLE: {details.get('title')}\nDESCRIPTION: {details.get('description')}\nRESPONSIBILITIES: {details.get('responsibilities')}\nREQUIREMENTS: {details.get('requirements')}"
            db_manager.add_offer(
                details.get('company'), 
                details.get('title'), 
                details.get('location'), 
                cand['Link'], 
                status=match['status'],
                full_text=full_description,
                score=match['score'],
                db='scan_cache'
            )
            
            if match['score'] >= CONFIG['settings']['min_score_to_save_folder']:
                create_folder(details, match)
                
        except Exception as e: print(f"   ❌ Error at offer {idx}: {e}")

if __name__ == "__main__":
    asyncio.run(job_hunter())
