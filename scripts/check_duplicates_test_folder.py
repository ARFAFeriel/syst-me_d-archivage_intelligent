import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5434, dbname="nouv_db",
    user="postgres", password="Nouv26"
)
cur = conn.cursor()

dossier_test = r"à classer (tester la classification)"

# Récupère les hash des 43 documents suspects
cur.execute("""
    SELECT id, filename, sha256_hash
    FROM documents
    WHERE original_path LIKE %s;
""", (f"%{dossier_test}%",))
suspects = cur.fetchall()

print(f"{len(suspects)} documents du dossier de test trouvés en base.\n")

doublons = 0
for doc_id, filename, sha in suspects:
    if not sha:
        continue
    cur.execute("""
        SELECT id, filename, original_path
        FROM documents
        WHERE sha256_hash = %s AND id != %s;
    """, (sha, doc_id))
    autres = cur.fetchall()
    if autres:
        doublons += 1
        print(f"DOUBLON : ID {doc_id} ({filename}) a le même hash que :")
        for a in autres:
            print(f"   -> ID {a[0]} ({a[1]}) chemin: {a[2]}")

print(f"\n=== Résultat : {doublons} document(s) sur {len(suspects)} sont des doublons d'un autre document déjà en base. ===")

cur.close()
conn.close()