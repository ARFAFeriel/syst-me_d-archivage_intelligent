import psycopg2
import cv2
import numpy as np
import os

conn = psycopg2.connect(
    host="localhost",
    port=5434,
    dbname="nouv_db",
    user="postgres",
    password="Nouv26"
)
cur = conn.cursor()

cur.execute("""
    SELECT id, filename, original_path, mime_type, file_size_kb
    FROM documents
    WHERE doc_type = 'WORK_ORDER'
      AND ocr_confidence = 0
      AND (ocr_text IS NULL OR TRIM(ocr_text) = '')
    ORDER BY RANDOM()
    LIMIT 15;
""")
rows = cur.fetchall()
cur.close()
conn.close()

print(f"{'ID':<6}{'Fichier':<35}{'Taille KB':<11}{'Dim (LxH)':<14}{'DPI est.':<10}{'Luminosité':<12}{'Contraste':<11}{'% blanc':<9}{'Net?':<6}")

def estimate_dpi(width_px, height_px):
    # Hypothèse A4 (210x297mm = 8.27x11.69 pouces)
    dpi_w = width_px / 8.27
    dpi_h = height_px / 11.69
    return round((dpi_w + dpi_h) / 2)

for doc_id, filename, path, mime, size_kb in rows:
    try:
        if not os.path.exists(path):
            print(f"{doc_id:<6}{filename:<35}{'FICHIER INTROUVABLE':<11}")
            continue

        if mime == "application/pdf":
            import fitz  # PyMuPDF
            pdf = fitz.open(path)
            page = pdf[0]
            pix = page.get_pixmap(dpi=300)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            img = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img_array
            pdf.close()
        else:
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)

        if img is None:
            print(f"{doc_id:<6}{filename:<35}{'ÉCHEC LECTURE IMAGE':<11}")
            continue

        h, w = img.shape
        dpi_est = estimate_dpi(w, h)
        luminosite = round(float(np.mean(img)), 1)
        contraste = round(float(np.std(img)), 1)
        pct_blanc = round(100.0 * np.sum(img > 240) / img.size, 1)
        # Netteté approximative via variance du Laplacien
        nettete = cv2.Laplacian(img, cv2.CV_64F).var()
        net = "Flou" if nettete < 50 else "OK"

        print(f"{doc_id:<6}{filename[:33]:<35}{round(size_kb,1):<11}{f'{w}x{h}':<14}{dpi_est:<10}{luminosite:<12}{contraste:<11}{pct_blanc:<9}{net:<6}")

    except Exception as e:
        print(f"{doc_id:<6}{filename[:33]:<35}ERREUR: {e}")