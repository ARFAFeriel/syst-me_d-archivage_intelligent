"""
evaluate_classifier.py
======================
Génère un test_set depuis nouv_db, évalue le classifier TF-IDF,
et exporte les métriques réelles pour le rapport PFE.

Usage : python evaluate_classifier.py
Sortie : test_set.csv + metrics_report.txt
"""

import sys
import os
import pickle
import csv
import time
import asyncio
import numpy as np
import psycopg2
from pathlib import Path
from collections import defaultdict

# ── Config BDD ────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "nouv_db",
    "user": "postgres",
    "password": "Nouv26"
}

# Chemin vers le modèle (adapter si besoin)
MODEL_PATH = Path(r"C:\Users\ferie\Desktop\système_darchivage_intelligent\backend\models\classifier_model.pkl")

# Chemin de sortie
OUTPUT_DIR = Path(r"C:\Users\ferie\Desktop\système_darchivage_intelligent\evaluation")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEST_SET_PATH = OUTPUT_DIR / "test_set.csv"
METRICS_PATH  = OUTPUT_DIR / "metrics_report.txt"

# Taille d'échantillon par classe (stratifié)
SAMPLE_PER_CLASS = 30

# ── Chargement modèle ─────────────────────────────────────────────────────────
def load_model():
    if not MODEL_PATH.exists():
        print(f"[ERREUR] Modèle introuvable : {MODEL_PATH}")
        sys.exit(1)
    with open(MODEL_PATH, "rb") as f:
        data = pickle.load(f)
    print(f"[OK] Modèle chargé — classes : {data['model'].classes_}")
    return data["model"], data["vectorizer"]

# ── Extraction BDD ────────────────────────────────────────────────────────────
def fetch_sample(conn):
    """
    Tire un échantillon stratifié : jusqu'à SAMPLE_PER_CLASS docs par type,
    avec du texte OCR non vide.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT doc_type, COUNT(*) 
        FROM documents 
        WHERE status = 'ARCHIVED'
          AND doc_type IS NOT NULL
          AND ocr_text IS NOT NULL 
          AND LENGTH(ocr_text) > 50
        GROUP BY doc_type
        ORDER BY COUNT(*) DESC
    """)
    class_counts = cur.fetchall()
    print("\n[BDD] Distribution des classes disponibles :")
    for dtype, cnt in class_counts:
        print(f"  {dtype:<20} : {cnt} docs")

    rows = []
    for dtype, cnt in class_counts:
        limit = min(SAMPLE_PER_CLASS, cnt)
        cur.execute("""
            SELECT id, doc_type, ocr_text, original_path, filename
            FROM documents
            WHERE status = 'ARCHIVED'
              AND doc_type = %s
              AND ocr_text IS NOT NULL
              AND LENGTH(ocr_text) > 50
            ORDER BY RANDOM()
            LIMIT %s
        """, (dtype, limit))
        rows.extend(cur.fetchall())

    print(f"\n[OK] {len(rows)} documents sélectionnés pour évaluation")
    cur.close()
    return rows

# ── Préparation texte (identique au classifier) ───────────────────────────────
def prepare_text(text: str, filename: str, original_path: str) -> str:
    parts = []
    if text:
        parts.append(text[:3000].lower())
    if filename:
        fn = filename.replace("-", " ").replace("_", " ").replace(".", " ").lower()
        parts.append(f"FILENAME {fn}")
    if original_path:
        path_parts = original_path.replace("\\", "/").split("/")
        parts.append(f"PATH {' '.join(path_parts).lower()}")
    return " ".join(parts)

# ── Évaluation ────────────────────────────────────────────────────────────────
def evaluate(model, vectorizer, rows):
    y_true = []
    y_pred = []
    results = []

    for doc_id, true_type, ocr_text, original_path, filename in rows:
        filename = filename or ""
        original_path = original_path or ""
        combined = prepare_text(ocr_text or "", filename, original_path)
        X = vectorizer.transform([combined])
        proba = model.predict_proba(X)[0]
        pred_idx = int(np.argmax(proba))
        pred_type = model.classes_[pred_idx]
        confidence = float(proba[pred_idx])

        y_true.append(true_type)
        y_pred.append(pred_type)
        results.append({
            "id": doc_id,
            "true_type": true_type,
            "pred_type": pred_type,
            "confidence": round(confidence, 4),
            "correct": true_type == pred_type,
            "filename": filename,
        })

    return y_true, y_pred, results

# ── Métriques manuelles (sans sklearn requis) ─────────────────────────────────
def compute_metrics(y_true, y_pred):
    classes = sorted(set(y_true + y_pred))
    metrics = {}

    for cls in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p == cls)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != cls and p == cls)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p != cls)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        support   = sum(1 for t in y_true if t == cls)

        metrics[cls] = {
            "precision": round(precision, 4),
            "recall":    round(recall, 4),
            "f1":        round(f1, 4),
            "support":   support
        }

    # Weighted average
    total = len(y_true)
    w_precision = sum(m["precision"] * m["support"] for m in metrics.values()) / total
    w_recall    = sum(m["recall"]    * m["support"] for m in metrics.values()) / total
    w_f1        = sum(m["f1"]        * m["support"] for m in metrics.values()) / total
    accuracy    = sum(1 for t, p in zip(y_true, y_pred) if t == p) / total

    return metrics, {
        "accuracy":           round(accuracy, 4),
        "weighted_precision": round(w_precision, 4),
        "weighted_recall":    round(w_recall, 4),
        "weighted_f1":        round(w_f1, 4),
        "total_samples":      total
    }

# ── Export CSV ────────────────────────────────────────────────────────────────
def save_test_set(results):
    with open(TEST_SET_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "true_type", "pred_type", "confidence", "correct", "filename"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n[OK] test_set.csv sauvegardé → {TEST_SET_PATH}")

# ── Export rapport texte ──────────────────────────────────────────────────────
def save_metrics_report(metrics, overall):
    lines = []
    lines.append("=" * 65)
    lines.append("  RAPPORT D'ÉVALUATION — CLASSIFIER TF-IDF + LR")
    lines.append("  Système d'archivage intelligent — NouvelAir MRO")
    lines.append("=" * 65)
    lines.append(f"\nEchantillon total  : {overall['total_samples']} documents")
    lines.append(f"Accuracy           : {overall['accuracy']*100:.1f}%")
    lines.append(f"Weighted Precision : {overall['weighted_precision']*100:.1f}%")
    lines.append(f"Weighted Recall    : {overall['weighted_recall']*100:.1f}%")
    lines.append(f"Weighted F1-score  : {overall['weighted_f1']*100:.1f}%")
    lines.append("\n" + "-" * 65)
    lines.append(f"{'Classe':<22} {'Precision':>9} {'Recall':>8} {'F1':>8} {'Support':>8}")
    lines.append("-" * 65)

    for cls, m in sorted(metrics.items()):
        lines.append(
            f"{cls:<22} {m['precision']*100:>8.1f}% {m['recall']*100:>7.1f}% "
            f"{m['f1']*100:>7.1f}% {m['support']:>8}"
        )

    lines.append("=" * 65)

    report = "\n".join(lines)
    print("\n" + report)

    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[OK] Rapport sauvegardé → {METRICS_PATH}")

    return report

# ── Métriques OCR depuis BDD ──────────────────────────────────────────────────
def fetch_ocr_metrics(conn):
    cur = conn.cursor()

    # Confidence moyenne (hors zéros)
    cur.execute("""
        SELECT 
            ROUND(AVG(ocr_confidence)::numeric, 1) as avg_conf,
            COUNT(*) FILTER (WHERE ocr_confidence > 0) as non_zero,
            COUNT(*) FILTER (WHERE ocr_confidence = 0) as zero_count,
            COUNT(*) as total,
            ROUND(MIN(ocr_confidence)::numeric, 1) as min_conf,
            ROUND(MAX(ocr_confidence)::numeric, 1) as max_conf
        FROM documents
        WHERE status = 'ARCHIVED' AND ocr_confidence > 0
    """)
    row = cur.fetchone()

    # Distribution par tranche
    cur.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE ocr_confidence >= 90) as high,
            COUNT(*) FILTER (WHERE ocr_confidence >= 70 AND ocr_confidence < 90) as medium,
            COUNT(*) FILTER (WHERE ocr_confidence >= 50 AND ocr_confidence < 70) as low,
            COUNT(*) FILTER (WHERE ocr_confidence < 50 AND ocr_confidence > 0) as very_low
        FROM documents WHERE status = 'ARCHIVED'
    """)
    dist = cur.fetchone()

    cur.close()
    return row, dist

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  ÉVALUATION SYSTÈME D'ARCHIVAGE INTELLIGENT — NouvelAir")
    print("=" * 65)

    # Connexion BDD
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("[OK] Connexion PostgreSQL établie")
    except Exception as e:
        print(f"[ERREUR] Connexion BDD impossible : {e}")
        sys.exit(1)

    # Métriques OCR
    print("\n── Métriques OCR ────────────────────────────────────────────")
    try:
        ocr_row, ocr_dist = fetch_ocr_metrics(conn)
        if ocr_row:
            avg_conf, non_zero, zero_count, total, min_conf, max_conf = ocr_row
            high, medium, low, very_low = ocr_dist
            print(f"  Confidence moyenne (hors zéros) : {avg_conf}%")
            print(f"  Min / Max                       : {min_conf}% / {max_conf}%")
            print(f"  Docs avec confidence > 0        : {non_zero} / {total}")
            print(f"  Docs avec confidence = 0        : {zero_count}")
            print(f"  Distribution :")
            print(f"    >= 90% (haute)     : {high}")
            print(f"    70-89% (moyenne)   : {medium}")
            print(f"    50-69% (faible)    : {low}")
            print(f"    < 50%  (très faib) : {very_low}")
    except Exception as e:
        print(f"  [ERREUR] {e}")

    # Classifier
    print("\n── Classifier TF-IDF + LR ───────────────────────────────────")
    model, vectorizer = load_model()
    rows = fetch_sample(conn)

    if not rows:
        print("[ERREUR] Aucun document récupéré depuis la BDD.")
        conn.close()
        sys.exit(1)

    y_true, y_pred, results = evaluate(model, vectorizer, rows)
    metrics, overall = compute_metrics(y_true, y_pred)
    save_test_set(results)
    save_metrics_report(metrics, overall)

    # Erreurs les plus fréquentes
    print("\n── Top confusions ───────────────────────────────────────────")
    confusion = defaultdict(int)
    for t, p in zip(y_true, y_pred):
        if t != p:
            confusion[(t, p)] += 1
    for (t, p), cnt in sorted(confusion.items(), key=lambda x: -x[1])[:5]:
        print(f"  {t:<20} → prédit {p:<20} ({cnt} fois)")

    conn.close()
    print(f"\n[DONE] Fichiers générés dans : {OUTPUT_DIR}")
    print("  → test_set.csv      (pour reproduire l'évaluation)")
    print("  → metrics_report.txt (à coller dans le rapport)")

if __name__ == "__main__":
    main()