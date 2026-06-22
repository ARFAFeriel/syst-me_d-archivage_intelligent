import sys
sys.path.insert(0, r"C:\Users\ferie\Desktop\système_darchivage_intelligent")

import psycopg2
import pdfplumber

from backend.agents.ocr_agent import (
    tesseract_ocr, preprocess_image, enhanced_ocr, OPENCV_THRESHOLD
)

conn = psycopg2.connect(
    host="localhost", port=5434, dbname="nouv_db",
    user="postgres", password="Nouv26"
)
cur = conn.cursor()
cur.execute("""
    SELECT id, filename, original_path
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

print(f"{'ID':<6}{'Fichier':<35}{'Conf après fix':<16}{'Caractères':<12}")

for doc_id, filename, path in rows:
    try:
        with pdfplumber.open(path) as pdf:
            page = pdf.pages[0]
            pil_img = page.to_image(resolution=400).original

        tess_text, tess_conf = tesseract_ocr(pil_img)

        preprocessed = preprocess_image(pil_img)
        tess_text2, tess_conf2 = tesseract_ocr(preprocessed)
        if tess_conf2 > tess_conf:
            tess_text, tess_conf = tess_text2, tess_conf2

        if tess_conf < OPENCV_THRESHOLD:
            opencv_text, opencv_conf = enhanced_ocr(pil_img)
            if opencv_conf > tess_conf:
                tess_text, tess_conf = opencv_text, opencv_conf

        print(f"{doc_id:<6}{filename[:33]:<35}{round(tess_conf,1):<16}{len(tess_text):<12}")
    except Exception as e:
        print(f"{doc_id:<6}{filename[:33]:<35}ERREUR: {e}")