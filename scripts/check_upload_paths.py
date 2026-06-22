import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5434, dbname="nouv_db",
    user="postgres", password="Nouv26"
)
cur = conn.cursor()

# Combien de documents ont ce chemin générique "upload/"
cur.execute("""
    SELECT doc_origin, COUNT(*), MIN(created_at), MAX(created_at)
    FROM documents
    WHERE original_path LIKE 'upload/%'
    GROUP BY doc_origin;
""")
print("=== Documents avec chemin générique 'upload/...' ===")
for row in cur.fetchall():
    print(row)

# Toutes les valeurs distinctes de doc_origin présentes dans la base
cur.execute("SELECT doc_origin, COUNT(*) FROM documents GROUP BY doc_origin;")
print("\n=== Répartition par doc_origin (toute la base) ===")
for row in cur.fetchall():
    print(row)

# Sur ces documents "upload/", combien ont un fichier qui existe réellement
cur.execute("SELECT id, filename, original_path FROM documents WHERE original_path LIKE 'upload/%' LIMIT 2000;")
rows = cur.fetchall()
import os
manquants = sum(1 for _, _, p in rows if not os.path.exists(p))
print(f"\nSur {len(rows)} documents 'upload/...', {manquants} ont un fichier introuvable sur disque.")

cur.close()
conn.close()