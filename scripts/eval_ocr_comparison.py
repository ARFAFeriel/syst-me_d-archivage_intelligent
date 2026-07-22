"""
eval_ocr_comparison.py
========================
Compare deux configurations sur l'echantillon stratifie de 281 documents
(genere par select_ocr_sample.py) :

  1. Tesseract multi-PSM seul     -> tesseract_ocr() sans aucun pretraitement
  2. Pipeline OCR complet         -> process_page() : toutes les etapes reelles
                                      (Tesseract multi-PSM + preprocessing CLAHE/
                                      adaptive + Otsu + renfort OpenCV si <50% +
                                      fusion + bonus contenu)

Reutilise directement les fonctions de backend/agents/ocr_agent.py — aucune
reimplementation, pour garantir la fidelite avec le pipeline de production.

Prerequis :
    python scripts/select_ocr_sample.py   (genere ocr_eval_sample.csv)

Usage :
    python scripts/eval_ocr_comparison.py

Sortie :
    ocr_eval_results.csv   (resultat detaille par document)
    Affichage console des statistiques agregees (moyenne, mediane, ecart-type, temps)
"""
import sys
import csv
import time
import gc
import statistics
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pdfplumber
from PIL import Image

from backend.agents.ocr_agent import (
    tesseract_ocr,
    process_page,
    MAX_PAGES,
)

SAMPLE_CSV = ROOT / "ocr_eval_sample.csv"
RESULTS_CSV = ROOT / "ocr_eval_results.csv"


def load_sample():
    """Charge la liste des documents de l'echantillon depuis le CSV."""
    if not SAMPLE_CSV.exists():
        print(f"ERREUR : {SAMPLE_CSV} introuvable.")
        print("Lancez d'abord : python scripts/select_ocr_sample.py")
        sys.exit(1)

    docs = []
    with open(SAMPLE_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            docs.append(row)
    return docs


def get_first_page_image(pdf_path: Path):
    """
    Ouvre le PDF et retourne l'image PIL de la premiere page (resolution 400 DPI,
    coherent avec process_page() dans ocr_agent.py).
    Retourne (None, None) si le fichier est introuvable ou illisible.

    FIX : le fichier PDF doit rester ouvert pendant tout le traitement de la page
    (process_page() peut rappeler page.extract_text() ou page.to_image()).
    On ne ferme donc PAS le pdfplumber.open() ici — il est ferme explicitement
    par l'appelant via pdf_handle.close() apres usage.
    """
    try:
        pdf_handle = pdfplumber.open(str(pdf_path))
        if len(pdf_handle.pages) == 0:
            pdf_handle.close()
            return None, None, None
        page = pdf_handle.pages[0]
        pil_img = page.to_image(resolution=400).original
        return pil_img, page, pdf_handle
    except Exception as e:
        return None, None, None


def evaluate_document(doc: dict) -> dict:
    """
    Evalue un document selon les deux configurations.
    Retourne un dict avec les resultats des deux configs + metadonnees.
    """
    original_path = doc["original_path"]
    pdf_path = Path(original_path)

    result = {
        "id": doc["id"],
        "doc_type": doc["doc_type"],
        "filename": doc["filename"],
        "file_found": False,
        "tesseract_conf": 0.0,
        "tesseract_time_s": 0.0,
        "pipeline_conf": 0.0,
        "pipeline_engine": "none",
        "pipeline_time_s": 0.0,
    }

    if not pdf_path.exists():
        return result

    result["file_found"] = True

    pil_img, page, pdf_handle = get_first_page_image(pdf_path)
    if pil_img is None:
        return result

    try:
        # ── Configuration 1 : Tesseract multi-PSM seul ────────────────────────
        t0 = time.perf_counter()
        try:
            _, tess_conf = tesseract_ocr(pil_img)
        except Exception as e:
            tess_conf = 0.0
        result["tesseract_time_s"] = round(time.perf_counter() - t0, 3)
        result["tesseract_conf"] = round(tess_conf, 2)

        # ── Configuration 2 : Pipeline complet (process_page) ─────────────────
        t0 = time.perf_counter()
        try:
            with open(pdf_path, "rb") as f:
                file_bytes = f.read()
            page_result = process_page(page, page_num=1, file_bytes=file_bytes, page_index=0)
            result["pipeline_conf"] = round(page_result["confidence"], 2)
            result["pipeline_engine"] = page_result["engine"]
        except Exception as e:
            result["pipeline_conf"] = 0.0
            result["pipeline_engine"] = "error"
        result["pipeline_time_s"] = round(time.perf_counter() - t0, 3)
    finally:
        # FIX : fermer explicitement le PDF + liberer l'image pour eviter
        # l'accumulation memoire sur 281 documents traites en boucle.
        if pdf_handle is not None:
            pdf_handle.close()
        del pil_img
        gc.collect()

    return result


def compute_stats(values: list[float]) -> dict:
    """Calcule moyenne, mediane, ecart-type pour une liste de valeurs."""
    if not values:
        return {"mean": 0.0, "median": 0.0, "stdev": 0.0}
    return {
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
    }


def main():
    docs = load_sample()
    print(f"Echantillon charge : {len(docs)} documents\n")

    # ── Option de limite pour test rapide ──────────────────────────────────────
    # Usage : python scripts/eval_ocr_comparison.py 10
    # → traite seulement les 10 premiers documents pour estimer le temps total
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            docs = docs[:limit]
            print(f"MODE TEST : limite a {limit} documents\n")
        except ValueError:
            print(f"Argument ignore (doit etre un nombre) : {sys.argv[1]}\n")

    results = []
    n_processed = 0
    n_not_found = 0
    t_start_total = time.perf_counter()

    fieldnames = ["id", "doc_type", "filename", "file_found",
                  "tesseract_conf", "tesseract_time_s",
                  "pipeline_conf", "pipeline_engine", "pipeline_time_s"]

    for i, doc in enumerate(docs, 1):
        print(f"[{i}/{len(docs)}] {doc['filename']} ({doc['doc_type']})...", end=" ")
        r = evaluate_document(doc)
        results.append(r)

        if not r["file_found"]:
            n_not_found += 1
            print("FICHIER INTROUVABLE")
        else:
            n_processed += 1
            print(
                f"Tesseract={r['tesseract_conf']:.1f}% "
                f"({r['tesseract_time_s']:.2f}s) | "
                f"Pipeline={r['pipeline_conf']:.1f}% "
                f"engine={r['pipeline_engine']} "
                f"({r['pipeline_time_s']:.2f}s)"
            )

        # FIX : sauvegarde incrementale tous les 10 documents — si le script
        # plante plus tard, les resultats deja calcules ne sont pas perdus.
        if i % 10 == 0 or i == len(docs):
            with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)

    t_total = time.perf_counter() - t_start_total
    print(f"\nTemps total pour {len(docs)} documents : {t_total:.1f}s ({t_total/60:.1f} min)")
    if limit:
        estimated_281 = (t_total / limit) * 281
        print(
            f"Estimation pour 281 documents : ~{estimated_281:.0f}s "
            f"(~{estimated_281/60:.1f} min)"
        )

    # ── Statistiques agregees (uniquement sur les documents trouves) ─────────
    valid = [r for r in results if r["file_found"]]

    tess_confs = [r["tesseract_conf"] for r in valid]
    tess_times = [r["tesseract_time_s"] for r in valid]
    pipe_confs = [r["pipeline_conf"] for r in valid]
    pipe_times = [r["pipeline_time_s"] for r in valid]

    tess_stats = compute_stats(tess_confs)
    pipe_stats = compute_stats(pipe_confs)
    tess_time_stats = compute_stats(tess_times)
    pipe_time_stats = compute_stats(pipe_times)

    print("\n" + "=" * 70)
    print("RESULTATS AGREGES")
    print("=" * 70)
    print(f"Documents traites      : {n_processed} / {len(docs)}")
    print(f"Fichiers introuvables  : {n_not_found}")
    print()
    print(f"{'Configuration':<25} {'Conf. moy.':>12} {'Mediane':>10} {'Ecart-type':>12} {'Temps moy.':>12}")
    print("-" * 75)
    print(
        f"{'Tesseract multi-PSM':<25} "
        f"{tess_stats['mean']:>11.2f}% "
        f"{tess_stats['median']:>9.2f}% "
        f"{tess_stats['stdev']:>11.2f}% "
        f"{tess_time_stats['mean']:>10.2f}s"
    )
    print(
        f"{'Pipeline complet':<25} "
        f"{pipe_stats['mean']:>11.2f}% "
        f"{pipe_stats['median']:>9.2f}% "
        f"{pipe_stats['stdev']:>11.2f}% "
        f"{pipe_time_stats['mean']:>10.2f}s"
    )
    print()
    print(f"Resultats detailles sauvegardes dans : {RESULTS_CSV}")


if __name__ == "__main__":
    main()