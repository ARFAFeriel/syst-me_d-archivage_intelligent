"""
scripts/get_ocr_example.py

Récupère le chemin d'un document par son nom de fichier, puis affiche
le texte OCR obtenu en mode brut et en mode prétraité, avec leurs scores
de confiance respectifs. Utile pour choisir un exemple représentatif
à insérer dans le rapport.

Usage :
    py scripts\\get_ocr_example.py "WO-ES001025.pdf"
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import fitz
from PIL import Image

from backend.agents.ocr_agent import tesseract_ocr, enhanced_ocr

DB_CONFIG = dict(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")


def main():
    if len(sys.argv) < 2:
        print("Usage : py scripts\\get_ocr_example.py <nom_du_fichier.pdf>")
        return

    filename = sys.argv[1]

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT original_path FROM documents WHERE filename = %s LIMIT 1;", (filename,))
    row = cur.fetchone()
    conn.close()

    if not row:
        print(f"[ERREUR] Aucun document trouvé pour le nom : {filename}")
        return

    path = row[0]
    print(f"Chemin trouvé : {path}\n")

    if not os.path.exists(path):
        print(f"[ERREUR] Le fichier n'existe pas sur le disque à ce chemin.")
        return

    doc = fitz.open(path)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    doc.close()

    text_raw, conf_raw = tesseract_ocr(img)
    text_enh, conf_enh = enhanced_ocr(img)

    print(f"=== BRUT (confiance = {conf_raw:.1f}%) ===")
    print(text_raw[:600])
    print(f"\n=== PRÉTRAITÉ (confiance = {conf_enh:.1f}%) ===")
    print(text_enh[:600])


if __name__ == "__main__":
    main()