import psycopg2

conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'documents' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print("Colonnes de la table documents:")
print(cols)
print()

cur.execute("SELECT * FROM documents WHERE id = 4016")
row = cur.fetchone()
print("Valeurs pour le document #4016:")
for col, val in zip(cols, row):
    print(f"  {col}: {val!r}")

cur.close()
conn.close()
