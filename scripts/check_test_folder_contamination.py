import os
import psycopg2

dossier_test = r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\à classer (tester la classification)"

# Liste tous les noms de fichiers du dossier de test (récursif)
fichiers_test = set()
for root, dirs, files in os.walk(dossier_test):
    for f in files:
        fichiers_test.add(f)

print(f"{len(fichiers_test)} noms de fichiers uniques trouvés dans le dossier de test.\n")

conn = psycopg2.connect(
    host="localhost", port=5434, dbname="nouv_db",
    user="postgres", password="Nouv26"
)
cur = conn.cursor()

cur.execute("SELECT id, filename, doc_type, aircraft_registration, original_path FROM documents;")
rows = cur.fetchall()

matches = [r for r in rows if r[1] in fichiers_test]

print(f"=== {len(matches)} documents en base correspondent à des fichiers du dossier de test ===\n")

if matches:
    # Répartition par type pour ces documents suspects
    from collections import Counter
    type_counts = Counter(m[2] for m in matches)
    print("Répartition par doc_type parmi ces documents suspects :")
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")

    print(f"\nExemples (5 premiers) :")
    for m in matches[:5]:
        print(f"  ID {m[0]} | {m[1]} | type={m[2]} | avion={m[3]}")
        print(f"     chemin en base : {m[4]}")

    # Combien ont un original_path qui pointe vers le DOSSIER DE TEST lui-même
    pointing_to_test = [m for m in matches if dossier_test.lower() in (m[4] or "").lower()]
    print(f"\n{len(pointing_to_test)} documents ont un original_path qui pointe DIRECTEMENT vers le dossier de test.")

    # Combien ont un original_path qui pointe vers un AUTRE dossier (peut-être le vrai dossier d'archive)
    pointing_elsewhere = len(matches) - len(pointing_to_test)
    print(f"{pointing_elsewhere} ont un chemin différent (peut-être le même fichier mais dans le vrai dossier d'archive).")
else:
    print("Aucune correspondance — aucun fichier de ce dossier de test n'a été importé en base. Tu peux respirer.")

cur.close()
conn.close()