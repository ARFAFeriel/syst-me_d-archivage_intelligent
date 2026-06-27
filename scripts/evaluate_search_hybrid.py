"""
scripts/evaluate_search_hybrid.py

Évalue le moteur de recherche hybride (FTS + sémantique + bonus NER) sur
un ground truth construit automatiquement et de façon fiable : on choisit
des documents réels de la base, on génère une requête à partir de leurs
propres métadonnées connues (référence ES, immatriculation, chapitre ATA,
type de document), puis on vérifie si la recherche retrouve bien CE document
précis. Le document source est par construction le résultat attendu :
aucun risque de désalignement entre le ground truth et les vraies données,
contrairement à un ground truth écrit à la main séparément de la base.

Usage :
    py scripts\\evaluate_search_hybrid.py --n 15
"""

import os

# IMPORTANT : doit être fait AVANT tout import numpy/scipy/torch/transformers,
# pour éviter le crash "OpenBLAS error: Memory allocation still failed"
# déjà rencontré sur ce projet lors du chargement de modèles d'embedding
# en environnement Windows avec multiprocessing.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"  # évite les appels réseau au chargement du modèle

import sys
import json
import asyncio
import argparse
import random
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

from backend.services.search_service import SearchService
from backend.schemas.search import SearchRequest
from backend.database import AsyncSessionLocal

DB_CONFIG = dict(host="localhost", port=5434, database="nouv_db", user="postgres", password="Nouv26")

RANDOM_SEED = 42
TOP_K = 10


def build_query_from_document(doc: dict) -> str | None:
    """
    Construit une requête de recherche réaliste à partir des métadonnées
    réelles d'un document, en combinant 2 à 3 informations identifiantes
    disponibles, pour simuler une recherche utilisateur plausible.
    """
    parts = []

    if doc.get("doc_type"):
        type_words = {
            "WORK_ORDER": "ordre de travail",
            "JOBCARD": "fiche de tâche",
            "AD": "directive de navigabilité",
            "SB": "bulletin de service",
            "CERTIFICATE": "certificat",
            "ATL": "carnet de route",
            "SPECS": "spécification",
            "DB_CHART": "diagramme",
            "DEFECT_REPORT": "rapport de défaut",
            "CMM": "manuel de composant",
        }
        parts.append(type_words.get(doc["doc_type"], doc["doc_type"]))

    # Pour les documents AD/SB, la référence pertinente est sb_ad_reference,
    # pas work_order_number (qui peut contenir des valeurs aberrantes issues
    # d'erreurs d'extraction NER en amont, par exemple 'FUEL' au lieu d'un
    # vrai numéro de Work Order, sur des documents qui n'en ont pas).
    is_plausible_wo = (
        doc.get("work_order_number")
        and any(ch.isdigit() for ch in doc["work_order_number"])
    )

    if doc.get("doc_type") in ("AD", "SB") and doc.get("sb_ad_reference"):
        parts.append(doc["sb_ad_reference"])
    elif doc.get("es_reference"):
        parts.append(doc["es_reference"])
    elif is_plausible_wo:
        parts.append(doc["work_order_number"])
    elif doc.get("sb_ad_reference"):
        parts.append(doc["sb_ad_reference"])

    if doc.get("ata_chapter"):
        parts.append(f"ATA {doc['ata_chapter']}")

    if doc.get("aircraft_registration"):
        parts.append(doc["aircraft_registration"])

    if len(parts) < 2:
        return None  # pas assez de métadonnées pour construire une requête fiable

    return " ".join(parts)


async def fetch_candidate_documents(n: int) -> list[dict]:
    """
    Récupère des documents variés avec suffisamment de métadonnées
    pour construire une requête identifiante.

    Deux cas sont traités différemment, suite à une observation empirique
    sur le corpus NouvelAir :
      - AD/SB : sb_ad_reference devrait identifier un document précis,
        mais peut être corrompue ou mal associée. On vérifie qu'elle
        apparaît bien dans le texte OCR du document avant de la retenir.
      - WORK_ORDER : es_reference identifie en réalité le Check dans son
        ensemble, pas un document individuel : plusieurs documents
        (Job Cards, Work Orders) peuvent légitimement partager la même
        valeur. Pour ces documents, on récupère l'ensemble des ids
        partageant la même es_reference, afin de considérer comme
        correcte toute réponse appartenant à ce groupe.
    """
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT id, filename, doc_type, ata_chapter, aircraft_registration,
               es_reference, work_order_number, sb_ad_reference, ocr_text
        FROM documents
        WHERE doc_type IS NOT NULL
          AND (
              (es_reference IS NOT NULL AND ata_chapter IS NOT NULL)
              OR (sb_ad_reference IS NOT NULL AND ata_chapter IS NOT NULL)
          )
        ORDER BY id
        LIMIT 100
    """)

    docs = [dict(r) for r in rows]
    random.seed(RANDOM_SEED)
    random.shuffle(docs)

    selected = []
    for doc in docs:
        if len(selected) >= n:
            break

        text = doc.get("ocr_text") or ""

        if doc["doc_type"] in ("AD", "SB"):
            ref = doc.get("sb_ad_reference")
            if not ref or ref not in text:
                continue  # référence non vérifiée dans le texte, on l'écarte
            valid_ids = {doc["id"]}
        else:
            ref = doc.get("es_reference")
            if not ref:
                continue
            group_rows = await conn.fetch(
                "SELECT id FROM documents WHERE es_reference = $1", ref
            )
            valid_ids = {r["id"] for r in group_rows}

        query = build_query_from_document(doc)
        if not query:
            continue

        selected.append({**doc, "_query": query, "_valid_ids": valid_ids})

    await conn.close()
    return selected


def compute_metrics(valid_ids: set, results: list) -> dict:
    """
    Calcule precision@k, rappel, MRR. Un résultat est considéré correct
    s'il appartient à l'ensemble valid_ids : pour un document AD/SB,
    cet ensemble ne contient que le document cible lui-même (référence
    vérifiée comme unique) ; pour un Work Order, il contient tous les
    documents partageant la même référence ES (même Check), car ce sont
    des réponses également pertinentes pour la requête.
    """
    ids = [r.document.id for r in results]
    rank = None
    for i, doc_id in enumerate(ids, 1):
        if doc_id in valid_ids:
            rank = i
            break

    return {
        "found": rank is not None,
        "rank": rank,
        "precision_at_1": 1.0 if rank == 1 else 0.0,
        "precision_at_3": 1.0 if rank is not None and rank <= 3 else 0.0,
        "precision_at_5": 1.0 if rank is not None and rank <= 5 else 0.0,
        "precision_at_10": 1.0 if rank is not None and rank <= 10 else 0.0,
        "reciprocal_rank": 1.0 / rank if rank else 0.0,
    }


async def main():
    parser = argparse.ArgumentParser(description="Évaluation du moteur de recherche hybride")
    parser.add_argument("--n", type=int, default=15, help="Nombre de requêtes de test à générer")
    args = parser.parse_args()

    print("=" * 70)
    print("  ÉVALUATION DU MOTEUR DE RECHERCHE HYBRIDE")
    print("  NouvelAir MRO — ground truth construit depuis des documents réels")
    print("=" * 70)

    print(f"\n[1/3] Sélection de {args.n} documents réels avec métadonnées exploitables...")
    candidates = await fetch_candidate_documents(args.n)
    print(f"      → {len(candidates)} documents retenus avec requête générée.")

    if not candidates:
        print("[ERREUR] Aucun document avec métadonnées suffisantes trouvé.")
        return

    print("\n[2/3] Initialisation du service de recherche...")
    search_service = SearchService()
    print("      → Service prêt.\n")

    # Les 3 modes testés pour chaque requête, afin de comparer les
    # approches lexicale seule, sémantique seule et hybride.
    MODES = {
        "lexical": dict(use_semantic=False, use_fts=True),
        "semantic": dict(use_semantic=True, use_fts=False),
        "hybrid": dict(use_semantic=True, use_fts=True),
    }

    per_query_results = {mode: [] for mode in MODES}

    async with AsyncSessionLocal() as db:
        for i, doc in enumerate(candidates, 1):
            query_text = doc["_query"]
            target_id = doc["id"]
            valid_ids = doc["_valid_ids"]

            group_note = f", groupe de {len(valid_ids)} document(s) acceptés" if len(valid_ids) > 1 else ""
            print(f"[{i}/{len(candidates)}] Requête : \"{query_text}\"  (doc cible id={target_id}, "
                  f"filename={doc['filename']}{group_note})")

            for mode_name, mode_kwargs in MODES.items():
                request = SearchRequest(query=query_text, limit=TOP_K, **mode_kwargs)

                t0 = time.perf_counter()
                try:
                    response = await search_service.search(db, request)
                except Exception as e:
                    print(f"      [{mode_name}] [ERREUR recherche] {e}")
                    continue
                elapsed_ms = (time.perf_counter() - t0) * 1000

                metrics = compute_metrics(valid_ids, response.results)
                metrics.update({
                    "query_id": f"Q{i:02d}",
                    "query": query_text,
                    "target_doc_id": target_id,
                    "target_filename": doc["filename"],
                    "target_doc_type": doc["doc_type"],
                    "valid_group_size": len(valid_ids),
                    "nb_returned": len(response.results),
                    "latency_ms": round(elapsed_ms, 1),
                    "mode": mode_name,
                })
                per_query_results[mode_name].append(metrics)

                status = f"rang {metrics['rank']}" if metrics["found"] else "NON TROUVÉ"
                print(f"      [{mode_name:>8}] → {status}  ({elapsed_ms:.0f} ms, {len(response.results)} résultats)")

            print()

    # ── Agrégation par mode ──────────────────────────────────────
    def avg(results, key):
        return round(sum(r[key] for r in results) / len(results), 4) if results else 0.0

    summaries = {}
    for mode_name, results in per_query_results.items():
        n = len(results)
        if n == 0:
            continue
        summaries[mode_name] = {
            "n_queries": n,
            "precision_at_1": avg(results, "precision_at_1"),
            "precision_at_3": avg(results, "precision_at_3"),
            "precision_at_5": avg(results, "precision_at_5"),
            "precision_at_10": avg(results, "precision_at_10"),
            "mrr": avg(results, "reciprocal_rank"),
            "recall_at_10": round(sum(1 for r in results if r["found"]) / n, 4),
            "mean_latency_ms": round(sum(r["latency_ms"] for r in results) / n, 1),
        }

    report = {
        "date": datetime.now().isoformat(),
        "summaries": summaries,
        "per_query": per_query_results,
    }

    out_path = os.path.join(os.path.dirname(__file__), "search_hybrid_eval_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print("\n" + "=" * 70)
    print("  SYNTHÈSE COMPARATIVE — LEXICALE vs SÉMANTIQUE vs HYBRIDE")
    print("=" * 70)
    header = f"  {'Métrique':<18}" + "".join(f"{m:>12}" for m in MODES)
    print(header)
    print("  " + "-" * (18 + 12 * len(MODES)))
    for key, label in [
        ("precision_at_1", "Precision@1"),
        ("precision_at_3", "Precision@3"),
        ("precision_at_5", "Precision@5"),
        ("precision_at_10", "Precision@10"),
        ("recall_at_10", "Recall@10"),
        ("mrr", "MRR"),
        ("mean_latency_ms", "Latence (ms)"),
    ]:
        row = f"  {label:<18}"
        for mode_name in MODES:
            s = summaries.get(mode_name, {})
            val = s.get(key, 0.0)
            if key == "mrr":
                row += f"{val:>12.3f}"
            elif key == "mean_latency_ms":
                row += f"{val:>12.0f}"
            else:
                row += f"{val*100:>11.1f}%"
        print(row)
    print("=" * 70)
    print(f"\n[OK] Rapport sauvegardé : {out_path}")


if __name__ == "__main__":
    asyncio.run(main())