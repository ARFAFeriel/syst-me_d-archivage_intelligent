import psycopg2
conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()
cur.execute("SELECT id, filename, es_reference FROM documents WHERE es_reference LIKE %s", ("%153597%",))
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
