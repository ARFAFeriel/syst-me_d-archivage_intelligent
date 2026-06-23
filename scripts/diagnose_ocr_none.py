# -*- coding: utf-8 -*-
"""
diagnose_ocr_none.py
=====================
Diagnostic ciblé : pourquoi ces documents ont-ils ocr_engine = 'ocr_v5_none' ?

Teste un échantillon de documents (par défaut 30) parmi ceux à
ocr_confidence < 20 et trace précisément à quelle étape ça échoue :

  A) Conversion PDF → image impossible (page.to_image() ET pdf2image échouent)
     → cause technique, potentiellement réparable (poppler manquant, PDF
       corrompu, format non supporté)
  B) Image obtenue MAIS Tesseract + OpenCV enhanced n'extraient aucun texte
     → page probablement réellement vide/illisible (photo noire, page blanche,
       résolution trop faible, scan totalement illisible)
  C) Erreur à l'ouverture même du PDF (pdfplumber.open() plante)
     → fichier corrompu ou non-PDF

Usage :
  py scripts/diagnose_ocr_none.py            # 30 documents (défaut)
  py scripts/diagnose_ocr_none.py --sample 50

Sortie : tableau récapitulatif + détail par document dans
  evaluation/diagnose_ocr_none.csv
"""

import sys
import os
import io
import csv
import argparse
from pathlib import Path

PROJECT_ROOT = Path(r"C:\Users\ferie\Desktop\système_darchivage_intelligent")
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
import psycopg2.extras

DB_CONFIG = dict(host="localhost", port=5434, dbname="nouv_db",
                  user="postgres", password="Nouv26")

OUTPUT_CSV = PROJECT_ROOT / "evaluation" / "diagnose_ocr_none.csv"
OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)


def fetch_sample(n):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, filename, original_path, doc_type, ocr_confidence
        FROM documents
        WHERE ocr_confidence < 20
          AND original_path IS NOT NULL
          AND original_path != ''
        ORDER BY RANDOM()
        LIMIT %s
    """, (n,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def diagnose_one(row):
    """Reproduit pas à pas process_page() / _process_sync() pour un document,
    en traçant précisément où ça échoue."""
    import pdfplumber

    diag = {
        "id": row["id"],
        "filename": row["filename"],
        "doc_type": row["doc_type"],
        "original_path": row["original_path"],
        "cause": None,
        "detail": "",
    }

    path = row["original_path"]
    if not os.path.exists(path):
        diag["cause"] = "FICHIER_INTROUVABLE"
        diag["detail"] = f"Chemin inexistant sur disque : {path}"
        return diag

    try:
        with open(path, "rb") as f:
            file_bytes = f.read()
    except Exception as e:
        diag["cause"] = "LECTURE_FICHIER_ECHOUEE"
        diag["detail"] = str(e)
        return diag

    if len(file_bytes) == 0:
        diag["cause"] = "FICHIER_VIDE"
        diag["detail"] = "0 octet sur disque"
        return diag

    # ── Étape C : ouverture pdfplumber ──────────────────────────────────────
    try:
        pdf = pdfplumber.open(io.BytesIO(file_bytes))
    except Exception as e:
        diag["cause"] = "C_OUVERTURE_PDF_ECHOUEE"
        diag["detail"] = str(e)
        return diag

    try:
        if len(pdf.pages) == 0:
            diag["cause"] = "PDF_SANS_PAGES"
            diag["detail"] = "pdfplumber: 0 page"
            pdf.close()
            return diag

        page = pdf.pages[0]

        # ── Étape 1 : texte natif ────────────────────────────────────────────
        try:
            native_text = (page.extract_text() or "").strip()
        except Exception as e:
            native_text = ""
            diag["detail"] += f"[extract_text erreur: {e}] "

        diag["native_chars"] = len(native_text)
        if len(native_text) >= 50:
            diag["cause"] = "OK_TEXTE_NATIF_SUFFISANT"
            diag["detail"] += f"{len(native_text)} caractères natifs trouvés — ne devrait PAS être 'none' !"
            pdf.close()
            return diag

        # ── Étape A : conversion en image ────────────────────────────────────
        pil_img = None
        err_to_image = None
        try:
            pil_img = page.to_image(resolution=400).original
        except Exception as e:
            err_to_image = str(e)
            try:
                from pdf2image import convert_from_bytes
                images = convert_from_bytes(file_bytes, dpi=400, first_page=1, last_page=1)
                pil_img = images[0] if images else None
            except Exception as e2:
                diag["cause"] = "A_CONVERSION_IMAGE_ECHOUEE"
                diag["detail"] += (
                    f"page.to_image() erreur: {err_to_image} | "
                    f"pdf2image erreur: {e2}"
                )
                pdf.close()
                return diag

        if pil_img is None:
            diag["cause"] = "A_CONVERSION_IMAGE_VIDE"
            diag["detail"] += "pil_img est None après les deux tentatives"
            pdf.close()
            return diag

        diag["image_size"] = f"{pil_img.size[0]}x{pil_img.size[1]}"

        # ── Étape B : tentative Tesseract réelle ─────────────────────────────
        import pytesseract
        import numpy as np
        try:
            data = pytesseract.image_to_data(
                pil_img, config="--psm 6 --oem 3 -l fra+eng",
                output_type=pytesseract.Output.DICT
            )
            confs = [int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) > 0]
            text = " ".join(w for w, c in zip(data["text"], data["conf"])
                             if str(c).lstrip("-").isdigit() and int(c) > 0 and w.strip())
            diag["tesseract_chars"] = len(text.strip())
            diag["tesseract_conf"] = round(float(np.mean(confs)), 1) if confs else 0.0

            if not text.strip():
                diag["cause"] = "B_TESSERACT_AUCUN_TEXTE"
                diag["detail"] += (
                    f"Image obtenue ({diag['image_size']}) mais Tesseract "
                    f"n'extrait aucun caractère avec confiance > 0"
                )
            else:
                diag["cause"] = "B_OK_MAIS_FAIBLE"
                diag["detail"] += (
                    f"Tesseract extrait {len(text.strip())} caractères, "
                    f"conf={diag['tesseract_conf']}% — devrait normalement "
                    f"être classé tesseract, pas none (vérifier fuse_ocr_results)"
                )
        except Exception as e:
            diag["cause"] = "B_TESSERACT_EXCEPTION"
            diag["detail"] += f"pytesseract erreur: {e}"

    finally:
        pdf.close()

    return diag


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=30)
    args = parser.parse_args()

    print("=" * 70)
    print(f"  DIAGNOSTIC OCR 'none' — échantillon de {args.sample} documents")
    print("=" * 70)

    rows = fetch_sample(args.sample)
    print(f"\n{len(rows)} documents récupérés (ocr_confidence < 20%)\n")

    results = []
    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {row['filename'][:60]}...")
        diag = diagnose_one(row)
        results.append(diag)
        print(f"        → {diag['cause']}")

    # ── Récapitulatif ────────────────────────────────────────────────────────
    from collections import Counter
    causes = Counter(r["cause"] for r in results)

    print("\n" + "=" * 70)
    print("  RÉCAPITULATIF")
    print("=" * 70)
    for cause, count in causes.most_common():
        pct = count / len(results) * 100
        print(f"  {cause:<35} : {count:>3} ({pct:.1f}%)")

    # ── CSV détaillé ─────────────────────────────────────────────────────────
    fieldnames = ["id", "filename", "doc_type", "original_path", "cause",
                  "detail", "native_chars", "image_size", "tesseract_chars",
                  "tesseract_conf"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[OK] Détail complet → {OUTPUT_CSV}")
    print("\n[TERMINÉ]")


if __name__ == "__main__":
    main()