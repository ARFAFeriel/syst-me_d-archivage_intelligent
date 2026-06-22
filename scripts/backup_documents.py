import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    host="localhost", port=5434, dbname="nouv_db",
    user="postgres", password="Nouv26"
)
cur = conn.cursor()

backup_name = f"documents_backup_{datetime.now().strftime('%Y%m%d_%H%M')}"

cur.execute(f"CREATE TABLE {backup_name} AS SELECT * FROM documents;")
conn.commit()

cur.execute(f"SELECT COUNT(*) FROM {backup_name};")
count = cur.fetchone()[0]

print(f"Backup créé : table '{backup_name}' avec {count} lignes.")
print("Pour restaurer en cas de problème :")
print(f"  DROP TABLE documents;")
print(f"  ALTER TABLE {backup_name} RENAME TO documents;")

cur.close()
conn.close()