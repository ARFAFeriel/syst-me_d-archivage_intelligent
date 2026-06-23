# -*- coding: utf-8 -*-
"""
diagnose_ocr_none_v2.py
=========================
Version corrigée : appelle DIRECTEMENT les vraies fonctions de
backend/agents/ocr_agent.py (tesseract_ocr, preprocess_image, enhanced_ocr,
fuse_ocr_results) au lieu de les réimplémenter — élimine tout risque de
divergence entre le diagnostic et le comportement réel en production.

Reproduit fidèlement process_page() étape par étape, avec un print après
CHAQUE étape pour voir exactement où best_text / best_conf changent ou
disparaissent.

Usage :
  py scripts/diagnose_ocr_none_v2.py --sample 10
"""

import sys
import os
import io
import argparse
from pathlib import Path

PROJECT_ROOT = Path(r"C:\Users\ferie\Desktop\système_darchivage_intelligent")
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
import psycopg2.extras

DB_CONFIG = dict(host="localhost", port=5434, dbname="nouv_db",
                  user="postgres", password="Nouv26")


def fetch_sample(n):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, filename, original_path
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=10)
    args = parser.parse_args()

    # ── Import direct des VRAIES fonctions du code de production ───────────
    from backend.agents.ocr_agent import (
        tesseract_ocr, preprocess_image, enhanced_ocr, fuse_ocr_results,
        content_score, OPENCV_THRESHOLD, MIN_NATIVE_CHARS,
    )
    import pdfplumber
    import numpy as np
    import cv2
    from PIL import Image

    rows = fetch_sample(args.sample)
    print(f"\n{len(rows)} documents à tester (réplique fidèle de process_page)\n")
    print("=" * 90)

    for row in rows:
        path = row["original_path"]
        filename = row["filename"]
        print(f"\n### Doc #{row['id']} — {filename}")
        print(f"    Chemin: {path}")

        if not os.path.exists(path):
            print("    [SKIP] fichier introuvable")
            continue

        with open(path, "rb") as f:
            file_bytes = f.read()

        try:
            pdf = pdfplumber.open(io.BytesIO(file_bytes))
            page = pdf.pages[0]
        except Exception as e:
            print(f"    [SKIP] ouverture PDF échouée: {e}")
            continue

        # ── Étape 1 : texte natif ────────────────────────────────────────────
        native_text = (page.extract_text() or "").strip()
        print(f"    [1] texte natif: {len(native_text)} chars (seuil={MIN_NATIVE_CHARS})")
        if len(native_text) >= MIN_NATIVE_CHARS:
            print("    [1] → texte natif suffisant, ne devrait pas être ici")
            pdf.close()
            continue

        # ── Étape 2 : conversion en image ────────────────────────────────────
        try:
            pil_img = page.to_image(resolution=400).original
            print(f"    [2] image obtenue via page.to_image(): {pil_img.size}")
        except Exception as e:
            print(f"    [2] page.to_image() échoué: {e}")
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(file_bytes, dpi=400, first_page=1, last_page=1)
            pil_img = images[0] if images else None
            print(f"    [2] fallback pdf2image: {'OK ' + str(pil_img.size) if pil_img else 'ECHEC'}")

        if pil_img is None:
            print("    [STOP] aucune image obtenue")
            pdf.close()
            continue

        # ── Étape 3 : Tesseract brut (VRAIE fonction) ───────────────────────
        tess_text, tess_conf = tesseract_ocr(pil_img)
        print(f"    [3] tesseract_ocr(brut)        → conf={tess_conf:.1f}% chars={len(tess_text)}")

        # ── Étape 4 : Tesseract + preprocessing (VRAIE fonction) ────────────
        try:
            preprocessed = preprocess_image(pil_img)
            tess_text2, tess_conf2 = tesseract_ocr(preprocessed)
            print(f"    [4] tesseract_ocr(preprocess)   → conf={tess_conf2:.1f}% chars={len(tess_text2)}")
            if tess_conf2 > tess_conf:
                tess_text, tess_conf = tess_text2, tess_conf2
                print(f"    [4] → adopté (meilleur)")
        except Exception as e:
            print(f"    [4] EXCEPTION preprocess_image: {e}")

        # ── Étape 4b : Otsu (VRAIE logique) ─────────────────────────────────
        try:
            img_np = np.array(pil_img.convert("L"))
            _, otsu = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            otsu_img = Image.fromarray(otsu)
            tess_text3, tess_conf3 = tesseract_ocr(otsu_img)
            print(f"    [4b] tesseract_ocr(otsu)        → conf={tess_conf3:.1f}% chars={len(tess_text3)}")
            if tess_conf3 > tess_conf:
                tess_text, tess_conf = tess_text3, tess_conf3
                print(f"    [4b] → adopté (meilleur)")
        except Exception as e:
            print(f"    [4b] EXCEPTION otsu: {e}")

        print(f"    [RÉSULTAT TESS FINAL] conf={tess_conf:.1f}% chars={len(tess_text)} "
              f"tess_text.strip() non-vide: {bool(tess_text.strip())}")

        # ── Étape 5 : OpenCV enhanced (VRAIE fonction, VRAIE condition) ─────
        opencv_text, opencv_conf = "", 0.0
        print(f"    [5] tess_conf={tess_conf:.1f} < OPENCV_THRESHOLD={OPENCV_THRESHOLD} "
              f"→ enhanced_ocr {'SERA appelé' if tess_conf < OPENCV_THRESHOLD else 'PAS appelé'}")
        if tess_conf < OPENCV_THRESHOLD:
            try:
                opencv_text, opencv_conf = enhanced_ocr(pil_img)
                print(f"    [5] enhanced_ocr() → conf={opencv_conf:.1f}% chars={len(opencv_text)}")
            except Exception as e:
                print(f"    [5] EXCEPTION enhanced_ocr: {e}")

        # ── Étape 6 : Fusion (VRAIE fonction) ───────────────────────────────
        try:
            final_text, final_conf, engine = fuse_ocr_results(
                tess_text, tess_conf, opencv_text, opencv_conf
            )
            print(f"    [6] fuse_ocr_results() → engine={engine} conf={final_conf:.1f}% "
                  f"chars={len(final_text)}")
        except Exception as e:
            print(f"    [6] EXCEPTION fuse_ocr_results: {e}")
            pdf.close()
            continue

        # ── Étape 7 : bonus contenu (VRAIE fonction) ────────────────────────
        try:
            bonus = content_score(final_text)
            final_conf_with_bonus = min(final_conf + bonus, 99.0)
            print(f"    [7] content_score bonus={bonus:.1f} → conf finale={final_conf_with_bonus:.1f}%")
        except Exception as e:
            print(f"    [7] EXCEPTION content_score: {e}")

        print(f"    >>> ENGINE FINAL ATTENDU: ocr_v5_{engine}")

        pdf.close()

    print("\n" + "=" * 90)
    print("[TERMINÉ]")


if __name__ == "__main__":
    main()