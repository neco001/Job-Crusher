# 📖 Instrukcja Obsługi - Job Crusher

## 🚀 Szybki Start

### 1. Instalacja

```bash
# Sklonuj repozytorium
git clone https://github.com/neco001/Job-Crusher.git
cd Job-Crusher

# Zainstaluj zależności
pip install -r requirements.txt
```

### 2. Konfiguracja

Otwórz `job_hunter_v3.py` i dostosuj wyszukiwania:

```python
SEARCH_QUERIES = [
    {
        'keyword': 'dyrektor sprzedaży FMCG',
        'description': 'Dyrektor sprzedaży w FMCG'
    },
    {
        'keyword': 'commercial director retail',
        'description': 'Commercial Director w Retail'
    },
    # Dodaj swoje wyszukiwania tutaj
]
```

### 3. Uruchomienie

**Prosty test (sprawdza czy działa):**
```bash
python test_pracuj_vpn.py
```

**Pełny Job Hunter (z filtrowaniem i zapisem):**
```bash
python job_hunter_v3.py
```

---

## 🎯 Jak to działa?

### Krok 1: Scraping
System wyszukuje oferty na Pracuj.pl według Twoich kryteriów.

### Krok 2: Filtrowanie
Odrzuca oferty, które nie spełniają wymagań:
- ❌ Zła lokalizacja (nie Warszawa/remote)
- ❌ Za niski poziom (junior, assistant)
- ❌ Za niskie wynagrodzenie (<12k PLN)

### Krok 3: Scoring (0-100%)
Ocenia dopasowanie do Twojego CV:
- **30 pkt** - Doświadczenie FMCG
- **25 pkt** - Doświadczenie Retail/E-commerce
- **20 pkt** - Zarządzanie zespołem
- **15 pkt** - Umiejętności analityczne
- **10 pkt** - Język angielski

### Krok 4: Zapis do bazy
Dodaje ofertę do bazy DuckDB ze statusem:
- **Lead** (≥70%) - Aplikuj!
- **Poczekalnia** (50-69%) - Rozważ
- **Rejected** (<50%) - Pomiń

### Krok 5: Tworzenie katalogu
Dla ofert ≥70% tworzy folder z:
- `00_OFERTA.md` - Szczegóły oferty
- `01_ANALIZA.md` - Scoring i notatki
- `04_NOTATKI.md` - Śledzenie aplikacji

---

## ⚙️ Dostosowanie Filtrów

### Lokalizacja
Edytuj `ALLOWED_LOCATIONS` w `job_hunter_v3.py`:
```python
ALLOWED_LOCATIONS = [
    "warszawa", "warsaw", "kraków", "wrocław",
    "remote", "zdalna", "hybrid", "hybrydowa"
]
```

### Poziom stanowiska
Edytuj `REQUIRED_LEVELS`:
```python
REQUIRED_LEVELS = [
    "director", "dyrektor", "head of", "vp", 
    "kierownik", "manager"
]
```

### Wynagrodzenie
Zmień `MIN_SALARY_PLN`:
```python
MIN_SALARY_PLN = 15000  # 15k PLN brutto/mies
```

### Scoring CV
Dostosuj wagi w funkcji `calculate_cv_match()`:
```python
# 1. FMCG (30 pkt) - zmień na 40 pkt jeśli to Twój priorytet
fmcg_keywords = ["fmcg", "fast moving", "consumer goods"]
```

---

## 🗄️ Zarządzanie Bazą Danych

### Wyświetl statystyki
```bash
python db_manager.py --stats
```

### Lista ofert
```bash
python db_manager.py --list
```

### Zmień status oferty
```python
from db_manager import update_offer

update_offer(
    offer_id=123,
    status="Applied"  # Lead, Applied, Interview, Rejected
)
```

---

## 🐛 Rozwiązywanie Problemów

### Problem: Error 1015 (Rate Limited)
**Przyczyna:** Cloudflare zablokował Twoje IP  
**Rozwiązanie:**
1. Zmień IP (VPN, restart routera)
2. Poczekaj 24h
3. Zwiększ opóźnienie w skrypcie (z 10s do 15s)

### Problem: Brak wyników
**Przyczyna:** Za wąskie kryteria wyszukiwania  
**Rozwiązanie:**
1. Sprawdź keywords w `SEARCH_QUERIES`
2. Zmniejsz `MIN_SALARY_PLN`
3. Dodaj więcej lokalizacji do `ALLOWED_LOCATIONS`

### Problem: Za dużo śmieci
**Przyczyna:** Za szerokie keywords  
**Rozwiązanie:**
1. Użyj bardziej precyzyjnych fraz (np. "dyrektor sprzedaży FMCG" zamiast "sprzedaż")
2. Dodaj wykluczenia do `EXCLUDED_KEYWORDS`
3. Zwiększ `MIN_SALARY_PLN`

---

## 📊 Przykładowe Użycie

### Scenariusz 1: Szukam pracy w FMCG (Warszawa/Remote)
```python
SEARCH_QUERIES = [
    {'keyword': 'dyrektor sprzedaży FMCG', 'description': 'Sales Director FMCG'},
    {'keyword': 'commercial director FMCG', 'description': 'Commercial Director'},
]

ALLOWED_LOCATIONS = ["warszawa", "warsaw", "remote", "zdalna"]
MIN_SALARY_PLN = 15000
```

### Scenariusz 2: Szukam pracy w Retail (cała Polska)
```python
SEARCH_QUERIES = [
    {'keyword': 'head of retail', 'description': 'Head of Retail'},
    {'keyword': 'dyrektor sieci handlowej', 'description': 'Retail Network Director'},
]

ALLOWED_LOCATIONS = ["warszawa", "kraków", "wrocław", "poznań", "remote"]
MIN_SALARY_PLN = 12000
```

### Scenariusz 3: Szukam pracy w E-commerce
```python
SEARCH_QUERIES = [
    {'keyword': 'e-commerce director', 'description': 'E-commerce Director'},
    {'keyword': 'marketplace manager', 'description': 'Marketplace Manager'},
]

ALLOWED_LOCATIONS = ["remote", "zdalna", "warszawa"]
MIN_SALARY_PLN = 10000
```

---

## 🔧 Zaawansowane

### Zmiana częstotliwości scrapingu
W `job_hunter_v3.py`, linia ~400:
```python
await asyncio.sleep(10)  # Zmień na 15 dla większego bezpieczeństwa
```

### Więcej stron wyników
W `job_hunter_v3.py`, linia ~310:
```python
max_pages=2  # Zmień na 3 lub 5 (więcej ofert, dłuższy czas)
```

### Export do CSV
```python
import duckdb

conn = duckdb.connect('job_crusher.duckdb')
conn.execute("COPY (SELECT * FROM offers) TO 'offers.csv' (HEADER, DELIMITER ',')").fetchall()
```

---

## 📞 Wsparcie

- **Issues:** https://github.com/neco001/Job-Crusher/issues
- **Pull Requests:** Mile widziane!

---

**Powodzenia w poszukiwaniach! 🚀**
