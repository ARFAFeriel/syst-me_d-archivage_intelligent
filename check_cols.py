import psycopg2
conn = psycopg2.connect("postgresql://postgres:Nouv26@localhost:5434/nouv_db")
cur  = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='documents' ORDER BY ordinal_position")
for r in cur.fetchall(): print(r[0])
cur.close(); conn.close()
