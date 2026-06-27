"""
scripts/find_good_ocr_example.py

Cherche, parmi des documents à confiance OCR moyenne (40-65%),
celui qui présente le plus fort gain entre Tesseract brut et Tesseract
prétraité (CLAHE + Otsu), afin de choisir un exemple démonstratif
pour le rapport.

Usage :
    py scripts\\find_good_ocr_example.py
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras
import fitz
from PIL import Image

from backend.agents.ocr_agent import tesseract_ocr, enhanced_ocr

DB_CONFIG = dict(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT filename, original_path, ocr_confidence
        FROM documents
        WHERE ocr_confidence BETWEEN 40 AND 65
          AND original_path IS NOT NULL AND original_path != ''
        ORDER BY RANDOM()
        LIMIT 8
    """)
    candidates = cur.fetchall()
    conn.close()

    results = []

    for row in candidates:
        filename = row["filename"]
        path = row["original_path"]

        if not os.path.exists(path):
            print(f"{filename:<50} fichier introuvable, ignoré")
            continue

        try:
            doc = fitz.open(path)
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            doc.close()

            text_raw, conf_raw = tesseract_ocr(img)
            text_enh, conf_enh = enhanced_ocr(img)
            gain = conf_enh - conf_raw

            print(f"{filename:<50} brut={conf_raw:5.1f}%  pretraite={conf_enh:5.1f}%  gain={gain:+5.1f}")
            results.append({
                "filename": filename, "path": path,
                "conf_raw": conf_raw, "conf_enh": conf_enh, "gain": gain,
                "text_raw": text_raw, "text_enh": text_enh,
            })
        except Exception as e:
            print(f"{filename:<50} ERREUR: {e}")

    if results:
        best = max(results, key=lambda r: r["gain"])
        print("\n" + "=" * 70)
        print(f"Meilleur candidat : {best['filename']}")
        print(f"Gain : {best['gain']:+.1f} points ({best['conf_raw']:.1f}% -> {best['conf_enh']:.1f}%)")
        print("=" * 70)
        print(f"\n=== TEXTE BRUT ===\n{best['text_raw'][:500]}")
        print(f"\n=== TEXTE PRETRAITE ===\n{best['text_enh'][:500]}")


if __name__ == "__main__":
    main()