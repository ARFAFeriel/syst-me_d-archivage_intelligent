import os
import psycopg2

archive_root = r"C:\Users\ferie\Desktop\stage nvl\AviationArchive"

conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()

cur.execute("""
    SELECT id, filename, original_path
    FROM documents
    WHERE original_path LIKE '%à classer%';
""")
rows = cur.fetchall()

print(f"Recherche des nouveaux emplacements pour {len(rows)} documents...\n")

updated, not_found, still_in_test = 0, 0, 0

for doc_id, filename, old_path in rows:
    found_path = None
    for root, dirs, files in os.walk(archive_root):
        if "à classer" in root:
            continue  # on ignore l'ancien dossier de test, on cherche le NOUVEL emplacement
        if filename in files:
            found_path = os.path.join(root, filename)
            break

    if found_path:
        cur.execute("UPDATE documents SET original_path = %s WHERE id = %s;", (found_path, doc_id))
        print(f"ID {doc_id} : mis à jour -> {found_path}")
        updated += 1
    elif os.path.exists(old_path):
        print(f"ID {doc_id} : toujours dans l'ancien dossier de test (pas encore déplacé).")
        still_in_test += 1
    else:
        print(f"ID {doc_id} : INTROUVABLE nulle part ({filename}) — à vérifier manuellement.")
        not_found += 1

conn.commit()
print(f"\n=== Résumé : {updated} mis à jour | {still_in_test} pas encore déplacés | {not_found} introuvables ===")

cur.close()
conn.close()