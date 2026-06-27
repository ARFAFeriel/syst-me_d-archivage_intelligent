"""
scripts/compare_ocr_engines.py

Compare 3 configurations d'extraction OCR sur un échantillon de documents
réels du corpus NouvelAir :

  1. Tesseract SANS prétraitement   (tesseract_ocr() sur l'image brute)
  2. Tesseract AVEC prétraitement   (enhanced_ocr() : CLAHE + Otsu + multi-PSM)
  3. EasyOCR                        (librairie tierce, non intégrée au pipeline)

Usage :
    py scripts\\compare_ocr_engines.py                  # échantillon stratifié (30/classe)
    py scripts\\compare_ocr_engines.py --full           # tous les documents valides
    py scripts\\compare_ocr_engines.py --sample 50      # 50 documents par classe
    py scripts\\compare_ocr_engines.py --limit 200      # 200 documents au total (rapide)

Pré-requis :
    pip install easyocr --break-system-packages   (si pas déjà installé)

Sortie :
    scripts/ocr_comparison_report.json
    Affichage console d'un tableau récapitulatif par moteur.
"""

import sys
import os
import io
import json
import time
import argparse
import statistics
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
import fitz  # PyMuPDF, utilisé uniquement ici pour rasteriser une page en image
import psycopg2
import psycopg2.extras

from backend.agents.ocr_agent import preprocess_image, tesseract_ocr, enhanced_ocr

# Connexion DB — ajuster si nécessaire selon ton .env
DB_CONFIG = dict(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")


def fetch_sample(sample_per_class, limit):
    """Récupère des documents avec un original_path valide (fichier sur disque)."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT doc_type, COUNT(*) AS cnt
        FROM documents
        WHERE doc_type IS NOT NULL
          AND original_path IS NOT NULL
          AND original_path != ''
        GROUP BY doc_type
        ORDER BY cnt DESC
    """)
    class_counts = cur.fetchall()
    print("\n[BDD] Distribution des classes disponibles :")
    for row in class_counts:
        print(f"  {row['doc_type']:<20} : {row['cnt']} docs")

    rows = []
    if sample_per_class:
        for row in class_counts:
            dtype = row["doc_type"]
            cur.execute("""
                SELECT id, filename, original_path, doc_type, ocr_confidence
                FROM documents
                WHERE doc_type = %s
                  AND original_path IS NOT NULL
                  AND original_path != ''
                ORDER BY RANDOM()
                LIMIT %s
            """, (dtype, sample_per_class))
            rows.extend(dict(r) for r in cur.fetchall())
    else:
        query = """
            SELECT id, filename, original_path, doc_type, ocr_confidence
            FROM documents
            WHERE doc_type IS NOT NULL
              AND original_path IS NOT NULL
              AND original_path != ''
            ORDER BY id
        """
        if limit:
            query += f" LIMIT {int(limit)}"
        cur.execute(query)
        rows = [dict(r) for r in cur.fetchall()]

    conn.close()
    return rows


def pdf_first_page_to_image(path: str) -> Image.Image | None:
    """Rasterise la première page du PDF en image PIL (zoom x2 pour une meilleure résolution)."""
    try:
        doc = fitz.open(path)
        if doc.page_count == 0:
            return None
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        doc.close()
        return img
    except Exception as e:
        print(f"  [ERREUR rasterisation] {path} : {e}")
        return None


def run_easyocr(reader, pil_img: Image.Image) -> tuple[str, float]:
    """Exécute EasyOCR sur l'image et retourne (texte, confiance moyenne en %)."""
    import numpy as np
    img_np = np.array(pil_img.convert("RGB"))
    results = reader.readtext(img_np)
    if not results:
        return "", 0.0
    texts = [r[1] for r in results]
    confidences = [r[2] for r in results]
    return " ".join(texts), float(statistics.mean(confidences)) * 100


def main():
    parser = argparse.ArgumentParser(description="Comparaison des moteurs OCR")
    parser.add_argument("--sample", type=int, default=30,
                         help="Documents par classe (échantillon stratifié, défaut: 30)")
    parser.add_argument("--full", action="store_true",
                         help="Évalue TOUS les documents valides (ignore --sample)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Limite le nombre total de documents (mode --full uniquement)")
    args = parser.parse_args()

    sample_per_class = None if args.full else args.sample
    rows = fetch_sample(sample_per_class, args.limit if args.full else None)

    if not rows:
        print("[ERREUR] Aucun document à évaluer.")
        return

    print(f"\n[Init] {len(rows)} documents à traiter avec 3 configurations OCR.")
    print("[Init] Chargement d'EasyOCR (peut prendre du temps au premier lancement)...")
    import easyocr
    reader = easyocr.Reader(["fr", "en"], gpu=False)
    print("[Init] EasyOCR prêt.\n")

    results = {"tesseract_brut": [], "tesseract_pretraite": [], "easyocr": []}
    errors = 0

    for i, row in enumerate(rows, 1):
        path = row["original_path"]
        if not os.path.exists(path):
            errors += 1
            continue

        print(f"[{i}/{len(rows)}] {row['filename']} ({row['doc_type']})")

        img = pdf_first_page_to_image(path)
        if img is None:
            errors += 1
            continue

        # 1. Tesseract SANS prétraitement
        t0 = time.time()
        try:
            text_raw, conf_raw = tesseract_ocr(img)
        except Exception as e:
            text_raw, conf_raw = "", 0.0
            print(f"  [ERREUR tesseract brut] {e}")
        dt_raw = time.time() - t0
        results["tesseract_brut"].append({
            "id": row["id"], "doc_type": row["doc_type"],
            "confidence": conf_raw, "text_len": len(text_raw), "time_s": round(dt_raw, 2),
        })

        # 2. Tesseract AVEC prétraitement (CLAHE + Otsu + multi-PSM)
        t0 = time.time()
        try:
            text_enh, conf_enh = enhanced_ocr(img)
        except Exception as e:
            text_enh, conf_enh = "", 0.0
            print(f"  [ERREUR tesseract prétraité] {e}")
        dt_enh = time.time() - t0
        results["tesseract_pretraite"].append({
            "id": row["id"], "doc_type": row["doc_type"],
            "confidence": conf_enh, "text_len": len(text_enh), "time_s": round(dt_enh, 2),
        })

        # 3. EasyOCR
        t0 = time.time()
        try:
            text_easy, conf_easy = run_easyocr(reader, img)
        except Exception as e:
            text_easy, conf_easy = "", 0.0
            print(f"  [ERREUR easyocr] {e}")
        dt_easy = time.time() - t0
        results["easyocr"].append({
            "id": row["id"], "doc_type": row["doc_type"],
            "confidence": conf_easy, "text_len": len(text_easy), "time_s": round(dt_easy, 2),
        })

        print(f"  Tesseract brut      : {conf_raw:5.1f}%  ({dt_raw:.2f}s)")
        print(f"  Tesseract prétraité : {conf_enh:5.1f}%  ({dt_enh:.2f}s)")
        print(f"  EasyOCR             : {conf_easy:5.1f}%  ({dt_easy:.2f}s)")

    # ── Synthèse ──────────────────────────────────────────────
    summary = {}
    for engine, items in results.items():
        if not items:
            continue
        confs = [it["confidence"] for it in items]
        times = [it["time_s"] for it in items]
        zero_count = sum(1 for c in confs if c == 0.0)
        summary[engine] = {
            "n_documents": len(items),
            "confidence_mean": round(statistics.mean(confs), 2),
            "confidence_median": round(statistics.median(confs), 2),
            "confidence_stdev": round(statistics.stdev(confs), 2) if len(confs) > 1 else 0.0,
            "zero_score_count": zero_count,
            "zero_score_pct": round(100 * zero_count / len(items), 2),
            "time_mean_s": round(statistics.mean(times), 3),
            "time_total_s": round(sum(times), 1),
        }

    report = {
        "date": datetime.now().isoformat(),
        "n_documents_total": len(rows),
        "n_errors_fichier_introuvable": errors,
        "summary": summary,
        "details": results,
    }

    out_path = os.path.join(os.path.dirname(__file__), "ocr_comparison_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("  RÉSUMÉ COMPARATIF DES MOTEURS OCR")
    print("=" * 70)
    print(f"{'Moteur':<22} {'Conf. moy.':>11} {'Médiane':>9} {'%=0':>7} {'Temps/doc':>10}")
    print("-" * 70)
    for engine, s in summary.items():
        print(f"{engine:<22} {s['confidence_mean']:>9.1f}% {s['confidence_median']:>8.1f}% "
              f"{s['zero_score_pct']:>6.1f}% {s['time_mean_s']:>9.2f}s")
    print("=" * 70)
    print(f"\n[OK] Rapport complet sauvegardé : {out_path}")


if __name__ == "__main__":
    main()