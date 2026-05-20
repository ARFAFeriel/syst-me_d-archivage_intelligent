"""
Import ciblé des fichiers manquants
Lit missing_files.txt et importe uniquement les PDFs absents de la base

Usage:
    py -m scripts.import_missing                    # Importer tout
    py -m scripts.import_missing --limit 100        # Limiter
    py -m scripts.import_missing --dry-run          # Voir sans importer
"""
import asyncio
import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from loguru import logger
from tqdm import tqdm


async def run(dry_run: bool, limit: int):
    from backend.database import init_db, AsyncSessionLocal
    from backend.agents.ocr_agent import OCRAgent
    from backend.agents.ner_agent import NERAgent
    from backend.agents.embedding_agent import EmbeddingAgent
    from backend.agents.archive_agent import ArchiveAgent
    from backend.agents.classifier_agent import ClassifierAgent
    from backend.schemas.document import OCRResult, NERResult, ClassifierResult

    # Lire la liste des fichiers manquants
    missing_file = Path("missing_files.txt")
    if not missing_file.exists():
        print("❌ missing_files.txt introuvable — lance d'abord la commande de génération")
        return

    with open(missing_file, encoding="utf-8") as f:
        all_paths = [line.strip() for line in f if line.strip()]

    paths = all_paths[:limit]

    print(f"\n{'═'*50}")
    print(f"  Import fichiers manquants")
    print(f"{'═'*50}")
    print(f"  Fichiers manquants : {len(all_paths)}")
    print(f"  À importer         : {len(paths)}")
    print(f"  Mode               : {'Dry-run' if dry_run else 'Import réel'}")
    print()

    if dry_run:
        print("Premiers fichiers à importer :")
        for p in paths[:10]:
            print(f"  {p}")
        if len(paths) > 10:
            print(f"  ... et {len(paths)-10} autres")
        return

    await init_db()

    ocr      = OCRAgent()
    ner      = NERAgent()
    embedder = EmbeddingAgent()
    archiver = ArchiveAgent()

    # Classifier si disponible
    try:
        from backend.agents.classifier_agent import ClassifierAgent
        classifier = ClassifierAgent()
    except Exception:
        classifier = None

    imported = 0
    duplicates = 0
    errors = 0

    pbar = tqdm(paths, desc="Import", unit="doc")

    for path_str in pbar:
        p = Path(path_str)
        if not p.exists():
            logger.warning(f"Fichier introuvable: {p}")
            errors += 1
            continue

        try:
            content = p.read_bytes()
            filename = p.name

            # Inférer métadonnées depuis le chemin
            aircraft_reg = ner.infer_aircraft_from_path(path_str)
            category, subcategory = ner.infer_category_from_path(path_str)

            # OCR
            doc_type_hint = "DEFAULT"
            if subcategory == "Jobcard":
                doc_type_hint = "JOBCARD"
            elif category == "AD":
                doc_type_hint = "AD"
            elif category == "SB":
                doc_type_hint = "SB"

            ocr_result = await ocr.process(content, filename, doc_type=doc_type_hint)

            # NER
            ner_result = await ner.process(ocr_result.text or "", filename)

            # Priorité au chemin pour l'immatriculation
            if aircraft_reg and not ner_result.aircraft_registration:
                ner_result.aircraft_registration = aircraft_reg

            # Classification
            if classifier:
                try:
                    classif_result = await classifier.classify(
                        text=ocr_result.text or "",
                        filename=filename,
                        ner_result=ner_result,
                    )
                except Exception:
                    from backend.models.document import DocumentType
                    classif_result = ClassifierResult(
                        predicted_type=DocumentType.OTHER,
                        predicted_category=category or "Unknown",
                        confidence=0.15,
                        scores={},
                    )
            else:
                from backend.models.document import DocumentType
                classif_result = ClassifierResult(
                    predicted_type=DocumentType.OTHER,
                    predicted_category=category or "Unknown",
                    confidence=0.15,
                    scores={},
                )

            # Embedding
            embedding = await embedder.embed_document(
                text=ocr_result.text or "",
                ner_result=ner_result,
                filename=filename,
            )

            # Archivage en base
            file_size_kb = p.stat().st_size / 1024
            async with AsyncSessionLocal() as db:
                doc, is_dup = await archiver.archive(
                    db=db,
                    content=content,
                    filename=filename,
                    original_path=f"\\\\?\\{path_str}",
                    ocr=ocr_result,
                    ner=ner_result,
                    classification=classif_result,
                    embedding=embedding,
                    file_size_kb=file_size_kb,
                )

                if is_dup:
                    duplicates += 1
                else:
                    # Mettre à jour subcategory si inféré depuis chemin
                    if subcategory and not doc.subcategory:
                        from sqlalchemy import update
                        from backend.models import Document
                        await db.execute(
                            update(Document)
                            .where(Document.id == doc.id)
                            .values(subcategory=subcategory)
                        )
                    await db.commit()
                    imported += 1

            pbar.set_postfix({"imp": imported, "dup": duplicates, "err": errors})

        except Exception as e:
            logger.error(f"[Import] {p.name}: {e}")
            errors += 1

    print(f"\n{'═'*50}")
    print(f"  Résultats Import")
    print(f"{'═'*50}")
    print(f"  Importés   : {imported}")
    print(f"  Doublons   : {duplicates}")
    print(f"  Erreurs    : {errors}")
    print(f"{'═'*50}\n")


def main():
    parser = argparse.ArgumentParser(description="Import fichiers manquants")
    parser.add_argument("--dry-run", action="store_true",
                        help="Voir sans importer")
    parser.add_argument("--limit", type=int, default=99999,
                        help="Nombre max de fichiers (défaut: tous)")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()