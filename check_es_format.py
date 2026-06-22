import psycopg2
conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()
cur.execute("SELECT DISTINCT es_reference FROM documents WHERE es_reference IS NOT NULL LIMIT 20")
for row in cur.fetchall():
    print(row[0])
cur.close()
conn.close()
