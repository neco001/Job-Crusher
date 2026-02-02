# 🎯 Job Crusher - Automated Job Hunting System

**Automated job search, filtering, and application tracking system for Pracuj.pl**

## 🚀 Features

- **Automated Scraping**: Scrapes job offers from Pracuj.pl with smart rate limiting
- **Smart Filtering**: Filters by location, position level, salary, and industry
- **CV Matching**: Scores job offers (0-100%) based on your CV and experience
- **Database Integration**: Stores offers in DuckDB with status tracking
- **Folder Generation**: Auto-creates structured folders for high-scoring offers (>70%)
- **Rate Limiting**: Built-in delays to avoid Cloudflare bans

## 📋 Requirements

- Python 3.10+
- VPN recommended (Pracuj.pl rate limits aggressively)

## 🛠️ Installation

```bash
# Clone repository
git clone https://github.com/neco001/Job-Crusher.git
cd Job-Crusher

# Install dependencies
pip install -r requirements.txt
```

## 🎮 Usage

### Basic Test
```bash
python test_pracuj_vpn.py
```

### Full Job Hunter
```bash
python job_hunter_v3.py
```

## 📊 Components

- **`db_manager.py`**: DuckDB database operations
- **`job_hunter_v3.py`**: Main job hunting automation
- **`test_pracuj_vpn.py`**: Simple scraper test
- **`JOB_HUNTER_FILTERS.md`**: Filtering criteria documentation

## 🔧 Configuration

Edit search queries in `job_hunter_v3.py`:

```python
SEARCH_QUERIES = [
    {
        'keyword': 'dyrektor sprzedaży FMCG',
        'description': 'Dyrektor sprzedaży w FMCG'
    },
    # Add your queries here
]
```

## 📁 Output Structure

For offers scoring ≥70%, creates:
```
CV Moje/
└── YYYY-MM-DD (Company) Title/
    ├── 00_OFERTA.md       # Full offer details
    ├── 01_ANALIZA.md      # Scoring breakdown
    └── 04_NOTATKI.md      # Application tracking
```

## ⚠️ Important Notes

- **VPN Required**: Pracuj.pl uses Cloudflare rate limiting (Error 1015)
- **Rate Limiting**: 10s delay between requests to avoid bans
- **Scraper Dependency**: Uses [TymekMor/Pracuj-pl-Scraper](https://github.com/TymekMor/Pracuj-pl-Scraper)

## 📝 License

MIT License - Feel free to use and modify

## 🤝 Contributing

Pull requests welcome! Please ensure:
- Code follows existing style
- Add tests for new features
- Update documentation

## 🔗 Related Projects

- [Pracuj-pl-Scraper](https://github.com/TymekMor/Pracuj-pl-Scraper) - Base scraper
- [JobSpy](https://github.com/speedyapply/JobSpy) - Multi-platform job scraper (LinkedIn, Indeed)

---

**Made with ❤️ for automated job hunting**
