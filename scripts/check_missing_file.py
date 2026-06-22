import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5434, dbname="nouv_db",
    user="postgres", password="Nouv26"
)
cur = conn.cursor()
cur.execute("SELECT id, filename, original_path, doc_origin FROM documents WHERE id = 4016;")
row = cur.fetchone()
print(row)

import os
if row and row[2]:
    print("Chemin existe sur disque ?", os.path.exists(row[2]))

cur.close()
conn.close()