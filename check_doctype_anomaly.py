import psycopg2
conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()
cur.execute("SELECT filename, doc_type, aircraft_registration FROM documents WHERE filename ILIKE %s", ("%Ozone Converters%",))
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
