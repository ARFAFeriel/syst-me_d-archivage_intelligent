# pipeline_combined.py
import asyncio
import hashlib
import sys
from pathlib import Path
from typing import Set

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.database import AsyncSessionLocal
from backend.core.pipeline import PipelineOrchestrator

# ============================================================
# CHECKPOINT
# ============================================================

async def get_processed_hashes() -> Set[str]:
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT sha256_hash FROM documents")
        )
        hashes = {row[0] for row in result.fetchall()}
    print(f"Documents déjà en base : {len(hashes)}")
    return hashes


def compute_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

# ============================================================
# FILTRER LES NOUVEAUX DOCS
# ============================================================

def get_new_documents(aircraft_folder: str,
                      processed_hashes: Set[str]) -> list:
    all_pdfs = list(Path(aircraft_folder).rglob("*.pdf"))
    new_docs = []
    for pdf in all_pdfs:
        sha256 = compute_sha256(str(pdf))
        if sha256 not in processed_hashes:
            new_docs.append((pdf, sha256))

    print(f"{Path(aircraft_folder).name} : "
          f"{len(all_pdfs)} total → "
          f"{len(new_docs)} nouveaux")
    return new_docs

# ============================================================
# TRAITER UN AVION
# ============================================================

async def process_aircraft_async(aircraft_folder: str,
                                  processed_hashes: Set[str]) -> dict:
    aircraft_name = Path(aircraft_folder).name
    new_docs = get_new_documents(aircraft_folder, processed_hashes)

    if not new_docs:
        print(f"✅ {aircraft_name} : déjà à jour")
        return {"aircraft": aircraft_name,
                "processed": 0,
                "errors": 0}

    orchestrator = PipelineOrchestrator()
    counters = {"processed": 0, "errors": 0}
    semaphore = asyncio.Semaphore(3)

    async def process_one(pdf_path, sha256):
        async with semaphore:
            try:
                size_mb = pdf_path.stat().st_size / (1024 * 1024)

                with open(pdf_path, 'rb') as f:
                    file_content = f.read()

                # Tronquer à 2 pages si gros fichier
                if size_mb > 5:
                    try:
                        import fitz
                        import io
                        doc = fitz.open(str(pdf_path))
                        max_pages = min(2, len(doc))
                        new_doc = fitz.open()
                        for i in range(max_pages):
                            new_doc.insert_pdf(doc, from_page=i, to_page=i)
                        buf = io.BytesIO()
                        new_doc.save(buf)
                        file_content = buf.getvalue()
                        print(f"  📄 Gros fichier "
                              f"({size_mb:.1f}MB) → 2 pages")
                    except Exception:
                        pass

                async with AsyncSessionLocal() as db:
                    result = await asyncio.wait_for(
                        orchestrator.process_document(
                            db=db,
                            file_content=file_content,
                            filename=pdf_path.name,
                            original_path=str(pdf_path),
                            file_size_kb=len(file_content) / 1024
                        ),
                        timeout=60.0
                    )

                counters["processed"] += 1
                print(f"  ✅ [{counters['processed']}/{len(new_docs)}]"
                      f" {pdf_path.name}")

            except asyncio.TimeoutError:
                counters["errors"] += 1
                print(f"  ⏱️  Timeout : {pdf_path.name}")
            except Exception as e:
                counters["errors"] += 1
                print(f"  ❌ {pdf_path.name} → {e}")

    tasks = [process_one(pdf, sha) for pdf, sha in new_docs]
    await asyncio.gather(*tasks)

    return {
        "aircraft": aircraft_name,
        "processed": counters["processed"],
        "errors": counters["errors"]
    }

# ============================================================
# ORCHESTRATION
# ============================================================

async def run_full_fleet_pipeline_async(archive_root: str):
    print("=== Chargement du checkpoint ===")
    processed_hashes = await get_processed_hashes()

    aircraft_folders = [
        str(f) for f in Path(archive_root).iterdir()
        if f.is_dir()
    ]
    print(f"\n=== Flotte détectée : "
          f"{len(aircraft_folders)} avions ===\n")

    results = []
    for folder in aircraft_folders:
        result = await process_aircraft_async(
            folder, processed_hashes
        )
        results.append(result)

    print_summary(results)

# ============================================================
# RAPPORT
# ============================================================

def print_summary(results: list):
    total_processed = sum(r["processed"] for r in results)
    total_errors    = sum(r["errors"] for r in results)

    print("\n" + "="*50)
    print("       RAPPORT DE MIGRATION FLOTTE")
    print("="*50)
    for r in results:
        print(f"  {r['aircraft']:<15} : "
              f"{r['processed']} traités | "
              f"{r['errors']} erreurs")
    print("-"*50)
    print(f"  TOTAL : {total_processed} traités | "
          f"{total_errors} erreurs")
    print("="*50)

# ============================================================
# POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    asyncio.run(run_full_fleet_pipeline_async(
        archive_root=r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft"
    ))