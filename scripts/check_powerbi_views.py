import psycopg2

conn = psycopg2.connect(
    host='localhost', port=5434,
    dbname='nouv_db', user='postgres', password='Nouv26'
)
cur = conn.cursor()

# Lister les vues
cur.execute("SELECT viewname FROM pg_views WHERE schemaname = 'public' AND viewname LIKE 'vw_%' ORDER BY viewname")
views = [row[0] for row in cur.fetchall()]
print(f"Vues trouvées : {len(views)}")
for v in views:
    cur.execute(f"SELECT COUNT(*) FROM {v}")
    count = cur.fetchone()[0]
    print(f"  {v:35s} → {count} lignes")

conn.close()