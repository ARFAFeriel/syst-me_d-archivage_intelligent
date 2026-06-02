import psycopg2

conn = psycopg2.connect(host='localhost', port=5434, dbname='nouv_db', user='postgres', password='Nouv26')
cur = conn.cursor()

# Toutes les tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print("TABLES :", tables)

# Colonnes de documents
cur.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='documents' ORDER BY ordinal_position")
cols = cur.fetchall()
print("\n── TABLE documents ──────────────────────────────────────")
print(f"{'#':<4} {'Colonne':<30} {'Type':<30} {'Nullable'}")
print("-" * 75)
for i, (name, dtype, nullable) in enumerate(cols, 1):
    print(f"{i:<4} {name:<30} {dtype:<30} {nullable}")

# Valeurs distinctes de doc_type
cur.execute("SELECT DISTINCT doc_type, COUNT(*) FROM documents GROUP BY doc_type ORDER BY COUNT(*) DESC")
print("\n── doc_type (valeurs distinctes) ────────────────────────")
print(f"{'Type':<25} {'Nb docs':>10}")
print("-" * 37)
total = 0
for row in cur.fetchall():
    dtype, cnt = row
    print(f"{str(dtype):<25} {cnt:>10}")
    total += cnt
print(f"{'TOTAL':<25} {total:>10}")

# Valeurs distinctes de category
cur.execute("SELECT DISTINCT category, COUNT(*) FROM documents GROUP BY category ORDER BY COUNT(*) DESC")
print("\n── category (valeurs distinctes) ────────────────────────")
print(f"{'Catégorie':<30} {'Nb docs':>10}")
print("-" * 42)
for row in cur.fetchall():
    cat, cnt = row
    print(f"{str(cat):<30} {cnt:>10}")

# Valeurs distinctes de status
cur.execute("SELECT DISTINCT status, COUNT(*) FROM documents GROUP BY status ORDER BY COUNT(*) DESC")
print("\n── status ───────────────────────────────────────────────")
for row in cur.fetchall():
    print(f"  {row[0]}  →  {row[1]} docs")

# Stats générales
cur.execute("SELECT COUNT(*) FROM documents")
print(f"\n── Total documents : {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(DISTINCT aircraft_registration) FROM documents WHERE aircraft_registration IS NOT NULL")
print(f"── Immatriculations distinctes : {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM documents WHERE needs_review = true")
print(f"── needs_review = true : {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM documents WHERE is_duplicate = true")
print(f"── is_duplicate = true : {cur.fetchone()[0]}")

conn.close()