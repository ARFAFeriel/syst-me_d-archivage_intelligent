import os
import psycopg2

conn = psycopg2.connect(host='localhost', port=5434, dbname='nouv_db', user='postgres', password='Nouv26')
cur = conn.cursor()
cur.execute("SELECT original_path FROM documents WHERE id = 4016")
original_path = cur.fetchone()[0]

print("repr:", repr(original_path))
print("longueur:", len(original_path))
print("isfile:", os.path.isfile(original_path))

stripped = original_path.lstrip("\\\\?\\").lstrip("//?/")
print("isfile apres lstrip:", os.path.isfile(stripped))

idx = original_path.find("classer")
print("hex autour de 'classer':", [hex(ord(c)) for c in original_path[idx-2:idx+10]])

cur.close()
conn.close()