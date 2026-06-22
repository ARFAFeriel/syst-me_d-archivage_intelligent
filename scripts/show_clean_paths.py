import psycopg2

conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()
cur.execute("""
    SELECT original_path
    FROM documents
    WHERE original_path NOT LIKE '%à classer%'
    LIMIT 5;
""")
for row in cur.fetchall():
    print(row[0])
cur.close()
conn.close()