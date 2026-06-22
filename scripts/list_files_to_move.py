import psycopg2

conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()

cur.execute("""
    SELECT id, filename, original_path, aircraft_registration, category, doc_type, es_reference
    FROM documents
    WHERE original_path LIKE '%à classer%'
    ORDER BY aircraft_registration, category, id;
""")
rows = cur.fetchall()

print(f"{len(rows)} documents à déplacer.\n")

for doc_id, filename, path, avion, cat, dtype, es_ref in rows:
    avion_aff = avion or "SANS_AVION"
    cat_aff   = cat or "Sans_categorie"
    es_aff    = es_ref or "Sans_ref"
    destination_suggeree = f"Aircraft\\{avion_aff}\\{cat_aff}\\{es_aff}\\{dtype}\\{filename}"

    print(f"ID {doc_id}")
    print(f"  Fichier actuel : {path}")
    print(f"  Destination suggérée (sous AviationArchive\\) : {destination_suggeree}")
    print()

cur.close()
conn.close()