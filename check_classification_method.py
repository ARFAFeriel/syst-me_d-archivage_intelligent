import psycopg2
conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()
cur.execute("""
    SELECT filename, doc_type, classifier_confidence, classifier_scores, extracted_entities, ocr_text
    FROM documents WHERE filename ILIKE %s
""", ("%Ozone Converters%",))
row = cur.fetchone()
print("Fichier:", row[0])
print("Doc type:", row[1])
print("Confidence:", row[2])
print("Scores:", row[3])
print("Entites extraites:", row[4])
print("OCR text (300 premiers caracteres):", (row[5] or "")[:300])
cur.close()
conn.close()
