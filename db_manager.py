import duckdb
import argparse
import os
from pathlib import Path
from tabulate import tabulate

# Config
BASE_DIR = Path(__file__).parent
MAIN_DB = os.path.join(BASE_DIR, 'job_crusher.duckdb')
CACHE_DB = os.path.join(BASE_DIR, 'scan_cache.duckdb')

def get_conn(db_name='main'):
    if db_name == 'main':
        db_path = MAIN_DB
    else:
        db_path = os.path.join(BASE_DIR, f'{db_name}.duckdb')
    
    conn = duckdb.connect(db_path)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY,
            name VARCHAR UNIQUE,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY,
            company_id INTEGER,
            title VARCHAR,
            location VARCHAR,
            source_url VARCHAR UNIQUE,
            status VARCHAR DEFAULT 'Lead',
            note TEXT,
            full_text TEXT,
            score INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id)
        );
    """)
    return conn

def add_offer(company_name, title, location, url, status='New', full_text=None, score=0, db='main'):
    with get_conn(db) as conn:
        # Generowanie ID dla firmy
        conn.execute("INSERT INTO companies (id, name) SELECT COALESCE(MAX(id), 0) + 1, ? FROM companies WHERE NOT EXISTS (SELECT 1 FROM companies WHERE name = ?)", (company_name, company_name))
        comp_id = conn.execute("SELECT id FROM companies WHERE name = ?", (company_name,)).fetchone()[0]
        
        # Generowanie ID dla oferty
        next_id_offer = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM offers").fetchone()[0]
        
        # Insert or update
        existing = conn.execute("SELECT id FROM offers WHERE source_url = ?", (url,)).fetchone()
        
        if existing:
            conn.execute("""
                UPDATE offers SET 
                    full_text = ?,
                    score = ?
                WHERE source_url = ?
            """, (full_text, score, url))
        else:
            conn.execute("""
                INSERT INTO offers (id, company_id, title, location, source_url, status, full_text, score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (next_id_offer, comp_id, title, location, url, status, full_text, score))
            
        print(f"✅ Saved to {db}: {title} at {company_name}")

def list_offers(db='main', limit=20):
    with get_conn(db) as conn:
        data = conn.execute("""
            SELECT o.id, c.name, o.title, o.score, o.status, CAST(o.added_at AS DATE)
            FROM offers o JOIN companies c ON o.company_id = c.id
            ORDER BY o.added_at DESC LIMIT ?
        """, (limit,)).fetchall()
        print(f"\n--- OFFERS IN {db.upper()} ---")
        print(tabulate(data, headers=["ID", "Company", "Title", "Score", "Status", "Date"]))

def get_offer_text(offer_id, db='main'):
    with get_conn(db) as conn:
        res = conn.execute("SELECT title, full_text FROM offers WHERE id = ?", (offer_id,)).fetchone()
        if res:
            print(f"\n=== {res[0]} ===\n")
            print(res[1])
        else:
            print("❌ Offer not found.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', action='store_true', help='List recent offers')
    parser.add_argument('--get_text', type=int, help='Get full text of offer by ID')
    parser.add_argument('--db', default='main', help='Database to use (main or scan_cache)')
    
    args = parser.parse_args()
    
    if args.list: 
        list_offers(args.db)
    elif args.get_text:
        get_offer_text(args.get_text, args.db)
