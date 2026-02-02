
import duckdb
import argparse
import sys
import os
import shutil
from datetime import datetime, timedelta
from tabulate import tabulate

# Configuration
DB_PATH = r'c:\Users\pawel\OneDrive\python git 2501\Officer\03_FREELANCE_Labs\Job_Crusher\data\job_crusher.duckdb'
CV_MOJE_PATH = r'c:\Users\pawel\OneDrive\python git 2501\Officer\03_FREELANCE_Labs\Job_Crusher\CV Moje'
ARCHIVE_PATH = os.path.join(CV_MOJE_PATH, '99_Arichwum')

ACTIVE_STATUSES = ['New', 'Lead', 'Applied', 'Under Review', 'Interview', 'Offer']

def get_conn():
    return duckdb.connect(DB_PATH)

def add_offer(company_name, title, location, source_url, status='New'):
    with get_conn() as conn:
        conn.execute("INSERT INTO companies (name) VALUES (?) ON CONFLICT (name) DO NOTHING", (company_name,))
        comp_id = conn.execute("SELECT id FROM companies WHERE name = ?", (company_name,)).fetchone()[0]
        conn.execute("""
            INSERT INTO offers (company_id, title, location, source_url, status)
            VALUES (?, ?, ?, ?, ?)
        """, (comp_id, title, location, source_url, status))
        offer_id = conn.execute("SELECT id FROM offers WHERE title = ? AND company_id = ? ORDER BY added_at DESC LIMIT 1", (title, comp_id)).fetchone()[0]
        print(f"✅ Added [ID:{offer_id}] {title} at {company_name}")

def update_offer(offer_id, status=None, note=None):
    with get_conn() as conn:
        if status:
            conn.execute("UPDATE offers SET status = ? WHERE id = ?", (status, offer_id))
        if note:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("UPDATE offers SET notes = COALESCE(notes, '') || ? || ': ' || ? || '\n' WHERE id = ?", (timestamp, note, offer_id))
        print(f"✅ Updated ID:{offer_id}")

def show_stats():
    with get_conn() as conn:
        stats = conn.execute("SELECT status, count(*) FROM offers GROUP BY status ORDER BY count(*) DESC").fetchall()
        print("\n--- JOB CRUSHER STATS ---")
        if not stats:
            print("Baza jest pusta.")
        else:
            print(tabulate(stats, headers=["Status", "Count"], tablefmt="fancy_grid"))

def list_offers(query=None, show_all=False, limit=25):
    with get_conn() as conn:
        sql = """
            SELECT o.id, c.name, o.title, o.status, CAST(o.added_at AS DATE)
            FROM offers o JOIN companies c ON o.company_id = c.id
        """
        params = []
        where_clauses = []
        if not show_all and not query:
            placeholders = ",".join(["?"] * len(ACTIVE_STATUSES))
            where_clauses.append(f"o.status IN ({placeholders})")
            params.extend(ACTIVE_STATUSES)
        if query:
            where_clauses.append("(o.title LIKE ? OR c.name LIKE ? OR o.status LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY o.added_at DESC LIMIT ?"
        params.append(limit)
        
        data = conn.execute(sql, params).fetchall()
        print(f"\n--- OFFERS ({'ALL' if show_all else 'ACTIVE ONLY'}) ---")
        if not data:
            print("Brak pasujących ofert.")
        else:
            print(tabulate(data, headers=["ID", "Company", "Title", "Status", "Date"], tablefmt="simple"))

def cleanup_and_archive():
    print("--- STARTING CLEANUP & ARCHIVE PROTOCOL ---")
    with get_conn() as conn:
        limit_date = (datetime.now() - timedelta(days=60))
        affected = conn.execute("""
            UPDATE offers 
            SET status = 'No Response' 
            WHERE status IN ('New', 'Applied', 'Lead') 
            AND added_at < ?
        """, (limit_date,)).rowcount
        print(f"Baza: Zmieniono status na 'No Response' dla {affected} starych ofert.")

        offers_to_archive = conn.execute("""
            SELECT c.name
            FROM offers o JOIN companies c ON o.company_id = c.id
            WHERE o.status IN ('Rejected', 'Resigned', 'No Response')
        """).fetchall()
    
    comp_names = set(row[0] for row in offers_to_archive)
    if not os.path.exists(ARCHIVE_PATH): os.makedirs(ARCHIVE_PATH)

    moved_count = 0
    for folder_name in os.listdir(CV_MOJE_PATH):
        if folder_name in ["99_Arichwum", "_pliki_Bazowe"]: continue
        full_path = os.path.join(CV_MOJE_PATH, folder_name)
        if os.path.isdir(full_path):
            for comp in comp_names:
                if f"( {comp} )" in folder_name:
                    print(f"Archiving: {folder_name}")
                    try:
                        shutil.move(full_path, os.path.join(ARCHIVE_PATH, folder_name))
                        moved_count += 1
                        break
                    except Exception as e: print(f"Error: {e}")
    print(f"--- ARCHIVE DONE: {moved_count} ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--add', action='store_true')
    parser.add_argument('--update', type=int)
    parser.add_argument('--status', type=str)
    parser.add_argument('--note', type=str)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--search', type=str)
    parser.add_argument('--stats', action='store_true')
    parser.add_argument('--cleanup', action='store_true')
    parser.add_argument('--company', help='Company name')
    parser.add_argument('--title', help='Job title')
    parser.add_argument('--url', default='')
    
    args = parser.parse_args()
    if args.add: add_offer(args.company, args.title, 'Warszawa', args.url)
    elif args.update: update_offer(args.update, args.status, args.note)
    elif args.stats: show_stats()
    elif args.list: list_offers(show_all=args.all)
    elif args.search: list_offers(args.search, show_all=True)
    elif args.cleanup: cleanup_and_archive()
    else: parser.print_help()
