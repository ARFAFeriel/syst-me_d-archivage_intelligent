import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
conn = psycopg2.connect(host='localhost', port=5434, dbname='nouv_db', user='postgres', password='Nouv26')
cur = conn.cursor()
cur.execute("""
    SELECT filename, original_path, ocr_confidence
    FROM documents
    WHERE ocr_confidence BETWEEN 30 AND 60
    LIMIT 5
""")
for row in cur.fetchall():
    print(row)
conn.close()