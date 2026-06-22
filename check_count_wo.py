import psycopg2
conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM documents WHERE status = 'ARCHIVED' AND doc_type::text = 'WORK_ORDER' AND aircraft_registration ILIKE %s", ("%TS-INQ%",))
print("Work Order + TS-INQ (les deux criteres):", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM documents WHERE status = 'ARCHIVED' AND doc_type::text = 'WORK_ORDER'")
print("Work Order seul (tous avions):", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM documents WHERE status = 'ARCHIVED' AND aircraft_registration ILIKE %s", ("%TS-INQ%",))
print("TS-INQ seul (tous types):", cur.fetchone()[0])

cur.close()
conn.close()
