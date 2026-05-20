import psycopg2

conn = psycopg2.connect(host='localhost', port=5434, dbname='nouv_db', user='postgres', password='Nouv26')
cur = conn.cursor()
cur.execute("SELECT definition FROM pg_views WHERE viewname = 'vw_par_avion'")
print(cur.fetchone()[0])
conn.close()