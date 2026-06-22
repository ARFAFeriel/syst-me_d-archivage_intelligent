import psycopg2

conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM documents WHERE original_path LIKE %s", ("upload/%",))
print("Documents avec chemin upload/ (potentiellement casses):", cur.fetchone()[0])

cur.execute("SELECT id, filename, original_path, created_at FROM documents WHERE original_path LIKE %s ORDER BY created_at", ("upload/%",))
for row in cur.fetchall():
    print(row)

cur.close()
conn.close()
