"""
Script de calcul des vraies métriques du classificateur
Accuracy, F1 Macro, F1 par classe, Matrice de confusion

Usage :
    python scripts/evaluate_classifier.py

Résultat : affichage console + sauvegarde JSON dans reports/classifier_metrics.json
"""
import sys
import os
import json
import asyncio
from pathlib import Path

# Ajouter le répertoire racine au path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from sklearn.metrics import (
    classification_report,
    f1_score,
    accuracy_score,
    confusion_matrix,
)
import numpy as np

# ── Config DB ─────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     5434,
    "database": "nouv_db",
    "user":     "postgres",
    "password": "Nouv26",
}

# ── Import classificateur ─────────────────────────────────────────────────────
from backend.agents.classifier_agent import ClassifierAgent


async def fetch_documents():
    """Récupère les docs avec texte OCR et doc_type depuis la DB."""
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT id, filename, original_path, ocr_text, doc_type
        FROM documents
        WHERE doc_type IS NOT NULL
          AND ocr_text IS NOT NULL
          AND ocr_text != ''
        ORDER BY id
    """)
    await conn.close()
    return rows


async def main():
    print("=" * 60)
    print("  Évaluation du Classificateur — NouvelAir MRO")
    print("=" * 60)

    # ── 1. Charger les documents ──────────────────────────────────────────────
    print("\n[1/4] Chargement des documents depuis la DB...")
    docs = await fetch_documents()
    print(f"      → {len(docs)} documents chargés")

    # ── 2. Reclassifier chaque document ──────────────────────────────────────
    print("\n[2/4] Reclassification en cours...")
    classifier = ClassifierAgent()

    y_true = []
    y_pred = []
    errors = []

    for i, doc in enumerate(docs):
        if i % 200 == 0:
            print(f"      → {i}/{len(docs)} traités...")

        try:
            result = await classifier.process(
                text=doc["ocr_text"],
                filename=doc["filename"],
                file_path=doc["original_path"] or "",
            )
            y_true.append(doc["doc_type"])
            y_pred.append(result.predicted_type.value
                          if hasattr(result.predicted_type, "value")
                          else str(result.predicted_type))
        except Exception as e:
            errors.append({"id": doc["id"], "error": str(e)})

    print(f"      → {len(y_true)} documents évalués, {len(errors)} erreurs")

    # ── 3. Calcul des métriques ───────────────────────────────────────────────
    print("\n[3/4] Calcul des métriques...")

    accuracy   = accuracy_score(y_true, y_pred)
    f1_macro   = f1_score(y_true, y_pred, average="macro",    zero_division=0)
    f1_weighted= f1_score(y_true, y_pred, average="weighted", zero_division=0)
    f1_micro   = f1_score(y_true, y_pred, average="micro",    zero_division=0)

    report = classification_report(
        y_true, y_pred,
        zero_division=0,
        output_dict=True,
    )
    report_str = classification_report(
        y_true, y_pred,
        zero_division=0,
    )

    # ── 4. Affichage ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RÉSULTATS GLOBAUX")
    print("=" * 60)
    print(f"  Accuracy     : {accuracy*100:.1f}%")
    print(f"  F1 Macro     : {f1_macro*100:.1f}%")
    print(f"  F1 Weighted  : {f1_weighted*100:.1f}%")
    print(f"  F1 Micro     : {f1_micro*100:.1f}%")
    print(f"  Documents    : {len(y_true)}")
    print("=" * 60)

    print("\n  DÉTAIL PAR CLASSE")
    print("-" * 60)
    print(report_str)

    # Classes les plus mal classifiées
    print("\n  TOP ERREURS (classes avec F1 < 70%)")
    print("-" * 60)
    for cls, metrics in report.items():
        if cls in ("accuracy", "macro avg", "weighted avg", "micro avg"):
            continue
        if isinstance(metrics, dict) and metrics.get("f1-score", 1) < 0.70:
            print(
                f"  {cls:<20} "
                f"P={metrics['precision']*100:.0f}%  "
                f"R={metrics['recall']*100:.0f}%  "
                f"F1={metrics['f1-score']*100:.0f}%  "
                f"support={metrics['support']}"
            )

    # ── 5. Sauvegarde JSON ────────────────────────────────────────────────────
    output_dir = Path("reports")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "classifier_metrics.json"

    metrics_json = {
        "total_documents": len(y_true),
        "accuracy":        round(accuracy,    4),
        "f1_macro":        round(f1_macro,    4),
        "f1_weighted":     round(f1_weighted, 4),
        "f1_micro":        round(f1_micro,    4),
        "per_class":       {
            cls: {
                "precision": round(m["precision"], 4),
                "recall":    round(m["recall"],    4),
                "f1":        round(m["f1-score"],  4),
                "support":   m["support"],
            }
            for cls, m in report.items()
            if cls not in ("accuracy", "macro avg", "weighted avg", "micro avg")
            and isinstance(m, dict)
        },
        "errors": len(errors),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics_json, f, indent=2, ensure_ascii=False)

    print(f"\n[4/4] Métriques sauvegardées → {output_path}")
    print("\nMets à jour le frontend avec ces valeurs réelles :")
    print(f"  Accuracy : {accuracy*100:.1f}%")
    print(f"  F1 Macro : {f1_macro*100:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())