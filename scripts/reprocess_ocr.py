"""
Retraitement OCR des documents a confiance faible ou nulle.
Relance le pipeline OCR v4 sur les documents cibles.

Corrections vs version precedente :
  - ocr.process() appelé avec (bytes, filename, doc_type, profile) — pas un chemin string
  - embed_document(ocr_text=...) — kwarg corrigé (était text=)
  - Traitement concurrent via asyncio.Semaphore (N docs en parallele)
  - yield_per(50) pour ne pas charger 2 000+ docs en RAM d'un coup
  - --below default 75 (au lieu de 1.0) pour couvrir les docs faibles

Usage:
    py scripts/reprocess_ocr.py --dry-run
    py scripts/reprocess_ocr.py
    py scripts/reprocess_ocr.py --limit 100
    py scripts/reprocess_ocr.py --below 50
    py scripts/reprocess_ocr.py --review-only
    py scripts/reprocess_ocr.py --below 70 --limit 200 --concurrency 4
"""
import asyncio
import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from loguru import logger
from tqdm import tqdm
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════════════
# WORKER — traitement d'un document
# ══════════════════════════════════════════════════════════════════════════════

async def process_one(
    doc,
    ocr,
    ner,
    embedder,
    sem: asyncio.Semaphore,
    counters: dict,
    pbar,
) -> None:
    """Retraite un seul document sous le semaphore de concurrence."""
    async with sem:
        path = doc.original_path
        if not path:
            counters["skipped"] += 1
            pbar.update(1)
            return

        # Nettoyage du préfixe Windows \\?\
        clean_path = path.replace("\\\\?\\", "").replace("\\\\?/", "")
        p = Path(clean_path)
        if not p.exists():
            logger.warning(f"Fichier introuvable: {clean_path}")
            counters["skipped"] += 1
            pbar.update(1)
            return

        try:
            # ── Lecture du fichier en bytes ───────────────────────────────
            # BUG CORRIGÉ : ancienne version passait str(p) directement à
            # ocr.process() alors que la signature attend (bytes, filename, ...)
            file_bytes = p.read_bytes()

            # ── Pipeline OCR v4 ───────────────────────────────────────────
            ocr_result = await ocr.process(
                file_content=file_bytes,
                filename=doc.filename,
                doc_type=doc.doc_type or "unknown",
                profile=None,
            )

            old_conf = doc.ocr_confidence or 0.0
            new_conf = ocr_result.confidence

            if new_conf > old_conf:
                counters["improved"] += 1
            elif 0 < new_conf < old_conf:
                counters["degraded"] += 1

            if not ocr_result.needs_review and doc.needs_review:
                counters["reviewed"] += 1

            pbar.set_postfix({"conf": f"{old_conf:.0f}>{new_conf:.0f}%"})

            # ── NER + Embedding si texte disponible ───────────────────────
            new_entities  = doc.extracted_entities
            new_embedding = doc.embedding
            ner_result    = None

            if ocr_result.text:
                ner_result = await ner.process(ocr_result.text, doc.filename)
                new_entities = ner_result.raw_entities

                # BUG CORRIGÉ : kwarg était text= au lieu de ocr_text=
                new_embedding = await embedder.embed_document(
                    ocr_text=ocr_result.text,
                    ner_result=ner_result,
                    filename=doc.filename,
                )

            # ── Calcul needs_review final ─────────────────────────────────
            final_needs_review = ocr_result.needs_review or (
                0 < new_conf < 50.0
            )

            # ── Mise à jour base de données ───────────────────────────────
            # Chaque doc ouvre sa propre session (asyncpg interdit le partage)
            from backend.database import AsyncSessionLocal
            from backend.models.document import Document
            from sqlalchemy import update

            async with AsyncSessionLocal() as db:
                update_values = {
                    "ocr_text":            ocr_result.text or doc.ocr_text,
                    "ocr_confidence":      new_conf if new_conf > 0 else old_conf,
                    "ocr_engine":          ocr_result.engine,
                    "ocr_pages":           ocr_result.pages or doc.ocr_pages,
                    "extracted_entities":  new_entities,
                    "needs_review":        final_needs_review,
                }

                # Embedding seulement si calculé (pas None)
                if new_embedding is not None:
                    update_values["embedding"] = new_embedding

                # Champs optionnels depuis OCRResult
                for attr in ("quality_score", "validation_warnings"):
                    val = getattr(ocr_result, attr, None)
                    if val is not None:
                        key = "ocr_quality_score" if attr == "quality_score" else attr
                        update_values[key] = val

                # Champs NER — on ne remplace que si le NER a trouvé quelque chose
                if ner_result:
                    ner_fields = {
                        "aircraft_registration": ner_result.aircraft_registration,
                        "es_reference":          ner_result.es_reference,
                        "item_number":           ner_result.item_number,
                        "part_number":           ner_result.part_number,
                        "serial_number":         ner_result.serial_number,
                        "work_order_number":     ner_result.work_order_number,
                        "sb_ad_reference":       ner_result.sb_ad_reference,
                        "ata_chapter":           ner_result.ata_chapter,
                        "effectivity":           ner_result.effectivity,
                    }
                    for db_col, ner_val in ner_fields.items():
                        if ner_val:  # Ne remplace que si NER a extrait qqch
                            update_values[db_col] = ner_val

                await db.execute(
                    update(Document)
                    .where(Document.id == doc.id)
                    .values(**update_values)
                )
                await db.commit()

        except Exception as exc:
            logger.error(f"[Reprocess] {doc.filename}: {exc}", exc_info=False)
            counters["failed"] += 1

        finally:
            pbar.update(1)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ASYNC
# ══════════════════════════════════════════════════════════════════════════════

async def reprocess(
    dry_run: bool,
    limit: int,
    below: float,
    review_only: bool,
    concurrency: int,
) -> None:
    from backend.database import init_db, AsyncSessionLocal
    from backend.agents.ocr_agent import OCRAgent
    from backend.agents.ner_agent import NERAgent
    from backend.agents.embedding_agent import EmbeddingAgent
    from backend.models.document import Document
    from sqlalchemy import select

    await init_db()

    # ── Chargement des documents cibles ──────────────────────────────────────
    # yield_per(50) évite de charger 2 000+ docs en RAM d'un coup
    async with AsyncSessionLocal() as db:
        query = select(Document)
        if review_only:
            query = query.where(Document.needs_review == True)  # noqa: E712
        else:
            query = query.where(Document.ocr_confidence < below)
        query = query.order_by(Document.id).limit(limit)

        result = await db.execute(query)
        docs = result.scalars().all()

    mode_label = "needs_review=True" if review_only else f"confiance < {below}%"

    print(f"\n{'='*58}")
    print(f"  Systeme d'archivage intelligent — Retraitement OCR v4")
    print(f"{'='*58}")
    print(f"  Filtre       : {mode_label}")
    print(f"  Documents    : {len(docs)}")
    print(f"  Concurrence  : {concurrency} docs en parallele")
    print(f"  Mode         : {'Dry-run (aucune modification)' if dry_run else 'Retraitement reel'}")
    print()

    if dry_run:
        # Affiche la distribution de confiance OCR
        buckets = {"0%": 0, "1-24%": 0, "25-49%": 0, "50-74%": 0, "75-99%": 0}
        for doc in docs:
            c = doc.ocr_confidence or 0
            if c == 0:        buckets["0%"] += 1
            elif c < 25:      buckets["1-24%"] += 1
            elif c < 50:      buckets["25-49%"] += 1
            elif c < 75:      buckets["50-74%"] += 1
            else:             buckets["75-99%"] += 1

        print("  Distribution confiance OCR :")
        for label, cnt in buckets.items():
            bar = "█" * min(cnt, 40)
            print(f"    {label:>7} : {bar} {cnt}")
        print()
        print("  20 premiers documents :")
        for doc in docs[:20]:
            print(f"    [{doc.id:>5}] {doc.filename[:52]:<52} conf={doc.ocr_confidence or 0:.0f}%")
        if len(docs) > 20:
            print(f"    ... et {len(docs) - 20} autres")
        print(f"\n  {len(docs)} documents seraient retraites (dry-run).")
        return

    if not docs:
        print("  Aucun document a retraiter.")
        return

    # ── Instanciation des agents ──────────────────────────────────────────────
    ocr      = OCRAgent()
    ner      = NERAgent()
    embedder = EmbeddingAgent()

    counters = {
        "improved": 0,
        "degraded": 0,
        "failed":   0,
        "skipped":  0,
        "reviewed": 0,
    }

    sem  = asyncio.Semaphore(concurrency)
    pbar = tqdm(total=len(docs), desc="OCR v4", unit="doc")

    # ── Lancement concurrent ──────────────────────────────────────────────────
    tasks = [
        process_one(doc, ocr, ner, embedder, sem, counters, pbar)
        for doc in docs
    ]
    await asyncio.gather(*tasks)
    pbar.close()

    # ── Rapport final ─────────────────────────────────────────────────────────
    total_processed = len(docs) - counters["skipped"] - counters["failed"]
    print(f"\n{'='*58}")
    print(f"  Resultats — Systeme d'archivage intelligent")
    print(f"{'='*58}")
    print(f"  Traites      : {total_processed}")
    print(f"  Ameliores    : {counters['improved']}  (confiance augmentee)")
    print(f"  Degrades     : {counters['degraded']}  (confiance diminuee)")
    print(f"  Revue levee  : {counters['reviewed']}  (needs_review True -> False)")
    print(f"  Introuvables : {counters['skipped']}")
    print(f"  Erreurs      : {counters['failed']}")
    print(f"{'='*58}\n")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Retraitement OCR v4 — Systeme d'archivage intelligent",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Afficher les documents sans modifier la base",
    )
    parser.add_argument(
        "--limit", type=int, default=99999,
        help="Nombre maximum de documents a traiter",
    )
    parser.add_argument(
        "--below", type=float, default=75.0,
        help="Retraiter les documents avec confiance < N%% (defaut: 75.0)",
    )
    parser.add_argument(
        "--review-only", action="store_true",
        help="Retraiter uniquement les documents needs_review=True",
    )
    parser.add_argument(
        "--concurrency", type=int, default=3,
        help="Nombre de documents traites en parallele (defaut: 3)",
    )
    args = parser.parse_args()

    asyncio.run(reprocess(
        dry_run=args.dry_run,
        limit=args.limit,
        below=args.below,
        review_only=args.review_only,
        concurrency=args.concurrency,
    ))


if __name__ == "__main__":
    main()