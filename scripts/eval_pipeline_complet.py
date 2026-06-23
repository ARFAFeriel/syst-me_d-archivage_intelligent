# -*- coding: utf-8 -*-
"""
eval_pipeline_complet.py
=========================
Évaluation FIDÈLE du système complet de classification — réplique exactement
la logique de PipelineOrchestrator.test_document() :

  OCR réel (OCRAgent._process_sync)
    → NER réel (NERAgent.process — Groq LLM + regex fallback)
    → AircraftResolver (lecture DB, lookup ES reference)
    → Classifier réel (ClassifierAgent.process — règles chemin internes
      + filename ES###### + ML TF-IDF/LR + NER boost + LLM fallback)
    → Correction PATH_TO_ENUM (ProfileRegistry.infer_from_path, niveau pipeline)
    → LinkedWP resolver (catégorie, pas le type)

Contrairement à scripts/eval_with_path.py, ce script :
  - Relance l'OCR réel sur le PDF (pas le ocr_text déjà en base, potentiellement
    obsolète ou à confidence=0 suite au crash fra.traineddata)
  - Réplique la correction PATH_TO_ENUM de pipeline.py (que eval_with_path.py
    ignore complètement, puisqu'il n'appelle que ClassifierAgent.process())

ATTENTION — limite connue (à mentionner dans le rapport) :
  PATH_TO_ENUM (pipeline.py) compare doc_type.lower() — où doc_type provient de
  ProfileRegistry.infer_from_path() — à ses propres clés ('job_card',
  'work_order', 'ncr', 'atl', 'ad', 'sb', 'rct', 'certificate', 'defect_report',
  'd_b_chart', 'amm', 'cmm', 'ipc', 'specs'). Mais ProfileRegistry ne connaît
  que 7 document_type : job_card, work_order, service_bulletin, amm,
  delivery_package, cmm_ipc, mel. Aucun ne s'appelle exactement 'sb', 'ncr',
  'atl', 'rct', 'certificate', 'defect_report', 'd_b_chart', 'ipc', 'specs',
  et 'cmm_ipc' ne matche ni 'cmm' ni 'ipc'. En pratique la correction
  PATH_TO_ENUM ne peut donc s'appliquer QUE pour doc_type in {'job_card',
  'work_order'} (le seul autre candidat, 'amm', a déjà le même nom des deux
  côtés donc n'a pas d'effet de correction). Ce script réplique ce comportement
  tel quel — fidèle au bug/non-bug réel du système en production, sans le
  corriger silencieusement.

Usage :
  py eval_pipeline_complet.py                  # échantillon stratifié (30/classe)
  py eval_pipeline_complet.py --full            # tous les documents valides
  py eval_pipeline_complet.py --sample 50       # 50 par classe
  py eval_pipeline_complet.py --limit 200       # 200 documents au total (rapide, test)

Sorties :
  evaluation/pipeline_complet_results.csv   (1 ligne par document, prédiction détaillée)
  evaluation/pipeline_complet_report.txt    (métriques formatées, à coller dans le rapport)
  evaluation/pipeline_complet_report.json   (mêmes métriques, machine-readable)
"""

import sys
import os
import re
import time
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

# ── Doit être fait AVANT numpy/sklearn/sentence-transformers (cf. notes OOM) ──
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

PROJECT_ROOT = Path(r"C:\Users\ferie\Desktop\système_darchivage_intelligent")
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
import psycopg2.extras
import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "nouv_db",
    "user": "postgres",
    "password": "Nouv26",
}

OUTPUT_DIR = PROJECT_ROOT / "evaluation"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_CSV   = OUTPUT_DIR / "pipeline_complet_results.csv"
REPORT_TXT    = OUTPUT_DIR / "pipeline_complet_report.txt"
REPORT_JSON   = OUTPUT_DIR / "pipeline_complet_report.json"

# Normalisation des libellés doc_type stockés en base (souvent en MAJUSCULES
# avec underscore) vers les libellés humains utilisés par DocumentTypeEnum.
NORM = {
    "WORK_ORDER": "Work Order", "JOBCARD": "Jobcard", "JOB_CARD": "Jobcard",
    "DEFECT_REPORT": "Defect Report", "SPECS": "Specs",
    "CERTIFICATE": "Certificate", "AD": "AD", "SB": "SB",
    "AMM": "AMM", "CMM": "CMM", "IPC": "IPC",
    "ATL": "ATL", "NCR": "NCR", "RCT": "RCT", "D_B_CHART": "D&B Chart",
    "D&B_CHART": "D&B Chart", "OTHER": "Other",
}


def norm_type(x: str) -> str:
    if x is None:
        return "Other"
    s = str(x).strip().upper().replace(" ", "_").replace("-", "_").replace("&", "")
    return NORM.get(s, str(x).strip())


# ──────────────────────────────────────────────────────────────────────────────
# RÉCUPÉRATION DE L'ÉCHANTILLON
# ──────────────────────────────────────────────────────────────────────────────

def fetch_sample(sample_per_class: int | None, limit: int | None) -> list[dict]:
    """
    Récupère les documents à évaluer. Filtre sur original_path non vide —
    le fichier sur disque doit exister, sinon impossible de relancer l'OCR réel.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

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
    print("\n[BDD] Distribution des classes disponibles (avec original_path) :")
    for row in class_counts:
        print(f"  {row['doc_type']:<20} : {row['cnt']} docs")

    rows: list[dict] = []

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

    cur.close()
    conn.close()

    # Filtrer les fichiers réellement présents sur disque (les chemins peuvent
    # avoir bougé, ou pointer vers un montage réseau temporairement absent).
    existing = []
    missing = 0
    for r in rows:
        if r["original_path"] and os.path.exists(r["original_path"]):
            existing.append(r)
        else:
            missing += 1

    print(f"\n[OK] {len(existing)} documents sélectionnés, fichier présent sur disque")
    if missing:
        print(f"[ATTENTION] {missing} documents ignorés — fichier introuvable sur disque")

    return existing


# ──────────────────────────────────────────────────────────────────────────────
# ÉVALUATION — réplique fidèle de PipelineOrchestrator.test_document()
# sans dépendre d'AsyncSession SQLAlchemy : on garde une connexion asyncpg
# légère uniquement pour l'AircraftResolver (lecture seule, SELECT).
# ──────────────────────────────────────────────────────────────────────────────

async def evaluate_all(rows: list[dict]) -> list[dict]:
    import asyncpg

    # Imports tardifs : doivent arriver après les variables d'env OPENBLAS/OMP
    from backend.agents.ocr_agent import OCRAgent
    from backend.agents.ner_agent import NERAgent
    from backend.agents.classifier_agent import ClassifierAgent
    from backend.agents.linked_wp_resolver import resolve_linked_wp_category
    from backend.core.processing_profiles import ProfileRegistry
    from backend.core.pipeline import PATH_TO_ENUM
    from backend.schemas.document import DocumentTypeEnum, NERResult

    print("\n[Init] Chargement des agents (OCR, NER, Classifier)...")
    ocr_agent = OCRAgent()
    ner_agent = NERAgent()
    clf_agent = ClassifierAgent()
    print("[Init] Agents prêts.\n")

    apg_conn = await asyncpg.connect(
        host=DB_CONFIG["host"], port=DB_CONFIG["port"],
        database=DB_CONFIG["dbname"], user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )

    async def resolve_aircraft_from_db(es_reference, filename):
        """Réplique _resolve_aircraft_from_db de pipeline.py en asyncpg brut."""
        if es_reference:
            es_clean = es_reference.upper().strip()
            es_num = es_clean[2:] if es_clean.startswith("ES") else es_clean
            row = await apg_conn.fetchrow("""
                SELECT aircraft_registration, COUNT(*) AS cnt
                FROM documents
                WHERE aircraft_registration IS NOT NULL
                  AND aircraft_registration != ''
                  AND es_reference ILIKE $1
                GROUP BY aircraft_registration
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """, f"%{es_num}%")
            if row and row["aircraft_registration"]:
                return row["aircraft_registration"]

        m = re.search(r"(ES\d{4,8})", filename, re.IGNORECASE)
        if m:
            es_from_name = m.group(1).upper()
            es_num = es_from_name[2:]
            row = await apg_conn.fetchrow("""
                SELECT aircraft_registration, COUNT(*) AS cnt
                FROM documents
                WHERE aircraft_registration IS NOT NULL
                  AND aircraft_registration != ''
                  AND es_reference ILIKE $1
                GROUP BY aircraft_registration
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """, f"%{es_num}%")
            if row and row["aircraft_registration"]:
                return row["aircraft_registration"]
        return None

    async def resolve_linked_wp_category_apg(ocr_text, filename):
        """
        resolve_linked_wp_category attend une AsyncSession SQLAlchemy ;
        on réimplémente la requête directement en asyncpg pour éviter
        de monter une session SQLAlchemy complète juste pour l'éval.
        """
        from backend.agents.linked_wp_resolver import extract_linked_wp_es, normalize_es
        linked_refs = extract_linked_wp_es(ocr_text)
        if not linked_refs:
            return None
        for ref in linked_refs:
            norm = normalize_es(ref)
            if not norm:
                continue
            row = await apg_conn.fetchrow("""
                SELECT category FROM documents
                WHERE doc_type = 'WORK_ORDER'
                  AND category IN ('Check A', 'Check B', 'Check C', 'Check D')
                  AND (
                    es_reference ILIKE $1
                    OR REGEXP_REPLACE(LOWER(es_reference), '^es\\s*0*', '') = $2
                  )
                LIMIT 1
            """, f"%{norm}%", norm)
            if row and row["category"]:
                return row["category"]
        return None

    results = []
    n = len(rows)
    t0 = time.time()

    for i, row in enumerate(rows, 1):
        doc_id = row["id"]
        filename = row["filename"] or ""
        original_path = row["original_path"] or ""
        true_type = norm_type(row["doc_type"])

        rec = {
            "id": doc_id, "filename": filename, "true_type": true_type,
            "pred_type": None, "confidence": None, "ocr_confidence": None,
            "ocr_engine": None, "path_correction_applied": False,
            "error": None,
        }

        try:
            with open(original_path, "rb") as f:
                file_content = f.read()

            # ── Profil de traitement (étape 0.5) ──────────────────────────
            inferred_type, infer_conf = ProfileRegistry.infer_from_path(
                original_path or filename
            )
            profile = ProfileRegistry.get(inferred_type)

            # ── OCR réel ───────────────────────────────────────────────────
            ocr_result = await ocr_agent.process(
                file_content, filename, doc_type=inferred_type, profile=profile,
            )
            rec["ocr_confidence"] = ocr_result.confidence
            rec["ocr_engine"] = ocr_result.engine

            # ── NER réel ───────────────────────────────────────────────────
            try:
                ner_result = await ner_agent.process(
                    ocr_result.text, filename, profile=profile,
                )
                if not ner_result.aircraft_registration and original_path:
                    ner_result.aircraft_registration = \
                        ner_agent.infer_aircraft_from_path(original_path)
                if not ner_result.aircraft_registration:
                    m = re.search(r"(TS-IN[A-Z])", filename, re.IGNORECASE)
                    if m:
                        ner_result.aircraft_registration = m.group(1).upper()
            except Exception as e:
                ner_result = NERResult()

            # ── AircraftResolver (lecture DB) ─────────────────────────────
            if not ner_result.aircraft_registration:
                resolved = await resolve_aircraft_from_db(
                    ner_result.es_reference, filename
                )
                if resolved:
                    ner_result.aircraft_registration = resolved

            # ── Classification réelle ─────────────────────────────────────
            classifier_result = await clf_agent.process(
                ocr_result.text, filename, original_path, ner_result
            )

            # ── Correction PATH_TO_ENUM (logique pipeline.py exacte) ──────
            if classifier_result.predicted_type.value != inferred_type:
                if inferred_type != "unknown":
                    enum_value = PATH_TO_ENUM.get(inferred_type.lower())
                    if enum_value:
                        try:
                            classifier_result.predicted_type = DocumentTypeEnum(enum_value)
                            classifier_result.predicted_category = enum_value
                            rec["path_correction_applied"] = True
                        except ValueError:
                            pass

            # ── LinkedWP (catégorie seulement, n'affecte pas predicted_type) ─
            if classifier_result.predicted_type == DocumentTypeEnum.WORK_ORDER:
                try:
                    resolved_category = await resolve_linked_wp_category_apg(
                        ocr_result.text, filename
                    )
                    if resolved_category:
                        classifier_result.predicted_category = resolved_category
                except Exception:
                    pass

            rec["pred_type"] = classifier_result.predicted_type.value
            rec["confidence"] = round(float(classifier_result.confidence), 4)

        except Exception as e:
            rec["error"] = str(e)
            rec["pred_type"] = "Other"
            rec["confidence"] = 0.0

        results.append(rec)

        if i % 25 == 0 or i == n:
            elapsed = time.time() - t0
            rate = elapsed / i
            eta_min = rate * (n - i) / 60
            print(f"  [{i}/{n}] {rate:.1f}s/doc — ETA {eta_min:.1f} min restantes")

    await apg_conn.close()
    return results


# ──────────────────────────────────────────────────────────────────────────────
# MÉTRIQUES
# ──────────────────────────────────────────────────────────────────────────────

def compute_metrics(results: list[dict]) -> dict:
    valid = [r for r in results if r["error"] is None]
    y_true = [r["true_type"] for r in valid]
    y_pred = [r["pred_type"] for r in valid]

    classes = sorted(set(y_true) | set(y_pred))
    per_class = {}
    for cls in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p == cls)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != cls and p == cls)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p != cls)
        support = sum(1 for t in y_true if t == cls)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_class[cls] = {
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "support": support,
        }

    total = len(y_true)
    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / total if total else 0.0
    f1_macro = np.mean([m["f1"] for m in per_class.values()]) if per_class else 0.0
    w_precision = sum(m["precision"] * m["support"] for m in per_class.values()) / total if total else 0.0
    w_recall = sum(m["recall"] * m["support"] for m in per_class.values()) / total if total else 0.0
    w_f1 = sum(m["f1"] * m["support"] for m in per_class.values()) / total if total else 0.0

    confusion = defaultdict(int)
    for t, p in zip(y_true, y_pred):
        if t != p:
            confusion[(t, p)] += 1
    top_confusions = sorted(confusion.items(), key=lambda x: -x[1])[:10]

    n_errors = len(results) - len(valid)
    path_corrections = sum(1 for r in valid if r.get("path_correction_applied"))

    return {
        "date": datetime.now().isoformat(),
        "total_documents": len(results),
        "valid_documents": total,
        "pipeline_errors": n_errors,
        "path_corrections_applied": path_corrections,
        "metrics": {
            "accuracy": round(accuracy * 100, 2),
            "f1_macro": round(float(f1_macro) * 100, 2),
            "f1_weighted": round(w_f1 * 100, 2),
            "precision_weighted": round(w_precision * 100, 2),
            "recall_weighted": round(w_recall * 100, 2),
        },
        "per_class": per_class,
        "top_confusions": [
            {"true": t, "pred": p, "count": c} for (t, p), c in top_confusions
        ],
    }


def save_csv(results: list[dict]):
    import csv
    fieldnames = [
        "id", "filename", "true_type", "pred_type", "confidence",
        "ocr_confidence", "ocr_engine", "path_correction_applied", "error",
    ]
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"\n[OK] Détails par document → {RESULTS_CSV}")


def save_report(report: dict):
    lines = []
    lines.append("=" * 70)
    lines.append("  ÉVALUATION DU PIPELINE COMPLET (OCR réel → NER → AircraftResolver")
    lines.append("  → Classifier → correction PATH_TO_ENUM → LinkedWP)")
    lines.append("  Système d'archivage intelligent — NouvelAir MRO")
    lines.append("=" * 70)
    lines.append(f"\nDate                    : {report['date']}")
    lines.append(f"Documents totaux        : {report['total_documents']}")
    lines.append(f"Documents évalués       : {report['valid_documents']}")
    lines.append(f"Erreurs pipeline        : {report['pipeline_errors']}")
    lines.append(f"Corrections PATH_TO_ENUM appliquées : {report['path_corrections_applied']}")
    m = report["metrics"]
    lines.append(f"\nAccuracy                : {m['accuracy']:.1f}%")
    lines.append(f"F1-score (macro)         : {m['f1_macro']:.1f}%")
    lines.append(f"F1-score (weighted)      : {m['f1_weighted']:.1f}%")
    lines.append(f"Precision (weighted)     : {m['precision_weighted']:.1f}%")
    lines.append(f"Recall (weighted)        : {m['recall_weighted']:.1f}%")

    lines.append("\n" + "-" * 70)
    lines.append(f"{'Classe':<20} {'Precision':>10} {'Recall':>9} {'F1':>9} {'Support':>9}")
    lines.append("-" * 70)
    for cls, mc in sorted(report["per_class"].items()):
        lines.append(
            f"{cls:<20} {mc['precision']*100:>9.1f}% {mc['recall']*100:>8.1f}% "
            f"{mc['f1']*100:>8.1f}% {mc['support']:>9}"
        )

    if report["top_confusions"]:
        lines.append("\n" + "-" * 70)
        lines.append("Top confusions (réel → prédit) :")
        lines.append("-" * 70)
        for c in report["top_confusions"]:
            lines.append(f"  {c['true']:<20} → {c['pred']:<20} ({c['count']} fois)")

    lines.append("\n" + "=" * 70)

    text_report = "\n".join(lines)
    print("\n" + text_report)

    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write(text_report)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Rapport texte → {REPORT_TXT}")
    print(f"[OK] Rapport JSON  → {REPORT_JSON}")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Évaluation pipeline complet")
    parser.add_argument("--sample", type=int, default=30,
                         help="Documents par classe (échantillon stratifié, défaut: 30)")
    parser.add_argument("--full", action="store_true",
                         help="Évalue TOUS les documents valides (ignore --sample)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Limite le nombre total de documents (mode --full uniquement, pour tests rapides)")
    args = parser.parse_args()

    print("=" * 70)
    print("  ÉVALUATION PIPELINE COMPLET — NouvelAir MRO")
    print("=" * 70)

    sample_per_class = None if args.full else args.sample
    rows = fetch_sample(sample_per_class, args.limit if args.full else None)

    if not rows:
        print("[ERREUR] Aucun document à évaluer.")
        sys.exit(1)

    print(f"\n[Démarrage] Évaluation de {len(rows)} documents...")
    print("[ATTENTION] Ceci relance l'OCR réel sur chaque PDF — peut être lent.\n")

    results = asyncio.run(evaluate_all(rows))

    report = compute_metrics(results)
    save_csv(results)
    save_report(report)

    print("\n[TERMINÉ]")


if __name__ == "__main__":
    main()