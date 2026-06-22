import psycopg2

conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
cur = conn.cursor()
cur.execute(
    "UPDATE documents SET original_path = %s WHERE id = 4016",
    (r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INQ\CHECK D\ES001071\WO\ES153597.pdf",)
)
conn.commit()
print("Lignes modifiees:", cur.rowcount)
cur.close()
conn.close()
