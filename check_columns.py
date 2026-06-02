import psycopg2
conn = psycopg2.connect(host='localhost', port=5434, dbname='nouv_db', user='postgres', password='Nouv26')
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='documents' ORDER BY ordinal_position")
for row in cur.fetchall():
    print(row)
conn.close()
